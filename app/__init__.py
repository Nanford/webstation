# Flask应用初始化

from flask import Flask
import redis
from app.config import Config

def create_app(test_config=None):
    app = Flask(__name__, 
                template_folder='../templates', 
                static_folder='../static')
    app.config.from_object(Config)
    
    # 连接Redis
    try:
        redis_client = redis.Redis(
            host=Config.REDIS_HOST,
            port=Config.REDIS_PORT,
            db=Config.REDIS_DB,
            password=Config.REDIS_PASSWORD,
            socket_timeout=5,
            decode_responses=True  # 自动解码为Python字符串
        )
        # 测试连接
        redis_client.ping()
        app.logger.info("Redis连接成功")
    except Exception as e:
        app.logger.error(f"Redis连接失败: {e}")
        # 使用无密码连接作为备选
        try:
            redis_client = redis.Redis(
                host=Config.REDIS_HOST,
                port=Config.REDIS_PORT,
                db=Config.REDIS_DB,
                socket_timeout=5,
                decode_responses=True
            )
            app.logger.info("Redis无密码连接成功")
        except Exception as e:
            app.logger.error(f"Redis备选连接也失败: {e}")
            redis_client = None

    # 注册蓝图
    from app.views import main
    app.register_blueprint(main)
    
    # 将Redis客户端添加到应用
    app.redis_client = redis_client
    
    # 初始化定时任务调度器
    from app.scheduler import init_scheduler
    init_scheduler(app)
    
    # 添加自定义过滤器
    @app.template_filter('timestamp_to_date')
    def timestamp_to_date_filter(timestamp):
        if not timestamp:
            return "未知"
        from datetime import datetime
        return datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
    
    return app 