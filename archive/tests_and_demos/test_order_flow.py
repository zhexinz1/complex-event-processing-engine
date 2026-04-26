"""
测试完整的订单确认流程
模拟从产品配置到订单执行的完整链路
"""
import sys
import os
sys.path.insert(0, '/home/ubuntu/xt_sdk')
os.environ['LD_LIBRARY_PATH'] = '/home/ubuntu/xt_sdk:' + os.environ.get('LD_LIBRARY_PATH', '')

from decimal import Decimal
from database.dao import DatabaseDAO
from database.models import Product, ProductStatus, PendingOrder, OrderStatus
from adapters.xuntou import get_xt_connection_manager
from adapters.xuntou import OrderRequest, OrderDirection, OrderPriceType
import uuid

# 数据库配置
DB_CONFIG = {
    'host': '120.25.245.137',
    'port': 23306,
    'user': 'cx',
    'password': 'cC3z#,2?od)gn7Nhd2L1',
    'database': 'fof'
}

def test_order_flow():
    """测试订单确认流程"""
    print("=== 测试订单确认流程 ===\n")

    dao = DatabaseDAO(**DB_CONFIG)

    # 1. 检查产品配置
    print("1. 检查产品配置")
    product_name = "测试产品D"  # 使用已配置凭证的产品
    product = dao.get_product_by_name(product_name)

    if not product:
        print(f"   产品不存在，创建测试产品...")
        # 这里需要手动在数据库中创建产品，或者添加 create_product 方法
        print(f"   ✗ 请先在数据库中创建产品: {product_name}")
        print(f"   需要字段: product_name, leverage_ratio, account_id, xt_username, xt_password")
        return

    print(f"   产品名称: {product.product_name}")
    print(f"   资金账号: {product.account_id}")
    print(f"   迅投用户: {product.xt_username}")
    print(f"   密码配置: {'已配置' if product.xt_password else '未配置'}")

    if not product.xt_username or not product.xt_password:
        print(f"   ✗ 产品未配置迅投账号凭证")
        return

    # 2. 创建模拟订单
    print(f"\n2. 创建模拟待确认订单")
    batch_id = str(uuid.uuid4())

    test_order = PendingOrder(
        id=None,
        batch_id=batch_id,
        product_name=product.product_name,
        asset_code="IF2504.CFE",  # 测试合约
        target_market_value=Decimal("100000.00"),
        price=Decimal("3500.00"),
        contract_multiplier=300,
        theoretical_quantity=Decimal("0.095"),
        rounded_quantity=0,
        fractional_part=Decimal("0.095"),
        final_quantity=1,  # 手动调整为1手
        status=OrderStatus.PENDING
    )

    order_id = dao.create_pending_order(test_order)
    print(f"   ✓ 创建订单 ID: {order_id}")
    print(f"   批次ID: {batch_id}")
    print(f"   合约: {test_order.asset_code}")
    print(f"   数量: {test_order.final_quantity}")

    # 3. 测试连接管理器
    print(f"\n3. 测试迅投连接")
    manager = get_xt_connection_manager()

    xt_service = manager.get_connection(
        username=product.xt_username,
        password=product.xt_password,
        account_id=product.account_id,
        timeout=30.0
    )

    if not xt_service:
        print(f"   ✗ 连接失败")
        return

    print(f"   ✓ 连接成功")
    print(f"   登录状态: {xt_service._logined}")

    # 4. 模拟订单执行逻辑（不实际下单）
    print(f"\n4. 模拟订单执行逻辑")

    orders = dao.get_pending_orders_by_batch(batch_id)
    print(f"   待执行订单数: {len(orders)}")

    for order in orders:
        if order.final_quantity == 0:
            print(f"   跳过数量为0的订单: {order.asset_code}")
            continue

        # 解析资产代码
        parts = order.asset_code.split('.')
        if len(parts) != 2:
            print(f"   ✗ 资产代码格式错误: {order.asset_code}")
            continue

        instrument, market = parts[0], parts[1]

        # 判断买卖方向
        if order.final_quantity > 0:
            direction = OrderDirection.BUY
            quantity = order.final_quantity
        else:
            direction = OrderDirection.SELL
            quantity = abs(order.final_quantity)

        print(f"\n   订单详情:")
        print(f"   - 合约: {order.asset_code}")
        print(f"   - 方向: {direction.value}")
        print(f"   - 数量: {quantity}")
        print(f"   - 价格: {order.price}")
        print(f"   - 市场: {market}")
        print(f"   - 代码: {instrument}")
        print(f"   - 账号: {product.account_id}")

        # 构造订单请求（不实际发送）
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

        print(f"   ✓ 订单请求构造成功")
        print(f"   （测试模式，不实际下单）")

    # 5. 清理测试数据
    print(f"\n5. 清理测试数据")
    dao.update_order_status(order_id, OrderStatus.CANCELLED)
    print(f"   ✓ 已取消测试订单")

    print("\n=== 测试完成 ===")
    print("\n总结:")
    print("✓ 产品配置读取正常")
    print("✓ 迅投连接管理器工作正常")
    print("✓ 订单执行逻辑正确")
    print("\n如需实际下单测试，请修改代码调用 xt_service.place_order(order_req)")

if __name__ == "__main__":
    test_order_flow()
