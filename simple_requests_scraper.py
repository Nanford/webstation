import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import random
import re
from datetime import datetime
import matplotlib.pyplot as plt

def extract_price_value(price_str):
    """从价格字符串中提取数值"""
    if price_str == "N/A":
        return None
    # 提取数字部分，处理范围价格
    match = re.search(r'(\d+\.\d+|\d+)', price_str.replace(',', ''))
    if match:
        return float(match.group(1))
    return None

def analyze_and_display_results(df):
    """分析并展示爬取结果的统计信息"""
    if df is None or df.empty:
        print("没有数据可供分析")
        return
    
    # 基本统计
    print("\n================ eBay商品统计分析 ================")
    print(f"总商品数: {len(df)}")
    
    # 提取价格数值用于分析
    df['price_value'] = df['price'].apply(extract_price_value)
    valid_prices = df['price_value'].dropna()
    
    if not valid_prices.empty:
        # 价格统计
        print("\n【价格统计】")
        print(f"平均价格: ${valid_prices.mean():.2f}")
        print(f"最低价格: ${valid_prices.min():.2f}")
        print(f"最高价格: ${valid_prices.max():.2f}")
        print(f"中位数价格: ${valid_prices.median():.2f}")
        
        # 价格分布
        price_ranges = [(0, 10), (10, 20), (20, 50), (50, 100), (100, float('inf'))]
        print("\n【价格分布】")
        for low, high in price_ranges:
            if high == float('inf'):
                count = sum(valid_prices >= low)
                print(f"${low}以上: {count}件商品 ({count/len(valid_prices)*100:.1f}%)")
            else:
                count = sum((valid_prices >= low) & (valid_prices < high))
                print(f"${low}-${high}: {count}件商品 ({count/len(valid_prices)*100:.1f}%)")
    
    # 展示部分商品信息 - 改进展示格式
    print("\n===================== 【最新商品详情展示】(前10条) =====================")
    for i, (_, row) in enumerate(df.head(10).iterrows()):
        print(f"\n{'-'*80}")
        print(f"商品 {i+1}:")
        print(f"【商品名称】: {row['title']}")
        print(f"【商品价格】: {row['price']}")
        print(f"【商品状态】: {row['condition']}")
        print(f"【商品品类】: {row['category'] if 'category' in row else '未分类'}")
        print(f"【运费信息】: {row['shipping']}")
        
        # 展示描述信息（如果有）
        if 'description' in row and row['description'] != "N/A":
            # 限制描述长度并格式化
            desc = row['description']
            max_length = 200
            formatted_desc = desc[:max_length] + "..." if len(desc) > max_length else desc
            print(f"【商品描述】: {formatted_desc}")
        
        # 展示卖家信息（如果有）
        if 'seller_info' in row and row['seller_info'] != "N/A":
            print(f"【卖家信息】: {row['seller_info']}")
            
        # 展示商品链接
        print(f"【详情链接】: {row['link']}")
        
        # 展示商品图片链接
        if 'image_url' in row and row['image_url'] != "N/A":
            print(f"【图片链接】: {row['image_url']}")
    
    print(f"\n{'-'*80}")
    
    # 保存分析报告
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    report_file = f"ebay_analysis_report_{timestamp}.txt"
    
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(f"eBay商品分析报告 - 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write(f"总商品数: {len(df)}\n\n")
        
        if not valid_prices.empty:
            f.write("【价格统计】\n")
            f.write(f"平均价格: ${valid_prices.mean():.2f}\n")
            f.write(f"最低价格: ${valid_prices.min():.2f}\n")
            f.write(f"最高价格: ${valid_prices.max():.2f}\n")
            f.write(f"中位数价格: ${valid_prices.median():.2f}\n\n")
        
            f.write("【价格分布】\n")
            for low, high in price_ranges:
                if high == float('inf'):
                    count = sum(valid_prices >= low)
                    f.write(f"${low}以上: {count}件商品 ({count/len(valid_prices)*100:.1f}%)\n")
                else:
                    count = sum((valid_prices >= low) & (valid_prices < high))
                    f.write(f"${low}-${high}: {count}件商品 ({count/len(valid_prices)*100:.1f}%)\n")
            
        # 将商品详情也写入报告
        f.write("\n\n===================== 【最新商品详情】 =====================\n\n")
        for i, (_, row) in enumerate(df.head(10).iterrows()):
            f.write(f"\n{'-'*80}\n")
            f.write(f"商品 {i+1}:\n")
            f.write(f"【商品名称】: {row['title']}\n")
            f.write(f"【商品价格】: {row['price']}\n")
            f.write(f"【商品状态】: {row['condition']}\n")
            f.write(f"【商品品类】: {row['category'] if 'category' in row else '未分类'}\n")
            f.write(f"【运费信息】: {row['shipping']}\n")
            
            if 'description' in row and row['description'] != "N/A":
                desc = row['description']
                max_length = 300
                formatted_desc = desc[:max_length] + "..." if len(desc) > max_length else desc
                f.write(f"【商品描述】: {formatted_desc}\n")
            
            f.write(f"【详情链接】: {row['link']}\n")
    
    print(f"\n分析报告已保存至: {report_file}")
    
    # 尝试绘制价格分布图
    try:
        plt.figure(figsize=(10, 6))
        plt.hist(valid_prices, bins=20, alpha=0.7, color='skyblue')
        plt.title('商品价格分布')
        plt.xlabel('价格 ($)')
        plt.ylabel('商品数量')
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        
        chart_file = f"price_distribution_{timestamp}.png"
        plt.savefig(chart_file)
        print(f"价格分布图已保存至: {chart_file}")
    except Exception as e:
        print(f"生成图表时出错: {e}")

def is_valid_ebay_item(item, title, price, link):
    """验证是否为有效的eBay商品"""
    # 检查标题是否有效
    if not title or title == "N/A" or title == "Shop on eBay":
        return False
    
    # 检查价格是否有效
    if not price or price == "N/A":
        return False
    
    # 检查链接是否有效
    if not link or link == "N/A" or "itm/" not in link:
        return False
        
    # 检查是否有图片元素(真实商品通常有图片)
    img_elem = item.select_one('.s-item__image-img')
    if not img_elem:
        return False
        
    return True

def scrape_ebay_seller(seller_id,store_name, max_pages=5):
    results = []
    base_url = f"https://www.ebay.com/sch/i.html?_dkr=1&iconV2Request=true&_blrs=recall_filtering&_ssn={seller_id}&store_name={store_name}&_oac=1&_sop=10"
    
    # 添加排序参数，按最新上架排序
    base_url += "&_sop=10"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.61 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8'
    }
    
    for page in range(1, max_pages + 1):
        url = f"{base_url}&_pgn={page}"
        print(f"正在爬取第 {page} 页...")
        
        try:
            response = requests.get(url, headers=headers)
            if response.status_code != 200:
                print(f"请求失败: 状态码 {response.status_code}")
                break
                
            soup = BeautifulSoup(response.text, 'html.parser')
            items = soup.select('li.s-item')
            
            if not items or len(items) <= 1:
                print("没有找到更多商品，结束爬取")
                break
                
            print(f"在第 {page} 页找到 {len(items) - 1} 个商品")
            
            # 处理每个商品
            valid_items_count = 0
            for item in items[1:]:  # 跳过第一个元素
                try:
                    # 提取商品数据
                    title_elem = item.select_one('.s-item__title')
                    price_elem = item.select_one('.s-item__price')
                    
                    title = title_elem.text if title_elem else "N/A"
                    price = price_elem.text if price_elem else "N/A"
                    
                    # 跳过无效商品 - 新增验证
                    # 跳过"Shop on eBay"和其他可能的非商品条目
                    if title in ["Shop on eBay", "N/A"] or price == "N/A":
                        print(f"跳过无效商品: {title}")
                        continue
                    
                    # 进一步验证 - 检查是否有有效的链接
                    link_elem = item.select_one('a.s-item__link')
                    link = link_elem['href'] if link_elem and 'href' in link_elem.attrs else "N/A"
                    
                    # 验证链接是否有效且包含商品ID
                    if link == "N/A" or "itm/" not in link:
                        print(f"跳过无效链接的商品: {title}")
                        continue
                    
                    valid_items_count += 1
                    
                    # 提取商品状态
                    condition_elem = item.select_one('.SECONDARY_INFO')
                    condition = condition_elem.text if condition_elem else "N/A"
                    
                    # 提取商品品类 - 新增
                    category_elem = item.select_one('.s-item__category span.clipped')
                    category = category_elem.text if category_elem else "N/A"
                    
                    # 如果没有找到类别元素，尝试从标题中提取可能的类别关键词
                    if category == "N/A" and title != "N/A":
                        # 一些常见的eBay商品类别关键词
                        category_keywords = ['Electronics', 'Clothing', 'Shoes', 'Accessories', 'Home', 
                                            'Garden', 'Sports', 'Toys', 'Books', 'Health', 'Beauty',
                                            'Jewelry', 'Watches', 'Computer', 'Phone', 'Automotive']
                        
                        for keyword in category_keywords:
                            if keyword.lower() in title.lower():
                                category = keyword
                                break
                    
                    # 提取商品描述摘要 - 新增
                    # 注意：需要从列表页获取详细描述通常比较困难
                    # 这里使用标题和状态信息组合作为简单描述
                    description = f"{title} - {condition}"
                    
                    # 从卖家评分和交易信息中提取卖家信息 - 新增
                    seller_info_elem = item.select_one('.s-item__seller-info')
                    seller_info = seller_info_elem.text if seller_info_elem else seller_id
                    
                    # 提取运费信息 - 这行被误删了
                    shipping_elem = item.select_one('.s-item__shipping')
                    shipping = shipping_elem.text if shipping_elem else "N/A"
                    
                    # 提取图片链接
                    img_elem = item.select_one('.s-item__image-wrapper img')
                    img_url = img_elem['src'] if img_elem and 'src' in img_elem.attrs else "N/A"
                    
                    item_data = {
                        'title': title,
                        'price': price,
                        'condition': condition,
                        'category': category,  # 新增
                        'description': description,  # 新增
                        'seller_info': seller_info,  # 新增
                        'shipping': shipping,
                        'link': link,
                        'image_url': img_url,
                        'scrape_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    }
                    
                    results.append(item_data)
                except Exception as e:
                    print(f"处理商品时出错: {e}")
                    continue
            
            # 添加随机延迟，避免被封IP
            delay = random.uniform(2, 5)
            print(f"等待 {delay:.1f} 秒后继续...")
            time.sleep(delay)
            
        except Exception as e:
            print(f"爬取过程中出错: {e}")
            break
    
    # 将结果保存为CSV
    if results:
        df = pd.DataFrame(results)
        filename = f"{seller_id}_listings_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        df.to_csv(filename, index=False, encoding='utf-8-sig')
        print(f"已将 {len(results)} 条商品数据保存到 {filename}")
        
        # 分析并展示结果
        analyze_and_display_results(df)
        
        return df
    else:
        print("没有找到任何商品数据")
        return None

if __name__ == "__main__":
    seller_id = "starbellone"  # 替换为目标卖家ID
    store_name= "starbellone"
    results_df = scrape_ebay_seller(seller_id,store_name,max_pages=3) 