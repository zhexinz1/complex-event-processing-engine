"""
ctp_market_gateway_example.py — CTP 实时行情接入示例

演示如何使用 CTPMarketGateway 接入 SimNow 仿真环境，接收期货实时行情。

前置条件：
  1. 安装依赖：pip install openctp-ctp
  2. 在 SimNow 官网注册账号：http://www.simnow.com.cn
  3. 交易时段（09:00–15:00 或夜盘）运行，非交易时段前置可能无法连接

SimNow 前置地址（任选其一）：
  - tcp://180.168.146.187:10131  （第一套）
  - tcp://180.168.146.187:10132  （第一套备用）
  - tcp://218.202.237.33:10112   （第二套）

运行：
  cd /home/ubuntu/CEP
  python -m examples.ctp_market_gateway_example
"""

import logging
import signal
import sys
import time

from cep.core.event_bus import EventBus
from cep.core.events import TickEvent, BarEvent
from adapters.market_gateway import CTPMarketGateway

# ---------------------------------------------------------------------------
# 日志配置
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.DEBUG,  # 改为 DEBUG 可看到五档原始数据验证日志
    format="[%(asctime)s] [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("ctp_example")

# ---------------------------------------------------------------------------
# SimNow 仿真账户配置（替换为你自己的账号）
# ---------------------------------------------------------------------------
FRONT_ADDR = "tcp://182.254.243.31:30011"  # 你原来用的地址
BROKER_ID  = "9999"          # SimNow 固定经纪商代码
USER_ID    = "259563"  # 替换为你的 SimNow 账号
PASSWORD   = "ZZXgoUSA@2018" # 替换为你的 SimNow 密码

# 订阅的主力合约（按当期主力合约调整）
# 尝试订阅 2026年4月的近月合约
SYMBOLS = ["au2604", "rb2605", "hc2605"]

# ---------------------------------------------------------------------------
# 事件处理器
# ---------------------------------------------------------------------------

def on_tick(event: TickEvent) -> None:
    """处理 Tick 事件，显示五档行情"""
    logger.info(f"\n{'='*80}")
    logger.info(f"[TICK] {event.symbol:12s} 最新价={event.last_price:>10.2f}  成交量={event.volume}")
    logger.info(f"{'='*80}")

    # 显示五档卖盘（从卖五到卖一，价格从高到低）
    logger.info("  卖盘 (Ask):")
    for i in range(4, -1, -1):  # 从卖五到卖一
        price = event.ask_prices[i]
        volume = event.ask_volumes[i]
        level = f"卖{i+1}"
        logger.info(f"    {level}  价格: {price:>10.2f}  量: {volume:>8d}")

    logger.info(f"  {'-'*60}")
    logger.info(f"  最新价: {event.last_price:>10.2f}")
    logger.info(f"  {'-'*60}")

    # 显示五档买盘（从买一到买五，价格从高到低）
    logger.info("  买盘 (Bid):")
    for i in range(5):  # 从买一到买五
        price = event.bid_prices[i]
        volume = event.bid_volumes[i]
        level = f"买{i+1}"
        logger.info(f"    {level}  价格: {price:>10.2f}  量: {volume:>8d}")

    logger.info(f"{'='*80}\n")


def on_bar(event: BarEvent) -> None:
    logger.info(
        f"[BAR]  {event.symbol:12s} {event.bar_time.strftime('%H:%M')}  "
        f"O={event.open:.2f}  H={event.high:.2f}  L={event.low:.2f}  "
        f"C={event.close:.2f}  V={event.volume}"
    )


# ---------------------------------------------------------------------------
# 主程序
# ---------------------------------------------------------------------------

def main() -> None:
    # 1. 创建事件总线
    bus = EventBus()

    # 2. 订阅 Tick 和 Bar 事件
    bus.subscribe(TickEvent, on_tick)
    bus.subscribe(BarEvent, on_bar)

    # 3. 初始化 CTP 行情网关
    gateway = CTPMarketGateway(
        event_bus=bus,
        front_addr=FRONT_ADDR,
        broker_id=BROKER_ID,
        user_id=USER_ID,
        password=PASSWORD,
        flow_path="./ctp_flow/",
    )

    # 4. 优雅退出处理
    def shutdown(signum, frame) -> None:
        logger.info("收到退出信号，正在断开连接...")
        gateway.unsubscribe(SYMBOLS)
        gateway.disconnect()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # 5. 连接到 SimNow
    logger.info(f"正在连接到 {FRONT_ADDR} ...")
    if not gateway.connect():
        logger.error("连接失败，请检查账号配置和网络")
        sys.exit(1)

    # 6. 订阅行情
    gateway.subscribe(SYMBOLS)

    # 7. 主线程阻塞，等待行情推送
    logger.info("开始接收行情，按 Ctrl+C 退出...")
    while True:
        time.sleep(1)


if __name__ == "__main__":
    main()
