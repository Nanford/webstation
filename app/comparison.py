# 价格对比监控模块

import json
import time
import logging
import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from app.improved_scraper import ImprovedEbayStoreScraper
import random

# 配置日志
logger = logging.getLogger(__name__)

class PriceComparison:
    """价格对比监控类"""
    
    def __init__(self, redis_client=None):
        """初始化价格对比监控"""
        self.redis = redis_client
        self.scraper = ImprovedEbayStoreScraper(redis_client=redis_client)
        self.logger = logger
    
    # Redis数据结构设计
    # ==================
    # 对比配置存储：comparison:config:{comparison_id}
    # {
    #     "id": "comp_20241201_001",
    #     "name": "我的商品vs竞争对手",
    #     "my_listing": {
    #         "url": "https://www.ebay.com/itm/123456789",
    #         "title": "我的商品标题",
    #         "item_id": "123456789"
    #     },
    #     "competitor_listing": {
    #         "url": "https://www.ebay.com/itm/987654321", 
    #         "title": "竞争对手商品标题",
    #         "item_id": "987654321"
    #     },
    #     "notify_email": "user@example.com",
    #     "notify_conditions": {
    #         "higher": true,        # 对手价格比我高时通知
    #         "lower": true,         # 对手价格比我低时通知
    #         "threshold": 5.0       # 价格差异阈值（美元）
    #     },
    #     "created_at": 1701234567,
    #     "last_check": 1701234567,
    #     "status": "active"         # active, paused, disabled
    # }
    
    # 对比历史记录：comparison:history:{comparison_id}:{timestamp}
    # {
    #     "timestamp": 1701234567,
    #     "comparison_id": "comp_20241201_001",
    #     "my_price": {
    #         "current": 99.99,
    #         "currency": "USD",
    #         "status": "active",         # active, sold, ended
    #         "title": "我的商品标题"
    #     },
    #     "competitor_price": {
    #         "current": 89.99,
    #         "currency": "USD", 
    #         "status": "active",
    #         "title": "竞争对手商品标题"
    #     },
    #     "comparison_result": {
    #         "difference": -10.00,           # 负数表示对手更便宜
    #         "percentage": -10.01,           # 百分比差异
    #         "status": "competitor_lower",   # competitor_higher, competitor_lower, equal
    #         "threshold_exceeded": true      # 是否超过阈值
    #     },
    #     "notification_sent": true,
    #     "check_status": "success"           # success, failed, partial
    # }
    
    # 对比配置索引：comparison:list
    # ["comp_20241201_001", "comp_20241201_002", ...]
    
    # 对比历史索引：comparison:history_index:{comparison_id}
    # [1701234567, 1701320967, ...] (按时间戳排序)
    
    def generate_comparison_id(self) -> str:
        """生成唯一的对比配置ID"""
        timestamp = int(time.time())
        date_str = datetime.fromtimestamp(timestamp).strftime('%Y%m%d')
        
        # 获取当日已有的对比配置数量
        existing_configs = self.get_all_comparisons()
        today_configs = [c for c in existing_configs if c['id'].startswith(f'comp_{date_str}')]
        next_number = len(today_configs) + 1
        
        return f"comp_{date_str}_{next_number:03d}"
    
    def extract_ebay_item_id(self, url: str) -> Optional[str]:
        """从eBay URL中提取商品ID"""
        patterns = [
            r'/itm/(\d+)',           # 标准格式
            r'/p/(\d+)',             # p格式
            r'item=(\d+)',           # 参数格式
            r'(\d{10,15})'           # 纯数字ID
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        
        return None
    
    def get_all_comparisons(self) -> List[Dict]:
        """获取所有对比配置"""
        list_key = "comparison:list"
        current_list = self.redis.get(list_key)
        
        if not current_list:
            return []
        
        comparison_ids = json.loads(current_list)
        comparisons = []
        
        for comparison_id in comparison_ids:
            config = self.get_comparison_config(comparison_id)
            if config:
                comparisons.append(config)
        
        return comparisons
    
    def get_comparison_config(self, comparison_id: str) -> Optional[Dict]:
        """获取指定的对比配置"""
        config_key = f"comparison:config:{comparison_id}"
        config_data = self.redis.get(config_key)
        
        if config_data:
            return json.loads(config_data)
        return None
    
    def save_comparison_history(self, comparison_id: str, history_data: Dict) -> bool:
        """保存对比历史记录"""
        timestamp = history_data.get('timestamp', int(time.time()))
        
        # 保存历史记录
        history_key = f"comparison:history:{comparison_id}:{timestamp}"
        self.redis.set(history_key, json.dumps(history_data))
        
        # 更新历史索引
        self._add_to_history_index(comparison_id, timestamp)
        
        # 设置过期时间（保留90天的历史记录）
        self.redis.expire(history_key, 90 * 24 * 3600)
        
        self.logger.info(f"保存对比历史记录: {comparison_id} - {timestamp}")
        return True
    
    def _add_to_history_index(self, comparison_id: str, timestamp: int):
        """将时间戳添加到历史索引"""
        index_key = f"comparison:history_index:{comparison_id}"
        current_index = self.redis.get(index_key)
        
        if current_index:
            history_timestamps = json.loads(current_index)
        else:
            history_timestamps = []
        
        if timestamp not in history_timestamps:
            history_timestamps.append(timestamp)
            # 按时间排序，最新的在前面
            history_timestamps.sort(reverse=True)
            
            # 只保留最近100条记录的索引
            if len(history_timestamps) > 100:
                history_timestamps = history_timestamps[:100]
            
            self.redis.set(index_key, json.dumps(history_timestamps))
    
    def get_comparison_history(self, comparison_id: str, limit: int = 10) -> List[Dict]:
        """获取对比历史记录"""
        index_key = f"comparison:history_index:{comparison_id}"
        current_index = self.redis.get(index_key)
        
        if not current_index:
            return []
        
        history_timestamps = json.loads(current_index)
        history_records = []
        
        # 获取最近的记录
        for timestamp in history_timestamps[:limit]:
            history_key = f"comparison:history:{comparison_id}:{timestamp}"
            history_data = self.redis.get(history_key)
            
            if history_data:
                history_records.append(json.loads(history_data))
        
        return history_records
    
    def get_latest_comparison_result(self, comparison_id: str) -> Optional[Dict]:
        """获取最新的对比结果"""
        history_records = self.get_comparison_history(comparison_id, limit=1)
        return history_records[0] if history_records else None
    
    def create_comparison_record(self, comparison_id: str, my_price_data: Dict, 
                               competitor_price_data: Dict, notification_sent: bool = False) -> Dict:
        """创建对比记录数据结构"""
        timestamp = int(time.time())
        
        # 计算价格差异
        my_price = my_price_data.get('current', 0)
        competitor_price = competitor_price_data.get('current', 0)
        
        if my_price > 0 and competitor_price > 0:
            difference = competitor_price - my_price
            percentage = (difference / my_price) * 100
            
            if abs(difference) < 0.01:  # 差异小于1分钱认为相等
                status = "equal"
            elif difference > 0:
                status = "competitor_higher"
            else:
                status = "competitor_lower"
        else:
            difference = 0
            percentage = 0
            status = "unknown"
        
        # 获取配置中的阈值
        config = self.get_comparison_config(comparison_id)
        threshold = config.get('notify_conditions', {}).get('threshold', 5.0) if config else 5.0
        threshold_exceeded = abs(difference) >= threshold
        
        # 构建历史记录
        history_data = {
            "timestamp": timestamp,
            "comparison_id": comparison_id,
            "my_price": my_price_data,
            "competitor_price": competitor_price_data,
            "comparison_result": {
                "difference": round(difference, 2),
                "percentage": round(percentage, 2),
                "status": status,
                "threshold_exceeded": threshold_exceeded
            },
            "notification_sent": notification_sent,
            "check_status": "success"
        }
        
        return history_data
    
    def validate_ebay_url(self, url: str) -> bool:
        """验证eBay URL的有效性"""
        if not url or not url.startswith('http'):
            return False
        
        ebay_domains = ['ebay.com', 'ebay.co.uk', 'ebay.de', 'ebay.fr', 'ebay.com.au', 'ebay.ca']
        if not any(domain in url for domain in ebay_domains):
            return False
        
        # 检查是否包含商品ID
        item_id = self.extract_ebay_item_id(url)
        return item_id is not None
    
    def create_comparison(self, my_listing_url: str, competitor_listing_url: str, 
                         notify_email: str, name: str = None, 
                         notify_conditions: Dict = None) -> Dict:
        """创建新的价格对比配置"""
        
        # 验证URL
        if not self.validate_ebay_url(my_listing_url):
            raise ValueError("我的商品URL格式无效")
        
        if not self.validate_ebay_url(competitor_listing_url):
            raise ValueError("竞争对手商品URL格式无效")
        
        # 生成配置ID
        comparison_id = self.generate_comparison_id()
        
        # 提取商品ID
        my_item_id = self.extract_ebay_item_id(my_listing_url)
        competitor_item_id = self.extract_ebay_item_id(competitor_listing_url)
        
        # 默认通知条件
        if notify_conditions is None:
            notify_conditions = {
                "higher": True,
                "lower": True, 
                "threshold": 5.0
            }
        
        # 尝试获取商品标题
        my_title = "我的商品"
        competitor_title = "竞争对手商品"
        
        try:
            my_info = self.scraper.get_single_listing_info(my_listing_url)
            if my_info:
                my_title = my_info.get('title', my_title)
        except:
            pass
            
        try:
            competitor_info = self.scraper.get_single_listing_info(competitor_listing_url)
            if competitor_info:
                competitor_title = competitor_info.get('title', competitor_title)
        except:
            pass
        
        # 构建配置数据
        config_data = {
            "id": comparison_id,
            "name": name or f"{my_title[:30]} vs {competitor_title[:30]}",
            "my_listing": {
                "url": my_listing_url,
                "title": my_title,
                "item_id": my_item_id
            },
            "competitor_listing": {
                "url": competitor_listing_url,
                "title": competitor_title,
                "item_id": competitor_item_id
            },
            "notify_email": notify_email,
            "notify_conditions": notify_conditions,
            "created_at": int(time.time()),
            "last_check": 0,
            "status": "active"
        }
        
        # 保存配置到Redis
        config_key = f"comparison:config:{comparison_id}"
        self.redis.set(config_key, json.dumps(config_data))
        
        # 添加到配置索引
        self._add_to_comparison_list(comparison_id)
        
        self.logger.info(f"创建价格对比配置成功: {comparison_id}")
        return config_data
    
    def _add_to_comparison_list(self, comparison_id: str):
        """将配置ID添加到索引列表"""
        list_key = "comparison:list"
        current_list = self.redis.get(list_key)
        
        if current_list:
            comparison_list = json.loads(current_list)
        else:
            comparison_list = []
        
        if comparison_id not in comparison_list:
            comparison_list.append(comparison_id)
            self.redis.set(list_key, json.dumps(comparison_list))
    
    def delete_comparison(self, comparison_id: str) -> bool:
        """删除对比配置"""
        # 删除配置数据
        config_key = f"comparison:config:{comparison_id}"
        self.redis.delete(config_key)
        
        # 从索引中移除
        self._remove_from_comparison_list(comparison_id)
        
        # 删除历史记录（可选，也可以保留用于审计）
        history_keys = self.redis.keys(f"comparison:history:{comparison_id}:*")
        if history_keys:
            self.redis.delete(*history_keys)
            
        # 删除历史索引
        index_key = f"comparison:history_index:{comparison_id}"
        self.redis.delete(index_key)
        
        self.logger.info(f"删除价格对比配置: {comparison_id}")
        return True
    
    def _remove_from_comparison_list(self, comparison_id: str):
        """从索引列表中移除配置ID"""
        list_key = "comparison:list"
        current_list = self.redis.get(list_key)
        
        if current_list:
            comparison_list = json.loads(current_list)
            if comparison_id in comparison_list:
                comparison_list.remove(comparison_id)
                self.redis.set(list_key, json.dumps(comparison_list))
    
    def perform_comparison(self, comparison_id: str) -> Optional[Dict]:
        """执行单个对比检查"""
        config = self.get_comparison_config(comparison_id)
        if not config:
            self.logger.error(f"找不到对比配置: {comparison_id}")
            return None
        
        if config.get('status') != 'active':
            self.logger.info(f"对比配置已暂停或禁用: {comparison_id}")
            return None
        
        try:
            # 获取我的商品信息
            my_listing_url = config['my_listing']['url']
            my_info = self.scraper.get_single_listing_info(my_listing_url)
            
            if not my_info:
                self.logger.error(f"无法获取我的商品信息: {my_listing_url}")
                return None
            
            # 获取竞争对手商品信息
            competitor_listing_url = config['competitor_listing']['url']
            competitor_info = self.scraper.get_single_listing_info(competitor_listing_url)
            
            if not competitor_info:
                self.logger.error(f"无法获取竞争对手商品信息: {competitor_listing_url}")
                return None
            
            # 构建价格数据
            my_price_data = {
                "current": my_info.get('current', 0),
                "currency": my_info.get('currency', 'USD'),
                "status": my_info.get('status', 'unknown'),
                "title": my_info.get('title', config['my_listing']['title'])
            }
            
            competitor_price_data = {
                "current": competitor_info.get('current', 0),
                "currency": competitor_info.get('currency', 'USD'),
                "status": competitor_info.get('status', 'unknown'),
                "title": competitor_info.get('title', config['competitor_listing']['title'])
            }
            
            # 创建对比记录
            comparison_record = self.create_comparison_record(
                comparison_id, my_price_data, competitor_price_data
            )
            
            # 检查是否需要发送通知
            should_notify = self._should_send_notification(config, comparison_record)
            comparison_record['notification_sent'] = should_notify
            
            # 保存对比历史
            self.save_comparison_history(comparison_id, comparison_record)
            
            # 更新配置的最后检查时间
            config['last_check'] = int(time.time())
            config_key = f"comparison:config:{comparison_id}"
            self.redis.set(config_key, json.dumps(config))
            
            self.logger.info(f"完成价格对比检查: {comparison_id}")
            return comparison_record
            
        except Exception as e:
            self.logger.error(f"执行价格对比时出错: {comparison_id} - {str(e)}")
            return None
    
    def _should_send_notification(self, config: Dict, comparison_record: Dict) -> bool:
        """判断是否应该发送通知"""
        comparison_result = comparison_record.get('comparison_result', {})
        notify_conditions = config.get('notify_conditions', {})
        
        # 检查是否超过阈值
        if not comparison_result.get('threshold_exceeded', False):
            return False
        
        status = comparison_result.get('status')
        
        # 检查通知条件
        if status == 'competitor_higher' and notify_conditions.get('higher', False):
            return True
        elif status == 'competitor_lower' and notify_conditions.get('lower', False):
            return True
        
        return False
    
    def perform_all_comparisons(self) -> Dict:
        """执行所有活跃的价格对比检查"""
        self.logger.info("开始执行所有价格对比检查")
        
        comparisons = self.get_all_comparisons()
        active_comparisons = [c for c in comparisons if c.get('status') == 'active']
        
        results = {
            'total_comparisons': len(active_comparisons),
            'successful_checks': 0,
            'failed_checks': 0,
            'notifications_needed': [],
            'comparison_results': []
        }
        
        # 导入邮件通知模块
        from app.notification import EmailNotifier
        notifier = EmailNotifier()
        
        for config in active_comparisons:
            comparison_id = config['id']
            self.logger.info(f"检查对比配置: {comparison_id}")
            
            # 添加随机延迟避免频繁请求
            time.sleep(random.uniform(5.0, 10.0))
            
            comparison_result = self.perform_comparison(comparison_id)
            
            if comparison_result:
                results['successful_checks'] += 1
                results['comparison_results'].append(comparison_result)
                
                # 如果需要发送通知，发送邮件
                if comparison_result.get('notification_sent'):
                    notify_email = config.get('notify_email')
                    if notify_email:
                        try:
                            # 发送价格对比通知邮件
                            email_sent = notifier.notify_price_comparison(
                                recipient=notify_email,
                                comparison_config=config,
                                comparison_result=comparison_result
                            )
                            
                            if email_sent:
                                self.logger.info(f"成功发送价格对比通知邮件: {config['name']}")
                                results['notifications_needed'].append({
                                    'comparison_id': comparison_id,
                                    'config': config,
                                    'result': comparison_result,
                                    'email_sent': True
                                })
                            else:
                                self.logger.error(f"发送价格对比通知邮件失败: {config['name']}")
                                results['notifications_needed'].append({
                                    'comparison_id': comparison_id,
                                    'config': config,
                                    'result': comparison_result,
                                    'email_sent': False
                                })
                        except Exception as e:
                            self.logger.error(f"发送价格对比通知邮件时出错: {str(e)}")
                            results['notifications_needed'].append({
                                'comparison_id': comparison_id,
                                'config': config,
                                'result': comparison_result,
                                'email_sent': False,
                                'error': str(e)
                            })
            else:
                results['failed_checks'] += 1
        
        self.logger.info(f"价格对比检查完成 - 成功: {results['successful_checks']}, "
                        f"失败: {results['failed_checks']}, 需要通知: {len(results['notifications_needed'])}")
        
        return results 