"""
position_source_example.py — 持仓数据源使用示例

演示如何从迅投 GT API 或其他外部系统同步持仓信息，
并基于实时持仓进行偏离度监控和再平衡。

核心流程：
  1. 创建持仓数据源（迅投 GT / CTP / Mock）
  2. 定期从数据源同步持仓到 PortfolioContext
  3. CTP 行情推送 → 更新价格 → 检查偏离度
  4. 触发再平衡 → 生成订单

运行：
  cd /home/ubuntu/CEP
  python -m examples.position_source_example
"""

import logging
import time
from datetime import date, datetime

from cep.core.event_bus import EventBus
from cep.core.events import TickEvent, TimerEvent
from rebalance import (
    PortfolioContext,
    ContractInfo,
    Position,
    RebalanceHandler,
    PortfolioDeviationTrigger,
    MonthlyRebalanceTrigger,
    MockPositionSource,
    InMemoryConfigLoader,
    ProductConfig,
    TargetWeightConfig,
)

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("position_source_example")


def main():
    logger.info("=" * 80)
    logger.info("持仓数据源使用示例")
    logger.info("=" * 80)

    # -----------------------------------------------------------------------
    # 1. 创建持仓数据源
    # -----------------------------------------------------------------------

    # 方式 1: 使用模拟数据源（测试用）
    position_source = MockPositionSource()

    # 方式 2: 使用迅投 GT 数据源（生产环境）
    # position_source = XunTouPositionSource(
    #     server_addr="tcp://xxx.xxx.xxx.xxx:xxxx",
    #     account_id="your_account_id",
    #     password="your_password",
    #     app_id="your_app_id"
    # )
    # position_source.connect()

    # 设置模拟持仓（仅用于测试）
    position_source.set_position(Position(
        symbol="AU2606.SHF",
        quantity=50,
        avg_price=580.0,
        market_value=50 * 580.0 * 1000  # 50手 * 580元 * 1000乘数
    ))
    position_source.set_position(Position(
        symbol="IC2606.CFE",
        quantity=10,
        avg_price=6500.0,
        market_value=10 * 6500.0 * 200  # 10手 * 6500点 * 200乘数
    ))
    position_source.set_account_info(
        total_nav=10_000_000.0,
        available_cash=5_000_000.0,
        margin_used=2_000_000.0
    )

    logger.info("持仓数据源已创建（模拟）")

    # -----------------------------------------------------------------------
    # 2. 创建组合上下文并设置数据源
    # -----------------------------------------------------------------------
    bus = EventBus()
    portfolio_ctx = PortfolioContext(position_source=position_source)

    # 加载目标权重配置
    config_loader = InMemoryConfigLoader()
    config = ProductConfig(
        product_name="明钺全天候1号",
        date=date(2026, 3, 30),
        assets=[
            TargetWeightConfig(
                date=date(2026, 3, 30),
                product_name="明钺全天候1号",
                symbol="AU2606.SHF",
                target_weight=0.30,
                deviation_threshold=0.03,
                algorithm="TWAP"
            ),
            TargetWeightConfig(
                date=date(2026, 3, 30),
                product_name="明钺全天候1号",
                symbol="IC2606.CFE",
                target_weight=0.20,
                deviation_threshold=0.05,
                algorithm="TWAP"
            ),
        ],
        global_threshold=0.05
    )
    config_loader.save_product_config(config)

    portfolio_ctx.set_target_weights(config.get_target_weights())

    # 注册合约信息
    contracts = {
        "AU2606.SHF": ContractInfo("AU2606.SHF", multiplier=1000, margin_rate=0.08),
        "IC2606.CFE": ContractInfo("IC2606.CFE", multiplier=200, margin_rate=0.12),
    }
    for contract in contracts.values():
        portfolio_ctx.register_contract(contract)

    # -----------------------------------------------------------------------
    # 3. 从数据源同步持仓（模拟从迅投 GT API 拉取）
    # -----------------------------------------------------------------------
    logger.info("\n" + "=" * 80)
    logger.info("场景 1: 从迅投 GT API 同步持仓")
    logger.info("=" * 80)

    success = portfolio_ctx.sync_positions_from_source()
    if success:
        logger.info("✅ 持仓同步成功")
        positions = portfolio_ctx.get_all_positions()
        for symbol, pos in positions.items():
            logger.info(
                f"  {symbol:15s} 数量={pos.quantity:>6.0f}  "
                f"均价={pos.avg_price:>8.2f}  市值={pos.market_value:>12,.0f}"
            )
    else:
        logger.error("❌ 持仓同步失败")

    # -----------------------------------------------------------------------
    # 4. 创建再平衡处理器
    # -----------------------------------------------------------------------
    rebalance_handler = RebalanceHandler(bus, portfolio_ctx)
    rebalance_handler.register()

    # -----------------------------------------------------------------------
    # 5. 创建偏离触发器（基于实时持仓）
    # -----------------------------------------------------------------------
    deviation_trigger = PortfolioDeviationTrigger(
        event_bus=bus,
        trigger_id="portfolio_deviation",
        portfolio_ctx=portfolio_ctx,
        threshold=config.global_threshold,
        symbol_thresholds=config.get_deviation_thresholds(),
        cooldown=5.0,  # 5秒冷却（测试用）
    )
    deviation_trigger.register()

    # -----------------------------------------------------------------------
    # 6. 创建月初定时触发器（不管偏离度，强制再平衡）
    # -----------------------------------------------------------------------
    monthly_trigger = MonthlyRebalanceTrigger(
        event_bus=bus,
        trigger_id="monthly_rebalance",
        timer_id="MONTHLY_REBALANCE_0930"
    )
    monthly_trigger.register()
    logger.info("月初定时触发器已注册（每月1号9:30触发）")

    # -----------------------------------------------------------------------
    # 7. 模拟场景：定期同步持仓 + 行情推送
    # -----------------------------------------------------------------------
    logger.info("\n" + "=" * 80)
    logger.info("场景 2: 定期同步持仓 + 实时行情监控")
    logger.info("=" * 80)

    # 推送初始行情
    tick1 = TickEvent(
        symbol="AU2606.SHF",
        timestamp=datetime.now(),
        last_price=580.0,
        volume=1000,
        bid_prices=tuple([579.0] * 5),
        bid_volumes=tuple([100] * 5),
        ask_prices=tuple([581.0] * 5),
        ask_volumes=tuple([100] * 5),
    )
    bus.publish(tick1)

    tick2 = TickEvent(
        symbol="IC2606.CFE",
        timestamp=datetime.now(),
        last_price=6500.0,
        volume=1000,
        bid_prices=tuple([6499.0] * 5),
        bid_volumes=tuple([100] * 5),
        ask_prices=tuple([6501.0] * 5),
        ask_volumes=tuple([100] * 5),
    )
    bus.publish(tick2)

    logger.info("初始行情已推送")

    # 等待冷却期
    time.sleep(6)

    # 模拟持仓变化（迅投 GT API 返回新持仓）
    logger.info("\n持仓发生变化（模拟迅投 GT API 返回）...")
    position_source.set_position(Position(
        symbol="AU2606.SHF",
        quantity=60,  # 增加了 10 手
        avg_price=585.0,
        market_value=60 * 585.0 * 1000
    ))

    # 重新同步持仓
    portfolio_ctx.sync_positions_from_source()

    # 推送新行情（价格上涨）
    logger.info("黄金价格上涨 5% ...")
    tick3 = TickEvent(
        symbol="AU2606.SHF",
        timestamp=datetime.now(),
        last_price=609.0,  # 上涨 5%
        volume=1000,
        bid_prices=tuple([608.0] * 5),
        bid_volumes=tuple([100] * 5),
        ask_prices=tuple([610.0] * 5),
        ask_volumes=tuple([100] * 5),
    )
    bus.publish(tick3)

    # -----------------------------------------------------------------------
    # 8. 模拟月初定时触发
    # -----------------------------------------------------------------------
    logger.info("\n" + "=" * 80)
    logger.info("场景 3: 月初定时触发（强制再平衡）")
    logger.info("=" * 80)

    # 发送月初定时事件
    timer_event = TimerEvent(
        timer_id="MONTHLY_REBALANCE_0930",
        fired_at=datetime.now()
    )
    bus.publish(timer_event)

    logger.info("\n" + "=" * 80)
    logger.info("示例完成")
    logger.info("=" * 80)

    # -----------------------------------------------------------------------
    # 9. 总结：生产环境使用方式
    # -----------------------------------------------------------------------
    logger.info("\n生产环境使用方式：")
    logger.info("1. 创建迅投 GT 持仓数据源")
    logger.info("   position_source = XunTouPositionSource(...)")
    logger.info("   position_source.connect()")
    logger.info("")
    logger.info("2. 定期同步持仓（如每 5 秒）")
    logger.info("   portfolio_ctx.sync_positions_from_source()")
    logger.info("")
    logger.info("3. CTP 行情自动触发偏离检查")
    logger.info("   无需手动操作，Tick 事件会自动触发")
    logger.info("")
    logger.info("4. 月初定时触发（需要定时器模块）")
    logger.info("   每月 1 号 9:30 发送 TimerEvent")


if __name__ == "__main__":
    main()
