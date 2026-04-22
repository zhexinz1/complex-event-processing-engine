"""
xt_query_service.py — 迅投查询服务

封装 XtTraderApi 的查询功能，提供同步查询接口。
包括：产品查询、资金查询、账户详情查询等。
"""

import sys
import os
import threading
import logging
import time
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
# Python 层面不再强制修改全局 LD_LIBRARY_PATH 以免污染其他 C++ SDK
# 迅投依赖请在独立进程中使用 RPATH 或隔离的环境变量加载

sys.path.insert(0, '/home/ubuntu/xt_sdk')

try:
    from XtTraderPyApi import (
        XtTraderApi,
        XtTraderApiCallback,
        XtError,
        EBrokerLoginStatus,
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

logger = logging.getLogger(__name__)


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
    balance: float          # 总资产
    available: float        # 可用资金
    frozen: float          # 冻结资金
    market_value: float    # 持仓市值


@dataclass
class OrderDetail:
    """订单详情"""
    order_id: int
    instrument: str         # 合约代码
    market: str            # 交易所
    direction: int         # 买卖方向
    volume: int            # 委托数量
    price: float           # 委托价格
    status: int            # 订单状态
    traded_volume: int     # 成交数量
    order_time: str        # 委托时间
    status_msg: str        # 状态描述


class XtQueryService:
    """迅投查询服务（单例模式）"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, '_initialized'):
            return

        self._initialized = True
        self._api: Optional[XtTraderApi] = None
        self._callback: Optional['_QueryCallback'] = None
        self._logined = False
        self._login_event = threading.Event()
        self._account_ready: Dict[str, str] = {}  # account_id -> account_key

        # 配置
        self.server_addr = "8.166.130.204:65300"
        self.username = "system_trade"
        self.password = "my123456@"
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
            self._callback = _QueryCallback(
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

    def query_products(self, timeout: float = 10.0) -> List[ProductInfo]:
        """
        查询产品列表

        Returns:
            产品信息列表
        """
        if not self._logined or self._api is None:
            logger.error("XtTrader 未登录，无法查询产品")
            return []

        try:
            error = XtError(0, "")
            product_list = self._api.reqProductDataSync(error)

            if error.isSuccess():
                result = []
                for data in product_list:
                    product = ProductInfo(
                        product_id=data.m_nProductId,
                        product_name=data.m_strProductName,
                        product_code=data.m_strProductCode,
                        total_net_value=data.m_dTotalNetValue
                    )
                    result.append(product)
                logger.info("查询到 %d 个产品", len(result))
                return result
            else:
                logger.error("查询产品失败: %s", error.errorMsg())
                return []

        except Exception as e:
            logger.exception("查询产品异常: %s", e)
            return []

    def get_available_cash(self, account_id: Optional[str] = None) -> Optional[float]:
        """
        查询账户可用资金

        Args:
            account_id: 资金账号，如果为空则使用默认账号

        Returns:
            可用资金，查询失败返回 None
        """
        if not self._logined or self._api is None:
            logger.error("XtTrader 未登录，无法查询资金")
            return None

        # 如果未指定账号，使用第一个就绪的账号
        if account_id is None:
            if not self._account_ready:
                logger.error("没有可用的账号")
                return None
            account_id = next(iter(self._account_ready.keys()))

        account_key = self._account_ready.get(account_id)
        if account_key is None:
            logger.error("未找到账号 %s 对应的 account_key", account_id)
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
                logger.error("资金查询失败: account_id=%s, 错误=%s", account_id, error.errorMsg())
                return None

        except Exception as e:
            logger.exception("资金查询异常: %s", e)
            return None

    def query_account_detail(self, account_id: Optional[str] = None) -> Optional[AccountDetail]:
        """
        查询账户详情

        Args:
            account_id: 资金账号，如果为空则使用默认账号

        Returns:
            账户详情，查询失败返回 None
        """
        if not self._logined or self._api is None:
            logger.error("XtTrader 未登录，无法查询账户详情")
            return None

        # 如果未指定账号，使用第一个就绪的账号
        if account_id is None:
            if not self._account_ready:
                logger.error("没有可用的账号")
                return None
            account_id = next(iter(self._account_ready.keys()))

        account_key = self._account_ready.get(account_id)
        if account_key is None:
            logger.error("未找到账号 %s 对应的 account_key", account_id)
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
                logger.error("账户详情查询失败: account_id=%s, 错误=%s", account_id, error.errorMsg())
                return None

        except Exception as e:
            logger.exception("账户详情查询异常: %s", e)
            return None

    def query_orders(self, account_id: Optional[str] = None) -> List[OrderDetail]:
        """
        查询订单列表

        Args:
            account_id: 资金账号，如果为空则使用默认账号

        Returns:
            订单详情列表，查询失败返回空列表
        """
        if not self._logined or self._api is None:
            logger.error("XtTrader 未登录，无法查询订单")
            return []

        # 如果未指定账号，使用第一个就绪的账号
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
                logger.error("查询订单失败: account_id=%s, 错误=%s", account_id, error.errorMsg())
                return []

            result = []
            if orders:
                # 订单状态映射（根据实际枚举值）
                status_map = {
                    0: "未知",
                    1: "已报",
                    2: "部分成交",
                    3: "全部成交",
                    4: "已撤单",
                    5: "部成部撤",
                    6: "废单",
                    48: "未知",  # 实际枚举值
                    49: "已报",
                    50: "部分成交",
                    51: "全部成交",
                    52: "待报",
                    53: "待撤",
                    54: "已撤单",  # ENTRUST_STATUS_CANCELED
                    55: "部成部撤",
                    56: "废单"
                }

                logger.info(f"查询到 {len(orders)} 笔订单")

                for order in orders:
                    # 打印第一笔订单的所有属性用于调试
                    if len(result) == 0:
                        logger.info("订单对象属性:")
                        for attr in dir(order):
                            if not attr.startswith('_'):
                                try:
                                    value = getattr(order, attr)
                                    logger.info(f"  {attr} = {value}")
                                except:
                                    pass
                    # 尝试获取交易所字段
                    market = getattr(order, 'm_strExchangeID',
                                   getattr(order, 'm_strMarket',
                                         getattr(order, 'm_strExchange', 'UNKNOWN')))

                    # 获取数量字段
                    volume = getattr(order, 'm_nTotalVolume',
                                   getattr(order, 'm_nVolume',
                                         getattr(order, 'm_nOrderVolume', 0)))

                    # 获取成交数量字段
                    traded_volume = getattr(order, 'm_nTradedVolume',
                                          getattr(order, 'm_nTradeVolume', 0))

                    # 获取价格字段
                    price = getattr(order, 'm_dLimitPrice',
                                  getattr(order, 'm_dPrice',
                                        getattr(order, 'm_dAveragePrice', 0.0)))

                    # 获取方向字段并转换为整数
                    direction = getattr(order, 'm_nDirection', 0)
                    if hasattr(direction, 'value'):
                        direction = direction.value
                    elif not isinstance(direction, int):
                        try:
                            direction = int(direction)
                        except:
                            direction = 0

                    # 获取状态字段并转换为整数
                    status = order.m_eOrderStatus
                    status_raw = str(status)
                    if hasattr(status, 'value'):
                        status = status.value
                    elif not isinstance(status, int):
                        try:
                            status = int(status)
                        except:
                            status = 0

                    # 记录状态转换（仅第一笔）
                    if len(result) == 0:
                        logger.info(f"状态转换: {status_raw} -> {status}")

                    result.append(OrderDetail(
                        order_id=order.m_nOrderID,
                        instrument=order.m_strInstrumentID,
                        market=market,
                        direction=direction,
                        volume=volume,
                        price=price,
                        status=status,
                        traded_volume=traded_volume,
                        order_time=getattr(order, 'm_strInsertTime', getattr(order, 'm_strOrderTime', '')),
                        status_msg=status_map.get(status, "未知")
                    ))

                logger.info("订单查询成功: account_id=%s, 共 %d 笔订单", account_id, len(result))

            return result

        except Exception as e:
            logger.exception("订单查询异常: %s", e)
            return []

    @property
    def is_connected(self) -> bool:
        """返回当前连接状态"""
        return self._logined


class _QueryCallback(XtTraderApiCallback):
    """查询服务回调处理器"""

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
        logger.info("onConnected: success=%s, error_msg=%s", success, error_msg)

        if success:
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
                    logger.info("XtTrader 同步登录成功")
                else:
                    logger.error("XtTrader 同步登录失败: %s", error.errorMsg())
                    self._login_event.set()
            except Exception as e:
                logger.exception("XtTrader 登录过程异常: %s", e)
                self._login_event.set()

    def onUserLogin(self, username, password, nRequestId, error):
        logger.info("onUserLogin: username=%s, success=%s", username, error.isSuccess())

    def onRtnLoginStatusWithActKey(self, account_id, status, account_type, account_key, error_msg):
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


# 全局单例
_xt_query_service: Optional[XtQueryService] = None


def get_xt_query_service() -> XtQueryService:
    """获取迅投查询服务单例"""
    global _xt_query_service
    if _xt_query_service is None:
        _xt_query_service = XtQueryService()
    return _xt_query_service
