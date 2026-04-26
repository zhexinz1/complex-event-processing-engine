"""
测试查询合约信息
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

    # 查询持仓
    print("\n=== 查询持仓 ===")
    error1 = XtError(0, "")
    positions = api.reqPositionSync(account_id, error1, callback._account_key)
    if error1.isSuccess():
        print(f"共 {len(positions)} 个持仓:")
        for pos in positions:
            print(f"  合约: {pos.m_strInstrument}.{pos.m_strMarket}")
            print(f"    数量: {pos.m_nVolume}")
            print(f"    可用: {pos.m_nCanCloseVolume}")
    else:
        print(f"查询失败: {error1.errorMsg()}")

    # 查询资金
    print("\n=== 查询资金 ===")
    error2 = XtError(0, "")
    assets = api.reqAccountDetailSync(account_id, error2, callback._account_key)
    if error2.isSuccess():
        print(f"共 {len(assets)} 个资金账户:")
        for asset in assets:
            print(f"  账号: {asset.m_strAccountID}")
            print(f"    总资产: {asset.m_dBalance}")
            print(f"    可用: {asset.m_dAvailable}")
    else:
        print(f"查询失败: {error2.errorMsg()}")

    time.sleep(2)


if __name__ == "__main__":
    main()
