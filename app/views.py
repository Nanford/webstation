# Flask网站视图

from flask import Blueprint, render_template, request, jsonify, redirect, url_for, current_app, abort
import json
import time
from app.improved_scraper import ImprovedEbayStoreScraper as EbayStoreScraper
from app.notification import EmailNotifier
import re
import urllib.parse

# 创建蓝图
main = Blueprint('main', __name__)

# 首页
@main.route('/')
def index():
    return render_template('index.html')

# 添加店铺监控
@main.route('/add_store', methods=['POST'])
def add_store():
    store_url = request.form.get('store_url')
    notify_email = request.form.get('notify_email')
    
    # 验证URL格式是否为eBay店铺
    if not store_url or not re.match(r'https?://(www\.)?ebay\.com/.*', store_url):
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
    
    # 提取店铺名称
    store_name = ''
    if 'store_name=' in store_url:
        store_name = store_url.split('store_name=')[1].split('&')[0]
    elif '_ssn=' in store_url:
        store_name = store_url.split('_ssn=')[1].split('&')[0]
    
    if not store_name:
        store_name = f"store_{int(time.time())}"
    
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
    
    # 创建爬虫并立即爬取第一次数据
    scraper = EbayStoreScraper(redis_client=current_app.redis_client)
    scraper.update_store_data(store_url, store_name)
    
    return jsonify({
        'success': True,
        'message': f'已成功添加店铺 {store_name} 的监控',
        'store_name': store_name
    })

# 店铺仪表板
@main.route('/dashboard')
def dashboard():
    """显示监控仪表盘"""
    # 获取店铺名参数
    store_name = request.args.get('store_name')
    
    # 查找所有监控的店铺
    stores = []
    selected_store = None
    store_keys = current_app.redis_client.keys("monitor:store:*")
    
    # 添加调试输出
    current_app.logger.info(f"查找店铺，参数store_name={store_name}")
    
    for key in store_keys:
        try:
            key_str = key.decode('utf-8') if isinstance(key, bytes) else key
            store_data_json = current_app.redis_client.get(key_str)
            
            if not store_data_json:
                continue
                
            store_data = json.loads(store_data_json)
            store_name_from_key = store_data.get('name')
            
            # 添加调试输出
            current_app.logger.info(f"处理店铺: {store_name_from_key}")
            
            # 获取店铺商品数据
            items_key = f"store:{store_name_from_key}:items"
            items_json = current_app.redis_client.get(items_key)
            
            items = []
            if items_json:
                items = json.loads(items_json)
            
            # 获取最后更新时间
            last_update_key = f"store:{store_name_from_key}:last_update"
            last_update = current_app.redis_client.get(last_update_key)
            
            if last_update:
                try:
                    last_update = int(last_update)
                except:
                    last_update = None
            else:
                last_update = None
            
            store_info = {
                'name': store_name_from_key,
                'url': store_data.get('url'),
                'items_count': len(items),
                'items_list': items,
                'last_update': last_update
            }
            
            stores.append(store_info)
            
            # 如果是指定的店铺，设置为选中的店铺
            if store_name and (store_name.lower() == store_name_from_key.lower() or 
                              urllib.parse.unquote(store_name).lower() == store_name_from_key.lower()):
                current_app.logger.info(f"找到匹配的店铺: {store_name} = {store_name_from_key}")
                selected_store = {
                    'name': store_name_from_key,
                    'url': store_data.get('url'),
                    'items_count': len(items),
                    'items_list': items,
                    'last_update': last_update
                }
            
            current_app.logger.info(f"店铺 {store_name_from_key} 有 {len(items)} 个商品")
            
        except Exception as e:
            current_app.logger.error(f"处理店铺数据时出错: {e}")
    
    current_app.logger.info(f"找到 {len(stores)} 个监控店铺")
    
    # 如果没有选择特定店铺，但有店铺数据，则默认选择第一个店铺
    if not selected_store and stores:
        first_store = stores[0]
        selected_store = {
            'name': first_store['name'],
            'url': first_store['url'],
            'items_count': first_store['items_count'],
            'items_list': first_store['items_list'],
            'last_update': first_store['last_update']
        }
        current_app.logger.info(f"默认选择第一个店铺: {selected_store['name']}")
    
    # 设置一个默认的last_update_time
    last_update_time = None
    if selected_store and selected_store.get('last_update'):
        last_update_time = selected_store['last_update']
    elif stores and stores[0].get('last_update'):
        last_update_time = stores[0]['last_update']
    
    return render_template('dashboard.html', 
                          stores=stores, 
                          selected_store=selected_store,
                          last_update_time=last_update_time)

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

@main.route('/refresh_store', methods=['POST'])
def refresh_store():
    """刷新店铺数据"""
    store_name = request.form.get('store_name')
    
    # 获取店铺信息
    store_key = f"monitor:store:{store_name}"
    store_data_json = current_app.redis_client.get(store_key)
    
    if not store_data_json:
        return jsonify({
            'success': False,
            'message': '未找到店铺信息'
        })
    
    try:
        store_data = json.loads(store_data_json)
        store_url = store_data.get('url')
        
        # 记录开始时间
        start_time = time.time()
        
        # 使用爬虫更新店铺数据
        scraper = EbayStoreScraper(current_app.redis_client)
        changes = scraper.update_store_data(store_url, store_name)
        
        # 计算耗时
        elapsed_time = time.time() - start_time
        
        # 返回结果
        return jsonify({
            'success': True,
            'message': f'店铺数据已更新，耗时 {elapsed_time:.1f} 秒。发现 {len(changes["new_listings"])} 个新商品，{len(changes["price_changes"])} 个价格变动'
        })
    except Exception as e:
        current_app.logger.error(f"更新店铺数据出错: {e}")
        return jsonify({
            'success': False,
            'message': f'更新店铺数据失败: {str(e)}'
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