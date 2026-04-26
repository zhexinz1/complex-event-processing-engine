#!/usr/bin/env python3
"""测试查询订单并打印所有属性"""

import sys
sys.path.append("/home/ubuntu/minitrader/userdata_mini/sdk")

from XtTraderPyApi import *
import time

class TestCallback(XtTraderApiCallback):
    def __init__(self):
        super().__init__()
        self._connected = False
        self._login_success = False
        self._account_key = None

    def onConnected(self, success, error_msg):
        print(f"连接回调: success={success}, error_msg={error_msg}")
        self._connected = success

    def onRtnLoginStatusWithActKey(self, account_id, status, account_key):
        print(f"账号登录状态: account_id={account_id}, status={status}, account_key={account_key}")
        if status == EBrokerLoginStatus.BROKER_LOGIN_STATUS_SUCCESS:
            self._login_success = True
            self._account_key = account_key

def main():
    # 配置
    server_addr = "8.166.130.204:65300"
    username = "90102870"
    password = "Aa123456"
    app_id = "xt_api_2.0"
    auth_code = "7f3c92e678f9ec77"
    account_id = "90102870"

    # 创建 API
    api = XtTraderApi.createXtTraderApi(server_addr)
    callback = TestCallback()
    api.setCallback(callback)

    # 初始化
    result = api.init("../config")
    print(f"API 初始化: {result}")

    # 等待连接
    print("等待连接...")
    for i in range(10):
        if callback._connected:
            break
        time.sleep(1)

    if not callback._connected:
        print("连接失败")
        return

    # 同步登录
    print("开始登录...")
    error = api.userLoginSync(username, password, "", app_id, auth_code)
    if not error.isSuccess():
        print(f"登录失败: {error.errorMsg()}")
        return

    print("同步登录成功")

    # 等待账号就绪
    print("等待账号就绪...")
    for i in range(30):
        if callback._login_success and callback._account_key:
            break
        time.sleep(1)

    if not callback._account_key:
        print("账号未就绪")
        return

    print(f"账号就绪，account_key={callback._account_key}")
    time.sleep(2)

    # 查询订单
    print(f"\n查询账号 {account_id} 的订单...")
    error = XtError(0, "")
    orders = api.reqOrderDetailSync(account_id, error, callback._account_key)

    if not error.isSuccess():
        print(f"查询失败: {error.errorMsg()}")
        return

    print(f"\n查询成功，共 {len(orders)} 笔订单")

    if len(orders) > 0:
        print("\n第一笔订单的所有属性:")
        order = orders[0]
        print(f"订单对象类型: {type(order)}")
        print(f"\n所有属性:")
        for attr in dir(order):
            if not attr.startswith('_'):
                try:
                    value = getattr(order, attr)
                    print(f"  {attr}: {value}")
                except Exception as e:
                    print(f"  {attr}: <无法访问: {e}>")
    else:
        print("没有订单")

    time.sleep(2)

if __name__ == "__main__":
    main()
