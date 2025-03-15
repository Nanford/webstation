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

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger('test_scheduler')

def test_scrape_and_notify(store_url, email, store_name=None, max_pages=1):
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
        
        # 爬取当前数据
        logger.info(f"开始爬取店铺，限制 {max_pages} 页...")
        current_items = scraper.scrape_all_pages(store_url, max_pages=max_pages)
        
        if not current_items:
            logger.error("没有获取到任何商品，请检查URL是否正确")
            return False
        
        logger.info(f"成功获取 {len(current_items)} 个商品")
        
        # 保存最新数据到Redis
        redis_client.set(f"store:{store_name}:items", json.dumps(current_items))
        redis_client.set(f"store:{store_name}:last_update", int(time.time()))
        
        # 如果没有之前的数据，则将所有商品视为新上架
        if not previous_items:
            new_listings = current_items
            logger.info(f"没有找到之前的数据，将所有 {len(new_listings)} 个商品视为新上架")
        else:
            # 比较数据，找出新上架商品
            previous_ids = {item.get('id'): item for item in previous_items}
            new_listings = [item for item in current_items if item.get('id') not in previous_ids]
            logger.info(f"对比数据后，发现 {len(new_listings)} 个新上架商品")
        
        # 查找带"New Listing"标记的商品
        true_new_listings = [item for item in current_items if item.get('is_new_listing')]
        if true_new_listings:
            logger.info(f"找到 {len(true_new_listings)} 个带'New Listing'标记的商品")
            # 合并两种方式找到的新商品
            for item in true_new_listings:
                if item.get('id') and item.get('id') not in [i.get('id') for i in new_listings]:
                    new_listings.append(item)
        
        # 没有新商品，结束测试
        if not new_listings:
            logger.info("没有发现新上架商品，不发送邮件通知")
            return True
        
        # 初始化邮件通知
        notifier = EmailNotifier()
        
        # 发送新商品通知
        logger.info(f"发送 {len(new_listings)} 个新上架商品的邮件通知到 {email}")
        result = notifier.notify_new_listings(email, store_name, new_listings)
        
        if result:
            logger.info("邮件发送成功！")
        else:
            logger.error("邮件发送失败！")
        
        return result
        
    except Exception as e:
        logger.error(f"测试过程中发生错误: {str(e)}", exc_info=True)
        return False

if __name__ == "__main__":
    # 创建命令行参数解析器
    parser = argparse.ArgumentParser(description='测试爬取eBay店铺并发送邮件通知')
    
    parser.add_argument('--url', required=True, help='eBay店铺URL')
    parser.add_argument('--email', required=True, help='通知邮箱')
    parser.add_argument('--name', help='店铺名称（可选）')
    parser.add_argument('--pages', type=int, default=1, help='爬取页数（默认1页）')
    
    args = parser.parse_args()
    
    # 执行测试
    success = test_scrape_and_notify(args.url, args.email, args.name, args.pages)
    
    # 设置退出码
    sys.exit(0 if success else 1) 