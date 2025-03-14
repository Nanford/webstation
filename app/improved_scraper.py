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
from urllib.parse import urljoin

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
        self.logger = logger
        
        # 从配置中加载设置
        self.config = Config
        
        # 设置用户代理
        self.user_agent = self.config.USER_AGENT
        
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
        
        # 添加代理列表
        self.proxy_list = []
        # 添加一个错误重试标记
        self.retry_with_different_method = False
    
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
    
    def get_random_headers(self):
        """获取随机的请求头，避免被反爬"""
        random_user_agent = self._get_random_user_agent()
        headers = {
            'User-Agent': random_user_agent,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Referer': 'https://www.ebay.com/',
            'Cache-Control': 'max-age=0'
        }
        return headers
    
    def get_store_items(self, store_url, max_retries=3):
        """获取店铺所有商品"""
        items = []
        self.stats['requests'] += 1
        
        self.logger.info(f"正在获取店铺商品: {store_url}")
        
        # 首先尝试使用curl方法获取数据
        self.logger.info("优先使用curl命令获取页面...")
        html_content = self._curl_request(store_url)
        if html_content:
            items = self.parse_items_from_html(html_content)
            if items:
                self.stats['successful_requests'] += 1
                self.stats['items_scraped'] += len(items)
                self.stats['last_success_time'] = time.time()
                self.logger.info(f"通过curl成功获取 {len(items)} 个商品")
                return items
        
        self.logger.warning("curl方法失败，尝试使用requests方法...")
        
        for attempt in range(max_retries):
            try:
                # 使用更长的等待时间 (10-20秒)
                delay = random.uniform(10.0, 20.0)
                self.logger.info(f"等待 {delay:.2f} 秒后发起请求...")
                time.sleep(delay)
                
                # 初始化start_time变量
                start_time = time.time()
                
                # 设置cookies - 每次请求使用随机生成的cookie值
                cookies = {
                    'npii': f'btguid/{self._generate_random_id()}^cguid/{self._generate_random_id()}^',
                    'dp1': f'bu1p/QEBfX0BAX19AQA**{self._generate_random_id(8)}^u1f/QEBfX0BAX19AQA**{self._generate_random_id(8)}^',
                    's': f'CgAD4gIBYLDqk9W{self._generate_random_id(30)}',
                    'ebay': '%5Ejs%3D1%5Edv%3D0%5Esjs%3D0%5E',
                }
                
                # 标准请求 - 使用随机化的User-Agent
                headers = {
                    'User-Agent': self._get_random_user_agent(),
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                    'Accept-Language': 'zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1',
                    'Cache-Control': 'max-age=0'
                }
                
                self.logger.info("使用标准请求方法")
                response = requests.get(
                    store_url,
                    headers=headers,
                    cookies=cookies,
                    timeout=40
                )
                
                # 如果这次失败，下次尝试不同方法
                if response.status_code != 200:
                    self.retry_with_different_method = True
                    self.logger.warning(f"请求失败，状态码: {response.status_code}，尝试第 {attempt+1}/{max_retries} 次")
                else:
                    self.retry_with_different_method = False
                    self.logger.info(f"成功获取店铺页面，状态码: 200，页面大小: {len(response.text)} 字节")
                    items = self.parse_items_from_html(response.text)
                    if items:
                        self.stats['successful_requests'] += 1
                        self.stats['items_scraped'] += len(items)
                        self.stats['last_success_time'] = time.sleep(time.time())
                        return items
                    else:
                        self.logger.warning(f"解析页面未找到商品数据，尝试第 {attempt+1}/{max_retries} 次")
                
                # 设置退避时间
                if attempt < max_retries - 1:
                    backoff_time = (2 ** attempt) + random.uniform(1, 2)
                    self.logger.info(f"等待 {backoff_time:.2f} 秒后重试...")
                    time.sleep(backoff_time)
            
            except Exception as e:
                self.logger.error(f"第 {attempt+1}/{max_retries} 次尝试失败: {str(e)}")
                if attempt < max_retries - 1:
                    backoff_time = (2 ** attempt) + random.uniform(1, 2)
                    self.logger.info(f"等待 {backoff_time:.2f} 秒后重试...")
                    time.sleep(backoff_time)
        
        self.logger.error(f"达到最大重试次数，爬取失败")
        return []
    
    def _curl_request(self, url):
        """使用curl命令行来获取页面内容"""
        try:
            import subprocess
            self.logger.info("尝试使用curl命令获取页面")
            
            # 创建随机cookie值
            random_id1 = self._generate_random_id()
            random_id2 = self._generate_random_id()
            random_id3 = self._generate_random_id(8)
            random_id4 = self._generate_random_id(30)
            
            # 随机等待5-10秒，模拟人类行为但不太长
            wait_time = random.uniform(5, 10)
            self.logger.info(f"等待 {wait_time:.2f} 秒后使用curl发起请求...")
            time.sleep(wait_time)
            
            # 使用curl命令
            cmd = [
                '/usr/bin/curl',  # 使用绝对路径
                '-s',  # 静默模式
                '-L',  # 跟随重定向
                '-A', self._get_random_user_agent(),  # 随机User-Agent
                '--max-time', '40',  # 最大超时时间
                '--connect-timeout', '40',  # 连接超时
                '-H', 'Accept-Language: en-US,en;q=0.9', 
                '-H', 'Accept: text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                '-H', 'dnt: 1',
                '-H', f'Cookie: npii=btguid/{random_id1}^cguid/{random_id2}^; dp1=bu1p/QEBfX0BAX19AQA**{random_id3}^; s=CgAD4gIBYLDqk9W{random_id4}; ebay=%5Ejs%3D1%5Edv%3D0%5Esjs%3D0%5E',
                '-H', 'Referer: https://www.google.com/',
                '-H', 'Connection: keep-alive',
                '-H', 'Cache-Control: max-age=0',
                url
            ]
            
            # 执行命令
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                self.logger.info(f"curl请求成功，获取内容大小: {len(result.stdout)} 字节")
                return result.stdout
            else:
                self.logger.error(f"curl请求失败: {result.stderr}")
                return None
        except Exception as e:
            self.logger.error(f"执行curl命令失败: {e}")
            return None
    
    def parse_items_from_html(self, html_content):
        """从HTML中解析所有商品信息"""
        soup = BeautifulSoup(html_content, 'html.parser')
        items = []
        
        # 保存页面以便调试
        try:
            debug_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'debug')
            os.makedirs(debug_dir, exist_ok=True)
            debug_file = os.path.join(debug_dir, f'ebay_page_{int(time.time())}.html')
            with open(debug_file, 'w', encoding='utf-8') as f:
                f.write(html_content)
            self.logger.info(f"保存了HTML页面到 {debug_file}")
        except Exception as e:
            self.logger.warning(f"保存HTML失败: {e}")
        
        # 尝试多种可能的CSS选择器
        selector_pairs = [
            ('.s-item__wrapper', None),
            ('.srp-results .s-item', None),
            ('#srp-river-results .s-item', None),
            ('.b-list__items_nofooter .s-item', None),
            ('li.s-item', None),
            ('.srp-river-results li.s-item', None),
            ('div[data-listing-id]', None)
        ]
        
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
        """从容器元素解析商品信息"""
        try:
            # 提取最基本的商品信息
            item_data = {}
            
            # 商品标题
            title_element = container.select_one('.s-item__title')
            if title_element:
                title = title_element.get_text(strip=True)
                # 跳过"Shop on eBay"广告元素
                if title == "Shop on eBay":
                    return None
                item_data['title'] = title
            
            # 商品链接和ID
            link_element = container.select_one('.s-item__link')
            if link_element and 'href' in link_element.attrs:
                url = link_element['href']
                item_data['url'] = url
                
                # 提取商品ID
                match = re.search(r'/(\d+)\?', url)
                if match:
                    item_id = match.group(1)
                    item_data['id'] = item_id
            
            # 商品价格
            price_data = self._extract_price(container)
            item_data['price'] = price_data['value']
            item_data['currency'] = price_data['currency']
            
            # 商品图片
            img_element = container.select_one('.s-item__image img')
            if img_element and 'src' in img_element.attrs:
                image_url = img_element['src']
                # 有时src可能是占位符，检查data-src属性
                if 'data-src' in img_element.attrs and img_element['data-src']:
                    image_url = img_element['data-src']
                # 如果图片URL是相对路径，添加域名
                if image_url.startswith('/'):
                    image_url = 'https://www.ebay.com' + image_url
                item_data['image_url'] = image_url
            
            # 获取销售数量
            sold_element = container.select_one('.s-item__quantitySold')
            if sold_element:
                sold_text = sold_element.get_text(strip=True)
                try:
                    sold_count = int(''.join(filter(str.isdigit, sold_text)))
                    item_data['sold_count'] = sold_count
                except ValueError:
                    item_data['sold_count'] = 0
            else:
                item_data['sold_count'] = 0
            
            # 添加爬取时间
            item_data['scraped_at'] = datetime.now().isoformat()
            
            # 确保至少有ID和标题
            if 'id' in item_data and 'title' in item_data:
                return item_data
            
            return None
        except Exception as e:
            self.logger.error(f"解析商品元素时出错: {str(e)}")
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
        self.logger.info(f"更新店铺数据: {store_name}")
        
        # 添加随机休眠，防止频繁请求
        cooldown = random.uniform(15, 30)  # 适当降低以匹配前端期望
        self.logger.info(f"休眠 {cooldown:.2f} 秒，避免请求过于频繁...")
        time.sleep(cooldown)
        
        # 获取店铺商品 - 使用scrape_all_pages获取所有分页商品
        self.logger.info(f"开始使用多页爬取获取店铺 {store_name} 的所有商品...")
        items = self.scrape_all_pages(store_url, max_pages=10)  # 设置最大爬取10页，可根据需要调整
        
        if not items:
            self.logger.error(f"无法获取店铺 {store_name} 的商品数据")
            
            # 从备份恢复
            backup_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'backups')
            os.makedirs(backup_dir, exist_ok=True)
            backup_file = os.path.join(backup_dir, f"backup_{store_name}_items.json")
            
            if os.path.exists(backup_file):
                self.logger.info(f"从备份文件 {backup_file} 恢复")
                with open(backup_file, 'r', encoding='utf-8') as f:
                    items = json.load(f)
            else:
                return {'new_listings': [], 'price_changes': [], 'removed_listings': []}
        
        self.logger.info(f"成功获取店铺 {store_name} 的商品数据，共 {len(items)} 个商品")
        
        # 将商品列表转换为以ID为键的字典
        current_items_dict = {item['id']: item for item in items if 'id' in item}
        
        # 获取以前的商品列表
        previous_items_json = self.redis.get(f"store:{store_name}:items")
        
        new_listings = []
        price_changes = []
        removed_listings = []
        
        # 检查是否存在旧数据
        if previous_items_json:
            try:
                previous_items = json.loads(previous_items_json)
                previous_items_dict = {item['id']: item for item in previous_items if 'id' in item}
                
                # 检查新上架和价格变动的商品
                for item_id, current_item in current_items_dict.items():
                    if item_id not in previous_items_dict:
                        # 新上架商品
                        new_listings.append(current_item)
                    else:
                        # 检查价格是否变动
                        previous_item = previous_items_dict[item_id]
                        current_price_text = current_item.get('price_text', str(current_item.get('price', 0)))
                        previous_price_text = previous_item.get('price_text', str(previous_item.get('price', 0)))
                        
                        if current_price_text != previous_price_text:
                            # 价格变动
                            change = {
                                'id': item_id,
                                'title': current_item['title'],
                                'url': current_item['url'],
                                'image_url': current_item.get('image_url', ''),
                                'old_price_text': previous_price_text,
                                'new_price_text': current_price_text,
                                'timestamp': int(time.time())
                            }
                            price_changes.append(change)
                
                # 检查下架商品
                for item_id, previous_item in previous_items_dict.items():
                    if item_id not in current_items_dict:
                        # 商品下架
                        removed_listings.append(previous_item)
            except Exception as e:
                self.logger.error(f"处理商品变化时出错: {e}")
                # 所有商品视为新上架
                new_listings = items
        else:
            # 没有旧数据，所有商品都是新上架
            new_listings = items
        
        # 保存当前商品列表到Redis
        if self.redis:
            self.redis.set(f"store:{store_name}:items", json.dumps(items))
            
            # 保存更新时间
            self.redis.set(f"store:{store_name}:last_update", int(time.time()))
            
            # 更新店铺统计信息
            self.redis.set(f"store:{store_name}:stats", json.dumps({
                'total_items': len(items),
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
            json.dump(items, f, ensure_ascii=False, indent=2)
        
        # 记录变更
        if new_listings:
            self.logger.info(f"发现 {len(new_listings)} 个新上架商品")
        if price_changes:
            self.logger.info(f"发现 {len(price_changes)} 个价格变动")
        if removed_listings:
            self.logger.info(f"发现 {len(removed_listings)} 个下架商品")
        
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

    def _generate_random_id(self, length=16):
        """生成随机ID用于cookie"""
        import string
        chars = string.ascii_letters + string.digits
        return ''.join(random.choice(chars) for _ in range(length))

    def parse_item_element(self, element):
        """解析单个商品元素"""
        try:
            # 商品ID
            item_id = self._extract_item_id(element)
            if not item_id:
                return None
            
            # 获取商品标题
            title_element = element.select_one('.s-item__title')
            title = title_element.get_text(strip=True) if title_element else "未知标题"
            
            # 检查是否为新上架商品
            is_new_listing = False
            new_listing_tag = element.select_one('.s-item__title .LIGHT_HIGHLIGHT')
            if new_listing_tag and 'New Listing' in new_listing_tag.get_text(strip=True):
                is_new_listing = True
                # 从标题中移除"New Listing"文本，获取纯标题
                title = title.replace('New Listing', '').strip()
            
            # 商品URL
            link_element = element.select_one('.s-item__link')
            url = link_element.get('href') if link_element else None
            
            # 商品图片
            image_element = element.select_one('.s-item__image-wrapper img')
            image_url = image_element.get('src') if image_element else None
            
            # 商品价格
            price_data = self._extract_price(element)
            
            # 原价（如果有折扣）
            original_price = None
            additional_price = element.select_one('.s-item__additional-price')
            if additional_price:
                try:
                    original_text = additional_price.select_one('.STRIKETHROUGH')
                    if original_text:
                        original_price_text = original_text.get_text(strip=True)
                        original_price = float(re.sub(r'[^\d.]', '', original_price_text))
                except:
                    pass
            
            # 折扣百分比
            discount_percent = None
            discount_element = element.select_one('.s-item__discount')
            if discount_element:
                try:
                    discount_text = discount_element.get_text(strip=True)
                    discount_match = re.search(r'(\d+)%', discount_text)
                    if discount_match:
                        discount_percent = int(discount_match.group(1))
                except:
                    pass
            
            # 商品状态
            status = "未知"
            subtitle = element.select_one('.s-item__subtitle')
            if subtitle:
                status = subtitle.get_text(strip=True)
            
            # 运费信息
            shipping = "未知"
            shipping_element = element.select_one('.s-item__shipping')
            if shipping_element:
                shipping = shipping_element.get_text(strip=True)
            
            # 返回是否包含免费退货信息
            free_returns = False
            returns_element = element.select_one('.s-item__free-returns')
            if returns_element and "Free returns" in returns_element.get_text(strip=True):
                free_returns = True
            
            # 卖家信息
            seller_info = None
            seller_element = element.select_one('.s-item__seller-info-text')
            if seller_element:
                seller_info = seller_element.get_text(strip=True)
            
            # 购买选项
            buy_format = "未知"
            format_element = element.select_one('.s-item__dynamic')
            if format_element:
                buy_format = format_element.get_text(strip=True)
            
            return {
                'id': item_id,
                'title': title,
                'url': url,
                'price': price_data['value'],
                'currency': price_data['currency'],
                'price_text': price_data['price_text'],
                'original_price': original_price,
                'discount_percent': discount_percent,
                'image_url': image_url,
                'status': status,
                'shipping': shipping,
                'free_returns': free_returns,
                'seller_info': seller_info,
                'buy_format': buy_format,
                'is_new_listing': is_new_listing,
                'timestamp': int(time.time())
            }
            
        except Exception as e:
            self.logger.error(f"解析商品元素时出错: {e}")
            return None

    def _extract_item_id(self, element):
        """从商品元素中提取商品ID"""
        try:
            # 从商品URL中提取ID
            link_element = element.select_one('.s-item__link')
            if not link_element:
                return None
            
            url = link_element.get('href')
            if not url:
                return None
            
            # eBay商品URL格式通常是 https://www.ebay.com/itm/123456789
            item_id_match = re.search(r'/itm/(\d+)', url)
            if item_id_match:
                return item_id_match.group(1)
            
            # 某些URL格式可能不同，尝试其他模式
            alternate_match = re.search(r'itm/([^?/]+)', url)
            if alternate_match:
                return alternate_match.group(1)
            
            return None
        except Exception as e:
            self.logger.error(f"提取商品ID时出错: {e}")
            return None
    
    def _extract_price(self, element):
        """从商品元素中提取价格"""
        try:
            price_element = element.select_one('.s-item__price')
            if not price_element:
                return {'value': 0, 'currency': '$', 'price_text': ''}
            
            price_text = price_element.get_text(strip=True)
            # 保存原始价格文本
            original_price_text = price_text
            
            # 提取货币符号
            currency = '$'  # 默认美元符号
            if 'US $' in price_text:
                currency = 'US $'
            elif '£' in price_text:
                currency = '£'
            elif '€' in price_text:
                currency = '€'
            
            # 保存价格文本，但仍然尝试提取数值用于排序和比较
            value = 0
            
            # 如果是价格范围，尝试提取第一个价格作为数值参考
            if 'to' in price_text.lower():
                first_price_match = re.search(r'(\d+(?:\.\d+)?)', price_text)
                if first_price_match:
                    try:
                        value = float(first_price_match.group(1))
                    except ValueError:
                        self.logger.warning(f"无法从价格范围提取数值: {price_text}")
                # 不修改price_text，保留完整范围
            else:
                # 常规价格处理
                # 处理含有单位的价格
                clean_text = price_text
                if '/ea' in clean_text:
                    clean_text = clean_text.split('/ea')[0]
                
                # 处理其他可能的单位
                for unit in ['/kg', '/lb', '/oz', '/pc', '/ct', '/set']:
                    if unit in clean_text:
                        clean_text = clean_text.split(unit)[0]
                        break
                    
                # 处理带逗号的价格
                clean_text = clean_text.replace(',', '')
                
                # 移除货币符号等非数字字符
                price_value = re.sub(r'[^\d.]', '', clean_text.strip())
                
                try:
                    if price_value:
                        value = float(price_value)
                except ValueError:
                    self.logger.warning(f"无法解析价格: {clean_text}")
            
            # 返回包含原始文本和提取值的结果
            return {
                'value': value,  # 用于排序和过滤的数值
                'currency': currency,
                'price_text': original_price_text  # 保留完整的原始价格文本
            }
        except Exception as e:
            self.logger.error(f"提取价格时出错: {e}")
            return {'value': 0, 'currency': '$', 'price_text': ''}

    def scrape_all_pages(self, store_url, max_pages=None):
        """
        抓取多页数据，更全面地获取店铺商品
        
        Args:
            store_url: eBay店铺URL
            max_pages: 最大爬取页数，None表示不限制
                
        Returns:
            包含所有分页商品的列表
        """
        all_items = []
        current_url = store_url
        current_page = 1
        processed_urls = set()  # 跟踪已处理的URL，避免陷入循环
        
        self.logger.info(f"开始多页爬取，起始URL: {store_url}")
        
        while True:
            # 检查是否达到最大页数限制
            if max_pages and current_page > max_pages:
                self.logger.info(f"已达到最大页数限制({max_pages}页)，停止爬取")
                break
                
            # 防止URL重复处理
            if current_url in processed_urls:
                self.logger.warning(f"检测到URL重复，爬取结束: {current_url}")
                break
                
            processed_urls.add(current_url)
            
            # 添加随机延迟，避免被反爬
            if current_page > 1:  # 第一页不延迟，因为会在get_store_items中延迟
                delay = random.uniform(8.0, 15.0)  # 增加延迟时间，避免触发反爬
                self.logger.info(f"等待 {delay:.2f} 秒后请求第 {current_page} 页...")
                time.sleep(delay)
            
            # 获取当前页商品
            self.logger.info(f"正在爬取第 {current_page} 页: {current_url}")
            
            # 使用既有方法获取单页数据
            current_page_items = self.get_store_items(current_url)
            
            if not current_page_items:
                self.logger.warning(f"第 {current_page} 页没有获取到商品数据，爬取结束")
                break
                
            self.logger.info(f"第 {current_page} 页获取到 {len(current_page_items)} 个商品")
            all_items.extend(current_page_items)
            
            # 获取下一页URL
            next_page_url = self._get_next_page_url_from_simple(current_url)
            
            if not next_page_url:
                self.logger.info(f"没有找到下一页，爬取结束")
                break
                
            current_url = next_page_url
            current_page += 1
        
        self.logger.info(f"多页爬取完成，共爬取 {current_page} 页，获取 {len(all_items)} 个商品")
        
        # 去重
        unique_items = {}
        for item in all_items:
            if 'id' in item and item['id']:
                unique_items[item['id']] = item
                
        return list(unique_items.values())

    def _get_next_page_url_from_simple(self, current_url):
        """从simple_requests_scraper中提取的获取下一页URL的逻辑"""
        try:
            # 使用随机请求头
            headers = self.get_random_headers()
            
            # 添加随机延迟
            delay = random.uniform(2.0, 4.0)
            self.logger.info(f"等待 {delay:.2f} 秒后获取下一页URL...")
            time.sleep(delay)
            
            # 发送请求
            response = requests.get(current_url, headers=headers, timeout=30)
            if response.status_code != 200:
                self.logger.warning(f"请求失败，状态码: {response.status_code}")
                return None
            
            # 解析HTML
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 保存当前页面以便调试
            try:
                debug_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'debug')
                os.makedirs(debug_dir, exist_ok=True)
                debug_file = os.path.join(debug_dir, f'page_{int(time.time())}.html')
                with open(debug_file, 'w', encoding='utf-8') as f:
                    f.write(response.text)
            except Exception as e:
                self.logger.warning(f"保存调试页面失败: {e}")
            
            # 方法1: 寻找下一页链接 - 这是eBay最新结构的最可靠方法
            next_link = soup.select_one('a.pagination__next')
            if next_link and 'href' in next_link.attrs:
                next_url = next_link['href']
                self.logger.info(f"方法1: 找到下一页链接: {next_url}")
                return next_url
            
            # 方法2: 从分页列表中找到当前页码，然后找下一页
            pagination = soup.select('ol.pagination__items li a')
            current_page = None
            
            for link in pagination:
                if link.get('aria-current') == 'page':
                    try:
                        current_page = int(link.text.strip())
                        self.logger.info(f"找到当前页码: {current_page}")
                        break
                    except (ValueError, TypeError):
                        pass
                        
            if current_page:
                next_page = current_page + 1
                
                # 寻找下一页链接
                for link in pagination:
                    try:
                        page_num = int(link.text.strip())
                        if page_num == next_page:
                            next_url = link['href']
                            self.logger.info(f"方法2: 找到下一页链接: {next_url}")
                            return next_url
                    except (ValueError, TypeError, KeyError):
                        continue
                        
                # 如果找不到下一页链接，尝试构造URL
                if '_pgn=' in current_url:
                    next_url = re.sub(r'_pgn=\d+', f'_pgn={next_page}', current_url)
                    self.logger.info(f"方法3: 构造下一页URL: {next_url}")
                    return next_url
                else:
                    separator = '&' if '?' in current_url else '?'
                    next_url = f"{current_url}{separator}_pgn={next_page}"
                    self.logger.info(f"方法3: 构造下一页URL: {next_url}")
                    return next_url
                    
            # 方法4: URL中没有页码参数时，添加第2页
            if '_pgn=' not in current_url:
                separator = '&' if '?' in current_url else '?'
                next_url = f"{current_url}{separator}_pgn=2"
                self.logger.info(f"方法4: 添加页码参数构造第2页URL: {next_url}")
                return next_url
                
            self.logger.warning("无法找到下一页链接")
            return None
                
        except Exception as e:
            self.logger.error(f"获取下一页URL时出错: {str(e)}")
            return None