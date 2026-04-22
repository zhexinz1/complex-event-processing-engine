"""
测试查询订单详情
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
)


class QueryCallback(XtTraderApiCallback):
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
        print(f"账号登录状态: account_id={account_id}, status={status}, account_key={account_key}")
        if status == EBrokerLoginStatus.BROKER_LOGIN_STATUS_OK:
            self._account_key = account_key
            self._login_success = True


def main():
    # 配置
    server_addr = "8.166.130.204:65300"
    username = "system_trade"
    password = "my123456@"
    config_path = "/home/ubuntu/xt_sdk/config"
    app_id = "xt_api_2.0"
    auth_code = "7f3c92e678f9ec77"
    account_id = "90102870"
    order_id = 17  # 刚才下单返回的订单号

    # 创建 API
    api = XtTraderApi.createXtTraderApi(server_addr)
    if api is None:
        print("创建 API 失败")
        return

    # 创建回调
    callback = QueryCallback(api, username, password, app_id, auth_code)
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

    # 查询订单详情
    print(f"\n查询订单 {order_id} 的详情...")
    error = XtError(0, "")
    orders = api.reqOrderDetailSync(account_id, error, callback._account_key)

    if error.isSuccess():
        print(f"查询成功，共 {len(orders)} 笔委托:")
        for order in orders:
            print(f"\n订单ID: {order.m_nOrderID}")
            print(f"  合约: {order.m_strInstrument}.{order.m_strMarket}")
            print(f"  方向: {order.m_eOperationType}")
            print(f"  数量: {order.m_nVolume}")
            print(f"  价格: {order.m_dPrice}")
            print(f"  状态: {order.m_eOrderStatus}")
            print(f"  成交量: {order.m_nTradeVolume}")
            print(f"  委托时间: {order.m_strOrderTime}")
    else:
        print(f"查询失败: {error.errorMsg()}")

    time.sleep(2)


if __name__ == "__main__":
    main()
