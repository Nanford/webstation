# Flask应用初始化

from flask import Flask, jsonify, request
import redis
from app.config import Config, REDIS_HOST, REDIS_PORT, REDIS_DB, REDIS_PASSWORD
import time
import json
from app.scheduler import init_scheduler

def create_app(test_config=None):
    app = Flask(__name__, 
                template_folder='../templates', 
                static_folder='../static')
    app.config.from_object(Config)
    
    # 连接Redis
    try:
        redis_client = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            db=REDIS_DB,
            password=REDIS_PASSWORD,
            socket_timeout=5,
            decode_responses=True  # 自动解码为Python字符串
        )
        # 测试连接
        redis_client.ping()
        app.logger.info("Redis连接成功")
    except Exception as e:
        app.logger.error(f"Redis连接失败: {e}")
        # 使用无密码连接作为备选
        try:
            redis_client = redis.Redis(
                host=REDIS_HOST,
                port=REDIS_PORT,
                db=REDIS_DB,
                socket_timeout=5,
                decode_responses=True
            )
            app.logger.info("Redis无密码连接成功")
        except Exception as e:
            app.logger.error(f"Redis备选连接也失败: {e}")
            redis_client = None

    # 确保使用正确的初始化函数
    init_scheduler(app)
    
    # 注册蓝图
    from app.views import main
    app.register_blueprint(main)
    
    # 将Redis客户端添加到应用
    app.redis_client = redis_client
    
    # 添加自定义过滤器
    @app.template_filter('timestamp_to_date')
    def timestamp_to_date_filter(timestamp):
        if not timestamp:
            return "未知"
        from datetime import datetime
        return datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
    
    # 在应用初始化中添加一个自定义过滤器
    @app.template_filter('price_format')
    def price_format(value):
        """格式化价格显示"""
        return f"${value:.2f}" if value else "$0.00"
    
    @app.route('/scrape_all')
    def scrape_all():
        """爬取所有页面的商品信息"""
        from app.improved_scraper import ImprovedEbayStoreScraper
        
        # 获取请求参数，允许自定义店铺URL和最大页数
        url = request.args.get('url')
        if not url:
            # 使用默认的eBay店铺URL
            url = 'https://www.ebay.com/sch/i.html?_dkr=1&iconV2Request=true&_blrs=recall_filtering&_ssn=starbellone&store_name=starbellone&_oac=1'
        
        # 可选: 设置最大页数限制，默认为5页，设置为0表示不限制页数
        try:
            max_pages = int(request.args.get('max_pages', 5))
            if max_pages <= 0:
                max_pages = None  # 不限制页数
        except ValueError:
            max_pages = 5  # 默认值
        
        try:
            # 创建爬虫实例并连接Redis
            scraper = ImprovedEbayStoreScraper(redis_client=app.redis_client)
            app.logger.info(f"开始多页爬取eBay店铺: {url}, 最大页数: {max_pages if max_pages else '不限'}")
            
            # 使用改进后的多页爬取方法
            all_items = scraper.scrape_all_pages(url, max_pages)
            
            # 提取店铺名称
            store_name = ''
            if 'store_name=' in url:
                store_name = url.split('store_name=')[1].split('&')[0]
            elif '_ssn=' in url:
                store_name = url.split('_ssn=')[1].split('&')[0]
                
            if not store_name:
                store_name = f"store_{int(time.time())}"
            
            # 保存爬取结果到Redis
            timestamp = int(time.time())
            key = f"all_items_{timestamp}"
            
            if app.redis_client:
                # 保存所有商品列表
                app.redis_client.set(key, json.dumps(all_items))
                app.logger.info(f"已将{len(all_items)}个商品数据保存到Redis (key: {key})")
                
                # 如果是已知店铺，也更新店铺的商品列表
                store_exists = app.redis_client.exists(f"monitor:store:{store_name}")
                if store_exists:
                    app.logger.info(f"更新店铺 {store_name} 的商品数据")
                    app.redis_client.set(f"store:{store_name}:items", json.dumps(all_items))
                    app.redis_client.set(f"store:{store_name}:last_update", timestamp)
            
            return jsonify({
                'success': True,
                'message': f'成功爬取了 {len(all_items)} 个商品信息',
                'items_count': len(all_items),
                'store_name': store_name,
                'redis_key': key,
                'timestamp': timestamp
            })
        except Exception as e:
            app.logger.error(f"爬取过程中出错: {str(e)}", exc_info=True)
            return jsonify({
                'success': False,
                'message': f'爬取过程中出错: {str(e)}'
            }), 500
    
    return app 