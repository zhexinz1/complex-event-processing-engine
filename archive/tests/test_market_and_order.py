"""
测试行情查询和下单成交
"""

import sys
import os
import logging
import time
import threading

sys.path.insert(0, '/home/ubuntu/xt_sdk')
os.environ['LD_LIBRARY_PATH'] = '/home/ubuntu/xt_sdk:' + os.environ.get('LD_LIBRARY_PATH', '')

from cep.core.event_bus import EventBus
from cep.core.events import TickEvent
from adapters.market_gateway import CTPMarketGateway
from adapters.xt_order_service import XtOrderService, OrderRequest, OrderDirection, OrderPriceType

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

# CTP 行情配置
FRONT_ADDR = "tcp://218.17.194.115:41413"
BROKER_ID = "8060"
USER_ID = "99683265"
PASSWORD = "456123"

# 迅投下单配置
ACCOUNT_ID = "90102870"

# 行情数据容器
market_data = {"tick": None, "done": threading.Event()}


def on_tick(event: TickEvent) -> None:
    """行情回调"""
    if event.symbol == "au2606":
        logger.info("收到 au2606 行情: last=%.2f, bid1=%.2f/%d, ask1=%.2f/%d",
                   event.last_price,
                   event.bid_prices[0], event.bid_volumes[0],
                   event.ask_prices[0], event.ask_volumes[0])
        market_data["tick"] = event
        market_data["done"].set()


def get_market_data(symbol="au2606", timeout=30.0):
    """获取行情数据"""
    bus = EventBus()
    bus.subscribe(TickEvent, on_tick, symbol="")

    gw = CTPMarketGateway(
        event_bus=bus,
        front_addr=FRONT_ADDR,
        broker_id=BROKER_ID,
        user_id=USER_ID,
        password=PASSWORD,
        flow_path="./ctp_flow/",
    )

    logger.info("正在连接 CTP 行情...")
    if not gw.connect():
        logger.error("连接失败")
        return None

    logger.info("订阅合约: %s", symbol)
    gw.subscribe([symbol])

    logger.info("等待行情推送（最多 %.0f 秒）...", timeout)
    if not market_data["done"].wait(timeout=timeout):
        logger.error("获取行情超时")
        gw.disconnect()
        return None

    gw.disconnect()
    return market_data["tick"]


def main():
    """主流程：获取行情 -> 下单成交"""

    # 1. 获取 au2606 行情
    logger.info("=" * 60)
    logger.info("步骤 1: 获取 au2606 黄金期货行情")
    logger.info("=" * 60)

    tick = get_market_data("au2606", timeout=30.0)

    if tick is None:
        logger.error("无法获取行情，退出")
        return

    logger.info("\n=== au2606 行情信息 ===")
    logger.info("最新价: %.2f", tick.last_price)
    logger.info("买一价: %.2f (量: %d)", tick.bid_prices[0], tick.bid_volumes[0])
    logger.info("卖一价: %.2f (量: %d)", tick.ask_prices[0], tick.ask_volumes[0])

    # 2. 下单策略：如果卖一价为0，用买一价+0.02下单
    logger.info("\n" + "=" * 60)
    logger.info("步骤 2: 下单买入")
    logger.info("=" * 60)

    # 判断使用哪个价格
    if tick.ask_prices[0] > 0:
        order_price = tick.ask_prices[0]
        logger.info("使用卖一价: %.2f", order_price)
    else:
        order_price = tick.bid_prices[0] + 0.02
        logger.info("卖一价为0，使用买一价+0.02: %.2f", order_price)

    # 等待一下
    time.sleep(2)

    # 创建下单服务
    order_service = XtOrderService()

    logger.info("连接下单服务...")
    if not order_service.connect(timeout=30.0):
        logger.error("连接下单服务失败")
        return

    order_req = OrderRequest(
        account_id=ACCOUNT_ID,
        asset_code="au2606.SHFE",
        direction=OrderDirection.OPEN_LONG,
        quantity=1,
        price=order_price,
        price_type=OrderPriceType.LIMIT
    )

    logger.info("下单参数: 合约=au2606, 方向=开多, 数量=1手, 价格=%.2f", order_price)

    result = order_service.place_order(order_req, timeout=10.0)

    if result.success:
        logger.info("\n✅ 下单成功！")
        logger.info("订单号: %d", result.order_id)
        logger.info("下单价格: %.2f", order_price)
    else:
        logger.error("\n❌ 下单失败: %s", result.error_msg)

    order_service.disconnect()

    logger.info("\n" + "=" * 60)
    logger.info("测试完成")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
