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
import os
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass as _dataclass
from datetime import datetime
from typing import Any, Callable, Optional

from cep.core.event_bus import EventBus
from cep.core.events import TickEvent, BarEvent

logger = logging.getLogger(__name__)

# ---- 终极环境保护垫片 ----
# 防御从外部终端或守护进程错误继承了含毒的 LD_LIBRARY_PATH (尤其是 xt_sdk)
_inherited_ld = os.environ.get("LD_LIBRARY_PATH", "")
if "xt_sdk" in _inherited_ld:
    _clean_paths = [p for p in _inherited_ld.split(":") if "xt_sdk" not in p]
    os.environ["LD_LIBRARY_PATH"] = ":".join(_clean_paths)
    logger.info("CTP 网关启动探测到全局 C++ 环境污染，已主动完成局部净化。")

mdapi: Any = None
_CTP_AVAILABLE = False
_CTP_MD_SPI_BASE = object
_CTP_IMPORT_ERROR: Exception | None = None
_CTP_MD_SPI_CLASS: type | None = None


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


@_dataclass
class _BarAccumulator:
    """每个订阅合约维护一个实例，用差分法将 CTP 累计量转换为分钟增量。"""

    symbol: str
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    close: float = 0.0
    volume: int = 0
    turnover: float = 0.0
    bar_minute: Optional[datetime] = None  # 当前 Bar 所属分钟（秒/微秒置 0）
    last_cum_vol: int = 0  # 上一 Tick 的累计成交量
    last_cum_to: float = 0.0  # 上一 Tick 的累计成交额
    initialized: bool = False


def _get_mdapi() -> Any:
    """Lazily import the CTP mdapi module so mock-only runs avoid native imports."""
    global mdapi, _CTP_AVAILABLE, _CTP_MD_SPI_BASE, _CTP_IMPORT_ERROR

    if mdapi is not None:
        return mdapi

    first_error: Exception | None = None
    for attr_name in ("thostmduserapi", "mdapi"):
        try:
            package = __import__("openctp_ctp", fromlist=[attr_name])
            imported = getattr(package, attr_name)
            mdapi = imported
            _CTP_AVAILABLE = True
            _CTP_MD_SPI_BASE = getattr(imported, "CThostFtdcMdSpi", object)
            return mdapi
        except Exception as exc:  # pragma: no cover - depends on local native SDK state
            if first_error is None:
                first_error = exc

    _CTP_AVAILABLE = False
    _CTP_IMPORT_ERROR = first_error
    raise RuntimeError(
        "openctp-ctp is not installed or failed to load"
    ) from first_error


