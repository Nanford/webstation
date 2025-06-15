# eBay店铺监控系统配置文件

import os
from datetime import timedelta

class Config:
    # Flask配置
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'your-secret-key'
    
    # Redis配置
    REDIS_HOST = os.environ.get('REDIS_HOST') or 'localhost'
    REDIS_PORT = int(os.environ.get('REDIS_PORT') or 6379)
    REDIS_DB = int(os.environ.get('REDIS_DB') or 0)
    REDIS_PASSWORD = '******'  # 确认这是正确密码
    REDIS_USERNAME = None  # 或者设置实际用户名
    
    # 邮件配置
    MAIL_SERVER = 'smtp.qq.com'
    MAIL_PORT = 465
    MAIL_USE_TLS = False
    MAIL_USE_SSL = True
    MAIL_USERNAME = '***********'  # 例如：12345678@qq.com
    MAIL_PASSWORD = '*************'  # 不是QQ密码
    MAIL_DEFAULT_SENDER = '**************'
    
    # 爬虫配置
    SCRAPE_INTERVAL = int(os.environ.get('SCRAPE_INTERVAL') or 3600)  # 默认每小时爬取一次
    USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36' 
    
    # 爬虫延迟配置
    MIN_DELAY = 1  # 最小延迟秒数
    MAX_DELAY = 5  # 最大延迟秒数
    
    # 重试配置
    MAX_RETRIES = 3  # 最大重试次数
    RETRY_DELAY_FACTOR = 2  # 重试延迟因子(指数退避)
    
    # 代理配置（如果使用）
    PROXY_LIST = []  # 代理服务器列表
    PROXY_FILE = None  # 代理文件路径
