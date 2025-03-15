# Flask网站视图

from flask import Blueprint, render_template, request, jsonify, redirect, url_for, current_app, abort
import json
import time
from app.improved_scraper import ImprovedEbayStoreScraper as EbayStoreScraper
from app.notification import EmailNotifier
import re
import urllib.parse
from app.utils import is_valid_ebay_url

# 创建蓝图
main = Blueprint('main', __name__)

# 首页
@main.route('/')
def index():
    return render_template('index.html')

# 添加店铺监控
@main.route('/add_store', methods=['POST'])
def add_store():
    try:
        store_url = request.form.get('store_url')
        notify_email = request.form.get('notify_email')
        
        # 使用通用验证函数
        if not is_valid_ebay_url(store_url):
            return jsonify({
                'success': False,
                'message': '请提供有效的eBay店铺URL'
            })
        
        # 验证邮箱格式
        if notify_email and not re.match(r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$', notify_email):
            return jsonify({
                'success': False,
                'message': '请提供有效的邮箱地址'
            })
        
        # 如果提供了邮箱，将其保存为系统默认邮箱
        if notify_email:
            current_app.redis_client.set('system:notify_email', notify_email)
            current_app.logger.info(f"已设置系统通知邮箱: {notify_email}")
        else:
            # 尝试从Redis获取系统默认邮箱
            default_email = current_app.redis_client.get('system:notify_email')
            if default_email:
                notify_email = default_email.decode('utf-8') if isinstance(default_email, bytes) else default_email
                current_app.logger.info(f"使用系统默认通知邮箱: {notify_email}")
        
        # 提取店铺名称
        store_name = ''
        if 'store_name=' in store_url:
            store_name = store_url.split('store_name=')[1].split('&')[0]
        elif '_ssn=' in store_url:
            store_name = store_url.split('_ssn=')[1].split('&')[0]
        
        if not store_name:
            store_name = f"store_{int(time.time())}"
        
        current_app.logger.info(f"提取的店铺名称: {store_name}")
        
        # 创建店铺监控记录
        store_data = {
            'name': store_name,
            'url': store_url,
            'added_at': int(time.time()),
            'notify_email': notify_email
        }
        
        # 保存到Redis
        current_app.redis_client.set(
            f"monitor:store:{store_name}",
            json.dumps(store_data)
        )
        
        current_app.logger.info(f"开始创建爬虫并爬取数据: {store_name}")
        
        # 创建爬虫并立即爬取第一次数据
        scraper = EbayStoreScraper(redis_client=current_app.redis_client)
        scraper.update_store_data(store_url, store_name)
        
        return jsonify({
            'success': True,
            'message': f'已成功添加店铺 {store_name} 的监控',
            'store_name': store_name
        })
    except Exception as e:
        current_app.logger.error(f"添加店铺监控时出错: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'message': f'添加店铺监控失败: {str(e)}'
        })

# 店铺仪表板
@main.route('/dashboard')
def dashboard():
    # 获取当前页码，默认为1
    page = request.args.get('page', 1, type=int)
    per_page = 20  # 每页显示20个商品
    store_name = request.args.get('store_name')
    
    # 如果指定了店铺名称，显示该店铺的商品
    if store_name:
        store_data_json = current_app.redis_client.get(f"monitor:store:{store_name}")
        if not store_data_json:
            # 如果店铺不存在，重定向到仪表盘首页
            return redirect(url_for('main.dashboard'))
        
        # 获取该店铺的所有商品
        items_json = current_app.redis_client.get(f"store:{store_name}:items")
        if items_json:
            items_data = json.loads(items_json)
            
            # 统计总商品数
            total_items = len(items_data)
            
            # 计算总页数
            pages = (total_items + per_page - 1) // per_page
            
            # 对数据分页
            start = (page - 1) * per_page
            end = min(start + per_page, total_items)
            paginated_items = items_data[start:end]
            
            # 获取店铺信息
            try:
                store_data = json.loads(store_data_json)
                store_data['items_list'] = paginated_items
                store_data['item_count'] = total_items
                
                # 获取最后更新时间
                last_update = current_app.redis_client.get(f"store:{store_name}:last_update")
                if last_update:
                    store_data['last_update'] = int(last_update)
                
                return render_template('dashboard.html', 
                                      selected_store=store_data,
                                      stores=get_all_stores(),
                                      total=total_items,
                                      page=page, 
                                      per_page=per_page, 
                                      pages=pages)
            except:
                pass
    
    # 如果没有指定店铺或获取数据失败，获取所有被监控的店铺
    stores = get_all_stores()
    
    # 如果有店铺，显示第一个店铺的数据
    if stores:
        first_store = stores[0]
        return redirect(url_for('main.dashboard', store_name=first_store['name']))
        
    # 如果没有店铺，显示空仪表盘
    return render_template('dashboard.html', 
                          stores=stores,
                          selected_store=None,
                          total=0, 
                          page=1, 
                          per_page=per_page, 
                          pages=0)

