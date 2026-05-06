"""
ctp_deviation_trigger_example.py — CTP 行情 + 组合偏离触发器集成示例

演示如何使用 CTP 实时行情驱动 PortfolioDeviationTrigger，实现盘中动态再平衡。

核心流程：
  CTP 实时行情 → TickEvent → PortfolioDeviationTrigger
                                    ↓
                            更新价格 + 检查偏离（60秒冷却）
                                    ↓
                            发射 REBALANCE_REQUEST
                                    ↓
                            RebalanceHandler → 生成订单

前置条件：
  1. 安装依赖：pip install openctp-ctp
  2. 在 SimNow 官网注册账号：http://www.simnow.com.cn
  3. 交易时段运行

运行：
  cd /home/ubuntu/CEP
  python -m examples.ctp_deviation_trigger_example
"""

import logging
import signal
import sys
import time

from cep.core.event_bus import EventBus
from adapters.market_gateway import CTPMarketGateway
from rebalance.portfolio_context import PortfolioContext, ContractInfo, Position
from rebalance.rebalance_handler import RebalanceHandler
from rebalance.rebalance_triggers import PortfolioDeviationTrigger

# ---------------------------------------------------------------------------
# 日志配置
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("ctp_deviation_example")

# ---------------------------------------------------------------------------
# SimNow 仿真账户配置
# ---------------------------------------------------------------------------
FRONT_ADDR = "tcp://182.254.243.31:30011"
BROKER_ID = "9999"
USER_ID = "259563"
PASSWORD = "ZZXgoUSA@2018"

# 订阅的主力合约
SYMBOLS = ["au2604", "rb2605", "hc2605", "IC2606"]

# ---------------------------------------------------------------------------
# 主程序
# ---------------------------------------------------------------------------


def main() -> None:
    logger.info("=" * 80)
    logger.info("CTP 行情 + 组合偏离触发器集成示例")
    logger.info("=" * 80)

    # -----------------------------------------------------------------------
    # 1. 创建事件总线
    # -----------------------------------------------------------------------
    bus = EventBus()

    # -----------------------------------------------------------------------
    # 2. 创建组合上下文
    # -----------------------------------------------------------------------
    portfolio_ctx = PortfolioContext()

    # 配置目标权重
    target_weights = {
        "au2604": 0.30,  # 黄金 30%
        "rb2605": 0.25,  # 螺纹钢 25%
        "hc2605": 0.20,  # 热卷 20%
        "IC2606": 0.25,  # 中证 500 25%
    }
    portfolio_ctx.set_target_weights(target_weights)
    logger.info(f"目标权重配置: {target_weights}")

    # 注册合约信息
    contracts = {
        "au2604": ContractInfo("au2604", multiplier=1000, margin_rate=0.08),
        "rb2605": ContractInfo("rb2605", multiplier=10, margin_rate=0.09),
        "hc2605": ContractInfo("hc2605", multiplier=10, margin_rate=0.09),
        "IC2606": ContractInfo("IC2606", multiplier=200, margin_rate=0.12),
    }
    for contract in contracts.values():
        portfolio_ctx.register_contract(contract)

    # 初始化账户（1000万）
    initial_nav = 10_000_000.0
    portfolio_ctx.update_account(
        total_nav=initial_nav, available_cash=initial_nav, margin_used=0.0
    )
    logger.info(f"初始资金: {initial_nav:,.0f} 元")

    # 初始化持仓（空仓）
    for symbol in SYMBOLS:
        portfolio_ctx.update_position(
            Position(symbol=symbol, quantity=0.0, avg_price=0.0, market_value=0.0)
        )

    # -----------------------------------------------------------------------
    # 3. 创建再平衡处理器
    # -----------------------------------------------------------------------
    rebalance_handler = RebalanceHandler(bus, portfolio_ctx)
    rebalance_handler.register()
    logger.info("再平衡处理器已注册")

    # -----------------------------------------------------------------------
    # 4. 创建偏离触发器（方案一：基于 TickEvent）
    # -----------------------------------------------------------------------
    deviation_trigger = PortfolioDeviationTrigger(
        event_bus=bus,
        trigger_id="portfolio_deviation",
        portfolio_ctx=portfolio_ctx,
        threshold=0.05,  # 5% 偏离阈值
        cooldown=60.0,  # 60 秒冷却期
    )
    deviation_trigger.register()

    # -----------------------------------------------------------------------
    # 5. 连接 CTP 行情网关
    # -----------------------------------------------------------------------
    gateway = CTPMarketGateway(
        event_bus=bus,
        front_addr=FRONT_ADDR,
        broker_id=BROKER_ID,
        user_id=USER_ID,
        password=PASSWORD,
        flow_path="./ctp_flow/",
    )

    # 优雅退出处理
    def shutdown(signum, frame) -> None:
        logger.info("收到退出信号，正在断开连接...")
        gateway.unsubscribe(SYMBOLS)
        gateway.disconnect()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # 连接到 SimNow
    logger.info(f"正在连接到 {FRONT_ADDR} ...")
    if not gateway.connect():
        logger.error("连接失败，请检查账号配置和网络")
        sys.exit(1)

    # 订阅行情
    gateway.subscribe(SYMBOLS)
    logger.info(f"已订阅行情: {SYMBOLS}")

    # -----------------------------------------------------------------------
    # 6. 主循环
    # -----------------------------------------------------------------------
    logger.info("\n" + "=" * 80)
    logger.info("系统运行中，实时监控组合偏离度")
    logger.info(f"偏离阈值: {deviation_trigger.threshold:.2%}")
    logger.info(f"检查冷却期: {deviation_trigger.cooldown} 秒")
    logger.info("按 Ctrl+C 退出...")
    logger.info("=" * 80 + "\n")

    while True:
        time.sleep(1)


if __name__ == "__main__":
    main()
