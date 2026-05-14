"""
xt_order_service.py — 迅投下单服务

封装 XtTraderApi 的下单功能，提供同步下单接口。
继承 XtBaseService 获得连接管理能力。
"""
# pyright: reportAssignmentType=false

import os
import sys
import logging
import time
from typing import Any, Optional
from dataclasses import dataclass
from enum import Enum

_xt_sdk_path = os.environ.get("XT_SDK_PATH", os.path.expanduser("~/xt_sdk"))
if _xt_sdk_path not in sys.path:
    sys.path.insert(0, _xt_sdk_path)

try:
    from XtTraderPyApi import (
        XtError as _XtError,
        COrdinaryOrder as _COrdinaryOrder,
        CIntelligentAlgorithmOrder as _CIntelligentAlgorithmOrder,
        EPriceType as _EPriceType,
        EOperationType as _EOperationType,
    )

    _XT_AVAILABLE = True
    XtError: Any = _XtError
    COrdinaryOrder: Any = _COrdinaryOrder
    CIntelligentAlgorithmOrder: Any = _CIntelligentAlgorithmOrder
    EPriceType: Any = _EPriceType
    EOperationType: Any = _EOperationType
except ImportError:
    _XT_AVAILABLE = False

    class _XtError:
        def __init__(self, *args: Any) -> None:
            pass

        def isSuccess(self) -> bool:
            return False

        def errorMsg(self) -> str:
            return ""

    class _COrdinaryOrder:
        def __setattr__(self, name: str, value: Any) -> None:
            super().__setattr__(name, value)

        def __getattr__(self, name: str) -> Any:
            raise AttributeError(name)

    class _CIntelligentAlgorithmOrder:
        def __setattr__(self, name: str, value: Any) -> None:
            super().__setattr__(name, value)

        def __getattr__(self, name: str) -> Any:
            raise AttributeError(name)

    class _EPriceType:
        PRTP_FIX = 0
        PRTP_MARKET = 1
        PRTP_MARKET_BEST = 2

    class _EOperationType:
        OPT_BUY = 0
        OPT_SELL = 1
        OPT_OPEN_LONG = 2
        OPT_CLOSE_LONG_TODAY = 3
        OPT_OPEN_SHORT = 4
        OPT_CLOSE_SHORT_TODAY = 5

    XtError = _XtError
    COrdinaryOrder = _COrdinaryOrder
    CIntelligentAlgorithmOrder = _CIntelligentAlgorithmOrder
    EPriceType = _EPriceType
    EOperationType = _EOperationType

from adapters.xuntou.base_service import XtBaseService, _XtBaseCallback

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------


class OrderDirection(Enum):
    """订单方向"""

    BUY = "buy"  # 股票买入
    SELL = "sell"  # 股票卖出
    OPEN_LONG = "open_long"  # 期货开多
    CLOSE_LONG = "close_long"  # 期货平多
    OPEN_SHORT = "open_short"  # 期货开空
    CLOSE_SHORT = "close_short"  # 期货平空


class OrderPriceType(Enum):
    """订单价格类型"""

    LIMIT = "limit"  # 限价
    MARKET = "market"  # 市价
    BEST_PRICE = "best"  # 最优价
    TWAP = "twap"  # 时间加权平均价格算法
    VWAP = "vwap"  # 成交量加权平均价格算法


@dataclass
class OrderRequest:
    """下单请求"""

    account_id: str  # 资金账号
    asset_code: str  # 资产代码（如 "600519.SH"）
    direction: OrderDirection  # 买卖方向
    quantity: int  # 数量
    price: float = 0.0  # 价格（市价单可为0）
    price_type: OrderPriceType = OrderPriceType.LIMIT
    market: str = ""  # 市场代码（如 "SH"/"SZ"），如果为空则从asset_code解析
    instrument: str = ""  # 合约代码（如 "600519"），如果为空则从asset_code解析


@dataclass
class OrderResult:
    """下单结果"""

    success: bool
    order_id: Optional[int] = None
    error_msg: Optional[str] = None


# ---------------------------------------------------------------------------
# 下单回调（扩展基础回调，增加订单/成交推送）
# ---------------------------------------------------------------------------


