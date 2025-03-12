#!/usr/bin/env python3
"""
手动爬取店铺脚本
"""

import os
import sys
import logging
import json
import redis
from app.config import Config
from app.improved_scraper import ImprovedEbayStoreScraper

# 配置日志
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def scrape_store(store_url, store_name):
    """手动爬取店铺"""
    try:
        # 连接Redis
        redis_client = redis.Redis(
            host=Config.REDIS_HOST,
            port=Config.REDIS_PORT,
            db=Config.REDIS_DB,
            password=Config.REDIS_PASSWORD
        )
        
        # 创建爬虫实例
        scraper = ImprovedEbayStoreScraper(redis_client=redis_client)
        
        # 爬取店铺
        logger.info(f"开始爬取店铺: {store_name}")
        changes = scraper.update_store_data(store_url, store_name)
        
        # 显示结果
        logger.info(f"爬取完成，结果:")
        logger.info(f"- 新商品: {len(changes['new_listings'])}")
        logger.info(f"- 价格变动: {len(changes['price_changes'])}")
        logger.info(f"- 下架商品: {len(changes['removed_listings'])}")
        
        # 获取存储的商品数据
        items_json = redis_client.get(f"store:{store_name}:items")
        if items_json:
            items = json.loads(items_json)
            logger.info(f"Redis中存储了 {len(items)} 个商品")
            
            # 显示部分商品信息
            for i, item in enumerate(items[:3]):
                logger.info(f"商品 {i+1}:")
                logger.info(f"  ID: {item.get('id', 'N/A')}")
                logger.info(f"  标题: {item.get('title', 'N/A')}")
                logger.info(f"  价格: ${float(item.get('price', 0)):.2f}")
        else:
            logger.error("Redis中未找到商品数据!")
        
        return True
    except Exception as e:
        logger.error(f"爬取失败: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("用法: python test_scrape_store.py <店铺URL> <店铺名称>")
        sys.exit(1)
    
    store_url = sys.argv[1]
    store_name = sys.argv[2]
    
    success = scrape_store(store_url, store_name)
    sys.exit(0 if success else 1) 