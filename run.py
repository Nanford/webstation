# 应用程序入口

from app import create_app
import logging
from flask import Flask
import os

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 创建应用实例
app = create_app()

# 添加Jinja2过滤器
@app.template_filter('timestamp_to_date')
def timestamp_to_date(timestamp):
    """将时间戳转换为日期字符串"""
    from datetime import datetime
    dt = datetime.fromtimestamp(timestamp)
    return dt.strftime('%Y-%m-%d %H:%M')

@app.template_filter('truncate')
def truncate_filter(s, length=50, end='...'):
    """截断长文本并添加省略号"""
    if s and len(s) > length:
        return s[:length] + end
    return s

if __name__ == '__main__':
    # 获取端口配置
    port = int(os.environ.get('PORT', 5000))
    
    # 运行应用
    logger.info(f"启动应用，运行在端口 {port}")
    app.run(host='0.0.0.0', port=port, debug=True) 