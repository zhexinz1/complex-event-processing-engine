import sys
import os

# ---- 强制环境变量隔离跳板 ----
# 为了彻底阻断带有 `LD_LIBRARY_PATH=/home/ubuntu/xt_sdk` 环境的所谓“新开终端”在启动 Python 进程底层链接时
# 就强行加载那些与 CTP (openctp_ctp) 产生 C++ ABI 冲突的老旧 Boost/glibc 库（这会导致 139 崩溃闪退甚至死循环）。
# 我们在这里使用操作系统 `exec` 级别的逃生舱（Trampoline），将宿醉环境掐灭并干净地重启当前 Python 进程本身。
_inherited_ld = os.environ.get("LD_LIBRARY_PATH", "")
if "xt_sdk" in _inherited_ld:
    print(f"⚠️ 探测到终端全局守护进程存在迅投 C++ 环境污染 ({_inherited_ld})\n⚠️ 正通过操作系统级 exec 无缝重生纯净 Python 进程...")
    _clean_paths = [p for p in _inherited_ld.split(":") if "xt_sdk" not in p]
    os.environ["LD_LIBRARY_PATH"] = ":".join(_clean_paths)
    os.execlp(sys.executable, sys.executable, "-m", "archive.tests.query_market")

"""
临时脚本：连接招商期货仿真 CTP 行情，验证能否收到 Tick 推送。
"""

import logging
import time

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

from cep.core.event_bus import EventBus
from cep.core.events import TickEvent, BarEvent
from adapters.market_gateway import CTPMarketGateway

# 招商期货仿真账号配置
FRONT_ADDR = "tcp://218.17.194.115:41413"
BROKER_ID  = "8060"   # 招商期货 BrokerID
USER_ID    = "99683265"
PASSWORD   = "456123"

# 订阅几个主力合约测试
SYMBOLS = ["au2606", "rb2610"]

def on_tick(event: TickEvent) -> None:
    bids = "  ".join(f"b{i+1}={event.bid_prices[i]:.2f}/{event.bid_volumes[i]}" for i in range(5))
    asks = "  ".join(f"a{i+1}={event.ask_prices[i]:.2f}/{event.ask_volumes[i]}" for i in range(5))
    logger.info("TICK  %s  last=%.2f  vol=%d\n  BID: %s\n  ASK: %s",
                event.symbol, event.last_price, event.volume, bids, asks)

def on_bar(event: BarEvent) -> None:
    logger.info("BAR   %s  %s  O=%.2f H=%.2f L=%.2f C=%.2f  vol=%d",
                event.symbol, event.freq,
                event.open, event.high, event.low, event.close, event.volume)

def main():
    bus = EventBus()
    bus.subscribe(TickEvent, on_tick, symbol="")
    bus.subscribe(BarEvent, on_bar, symbol="")

    gw = CTPMarketGateway(
        event_bus=bus,
        front_addr=FRONT_ADDR,
        broker_id=BROKER_ID,
        user_id=USER_ID,
        password=PASSWORD,
        flow_path="./ctp_flow/",
    )

    logger.info("正在连接 %s ...", FRONT_ADDR)
    if not gw.connect():
        logger.error("连接失败，退出")
        return

    logger.info("连接成功，订阅合约: %s", SYMBOLS)
    gw.subscribe(SYMBOLS)

    logger.info("等待行情推送（30 秒）...")
    time.sleep(30)

    gw.disconnect()

if __name__ == "__main__":
    main()
