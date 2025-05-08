#!/usr/bin/env python3
# 测试爬虫和邮件通知脚本

import sys
import json
import time
import redis
import logging
import argparse
from app.improved_scraper import ImprovedEbayStoreScraper
from app.notification import EmailNotifier
from app.config import Config
from app.utils import json_dumps  # 导入自定义JSON序列化函数

# 配置日志
log_level = logging.INFO 
logging.basicConfig(
    level=log_level,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger('test_scheduler')

def test_scrape_and_notify(store_url, email, store_name=None, max_pages=3):
    """测试爬取并通知新商品"""
    
    if not store_name:
        # 从URL中提取店铺名称
        if '_ssn=' in store_url:
            store_name = store_url.split('_ssn=')[1].split('&')[0]
        elif 'store_name=' in store_url:
            store_name = store_url.split('store_name=')[1].split('&')[0]
        else:
            store_name = f"store_test_{int(time.time())}"
    
    logger.info(f"开始测试爬取店铺: {store_name}")
    logger.info(f"URL: {store_url}")
    logger.info(f"通知邮箱: {email}")
    
    try:
        # 连接Redis
        redis_client = redis.Redis(
            host=Config.REDIS_HOST,
            port=Config.REDIS_PORT,
            db=Config.REDIS_DB,
            password=Config.REDIS_PASSWORD,
            decode_responses=True
        )
        
        # 测试Redis连接
        redis_client.ping()
        logger.info("Redis连接成功")
        
        # 初始化爬虫
        scraper = ImprovedEbayStoreScraper(redis_client=redis_client)
        
        # 先检查是否已有该店铺的之前数据
        previous_items = []
        previous_items_json = redis_client.get(f"store:{store_name}:items")
        if previous_items_json:
            try:
                previous_items = json.loads(previous_items_json)
                logger.info(f"找到之前的数据，共 {len(previous_items)} 个商品")
            except:
                logger.warning("解析之前的数据失败")
        
        # 爬取当前数据 - 强制至少爬取3页
        logger.info(f"开始爬取店铺，设置为爬取 {max_pages} 页...")
        if max_pages < 3:
            max_pages = 3
            logger.info(f"为确保获取更多商品，已调整为爬取 {max_pages} 页")
            
        current_items = scraper.scrape_all_pages(store_url, max_pages=max_pages)
        
        if not current_items:
            logger.error("没有获取到任何商品，请检查URL是否正确")
            return False
        
        logger.info(f"成功获取 {len(current_items)} 个商品")
        
        # 保存最新数据到Redis
        redis_client.set(f"store:{store_name}:items", json_dumps(current_items))
        redis_client.set(f"store:{store_name}:last_update", int(time.time()))
        
        # 筛选真正的"New listing"商品
        true_new_listings = []
        for item in current_items:
            if item.get('is_new_listing'):
                true_new_listings.append(item)
                logger.info(f"发现New Listing商品: {item.get('title')}")
        
        # 筛选昨日上架的商品（新增功能）
        yesterday_listings = []
        for item in current_items:
            # 如果已经标记为New listing就不重复添加
            if item.get('is_yesterday_listing') and not item.get('is_new_listing'):
                yesterday_listings.append(item)
                logger.info(f"发现昨日上架商品: {item.get('title')} - 上架时间: {item.get('listing_date')}")
        
        # 如果同时有New Listing和昨日上架商品，合并它们
        all_new_items = true_new_listings + yesterday_listings
        
        # 比较价格变动
        price_changes = []
        if previous_items:
            previous_ids = {item.get('id'): item for item in previous_items if item.get('id')}
            
            for item in current_items:
                item_id = item.get('id')
                if not item_id:
                    continue
                    
                if item_id in previous_ids:
                    prev_item = previous_ids[item_id]
                    # 比较价格是否有变化
                    if prev_item.get('price') != item.get('price'):
                        price_change = {
                            'id': item_id,
                            'title': item.get('title'),
                            'url': item.get('url'),
                            'old_price': prev_item.get('price'),
                            'new_price': item.get('price'),
                            'currency': item.get('currency', '$'),
                            'image_url': item.get('image_url')
                        }
                        price_changes.append(price_change)
                        logger.info(f"发现价格变动商品: {item.get('title')} - 从 {prev_item.get('price')} 变为 {item.get('price')}")
        
        # 如果没有新上架商品且没有价格变动，结束测试
        if not all_new_items and not price_changes:
            logger.info("没有发现New Listing商品、昨日上架商品或价格变动商品，不发送邮件通知")
            return True
        
        # 初始化邮件通知
        notifier = EmailNotifier()
        
        # 发送新上架商品通知（包括New Listing和昨日上架）
        if all_new_items:
            logger.info(f"发送 {len(all_new_items)} 个新上架商品的邮件通知到 {email}")
            result = notifier.notify_new_listings(email, store_name, all_new_items)
            
            if result:
                logger.info("新上架商品邮件发送成功！")
            else:
                logger.error("新上架商品邮件发送失败！")
        
        # 发送价格变动通知
        if price_changes:
            logger.info(f"发送 {len(price_changes)} 个价格变动商品的邮件通知到 {email}")
            result = notifier.notify_price_changes(email, store_name, price_changes)
            
            if result:
                logger.info("价格变动邮件发送成功！")
            else:
                logger.error("价格变动邮件发送失败！")
        
        return True
        
    except Exception as e:
        logger.error(f"测试过程中发生错误: {str(e)}", exc_info=True)
        return False

if __name__ == "__main__":
    # 创建命令行参数解析器
    parser = argparse.ArgumentParser(description='测试爬取eBay店铺并发送邮件通知')
    
    parser.add_argument('--url', required=True, help='eBay店铺URL')
    parser.add_argument('--email', required=True, help='通知邮箱')
    parser.add_argument('--name', help='店铺名称（可选）')
    parser.add_argument('--pages', type=int, default=3, help='爬取页数（默认3页）')
    parser.add_argument('--verbose', '-v', action='store_true', help='显示详细日志')
    
    args = parser.parse_args()
    
    # 执行测试
    success = test_scrape_and_notify(args.url, args.email, args.name, args.pages)
    
    # 设置退出码
    sys.exit(0 if success else 1) 