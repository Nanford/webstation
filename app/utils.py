# 通用工具函数

import re

def is_valid_ebay_url(url):
    """验证是否为有效的eBay店铺URL"""
    if not url:
        return False
        
    # 支持多种eBay域名
    pattern = r'https?://(www\.)?(ebay\.(com|co\.uk|de|fr|com\.au|ca|it|es))/.*'
    return bool(re.match(pattern, url)) 