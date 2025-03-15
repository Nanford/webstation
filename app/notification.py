# 邮件通知模块

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import logging
from app.config import Config  # 只导入Config类

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class EmailNotifier:
    def __init__(self):
        """初始化邮件通知器"""
        self.server = Config.MAIL_SERVER
        self.port = Config.MAIL_PORT
        self.use_tls = Config.MAIL_USE_TLS
        self.use_ssl = getattr(Config, 'MAIL_USE_SSL', False)  # 添加SSL支持
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
            if self.use_ssl:
                # 使用直接管理SMTP_SSL连接，而不是with语句
                try:
                    server = smtplib.SMTP_SSL(self.server, self.port)
                    server.login(self.username, self.password)
                    result = server.sendmail(self.default_sender, recipient, msg.as_string())
                    # 检查sendmail的返回结果，空字典表示成功
                    send_success = (result == {})
                    try:
                        server.quit()
                    except:
                        # 忽略关闭连接时的错误
                        pass
                    # 如果sendmail成功，则认为邮件发送成功
                    if send_success:
                        logger.info(f"邮件已发送至 {recipient}")
                        return True
                    else:
                        logger.error(f"发送邮件失败，返回结果: {result}")
                        return False
                except Exception as ssl_error:
                    logger.error(f"SSL邮件发送失败: {ssl_error}")
                    raise
            else:
                with smtplib.SMTP(self.server, self.port) as server:
                    if self.use_tls:
                        server.starttls()
                    server.login(self.username, self.password)
                    server.sendmail(self.default_sender, recipient, msg.as_string())
            
            # 非SSL模式下的成功信息已经在上面的代码中处理
            if not self.use_ssl:
                logger.info(f"邮件已发送至 {recipient}")
                return True
            return False  # 如果代码执行到这里，说明SSL模式下没有成功
        
        except Exception as e:
            logger.error(f"发送邮件失败: {e}")
            return False
    
    def notify_new_listings(self, recipient, store_name, new_items):
        """通知新上架商品"""
        
        # 过滤只发送真正的"New listing"商品
        true_new_items = [item for item in new_items if item.get('is_new_listing')]
        
        # 如果没有真正的新上架商品，直接返回
        if not true_new_items:
            self.logger.info(f"没有真正标记为'New listing'的商品，不发送通知")
            return True
        
        try:
            # 创建邮件
            msg = MIMEMultipart('alternative')
            msg['Subject'] = f'【eBay店铺监控】{store_name} 有新上架商品'
            msg['From'] = self.default_sender
            msg['To'] = recipient
            
            # 邮件HTML内容
            html = f"""
            <html>
            <head>
                <style>
                    .container {{ max-width: 800px; margin: 0 auto; font-family: Arial, sans-serif; }}
                    .header {{ background-color: #00509d; color: white; padding: 15px; text-align: center; }}
                    .item {{ border-bottom: 1px solid #eee; padding: 15px; margin-bottom: 15px; }}
                    .item-image {{ max-width: 200px; max-height: 200px; }}
                    .new-listing-badge {{ background-color: #ff4631; color: white; font-size: 12px; padding: 3px 8px; border-radius: 3px; margin-right: 10px; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h2>{store_name} 新上架商品通知</h2>
                        <p>发现 {len(true_new_items)} 个新上架商品</p>
                    </div>
            """
            
            for item in true_new_items:
                price = item.get('price', 0)
                shipping = item.get('shipping', '未知')
                status = item.get('status', '未知')
                listing_date = item.get('listing_date', '未知')
                
                html += f"""
                    <div class="item">
                        <h3>
                            <span class="new-listing-badge">新上架</span>
                            <a href="{item.get('url', '#')}">{item.get('title', '未知标题')}</a>
                        </h3>
                        <div>
                            <img src="{item.get('image_url', '')}" class="item-image" alt="{item.get('title', '商品图片')}">
                        </div>
                        <p>价格: <strong>{item.get('currency', '$')}{price:.2f}</strong></p>
                        <p>运费: {shipping}</p>
                        <p>状态: {status}</p>
                        <p>上架时间: {listing_date}</p>
                    </div>
                """
            
            html += """
                </div>
            </body>
            </html>
            """
            
            # 添加邮件内容
            msg.attach(MIMEText(html, 'html'))
            
            # 发送邮件
            if self.use_ssl:
                server = smtplib.SMTP_SSL(self.server, self.port)
            else:
                server = smtplib.SMTP(self.server, self.port)
                if self.use_tls:
                    server.starttls()
            
            server.login(self.username, self.password)
            server.sendmail(self.default_sender, recipient, msg.as_string())
            server.quit()
            
            self.logger.info(f"成功发送新上架商品通知邮件到 {recipient}")
            return True
        
        except Exception as e:
            self.logger.error(f"发送新上架商品通知邮件失败: {str(e)}")
            return False
    
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

def send_notification_email(recipient_email, changes, store_id):
    """发送商品变动通知邮件"""
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f'【eBay店铺监控】店铺 {store_id} 有新变化'
        msg['From'] = Config.MAIL_USERNAME
        msg['To'] = recipient_email
        
        # 构建HTML邮件内容
        html_content = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; }}
                .container {{ max-width: 600px; margin: 0 auto; }}
                .section {{ margin-bottom: 20px; }}
                .item {{ margin-bottom: 10px; border-bottom: 1px solid #eee; padding-bottom: 10px; }}
                .price-change {{ color: red; font-weight: bold; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h2>eBay店铺监控 - 变化通知</h2>
                <p>您监控的店铺 {store_id} 有以下变化：</p>
        """
        
        # 新上架商品
        if changes['new_items']:
            html_content += """
                <div class="section">
                    <h3>新上架商品</h3>
            """
            
            for item in changes['new_items']:
                html_content += f"""
                    <div class="item">
                        <p><strong>{item['title']}</strong></p>
                        <p>价格: ${item['price']}</p>
                        <p><a href="{item['url']}">查看商品</a></p>
                    </div>
                """
            
            html_content += "</div>"
        
        # 价格变化商品
        if changes['price_changes']:
            html_content += """
                <div class="section">
                    <h3>价格变化商品</h3>
            """
            
            for change in changes['price_changes']:
                item = change['item']
                html_content += f"""
                    <div class="item">
                        <p><strong>{item['title']}</strong></p>
                        <p>原价: ${change['old_price']} → 现价: <span class="price-change">${change['new_price']}</span></p>
                        <p><a href="{item['url']}">查看商品</a></p>
                    </div>
                """
            
            html_content += "</div>"
        
        # 下架商品
        if changes['removed_items']:
            html_content += """
                <div class="section">
                    <h3>已下架商品</h3>
            """
            
            for item in changes['removed_items']:
                html_content += f"""
                    <div class="item">
                        <p><strong>{item['title']}</strong></p>
                        <p>价格: ${item['price']}</p>
                    </div>
                """
            
            html_content += "</div>"
        
        html_content += """
            </div>
        </body>
        </html>
        """
        
        msg.attach(MIMEText(html_content, 'html'))
        
        # 发送邮件
        with smtplib.SMTP(Config.MAIL_SERVER, Config.MAIL_PORT) as server:
            server.starttls()
            server.login(Config.MAIL_USERNAME, Config.MAIL_PASSWORD)
            server.send_message(msg)
        
        return True
    
    except Exception as e:
        logger.error(f"发送邮件失败: {str(e)}")
        return False 