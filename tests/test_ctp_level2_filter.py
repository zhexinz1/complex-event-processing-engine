#!/usr/bin/env python3
"""
测试 CTP 五档行情字段过滤逻辑。

场景：CTP 仅推送一档行情时，BidPrice2-BidPrice5 字段会填充极大值
（1.7976931348623157e+308），此时对应的量字段需要配套归零，
否则会出现"价格=0 但量≠0"的数据矛盾。
"""

import sys
sys.path.insert(0, '/home/ubuntu/CEP')

from adapters.market_gateway import CTPMarketGateway
from cep.core.event_bus import EventBus
from cep.core.events import TickEvent

# CTP 用此值表示无效价格
_CTP_INVALID_PRICE = 1.7976931348623157e+308


class _FakeCTPData:
    """模拟 CTP OnRtnDepthMarketData 的原始数据包。"""
    InstrumentID    = "au2606"
    LastPrice       = 700.50
    TradingDay      = "20260403"
    UpdateTime      = "09:31:00"
    UpdateMillisec  = 0
    Volume          = 100        # 累计成交量
    Turnover        = 70050.0    # 累计成交额

    # 买一档：正常数据
    BidPrice1 = 700.40
    BidVolume1 = 50

    # 买二至买五：CTP 仅推一档时，价格为极大值，量非零（历史遗留脏数据）
    BidPrice2 = _CTP_INVALID_PRICE
    BidVolume2 = 999   # 脏数据，修复前会被原样带入
    BidPrice3 = _CTP_INVALID_PRICE
    BidVolume3 = 888
    BidPrice4 = _CTP_INVALID_PRICE
    BidVolume4 = 777
    BidPrice5 = _CTP_INVALID_PRICE
    BidVolume5 = 666

    # 卖一档：正常数据
    AskPrice1 = 700.60
    AskVolume1 = 60

    # 卖二至卖五：同上
    AskPrice2 = _CTP_INVALID_PRICE
    AskVolume2 = 555
    AskPrice3 = _CTP_INVALID_PRICE
    AskVolume3 = 444
    AskPrice4 = _CTP_INVALID_PRICE
    AskVolume4 = 333
    AskPrice5 = _CTP_INVALID_PRICE
    AskVolume5 = 222


def test_ctp_invalid_price_filter():
    """验证：价格无效时，对应档位的价格和数量都应被归零。"""
    print("测试：CTP 无效价格字段过滤逻辑...")

    class Collector:
        def __init__(self):
            self.received: list[TickEvent] = []

        def on_tick(self, event: TickEvent):
            self.received.append(event)

    collector = Collector()
    bus = EventBus()
    bus.subscribe(TickEvent, collector.on_tick)

    gateway = CTPMarketGateway(
        event_bus=bus,
        front_addr="tcp://fake:9999",
        broker_id="9999",
        user_id="test",
        password="test",
    )
    # 手动初始化累加器（跳过实际连接）
    from adapters.market_gateway import _BarAccumulator
    gateway._bar_accumulators["au2606"] = _BarAccumulator(symbol="au2606")

    # 注入模拟数据
    gateway._on_depth_market_data(_FakeCTPData())

    assert len(collector.received) == 1, "应收到一个 TickEvent"
    tick = collector.received[0]

    print(f"  标的: {tick.symbol}")
    print(f"  最新价: {tick.last_price}")
    print()
    print("  买盘:")
    for i in range(5):
        print(f"    买{i+1}  价格={tick.bid_prices[i]:.2f}  量={tick.bid_volumes[i]}")
    print()
    print("  卖盘:")
    for i in range(5):
        print(f"    卖{i+1}  价格={tick.ask_prices[i]:.2f}  量={tick.ask_volumes[i]}")

    # --- 买一档：应有正确数据 ---
    assert tick.bid_prices[0] == 700.40, f"买一价错误: {tick.bid_prices[0]}"
    assert tick.bid_volumes[0] == 50,    f"买一量错误: {tick.bid_volumes[0]}"

    # --- 买二至买五：价格和量都应为 0，不能带入脏数据 ---
    for i in range(1, 5):
        assert tick.bid_prices[i] == 0.0, \
            f"买{i+1}价格应为 0，实际={tick.bid_prices[i]}"
        assert tick.bid_volumes[i] == 0, \
            f"买{i+1}量应为 0（价格无效时不能有量），实际={tick.bid_volumes[i]}"

    # --- 卖一档：应有正确数据 ---
    assert tick.ask_prices[0] == 700.60, f"卖一价错误: {tick.ask_prices[0]}"
    assert tick.ask_volumes[0] == 60,    f"卖一量错误: {tick.ask_volumes[0]}"

    # --- 卖二至卖五：同上 ---
    for i in range(1, 5):
        assert tick.ask_prices[i] == 0.0, \
            f"卖{i+1}价格应为 0，实际={tick.ask_prices[i]}"
        assert tick.ask_volumes[i] == 0, \
            f"卖{i+1}量应为 0（价格无效时不能有量），实际={tick.ask_volumes[i]}"

    print()
    print("✅ CTP 无效价格过滤测试通过！")
    print("   价格无效时对应档位的量已正确归零，不再出现脏数据。")


if __name__ == "__main__":
    test_ctp_invalid_price_filter()
