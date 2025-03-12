# Flask网站视图

from flask import Blueprint, render_template, request, jsonify, redirect, url_for, current_app, abort
import json
import time
from app.improved_scraper import ImprovedEbayStoreScraper as EbayStoreScraper
from app.notification import EmailNotifier
import re

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
    # 获取所有监控的店铺
    store_keys = current_app.redis_client.keys("monitor:store:*")
    stores = []
    
    current_app.logger.info(f"找到 {len(store_keys)} 个监控店铺")
    
    for key in store_keys:
        try:
            # 不需要再decode了，因为我们设置了decode_responses=True
            key_str = key if isinstance(key, str) else key.decode('utf-8')
            store_name = key_str.split(':')[-1]
            
            store_data_json = current_app.redis_client.get(key_str)
            if store_data_json:
                # 同样不需要手动decode
                if isinstance(store_data_json, str):
                    store_data = json.loads(store_data_json)
                else:
                    store_data = json.loads(store_data_json.decode('utf-8'))
                
                # 获取商品列表
                items_json = current_app.redis_client.get(f"store:{store_name}:items")
                items = []
                
                if items_json:
                    # 同样处理可能的str或bytes
                    if isinstance(items_json, str):
                        items = json.loads(items_json)
                    else:
                        items = json.loads(items_json.decode('utf-8'))
                    current_app.logger.info(f"店铺 {store_name} 有 {len(items)} 个商品")
                else:
                    current_app.logger.warning(f"店铺 {store_name} 没有商品数据")
                
                # 获取最后更新时间
                last_update = current_app.redis_client.get(f"store:{store_name}:last_update")
                update_time = int(last_update) if last_update else 0
                
                store_info = {
                    'name': store_name,
                    'url': store_data.get('url', ''),
                    'total_items': len(items),
                    'items': items[:10],  # 只显示前10个商品
                    'last_update': update_time
                }
                
                stores.append(store_info)
        except Exception as e:
            current_app.logger.error(f"处理店铺数据时出错: {e}")
            import traceback
            current_app.logger.error(traceback.format_exc())
    
    return render_template('dashboard.html', stores=stores)

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