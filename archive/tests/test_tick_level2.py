#!/usr/bin/env python3
"""
测试 TickEvent 五档行情功能
"""

import sys
sys.path.insert(0, '/home/ubuntu/CEP')

from cep.core import TickEvent


def test_tick_level2():
    """测试五档行情数据结构"""
    print("测试 TickEvent 五档行情...")

    # 创建一个包含五档数据的 Tick
    tick = TickEvent(
        symbol="600519.SH",
        last_price=1850.0,
        bid_prices=(1849.5, 1849.0, 1848.5, 1848.0, 1847.5),
        bid_volumes=(100, 200, 150, 300, 250),
        ask_prices=(1850.5, 1851.0, 1851.5, 1852.0, 1852.5),
        ask_volumes=(120, 180, 160, 220, 190),
        volume=500,
        turnover=925000.0
    )

    # 验证五档数据
    assert tick.bid_prices[0] == 1849.5, "买一价错误"
    assert tick.ask_prices[0] == 1850.5, "卖一价错误"
    assert tick.bid_volumes[0] == 100, "买一量错误"
    assert tick.ask_volumes[0] == 120, "卖一量错误"

    # 验证向后兼容的属性
    assert tick.bid == 1849.5, "bid 属性应该返回买一价"
    assert tick.ask == 1850.5, "ask 属性应该返回卖一价"

    print(f"  ✓ 标的: {tick.symbol}")
    print(f"  ✓ 最新价: {tick.last_price}")
    print(f"  ✓ 买一价: {tick.bid} (兼容属性)")
    print(f"  ✓ 卖一价: {tick.ask} (兼容属性)")
    print(f"  ✓ 五档买价: {tick.bid_prices}")
    print(f"  ✓ 五档买量: {tick.bid_volumes}")
    print(f"  ✓ 五档卖价: {tick.ask_prices}")
    print(f"  ✓ 五档卖量: {tick.ask_volumes}")

    # 测试默认值（空 Tick）
    empty_tick = TickEvent(symbol="000001.SZ")
    assert empty_tick.bid == 0.0, "空 Tick 的 bid 应该为 0"
    assert empty_tick.ask == 0.0, "空 Tick 的 ask 应该为 0"
    assert len(empty_tick.bid_prices) == 5, "应该有 5 档买价"
    assert len(empty_tick.ask_prices) == 5, "应该有 5 档卖价"

    print("  ✓ 默认值测试通过")
    print("\n✅ TickEvent 五档行情测试通过！")


if __name__ == "__main__":
    test_tick_level2()
