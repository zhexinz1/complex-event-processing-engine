"""
xt_query_service.py — 迅投查询服务

封装 XtTraderApi 的所有查询功能，提供同步查询接口。
继承 XtBaseService 获得连接管理能力。
"""
# pyright: reportAssignmentType=false

import sys
import logging
from typing import Optional, List, Dict, Any
from dataclasses import dataclass

sys.path.insert(0, "/home/ubuntu/xt_sdk")

try:
    from XtTraderPyApi import XtError as _XtError

    _XT_AVAILABLE = True
    XtError: Any = _XtError
except ImportError:
    _XT_AVAILABLE = False

    class _XtError:
        def __init__(self, *args: Any) -> None:
            pass

        def isSuccess(self) -> bool:
            return False

        def errorMsg(self) -> str:
            return ""

    XtError = _XtError

from adapters.xuntou.base_service import XtBaseService

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------


@dataclass
class ProductInfo:
    """产品信息"""

    product_id: int
    product_name: str
    product_code: str
    total_net_value: float


@dataclass
class AccountDetail:
    """账户详情"""

    account_id: str
    balance: float  # 总资产
    available: float  # 可用资金
    frozen: float  # 冻结资金
    market_value: float  # 持仓市值


@dataclass
class OrderDetail:
    """委托详情（broker 柜台层面的委托单）"""

    order_id: int
    instrument: str  # 合约代码
    market: str  # 交易所
    direction: int  # 买卖方向
    volume: int  # 委托数量
    price: float  # 委托价格
    status: int  # 订单状态
    traded_volume: int  # 成交数量
    order_time: str  # 委托时间
    status_msg: str  # 状态描述


# ---------------------------------------------------------------------------
# 查询服务
# ---------------------------------------------------------------------------