def get_all_stores():
    """获取所有店铺信息"""
    stores = []
    store_keys = current_app.redis_client.keys("monitor:store:*")
    
    for key in store_keys:
        key_str = key.decode('utf-8') if isinstance(key, bytes) else key
        store_data_json = current_app.redis_client.get(key_str)
        if store_data_json:
            try:
                store_data = json.loads(store_data_json.decode('utf-8') if isinstance(store_data_json, bytes) else store_data_json)
                
                # 获取附加信息
                store_name = store_data.get('name')
                
                # 商品数量
                items_json = current_app.redis_client.get(f"store:{store_name}:items")
                item_count = 0
                if items_json:
                    items = json.loads(items_json.decode('utf-8') if isinstance(items_json, bytes) else items_json)
                    item_count = len(items)
                
                # 最后更新时间
                last_updated = current_app.redis_client.get(f"store:{store_name}:last_update")
                if last_updated:
                    last_updated_val = int(last_updated.decode('utf-8') if isinstance(last_updated, bytes) else last_updated)
                    store_data['last_update'] = last_updated_val
                
                store_data['item_count'] = item_count
                stores.append(store_data)
            except Exception as e:
                current_app.logger.error(f"获取店铺信息出错: {str(e)}")
    
    return stores

# 获取店铺列表API
@main.route('/api/stores')
def get_stores():
    stores = []
    store_keys = current_app.redis_client.keys("monitor:store:*")
    
    for key in store_keys:
        key_str = key.decode('utf-8') if isinstance(key, bytes) else key
        store_data_json = current_app.redis_client.get(key_str)
        if store_data_json:
            try:
                store_data = json.loads(store_data_json.decode('utf-8'))
                
                # 获取附加信息
                store_name = store_data.get('name')
                # 商品数量
                item_count = len(current_app.redis_client.keys(f"store:{store_name}:item:*"))
                # 最后更新时间
                last_updated = current_app.redis_client.get(f"store:{store_name}:last_updated")
                if last_updated:
                    store_data['last_updated'] = int(last_updated)
                
                store_data['item_count'] = item_count
                stores.append(store_data)
            except:
                pass
    
    return jsonify(stores)

# 获取商品价格历史API
@main.route('/api/item/<store_name>/<item_id>/price_history')
def get_price_history(store_name, item_id):
    history = []
    price_points = current_app.redis_client.zrange(
        f"store:{store_name}:item:{item_id}:price_history",
        0,
        -1,
        withscores=True
    )
    
    for data_json, timestamp in price_points:
        try:
            data = json.loads(data_json.decode('utf-8'))
            history.append({
                'timestamp': int(timestamp),
                'price': data.get('price', 0)
            })
        except:
            pass
    
    # 获取当前商品信息
    item_data = {}
    item_data_json = current_app.redis_client.get(f"store:{store_name}:item:{item_id}")
    if item_data_json:
        try:
            item_data = json.loads(item_data_json.decode('utf-8'))
        except:
            pass
    
    return jsonify({
        'item': item_data,
        'history': history
    })

# 手动触发爬取
@main.route('/api/scrape_now/<store_name>', methods=['POST'])
def scrape_now(store_name):
    # 获取店铺信息
    store_data_json = current_app.redis_client.get(f"monitor:store:{store_name}")
    if not store_data_json:
        return jsonify({
            'success': False,
            'message': '店铺不存在'
        })
    
    store_data = json.loads(store_data_json.decode('utf-8'))
    
    # 创建爬虫并立即爬取
    scraper = EbayStoreScraper(redis_client=current_app.redis_client)
    changes = scraper.update_store_data(store_data.get('url'), store_name)
    
    # 如果有设置通知邮箱并且有变动，发送邮件通知
    notify_email = store_data.get('notify_email')
    if notify_email:
        notifier = EmailNotifier()
        
        # 通知新上架商品
        if changes['new_listings']:
            notifier.notify_new_listings(
                notify_email, 
                store_name, 
                changes['new_listings']
            )
        
        # 通知价格变动
        if changes['price_changes']:
            notifier.notify_price_changes(
                notify_email, 
                store_name, 
                changes['price_changes']
            )
    
    return jsonify({
        'success': True,
        'message': f'已手动爬取店铺 {store_name}',
        'changes': {
            'new_listings': len(changes['new_listings']),
            'price_changes': len(changes['price_changes']),
            'removed_listings': len(changes['removed_listings'])
        }
    })

