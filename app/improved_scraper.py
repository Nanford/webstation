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
from app.utils import is_valid_ebay_url
from app.utils import json_dumps
import subprocess

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

logger.setLevel(logging.WARNING)

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
        
        # 支持的eBay域名
        self.supported_domains = [
            'ebay.com',
            'ebay.co.uk',
            'ebay.de',
            'ebay.fr',
            'ebay.com.au',
            'ebay.ca'
        ]
    
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
        """从HTML解析商品列表"""
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # 查找主要内容区域
        result_list = soup.select('.srp-results .s-item__wrapper')
        self.logger.info(f"使用选择器 '.s-item__wrapper' 找到 {len(result_list)} 个商品元素")
        
        # 检查HTML中是否有"New listing"文本
        if 'New listing' in html_content or 'new listing' in html_content.lower():
            self.logger.info("HTML内容中检测到'New listing'文本")
            # 查找所有可能的New Listing标记位置
            new_listing_elements = soup.select('.LIGHT_HIGHLIGHT')
            self.logger.info(f"找到 {len(new_listing_elements)} 个可能的LIGHT_HIGHLIGHT元素")
            for i, elem in enumerate(new_listing_elements):
                self.logger.info(f"LIGHT_HIGHLIGHT元素 #{i+1} 文本: {elem.get_text(strip=True)}")
        
        items = []
        for item_element in result_list:
            item_data = self.parse_item_element(item_element)
            if item_data:
                items.append(item_data)
        
        self.logger.info(f"共解析出 {len(items)} 个商品")
        return items
    
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
            
            # 检测是否为新上架商品（不区分大小写）
            is_new_listing = False
            
            # 保存元素HTML用于调试
            element_html = str(element)
            debug_dir = '/var/www/ebay-store-monitor/debug/items/'
            os.makedirs(debug_dir, exist_ok=True)
            with open(f"{debug_dir}/item_{int(time.time())}_{hash(element_html) % 10000}.html", 'w', encoding='utf-8') as f:
                f.write(element_html)
            
            # 方法1: 直接搜索"New listing"字符串（最可靠的方法）
            if 'New listing' in element_html or 'new listing' in element_html.lower():
                is_new_listing = True
                self.logger.info(f"在HTML中找到'New listing'文本: {title[:50]}...")
            
            # 方法2: 检查LIGHT_HIGHLIGHT类（您提供的HTML结构）
            if not is_new_listing:
                highlight_elements = element.select('.LIGHT_HIGHLIGHT')
                for highlight in highlight_elements:
                    text = highlight.get_text(strip=True)
                    if 'new listing' in text.lower():
                        is_new_listing = True
                        self.logger.info(f"在LIGHT_HIGHLIGHT中找到'New listing': {text} - {title[:50]}...")
                        break
            
            # 方法3: 检查标题区域中的所有span元素
            if not is_new_listing:
                title_element = element.select_one('.s-item__title')
                if title_element:
                    for span in title_element.select('span'):
                        text = span.get_text(strip=True)
                        if 'new listing' in text.lower():
                            is_new_listing = True
                            self.logger.info(f"在标题span中找到'New listing': {text} - {title[:50]}...")
                            break
            
            # 记录结果
            if is_new_listing:
                self.logger.info(f"✅ 确认为New listing: {title[:50]}...")
            
            # 商品URL
            link_element = element.select_one('.s-item__link')
            url = link_element.get('href') if link_element else None
            
            # 商品图片
            image_element = element.select_one('.s-item__image-wrapper img')
            image_url = image_element.get('src') if image_element else None
            
            # 商品价格
            price_element = element.select_one('.s-item__price')
            price_data = {'value': 0.0, 'currency': 'USD', 'price_text': ''}
            
            if price_element:
                price_text = price_element.get_text(strip=True)
                price_data['price_text'] = price_text
                
                # 识别货币符号
                currency_map = {
                    '$': 'USD',
                    '£': 'GBP',
                    '€': 'EUR',
                    '¥': 'JPY',
                    'C$': 'CAD',
                    'A$': 'AUD'
                }
                
                # 判断货币类型
                for symbol, code in currency_map.items():
                    if symbol in price_text:
                        price_data['currency'] = code
                        break
                
                # 提取数字
                price_match = re.search(r'[\d,.]+', price_text)
                if price_match:
                    try:
                        # 清理英国格式的价格 (£1,234.56)
                        price_value = price_match.group(0).replace(',', '')
                        price_data['value'] = float(price_value)
                    except:
                        self.logger.warning(f"无法解析价格: {price_text}")
            
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
            
            # 获取上架时间 - 支持多种格式
            listing_date = "未知"
            parsed_date = None  # 新增：用于存储解析后的日期对象
            
            # 方法1：查找日期标签内的BOLD文本（常见格式）
            date_element = element.select_one('.s-item__listingDate')
            if date_element:
                bold_span = date_element.select_one('.BOLD')
                if bold_span:
                    listing_date = bold_span.get_text(strip=True)
                else:
                    listing_date = date_element.get_text(strip=True)
                
                self.logger.info(f"找到上架时间: {listing_date}")
                
                # 解析"14-Mar 11:46"这种格式
                import datetime
                date_pattern = re.compile(r'(\d{1,2})-([A-Za-z]{3})\s+(\d{1,2}):(\d{2})')
                match = date_pattern.search(listing_date)
                
                if match:
                    day = int(match.group(1))
                    month_abbr = match.group(2)
                    hour = int(match.group(3))
                    minute = int(match.group(4))
                    
                    # 月份缩写转数字
                    months = {
                        'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6,
                        'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12
                    }
                    
                    month = months.get(month_abbr, 0)
                    if month > 0:
                        # 假设是今年
                        current_year = datetime.datetime.now().year
                        
                        # 构建完整日期时间
                        try:
                            parsed_date = datetime.datetime(
                                year=current_year, 
                                month=month, 
                                day=day,
                                hour=hour,
                                minute=minute
                            )
                            
                            # 格式化为更友好的表示
                            formatted_date = parsed_date.strftime('%Y年%m月%d日 %H:%M:%S')
                            listing_date = f"{listing_date} (完整日期: {formatted_date})"
                            self.logger.info(f"转换为完整日期: {listing_date}")
                        except ValueError as e:
                            self.logger.warning(f"日期转换失败: {e}")
            
            # 备用方法：查找其他可能包含日期的元素
            if listing_date == "未知":
                for dynamic in element.select('.s-item__dynamic'):
                    if 'listingDate' in dynamic.get('class', []):
                        continue  # 已经处理过
                    
                    date_text = dynamic.get_text(strip=True)
                    if '上架' in date_text or 'listed' in date_text.lower() or re.search(r'\d{1,2}-[A-Za-z]{3}', date_text):
                        listing_date = date_text
                        self.logger.info(f"从其他元素获取上架时间: {listing_date}")
                        break
            
            # 新增：检查是否为昨日上架
            is_yesterday_listing = False
            if parsed_date:
                today = datetime.datetime.now().date()
                yesterday = today - datetime.timedelta(days=1)
                
                listing_date_only = parsed_date.date()
                if listing_date_only == yesterday:
                    is_yesterday_listing = True
                    self.logger.info(f"检测到昨日上架商品: {title[:50]}... 上架时间: {listing_date}")
            
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
                'is_yesterday_listing': is_yesterday_listing,  # 新增：昨日上架标记
                'listing_date': listing_date,
                'parsed_date': parsed_date,  # 新增：解析后的日期对象
                'timestamp': int(time.time())
            }
            
        except Exception as e:
            self.logger.error(f"解析商品元素失败: {str(e)}")
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

    def scrape_all_pages(self, url, max_pages=None):
        """爬取所有页面的商品信息"""
        self.logger.info(f"开始多页爬取eBay店铺: {url}")
        all_items = []
        page_num = 1
        current_url = url
        
        # 确保URL中有正确的排序参数（最近上架优先）
        if '_sop=' not in current_url:
            separator = '&' if '?' in current_url else '?'
            current_url = f"{current_url}{separator}_sop=10"
            self.logger.info(f"添加了排序参数，更新后的URL: {current_url}")
        
        # 构造基础URL，用于后续分页
        base_url = current_url
        
        while True:
            self.logger.info(f"正在爬取第 {page_num} 页: {current_url}")
            
            # 获取当前页面的HTML内容
            html_content = self._get_html_content(current_url)
            if not html_content:
                self.logger.error(f"无法获取页面内容，URL: {current_url}")
                break
            
            # 解析当前页面的商品信息
            items = self.parse_items_from_html(html_content)
            if items:
                all_items.extend(items)
                self.logger.info(f"第 {page_num} 页爬取成功，获取到 {len(items)} 个商品")
            else:
                self.logger.warning(f"第 {page_num} 页没有找到商品")
            
            # 检查是否达到最大页数限制
            if max_pages and page_num >= max_pages:
                self.logger.info(f"已达到最大页数限制 ({max_pages} 页)，停止爬取")
                break
            
            # ------------ 关键修改：强化翻页逻辑 ------------
            # 1. 尝试从HTML中提取"下一页"链接
            next_page_url = None
            
            # 保存HTML用于调试
            debug_path = f"/var/www/ebay-store-monitor/debug/pagination_page_{page_num}.html"
            with open(debug_path, 'w', encoding='utf-8') as f:
                f.write(html_content)
            self.logger.info(f"已保存第 {page_num} 页HTML到 {debug_path}")
            
            try:
                soup = BeautifulSoup(html_content, 'html.parser')
                # 寻找各种可能的"下一页"链接
                next_buttons = []
                
                # 方法1: 官方分页控件
                next_buttons.extend(soup.select('.pagination__next'))
                next_buttons.extend(soup.select('a.pagination__item[rel="next"]'))
                
                # 方法2: 包含"Next"文本的链接
                for a in soup.select('a'):
                    if a.get_text(strip=True) in ['Next', '下一页', 'Next page']:
                        next_buttons.append(a)
                
                # 检查找到的按钮
                self.logger.info(f"找到 {len(next_buttons)} 个可能的'下一页'按钮")
                
                # 尝试从按钮中获取URL
                for btn in next_buttons:
                    href = btn.get('href')
                    if href:
                        next_page_url = href
                        self.logger.info(f"从按钮获取到下一页URL: {next_page_url}")
                        break
            except Exception as e:
                self.logger.error(f"从HTML提取下一页URL失败: {str(e)}")
            
            # 2. 如果没有找到"下一页"链接，手动构造
            if not next_page_url:
                self.logger.info("没有从HTML中找到下一页链接，尝试手动构造")
                
                # 如果已经有页码参数，替换它
                next_page = page_num + 1
                if '_pgn=' in base_url:
                    next_page_url = re.sub(r'_pgn=\d+', f'_pgn={next_page}', base_url)
                else:
                    # 否则添加页码参数
                    separator = '&' if '?' in base_url else '?'
                    next_page_url = f"{base_url}{separator}_pgn={next_page}"
                    
                self.logger.info(f"手动构造的下一页URL: {next_page_url}")
            
            # 3. 使用构造的URL继续爬取
            current_url = next_page_url
            page_num += 1
            
            # 添加延迟，避免频繁请求
            time.sleep(1)
        
        self.logger.info(f"多页爬取完成，共爬取 {page_num-1} 页，获取 {len(all_items)} 个商品")
        return all_items

    def validate_url(self, url):
        """验证是否为有效的eBay URL"""
        return is_valid_ebay_url(url)

    def _get_html_content(self, url):
        """获取页面HTML内容"""
        self.logger.info(f"正在获取页面内容: {url}")
        
        try:
            # 使用请求库获取HTML内容
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1'
            }
            
            # 添加随机延迟，避免被识别为爬虫
            time.sleep(random.uniform(0.5, 2.0))
            
            # 使用curl命令获取HTML内容 (更可靠)
            curl_command = [
                'curl', '-s', '-L',
                '-A', headers['User-Agent'],
                '-H', f'Accept: {headers["Accept"]}',
                '-H', f'Accept-Language: {headers["Accept-Language"]}',
                url
            ]
            
            result = subprocess.run(curl_command, capture_output=True, text=True)
            html_content = result.stdout
            
            if not html_content:
                self.logger.error(f"curl返回空内容: {result.stderr}")
                return None
            
            # 保存HTML内容用于调试
            debug_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'debug')
            os.makedirs(debug_dir, exist_ok=True)
            
            html_filename = os.path.join(debug_dir, f"ebay_page_{int(time.time())}.html")
            with open(html_filename, 'w', encoding='utf-8') as f:
                f.write(html_content)
            self.logger.info(f"保存了HTML页面到 {html_filename}")
            
            # 检查页面内容是否有效
            items_count = html_content.count('s-item__wrapper')
            if items_count > 0:
                self.logger.info(f"通过curl成功获取HTML内容，检测到约 {items_count} 个商品元素")
            else:
                self.logger.warning("获取的HTML内容中没有检测到商品元素")
            
            return html_content
            
        except Exception as e:
            self.logger.error(f"获取HTML内容时出错: {str(e)}")
            return None