class CTPMdSpi(_CTP_MD_SPI_BASE):
    """
    CTP 行情回调处理器（SPI）。

    职责纯粹：解码 CTP 原始回调，通过注入的回调函数转发给 Gateway。
    不直接操作 EventBus，保持职责分离。
    """

    def __init__(
        self,
        api: Any,
        broker_id: str,
        user_id: str,
        password: str,
        login_event: threading.Event,
        on_tick_callback: Callable,
    ):
        type(self).__mro__[1].__init__(self)
        self._api = api
        self._broker_id = broker_id
        self._user_id = user_id
        self._password = password
        self._login_event = login_event
        self._on_tick_callback = on_tick_callback
        self.login_success: bool = False

    def OnFrontConnected(self) -> None:
        """前置连接成功，立即发起登录。"""
        logger.info("CTP: 前置连接成功，发起登录...")
        ctp_mdapi = _get_mdapi()
        req = ctp_mdapi.CThostFtdcReqUserLoginField()
        req.BrokerID = self._broker_id
        req.UserID = self._user_id
        req.Password = self._password
        self._api.ReqUserLogin(req, 0)

    def OnFrontDisconnected(self, nReason: int) -> None:
        """前置断开（CTP 会自动重连，无需手动处理）。"""
        logger.warning(f"CTP: 前置断开，原因码={nReason}，等待自动重连...")
        self.login_success = False

    def OnRspUserLogin(
        self, pRspUserLogin, pRspInfo, nRequestID: int, bIsLast: bool
    ) -> None:
        """登录响应：设置结果标志并解除 connect() 阻塞。"""
        if pRspInfo is not None and pRspInfo.ErrorID != 0:
            logger.error(
                f"CTP: 登录失败，ErrorID={pRspInfo.ErrorID}，Msg={pRspInfo.ErrorMsg}"
            )
            self.login_success = False
        else:
            logger.info("CTP: 登录成功")
            self.login_success = True
        self._login_event.set()

    def OnRspSubMarketData(
        self, pSpecificInstrument, pRspInfo, nRequestID: int, bIsLast: bool
    ) -> None:
        if pRspInfo is not None and pRspInfo.ErrorID != 0:
            logger.error(
                f"CTP: 订阅失败 {pSpecificInstrument.InstrumentID}，Msg={pRspInfo.ErrorMsg}"
            )
        else:
            logger.info(f"CTP: 订阅成功 {pSpecificInstrument.InstrumentID}")

    def OnRspUnSubMarketData(
        self, pSpecificInstrument, pRspInfo, nRequestID: int, bIsLast: bool
    ) -> None:
        if pRspInfo is not None and pRspInfo.ErrorID != 0:
            logger.error(
                f"CTP: 取消订阅失败 {pSpecificInstrument.InstrumentID}，Msg={pRspInfo.ErrorMsg}"
            )
        else:
            logger.info(f"CTP: 取消订阅成功 {pSpecificInstrument.InstrumentID}")

    def OnRtnDepthMarketData(self, pDepthMarketData) -> None:
        """深度行情回调：直接转发原始数据给 Gateway 处理。"""
        try:
            self._on_tick_callback(pDepthMarketData)
        except Exception:
            logger.exception("CTP: _on_tick_callback 处理异常")


def _get_ctp_md_spi_class() -> type:
    """Build the SPI subclass after the native mdapi module has been loaded."""
    global CTPMdSpi, _CTP_MD_SPI_CLASS

    ctp_mdapi = _get_mdapi()
    spi_base = getattr(ctp_mdapi, "CThostFtdcMdSpi", object)
    if _CTP_MD_SPI_CLASS is not None and issubclass(_CTP_MD_SPI_CLASS, spi_base):
        return _CTP_MD_SPI_CLASS

    attrs = {
        name: value
        for name, value in CTPMdSpi.__dict__.items()
        if name not in {"__dict__", "__weakref__"}
    }
    attrs["__module__"] = __name__

    _CTP_MD_SPI_CLASS = type("CTPMdSpi", (spi_base,), attrs)
    CTPMdSpi = _CTP_MD_SPI_CLASS
    return _CTP_MD_SPI_CLASS