# 删除店铺监控
@main.route('/api/store/<store_name>', methods=['DELETE'])
def delete_store(store_name):
    # 删除店铺监控配置
    current_app.redis_client.delete(f"monitor:store:{store_name}")
    
    # 删除相关数据
    keys_to_delete = []
    keys_to_delete.extend(current_app.redis_client.keys(f"store:{store_name}:*"))
    
    for key in keys_to_delete:
        current_app.redis_client.delete(key)
    
    return jsonify({
        'success': True,
        'message': f'已删除店铺 {store_name} 的监控'
    })

@main.route('/item/<item_id>')
def item_details(item_id):
    store_keys = current_app.redis_client.keys("monitor:store:*")
    item_data = None
    
    for key in store_keys:
        try:
            store_name = key.split(':')[-1]
            item_key = f"store:{store_name}:item:{item_id}"
            item_json = current_app.redis_client.get(item_key)
            
            if item_json:
                item_data = json.loads(item_json)
                break
        except Exception as e:
            current_app.logger.error(f"获取商品数据时出错: {e}")
    
    if not item_data:
        abort(404)
        
    return render_template('item_details.html', item=item_data)

@main.app_template_filter('default_if_none')
def default_if_none(value, default_value="未知"):
    """如果值为None则返回默认值"""
    return value if value is not None else default_value 

@main.route('/refresh_store_data', methods=['POST'])
def refresh_store_data():
    """立即刷新店铺数据"""
    store_name = request.form.get('store_name')
    if not store_name:
        return jsonify({
            'success': False,
            'message': '参数错误：未提供店铺名称'
        })
    
    try:
        # 获取Redis客户端
        redis_client = current_app.redis_client
        
        # 获取店铺URL
        store_key = f"monitor:store:{store_name}"
        store_data_json = redis_client.get(store_key)
        
        if not store_data_json:
            return jsonify({
                'success': False,
                'message': f'未找到店铺: {store_name}'
            })
        
        store_data = json.loads(store_data_json)
        store_url = store_data.get('url')
        
        if not store_url:
            return jsonify({
                'success': False,
                'message': '店铺URL不正确'
            })
            
        current_app.logger.info(f"开始刷新店铺数据: {store_name}")
        current_app.logger.info(f"此操作可能需要10-30秒，请耐心等待...")
        
        # 使用爬虫更新数据
        scraper = EbayStoreScraper(redis_client=redis_client)
        changes = scraper.update_store_data(store_url, store_name)
        
        # 通知功能 - 获取通知邮箱
        notify_email = store_data.get('notify_email')
        if not notify_email:
            # 尝试获取系统默认邮箱
            default_email = redis_client.get('system:notify_email')
            if default_email:
                notify_email = default_email.decode('utf-8') if isinstance(default_email, bytes) else default_email
        
        # 如果有邮箱和变更，发送通知
        if notify_email and (changes['new_listings'] or changes['price_changes']):
            try:
                notifier = EmailNotifier()
                
                if changes['new_listings']:
                    current_app.logger.info(f"发送新商品通知到: {notify_email}")
                    notifier.notify_new_listings(notify_email, store_name, changes['new_listings'])
                    
                if changes['price_changes']:
                    current_app.logger.info(f"发送价格变动通知到: {notify_email}")
                    notifier.notify_price_changes(notify_email, store_name, changes['price_changes'])
            except Exception as e:
                current_app.logger.error(f"发送通知邮件失败: {e}")
        
        # 构建消息
        message = f"已刷新店铺 {store_name} 的数据。"
        if changes['new_listings']:
            message += f" {len(changes['new_listings'])} 个新商品。"
        if changes['price_changes']:
            message += f" {len(changes['price_changes'])} 个价格变动。"
        if changes['removed_listings']:
            message += f" {len(changes['removed_listings'])} 个下架商品。"
            
        if not any([changes['new_listings'], changes['price_changes'], changes['removed_listings']]):
            message += " 没有检测到变化。"
        
        current_app.logger.info(message)
        return jsonify({
            'success': True,
            'message': message
        })
    except Exception as e:
        current_app.logger.error(f"刷新店铺数据时出错: {e}")
        return jsonify({
            'success': False,
            'message': f'刷新店铺数据失败: {str(e)}'
        })

