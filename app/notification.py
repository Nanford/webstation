# 邮件通知模块

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import logging
from app.config import Config  # 只导入Config类
import time

# 配置日志
logging.basicConfig(level=logging.WARNING, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
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
        
        # 初始化日志记录器
        self.logger = logging.getLogger('app.notification')
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.WARNING)
    
    def send_email(self, recipient, subject, body, is_html=True):
        """发送邮件"""
        server = None  #确保server在finally块中可用
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
                try:
                    self.logger.info(f"正在尝试使用SSL连接到 {self.server}:{self.port} 发送邮件至 {recipient}")
                    server = smtplib.SMTP_SSL(self.server, self.port, timeout=10) # 添加超时
                    server.login(self.username, self.password)
                    self.logger.info(f"SSL连接成功并登录，准备发送邮件至 {recipient}")
                    result = server.sendmail(self.default_sender, recipient, msg.as_string())
                    
                    if not result:  # 空字典表示所有收件人都成功
                        self.logger.info(f"邮件已成功发送至 {recipient} (SSL)")
                        return True
                    else:
                        # result 是一个字典，键是发送失败的收件人，值是错误信息
                        for failed_recipient, error_info in result.items():
                            self.logger.error(f"通过SSL发送邮件至 {failed_recipient} 失败: {error_info}")
                        return False
                except smtplib.SMTPException as ssl_smtp_error:
                    self.logger.error(f"SSL邮件发送过程中发生SMTP错误 (收件人: {recipient}): {ssl_smtp_error}", exc_info=True)
                    return False
                except Exception as ssl_error:
                    self.logger.error(f"SSL邮件发送失败 (收件人: {recipient}): {ssl_error}", exc_info=True)
                    return False #确保连接错误等也返回False
            else: # 使用TLS或无加密
                try:
                    self.logger.info(f"正在尝试使用TLS/无加密连接到 {self.server}:{self.port} 发送邮件至 {recipient}")
                    server = smtplib.SMTP(self.server, self.port, timeout=10) # 添加超时
                    if self.use_tls:
                        server.starttls()
                    server.login(self.username, self.password)
                    self.logger.info(f"TLS/无加密连接成功并登录，准备发送邮件至 {recipient}")
                    result = server.sendmail(self.default_sender, recipient, msg.as_string())

                    if not result: # 空字典表示所有收件人都成功
                        self.logger.info(f"邮件已成功发送至 {recipient} (TLS/无加密)")
                        return True
                    else:
                        for failed_recipient, error_info in result.items():
                            self.logger.error(f"通过TLS/无加密发送邮件至 {failed_recipient} 失败: {error_info}")
                        return False
                except smtplib.SMTPException as smtp_error:
                    self.logger.error(f"TLS/无加密邮件发送过程中发生SMTP错误 (收件人: {recipient}): {smtp_error}", exc_info=True)
                    return False
                except Exception as e:
                    self.logger.error(f"TLS/无加密邮件发送失败 (收件人: {recipient}): {e}", exc_info=True)
                    return False
        
        except Exception as e:
            # 捕获邮件构建等早期阶段的错误
            self.logger.error(f"构建或准备发送邮件时发生意外错误 (收件人: {recipient}): {e}", exc_info=True)
            return False
        finally:
            if server:
                try:
                    server.quit()
                    self.logger.info(f"已关闭与邮件服务器的连接 (针对 {recipient})")
                except Exception as e:
                    self.logger.warning(f"关闭邮件服务器连接时发生错误 (针对 {recipient}): {e}", exc_info=True)
    
    def notify_new_listings(self, recipient, store_name, new_items):
        """通知新上架商品"""
        
        # 过滤只发送真正的"New listing"商品
        true_new_items = [item for item in new_items if item.get('is_new_listing')]
        
        # 如果没有真正的新上架商品，直接返回
        if not true_new_items:
            self.logger.info(f"没有真正标记为'New listing'的商品，不为店铺 {store_name} 发送新上架通知给 {recipient}")
            return True # 认为操作成功，因为没有需要通知的内容
        
        try:
            subject = f'【eBay店铺监控】{store_name} 有新上架商品 ({len(true_new_items)}个)' # 更新标题以包含数量
            
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
                        <p>上架时间: <span style="color: #0066cc; font-weight: bold;">{listing_date}</span></p>
                    </div>
                """
            
            html += """
                </div>
            </body>
            </html>
            """
            
            # 使用统一的 send_email 方法
            success = self.send_email(recipient, subject, html, is_html=True)
            if success:
                self.logger.info(f"成功发送新上架商品通知邮件到 {recipient} (店铺: {store_name})")
            else:
                self.logger.error(f"发送新上架商品通知邮件失败到 {recipient} (店铺: {store_name})")
            return success
        
        except Exception as e:
            self.logger.error(f"构建新上架商品通知邮件时发生错误 (店铺: {store_name}, 收件人: {recipient}): {str(e)}", exc_info=True)
            return False
    
    def notify_price_changes(self, recipient, store_name, price_changes):
        """通知价格变动"""
        if not price_changes:
            self.logger.info(f"店铺 {store_name}: 没有价格变动，不发送通知给 {recipient}") # 增加店铺和收件人信息
            return True
        
        subject = f"【eBay店铺监控】{store_name} - {len(price_changes)} 个商品价格变动" # 统一邮件标题格式
        
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
                .item-header {{ display: flex; justify-content: space-between; align-items: center;}}
                .item-title {{ font-weight: bold; flex-grow: 1; margin-right: 10px;}}
                .price-change {{ display: flex; align-items: baseline; }}
                .old-price {{ text-decoration: line-through; color: #777; margin-right: 10px; }}
                .new-price {{ font-weight: bold; margin-right: 5px;}}
                .price-up {{ color: #e63946; }}
                .price-down {{ color: #2ecc71; }}
                .item-image-container {{ width: 100px; height: 100px; margin-right: 15px; float: left; overflow: hidden; display: flex; justify-content: center; align-items: center;}}
                .item-image {{ max-width: 100%; max-height: 100%; object-fit: contain; }}
                .item-details p {{ margin: 5px 0; }}
                .clear {{ clear: both; }}
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
            item = change.get('item', {}) # 确保 item 存在
            old_price = change.get('old_price', 0)
            new_price = change.get('new_price', 0)
            
            # 确保价格是数值类型，以便进行比较和格式化
            try:
                old_price_float = float(old_price)
                new_price_float = float(new_price)
                price_diff = new_price_float - old_price_float
            except (ValueError, TypeError):
                price_diff = 0 # 如果价格无效，则差异为0
                old_price_float = old_price # 保留原始值用于显示
                new_price_float = new_price # 保留原始值用于显示


            price_class = "price-up" if price_diff > 0 else ("price-down" if price_diff < 0 else "price-same")
            price_sign = "+" if price_diff > 0 else ""
            currency = item.get('currency', '$') # 从item获取货币符号

            # 构建价格显示字符串，处理可能的非数值情况
            old_price_display = f"{currency}{old_price_float:.2f}" if isinstance(old_price_float, (int, float)) else str(old_price)
            new_price_display = f"{currency}{new_price_float:.2f}" if isinstance(new_price_float, (int, float)) else str(new_price)
            price_diff_display = f"({price_sign}{currency}{price_diff:.2f})" if isinstance(price_diff, (int, float)) and price_diff != 0 else ""


            html += f"""
                    <div class="item">
                        <div class="item-image-container">
                            <img class="item-image" src="{item.get('image_url', '')}" alt="商品图片">
                        </div>
                        <div class="item-details">
                            <div class="item-header">
                                <div class="item-title"><a href="{item.get('url', '#')}" target="_blank">{item.get('title', 'N/A')}</a></div>
                                <div class="price-change">
                                    <div class="old-price">{old_price_display}</div>
                                    <div class="new-price {price_class}">{new_price_display}</div>
                                    <div class="{price_class}">{price_diff_display}</div>
                                </div>
                            </div>
                        </div>
                        <div class="clear"></div>
                    </div>
            """
        
        html += """
                </div>
            </div>
        </body>
        </html>
        """
        
        # 使用统一的 send_email 方法
        success = self.send_email(recipient, subject, html, is_html=True)
        if success:
            self.logger.info(f"成功发送价格变动通知邮件到 {recipient} (店铺: {store_name})")
        else:
            self.logger.error(f"发送价格变动通知邮件失败到 {recipient} (店铺: {store_name})")
        return success

    def notify_price_comparison(self, recipient: str, comparison_config: dict, comparison_result: dict) -> bool:
        """发送价格对比通知邮件"""
        try:
            comparison_name = comparison_config.get('name', '价格对比')
            my_listing = comparison_config.get('my_listing', {})
            competitor_listing = comparison_config.get('competitor_listing', {})
            
            # 获取对比结果
            my_price_data = comparison_result.get('my_price', {})
            competitor_price_data = comparison_result.get('competitor_price', {})
            result = comparison_result.get('comparison_result', {})
            
            my_price = my_price_data.get('current', 0)
            competitor_price = competitor_price_data.get('current', 0)
            difference = result.get('difference', 0)
            percentage = result.get('percentage', 0)
            status = result.get('status', 'unknown')
            
            # 确定邮件主题和状态文本
            if status == 'competitor_higher':
                status_text = '竞争对手价格更高'
                status_color = '#28a745'  # 绿色，对我们有利
                advantage_text = '您的价格更有竞争力！'
            elif status == 'competitor_lower':
                status_text = '竞争对手价格更低'
                status_color = '#dc3545'  # 红色，对我们不利
                advantage_text = '竞争对手价格更低，考虑调整定价策略'
            else:
                status_text = '价格相近'
                status_color = '#6c757d'  # 灰色
                advantage_text = '价格相近，保持关注'
            
            subject = f"【价格对比提醒】{comparison_name} - {status_text}"
            
            # 构建HTML邮件内容
            html = f"""
            <html>
            <head>
                <style>
                    body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 0; padding: 0; background-color: #f8f9fa; }}
                    .container {{ max-width: 800px; margin: 0 auto; background-color: white; }}
                    .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px 20px; text-align: center; }}
                    .header h1 {{ margin: 0; font-size: 24px; }}
                    .content {{ padding: 30px 20px; }}
                    .comparison-card {{ border: 1px solid #e0e0e0; border-radius: 8px; margin: 20px 0; overflow: hidden; }}
                    .card-header {{ background-color: #f8f9fa; padding: 15px 20px; border-bottom: 1px solid #e0e0e0; }}
                    .card-body {{ padding: 20px; }}
                    .price-section {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }}
                    .price-item {{ text-align: center; flex: 1; }}
                    .price-label {{ font-size: 14px; color: #6c757d; margin-bottom: 5px; }}
                    .price-value {{ font-size: 24px; font-weight: bold; color: #2c3e50; }}
                    .vs-divider {{ font-size: 18px; color: #adb5bd; margin: 0 20px; }}
                    .result-section {{ background-color: {status_color}; color: white; padding: 20px; text-align: center; border-radius: 8px; margin: 20px 0; }}
                    .result-title {{ font-size: 18px; font-weight: bold; margin-bottom: 10px; }}
                    .result-details {{ font-size: 16px; }}
                    .product-info {{ background-color: #f8f9fa; padding: 15px; border-radius: 8px; margin: 15px 0; }}
                    .product-title {{ font-weight: bold; color: #2c3e50; margin-bottom: 8px; }}
                    .product-link {{ color: #007bff; text-decoration: none; }}
                    .footer {{ background-color: #f8f9fa; padding: 20px; text-align: center; color: #6c757d; font-size: 12px; }}
                    .badge {{ display: inline-block; padding: 6px 12px; border-radius: 20px; font-size: 12px; font-weight: bold; }}
                    .badge-success {{ background-color: #28a745; color: white; }}
                    .badge-danger {{ background-color: #dc3545; color: white; }}
                    .badge-secondary {{ background-color: #6c757d; color: white; }}
                    @media (max-width: 600px) {{
                        .price-section {{ flex-direction: column; }}
                        .vs-divider {{ margin: 10px 0; }}
                    }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>🔔 价格对比提醒</h1>
                        <p>{comparison_name}</p>
                    </div>
                    
                    <div class="content">
                        <div class="result-section">
                            <div class="result-title">{advantage_text}</div>
                            <div class="result-details">
                                价格差异: <strong>${abs(difference):.2f}</strong> ({abs(percentage):.1f}%)
                            </div>
                        </div>
                        
                        <div class="comparison-card">
                            <div class="card-header">
                                <h3 style="margin: 0;">💰 价格对比详情</h3>
                            </div>
                            <div class="card-body">
                                <div class="price-section">
                                    <div class="price-item">
                                        <div class="price-label">我的商品价格</div>
                                        <div class="price-value">${my_price:.2f}</div>
                                        <div class="badge badge-success">我的价格</div>
                                    </div>
                                    <div class="vs-divider">VS</div>
                                    <div class="price-item">
                                        <div class="price-label">竞争对手价格</div>
                                        <div class="price-value">${competitor_price:.2f}</div>
                                        <div class="badge badge-danger">竞争对手</div>
                                    </div>
                                </div>
                            </div>
                        </div>
                        
                        <div class="comparison-card">
                            <div class="card-header">
                                <h3 style="margin: 0;">📋 商品信息</h3>
                            </div>
                            <div class="card-body">
                                <div class="product-info">
                                    <div class="product-title">我的商品</div>
                                    <div>{my_listing.get('title', '商品标题')}</div>
                                    <div><a href="{my_listing.get('url', '#')}" class="product-link" target="_blank">查看商品详情 →</a></div>
                                </div>
                                
                                <div class="product-info">
                                    <div class="product-title">竞争对手商品</div>
                                    <div>{competitor_listing.get('title', '商品标题')}</div>
                                    <div><a href="{competitor_listing.get('url', '#')}" class="product-link" target="_blank">查看商品详情 →</a></div>
                                </div>
                            </div>
                        </div>
                        
                        <div style="margin-top: 30px; padding: 20px; background-color: #e3f2fd; border-radius: 8px;">
                            <h4 style="margin-top: 0; color: #1976d2;">💡 建议操作</h4>
                            <ul style="margin-bottom: 0;">
            """
            
            # 根据对比结果添加建议
            if status == 'competitor_higher':
                html += """
                                <li>您的价格更有优势，可以考虑保持当前定价</li>
                                <li>如果销量不错，可以考虑适当提价</li>
                                <li>继续监控竞争对手是否调价</li>
                """
            elif status == 'competitor_lower':
                html += """
                                <li>竞争对手价格更低，建议评估是否需要调价</li>
                                <li>分析竞争对手商品的质量和服务差异</li>
                                <li>考虑通过其他方式提升竞争力（如免邮、快速发货等）</li>
                """
            else:
                html += """
                                <li>价格相近，关注其他竞争因素</li>
                                <li>继续监控价格变化趋势</li>
                                <li>考虑通过服务差异化获得竞争优势</li>
                """
            
            html += f"""
                            </ul>
                        </div>
                    </div>
                    
                    <div class="footer">
                        <p>此邮件由eBay价格监控系统自动发送</p>
                        <p>检查时间: {time.strftime('%Y-%m-%d %H:%M:%S')}</p>
                        <p>配置ID: {comparison_config.get('id', 'N/A')}</p>
                    </div>
                </div>
            </body>
            </html>
            """
            
            # 发送邮件
            success = self.send_email(recipient, subject, html, is_html=True)
            if success:
                self.logger.info(f"成功发送价格对比通知邮件到 {recipient} (对比: {comparison_name})")
            else:
                self.logger.error(f"发送价格对比通知邮件失败到 {recipient} (对比: {comparison_name})")
            
            return success
            
        except Exception as e:
            self.logger.error(f"构建价格对比通知邮件时发生错误 (收件人: {recipient}): {str(e)}", exc_info=True)
            return False

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