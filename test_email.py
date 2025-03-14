#!/usr/bin/env python3
"""
测试邮件通知功能
"""

import logging
import sys
from app.notification import EmailNotifier
from app.config import Config

# 配置日志
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_email_notification():
    """测试邮件通知功能"""
    logger.info("开始测试邮件通知功能")
    
    # 显示当前邮件配置
    logger.info(f"邮件服务器配置: {Config.MAIL_SERVER}:{Config.MAIL_PORT}")
    logger.info(f"发件人: {Config.MAIL_DEFAULT_SENDER}")
    
    # 初始化EmailNotifier
    notifier = EmailNotifier()
    
    # 获取邮箱地址
    recipient = input("请输入接收测试邮件的邮箱地址: ")
    
    # 测试简单邮件发送
    logger.info("正在发送简单测试邮件...")
    simple_result = notifier.send_email(
        recipient=recipient,
        subject="eBay店铺监控 - 邮件测试",
        body="""
        <html>
        <body>
            <h2>eBay店铺监控系统</h2>
            <p>这是一封测试邮件，用于验证邮件通知功能是否正常。</p>
            <p>如果您收到这封邮件，说明邮件发送功能正常。</p>
        </body>
        </html>
        """
    )
    
    if simple_result:
        logger.info("简单测试邮件发送成功")
    else:
        logger.warning("脚本报告邮件发送失败，但实际上可能已成功发送")
        user_confirm = input("请检查您的邮箱，如果已收到邮件请输入'y'继续测试，否则输入'n'中止: ")
        if user_confirm.lower() == 'y':
            logger.info("用户确认邮件已收到，继续测试...")
            simple_result = True
        else:
            logger.error("简单测试邮件发送失败")
            return False
    
    # 测试新商品通知
    logger.info("正在发送新商品通知测试...")
    new_items = [
        {
            'id': 'test123',
            'title': '测试商品1 - 新上架',
            'price': 99.99,
            'url': 'https://www.ebay.com/itm/test123',
            'image_url': 'https://i.ebayimg.com/images/g/test/s-l500.jpg',
            'status': '全新',
            'shipping': '免运费'
        },
        {
            'id': 'test456',
            'title': '测试商品2 - 限时特价',
            'price': 49.99,
            'url': 'https://www.ebay.com/itm/test456',
            'image_url': 'https://i.ebayimg.com/images/g/test/s-l500.jpg',
            'status': '二手',
            'shipping': '$4.99 运费'
        }
    ]
    
    new_items_result = notifier.notify_new_listings(
        recipient=recipient,
        store_name="测试店铺",
        new_items=new_items
    )
    
    if new_items_result:
        logger.info("新商品通知测试邮件发送成功")
    else:
        logger.error("新商品通知测试邮件发送失败")
    
    # 测试价格变动通知
    logger.info("正在发送价格变动通知测试...")
    price_changes = [
        {
            'item': {
                'id': 'test789',
                'title': '测试商品3 - 涨价',
                'price': 159.99,
                'url': 'https://www.ebay.com/itm/test789',
                'image_url': 'https://i.ebayimg.com/images/g/test/s-l500.jpg'
            },
            'old_price': 129.99,
            'new_price': 159.99
        },
        {
            'item': {
                'id': 'test101',
                'title': '测试商品4 - 降价',
                'price': 79.99,
                'url': 'https://www.ebay.com/itm/test101',
                'image_url': 'https://i.ebayimg.com/images/g/test/s-l500.jpg'
            },
            'old_price': 99.99,
            'new_price': 79.99
        }
    ]
    
    price_changes_result = notifier.notify_price_changes(
        recipient=recipient,
        store_name="测试店铺",
        price_changes=price_changes
    )
    
    if price_changes_result:
        logger.info("价格变动通知测试邮件发送成功")
    else:
        logger.error("价格变动通知测试邮件发送失败")
    
    logger.info("所有测试完成")
    return simple_result and new_items_result and price_changes_result

if __name__ == "__main__":
    success = test_email_notification()
    sys.exit(0 if success else 1) 