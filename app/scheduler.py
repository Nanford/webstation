# 定时任务调度器

import atexit
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
import logging
import os
from logging.handlers import TimedRotatingFileHandler
from app.improved_scraper import ImprovedEbayStoreScraper as EbayStoreScraper
from app.notification import EmailNotifier
import json
import time

# 创建logs目录
log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'logs')
os.makedirs(log_dir, exist_ok=True)

# 配置任务日志
scheduler_logger = logging.getLogger('app.scheduler')
scheduler_logger.setLevel(logging.INFO)

# 添加日志处理器，每天轮换一次日志
scheduler_log_file = os.path.join(log_dir, 'scheduler_job.log')
job_handler = TimedRotatingFileHandler(
    scheduler_log_file, 
    when='midnight',  # 每天午夜轮换
    interval=1,       # 每1天
    backupCount=30    # 保留30天的日志
)
job_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
scheduler_logger.addHandler(job_handler)

# 添加控制台处理器
console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
scheduler_logger.addHandler(console_handler)

# 配置普通日志
logging.basicConfig(level=logging.WARNING, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def init_scheduler(app):
    """初始化定时任务调度器"""
    scheduler = BackgroundScheduler()
    
    # 注册定时任务
    @scheduler.scheduled_job(
        CronTrigger(hour=0, minute=50),  # 每天凌晨0:50执行（美国时间）
        id='scrape_stores_job'
    )
    def scrape_stores_job():
        """定时爬取所有店铺"""
        job_start_time = time.time()
        scheduler_logger.info("============== 定时任务开始执行 ==============")
        scheduler_logger.info(f"任务执行时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())}")
        
        # 获取所有需要监控的店铺
        store_keys = app.redis_client.keys("monitor:store:*")
        if not store_keys:
            scheduler_logger.info("没有需要监控的店铺")
            return
        
        scheduler_logger.info(f"发现 {len(store_keys)} 个需要监控的店铺")
        
        # 初始化爬虫和邮件通知
        scraper = EbayStoreScraper(redis_client=app.redis_client)
        notifier = EmailNotifier()
        
        # 记录总体统计信息
        total_stats = {
            'total_stores': len(store_keys),
            'processed_stores': 0,
            'success_stores': 0,
            'failed_stores': 0,
            'new_listings_total': 0,
            'price_changes_total': 0,
            'removed_listings_total': 0,
            'emails_sent': 0,
            'comparison_checks': 0,
            'comparison_notifications': 0
        }
        
        # 遍历每个店铺并更新数据
        for i, key in enumerate(store_keys, 1):
            key_str = key.decode('utf-8') if isinstance(key, bytes) else key
            store_data_json = app.redis_client.get(key_str)
            
            if not store_data_json:
                scheduler_logger.warning(f"店铺键 {key_str} 没有关联数据")
                continue
                
            try:
                store_data = json.loads(store_data_json.decode('utf-8') if isinstance(store_data_json, bytes) else store_data_json)
                store_url = store_data.get('url')
                store_name = store_data.get('name')
                notify_email = store_data.get('notify_email')
                
                if not store_url or not store_name:
                    scheduler_logger.warning(f"店铺数据不完整: {store_data}")
                    continue
                
                store_start_time = time.time()
                scheduler_logger.info(f"[{i}/{len(store_keys)}] 开始爬取店铺: {store_name}")
                
                # 更新店铺数据并检测变化
                changes = scraper.update_store_data(store_url, store_name)
                
                # 更新统计信息
                total_stats['processed_stores'] += 1
                total_stats['new_listings_total'] += len(changes['new_listings'])
                total_stats['price_changes_total'] += len(changes['price_changes'])
                total_stats['removed_listings_total'] += len(changes['removed_listings'])
                
                # 如果有设置通知邮箱并且有变动，发送邮件通知
                emails_sent = 0
                if notify_email:
                    # 仅当检测到真正的"new listing"商品时发送新上架通知
                    if any(item.get('is_new_listing') for item in changes['new_listings']):
                        new_listings_sent = notifier.notify_new_listings(
                            notify_email, 
                            store_name, 
                            changes['new_listings']
                        )
                        if new_listings_sent:
                            emails_sent += 1
                            scheduler_logger.info(f"成功发送新上架商品通知: {store_name}")
                        else:
                            scheduler_logger.error(f"发送新上架商品通知失败: {store_name}")
                    
                    # 通知价格变动
                    if changes['price_changes']:
                        price_changes_sent = notifier.notify_price_changes(
                            notify_email, 
                            store_name, 
                            changes['price_changes']
                        )
                        if price_changes_sent:
                            emails_sent += 1
                            scheduler_logger.info(f"成功发送价格变动通知: {store_name}")
                        else:
                            scheduler_logger.error(f"发送价格变动通知失败: {store_name}")
                
                if emails_sent > 0:
                    total_stats['emails_sent'] += emails_sent
                
                store_end_time = time.time()
                store_duration = store_end_time - store_start_time
                
                scheduler_logger.info(
                    f"店铺 {store_name} 更新完成 (耗时: {store_duration:.2f}秒). "
                    f"新商品: {len(changes['new_listings'])}, "
                    f"价格变动: {len(changes['price_changes'])}, "
                    f"下架商品: {len(changes['removed_listings'])}"
                )
                total_stats['success_stores'] += 1
                
            except Exception as e:
                scheduler_logger.error(f"处理店铺时发生错误: {e}", exc_info=True)
                total_stats['failed_stores'] += 1
        
        # 记录任务结束和总体统计
        job_end_time = time.time()
        job_duration = job_end_time - job_start_time
        
        scheduler_logger.info("============== 定时任务执行完毕 ==============")
        scheduler_logger.info(f"总耗时: {job_duration:.2f}秒")
        scheduler_logger.info(f"成功处理店铺: {total_stats['success_stores']}/{total_stats['total_stores']}")
        scheduler_logger.info(f"新上架商品: {total_stats['new_listings_total']}")
        scheduler_logger.info(f"价格变动商品: {total_stats['price_changes_total']}")
        scheduler_logger.info(f"下架商品: {total_stats['removed_listings_total']}")
        scheduler_logger.info(f"发送邮件: {total_stats['emails_sent']}封")
        scheduler_logger.info("============================================")
        
        # 如果任务失败数>0，额外记录警告信息
        if total_stats['failed_stores'] > 0:
            scheduler_logger.warning(f"警告：有 {total_stats['failed_stores']} 个店铺处理失败！")
        
        # 执行价格对比检查
        scheduler_logger.info("============== 开始执行价格对比检查 ==============")
        comparison_start_time = time.time()
        
        try:
            from app.comparison import PriceComparison
            comparison = PriceComparison(redis_client=app.redis_client)
            
            # 执行所有价格对比检查
            comparison_results = comparison.perform_all_comparisons()
            
            comparison_end_time = time.time()
            comparison_duration = comparison_end_time - comparison_start_time
            
            scheduler_logger.info("============== 价格对比检查完毕 ==============")
            scheduler_logger.info(f"对比检查耗时: {comparison_duration:.2f}秒")
            scheduler_logger.info(f"总对比配置: {comparison_results['total_comparisons']}")
            scheduler_logger.info(f"成功检查: {comparison_results['successful_checks']}")
            scheduler_logger.info(f"失败检查: {comparison_results['failed_checks']}")
            scheduler_logger.info(f"发送通知: {len(comparison_results['notifications_needed'])}个")
            
            # 统计邮件发送成功率
            email_success = sum(1 for n in comparison_results['notifications_needed'] if n.get('email_sent', False))
            email_total = len(comparison_results['notifications_needed'])
            if email_total > 0:
                scheduler_logger.info(f"邮件发送成功率: {email_success}/{email_total} ({email_success/email_total*100:.1f}%)")
            
            scheduler_logger.info("============================================")
            
            # 更新总体统计
            total_stats['comparison_checks'] = comparison_results['successful_checks']
            total_stats['comparison_notifications'] = len(comparison_results['notifications_needed'])
            
        except Exception as e:
            scheduler_logger.error(f"执行价格对比检查时出错: {str(e)}", exc_info=True)
        
        return total_stats
    
    # 启动调度器
    scheduler.start()
    
    # 确保应用退出时调度器也会关闭
    atexit.register(lambda: scheduler.shutdown())
    
    logger.info("定时任务调度器已启动")
    scheduler_logger.info("============== 定时任务调度器已启动 ==============")
    scheduler_logger.info(f"下次任务执行时间: 每天凌晨0:50 (美国时间)")
    
    return scheduler