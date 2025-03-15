# 通用工具函数

import re
import urllib.parse
import logging
import json
from datetime import datetime

logger = logging.getLogger(__name__)

def is_valid_ebay_url(url):
    """验证是否为有效的eBay商店URL"""
    if not url:
        logger.warning("URL为空")
        return False
    
    # 检查URL是否有基本格式
    if not url.startswith(('http://', 'https://')):
        logger.warning(f"URL格式错误: {url}")
        return False
    
    # 解析URL
    parsed_url = urllib.parse.urlparse(url)
    
    # 检查是否为eBay域名
    valid_domains = [
        'ebay.com', 'www.ebay.com',
        'ebay.co.uk', 'www.ebay.co.uk',
        'ebay.de', 'www.ebay.de',
        'ebay.com.au', 'www.ebay.com.au'
    ]
    
    domain_valid = any(parsed_url.netloc.endswith(domain) for domain in valid_domains)
    
    if not domain_valid:
        logger.warning(f"非eBay域名: {parsed_url.netloc}")
        return False
    
    # 检查是否包含店铺相关参数
    store_indicators = [
        '_ssn=', 'store_name=', 'sch/m.html?', 'usr/', '_sop=', 'sch/'
    ]
    
    has_store_indicator = any(indicator in url for indicator in store_indicators)
    
    if not has_store_indicator:
        logger.warning(f"URL不包含商店标识: {url}")
        return False
    
    logger.info(f"有效的eBay URL: {url}")
    return True 

class DateTimeEncoder(json.JSONEncoder):
    """自定义JSON编码器，处理datetime对象"""
    def default(self, obj):
        if isinstance(obj, datetime):
            # 将datetime转换为ISO格式字符串
            return obj.isoformat()
        # 对于其他类型，使用默认方法
        return super().default(obj)

def json_dumps(obj):
    """使用自定义编码器进行JSON序列化"""
    return json.dumps(obj, cls=DateTimeEncoder)

def json_loads(json_str):
    """JSON反序列化函数"""
    return json.loads(json_str)