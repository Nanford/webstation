#!/usr/bin/env python3
"""
改进的eBay爬虫测试脚本
"""

import os
import sys
import logging
import json
import time
from app.improved_scraper import ImprovedEbayStoreScraper

# 配置日志
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_improved_scraper():
    """测试改进的爬虫"""
    # 解析命令行参数
    import argparse
    parser = argparse.ArgumentParser(description="测试改进的eBay爬虫")
    parser.add_argument("--url", help="要爬取的eBay店铺URL", 
                       default="https://www.ebay.com/sch/i.html?_dkr=1&iconV2Request=true&_blrs=recall_filtering&_ssn=yingniao02&store_name=yingniao02&_oac=1")
    parser.add_argument("--retries", type=int, help="最大重试次数", default=3)
    args = parser.parse_args()
    
    logger.info(f"开始测试爬虫，URL: {args.url}")
    
    # 创建爬虫实例
    scraper = ImprovedEbayStoreScraper()
    
    # 获取商品
    start_time = time.time()
    items = scraper.get_store_items(args.url, args.retries)
    duration = time.time() - start_time
    
    if items:
        logger.info(f"成功获取 {len(items)} 个商品，耗时: {duration:.2f} 秒")
        
        # 保存到JSON文件
        with open("improved_scraper_items.json", "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=2)
        logger.info("已将商品数据保存到 improved_scraper_items.json")
        
        # 显示部分商品
        for i, item in enumerate(items[:3]):
            logger.info(f"商品 {i+1}:")
            logger.info(f"  - ID: {item.get('id', 'N/A')}")
            logger.info(f"  - 标题: {item.get('title', 'N/A')}")
            logger.info(f"  - 价格: ${item.get('price', 0):.2f}")
            logger.info(f"  - 销量: {item.get('sold_count', 0)}")
        
        # 获取统计信息
        stats = scraper.get_stats()
        logger.info(f"爬虫统计: 成功率 {stats['success_rate']:.2f}%, 总请求 {stats['requests']}")
        
        return True
    else:
        logger.error(f"爬取失败，耗时: {duration:.2f} 秒")
        return False

if __name__ == "__main__":
    test_improved_scraper() 