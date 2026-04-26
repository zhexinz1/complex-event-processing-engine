"""最简化测试：不调用 userLogin，看看是否会自动触发账号状态回调"""
import sys
import os
import threading
import logging
import time

sys.path.insert(0, '/home/ubuntu/xt_sdk')
os.environ['LD_LIBRARY_PATH'] = '/home/ubuntu/xt_sdk:' + os.environ.get('LD_LIBRARY_PATH', '')

from XtTraderPyApi import XtTraderApi, XtTraderApiCallback, XtError, EBrokerLoginStatus

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

SERVER_ADDR = "8.166.130.204:63500"
CONFIG_PATH = "/home/ubuntu/xt_sdk/config"
done = threading.Event()

class CB(XtTraderApiCallback):
    def __init__(self, api):
        super().__init__()
        self._api = api

    def onConnected(self, success, error_msg):
        logger.info("onConnected: success=%s, msg=%s", success, error_msg)
        if success:
            logger.info("连接成功，不调用 userLogin，等待自动推送...")

    def onDisconnected(self, reason):
        logger.warning("onDisconnected: reason=%d", reason)

    def onRtnLoginStatus(self, account_id, status, account_type, error_msg):
        logger.info("onRtnLoginStatus: account_id=%s, status=%s, account_type=%s, error_msg=%s",
                   account_id, status, account_type, error_msg)

    def onRtnLoginStatusWithActKey(self, account_id, status, account_type, account_key, error_msg):
        logger.info("onRtnLoginStatusWithActKey: account_id=%s, status=%s, account_type=%s, account_key=%s, error_msg=%s",
                   account_id, status, account_type, account_key, error_msg)
        done.set()

def main():
    api = XtTraderApi.createXtTraderApi(SERVER_ADDR)
    if api is None:
        logger.error("创建 API 实例失败")
        return

    cb = CB(api)
    api.setCallback(cb)
    ret = api.init(CONFIG_PATH)
    logger.info("init() 返回: %s", ret)

    t = threading.Thread(target=api.join_async, daemon=True)
    t.start()

    logger.info("等待 30 秒...")
    fired = done.wait(timeout=30)

    if fired:
        logger.info("收到账号状态回调！")
    else:
        logger.error("30 秒内未收到任何账号状态回调")

    try:
        api.release()
    except Exception:
        pass

if __name__ == "__main__":
    main()
