"""
xt_market_service.py — 迅投股票行情服务

封装 XtTraderApi 的行情订阅功能，通过 EventBus 发布 TickEvent。
"""
# pyright: reportAssignmentType=false

import os
import sys
import logging
from typing import Any, Optional
from datetime import datetime

_xt_sdk_path = os.environ.get("XT_SDK_PATH", os.path.expanduser("~/xt_sdk"))
if _xt_sdk_path not in sys.path:
    sys.path.insert(0, _xt_sdk_path)

try:
    from XtTraderPyApi import (
        XtError as _XtError,
        CSubscribData as _CSubscribData,
        EXTOfferStatus as _EXTOfferStatus,
    )

    _XT_AVAILABLE = True
    XtError: Any = _XtError
    CSubscribData: Any = _CSubscribData
    EXTOfferStatus: Any = _EXTOfferStatus
except ImportError:
    _XT_AVAILABLE = False

    class _XtError:
        def __init__(self, *args: Any) -> None:
            pass

        def isSuccess(self) -> bool:
            return False

        def errorMsg(self) -> str:
            return ""

    class _CSubscribData:
        def __setattr__(self, name: str, value: Any) -> None:
            super().__setattr__(name, value)

        def __getattr__(self, name: str) -> Any:
            raise AttributeError(name)

    class _EXTOfferStatus:
        XT_OFFER_STATUS_SP = 0

    XtError = _XtError
    CSubscribData = _CSubscribData
    EXTOfferStatus = _EXTOfferStatus

from adapters.xuntou.base_service import XtBaseService, _XtBaseCallback
from cep.core.events import TickEvent

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 行情回调
# ---------------------------------------------------------------------------


class _MarketCallback(_XtBaseCallback):
    """迅投行情服务回调 — 接收行情主推并发布为 EventBus 的 TickEvent"""

    def __init__(self, **kwargs):
        self._event_bus = kwargs.pop("event_bus", None)
        super().__init__(**kwargs)

    def onSubscribQuote(self, request_id, data, error):
        """订阅行情后的回调"""
        if error.isSuccess():
            logger.info("订阅行情成功: market=%s, instrument=%s", data.m_strExchangeID, data.m_strInstrumentID)
        else:
            logger.error("订阅行情失败: %s", error.errorMsg())

    def onRtnPriceData(self, data):
        """行情订阅成功后的行情主推，data对应CPriceData结构"""
        if not data:
            return

        symbol = f"{data.m_strInstrumentID}.{data.m_strExchangeID}"
        logger.info(
            "onRtnPriceData 收到推送: symbol=%s, last=%.4f, bid1=%.4f, ask1=%.4f, vol=%s",
            symbol, data.m_dLastPrice, data.m_dBidPrice1, data.m_dAskPrice1, data.m_nVolume,
        )

        if not self._event_bus:
            logger.warning("onRtnPriceData: event_bus 为 None，跳过发布")
            return

        # 提取五档买卖盘
        bid_prices = (
            data.m_dBidPrice1,
            data.m_dBidPrice2,
            data.m_dBidPrice3,
            data.m_dBidPrice4,
            data.m_dBidPrice5,
        )
        bid_volumes = (
            data.m_nBidVolume1,
            data.m_nBidVolume2,
            data.m_nBidVolume3,
            data.m_nBidVolume4,
            data.m_nBidVolume5,
        )
        ask_prices = (
            data.m_dAskPrice1,
            data.m_dAskPrice2,
            data.m_dAskPrice3,
            data.m_dAskPrice4,
            data.m_dAskPrice5,
        )
        ask_volumes = (
            data.m_nAskVolume1,
            data.m_nAskVolume2,
            data.m_nAskVolume3,
            data.m_nAskVolume4,
            data.m_nAskVolume5,
        )

        try:
            # 解析迅投的交易时间（与 CTP 保持一致的处理方式）
            try:
                trading_day = data.m_strTradingDay  # "YYYYMMDD"
                update_time = data.m_strUpdateTime  # "HH:MM:SS"
                ms = data.m_nUpdateMillisec
                timestamp = datetime.strptime(
                    f"{trading_day} {update_time}", "%Y%m%d %H:%M:%S"
                ).replace(microsecond=ms * 1000)
            except (ValueError, AttributeError):
                timestamp = datetime.now()

            tick_event = TickEvent(
                timestamp=timestamp,
                symbol=symbol,
                last_price=data.m_dLastPrice,
                bid_prices=bid_prices,
                bid_volumes=bid_volumes,
                ask_prices=ask_prices,
                ask_volumes=ask_volumes,
                volume=data.m_nVolume,
                turnover=data.m_dTurnover,
            )

            self._event_bus.publish(tick_event)

        except Exception as e:
            logger.error("解析并发布 TickEvent 时发生异常: %s", e)


