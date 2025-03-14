#!/usr/bin/env python3
"""
测试改进的eBay店铺爬虫
"""

import os
import sys
from bs4 import BeautifulSoup
from app.improved_scraper import ImprovedEbayStoreScraper
import json

def test_parser_with_html_file():
    """使用本地HTML文件测试解析器"""
    # 获取文件路径
    html_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), '1.html')
    
    if not os.path.exists(html_file):
        print(f"错误: HTML文件 {html_file} 不存在")
        sys.exit(1)
    
    # 读取HTML文件
    with open(html_file, 'r', encoding='utf-8') as f:
        html_content = f.read()
    
    # 初始化爬虫
    scraper = ImprovedEbayStoreScraper()
    
    # 解析HTML
    soup = BeautifulSoup(html_content, 'html.parser')
    item_elements = soup.select('.s-item__wrapper')
    
    if not item_elements:
        print("未找到商品元素")
        return
    
    print(f"找到 {len(item_elements)} 个商品元素")
    
    # 解析每个商品
    items = []
    new_listings_count = 0
    error_count = 0
    
    for element in item_elements:
        try:
            item = scraper.parse_item_element(element)
            if item:
                items.append(item)
                if item.get('is_new_listing', False):
                    new_listings_count += 1
        except Exception as e:
            error_count += 1
            print(f"解析元素时出错: {e}")
    
    print(f"成功解析 {len(items)} 个商品")
    print(f"其中新上架商品: {new_listings_count} 个")
    print(f"解析失败: {error_count} 个")
    
    # 打印前3个商品的详细信息
    for i, item in enumerate(items[:3]):
        print(f"\n商品 {i+1}:")
        print(f"  ID: {item.get('id', '未知')}")
        print(f"  标题: {item.get('title', '未知')}")
        print(f"  价格: ${item.get('price', 0):.2f}")
        print(f"  原价: ${item.get('original_price', 0):.2f}" if item.get('original_price') else "  原价: 无")
        print(f"  折扣: {item.get('discount_percent')}%" if item.get('discount_percent') else "  折扣: 无")
        print(f"  状态: {item.get('status', '未知')}")
        print(f"  运费: {item.get('shipping', '未知')}")
        print(f"  新上架: {'是' if item.get('is_new_listing', False) else '否'}")
    
    # 将所有商品保存到JSON文件
    output_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'parsed_items.json')
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    
    print(f"\n所有商品数据已保存到 {output_file}")

if __name__ == "__main__":
    test_parser_with_html_file() 