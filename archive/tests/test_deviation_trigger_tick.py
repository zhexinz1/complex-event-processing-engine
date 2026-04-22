"""
测试 PortfolioDeviationTrigger 基于 TickEvent 的实现
"""

import time
from datetime import datetime

from cep.core.event_bus import EventBus
from cep.core.events import TickEvent, SignalEvent, SignalType
from rebalance.portfolio_context import PortfolioContext, ContractInfo, Position
from rebalance.rebalance_triggers import PortfolioDeviationTrigger


def test_deviation_trigger_with_tick():
    """测试偏离触发器能否正确处理 TickEvent"""

    # 创建事件总线
    bus = EventBus()

    # 创建组合上下文
    ctx = PortfolioContext()

    # 配置目标权重
    ctx.set_target_weights({
        'SYMBOL_A': 0.50,  # 50%
        'SYMBOL_B': 0.50,  # 50%
    })

    # 注册合约信息
    ctx.register_contract(ContractInfo('SYMBOL_A', multiplier=1.0))
    ctx.register_contract(ContractInfo('SYMBOL_B', multiplier=1.0))

    # 初始化账户（100万）
    ctx.update_account(total_nav=1_000_000.0, available_cash=1_000_000.0, margin_used=0.0)

    # 初始化持仓（各 50 万）
    ctx.update_position(Position('SYMBOL_A', quantity=5000, avg_price=100.0, market_value=500_000.0))
    ctx.update_position(Position('SYMBOL_B', quantity=5000, avg_price=100.0, market_value=500_000.0))

    # 记录触发的信号
    signals = []

    def on_signal(event: SignalEvent):
        if event.signal_type == SignalType.REBALANCE_REQUEST:
            signals.append(event)
            print(f"✅ 收到再平衡信号: {event.payload}")

    bus.subscribe(SignalEvent, on_signal)

    # 创建偏离触发器（5% 阈值，1 秒冷却）
    trigger = PortfolioDeviationTrigger(
        event_bus=bus,
        trigger_id='test_trigger',
        portfolio_ctx=ctx,
        threshold=0.05,  # 5%
        cooldown=1.0,    # 1 秒冷却
    )
    trigger.register()

    print("=" * 60)
    print("测试 1: 发送 TickEvent，价格未偏离")
    print("=" * 60)

    # 发送 Tick（价格不变，不应触发）
    tick1 = TickEvent(
        symbol='SYMBOL_A',
        timestamp=datetime.now(),
        last_price=100.0,
        volume=1000,
        bid_prices=[99.0] * 5,
        bid_volumes=[100] * 5,
        ask_prices=[101.0] * 5,
        ask_volumes=[100] * 5
    )
    bus.publish(tick1)

    assert len(signals) == 0, "价格未偏离，不应触发信号"
    print("✅ 测试通过：价格未偏离，未触发信号")

    print("\n" + "=" * 60)
    print("测试 2: 发送 TickEvent，价格大幅上涨（超过 5% 阈值）")
    print("=" * 60)

    # 等待冷却期结束
    time.sleep(1.1)

    # 发送 Tick（SYMBOL_A 价格涨到 120，市值变为 60 万，权重变为 60%，偏离 10%）
    tick2 = TickEvent(
        symbol='SYMBOL_A',
        timestamp=datetime.now(),
        last_price=120.0,
        volume=1000,
        bid_prices=[119.0] * 5,
        bid_volumes=[100] * 5,
        ask_prices=[121.0] * 5,
        ask_volumes=[100] * 5
    )
    bus.publish(tick2)

    assert len(signals) == 1, "价格偏离超过 5%，应触发信号"
    assert signals[0].payload['trigger_type'] == 'deviation'
    assert signals[0].payload['max_deviation_symbol'] == 'SYMBOL_A'
    print(f"✅ 测试通过：触发再平衡信号，偏离品种 = {signals[0].payload['max_deviation_symbol']}")

    print("\n" + "=" * 60)
    print("测试 3: 冷却期内发送 TickEvent，不应触发")
    print("=" * 60)

    # 立即发送另一个 Tick（冷却期内，不应触发）
    tick3 = TickEvent(
        symbol='SYMBOL_A',
        timestamp=datetime.now(),
        last_price=130.0,
        volume=1000,
        bid_prices=[129.0] * 5,
        bid_volumes=[100] * 5,
        ask_prices=[131.0] * 5,
        ask_volumes=[100] * 5
    )
    bus.publish(tick3)

    assert len(signals) == 1, "冷却期内，不应触发新信号"
    print("✅ 测试通过：冷却期内未触发新信号")

    print("\n" + "=" * 60)
    print("所有测试通过！")
    print("=" * 60)


if __name__ == '__main__':
    test_deviation_trigger_with_tick()
