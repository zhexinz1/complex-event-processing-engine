"""
xt_base_service.py — 迅投基础服务

提供 XtTraderApi 的连接管理、登录认证和账号就绪等共享逻辑。
XtOrderService 和 XtQueryService 均继承此基类。
"""
# pyright: reportAssignmentType=false

import os
import sys
import threading
import logging
from typing import Optional, Dict, Any

_xt_sdk_path = os.environ.get("XT_SDK_PATH", os.path.expanduser("~/xt_sdk"))
if _xt_sdk_path not in sys.path:
    sys.path.insert(0, _xt_sdk_path)

try:
    from XtTraderPyApi import (
        XtTraderApi as _XtTraderApi,
        XtTraderApiCallback as _XtTraderApiCallback,
        XtError as _XtError,
        EBrokerLoginStatus as _EBrokerLoginStatus,
    )

    _XT_AVAILABLE = True
    XtTraderApi: Any = _XtTraderApi
    XtTraderApiCallback: Any = _XtTraderApiCallback
    XtError: Any = _XtError
    EBrokerLoginStatus: Any = _EBrokerLoginStatus
except ImportError:
    _XT_AVAILABLE = False
    XtTraderApi: Any = object
    XtTraderApiCallback: Any = object

    class _XtError:
        pass

    class _EBrokerLoginStatus:
        BROKER_LOGIN_STATUS_OK = 1
        BROKER_LOGIN_STATUS_CLOSED = 2

    XtError = _XtError
    EBrokerLoginStatus = _EBrokerLoginStatus

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 基础回调
# ---------------------------------------------------------------------------


class _XtBaseCallback(XtTraderApiCallback):
    """迅投基础回调处理器 — 处理连接、登录和账号就绪"""

    def __init__(
        self,
        api: Any,
        username: str,
        password: str,
        app_id: str,
        auth_code: str,
        login_event: threading.Event,
        account_ready: Dict[str, str],
        **kwargs: Any,
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
                error = self._api.userLoginSync(
                    self._username,
                    self._password,
                    "",
                    self._app_id,
                    self._auth_code,
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

    def onRtnLoginStatusWithActKey(
        self, account_id, status, account_type, account_key, error_msg
    ):
        """账号登录状态回调"""
        logger.info(
            "onRtnLoginStatusWithActKey: account_id=%s, account_type=%s, status=%s, error_msg=%s",
            account_id,
            account_type,
            status,
            error_msg,
        )

        if (
            status == EBrokerLoginStatus.BROKER_LOGIN_STATUS_OK
            or status == EBrokerLoginStatus.BROKER_LOGIN_STATUS_CLOSED
        ):
            self._account_ready[account_id] = account_key
            logger.info("账号 %s 就绪，account_key=%s", account_id, account_key)
            if not self._login_event.is_set():
                self._login_event.set()


# ---------------------------------------------------------------------------
# 基础服务
# ---------------------------------------------------------------------------


class XtBaseService:
    """
    迅投基础服务

    管理 API 连接生命周期、登录认证和账号鉴权信息。
    子类 XtOrderService / XtQueryService 继承此类实现具体业务。
    """

    # 子类可覆盖此属性来使用自定义回调类
    _callback_class = _XtBaseCallback

    def __init__(
        self,
        username: Optional[str] = None,
        password: Optional[str] = None,
        dao: Any = None,
    ):
        self._api: Optional[Any] = None
        self._callback: Optional[_XtBaseCallback] = None
        self._logined = False
        self._login_event = threading.Event()
        self._account_ready: Dict[str, str] = {}  # account_id -> account_key
        self._dao = dao  # 数据库访问层（可选，回调写 DB 时使用）

        # 配置
        self.server_addr = "8.166.130.204:65300"
        self.username = username or "system_trade"
        self.password = password or "my123456@"
        self.config_path = os.path.join(_xt_sdk_path, "config")
        self.app_id = "xt_api_2.0"
        self.auth_code = "7f3c92e678f9ec77"

    def connect(self, timeout: float = 30.0) -> bool:
        """连接并登录迅投服务器"""
        if self._logined:
            logger.info("已经登录，跳过重复连接")
            return True

        try:
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
            )
            self._api.setCallback(self._callback)

            init_result = self._api.init(self.config_path)
            logger.info("XtTrader API 初始化结果: %s", init_result)

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

    @property
    def is_connected(self) -> bool:
        """返回当前连接状态"""
        return self._logined

    def _resolve_account(self, account_id: Optional[str] = None):
        """
        解析 account_id 和 account_key。

        Returns:
            (account_id, account_key)，解析失败返回 (None, None)
        """
        if account_id is None:
            if not self._account_ready:
                logger.error("没有可用的账号")
                return None, None
            account_id = next(iter(self._account_ready.keys()))

        account_key = self._account_ready.get(account_id)
        if account_key is None:
            logger.error("未找到账号 %s 对应的 account_key", account_id)
            return None, None

        return account_id, account_key
