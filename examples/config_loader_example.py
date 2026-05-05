"""
config_loader_example.py — 配置加载器使用示例

演示如何使用配置加载器从数据库或配置文件加载目标权重配置，
并为每个资产设置独立的偏离阈值。

运行：
  cd /home/ubuntu/CEP
  python -m examples.config_loader_example
"""

import logging
from datetime import date, datetime

from cep.core.event_bus import EventBus
from cep.core.events import TickEvent
from rebalance import (
    PortfolioContext,
    ContractInfo,
    Position,
    RebalanceHandler,
    PortfolioDeviationTrigger,
    InMemoryConfigLoader,
    ProductConfig,
    TargetWeightConfig,
)

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("config_loader_example")


def main():
    logger.info("=" * 80)
    logger.info("配置加载器使用示例")
    logger.info("=" * 80)

    # -----------------------------------------------------------------------
    # 1. 创建配置加载器（模拟从数据库加载）
    # -----------------------------------------------------------------------
    config_loader = InMemoryConfigLoader()

    # 创建产品配置（模拟数据库中的配置表）
    # 日期        产品名称           资产            比例      偏离阈值    算法
    # 2026/3/30  明钺全天候1号    AU2606.SHF    25.61%    3%        TWAP
    # 2026/3/30  明钺全天候1号    IC2606.CFE    20.48%    5%        TWAP
    # 2026/3/30  明钺全天候1号    T2605.CFE     124.76%   2%        TWAP
    # 2026/3/30  明钺全天候1号    M2609.DCE     7.81%     4%        TWAP

    product_config = ProductConfig(
        product_name="明钺全天候1号",
        date=date(2026, 3, 30),
        assets=[
            TargetWeightConfig(
                date=date(2026, 3, 30),
                product_name="明钺全天候1号",
                symbol="AU2606.SHF",
                target_weight=0.2561,
                deviation_threshold=0.03,  # 黄金 3% 阈值
                algorithm="TWAP"
            ),
            TargetWeightConfig(
                date=date(2026, 3, 30),
                product_name="明钺全天候1号",
                symbol="IC2606.CFE",
                target_weight=0.2048,
                deviation_threshold=0.05,  # 股指 5% 阈值
                algorithm="TWAP"
            ),
            TargetWeightConfig(
                date=date(2026, 3, 30),
                product_name="明钺全天候1号",
                symbol="T2605.CFE",
                target_weight=1.2476,  # 国债期货可以超过 100%（杠杆）
                deviation_threshold=0.02,  # 国债 2% 阈值（更严格）
                algorithm="TWAP"
            ),
            TargetWeightConfig(
                date=date(2026, 3, 30),
                product_name="明钺全天候1号",
                symbol="M2609.DCE",
                target_weight=0.0781,
                deviation_threshold=0.04,  # 豆粕 4% 阈值
                algorithm="TWAP"
            ),
        ],
        global_threshold=0.05  # 全局默认 5%
    )

    # 保存配置到加载器
    config_loader.save_product_config(product_config)
    logger.info(f"已保存产品配置: {product_config.product_name}")

    # -----------------------------------------------------------------------
    # 2. 从配置加载器读取配置
    # -----------------------------------------------------------------------
    loaded_config = config_loader.load_product_config("明钺全天候1号")
    if not loaded_config:
        logger.error("配置加载失败")
        return

    logger.info("\n加载的配置:")
    logger.info(f"  产品名称: {loaded_config.product_name}")
    logger.info(f"  配置日期: {loaded_config.date}")
    logger.info(f"  资产数量: {len(loaded_config.assets)}")
    logger.info("\n资产明细:")
    for asset in loaded_config.assets:
        logger.info(
            f"    {asset.symbol:15s} 目标权重={asset.target_weight:7.2%}  "
            f"偏离阈值={asset.deviation_threshold:5.2%}  算法={asset.algorithm}"
        )

    # -----------------------------------------------------------------------
    # 3. 创建事件总线和组合上下文
    # -----------------------------------------------------------------------
    bus = EventBus()
    portfolio_ctx = PortfolioContext()

    # 设置目标权重
    target_weights = loaded_config.get_target_weights()
    portfolio_ctx.set_target_weights(target_weights)

    # 注册合约信息
    contracts = {
        "AU2606.SHF": ContractInfo("AU2606.SHF", multiplier=1000, margin_rate=0.08),
        "IC2606.CFE": ContractInfo("IC2606.CFE", multiplier=200, margin_rate=0.12),
        "T2605.CFE": ContractInfo("T2605.CFE", multiplier=10000, margin_rate=0.015),
        "M2609.DCE": ContractInfo("M2609.DCE", multiplier=10, margin_rate=0.08),
    }
    for contract in contracts.values():
        portfolio_ctx.register_contract(contract)

    # 初始化账户（1000万）
    portfolio_ctx.update_account(
        total_nav=10_000_000.0,
        available_cash=10_000_000.0,
        margin_used=0.0
    )

    # 初始化持仓（空仓）
    for symbol in target_weights.keys():
        portfolio_ctx.update_position(Position(
            symbol=symbol,
            quantity=0.0,
            avg_price=0.0,
            market_value=0.0
        ))

    # -----------------------------------------------------------------------
    # 4. 创建再平衡处理器
    # -----------------------------------------------------------------------
    rebalance_handler = RebalanceHandler(bus, portfolio_ctx)
    rebalance_handler.register()

    # -----------------------------------------------------------------------
    # 5. 创建偏离触发器（使用配置中的独立阈值）
    # -----------------------------------------------------------------------
    symbol_thresholds = loaded_config.get_deviation_thresholds()

    deviation_trigger = PortfolioDeviationTrigger(
        event_bus=bus,
        trigger_id="portfolio_deviation",
        portfolio_ctx=portfolio_ctx,
        threshold=loaded_config.global_threshold,  # 全局默认阈值
        symbol_thresholds=symbol_thresholds,       # 每个资产的独立阈值
        cooldown=5.0,  # 5 秒冷却（测试用）
    )
    deviation_trigger.register()

    logger.info("\n偏离触发器配置:")
    logger.info(f"  全局阈值: {loaded_config.global_threshold:.2%}")
    logger.info("  独立阈值:")
    for symbol, threshold in symbol_thresholds.items():
        logger.info(f"    {symbol:15s} {threshold:.2%}")

    # -----------------------------------------------------------------------
    # 6. 模拟行情推送和偏离检测
    # -----------------------------------------------------------------------
    logger.info("\n" + "=" * 80)
    logger.info("模拟场景：黄金价格上涨，触发 3% 阈值")
    logger.info("=" * 80)

    # 初始价格
    initial_prices = {
        "AU2606.SHF": 580.0,
        "IC2606.CFE": 6500.0,
        "T2605.CFE": 102.5,
        "M2609.DCE": 3800.0,
    }

    # 推送初始价格
    for symbol, price in initial_prices.items():
        tick = TickEvent(
            symbol=symbol,
            timestamp=datetime.now(),
            last_price=price,
            volume=1000,
            bid_prices=tuple([price - 1] * 5),
            bid_volumes=tuple([100] * 5),
            ask_prices=tuple([price + 1] * 5),
            ask_volumes=tuple([100] * 5),
        )
        bus.publish(tick)

    logger.info("初始价格已推送")

    # 等待冷却期
    import time
    time.sleep(6)

    # 黄金价格上涨 4%（超过 3% 阈值）
    logger.info("\n黄金价格上涨 4% ...")
    tick = TickEvent(
        symbol="AU2606.SHF",
        timestamp=datetime.now(),
        last_price=580.0 * 1.04,  # 上涨 4%
        volume=1000,
        bid_prices=tuple([602.0] * 5),
        bid_volumes=tuple([100] * 5),
        ask_prices=tuple([604.0] * 5),
        ask_volumes=tuple([100] * 5),
    )
    bus.publish(tick)

    logger.info("\n" + "=" * 80)
    logger.info("示例完成")
    logger.info("=" * 80)


if __name__ == "__main__":
    main()