# 添加删除店铺监控API
@main.route('/remove_store', methods=['POST'])
def remove_store():
    """删除店铺监控"""
    store_name = request.form.get('store_name')
    if not store_name:
        return jsonify({
            'success': False,
            'message': '参数错误：未提供店铺名称'
        })
    
    try:
        # 获取Redis客户端
        redis_client = current_app.redis_client
        
        # 删除店铺相关的所有数据
        store_key = f"monitor:store:{store_name}"
        store_items_key = f"store:{store_name}:items"
        store_stats_key = f"store:{store_name}:stats"
        store_update_key = f"store:{store_name}:last_update"
        
        # 获取店铺的所有商品
        items_json = redis_client.get(store_items_key)
        if items_json:
            try:
                items = json.loads(items_json)
                # 删除每个商品的数据
                for item in items:
                    item_id = item.get('id')
                    if item_id:
                        redis_client.delete(f"store:{store_name}:item:{item_id}")
                        redis_client.delete(f"store:{store_name}:price_history:{item_id}")
            except:
                pass
        
        # 删除主要的店铺键
        redis_client.delete(store_key)
        redis_client.delete(store_items_key)
        redis_client.delete(store_stats_key)
        redis_client.delete(store_update_key)
        
        current_app.logger.info(f"已删除店铺监控: {store_name}")
        return jsonify({
            'success': True,
            'message': f'已删除店铺 {store_name} 的监控'
        })
    except Exception as e:
        current_app.logger.error(f"删除店铺监控时出错: {e}")
        return jsonify({
            'success': False,
            'message': f'删除失败: {str(e)}'
        })

# 添加以下路由来注册店铺监控

@main.route('/api/monitor_store', methods=['POST'])
def monitor_store():
    """注册店铺监控"""
    data = request.get_json()
    
    if not data or 'store_url' not in data or 'email' not in data:
        return jsonify({'error': '缺少必要参数'}), 400
    
    store_url = data['store_url']
    email = data['email']
    store_name = data.get('store_name', '')
    
    # 使用通用验证函数
    if not is_valid_ebay_url(store_url):
        return jsonify({
            'success': False,
            'message': '请提供有效的eBay店铺URL'
        }), 400
    
    # 如果没有提供店铺名称，尝试从URL提取
    if not store_name:
        if '_ssn=' in store_url:
            store_name = store_url.split('_ssn=')[1].split('&')[0]
        elif 'store_name=' in store_url:
            store_name = store_url.split('store_name=')[1].split('&')[0]
        else:
            # 使用时间戳作为唯一标识
            store_name = f"store_{int(time.time())}"
    
    # 创建店铺监控数据
    store_data = {
        'url': store_url,
        'name': store_name,
        'notify_email': email,
        'added_at': int(time.time())
    }
    
    # 存储到Redis
    redis_key = f"monitor:store:{store_name}"
    current_app.redis_client.set(redis_key, json.dumps(store_data))
    
    # 立即执行首次爬取以获取基准数据
    try:
        scraper = EbayStoreScraper(redis_client=current_app.redis_client)
        items = scraper.scrape_all_pages(store_url, max_pages=3)
        
        # 存储初始数据
        if items:
            current_app.redis_client.set(f"store:{store_name}:items", json.dumps(items))
            current_app.redis_client.set(f"store:{store_name}:last_update", int(time.time()))
            
            # 记录店铺商品数量
            current_app.logger.info(f"初始爬取成功，店铺 {store_name} 有 {len(items)} 个商品")
            
            return jsonify({
                'success': True,
                'message': f'店铺 {store_name} 已添加到监控列表',
                'store_name': store_name,
                'items_count': len(items)
            })
        else:
            return jsonify({
                'success': False,
                'message': '无法获取店铺商品数据，请检查URL是否正确'
            }), 400
    
    except Exception as e:
        current_app.logger.error(f"初始爬取失败: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'添加监控成功，但初始爬取失败: {str(e)}'
        }), 500

@main.route('/api/monitored_stores')
def list_monitored_stores():
    """列出所有监控的店铺"""
    stores = []
    
    # 获取所有监控的店铺
    store_keys = current_app.redis_client.keys("monitor:store:*")
    
    for key in store_keys:
        key_str = key.decode('utf-8') if isinstance(key, bytes) else key
        store_data_json = current_app.redis_client.get(key_str)
        
        if store_data_json:
            try:
                store_data = json.loads(store_data_json.decode('utf-8'))
                # 获取最近一次更新时间
                last_update_key = f"store:{store_data['name']}:last_update"
                last_update = current_app.redis_client.get(last_update_key)
                
                if last_update:
                    store_data['last_update'] = int(last_update)
                
                # 获取统计信息
                stats_key = f"store:{store_data['name']}:stats"
                stats_json = current_app.redis_client.get(stats_key)
                
                if stats_json:
                    store_data['stats'] = json.loads(stats_json.decode('utf-8'))
                
                stores.append(store_data)
            except Exception as e:
                current_app.logger.error(f"解析店铺数据失败: {str(e)}")
    
    return jsonify({
        'success': True,
        'stores': stores
    })

@main.route('/api/test_scheduler')
def test_scheduler():
    """测试定时任务"""
    try:
        # 从scheduler模块直接导入定时任务函数
        from app.scheduler import scrape_stores_job
        result = scrape_stores_job()
        
        return jsonify({
            'success': True,
            'message': '定时任务执行成功'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'定时任务执行失败: {str(e)}'
        }), 500 