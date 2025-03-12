# eBay店铺爬虫模块

import requests
from bs4 import BeautifulSoup
import json
import time
import logging
import redis
from datetime import datetime
from app.config import Config

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class EbayStoreScraper:
    def __init__(self, redis_client=None):
        """初始化爬虫"""
        self.headers = {
            'User-Agent': Config.USER_AGENT,
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        }
        
        # 连接Redis数据库
        if redis_client:
            self.redis = redis_client
        else:
            self.redis = redis.Redis(
                host=Config.REDIS_HOST,
                port=Config.REDIS_PORT,
                db=Config.REDIS_DB,
                password=Config.REDIS_PASSWORD
            )
    
    def get_store_items(self, store_url):
        """获取店铺所有商品信息"""
        try:
            logger.info(f"开始爬取店铺: {store_url}")
            
            # 发送HTTP请求获取页面内容
            response = requests.get(store_url, headers=self.headers)
            response.raise_for_status()  # 检查请求是否成功
            
            # 使用BeautifulSoup解析HTML
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 获取商品列表
            items = []
            
            # 查找所有商品容器
            item_containers = soup.select('.s-item__wrapper')
            
            for container in item_containers:
                # 跳过eBay搜索结果中的第一个项目，它通常是一个广告或提示
                if container.select_one('.s-item__title--tagblock'):
                    continue
                
                # 获取商品信息
                item_info = {}
                
                # 获取商品ID
                item_link_elem = container.select_one('.s-item__link')
                if item_link_elem:
                    item_url = item_link_elem.get('href', '')
                    item_id = item_url.split('itm/')[1].split('?')[0] if 'itm/' in item_url else ''
                    item_info['id'] = item_id
                    item_info['url'] = item_url
                
                # 获取商品标题
                title_elem = container.select_one('.s-item__title')
                if title_elem:
                    item_info['title'] = title_elem.get_text(strip=True)
                
                # 获取商品价格
                price_elem = container.select_one('.s-item__price')
                if price_elem:
                    price_text = price_elem.get_text(strip=True)
                    # 清理价格文本，移除货币符号和逗号
                    price_text = price_text.replace('$', '').replace(',', '')
                    # 如果价格范围格式为"$10.00 to $20.00"，取第一个价格
                    if ' to ' in price_text:
                        price_text = price_text.split(' to ')[0]
                    try:
                        item_info['price'] = float(price_text)
                    except ValueError:
                        item_info['price'] = 0.0
                
                # 获取商品图片
                img_elem = container.select_one('.s-item__image-img')
                if img_elem:
                    item_info['image_url'] = img_elem.get('src', '')
                
                # 获取是否有销售数量信息
                sold_elem = container.select_one('.s-item__quantitySold')
                if sold_elem:
                    sold_text = sold_elem.get_text(strip=True)
                    try:
                        sold_count = int(''.join(filter(str.isdigit, sold_text)))
                        item_info['sold_count'] = sold_count
                    except ValueError:
                        item_info['sold_count'] = 0
                else:
                    item_info['sold_count'] = 0
                
                # 添加爬取时间
                item_info['scraped_at'] = datetime.now().isoformat()
                
                # 添加到列表
                if 'id' in item_info and item_info['id']:
                    items.append(item_info)
            
            logger.info(f"成功爬取 {len(items)} 个商品")
            return items
            
        except requests.RequestException as e:
            logger.error(f"请求错误: {e}")
            return []
        except Exception as e:
            logger.error(f"爬取过程中发生错误: {e}")
            return []
    
    def update_store_data(self, store_url, store_name=None):
        """更新店铺数据并检测变化"""
        # 提取店铺名称（如果未提供）
        if not store_name:
            if 'store_name=' in store_url:
                store_name = store_url.split('store_name=')[1].split('&')[0]
            else:
                store_name = f"store_{int(time.time())}"
        
        # 获取新数据
        new_items = self.get_store_items(store_url)
        
        if not new_items:
            logger.warning(f"未获取到商品数据，跳过更新")
            return {
                'new_listings': [],
                'price_changes': [],
                'removed_listings': []
            }
        
        # 获取旧数据
        old_items_dict = {}
        old_keys = self.redis.keys(f"store:{store_name}:item:*")
        
        for key in old_keys:
            key_str = key.decode('utf-8') if isinstance(key, bytes) else key
            item_id = key_str.split(':')[-1]
            item_data = self.redis.get(key_str)
            if item_data:
                try:
                    item_json = json.loads(item_data.decode('utf-8'))
                    old_items_dict[item_id] = item_json
                except (json.JSONDecodeError, UnicodeDecodeError):
                    logger.error(f"解析项目数据时出错: {key_str}")
        
        # 检测新增商品、价格变动和下架商品
        new_listings = []
        price_changes = []
        new_item_ids = set()
        
        # 处理新数据
        for item in new_items:
            item_id = item['id']
            new_item_ids.add(item_id)
            
            # 保存到Redis
            self.redis.set(
                f"store:{store_name}:item:{item_id}", 
                json.dumps(item),
                ex=60*60*24*30  # 30天过期
            )
            
            # 检查是否为新上架商品
            if item_id not in old_items_dict:
                new_listings.append(item)
                
                # 记录新商品上架的时间戳
                self.redis.zadd(
                    f"store:{store_name}:new_listings", 
                    {item_id: int(time.time())}
                )
                continue
            
            # 检查价格是否变动
            old_price = old_items_dict[item_id].get('price', 0)
            new_price = item.get('price', 0)
            
            if abs(old_price - new_price) > 0.01:  # 考虑浮点数精度问题
                price_change = {
                    'item': item,
                    'old_price': old_price,
                    'new_price': new_price
                }
                price_changes.append(price_change)
                
                # 记录价格变动历史
                price_history = {
                    'timestamp': int(time.time()),
                    'price': new_price
                }
                self.redis.zadd(
                    f"store:{store_name}:item:{item_id}:price_history",
                    {json.dumps(price_history): price_history['timestamp']}
                )
        
        # 检测下架商品
        removed_listings = []
        for item_id, item in old_items_dict.items():
            if item_id not in new_item_ids:
                removed_listings.append(item)
                
                # 标记商品为已下架
                item['removed_at'] = datetime.now().isoformat()
                self.redis.set(
                    f"store:{store_name}:removed:item:{item_id}", 
                    json.dumps(item),
                    ex=60*60*24*30  # 30天过期
                )
                
                # 删除原有商品
                self.redis.delete(f"store:{store_name}:item:{item_id}")
        
        # 更新店铺最后更新时间
        self.redis.set(f"store:{store_name}:last_updated", int(time.time()))
        
        # 返回变动信息
        return {
            'new_listings': new_listings,
            'price_changes': price_changes,
            'removed_listings': removed_listings
        }

# 测试代码
if __name__ == "__main__":
    scraper = EbayStoreScraper()
    test_url = "https://www.ebay.com/sch/i.html?_dkr=1&iconV2Request=true&_blrs=recall_filtering&_ssn=yingniao02&store_name=yingniao02&_oac=1"
    results = scraper.update_store_data(test_url, "yingniao02")
    print(f"新商品: {len(results['new_listings'])}")
    print(f"价格变动: {len(results['price_changes'])}")
    print(f"下架商品: {len(results['removed_listings'])}")