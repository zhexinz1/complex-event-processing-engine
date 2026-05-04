"""
临时脚本：查询账号 90102870 下期货账号的可用资金。
"""

import sys
import os

# ---- 强制环境变量注入跳板 (XunTou SDK 依赖) ----
# 因为我们已经在全局 ~/.bashrc 移除了会导致 CTP 崩溃的迅投环境变量
# 所以如果要单独跑迅投的测试脚本，我们必须在这个脚本启动的第一秒，原生注入变量并重启自己。
_ld_lib_path = os.environ.get("LD_LIBRARY_PATH", "")
if "/home/ubuntu/xt_sdk" not in _ld_lib_path:
    print("⚠️ 探测到缺少迅投 C++ 动态链接库环境保护，正强制注入并重启进程...")
    os.environ["LD_LIBRARY_PATH"] = "/home/ubuntu/xt_sdk:" + _ld_lib_path
    os.execlp(sys.executable, sys.executable, "-m", "archive.tests.query_cash")

import threading
import logging

sys.path.insert(0, '/home/ubuntu/xt_sdk')
from XtTraderPyApi import (
    XtTraderApi,
    XtTraderApiCallback,
    XtError,
    EBrokerLoginStatus,
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

SERVER_ADDR  = "8.166.130.204:65300"
USERNAME     = "system_trade"
PASSWORD     = "my123456@"
TARGET_ACCT  = "90102870"
CONFIG_PATH  = "/home/ubuntu/xt_sdk/config"
LOGIN_TIMEOUT = 30.0

# 结果容器
result = {"available": None, "done": threading.Event()}


class _CB(XtTraderApiCallback):
    def __init__(self, api):
        super().__init__()
        self._api = api
        self._logined = False
        self._acct_id2key: dict = {}
        self._acct_key_status: dict = {}

    def onConnected(self, success, error_msg):
        logger.info("onConnected: success=%s, msg=%s", success, error_msg)
        if success:
            logger.info("连接成功，开始登录...")
            self._do_login()

    def onDisconnected(self, reason):
        logger.warning("onDisconnected: reason=%d", reason)

    def onUserLogin(self, username, password, nRequestId, error):
        logger.info("onUserLogin: username=%s, success=%s, msg=%s", username, error.isSuccess(), error.errorMsg() if not error.isSuccess() else "")
        if not error.isSuccess():
            logger.error("登录失败: %s", error.errorMsg())
            result["done"].set()

    def onUserLogout(self, username, password, nRequestId, error):
        pass

    def onRtnLoginStatus(self, account_id, status, account_type, error_msg):
        logger.info("onRtnLoginStatus: account_id=%s, status=%s, account_type=%s, error_msg=%s", account_id, status, account_type, error_msg)

    def _do_login(self):
        """连接成功后执行同步登录。必须用 userLoginSync，异步 userLogin 会报"未找到处理函数"。"""
        machine_info = ""
        app_id = "xt_api_2.0"
        auth_code = "7f3c92e678f9ec77"
        try:
            error = self._api.userLoginSync(USERNAME, PASSWORD, machine_info, app_id, auth_code)
            if error.isSuccess():
                self._logined = True
                logger.info("XtTrader 同步登录成功")
            else:
                logger.error("XtTrader 同步登录失败: %s", error.errorMsg())
                result["done"].set()
        except Exception as e:
            logger.exception("XtTrader 登录过程异常: %s", e)
            result["done"].set()

    def onRtnLoginStatusWithActKey(self, account_id, status, account_type, account_key, error_msg):
        self._acct_key_status[account_key] = status
        self._acct_id2key[account_id] = account_key
        logger.info(
            "onRtnLoginStatusWithActKey: account_id=%s, account_type=%s, status=%s, error_msg=%s",
            account_id, account_type, status, error_msg
        )

        # 找到目标账号且状态就绪 → 查询资金
        if account_id == TARGET_ACCT and (
            status == EBrokerLoginStatus.BROKER_LOGIN_STATUS_OK
            or status == EBrokerLoginStatus.BROKER_LOGIN_STATUS_CLOSED
        ):
            logger.info("目标账号就绪，开始查询资金...")
            errno = XtError(0, "")
            data = self._api.reqAccountDetailSync(account_id, errno, account_key)
            if errno.isSuccess():
                logger.info("=== 资金查询结果 ===")
                logger.info("账号 ID     : %s", data.m_strAccountID)
                logger.info("账号名称    : %s", data.m_strAccountName)
                logger.info("总资产      : %.2f", data.m_dBalance)
                logger.info("可用资金    : %.2f", data.m_dAvailable)
                logger.info("股票市值    : %.2f", data.m_dStockValue)
                logger.info("持仓盈亏    : %.2f", data.m_dPositionProfit)
                logger.info("平仓盈亏    : %.2f", data.m_dCloseProfit)
                result["available"] = data.m_dAvailable
            else:
                logger.error("资金查询失败: %s", errno.errorMsg())
            result["done"].set()


def main():
    api = XtTraderApi.createXtTraderApi(SERVER_ADDR)
    if api is None:
        logger.error("创建 API 实例失败")
        return

    cb = _CB(api)
    api.setCallback(cb)
    ret = api.init(CONFIG_PATH)
    logger.info("init() 返回: %s", ret)

    t = threading.Thread(target=api.join_async, daemon=True, name="xt-net")
    t.start()

    logger.info("等待账号登录就绪（最多 %.0f 秒）...", LOGIN_TIMEOUT)
    fired = result["done"].wait(timeout=LOGIN_TIMEOUT)

    if not fired:
        logger.error("超时：账号未在 %.0f 秒内就绪", LOGIN_TIMEOUT)
    else:
        v = result["available"]
        if v is not None:
            print(f"\n>>> 账号 {TARGET_ACCT} 可用资金：{v:,.2f} 元\n")
        else:
            print("\n>>> 查询失败，请查看上方日志\n")

    try:
        api.release()
    except Exception:
        pass


if __name__ == "__main__":
    main()
