"""
测试迅投下单服务
"""

import sys
import os
import logging

sys.path.insert(0, '/home/ubuntu/xt_sdk')
os.environ['LD_LIBRARY_PATH'] = '/home/ubuntu/xt_sdk:' + os.environ.get('LD_LIBRARY_PATH', '')

from adapters.xt_order_service import XtOrderService, OrderRequest, OrderDirection, OrderPriceType

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)


def test_place_order():
    """测试下单功能"""

    # 创建服务实例
    service = XtOrderService()

    # 连接服务器
    logger.info("正在连接迅投服务器...")
    if not service.connect(timeout=30.0):
        logger.error("连接失败")
        return

    logger.info("连接成功，准备下单...")

    # 构造下单请求（测试单：开多 1 手 IF2504 股指期货）
    order_req = OrderRequest(
        account_id="90102870",
        asset_code="IF2504.CFFEX",  # 沪深300股指期货，中金所
        direction=OrderDirection.OPEN_LONG,
        quantity=1,
        price=3800.0,
        price_type=OrderPriceType.LIMIT
    )

    # 执行下单
    result = service.place_order(order_req, timeout=10.0)

    if result.success:
        logger.info("✅ 下单成功！订单号: %d", result.order_id)
    else:
        logger.error("❌ 下单失败: %s", result.error_msg)

    # 断开连接
    service.disconnect()


if __name__ == "__main__":
    test_place_order()
