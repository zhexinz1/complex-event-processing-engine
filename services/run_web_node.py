"""
启动 Flask Web 微服务 (独立 Web 控制台)
"""

import logging
from pathlib import Path

# 加载 .env 环境变量（在读取任何配置之前）
_env_file = Path(__file__).resolve().parent.parent / ".env"
if _env_file.exists():
    import os

    for line in _env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip())

from adapters.flask_app import create_app, init_db
from adapters.price_service import init_redis_market_subscriber

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def main():
    logger.info("=" * 60)
    logger.info("[Web Node] 正在启动前端测控微服务...")
    logger.info("=" * 60)

    # 初始化数据库
    init_db()

    # 启动 Redis 行情订阅线程（复用 Market Node 的 cep_events 频道）
    init_redis_market_subscriber()

    # 创建 Flask Web 实例
    app = create_app()

    print("\n📍 欢迎访问 CEP 网页控制台:")
    print("  - 目标资产配置: http://<你的服务器 IP>:5000/")
    print("  - 净入金流程:   http://<你的服务器 IP>:5000/fund-inflow.html")
    print("  - 行情通道: Redis Pub/Sub (已接入 Market Node 实时行情)\n")

    # 绑定 0.0.0.0 以便外网或物理机能够访问，5000 端口
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)

if __name__ == "__main__":
    main()
