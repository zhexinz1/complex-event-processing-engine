#!/usr/bin/env python3
"""
测试 MockMarketGateway 五档行情推送
"""

import sys
sys.path.insert(0, '/home/ubuntu/CEP')

import logging
from cep.core.event_bus import EventBus
from cep.core.events import TickEvent
from adapters.market_gateway import MockMarketGateway

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("test_mock_level2")


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

    # 验证向后兼容性
    assert event.bid == event.bid_prices[0], "bid 属性应该等于 bid_prices[0]"
    assert event.ask == event.ask_prices[0], "ask 属性应该等于 ask_prices[0]"
    logger.info(f"✓ 向后兼容性验证通过: bid={event.bid}, ask={event.ask}")


def main():
    # 1. 创建事件总线
    bus = EventBus()

    # 2. 订阅 Tick 事件
    bus.subscribe(TickEvent, on_tick)

    # 3. 创建模拟行情网关
    gateway = MockMarketGateway(event_bus=bus)
    gateway.connect()
    gateway.subscribe(["600519.SH"])

    # 4. 推送一个包含五档数据的 Tick
    logger.info("推送五档行情数据...")
    gateway.push_tick(
        symbol="600519.SH",
        last_price=1850.0,
        bid_prices=(1849.5, 1849.0, 1848.5, 1848.0, 1847.5),
        bid_volumes=(100, 200, 150, 300, 250),
        ask_prices=(1850.5, 1851.0, 1851.5, 1852.0, 1852.5),
        ask_volumes=(120, 180, 160, 220, 190),
        volume=500,
        turnover=925000.0
    )

    logger.info("\n✅ 五档行情测试完成！")


if __name__ == "__main__":
    main()
