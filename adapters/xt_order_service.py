"""
xt_order_service.py — 迅投交易服务

封装 XtTraderApi 的下单功能，提供同步下单接口。
包括：普通下单、撤单、订单查询等。
"""

import sys
import os
import threading
import logging
import time
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from enum import Enum

# Python 层面不再强制修改全局 LD_LIBRARY_PATH 以免污染其他 C++ SDK
# 迅投依赖请在独立进程中使用 RPATH 或隔离的环境变量加载

sys.path.insert(0, '/home/ubuntu/xt_sdk')

try:
    from XtTraderPyApi import (
        XtTraderApi,
        XtTraderApiCallback,
        XtError,
        EBrokerLoginStatus,
        COrdinaryOrder,
        CIntelligentAlgorithmOrder,
        EPriceType,
        EOperationType,
    )
    _XT_AVAILABLE = True
except ImportError:
    _XT_AVAILABLE = False
    XtTraderApi = object
    XtTraderApiCallback = object
    class XtError: pass
    class EBrokerLoginStatus:
        BROKER_LOGIN_STATUS_OK = 1
        BROKER_LOGIN_STATUS_CLOSED = 2
    class COrdinaryOrder: pass
    class CIntelligentAlgorithmOrder: pass
    class EPriceType:
        PRTP_FIX = 0
        PRTP_MARKET = 1
        PRTP_MARKET_BEST = 2
    class EOperationType: pass

logger = logging.getLogger(__name__)


class OrderDirection(Enum):
    """订单方向"""
    BUY = "buy"              # 股票买入
    SELL = "sell"            # 股票卖出
    OPEN_LONG = "open_long"  # 期货开多
    CLOSE_LONG = "close_long"  # 期货平多
    OPEN_SHORT = "open_short"  # 期货开空
    CLOSE_SHORT = "close_short"  # 期货平空


class OrderPriceType(Enum):
    """订单价格类型"""
    LIMIT = "limit"          # 限价
    MARKET = "market"        # 市价
    BEST_PRICE = "best"      # 最优价
    TWAP = "twap"            # 时间加权平均价格算法
    VWAP = "vwap"            # 成交量加权平均价格算法


@dataclass
class OrderRequest:
    """下单请求"""
    account_id: str          # 资金账号
    asset_code: str          # 资产代码（如 "600519.SH"）
    direction: OrderDirection  # 买卖方向
    quantity: int            # 数量
    price: float = 0.0       # 价格（市价单可为0）
    price_type: OrderPriceType = OrderPriceType.LIMIT
    market: str = ""         # 市场代码（如 "SH"/"SZ"），如果为空则从asset_code解析
    instrument: str = ""     # 合约代码（如 "600519"），如果为空则从asset_code解析


@dataclass
class OrderResult:
    """下单结果"""
    success: bool
    order_id: Optional[int] = None
    error_msg: Optional[str] = None