class CTPMarketGateway(MarketGateway):
    """
    CTP 行情网关实现。

    对接上期技术 CTP 接口（通过 openctp-ctp 库），用于期货行情接入。
    支持 Tick 实时推送和自动聚合为 1 分钟 Bar。

    连接流程：
      主线程调用 connect() → 启动子线程运行 api.Init()（阻塞）
      → OnFrontConnected → ReqUserLogin → OnRspUserLogin → login_event.set()
      → connect() 解除阻塞，返回登录结果

    注意：需要先安装 `pip install openctp-ctp`
    """

    def __init__(
        self,
        event_bus: EventBus,
        front_addr: str,
        broker_id: str,
        user_id: str,
        password: str,
        app_id: str = "simnow_client_test",
        auth_code: str = "0000000000000000",
        flow_path: str = "./ctp_flow/",
    ):
        """
        初始化 CTP 行情网关。

        Args:
            event_bus:   事件总线
            front_addr:  行情前置地址，如 "tcp://180.168.146.187:10131"
            broker_id:   经纪商代码
            user_id:     用户账号
            password:    密码
            app_id:      客户端应用 ID（SimNow 用默认值即可）
            auth_code:   客户端认证码（SimNow 用默认值即可）
            flow_path:   CTP 流文件存放目录
        """
        super().__init__(event_bus)
        self.front_addr = front_addr
        self.broker_id = broker_id
        self.user_id = user_id
        self.password = password
        self.app_id = app_id
        self.auth_code = auth_code
        self.flow_path = flow_path

        self._api: Any = None
        self._spi: Any = None
        self._api_thread: Optional[threading.Thread] = None
        self._login_event: threading.Event = threading.Event()
        self._bar_accumulators: dict[str, _BarAccumulator] = {}
        self._bar_lock: threading.Lock = threading.Lock()
        self._connected: bool = False

        logger.info(f"CTPMarketGateway initialized: {front_addr}")

    def connect(self) -> bool:
        """
        连接到 CTP 行情服务器（同步，最多等待 10 秒）。

        Returns:
            True 表示连接并登录成功，False 表示失败或超时。
        """
        try:
            ctp_mdapi = _get_mdapi()
        except RuntimeError as exc:
            logger.error("openctp-ctp 不可用，无法连接: %s", exc)
            return False

        import uuid

        # 使用 unique UUID 作为 flow_path，防止多个进程/实例读写同一个 .con 文件导致底层 C++ Segfault
        unique_id = uuid.uuid4().hex[:8]
        self.flow_path = os.path.join(self.flow_path, f"run_{unique_id}/")
        os.makedirs(self.flow_path, exist_ok=True)
        self._login_event.clear()

        # openctp-ctp 在 Linux 下 CreateFtdcMdApi 必须传入 Python str
        self._api = ctp_mdapi.CThostFtdcMdApi.CreateFtdcMdApi(self.flow_path)

        spi_class = _get_ctp_md_spi_class()
        self._spi = spi_class(
            api=self._api,
            broker_id=self.broker_id,
            user_id=self.user_id,
            password=self.password,
            login_event=self._login_event,
            on_tick_callback=self._on_depth_market_data,
        )

        self._api.RegisterFront(self.front_addr)
        self._api.RegisterSpi(self._spi)

        # api.Init() 是非阻塞的，必须在当前线程调用
        self._api.Init()

        if not self._login_event.wait(timeout=10):
            logger.error("CTP: 登录超时（10 秒），请检查前置地址和网络")
            return False

        self._connected = self._spi.login_success
        return self._connected

    def disconnect(self) -> None:
        """断开 CTP 连接，释放 API 资源。"""
        if self._api is not None:
            try:
                self._api.Release()
            except Exception:
                logger.exception("CTP: Release 异常")
        self._connected = False
        logger.info("CTP: 已断开连接")

    def subscribe(self, symbols: list[str]) -> bool:
        """
        订阅 CTP 行情并初始化 Bar 聚合器。

        Args:
            symbols: 合约代码列表，如 ["AU2506", "RB2510"]

        Returns:
            True 表示请求已发送（实际订阅结果见 OnRspSubMarketData 日志）
        """
        if not self._connected:
            logger.error("CTP: 未连接，无法订阅")
            return False

        # 初始化每个合约的 Bar 聚合器
        with self._bar_lock:
            for sym in symbols:
                if sym not in self._bar_accumulators:
                    self._bar_accumulators[sym] = _BarAccumulator(symbol=sym)

        self._subscribed_symbols.update(symbols)
        sym_bytes = [s.encode("utf-8") for s in symbols]
        self._api.SubscribeMarketData(sym_bytes, len(sym_bytes))
        logger.info(f"CTP: 已发送订阅请求: {symbols}")
        return True

    def unsubscribe(self, symbols: list[str]) -> bool:
        """
        取消订阅 CTP 行情并清理 Bar 聚合器。

        Args:
            symbols: 合约代码列表

        Returns:
            True 表示请求已发送
        """
        if not self._connected:
            logger.error("CTP: 未连接，无法取消订阅")
            return False

        with self._bar_lock:
            for sym in symbols:
                self._bar_accumulators.pop(sym, None)

        self._subscribed_symbols.difference_update(symbols)
        sym_bytes = [s.encode("utf-8") for s in symbols]
        self._api.UnSubscribeMarketData(sym_bytes, len(sym_bytes))
        logger.info(f"CTP: 已发送取消订阅请求: {symbols}")
        return True

    def _on_depth_market_data(self, d) -> None:
        """
        处理 CTP OnRtnDepthMarketData 原始回调。

        步骤一：解析并发布 TickEvent（成交量取差分增量）
        步骤二：将 Tick 聚合为 1 分钟 BarEvent
        """
        symbol: str = d.InstrumentID
        last_price: float = d.LastPrice

        # 过滤无效价格（CTP 用 1.7976931348623157e+308 表示无效值）
        if last_price <= 0 or last_price > 1e15:
            return

        # --- 解析时间 ---
        try:
            # TradingDay: "20240101"，UpdateTime: "09:30:00"，UpdateMillisec: 500
            trading_day: str = d.TradingDay  # "YYYYMMDD"
            update_time: str = d.UpdateTime  # "HH:MM:SS"
            ms: int = d.UpdateMillisec
            tick_time = datetime.strptime(
                f"{trading_day} {update_time}", "%Y%m%d %H:%M:%S"
            ).replace(microsecond=ms * 1000)
        except (ValueError, AttributeError):
            tick_time = datetime.now()

        # --- 步骤一：发布 TickEvent（增量成交量）---
        with self._bar_lock:
            acc = self._bar_accumulators.get(symbol)

        if acc is None:
            return  # 未订阅的品种，忽略

        # 期货夜盘换日时累计量会归零，检测并重置
        cum_vol: int = d.Volume
        if cum_vol < acc.last_cum_vol:
            acc.last_cum_vol = 0
            acc.last_cum_to = 0.0

        delta_vol: int = cum_vol - acc.last_cum_vol
        delta_to: float = d.Turnover - acc.last_cum_to

        # [DEBUG] 打印 CTP 原始五档数据（验证是否为无效值）
        logger.debug(
            f"CTP原始数据 {symbol}: BidPrice2={d.BidPrice2:.2e}, AskPrice2={d.AskPrice2:.2e}, BidVol2={d.BidVolume2}"
        )

        # 解析五档买卖价格和数量（价格和数量配套过滤：价格无效时数量也置0）
        bid_price_1 = d.BidPrice1 if d.BidPrice1 < 1e15 else 0.0
        bid_price_2 = d.BidPrice2 if d.BidPrice2 < 1e15 else 0.0
        bid_price_3 = d.BidPrice3 if d.BidPrice3 < 1e15 else 0.0
        bid_price_4 = d.BidPrice4 if d.BidPrice4 < 1e15 else 0.0
        bid_price_5 = d.BidPrice5 if d.BidPrice5 < 1e15 else 0.0

        bid_prices = (bid_price_1, bid_price_2, bid_price_3, bid_price_4, bid_price_5)
        bid_volumes = (
            d.BidVolume1 if bid_price_1 > 0 else 0,
            d.BidVolume2 if bid_price_2 > 0 else 0,
            d.BidVolume3 if bid_price_3 > 0 else 0,
            d.BidVolume4 if bid_price_4 > 0 else 0,
            d.BidVolume5 if bid_price_5 > 0 else 0,
        )

        ask_price_1 = d.AskPrice1 if d.AskPrice1 < 1e15 else 0.0
        ask_price_2 = d.AskPrice2 if d.AskPrice2 < 1e15 else 0.0
        ask_price_3 = d.AskPrice3 if d.AskPrice3 < 1e15 else 0.0
        ask_price_4 = d.AskPrice4 if d.AskPrice4 < 1e15 else 0.0
        ask_price_5 = d.AskPrice5 if d.AskPrice5 < 1e15 else 0.0

        ask_prices = (ask_price_1, ask_price_2, ask_price_3, ask_price_4, ask_price_5)
        ask_volumes = (
            d.AskVolume1 if ask_price_1 > 0 else 0,
            d.AskVolume2 if ask_price_2 > 0 else 0,
            d.AskVolume3 if ask_price_3 > 0 else 0,
            d.AskVolume4 if ask_price_4 > 0 else 0,
            d.AskVolume5 if ask_price_5 > 0 else 0,
        )

        tick = TickEvent(
            symbol=symbol,
            last_price=last_price,
            bid_prices=bid_prices,
            bid_volumes=bid_volumes,
            ask_prices=ask_prices,
            ask_volumes=ask_volumes,
            volume=cum_vol,
            turnover=d.Turnover,
            timestamp=tick_time,
        )
        self._publish_tick(tick)

        # --- 步骤二：Tick → 1 分钟 Bar 聚合 ---
        current_minute = tick_time.replace(second=0, microsecond=0)

        with self._bar_lock:
            if not acc.initialized:
                # 第一个 Tick：初始化 Bar
                acc.open = acc.high = acc.low = acc.close = last_price
                acc.volume = delta_vol
                acc.turnover = delta_to
                acc.bar_minute = current_minute
                acc.last_cum_vol = cum_vol
                acc.last_cum_to = d.Turnover
                acc.initialized = True

            elif acc.bar_minute is not None and current_minute > acc.bar_minute:
                # 新分钟到来：封闭旧 Bar 并发布
                bar = BarEvent(
                    symbol=symbol,
                    freq="1m",
                    open=acc.open,
                    high=acc.high,
                    low=acc.low,
                    close=acc.close,
                    volume=acc.volume,
                    turnover=acc.turnover,
                    bar_time=acc.bar_minute,
                    timestamp=tick_time,
                )
                self._publish_bar(bar)

                # 重置为新分钟
                acc.open = acc.high = acc.low = acc.close = last_price
                acc.volume = delta_vol
                acc.turnover = delta_to
                acc.bar_minute = current_minute
                acc.last_cum_vol = cum_vol
                acc.last_cum_to = d.Turnover

            else:
                # 同一分钟内更新 Bar
                acc.high = max(acc.high, last_price)
                acc.low = min(acc.low, last_price)
                acc.close = last_price
                acc.volume += delta_vol
                acc.turnover += delta_to
                acc.last_cum_vol = cum_vol
                acc.last_cum_to = d.Turnover


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
        bid_prices: tuple[float, ...] | None = None,
        bid_volumes: tuple[int, ...] | None = None,
        ask_prices: tuple[float, ...] | None = None,
        ask_volumes: tuple[int, ...] | None = None,
        volume: int = 0,
        turnover: float = 0.0,
    ) -> None:
        """
        手动推送 Tick 数据（用于测试）。

        Args:
            symbol:      合约代码
            last_price:  最新价
            bid_prices:  五档买价（可选，默认全 0）
            bid_volumes: 五档买量（可选，默认全 0）
            ask_prices:  五档卖价（可选，默认全 0）
            ask_volumes: 五档卖量（可选，默认全 0）
            volume:      成交量
            turnover:    成交额
        """
        if symbol not in self._subscribed_symbols:
            logger.warning(f"Symbol {symbol} not subscribed, ignoring tick")
            return

        tick = TickEvent(
            symbol=symbol,
            last_price=last_price,
            bid_prices=bid_prices or (0.0,) * 5,
            bid_volumes=bid_volumes or (0,) * 5,
            ask_prices=ask_prices or (0.0,) * 5,
            ask_volumes=ask_volumes or (0,) * 5,
            volume=volume,
            turnover=turnover,
            timestamp=datetime.now(),
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
        turnover: float = 0.0,
        bar_time: datetime | None = None,
        timestamp: datetime | None = None,
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
            volume:    成交量
            turnover:  成交额
            bar_time:  Bar 时间（可选，默认当前时间）
            timestamp: 事件时间（可选，默认当前时间）
        """
        if symbol not in self._subscribed_symbols:
            logger.warning(f"Symbol {symbol} not subscribed, ignoring bar")
            return

        now = datetime.now()

        bar = BarEvent(
            symbol=symbol,
            freq=freq,
            open=open,
            high=high,
            low=low,
            close=close,
            volume=volume,
            turnover=turnover,
            bar_time=bar_time or now,
            timestamp=timestamp or now,
        )
        self._publish_bar(bar)
        logger.debug(f"Mock bar pushed: {symbol} {freq} close={close}")