class XtQueryService(XtBaseService):
    """
    迅投查询服务

    继承 XtBaseService 的连接管理能力，提供查询功能：
    - 产品 / 资金 / 账户详情查询
    - 当日委托 / 历史委托查询
    - 指令查询（含 CTP 驳回信息）
    """

    # 委托状态映射（来自 SDK 的 EEntrustStatus 枚举）
    ENTRUST_STATUS_MAP: Dict[int, str] = {
        0: "未知",
        1: "已报",
        2: "部分成交",
        3: "全部成交",
        4: "已撤单",
        5: "部成部撤",
        6: "废单",
        48: "未知",
        49: "已报",
        50: "部分成交",
        51: "全部成交",
        52: "待报",
        53: "待撤",
        54: "已撤单",
        55: "部成部撤",
        56: "废单",
    }

    # 指令状态映射（来自 SDK 的 EOrderCommandStatus 枚举）
    INSTRUCTION_STATUS_MAP: Dict[str, str] = {
        "OCS_CHECKING": "风控检查中",
        "OCS_RUNNING": "运行中",
        "OCS_APPROVING": "审批中",
        "OCS_REJECTED": "已驳回",
        "OCS_FINISHED": "已完成",
        "OCS_STOPPED": "已停止",
        "OCS_CANCELING": "撤销中",
    }

    # -------------------------------------------------------------------
    # 内部工具
    # -------------------------------------------------------------------

    def _parse_order_detail(self, order: Any) -> OrderDetail:
        """将迅投 SDK 的委托对象解析为标准化 OrderDetail"""
        market = getattr(
            order,
            "m_strExchangeID",
            getattr(order, "m_strMarket", getattr(order, "m_strExchange", "UNKNOWN")),
        )

        volume = getattr(
            order,
            "m_nTotalVolume",
            getattr(order, "m_nVolume", getattr(order, "m_nOrderVolume", 0)),
        )

        traded_volume = getattr(
            order, "m_nTradedVolume", getattr(order, "m_nTradeVolume", 0)
        )

        price = getattr(
            order,
            "m_dLimitPrice",
            getattr(order, "m_dPrice", getattr(order, "m_dAveragePrice", 0.0)),
        )

        direction: Any = getattr(order, "m_nDirection", 0)
        if hasattr(direction, "value"):
            direction = direction.value
        elif not isinstance(direction, int):
            try:
                direction = int(direction)
            except (ValueError, TypeError):
                direction = 0

        status: Any = order.m_eOrderStatus
        if hasattr(status, "value"):
            status = status.value
        elif not isinstance(status, int):
            try:
                status = int(status)
            except (ValueError, TypeError):
                status = 0

        return OrderDetail(
            order_id=order.m_nOrderID,
            instrument=order.m_strInstrumentID,
            market=market,
            direction=direction,
            volume=volume,
            price=price,
            status=status,
            traded_volume=traded_volume,
            order_time=getattr(
                order, "m_strInsertTime", getattr(order, "m_strOrderTime", "")
            ),
            status_msg=self.ENTRUST_STATUS_MAP.get(status, "未知"),
        )

    # -------------------------------------------------------------------
    # 产品 / 资金查询
    # -------------------------------------------------------------------

    def query_products(self) -> List[ProductInfo]:
        """查询产品列表"""
        if not self._logined or self._api is None:
            logger.error("XtTrader 未登录，无法查询产品")
            return []

        try:
            error = XtError(0, "")
            product_list = self._api.reqProductDataSync(error)

            if error.isSuccess():
                result = []
                for data in product_list:
                    result.append(
                        ProductInfo(
                            product_id=data.m_nProductId,
                            product_name=data.m_strProductName,
                            product_code=data.m_strProductCode,
                            total_net_value=data.m_dTotalNetValue,
                        )
                    )
                logger.info("查询到 %d 个产品", len(result))
                return result
            else:
                logger.error("查询产品失败: %s", error.errorMsg())
                return []

        except Exception as e:
            logger.exception("查询产品异常: %s", e)
            return []

    def get_available_cash(self, account_id: Optional[str] = None) -> Optional[float]:
        """查询账户可用资金"""
        if not self._logined or self._api is None:
            logger.error("XtTrader 未登录，无法查询资金")
            return None

        account_id, account_key = self._resolve_account(account_id)
        if account_id is None:
            return None

        try:
            error = XtError(0, "")
            data = self._api.reqAccountDetailSync(account_id, error, account_key)

            if error.isSuccess():
                available = data.m_dAvailable
                logger.info(
                    "资金查询成功: account_id=%s, 可用资金=%.2f, 总资产=%.2f",
                    account_id,
                    available,
                    data.m_dBalance,
                )
                return available
            else:
                logger.error(
                    "资金查询失败: account_id=%s, 错误=%s", account_id, error.errorMsg()
                )
                return None

        except Exception as e:
            logger.exception("资金查询异常: %s", e)
            return None

    def query_account_detail(
        self, account_id: Optional[str] = None
    ) -> Optional[AccountDetail]:
        """查询账户详情"""
        if not self._logined or self._api is None:
            logger.error("XtTrader 未登录，无法查询账户详情")
            return None

        account_id, account_key = self._resolve_account(account_id)
        if account_id is None:
            return None

        try:
            error = XtError(0, "")
            data = self._api.reqAccountDetailSync(account_id, error, account_key)

            if error.isSuccess():
                detail = AccountDetail(
                    account_id=account_id,
                    balance=data.m_dBalance,
                    available=data.m_dAvailable,
                    frozen=data.m_dFrozen,
                    market_value=data.m_dMarketValue,
                )
                logger.info("账户详情查询成功: %s", account_id)
                return detail
            else:
                logger.error(
                    "账户详情查询失败: account_id=%s, 错误=%s",
                    account_id,
                    error.errorMsg(),
                )
                return None

        except Exception as e:
            logger.exception("账户详情查询异常: %s", e)
            return None

    # -------------------------------------------------------------------
    # 委托查询（broker 柜台层面）
    # -------------------------------------------------------------------

    def query_today_orders(self, account_id: Optional[str] = None) -> List[OrderDetail]:
        """查询当日委托列表 (reqOrderDetailSync)"""
        if not self._logined or self._api is None:
            logger.error("XtTrader 未登录，无法查询当日委托")
            return []

        account_id, account_key = self._resolve_account(account_id)
        if account_id is None:
            return []

        try:
            error = XtError(0, "")
            orders = self._api.reqOrderDetailSync(account_id, error, account_key)

            if not error.isSuccess():
                logger.error(
                    "查询当日委托失败: account_id=%s, 错误=%s",
                    account_id,
                    error.errorMsg(),
                )
                return []

            result = []
            if orders:
                for order in orders:
                    result.append(self._parse_order_detail(order))
                logger.info(
                    "当日委托查询成功: account_id=%s, 共 %d 笔", account_id, len(result)
                )
            else:
                logger.info("当日委托查询: account_id=%s, 0 笔", account_id)
            return result

        except Exception as e:
            logger.exception("查询当日委托异常: %s", e)
            return []

    def query_history_orders(
        self,
        account_id: Optional[str] = None,
        start_date: str = "",
        end_date: str = "",
    ) -> List[OrderDetail]:
        """查询历史委托列表 (reqHistoryOrderDetailSync)"""
        if not self._logined or self._api is None:
            logger.error("XtTrader 未登录，无法查询历史委托")
            return []

        account_id, account_key = self._resolve_account(account_id)
        if account_id is None:
            return []

        try:
            error = XtError(0, "")
            orders = self._api.reqHistoryOrderDetailSync(
                account_id, start_date, end_date, error, account_key
            )

            if not error.isSuccess():
                logger.error(
                    "查询历史委托失败: account_id=%s, %s ~ %s, 错误=%s",
                    account_id,
                    start_date,
                    end_date,
                    error.errorMsg(),
                )
                return []

            result = []
            if orders:
                for order in orders:
                    result.append(self._parse_order_detail(order))
                logger.info(
                    "历史委托查询成功: account_id=%s, %s ~ %s, 共 %d 笔",
                    account_id,
                    start_date,
                    end_date,
                    len(result),
                )
            return result

        except Exception as e:
            logger.exception("查询历史委托异常: %s", e)
            return []

    # -------------------------------------------------------------------
    # 指令查询（迅投系统层面）
    # -------------------------------------------------------------------

    def query_instructions(
        self, account_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        查询指令列表 (reqCommandsInfoSync)

        重要区别：
        - reqOrderDetailSync 查的是「委托」（broker 柜台层面）
        - reqCommandsInfoSync 查的是「指令」（迅投系统层面）
        - 当 CTP 柜台驳回指令时（如资金不足），不会产生委托
        - 但 reqCommandsInfoSync 仍能查到指令及驳回原因
        """
        if not self._logined or self._api is None:
            logger.error("XtTrader 未登录，无法查询指令")
            return []

        try:
            error = XtError(0, "")
            cmds = self._api.reqCommandsInfoSync(error)

            if not error.isSuccess():
                logger.error("查询指令失败: 错误=%s", error.errorMsg())
                return []

            result = []
            if cmds:
                for cmd in cmds:
                    cmd_account = getattr(cmd, "m_strAccountID", "")
                    if account_id and cmd_account != account_id:
                        continue

                    raw_status = str(getattr(cmd, "m_eStatus", ""))
                    status_key = (
                        raw_status.split(".")[-1] if "." in raw_status else raw_status
                    )
                    status_msg = self.INSTRUCTION_STATUS_MAP.get(status_key, raw_status)

                    raw_direction = str(getattr(cmd, "m_eOperationType", ""))
                    direction_key = (
                        raw_direction.split(".")[-1]
                        if "." in raw_direction
                        else raw_direction
                    )

                    result.append(
                        {
                            "order_id": getattr(cmd, "m_nOrderID", 0),
                            "instrument": getattr(cmd, "m_strInstrument", ""),
                            "market": getattr(cmd, "m_strMarket", ""),
                            "direction": direction_key,
                            "volume": getattr(cmd, "m_nVolume", 0),
                            "price": getattr(cmd, "m_dPrice", 0.0),
                            "status": status_key,
                            "status_msg": status_msg,
                            "traded_volume": getattr(cmd, "m_dTradedVolume", 0.0),
                            "traded_price": getattr(cmd, "m_dTradedPrice", 0.0),
                            "traded_amount": getattr(cmd, "m_dTradedAmount", 0.0),
                            "error_msg": getattr(cmd, "m_strMsg", ""),
                            "account_id": cmd_account,
                            "broker_type": str(getattr(cmd, "m_eBrokerType", "")),
                        }
                    )

                logger.info(
                    "指令查询成功: 总数=%d, 过滤后=%d (account_id=%s)",
                    len(cmds),
                    len(result),
                    account_id or "全部",
                )

            return result

        except Exception as e:
            logger.exception("查询指令异常: %s", e)
            return []
