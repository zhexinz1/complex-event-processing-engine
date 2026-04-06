"""
test_level2_display.py — 测试五档行情显示逻辑

使用 MockMarketGateway 模拟中金所五档行情，验证：
1. TickEvent 是否正确存储五档数据
2. 显示逻辑是否正确输出五档买卖盘
"""

import logging
from cep.core.event_bus import EventBus
from cep.core.events import TickEvent
from adapters.market_gateway import MockMarketGateway

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("test_level2")


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


def main():
    # 1. 创建事件总线
    bus = EventBus()

    # 2. 订阅 Tick 事件
    bus.subscribe(TickEvent, on_tick)

    # 3. 创建模拟网关
    gateway = MockMarketGateway(event_bus=bus)
    gateway.connect()
    gateway.subscribe(["IC2606"])

    # 4. 模拟推送中金所五档行情数据
    logger.info("=" * 80)
    logger.info("测试场景 1: 完整五档行情（模拟中金所 IC2606）")
    logger.info("=" * 80)

    gateway.push_tick(
        symbol="IC2606",
        last_price=6850.0,
        bid_prices=(6849.8, 6849.6, 6849.4, 6849.2, 6849.0),  # 买1~买5
        bid_volumes=(10, 8, 15, 12, 20),
        ask_prices=(6850.2, 6850.4, 6850.6, 6850.8, 6851.0),  # 卖1~卖5
        ask_volumes=(12, 9, 18, 11, 22),
        volume=100,
        turnover=685000.0
    )

    logger.info("\n" + "=" * 80)
    logger.info("测试场景 2: 只有一档行情（模拟商品期货）")
    logger.info("=" * 80)

    gateway.push_tick(
        symbol="IC2606",
        last_price=6850.0,
        bid_prices=(6849.8, 0.0, 0.0, 0.0, 0.0),  # 只有买1
        bid_volumes=(10, 0, 0, 0, 0),
        ask_prices=(6850.2, 0.0, 0.0, 0.0, 0.0),  # 只有卖1
        ask_volumes=(12, 0, 0, 0, 0),
        volume=50,
        turnover=342500.0
    )

    gateway.disconnect()
    logger.info("\n测试完成！")


if __name__ == "__main__":
    main()