# ---------------------------------------------------------------------------
# 行情服务
# ---------------------------------------------------------------------------


class XtMarketService(XtBaseService):
    """
    迅投行情服务
    
    继承 XtBaseService 的连接管理能力，提供行情订阅功能。
    """

    _callback_class = _MarketCallback

    def __init__(
        self,
        username: Optional[str] = None,
        password: Optional[str] = None,
        dao: Any = None,
        event_bus: Any = None,
    ):
        super().__init__(username=username, password=password, dao=dao)
        self._event_bus = event_bus
        self._request_id = 1000  # 递增的请求ID

    def connect(self, timeout: float = 30.0) -> bool:
        """重写 connect，注入 event_bus 到 callback 中"""
        if self._logined:
            logger.info("已经登录，跳过重复连接")
            return True

        try:
            from XtTraderPyApi import XtTraderApi
            self._api = XtTraderApi.createXtTraderApi(self.server_addr)
            if self._api is None:
                logger.error("创建 XtTraderApi 实例失败")
                return False

            self._callback = self._callback_class(
                api=self._api,
                username=self.username,
                password=self.password,
                app_id=self.app_id,
                auth_code=self.auth_code,
                login_event=self._login_event,
                account_ready=self._account_ready,
                dao=self._dao,
                event_bus=self._event_bus,  # 注入 event_bus
            )
            self._api.setCallback(self._callback)

            init_result = self._api.init(self.config_path)
            logger.info("XtTrader API 初始化结果: %s", init_result)

            import threading
            network_thread = threading.Thread(target=self._api.join_async, daemon=True)
            network_thread.start()
            logger.info("XtTrader 异步网络循环已启动")

            if not self._login_event.wait(timeout):
                logger.error("XtTrader 登录超时（%s 秒）", timeout)
                return False

            if not self._account_ready:
                logger.error("XtTrader 登录流程结束，但未获取到合法账号鉴权信息")
                return False

            self._logined = True
            logger.info("XtTrader 登录成功")
            return True

        except Exception as e:
            logger.exception("XtTrader 连接失败: %s", e)
            return False

    def subscribe(self, asset_codes: list[str]) -> bool:
        """
        批量订阅股票行情。
        
        Args:
            asset_codes: 合约代码列表，格式如 ["600519.SH", "000001.SZ"]
            
        Returns:
            发送订阅请求是否成功
        """
        if not self._logined or self._api is None:
            logger.error("XtTrader 未登录，无法订阅行情")
            return False

        if not asset_codes:
            return True

        sub_data_list = []
        for code in asset_codes:
            parts = code.split(".")
            if len(parts) != 2:
                logger.warning("跳过非法格式合约: %s", code)
                continue
                
            instrument = parts[0]
            market = parts[1].upper()

            # 股票和ETF的平台号为 0
            platform_id = 0

            sub = CSubscribData()
            sub.m_strExchangeID = market
            sub.m_strInstrumentID = instrument
            sub.m_nPlatformID = platform_id
            sub.m_eOfferStatus = EXTOfferStatus.XT_OFFER_STATUS_SP
            
            sub_data_list.append(sub)

        if not sub_data_list:
            return False

        try:
            self._request_id += 1
            self._api.batchSubscribQuote(sub_data_list, self._request_id)
            logger.info("已发送行情订阅请求: %s", asset_codes)
            return True
        except Exception as e:
            logger.exception("批量订阅异常: %s", e)
            return False
