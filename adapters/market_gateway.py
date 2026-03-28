"""
market_gateway.py — 行情网关适配器

提供统一的行情接入接口，支持多种行情源：
- CTP（期货）
- XTP（股票）
- 模拟行情（用于测试）

设计原则：
  1. 抽象接口：定义统一的行情订阅和推送接口
  2. 依赖注入：通过 EventBus 发布 TickEvent/BarEvent
  3. 可插拔：支持运行时切换不同的行情源
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Callable, Optional

from cep.core.event_bus import EventBus
from cep.core.events import TickEvent, BarEvent

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 抽象基类
# ---------------------------------------------------------------------------

class MarketGateway(ABC):
    """
    行情网关抽象基类。

    所有行情源适配器必须实现此接口。
    """

    def __init__(self, event_bus: EventBus):
        """
        初始化行情网关。

        Args:
            event_bus: 全局事件总线，用于发布行情事件
        """
        self.event_bus = event_bus
        self._subscribed_symbols: set[str] = set()

    @abstractmethod
    def connect(self) -> bool:
        """
        连接到行情服务器。

        Returns:
            连接是否成功
        """
        pass

    @abstractmethod
    def disconnect(self) -> None:
        """断开行情连接。"""
        pass

    @abstractmethod
    def subscribe(self, symbols: list[str]) -> bool:
        """
        订阅行情。

        Args:
            symbols: 合约代码列表，如 ["600519.SH", "AU2606"]

        Returns:
            订阅是否成功
        """
        pass

    @abstractmethod
    def unsubscribe(self, symbols: list[str]) -> bool:
        """
        取消订阅行情。

        Args:
            symbols: 合约代码列表

        Returns:
            取消订阅是否成功
        """
        pass

    def _publish_tick(self, tick: TickEvent) -> None:
        """发布 Tick 事件到事件总线。"""
        self.event_bus.publish(tick)

    def _publish_bar(self, bar: BarEvent) -> None:
        """发布 Bar 事件到事件总线。"""
        self.event_bus.publish(bar)


# ---------------------------------------------------------------------------
# CTP 行情网关（期货）
# ---------------------------------------------------------------------------

class CTPMarketGateway(MarketGateway):
    """
    CTP 行情网关实现。

    对接上期技术 CTP 接口，用于期货行情接入。

    TODO: 实现 CTP API 对接
    - 引入 openctp 或 vnpy 的 CTP 封装
    - 实现 OnRtnDepthMarketData 回调
    - 处理断线重连逻辑
    """

    def __init__(
        self,
        event_bus: EventBus,
        front_addr: str,
        broker_id: str,
        user_id: str,
        password: str
    ):
        """
        初始化 CTP 行情网关。

        Args:
            event_bus:   事件总线
            front_addr:  行情前置地址，如 "tcp://180.168.146.187:10131"
            broker_id:   经纪商代码
            user_id:     用户账号
            password:    密码
        """
        super().__init__(event_bus)
        self.front_addr = front_addr
        self.broker_id = broker_id
        self.user_id = user_id
        self.password = password

        # TODO: 初始化 CTP API
        # self.md_api = MdApi()

        logger.info(f"CTPMarketGateway initialized: {front_addr}")

    def connect(self) -> bool:
        """连接到 CTP 行情服务器。"""
        # TODO: 实现 CTP 连接逻辑
        logger.warning("CTP connection not implemented yet")
        return False

    def disconnect(self) -> None:
        """断开 CTP 连接。"""
        # TODO: 实现断开逻辑
        logger.info("CTP disconnected")

    def subscribe(self, symbols: list[str]) -> bool:
        """订阅 CTP 行情。"""
        # TODO: 调用 CTP API 订阅
        # self.md_api.SubscribeMarketData(symbols)
        self._subscribed_symbols.update(symbols)
        logger.info(f"Subscribed to CTP market data: {symbols}")
        return True

    def unsubscribe(self, symbols: list[str]) -> bool:
        """取消订阅 CTP 行情。"""
        # TODO: 调用 CTP API 取消订阅
        self._subscribed_symbols.difference_update(symbols)
        logger.info(f"Unsubscribed from CTP market data: {symbols}")
        return True

    def _on_tick(self, data: dict) -> None:
        """
        CTP Tick 回调处理。

        Args:
            data: CTP 行情数据字典
        """
        tick = TickEvent(
            symbol=data["InstrumentID"],
            last_price=data["LastPrice"],
            bid=data["BidPrice1"],
            ask=data["AskPrice1"],
            volume=data["Volume"],
            turnover=data["Turnover"],
            timestamp=datetime.now()
        )
        self._publish_tick(tick)


# ---------------------------------------------------------------------------
# 模拟行情网关（用于测试）
# ---------------------------------------------------------------------------

class MockMarketGateway(MarketGateway):
    """
    模拟行情网关，用于测试和回测。

    支持：
    - 手动推送 Tick/Bar 数据
    - 从历史数据文件回放
    """

    def __init__(self, event_bus: EventBus):
        super().__init__(event_bus)
        self._connected = False
        logger.info("MockMarketGateway initialized")

    def connect(self) -> bool:
        """模拟连接成功。"""
        self._connected = True
        logger.info("Mock market gateway connected")
        return True

    def disconnect(self) -> None:
        """模拟断开连接。"""
        self._connected = False
        logger.info("Mock market gateway disconnected")

    def subscribe(self, symbols: list[str]) -> bool:
        """模拟订阅成功。"""
        if not self._connected:
            logger.error("Cannot subscribe: not connected")
            return False

        self._subscribed_symbols.update(symbols)
        logger.info(f"Mock subscribed: {symbols}")
        return True

    def unsubscribe(self, symbols: list[str]) -> bool:
        """模拟取消订阅。"""
        self._subscribed_symbols.difference_update(symbols)
        logger.info(f"Mock unsubscribed: {symbols}")
        return True

    def push_tick(
        self,
        symbol: str,
        last_price: float,
        bid: float = 0.0,
        ask: float = 0.0,
        volume: int = 0,
        turnover: float = 0.0
    ) -> None:
        """
        手动推送 Tick 数据（用于测试）。

        Args:
            symbol:     合约代码
            last_price: 最新价
            bid:        买一价
            ask:        卖一价
            volume:     成交量
            turnover:   成交额
        """
        if symbol not in self._subscribed_symbols:
            logger.warning(f"Symbol {symbol} not subscribed, ignoring tick")
            return

        tick = TickEvent(
            symbol=symbol,
            last_price=last_price,
            bid=bid,
            ask=ask,
            volume=volume,
            turnover=turnover,
            timestamp=datetime.now()
        )
        self._publish_tick(tick)
        logger.debug(f"Mock tick pushed: {symbol} @ {last_price}")

    def push_bar(
        self,
        symbol: str,
        freq: str,
        open: float,
        high: float,
        low: float,
        close: float,
        volume: int = 0,
        turnover: float = 0.0
    ) -> None:
        """
        手动推送 Bar 数据（用于测试）。

        Args:
            symbol:   合约代码
            freq:     K 线周期，如 "1m", "5m", "1d"
            open:     开盘价
            high:     最高价
            low:      最低价
            close:    收盘价
            volume:   成交量
            turnover: 成交额
        """
        if symbol not in self._subscribed_symbols:
            logger.warning(f"Symbol {symbol} not subscribed, ignoring bar")
            return

        bar = BarEvent(
            symbol=symbol,
            freq=freq,
            open=open,
            high=high,
            low=low,
            close=close,
            volume=volume,
            turnover=turnover,
            bar_time=datetime.now(),
            timestamp=datetime.now()
        )
        self._publish_bar(bar)
        logger.debug(f"Mock bar pushed: {symbol} {freq} close={close}")
