"""
测试实际下单功能（小数量测试）
"""
import sys
import os
sys.path.insert(0, '/home/ubuntu/xt_sdk')
os.environ['LD_LIBRARY_PATH'] = '/home/ubuntu/xt_sdk:' + os.environ.get('LD_LIBRARY_PATH', '')

from decimal import Decimal
from database.dao import DatabaseDAO
from database.models import PendingOrder, OrderStatus
from adapters.xuntou import get_xt_connection_manager
from adapters.xuntou import OrderRequest, OrderDirection, OrderPriceType
import uuid
import time

# 数据库配置
DB_CONFIG = {
    'host': '120.25.245.137',
    'port': 23306,
    'user': 'cx',
    'password': 'cC3z#,2?od)gn7Nhd2L1',
    'database': 'fof'
}

def test_real_order():
    """测试实际下单"""
    print("=== 测试实际下单功能 ===\n")

    dao = DatabaseDAO(**DB_CONFIG)

    # 1. 获取产品配置
    product_name = "测试产品D"
    product = dao.get_product_by_name(product_name)

    if not product or not product.xt_username or not product.xt_password:
        print("✗ 产品配置不完整")
        return

    print(f"产品: {product.product_name}")
    print(f"账号: {product.account_id}")
    print(f"用户: {product.xt_username}\n")

    # 2. 连接迅投
    print("连接迅投...")
    manager = get_xt_connection_manager()
    xt_service = manager.get_connection(
        username=product.xt_username,
        password=product.xt_password,
        account_id=product.account_id,
        timeout=30.0
    )

    if not xt_service:
        print("✗ 连接失败")
        return

    print(f"✓ 连接成功\n")

    # 3. 创建测试订单
    batch_id = str(uuid.uuid4())
    test_order = PendingOrder(
        id=None,
        batch_id=batch_id,
        product_name=product.product_name,
        asset_code="IF2504.CFFEX",  # 中金所期货
        target_market_value=Decimal("100000.00"),
        price=Decimal("3500.00"),
        contract_multiplier=300,
        theoretical_quantity=Decimal("0.095"),
        rounded_quantity=0,
        fractional_part=Decimal("0.095"),
        final_quantity=1,  # 买入1手
        status=OrderStatus.PENDING
    )

    order_id = dao.create_pending_order(test_order)
    print(f"创建订单 ID: {order_id}")
    print(f"合约: {test_order.asset_code}")
    print(f"数量: {test_order.final_quantity}\n")

    # 4. 执行下单
    print("执行下单...")

    orders = dao.get_pending_orders_by_batch(batch_id)
    executed_orders = []
    failed_orders = []

    for order in orders:
        if order.final_quantity == 0:
            continue

        try:
            # 解析资产代码
            parts = order.asset_code.split('.')
            instrument, market = parts[0], parts[1]

            # 判断方向
            if order.final_quantity > 0:
                direction = OrderDirection.OPEN_LONG  # 期货开多
                quantity = order.final_quantity
            else:
                direction = OrderDirection.CLOSE_LONG  # 期货平多
                quantity = abs(order.final_quantity)

            # 构造订单请求
            order_req = OrderRequest(
                account_id=product.account_id,
                asset_code=order.asset_code,
                direction=direction,
                quantity=quantity,
                price=float(order.price),
                price_type=OrderPriceType.LIMIT,
                market=market,
                instrument=instrument
            )

            print(f"下单参数:")
            print(f"  账号: {order_req.account_id}")
            print(f"  合约: {order_req.asset_code}")
            print(f"  方向: {order_req.direction.value}")
            print(f"  数量: {order_req.quantity}")
            print(f"  价格: {order_req.price}")
            print(f"  市场: {order_req.market}")
            print(f"  代码: {order_req.instrument}\n")

            # 实际下单
            result = xt_service.place_order(order_req)

            if result.success:
                print(f"✓ 下单成功")
                print(f"  订单ID: {result.order_id}")
                dao.update_order_status(order.id, OrderStatus.EXECUTED)
                executed_orders.append(order.asset_code)
            else:
                print(f"✗ 下单失败: {result.error_msg}")
                dao.update_order_status(order.id, OrderStatus.FAILED, result.error_msg)
                failed_orders.append({"asset_code": order.asset_code, "error": result.error_msg})

        except Exception as e:
            print(f"✗ 异常: {e}")
            dao.update_order_status(order.id, OrderStatus.FAILED, str(e))
            failed_orders.append({"asset_code": order.asset_code, "error": str(e)})

    # 5. 总结
    print(f"\n=== 测试完成 ===")
    print(f"成功: {len(executed_orders)}")
    print(f"失败: {len(failed_orders)}")

    if failed_orders:
        print("\n失败详情:")
        for f in failed_orders:
            print(f"  {f['asset_code']}: {f['error']}")

if __name__ == "__main__":
    test_real_order()
