# 邮件通知模块

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import logging
from app.config import Config

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class EmailNotifier:
    def __init__(self):
        """初始化邮件通知器"""
        self.server = Config.MAIL_SERVER
        self.port = Config.MAIL_PORT
        self.use_tls = Config.MAIL_USE_TLS
        self.username = Config.MAIL_USERNAME
        self.password = Config.MAIL_PASSWORD
        self.default_sender = Config.MAIL_DEFAULT_SENDER
    
    def send_email(self, recipient, subject, body, is_html=True):
        """发送邮件"""
        try:
            # 创建邮件
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = self.default_sender
            msg['To'] = recipient
            
            # 添加邮件内容
            if is_html:
                msg.attach(MIMEText(body, 'html'))
            else:
                msg.attach(MIMEText(body, 'plain'))
            
            # 连接到SMTP服务器并发送邮件
            with smtplib.SMTP(self.server, self.port) as server:
                if self.use_tls:
                    server.starttls()
                server.login(self.username, self.password)
                server.sendmail(self.default_sender, recipient, msg.as_string())
            
            logger.info(f"邮件已发送至 {recipient}")
            return True
        
        except Exception as e:
            logger.error(f"发送邮件失败: {e}")
            return False
    
    def notify_new_listings(self, recipient, store_name, new_items):
        """通知新上架商品"""
        if not new_items:
            return False
        
        subject = f"{store_name} - 发现 {len(new_items)} 个新上架商品"
        
        # 构建HTML邮件内容
        html = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; }}
                .container {{ max-width: 800px; margin: 0 auto; }}
                .header {{ background-color: #4CAF50; color: white; padding: 10px; text-align: center; }}
                .item-list {{ padding: 10px; }}
                .item {{ border-bottom: 1px solid #ddd; padding: 10px; margin-bottom: 10px; }}
                .item-header {{ display: flex; justify-content: space-between; }}
                .item-title {{ font-weight: bold; }}
                .item-price {{ color: #e63946; font-weight: bold; }}
                .item-image {{ max-width: 150px; max-height: 150px; margin-right: 10px; float: left; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h2>{store_name} - 新上架商品通知</h2>
                    <p>发现 {len(new_items)} 个新上架商品</p>
                </div>
                <div class="item-list">
        """
        
        for item in new_items:
            html += f"""
                    <div class="item">
                        <div class="item-header">
                            <div class="item-title">{item.get('title', 'N/A')}</div>
                            <div class="item-price">${item.get('price', 0):.2f}</div>
                        </div>
                        <p>
                            <img class="item-image" src="{item.get('image_url', '')}" alt="商品图片">
                            <a href="{item.get('url', '#')}" target="_blank">查看商品</a>
                        </p>
                        <div style="clear: both;"></div>
                    </div>
            """
        
        html += """
                </div>
            </div>
        </body>
        </html>
        """
        
        return self.send_email(recipient, subject, html)
    
    def notify_price_changes(self, recipient, store_name, price_changes):
        """通知价格变动"""
        if not price_changes:
            return False
        
        subject = f"{store_name} - {len(price_changes)} 个商品价格变动"
        
        # 构建HTML邮件内容
        html = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; }}
                .container {{ max-width: 800px; margin: 0 auto; }}
                .header {{ background-color: #3498db; color: white; padding: 10px; text-align: center; }}
                .item-list {{ padding: 10px; }}
                .item {{ border-bottom: 1px solid #ddd; padding: 10px; margin-bottom: 10px; }}
                .item-header {{ display: flex; justify-content: space-between; }}
                .item-title {{ font-weight: bold; }}
                .price-change {{ display: flex; }}
                .old-price {{ text-decoration: line-through; color: #777; margin-right: 10px; }}
                .new-price {{ color: #e63946; font-weight: bold; }}
                .price-up {{ color: #e63946; }}
                .price-down {{ color: #2ecc71; }}
                .item-image {{ max-width: 150px; max-height: 150px; margin-right: 10px; float: left; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h2>{store_name} - 价格变动通知</h2>
                    <p>{len(price_changes)} 个商品价格发生变化</p>
                </div>
                <div class="item-list">
        """
        
        for change in price_changes:
            item = change['item']
            old_price = change['old_price']
            new_price = change['new_price']
            price_diff = new_price - old_price
            price_class = "price-up" if price_diff > 0 else "price-down"
            price_sign = "+" if price_diff > 0 else ""
            
            html += f"""
                    <div class="item">
                        <div class="item-header">
                            <div class="item-title">{item.get('title', 'N/A')}</div>
                            <div class="price-change">
                                <div class="old-price">${old_price:.2f}</div>
                                <div class="new-price">${new_price:.2f}</div>
                                <div class="{price_class}">({price_sign}{price_diff:.2f})</div>
                            </div>
                        </div>
                        <p>
                            <img class="item-image" src="{item.get('image_url', '')}" alt="商品图片">
                            <a href="{item.get('url', '#')}" target="_blank">查看商品</a>
                        </p>
                        <div style="clear: both;"></div>
                    </div>
            """
        
        html += """
                </div>
            </div>
        </body>
        </html>
        """
        
        return self.send_email(recipient, subject, html) 