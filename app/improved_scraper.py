#!/usr/bin/env python3
# 改进的eBay爬虫模块 - 整合simple_requests_scraper.py成功经验

import requests
from bs4 import BeautifulSoup
import json
import time
import logging
import redis
import random
import os
import re
from datetime import datetime
from app.config import Config
import logging.handlers

# 配置日志
log_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 添加文件处理器
log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'logs')
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, 'ebay_scraper.log')

file_handler = logging.handlers.RotatingFileHandler(
    log_file, maxBytes=5*1024*1024, backupCount=5, encoding='utf-8'
)
file_handler.setFormatter(log_formatter)
logger.addHandler(file_handler)

# 添加控制台处理器
console_handler = logging.StreamHandler()
console_handler.setFormatter(log_formatter)
logger.addHandler(console_handler)

logger.setLevel(logging.INFO)

class ImprovedEbayStoreScraper:
    """改进的eBay店铺爬虫 - 直接访问目标URL模式"""
    
    def __init__(self, redis_client=None, use_proxy=False):
        """初始化爬虫"""
        # 默认headers
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Cache-Control': 'max-age=0',
        }
        
        # User-Agent列表，用于轮换
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 Edg/121.0.0.0',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.4 Safari/605.1.15',
            'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/119.0'
        ]
        
        # 连接Redis数据库
        if redis_client:
            self.redis = redis_client
        else:
            try:
                self.redis = redis.Redis(
                    host=Config.REDIS_HOST,
                    port=Config.REDIS_PORT,
                    db=Config.REDIS_DB,
                    password=Config.REDIS_PASSWORD
                )
                self.redis.ping()  # 测试连接
                logger.info("成功连接到Redis")
            except Exception as e:
                logger.error(f"连接Redis失败: {e}")
                self.redis = None
        
        # 代理支持
        self.use_proxy = use_proxy
        self.proxies = None
        if use_proxy:
            self._load_proxies()
        
        # 添加统计信息
        self.stats = {
            'requests': 0,
            'successful_requests': 0,
            'failed_requests': 0,
            'items_scraped': 0,
            'retry_count': 0,
            'last_success_time': 0,
            'avg_response_time': 0
        }
    
    def _load_proxies(self):
        """加载代理列表"""
        # 从配置文件或环境变量加载代理
        # 这里仅作示例，实际应根据需求配置
        proxy_list = getattr(Config, 'PROXY_LIST', [])
        if not proxy_list and hasattr(Config, 'PROXY_FILE') and os.path.exists(Config.PROXY_FILE):
            try:
                with open(Config.PROXY_FILE, 'r') as f:
                    proxy_list = [line.strip() for line in f if line.strip()]
            except Exception as e:
                logger.error(f"从文件加载代理失败: {e}")
        
        self.proxies = proxy_list
        logger.info(f"加载了 {len(self.proxies)} 个代理")
    
    def _get_random_proxy(self):
        """获取随机代理"""
        if not self.proxies:
            return None
        return random.choice(self.proxies)
    
    def _get_random_user_agent(self):
        """获取随机User-Agent"""
        return random.choice(self.user_agents)
    
    def get_store_items(self, store_url, max_retries=3):
        """获取店铺所有商品"""
        items = []
        self.stats['requests'] += 1
        
        logger.info(f"正在获取店铺商品: {store_url}")
        
        # 更精细的请求头配置
        self.headers = {
            'User-Agent': random.choice(self.user_agents),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Referer': 'https://www.google.com/',
            'Cache-Control': 'max-age=0',
            'Pragma': 'no-cache'
        }
        
        for attempt in range(max_retries):
            try:
                # 添加随机延迟，模拟人类行为
                delay = random.uniform(2.0, 5.0)
                logger.info(f"等待 {delay:.2f} 秒后发起请求...")
                time.sleep(delay)
                
                # 准备代理
                proxies = None
                if self.use_proxy and self.proxies:
                    proxy = random.choice(self.proxies)
                    proxies = {
                        'http': proxy,
                        'https': proxy
                    }
                
                start_time = time.time()
                # 添加cookies参数和refer头，减少被检测概率
                cookies = {
                    'ebay': '%5Esbf%3D%23100000%5E',
                    'dp1': 'bu1p/QEBfX0BAX19AQA**63e9e1d5^',
                    's': 'CgAD4ACBjLqUMOTUzYjQxODcwMTgwYWI5YTUzYWJmZmZmZmU0ZmYzZjXshixH',
                }
                
                response = requests.get(
                    store_url, 
                    headers=self.headers, 
                    proxies=proxies,
                    cookies=cookies,
                    timeout=30,
                    verify=True
                )
                
                try:
                    response.raise_for_status()
                    
                    # 获取响应成功
                    response_time = time.time() - start_time
                    logger.info(f"成功获取店铺页面，响应时间: {response_time:.2f} 秒")
                    store_html = response.text
                    
                    # 解析HTML获取商品信息
                    items = self.parse_items_from_html(store_html)
                    
                    # 成功获取数据，更新统计信息
                    self.stats['successful_requests'] += 1
                    
                    return items
                    
                except requests.exceptions.HTTPError as e:
                    if "503" in str(e):
                        logger.warning(f"遇到503服务不可用错误")
                        
                        # 保存错误响应内容以便分析
                        if hasattr(e, 'response') and e.response:
                            debug_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'debug')
                            os.makedirs(debug_dir, exist_ok=True)
                            debug_file = os.path.join(debug_dir, f"error_503_{int(time.time())}.html")
                            with open(debug_file, 'w', encoding='utf-8') as f:
                                f.write(e.response.text)
                            logger.info(f"已保存503错误响应内容到 {debug_file}")
                    
                    self.stats['failed_requests'] += 1
                    self.stats['retry_count'] += 1
                    
                    if attempt < max_retries - 1:
                        # 增加退避时间
                        backoff_time = (2 ** attempt) + random.uniform(5, 10)
                        logger.warning(f"请求失败，等待 {backoff_time:.2f} 秒后进行第 {attempt+2}/{max_retries} 次尝试")
                        time.sleep(backoff_time)
                    else:
                        logger.error(f"所有尝试均失败: {e}")
                
            except Exception as e:
                self.stats['failed_requests'] += 1
                self.stats['retry_count'] += 1
                logger.warning(f"第 {attempt+1}/{max_retries} 次尝试失败: {e}")
                
                if attempt == max_retries - 1:
                    duration = time.time() - start_time
                    logger.error(f"达到最大重试次数，爬取失败，耗时: {duration:.2f} 秒")
                    import traceback
                    logger.error(traceback.format_exc())
        
        # 所有尝试都失败
        return []
    
    def parse_items_from_html(self, html_content):
        """从HTML中解析所有商品信息"""
        soup = BeautifulSoup(html_content, 'html.parser')
        items = []
        
        # 尝试多种可能的CSS选择器
        selector_pairs = [
            ('.s-item__wrapper', '.s-item'),
            ('.srp-results .s-item', None),
            ('#srp-river-results .s-item', None),
            ('.b-list__items_nofooter .s-item', None),
            ('li.s-item', None),
            ('.srp-river-results li.s-item', None),
            ('div[data-listing-id]', None)
        ]
        
        # 保存页面以便调试
        debug_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'debug')
        os.makedirs(debug_dir, exist_ok=True)
        with open(os.path.join(debug_dir, f'page_{int(time.time())}.html'), 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        for main_selector, sub_selector in selector_pairs:
            containers = soup.select(main_selector)
            if containers:
                self.logger.info(f"使用选择器 '{main_selector}' 找到 {len(containers)} 个商品元素")
                
                # 如果存在子选择器，进一步筛选
                if sub_selector:
                    filtered_containers = []
                    for container in containers:
                        sub_elements = container.select(sub_selector)
                        filtered_containers.extend(sub_elements)
                    containers = filtered_containers
                    self.logger.info(f"使用子选择器 '{sub_selector}' 筛选出 {len(containers)} 个商品元素")
                
                # 跳过第一个元素，因为通常是广告
                if len(containers) > 1:
                    containers = containers[1:]
                
                # 解析每个商品容器
                for container in containers:
                    item = self.parse_item_container(container)
                    if item:
                        items.append(item)
                
                # 如果找到了商品，就不再尝试其他选择器
                if items:
                    break
        
        self.logger.info(f"共解析出 {len(items)} 个商品")
        return items
    
    def parse_item_container(self, container):
        """从HTML元素中解析商品信息"""
        try:
            # 恢复原始解析逻辑
            # 商品标题
            title_element = container.select_one('.s-item__title')
            title = title_element.text.strip() if title_element else "N/A"
            
            # 跳过广告元素
            if title == "Shop on eBay":
                return None
            
            # 商品价格
            price_element = container.select_one('.s-item__price')
            price_text = price_element.text.strip() if price_element else "N/A"
            
            # 清理价格文本
            price = 0
            if price_text != "N/A":
                # 处理价格范围 (例如: $10.99 to $24.99)
                if " to " in price_text:
                    price_text = price_text.split(" to ")[0]
                
                # 提取数字
                price_match = re.search(r'(\d+\.\d+|\d+)', price_text)
                if price_match:
                    price = float(price_match.group(1))
            
            # 商品链接
            link_element = container.select_one('.s-item__link')
            url = link_element['href'] if link_element and 'href' in link_element.attrs else "N/A"
            
            # 商品图片
            image_element = container.select_one('.s-item__image-img')
            image_url = image_element['src'] if image_element and 'src' in image_element.attrs else "N/A"
            
            # 商品ID
            item_id = "unknown"
            if url != "N/A" and "/itm/" in url:
                item_id = url.split("/itm/")[1].split("?")[0].split("/")[0]
            
            # 获取已售数量信息（如果有）
            sold_element = container.select_one('.s-item__quantitySold, .s-item__hotness, .s-item__additionalItemHotness')
            sold_text = sold_element.text.strip() if sold_element else ""
            sold_count = 0
            
            if sold_text:
                sold_match = re.search(r'(\d+)', sold_text)
                if sold_match:
                    sold_count = int(sold_match.group(1))
            
            # 构建基本商品数据
            item_data = {
                'id': item_id,
                'title': title,
                'price': price,
                'url': url,
                'image_url': image_url,
                'sold_count': sold_count,
                'timestamp': int(time.time())
            }
            
            # 添加额外信息字段
            self._add_optional_fields(container, item_data)
            
            return item_data
        except Exception as e:
            logger.error(f"处理商品元素时出错: {e}")
            return None
    
    def _add_optional_fields(self, container, item_data):
        """安全地添加可选字段到商品数据"""
        try:
            # 商品状态
            status_elem = container.select_one('.SECONDARY_INFO')
            if status_elem:
                item_data['status'] = status_elem.get_text(strip=True)
            
            # 运费信息
            shipping_elem = container.select_one('.s-item__shipping, .s-item__freeXBorder')
            if shipping_elem:
                item_data['shipping'] = shipping_elem.get_text(strip=True)
            
            # 退货政策
            returns_elem = container.select_one('.s-item__free-returns')
            if returns_elem:
                item_data['returns_policy'] = returns_elem.get_text(strip=True)
            
            # 购买方式
            purchase_elem = container.select_one('.s-item__dynamic')
            if purchase_elem:
                item_data['purchase_type'] = purchase_elem.get_text(strip=True)
            
            # 卖家信息
            seller_info_elem = container.select_one('.s-item__seller-info-text')
            if seller_info_elem:
                item_data['seller_info'] = seller_info_elem.get_text(strip=True)
            
            # 原价和折扣
            original_price_elem = container.select_one('.STRIKETHROUGH')
            if original_price_elem:
                original_price_text = original_price_elem.get_text(strip=True)
                price_match = re.search(r'[\d,\.]+', original_price_text)
                if price_match:
                    item_data['original_price'] = float(price_match.group(0).replace(',', ''))
            
            discount_elem = container.select_one('.s-item__discount')
            if discount_elem:
                discount_text = discount_elem.get_text(strip=True)
                discount_match = re.search(r'(\d+)%', discount_text)
                if discount_match:
                    item_data['discount_percent'] = int(discount_match.group(1))
        
        except Exception as e:
            logger.error(f"获取可选字段时出错: {e}")
            # 出错时不影响主流程
    
    def update_store_data(self, store_url, store_name):
        """更新店铺数据并检测变化"""
        logger.info(f"更新店铺数据: {store_name}")
        max_attempts = 3
        
        for attempt in range(max_attempts):
            try:
                # 获取当前商品列表
                current_items = self.get_store_items(store_url)
                
                if not current_items:
                    if attempt < max_attempts - 1:
                        logger.warning(f"未获取到商品数据，尝试第 {attempt+1}/{max_attempts} 次")
                        time.sleep(60)  # 等待一分钟
                        continue
                    else:
                        logger.error(f"无法获取店铺 {store_name} 的商品数据")
                        
                        # 从备份恢复
                        backup_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'backups')
                        os.makedirs(backup_dir, exist_ok=True)
                        backup_file = os.path.join(backup_dir, f"backup_{store_name}_items.json")
                        
                        if os.path.exists(backup_file):
                            logger.info(f"从备份文件 {backup_file} 恢复")
                            with open(backup_file, 'r', encoding='utf-8') as f:
                                current_items = json.load(f)
                        else:
                            return {'new_listings': [], 'price_changes': [], 'removed_listings': []}
                
                # 成功获取数据，跳出循环
                break
                
            except Exception as e:
                logger.error(f"更新数据异常: {e}")
                if attempt < max_attempts - 1:
                    logger.info(f"将在30秒后重试 ({attempt+1}/{max_attempts})")
                    time.sleep(30)
                else:
                    logger.error("达到最大重试次数，无法更新数据")
                    return {'new_listings': [], 'price_changes': [], 'removed_listings': []}
        
        # 将商品列表转换为以ID为键的字典
        current_items_dict = {item['id']: item for item in current_items}
        
        # 获取以前的商品列表
        previous_items_json = self.redis.get(f"store:{store_name}:items")
        
        new_listings = []
        price_changes = []
        removed_listings = []
        
        # 检查是否存在旧数据
        if previous_items_json:
            previous_items = json.loads(previous_items_json)
            previous_items_dict = {item['id']: item for item in previous_items}
            
            # 检查新上架和价格变动的商品
            for item_id, current_item in current_items_dict.items():
                if item_id not in previous_items_dict:
                    # 新上架商品
                    new_listings.append(current_item)
                else:
                    # 检查价格是否变动
                    previous_item = previous_items_dict[item_id]
                    if current_item['price'] != previous_item['price']:
                        # 价格变动
                        change = {
                            'id': item_id,
                            'title': current_item['title'],
                            'url': current_item['url'],
                            'image_url': current_item['image_url'],
                            'old_price': previous_item['price'],
                            'new_price': current_item['price'],
                            'timestamp': int(time.time())
                        }
                        price_changes.append(change)
            
            # 检查下架商品
            for item_id, previous_item in previous_items_dict.items():
                if item_id not in current_items_dict:
                    # 商品下架
                    removed_listings.append(previous_item)
        else:
            # 没有旧数据，所有商品都是新上架
            new_listings = current_items
        
        # 保存当前商品列表到Redis
        if self.redis:
            self.redis.set(f"store:{store_name}:items", json.dumps(current_items))
            
            # 保存更新时间
            self.redis.set(f"store:{store_name}:last_update", int(time.time()))
            
            # 更新店铺统计信息
            self.redis.set(f"store:{store_name}:stats", json.dumps({
                'total_items': len(current_items),
                'new_items': len(new_listings),
                'price_changes': len(price_changes),
                'removed_items': len(removed_listings),
                'update_time': int(time.time())
            }))
        
        # 创建备份
        backup_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'backups')
        os.makedirs(backup_dir, exist_ok=True)
        backup_file = os.path.join(backup_dir, f"backup_{store_name}_items.json")
        with open(backup_file, 'w', encoding='utf-8') as f:
            json.dump(current_items, f, ensure_ascii=False, indent=2)
        
        # 记录变更
        if new_listings:
            logger.info(f"发现 {len(new_listings)} 个新上架商品")
        if price_changes:
            logger.info(f"发现 {len(price_changes)} 个价格变动")
        if removed_listings:
            logger.info(f"发现 {len(removed_listings)} 个下架商品")
        
        return {
            'new_listings': new_listings,
            'price_changes': price_changes,
            'removed_listings': removed_listings
        }

    def get_stats(self):
        """获取爬虫统计信息"""
        self.stats['success_rate'] = 0
        if self.stats['requests'] > 0:
            self.stats['success_rate'] = (self.stats['successful_requests'] / self.stats['requests']) * 100
        
        return self.stats

    def _handle_captcha(self, html_content):
        """检测并尝试处理验证码"""
        # 检查是否包含验证码或机器人检测
        if 'captcha' in html_content.lower() or 'robot' in html_content.lower():
            logger.warning("检测到验证码或机器人检测页面")
            
            # 保存页面以便调试
            debug_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'debug')
            os.makedirs(debug_dir, exist_ok=True)
            
            debug_file = os.path.join(debug_dir, f"captcha_page_{int(time.time())}.html")
            with open(debug_file, 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            logger.info(f"验证码页面已保存至 {debug_file}")
            return True
        
        return False

    def _avoid_detection(self):
        """通过更改请求特征来避免检测"""
        # 使用更真实的设备指纹
        platform = random.choice(['Windows NT 10.0', 'Macintosh; Intel Mac OS X 10_15', 'X11; Linux x86_64'])
        chrome_version = f"{random.randint(90, 122)}.0.{random.randint(1000, 9999)}.{random.randint(10, 999)}"
        
        user_agent = f"Mozilla/5.0 ({platform}) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{chrome_version} Safari/537.36"
        
        self.headers['User-Agent'] = user_agent
        
        # 添加更多随机参数
        if random.random() > 0.5:
            self.headers['Referer'] = 'https://www.ebay.com/'
        
        # 添加各种随机cookie
        cf_clearance = ''.join(random.choices('0123456789abcdef', k=32))
        self.headers['Cookie'] = f"cf_clearance={cf_clearance}; dp1=bu1p/QEBfX0BAX19AQA**{cf_clearance}^"

# 测试代码
if __name__ == "__main__":
    test_url = "https://www.ebay.com/sch/i.html?_dkr=1&iconV2Request=true&_blrs=recall_filtering&_ssn=yingniao02&store_name=yingniao02&_oac=1"
    scraper = ImprovedEbayStoreScraper()
    items = scraper.get_store_items(test_url)
    
    if items:
        print(f"成功获取 {len(items)} 个商品")
        for i, item in enumerate(items[:3]):
            print(f"商品 {i+1}:")
            print(f"  - ID: {item.get('id', 'N/A')}")
            print(f"  - 标题: {item.get('title', 'N/A')}")
            print(f"  - 价格: ${item.get('price', 0):.2f}")
            print(f"  - 图片: {item.get('image_url', 'N/A')}")
            print(f"  - 销量: {item.get('sold_count', 0)}")
            print(f"  - 状态: {item.get('status', 'N/A')}")
            print(f"  - 类别: {item.get('category', 'N/A')}")
            print(f"  - 运费: {item.get('shipping', 'N/A')}")
            print(f"  - 描述: {item.get('description', 'N/A')}")
            print("---")
    else:
        print("获取商品失败") 