class XtOrderService:
    """迅投下单服务"""

    def __init__(self, username: Optional[str] = None, password: Optional[str] = None):
        """
        初始化迅投下单服务

        Args:
            username: 迅投用户名（可选，默认使用配置）
            password: 迅投密码（可选，默认使用配置）
        """
        self._api: Optional[XtTraderApi] = None
        self._callback: Optional['_OrderCallback'] = None
        self._logined = False
        self._login_event = threading.Event()
        self._account_ready: Dict[str, str] = {}  # account_id -> account_key

        # 配置
        self.server_addr = "8.166.130.204:65300"
        self.username = username or "system_trade"
        self.password = password or "my123456@"
        self.config_path = "/home/ubuntu/xt_sdk/config"
        self.app_id = "xt_api_2.0"
        self.auth_code = "7f3c92e678f9ec77"

    def connect(self, timeout: float = 30.0) -> bool:
        """连接并登录迅投服务器"""
        if self._logined:
            logger.info("已经登录，跳过重复连接")
            return True

        try:
            # 创建 API 实例
            self._api = XtTraderApi.createXtTraderApi(self.server_addr)
            if self._api is None:
                logger.error("创建 XtTraderApi 实例失败")
                return False

            # 创建回调
            self._callback = _OrderCallback(
                api=self._api,
                username=self.username,
                password=self.password,
                app_id=self.app_id,
                auth_code=self.auth_code,
                login_event=self._login_event,
                account_ready=self._account_ready,
            )

            # 注册回调
            self._api.setCallback(self._callback)

            # 初始化 API
            init_result = self._api.init(self.config_path)
            logger.info("XtTrader API 初始化结果: %s", init_result)

            # 在守护线程中启动异步网络循环
            network_thread = threading.Thread(target=self._api.join_async, daemon=True)
            network_thread.start()
            logger.info("XtTrader 异步网络循环已启动")

            # 等待登录完成
            if not self._login_event.wait(timeout):
                logger.error("XtTrader 登录超时（%s 秒）", timeout)
                return False

            # 如果等到了事件，还需要校验是不是真的拿到了 account_key
            if not self._account_ready:
                logger.error("XtTrader 登录流程结束，但未获取到合法账号鉴权信息（可能是无权限或密码错误）")
                return False

            self._logined = True
            logger.info("XtTrader 登录成功")
            return True

        except Exception as e:
            logger.exception("XtTrader 连接失败: %s", e)
            return False

    def disconnect(self):
        """断开连接"""
        if self._api is not None:
            try:
                self._api.exit()
                logger.info("XtTrader 已断开连接")
            except Exception as e:
                logger.exception("XtTrader 断开连接异常: %s", e)
            finally:
                self._api = None
                self._callback = None
                self._logined = False
                self._login_event.clear()
                self._account_ready.clear()

    def place_order(self, order_req: OrderRequest, timeout: float = 10.0) -> OrderResult:
        """
        下单

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
                error_msg=f"未找到账号 {order_req.account_id} 对应的 account_key"
            )

        try:
            # 解析资产代码
            if not order_req.market or not order_req.instrument:
                parts = order_req.asset_code.split('.')
                if len(parts) == 2:
                    order_req.instrument = parts[0].lower()  # 合约代码必须小写！
                    order_req.market = parts[1].upper()      # 交易所代码大写
                else:
                    return OrderResult(
                        success=False,
                        error_msg=f"无效的资产代码格式: {order_req.asset_code}"
                    )

            # 构造订单对象
            order = COrdinaryOrder()
            order.m_strAccountID = order_req.account_id
            order.m_strInstrument = order_req.instrument
            order.m_strMarket = order_req.market
            order.m_nVolume = order_req.quantity
            order.m_dPrice = order_req.price

            # 记录详细的订单参数
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
                order.m_ePriceType = EPriceType.PRTP_FIX  # 限价
            elif order_req.price_type == OrderPriceType.MARKET:
                order.m_ePriceType = EPriceType.PRTP_MARKET  # 市价
            elif order_req.price_type == OrderPriceType.BEST_PRICE:
                order.m_ePriceType = EPriceType.PRTP_MARKET_BEST  # 最优价
            else:
                order.m_ePriceType = EPriceType.PRTP_FIX  # 默认限价

            # 设置买卖方向
            direction_map = {
                OrderDirection.BUY: EOperationType.OPT_BUY,
                OrderDirection.SELL: EOperationType.OPT_SELL,
                OrderDirection.OPEN_LONG: EOperationType.OPT_OPEN_LONG,
                OrderDirection.CLOSE_LONG: EOperationType.OPT_CLOSE_LONG_TODAY,
                OrderDirection.OPEN_SHORT: EOperationType.OPT_OPEN_SHORT,
                OrderDirection.CLOSE_SHORT: EOperationType.OPT_CLOSE_SHORT_TODAY,
            }
            order.m_eOperationType = direction_map.get(order_req.direction, EOperationType.OPT_BUY)

            # 获取 account_key（必须！）
            account_key = self._account_ready.get(order_req.account_id)
            if account_key is None:
                return OrderResult(
                    success=False,
                    error_msg=f"未找到账号 {order_req.account_id} 对应的 account_key，请确认账号已登录"
                )

            # 同步下单（必须传入 account_key）
            error = XtError(0, "")
            order_id = self._api.orderSync(order, error, account_key)

            # 记录原始返回值
            logger.info(
                "orderSync 返回: order_id=%s, error.isSuccess()=%s, error.errorMsg()=%s",
                order_id,
                error.isSuccess(),
                error.errorMsg()
            )

            # 检查下单结果：必须同时满足 error.isSuccess() 和 order_id > 0
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
                error_msg = error.errorMsg() if not error.isSuccess() else f"订单被拒绝 (order_id={order_id})"
                logger.error("下单失败: %s", error_msg)
                return OrderResult(success=False, error_msg=error_msg)

        except Exception as e:
            logger.exception("下单异常: %s", e)
            return OrderResult(success=False, error_msg=str(e))

    def _place_algo_order(self, order_req: OrderRequest) -> OrderResult:
        """
        使用 CIntelligentAlgorithmOrder 下达 TWAP/VWAP 智能算法单。

        算法委托由迅投系统自动在指定时间窗口内拆分并执行，
        用户无需指定挂单价格，系统追踪市场价格自动下单。
        """
        algo_type = order_req.price_type.value.upper()  # "TWAP" or "VWAP"
        logger.info(
            "准备下达 %s 算法单: account=%s, asset=%s, volume=%d",
            algo_type, order_req.account_id, order_req.asset_code, order_req.quantity,
        )

        try:
            order = CIntelligentAlgorithmOrder()
            order.m_strAccountID = order_req.account_id
            order.m_strMarket = order_req.market
            order.m_strInstrument = order_req.instrument
            order.m_nVolume = order_req.quantity
            order.m_dPrice = order_req.price  # 基准价（参考价）
            order.m_ePriceType = EPriceType.PRTP_MARKET  # 算法单通常用市价跟踪
            order.m_strOrderType = algo_type  # "TWAP" or "VWAP"

            # 买卖方向
            direction_map = {
                OrderDirection.BUY: EOperationType.OPT_BUY,
                OrderDirection.SELL: EOperationType.OPT_SELL,
                OrderDirection.OPEN_LONG: EOperationType.OPT_OPEN_LONG,
                OrderDirection.CLOSE_LONG: EOperationType.OPT_CLOSE_LONG_TODAY,
                OrderDirection.OPEN_SHORT: EOperationType.OPT_OPEN_SHORT,
                OrderDirection.CLOSE_SHORT: EOperationType.OPT_CLOSE_SHORT_TODAY,
            }
            order.m_eOperationType = direction_map.get(order_req.direction, EOperationType.OPT_BUY)

            # 算法有效时间窗口（当前时间起 30 分钟）
            now_ts = int(time.time())
            order.m_nValidTimeStart = now_ts
            order.m_nValidTimeEnd = now_ts + 1800  # 30 分钟

            # 算法参数
            order.m_dMaxPartRate = 1       # 量比比例
            order.m_dMinAmountPerOrder = 1  # 委托最小金额（期货设为1）

            order.m_strRemark = f"CEP_{algo_type}"

            # 获取 account_key
            account_key = self._account_ready.get(order_req.account_id)
            if account_key is None:
                return OrderResult(
                    success=False,
                    error_msg=f"未找到账号 {order_req.account_id} 对应的 account_key"
                )

            # 同步下单
            error = XtError(0, "")
            order_id = self._api.orderSync(order, error, account_key)

            logger.info(
                "%s orderSync 返回: order_id=%s, success=%s, msg=%s",
                algo_type, order_id, error.isSuccess(), error.errorMsg(),
            )

            if error.isSuccess() and order_id > 0:
                logger.info(
                    "%s 算法单下单成功: order_id=%s, asset=%s, quantity=%d",
                    algo_type, order_id, order_req.asset_code, order_req.quantity,
                )
                return OrderResult(success=True, order_id=order_id)
            else:
                error_msg = error.errorMsg() if not error.isSuccess() else f"算法单被拒绝 (order_id={order_id})"
                logger.error("%s 算法单下单失败: %s", algo_type, error_msg)
                return OrderResult(success=False, error_msg=error_msg)

        except Exception as e:
            logger.exception("%s 算法单异常: %s", algo_type, e)
            return OrderResult(success=False, error_msg=str(e))

    def cancel_order(self, account_id: str, order_id: int) -> OrderResult:
        """
        撤单

        Args:
            account_id: 资金账号
            order_id: 订单ID

        Returns:
            撤单结果
        """
        if not self._logined or self._api is None:
            return OrderResult(success=False, error_msg="XtTrader 未登录")

        account_key = self._account_ready.get(account_id)
        if account_key is None:
            return OrderResult(
                success=False,
                error_msg=f"未找到账号 {account_id} 对应的 account_key"
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

    # ---------------------------------------------------------------------------
    # 订单查询方法
    # ---------------------------------------------------------------------------

    # 订单状态映射（根据迅投实际枚举值）
    _STATUS_MAP: Dict[int, str] = {
        0: "未知", 1: "已报", 2: "部分成交", 3: "全部成交",
        4: "已撤单", 5: "部成部撤", 6: "废单",
        48: "未知", 49: "已报", 50: "部分成交", 51: "全部成交",
        52: "待报", 53: "待撤", 54: "已撤单", 55: "部成部撤", 56: "废单",
    }

    def _parse_order_detail(self, order: Any) -> Dict[str, Any]:
        """将迅投 SDK 的订单对象解析为标准化字典"""
        from adapters.xt_query_service import OrderDetail as QOrderDetail

        market = getattr(order, 'm_strExchangeID',
                         getattr(order, 'm_strMarket',
                                 getattr(order, 'm_strExchange', 'UNKNOWN')))

        volume = getattr(order, 'm_nTotalVolume',
                         getattr(order, 'm_nVolume',
                                 getattr(order, 'm_nOrderVolume', 0)))

        traded_volume = getattr(order, 'm_nTradedVolume',
                                getattr(order, 'm_nTradeVolume', 0))

        price = getattr(order, 'm_dLimitPrice',
                        getattr(order, 'm_dPrice',
                                getattr(order, 'm_dAveragePrice', 0.0)))

        direction = getattr(order, 'm_nDirection', 0)
        if hasattr(direction, 'value'):
            direction = direction.value
        elif not isinstance(direction, int):
            try:
                direction = int(direction)
            except (ValueError, TypeError):
                direction = 0

        status = order.m_eOrderStatus
        if hasattr(status, 'value'):
            status = status.value
        elif not isinstance(status, int):
            try:
                status = int(status)
            except (ValueError, TypeError):
                status = 0

        return QOrderDetail(
            order_id=order.m_nOrderID,
            instrument=order.m_strInstrumentID,
            market=market,
            direction=direction,
            volume=volume,
            price=price,
            status=status,
            traded_volume=traded_volume,
            order_time=getattr(order, 'm_strInsertTime',
                               getattr(order, 'm_strOrderTime', '')),
            status_msg=self._STATUS_MAP.get(status, "未知"),
        )

    def query_orders(self, account_id: Optional[str] = None) -> List[Any]:
        """
        查询当日委托列表

        Args:
            account_id: 资金账号，为空则使用第一个就绪账号

        Returns:
            OrderDetail 列表
        """
        if not self._logined or self._api is None:
            logger.error("XtTrader 未登录，无法查询订单")
            return []

        if account_id is None:
            if not self._account_ready:
                logger.error("没有可用的账号")
                return []
            account_id = next(iter(self._account_ready.keys()))

        account_key = self._account_ready.get(account_id)
        if account_key is None:
            logger.error("未找到账号 %s 对应的 account_key", account_id)
            return []

        try:
            error = XtError(0, "")
            orders = self._api.reqOrderDetailSync(account_id, error, account_key)

            if not error.isSuccess():
                logger.error("查询当日订单失败: account_id=%s, 错误=%s", account_id, error.errorMsg())
                return []

            result = []
            if orders:
                for order in orders:
                    result.append(self._parse_order_detail(order))
                logger.info("当日订单查询成功: account_id=%s, 共 %d 笔", account_id, len(result))
            return result

        except Exception as e:
            logger.exception("查询当日订单异常: %s", e)
            return []

    def query_history_orders(self, account_id: Optional[str] = None,
                             start_date: str = "", end_date: str = "") -> List[Any]:
        """
        查询历史委托列表

        Args:
            account_id: 资金账号
            start_date: 开始日期，格式 YYYYMMDD
            end_date: 结束日期，格式 YYYYMMDD

        Returns:
            OrderDetail 列表
        """
        if not self._logined or self._api is None:
            logger.error("XtTrader 未登录，无法查询历史订单")
            return []

        if account_id is None:
            if not self._account_ready:
                logger.error("没有可用的账号")
                return []
            account_id = next(iter(self._account_ready.keys()))

        account_key = self._account_ready.get(account_id)
        if account_key is None:
            logger.error("未找到账号 %s 对应的 account_key", account_id)
            return []

        try:
            error = XtError(0, "")
            orders = self._api.reqHistoryOrderDetailSync(
                account_id, start_date, end_date, error, account_key
            )

            if not error.isSuccess():
                logger.error(
                    "查询历史订单失败: account_id=%s, %s ~ %s, 错误=%s",
                    account_id, start_date, end_date, error.errorMsg()
                )
                return []

            result = []
            if orders:
                for order in orders:
                    result.append(self._parse_order_detail(order))
                logger.info(
                    "历史订单查询成功: account_id=%s, %s ~ %s, 共 %d 笔",
                    account_id, start_date, end_date, len(result)
                )
            return result

        except Exception as e:
            logger.exception("查询历史订单异常: %s", e)
            return []

    @property
    def is_connected(self) -> bool:
        """返回当前连接状态"""
        return self._logined


# ---------------------------------------------------------------------------
# 回调处理类
# ---------------------------------------------------------------------------

class _OrderCallback(XtTraderApiCallback):
    """迅投下单服务回调处理器"""

    def __init__(
        self,
        api: XtTraderApi,
        username: str,
        password: str,
        app_id: str,
        auth_code: str,
        login_event: threading.Event,
        account_ready: Dict[str, str],
    ):
        super().__init__()
        self._api = api
        self._username = username
        self._password = password
        self._app_id = app_id
        self._auth_code = auth_code
        self._login_event = login_event
        self._account_ready = account_ready

    def onConnected(self, success, error_msg):
        """连接回调"""
        if success:
            logger.info("XtTrader 连接成功，开始登录...")
            try:
                # 使用同步登录接口
                error = self._api.userLoginSync(
                    self._username,
                    self._password,
                    "",
                    self._app_id,
                    self._auth_code
                )
                if error.isSuccess():
                    logger.info("XtTrader 同步登录成功，等待账号就绪...")
                else:
                    logger.error("XtTrader 同步登录失败: %s", error.errorMsg())
                    self._login_event.set()
            except Exception as e:
                logger.exception("XtTrader 登录过程异常: %s", e)
                self._login_event.set()
        else:
            logger.error("XtTrader 连接失败: %s", error_msg)
            self._login_event.set()

    def onDisconnected(self, reason):
        """断开连接回调"""
        logger.warning("XtTrader 连接断开: %s", reason)

    def onUserLogin(self, username, password, nRequestId, error):
        """用户登录回调"""
        logger.info("onUserLogin: username=%s, success=%s", username, error.isSuccess())

    def onRtnLoginStatusWithActKey(self, account_id, status, account_type, account_key, error_msg):
        """账号登录状态回调"""
        logger.info(
            "onRtnLoginStatusWithActKey: account_id=%s, account_type=%s, status=%s, error_msg=%s",
            account_id, account_type, status, error_msg
        )

        # 账号就绪，保存 account_key
        if status == EBrokerLoginStatus.BROKER_LOGIN_STATUS_OK or status == EBrokerLoginStatus.BROKER_LOGIN_STATUS_CLOSED:
            self._account_ready[account_id] = account_key
            logger.info("账号 %s 就绪，account_key=%s", account_id, account_key)
            # 第一个账号就绪时触发登录完成
            if not self._login_event.is_set():
                self._login_event.set()

    def onOrderEvent(self, order_event, error):
        """订单回报"""
        if error.isSuccess():
            logger.info("订单回报: order_id=%s, status=%s", order_event.m_nOrderID, order_event.m_nOrderStatus)
        else:
            logger.error("订单回报错误: %s", error.errorMsg())

    def onTradeEvent(self, trade_event, error):
        """成交回报"""
        if error.isSuccess():
            logger.info("成交回报: order_id=%s, volume=%d, price=%.2f",
                       trade_event.m_nOrderID, trade_event.m_nTradeVolume, trade_event.m_dTradePrice)
        else:
            logger.error("成交回报错误: %s", error.errorMsg())


