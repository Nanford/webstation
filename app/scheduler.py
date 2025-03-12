# 定时任务调度器

import atexit
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
import logging
from app.improved_scraper import ImprovedEbayStoreScraper as EbayStoreScraper
from app.notification import EmailNotifier
import json

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def init_scheduler(app):
    """初始化定时任务调度器"""
    scheduler = BackgroundScheduler()
    
    # 注册定时任务
    @scheduler.scheduled_job(
        'interval', hours=3,   # 每3小时执行一次
        jitter=900,            # 添加±15分钟随机抖动，避免固定时间请求
        id='scrape_stores_job'
    )
    def scrape_stores_job():
        """定时爬取所有店铺"""
        logger.info("开始执行定时爬取任务")
        
        # 获取所有需要监控的店铺
        store_keys = app.redis_client.keys("monitor:store:*")
        if not store_keys:
            logger.info("没有需要监控的店铺")
            return
        
        # 初始化爬虫和邮件通知
        scraper = EbayStoreScraper(redis_client=app.redis_client)
        notifier = EmailNotifier()
        
        # 遍历每个店铺并更新数据
        for key in store_keys:
            key_str = key.decode('utf-8') if isinstance(key, bytes) else key
            store_data_json = app.redis_client.get(key_str)
            
            if not store_data_json:
                continue
                
            try:
                store_data = json.loads(store_data_json.decode('utf-8'))
                store_url = store_data.get('url')
                store_name = store_data.get('name')
                notify_email = store_data.get('notify_email')
                
                if not store_url or not store_name:
                    continue
                
                logger.info(f"正在爬取店铺: {store_name}")
                
                # 更新店铺数据并检测变化
                changes = scraper.update_store_data(store_url, store_name)
                
                # 如果有设置通知邮箱并且有变动，发送邮件通知
                if notify_email:
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
                
                logger.info(f"店铺 {store_name} 更新完成. 新商品: {len(changes['new_listings'])}, "
                           f"价格变动: {len(changes['price_changes'])}, 下架商品: {len(changes['removed_listings'])}")
                
            except Exception as e:
                logger.error(f"处理店铺时发生错误: {e}")
    
    # 启动调度器
    scheduler.start()
    
    # 确保应用退出时调度器也会关闭
    atexit.register(lambda: scheduler.shutdown())
    
    logger.info("定时任务调度器已启动")
    return scheduler 