class _OrderCallback(_XtBaseCallback):
    """迅投下单服务回调 — 在基础回调上增加订单和成交推送处理，直接写入 DB"""

    # SDK 订单状态枚举 → 我们的 XtStatus 映射
    _STATUS_MAP = {
        # EEntrustStatus 数值
        1: "sent",
        49: "sent",  # 已报
        2: "partial",
        50: "partial",  # 部分成交
        3: "filled",
        51: "filled",  # 全部成交
        4: "cancelled",
        54: "cancelled",  # 已撤单
        5: "partial",
        55: "partial",  # 部成部撤
        6: "rejected",
        56: "rejected",  # 废单
        52: "sent",  # 待报
        53: "sent",  # 待撤
    }

    def __init__(self, **kwargs):
        # 提取 dao 参数，其余传给父类
        self._dao = kwargs.pop("dao", None)
        super().__init__(**kwargs)

    def onRtnOrder(self, order_detail):
        """订单状态变更推送 → 更新 DB 中的 xt_status

        注意：onRtnOrder 传入的是 COrderInfo，状态字段是 m_eStatus (EOrderCommandStatus)，
        而非 COrderDetail 的 m_eOrderStatus (EEntrustStatus)。
        """
        try:
            order_id = getattr(order_detail, "m_nOrderID", 0)
            error_msg = getattr(order_detail, "m_strMsg", "") or ""

            # COrderInfo 的状态字段是 m_eStatus，不是 m_eOrderStatus
            raw_status = getattr(order_detail, "m_eStatus", None)
            status_val = raw_status
            if hasattr(status_val, "value"):
                status_val = status_val.value

            # EOrderCommandStatus 映射（根据实际回调观测到的枚举值）
            # OCS_APPROVING = 0 → 审批中/待执行
            # OCS_FINISHED  = 4 → 已完成
            CMD_STATUS_MAP = {
                0: "sent",      # OCS_APPROVING 审批中/待执行
                1: "sent",      # 运行中（推测）
                2: "sent",      # 运行中（推测）
                3: "cancelled", # 已撤销（推测）
                4: "filled",    # OCS_FINISHED 已完成
                5: "stopped",   # 已停止（推测）
                6: "send_failed",  # 失败（推测）
            }
            xt_status = CMD_STATUS_MAP.get(status_val) if status_val is not None else None

            # 如果 m_eStatus 读不到或值不在映射中，通过 msg 文本推断（保底）
            if xt_status is None:
                msg_lower = error_msg.lower()
                if "完成" in error_msg or "finish" in msg_lower:
                    xt_status = "filled"
                elif "撤" in error_msg or "cancel" in msg_lower:
                    xt_status = "cancelled"
                elif "失败" in error_msg or "error" in msg_lower or "fail" in msg_lower:
                    xt_status = "send_failed"
                elif "驳回" in error_msg or "reject" in msg_lower:
                    xt_status = "rejected"
                elif "部分" in error_msg or "partial" in msg_lower:
                    xt_status = "partial"
                else:
                    xt_status = "sent"

            logger.info(
                "订单回报(onRtnOrder): order_id=%s, raw_status=%s(val=%s) → xt_status=%s, msg=%s",
                order_id,
                raw_status,
                status_val,
                xt_status,
                error_msg,
            )

            if self._dao and order_id:
                try:
                    self._dao.update_order_xt_status(
                        xt_order_id=order_id,
                        xt_status=xt_status,
                        xt_error_msg=error_msg,
                    )
                except Exception as e:
                    logger.error("回调写入 DB 失败 (onRtnOrder): %s", e)
            elif not self._dao:
                logger.warning("onRtnOrder: _dao 为 None，无法写入 DB")
        except Exception as e:
            logger.exception("onRtnOrder 处理异常: %s", e)

    def onRtnDealDetail(self, deal_detail):
        """成交回报推送 → 更新 DB 中的成交量/成交价"""
        try:
            order_id = getattr(deal_detail, "m_nOrderID", 0)
            volume = getattr(deal_detail, "m_nTradeVolume",
                             getattr(deal_detail, "m_nTradedVolume", 0))
            price = getattr(deal_detail, "m_dTradePrice",
                            getattr(deal_detail, "m_dAveragePrice", 0.0))

            logger.info(
                "成交回报(onRtnDealDetail): order_id=%s, volume=%s, price=%s",
                order_id,
                volume,
                price,
            )

            if self._dao and order_id:
                try:
                    self._dao.update_order_xt_trade(
                        xt_order_id=order_id,
                        traded_volume=volume,
                        traded_price=price,
                    )
                except Exception as e:
                    logger.error("回调写入 DB 失败 (onRtnDealDetail): %s", e)
            elif not self._dao:
                logger.warning("onRtnDealDetail: _dao 为 None，无法写入 DB")
        except Exception as e:
            logger.exception("onRtnDealDetail 处理异常: %s", e)

    def onRtnOrderError(self, order_error):
        """订单错误回报 → 更新 DB"""
        try:
            order_id = getattr(order_error, "m_nOrderID", 0)
            error_msg = getattr(order_error, "m_strMsg",
                                getattr(order_error, "m_strErrorMsg", "未知错误"))

            logger.error(
                "订单错误回报(onRtnOrderError): order_id=%s, error=%s",
                order_id,
                error_msg,
            )

            if self._dao and order_id:
                try:
                    self._dao.update_order_xt_status(
                        xt_order_id=order_id,
                        xt_status="rejected",
                        xt_error_msg=error_msg or "订单被拒绝",
                    )
                except Exception as e:
                    logger.error("回调写入 DB 失败 (onRtnOrderError): %s", e)
        except Exception as e:
            logger.exception("onRtnOrderError 处理异常: %s", e)


