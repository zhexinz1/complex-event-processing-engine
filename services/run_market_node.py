"""
run_market_node.py - 微服务化：独立行情接入节点

此进程只负责连接 CTP (或其它行情源)，监听 Tick 数据，并将其转发至 Redis。
在这个进程中绝不能导入任何迅投或者有毒的 SDK 环境。
"""

import sys
import os

# ---- 强制环境变量隔离跳板 ----
# 为了彻底阻断带有 `LD_LIBRARY_PATH=/home/ubuntu/xt_sdk` 环境继承导致的 139 段错误
# 这里务必使用 exec 级别的逃生舱，干净重启 Python 进程底层链接。
_inherited_ld = os.environ.get("LD_LIBRARY_PATH", "")
if "xt_sdk" in _inherited_ld:
    print(f"⚠️ 探测到终端环境变量继承污染 ({_inherited_ld})\n⚠️ 正通过操作系统级 exec 重生纯净 Python 进程...")
    _clean_paths = [p for p in _inherited_ld.split(":") if "xt_sdk" not in p]
    os.environ["LD_LIBRARY_PATH"] = ":".join(_clean_paths)
    os.execlp(sys.executable, sys.executable, "-m", "services.run_market_node")

import time
from datetime import datetime
import logging

from cep.core.event_bus import EventBus
from cep.core.events import TickEvent, BarEvent
from cep.core.remote_bus import RedisEventBridge
from adapters.market_gateway import CTPMarketGateway
from database.dao import DatabaseDAO

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

def main():

    logger.info("=" * 60)
    logger.info("[Market Node] 正在启动独立行情微服务...")
    logger.info("=" * 60)

    # 1. 初始化纯内存的 EventBus
    local_bus = EventBus()

    # 2. 初始化 Redis 流水线桥接器 (扮演发布者)
    redis_bridge = RedisEventBridge(local_bus)
    # 将本地的所有 Tick 和 Bar 事件全部无脑推送上云
    redis_bridge.start_publishing([TickEvent, BarEvent])

    # 建立正式的 MySQL 数据库层 (DAO) 连接
    from adapters.config_source import MySQLConfigSource
    db_dao = DatabaseDAO(
        host=MySQLConfigSource.DB_HOST,
        port=MySQLConfigSource.DB_PORT,
        user=MySQLConfigSource.DB_USER,
        password=MySQLConfigSource.DB_PASS,
        database=MySQLConfigSource.DB_NAME
    )

    # 3. 初始化并连接 CTP 行情网关
    gateway = CTPMarketGateway(
        event_bus=local_bus,
        front_addr="tcp://218.17.194.115:41413",
        broker_id="8060",
        user_id="99683265",
        password="456123",
        flow_path="./ctp_flow/"
    )
    
    if gateway.connect():
        # 记录我已经订阅过的合约，防止重复调用 CTP C++ 层
        subscribed_symbols = set()

        def sync_symbols():
            """通过真正的 DAO 数据库层拉取最新的目标合约，并增量订阅"""
            target_pool = db_dao.get_all_target_assets()
            new_symbols = [s for s in target_pool if s not in subscribed_symbols]
            
            if new_symbols:
                logger.info(f"[Market Node] 通过 DAO 发现并订阅新目标合约: {new_symbols}")
                gateway.subscribe(new_symbols)
                subscribed_symbols.update(new_symbols)

        # 启动时先强制同步一次数据库，保证默认/数据库挂载池加载
        sync_symbols()
        
        logger.info("[Market Node] 系统现已就绪。所有行情将通过 Redis 实时向全网分发。按 Ctrl+C 退出。")
        try:
            # 7x24 全天候心跳监听，每10秒从数据库重载一次全网标的
            while True:
                time.sleep(30)
                sync_symbols()
        except KeyboardInterrupt:
            logger.info("收到中止信号，正在关闭服务...")
        finally:
            redis_bridge.stop()
    else:
        logger.error("[Market Node] 无法连接到行情前置网络，服务即将终止。")

if __name__ == "__main__":
    main()
