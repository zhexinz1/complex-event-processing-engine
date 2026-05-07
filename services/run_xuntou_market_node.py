"""
run_xuntou_market_node.py - 微服务化：独立股票行情接入节点

此进程只负责连接迅投行情，监听股票 Tick 数据，并将其转发至 Redis。
该进程独立于 CTP 行情进程，避免 C++ 库冲突。

用法：
  uv run -m services.run_xuntou_market_node
  uv run -m services.run_xuntou_market_node --server 175.25.41.106:65300 --user api3 --password @a1234567
"""

import sys
import os

# --- 强制环境变量注入跳板 (XunTou C++ 防爆盾) ---
_ld_lib_path = os.environ.get("LD_LIBRARY_PATH", "")
if "/home/ubuntu/xt_sdk" not in _ld_lib_path:
    print("⚠️ [Xt Market Node] 探测到纯净环境，正在为您打入迅投依赖药剂兵无缝重启...")
    os.environ["LD_LIBRARY_PATH"] = "/home/ubuntu/xt_sdk:" + _ld_lib_path
    # 保留用户传入的全部命令行参数
    os.execlp(sys.executable, sys.executable, "-m", "services.run_xuntou_market_node", *sys.argv[1:])

import argparse
import time
from pathlib import Path
import logging

# 加载 .env 环境变量（在读取任何配置之前）
_env_file = Path(__file__).resolve().parent.parent / ".env"
if _env_file.exists():
    for line in _env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip())

from cep.core.event_bus import EventBus
from cep.core.events import TickEvent
from cep.core.remote_bus import RedisEventBridge
from adapters.xuntou import XtMarketService
from database.dao import DatabaseDAO

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def parse_args():
    parser = argparse.ArgumentParser(description="迅投股票行情微服务节点")
    parser.add_argument(
        "--server",
        default=None,
        help="迅投服务器地址 (如 175.25.41.106:65300)，默认使用 base_service 中的配置",
    )
    parser.add_argument(
        "--user",
        default=None,
        help="迅投登录用户名",
    )
    parser.add_argument(
        "--password",
        default=None,
        help="迅投登录密码",
    )
    return parser.parse_args()


def sync_symbols(dao: DatabaseDAO, gateway: XtMarketService, subscribed: set) -> None:
    """定时从 DB 同步并订阅需要的新股票合约"""
    try:
        # 从 target_assets 表读取所有的合约
        all_targets = dao.get_all_target_assets()
        
        # 仅过滤出股票合约 (带有 .SH 或 .SZ)
        stock_targets = [
            t for t in all_targets 
            if t.endswith(".SH") or t.endswith(".SZ")
        ]

        if not stock_targets:
            logger.info("[Xt Market Node] 数据库中没有需要订阅的股票合约")
            return

        new_symbols = set(stock_targets) - subscribed
        if new_symbols:
            logger.info("[Xt Market Node] 发现并订阅新股票合约: %s", list(new_symbols))
            gateway.subscribe(list(new_symbols))
            subscribed.update(new_symbols)
        else:
            logger.info("[Xt Market Node] sync_symbols: DB返回 %d 个股票合约, 已订阅 %d 个, 无新增", len(stock_targets), len(subscribed))
    except Exception as e:
        logger.error("[Xt Market Node] 同步目标合约异常: %s", e)


def main():
    args = parse_args()

    logger.info("=" * 60)
    logger.info("[Xt Market Node] 正在启动独立迅投股票行情微服务...")
    logger.info("=" * 60)

    # 1. 初始化纯内存的 EventBus
    local_bus = EventBus()

    # 2. 初始化 Redis 流水线桥接器 (扮演发布者)
    redis_bridge = RedisEventBridge(local_bus)
    # 将本地的所有 Tick 事件全部推送到 Redis 的 cep_events 频道
    redis_bridge.start_publishing([TickEvent])

    # 建立正式的 MySQL 数据库层 (DAO) 连接
    db_dao = DatabaseDAO()

    # 3. 初始化并连接 XunTou 行情网关
    gateway = XtMarketService(
        username=args.user,
        password=args.password,
        event_bus=local_bus,
    )
    # 如果指定了服务器地址则覆盖默认值
    if args.server:
        gateway.server_addr = args.server

    logger.info("[Xt Market Node] 连接目标: server=%s, user=%s", gateway.server_addr, gateway.username)

    if not gateway.connect():
        logger.error("[Xt Market Node] 无法连接迅投服务器，进程退出。")
        sys.exit(1)
        
    logger.info("[Xt Market Node] 迅投服务器连接并登录成功。")

    subscribed: set[str] = set()
    sync_symbols(db_dao, gateway, subscribed)

    # 4. 进入定时同步的防阻塞轮询循环
    try:
        while True:
            time.sleep(30)
            sync_symbols(db_dao, gateway, subscribed)
    except KeyboardInterrupt:
        logger.info("收到中止信号，正在关闭股票行情服务...")
    finally:
        gateway.disconnect()
        logger.info("退出完成。")


if __name__ == "__main__":
    main()