# ---------------------------------------------------------------------------
# 下单服务
# ---------------------------------------------------------------------------


class XtOrderService(XtBaseService):
    """
    迅投下单服务

    继承 XtBaseService 的连接管理能力，提供下单和撤单功能。
    """

    # 使用扩展的回调类（包含订单/成交推送）
    _callback_class = _OrderCallback

    def place_order(
        self, order_req: OrderRequest, timeout: float = 10.0
    ) -> OrderResult:
        """
        同步下单

        Args:
            order_req: 下单请求
            timeout: 超时时间（秒）

        Returns:
            下单结果
        """
        if not self._logined or self._api is None:
            return OrderResult(success=False, error_msg="XtTrader 未登录")

        # 获取 account_key
        account_key = self._account_ready.get(order_req.account_id)
        if account_key is None:
            return OrderResult(
                success=False,
                error_msg=f"未找到账号 {order_req.account_id} 对应的 account_key",
            )

        try:
            # 解析资产代码
            if not order_req.market or not order_req.instrument:
                parts = order_req.asset_code.split(".")
                if len(parts) == 2:
                    order_req.instrument = parts[0].lower()  # 合约代码必须小写！
                    order_req.market = parts[1].upper()  # 交易所代码大写
                else:
                    return OrderResult(
                        success=False,
                        error_msg=f"无效的资产代码格式: {order_req.asset_code}",
                    )

            # 构造订单对象
            order = COrdinaryOrder()
            order.m_strAccountID = order_req.account_id
            order.m_strInstrument = order_req.instrument
            order.m_strMarket = order_req.market
            order.m_nVolume = order_req.quantity
            order.m_dPrice = order_req.price

            logger.info(
                "准备下单: account_id=%s, instrument=%s, market=%s, volume=%d, price=%.2f, direction=%s",
                order.m_strAccountID,
                order.m_strInstrument,
                order.m_strMarket,
                order.m_nVolume,
                order.m_dPrice,
                order_req.direction.value,
            )

            # TWAP / VWAP → 走智能算法单路径
            if order_req.price_type in (OrderPriceType.TWAP, OrderPriceType.VWAP):
                return self._place_algo_order(order_req)

            # 设置价格类型
            if order_req.price_type == OrderPriceType.LIMIT:
                order.m_ePriceType = EPriceType.PRTP_FIX
            elif order_req.price_type == OrderPriceType.MARKET:
                order.m_ePriceType = EPriceType.PRTP_MARKET
            elif order_req.price_type == OrderPriceType.BEST_PRICE:
                order.m_ePriceType = EPriceType.PRTP_MARKET_BEST
            else:
                order.m_ePriceType = EPriceType.PRTP_FIX

            # 设置买卖方向
            direction_map = {
                OrderDirection.BUY: EOperationType.OPT_BUY,
                OrderDirection.SELL: EOperationType.OPT_SELL,
                OrderDirection.OPEN_LONG: EOperationType.OPT_OPEN_LONG,
                OrderDirection.CLOSE_LONG: EOperationType.OPT_CLOSE_LONG_TODAY,
                OrderDirection.OPEN_SHORT: EOperationType.OPT_OPEN_SHORT,
                OrderDirection.CLOSE_SHORT: EOperationType.OPT_CLOSE_SHORT_TODAY,
            }
            order.m_eOperationType = direction_map.get(
                order_req.direction, EOperationType.OPT_BUY
            )

            # 同步下单
            error = XtError(0, "")
            order_id = self._api.orderSync(order, error, account_key)

            logger.info(
                "orderSync 返回: order_id=%s, error.isSuccess()=%s, error.errorMsg()=%s",
                order_id,
                error.isSuccess(),
                error.errorMsg(),
            )

            if error.isSuccess() and order_id > 0:
                logger.info(
                    "下单成功: order_id=%s, account=%s, asset=%s, direction=%s, quantity=%d, price=%.2f",
                    order_id,
                    order_req.account_id,
                    order_req.asset_code,
                    order_req.direction.value,
                    order_req.quantity,
                    order_req.price,
                )
                return OrderResult(success=True, order_id=order_id)
            else:
                error_msg = (
                    error.errorMsg()
                    if not error.isSuccess()
                    else f"订单被拒绝 (order_id={order_id})"
                )
                logger.error("下单失败: %s", error_msg)
                return OrderResult(success=False, error_msg=error_msg)

        except Exception as e:
            logger.exception("下单异常: %s", e)
            return OrderResult(success=False, error_msg=str(e))

    def _place_algo_order(self, order_req: OrderRequest) -> OrderResult:
        """
        使用 CIntelligentAlgorithmOrder 下达 TWAP/VWAP 智能算法单。
        """
        if self._api is None:
            return OrderResult(success=False, error_msg="XtTrader 未登录")

        algo_type = order_req.price_type.value.upper()
        logger.info(
            "准备下达 %s 算法单: account=%s, asset=%s, volume=%d",
            algo_type,
            order_req.account_id,
            order_req.asset_code,
            order_req.quantity,
        )

        try:
            order = CIntelligentAlgorithmOrder()
            order.m_strAccountID = order_req.account_id
            order.m_strMarket = order_req.market
            order.m_strInstrument = order_req.instrument
            order.m_nVolume = order_req.quantity
            order.m_dPrice = order_req.price
            order.m_ePriceType = EPriceType.PRTP_MARKET
            order.m_strOrderType = algo_type

            direction_map = {
                OrderDirection.BUY: EOperationType.OPT_BUY,
                OrderDirection.SELL: EOperationType.OPT_SELL,
                OrderDirection.OPEN_LONG: EOperationType.OPT_OPEN_LONG,
                OrderDirection.CLOSE_LONG: EOperationType.OPT_CLOSE_LONG_TODAY,
                OrderDirection.OPEN_SHORT: EOperationType.OPT_OPEN_SHORT,
                OrderDirection.CLOSE_SHORT: EOperationType.OPT_CLOSE_SHORT_TODAY,
            }
            order.m_eOperationType = direction_map.get(
                order_req.direction, EOperationType.OPT_BUY
            )

            now_ts = int(time.time())
            order.m_nValidTimeStart = now_ts
            order.m_nValidTimeEnd = now_ts + 1800

            order.m_dMaxPartRate = 1
            order.m_dMinAmountPerOrder = 1
            order.m_strRemark = f"CEP_{algo_type}"

            account_key = self._account_ready.get(order_req.account_id)
            if account_key is None:
                return OrderResult(
                    success=False,
                    error_msg=f"未找到账号 {order_req.account_id} 对应的 account_key",
                )

            error = XtError(0, "")
            order_id = self._api.orderSync(order, error, account_key)

            logger.info(
                "%s orderSync 返回: order_id=%s, success=%s, msg=%s",
                algo_type,
                order_id,
                error.isSuccess(),
                error.errorMsg(),
            )

            if error.isSuccess() and order_id > 0:
                logger.info(
                    "%s 算法单下单成功: order_id=%s, asset=%s, quantity=%d",
                    algo_type,
                    order_id,
                    order_req.asset_code,
                    order_req.quantity,
                )
                return OrderResult(success=True, order_id=order_id)
            else:
                error_msg = (
                    error.errorMsg()
                    if not error.isSuccess()
                    else f"算法单被拒绝 (order_id={order_id})"
                )
                logger.error("%s 算法单下单失败: %s", algo_type, error_msg)
                return OrderResult(success=False, error_msg=error_msg)

        except Exception as e:
            logger.exception("%s 算法单异常: %s", algo_type, e)
            return OrderResult(success=False, error_msg=str(e))

    def cancel_order(self, account_id: str, order_id: int) -> OrderResult:
        """撤单"""
        if not self._logined or self._api is None:
            return OrderResult(success=False, error_msg="XtTrader 未登录")

        account_key = self._account_ready.get(account_id)
        if account_key is None:
            return OrderResult(
                success=False, error_msg=f"未找到账号 {account_id} 对应的 account_key"
            )

        try:
            error = XtError(0, "")
            self._api.cancelOrderSync(account_id, order_id, error, account_key)

            if error.isSuccess():
                logger.info("撤单成功: account=%s, order_id=%s", account_id, order_id)
                return OrderResult(success=True, order_id=order_id)
            else:
                logger.error("撤单失败: %s", error.errorMsg())
                return OrderResult(success=False, error_msg=error.errorMsg())

        except Exception as e:
            logger.exception("撤单异常: %s", e)
            return OrderResult(success=False, error_msg=str(e))
