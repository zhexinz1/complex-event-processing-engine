"""
测试小写合约代码下单
"""
import sys
import os
import time

sys.path.insert(0, '/home/ubuntu/xt_sdk')
os.environ['LD_LIBRARY_PATH'] = '/home/ubuntu/xt_sdk:' + os.environ.get('LD_LIBRARY_PATH', '')

from XtTraderPyApi import (
    XtTraderApi,
    XtTraderApiCallback,
    XtError,
    EBrokerLoginStatus,
    COrdinaryOrder,
    EPriceType,
    EOperationType,
)


class TestCallback(XtTraderApiCallback):
    def __init__(self, api, username, password, app_id, auth_code):
        super().__init__()
        self._api = api
        self._username = username
        self._password = password
        self._app_id = app_id
        self._auth_code = auth_code
        self._account_key = None
        self._login_success = False

    def onConnected(self, success, error_msg):
        print(f"连接回调: success={success}, error_msg={error_msg}")
        if success:
            error = self._api.userLoginSync(
                self._username, self._password, "", self._app_id, self._auth_code
            )
            if error.isSuccess():
                print("同步登录成功")
            else:
                print(f"同步登录失败: {error.errorMsg()}")

    def onRtnLoginStatusWithActKey(self, account_id, status, account_type, account_key, error_msg):
        print(f"账号登录状态: account_id={account_id}, status={status}")
        if status == EBrokerLoginStatus.BROKER_LOGIN_STATUS_OK:
            self._account_key = account_key
            self._login_success = True

    def onOrderEvent(self, order_event, error):
        """订单回报"""
        if error.isSuccess():
            print(f"*** 订单回报: order_id={order_event.m_nOrderID}, status={order_event.m_nOrderStatus} ***")
        else:
            print(f"*** 订单回报错误: {error.errorMsg()} ***")

    def onTradeEvent(self, trade_event, error):
        """成交回报"""
        if error.isSuccess():
            print(f"*** 成交回报: order_id={trade_event.m_nOrderID} ***")
        else:
            print(f"*** 成交回报错误: {error.errorMsg()} ***")


def main():
    # 配置
    server_addr = "8.166.130.204:65300"
    username = "system_trade"
    password = "my123456@"
    config_path = "/home/ubuntu/xt_sdk/config"
    app_id = "xt_api_2.0"
    auth_code = "7f3c92e678f9ec77"
    account_id = "90102870"

    # 创建 API
    api = XtTraderApi.createXtTraderApi(server_addr)
    if api is None:
        print("创建 API 失败")
        return

    # 创建回调
    callback = TestCallback(api, username, password, app_id, auth_code)
    api.setCallback(callback)

    # 初始化
    init_result = api.init(config_path)
    print(f"API 初始化: {init_result}")

    # 启动网络循环（非阻塞）
    import threading
    network_thread = threading.Thread(target=api.join_async, daemon=True)
    network_thread.start()

    # 等待登录成功
    print("等待登录...")
    for i in range(30):
        if callback._login_success:
            break
        time.sleep(1)
    else:
        print("登录超时")
        return

    print(f"登录成功，account_key={callback._account_key}")
    time.sleep(2)

    # 下单 - 使用小写合约代码
    print("\n=== 下单（小写合约代码 ag2606）===")
    order1 = COrdinaryOrder()
    order1.m_strAccountID = account_id
    order1.m_strInstrument = "ag2606"  # 小写！
    order1.m_strMarket = "SHFE"
    order1.m_nVolume = 1
    order1.m_dPrice = 7145.0
    order1.m_ePriceType = EPriceType.PRTP_FIX
    order1.m_eOperationType = EOperationType.OPT_OPEN_LONG

    error1 = XtError(0, "")
    order_id1 = api.orderSync(order1, error1)
    print(f"结果: order_id={order_id1}, success={error1.isSuccess()}, error={error1.errorMsg()}")

    print("\n等待订单回报（10秒）...")
    time.sleep(10)

    # 查询订单
    print("\n=== 查询所有订单 ===")
    error2 = XtError(0, "")
    orders = api.reqOrderDetailSync(account_id, error2, callback._account_key)
    if error2.isSuccess():
        print(f"共 {len(orders)} 笔委托:")
        for order in orders:
            print(f"  订单ID={order.m_nOrderID}, 合约={order.m_strInstrument}.{order.m_strMarket}")
    else:
        print(f"查询失败: {error2.errorMsg()}")

    # 查询持仓
    print("\n=== 查询持仓 ===")
    error3 = XtError(0, "")
    positions = api.reqPositionDetailSync(account_id, error3, callback._account_key)
    if error3.isSuccess():
        print(f"共 {len(positions)} 个持仓:")
        for pos in positions:
            print(f"  {pos.m_strInstrumentID} ({pos.m_strExchangeID}): 数量={pos.m_nVolume}, 方向={pos.m_nDirection}")
    else:
        print(f"查询失败: {error3.errorMsg()}")

    time.sleep(2)


if __name__ == "__main__":
    main()
