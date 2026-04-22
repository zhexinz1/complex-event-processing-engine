"""
测试净入金流程的完整端到端测试
"""
from decimal import Decimal
from database.dao import DatabaseDAO
from rebalance.rebalance_engine import RebalanceEngine

# 数据库配置
DB_CONFIG = {
    'host': '120.25.245.137',
    'port': 23306,
    'user': 'cx',
    'password': 'cC3z#,2?od)gn7Nhd2L1',
    'database': 'fof'
}

def test_fund_inflow_flow():
    """测试净入金完整流程"""
    print("=" * 60)
    print("测试净入金流程")
    print("=" * 60)

    # 1. 初始化 DAO
    dao = DatabaseDAO(**DB_CONFIG)
    print("\n✅ 数据库连接成功")

    # 2. 查询产品配置
    product = dao.get_product_by_name("产品A")
    if not product:
        print("❌ 产品A不存在")
        return

    print(f"\n📦 产品信息:")
    print(f"  - 产品名称: {product.product_name}")
    print(f"  - 杠杆倍数: {product.leverage_ratio}")
    print(f"  - 关联账号: {product.account_id}")

    # 3. 模拟目标权重配置
    target_weights = {
        'AU2609': Decimal('0.25'),  # 黄金 25%
        'AG2609': Decimal('0.75')   # 白银 75%
    }

    # 4. 模拟市场价格（实际应从行情网关获取）
    market_prices = {
        'AU2609': Decimal('450.50'),
        'AG2609': Decimal('5200.00')
    }

    contract_multipliers = {
        'AU2609': 1000,
        'AG2609': 15
    }

    # 5. 获取留白数据
    previous_fractionals = {
        'AU2609': dao.get_fractional_share("产品A", "AU2609"),
        'AG2609': dao.get_fractional_share("产品A", "AG2609")
    }

    print(f"\n💰 净入金: 1,000,000 元")
    print(f"📊 杠杆倍数: {product.leverage_ratio}")
    print(f"💵 杠杆后金额: {1000000 * product.leverage_ratio:,.2f} 元")

    # 6. 计算增量订单
    engine = RebalanceEngine()
    orders = engine.calculate_incremental_orders(
        net_inflow=Decimal('1000000'),
        leverage_ratio=product.leverage_ratio,
        target_weights=target_weights,
        market_prices=market_prices,
        contract_multipliers=contract_multipliers,
        previous_fractionals=previous_fractionals
    )

    print(f"\n📋 计算结果:")
    print("-" * 60)
    for order in orders:
        print(f"\n合约: {order.asset_code}")
        print(f"  目标市值: {order.target_market_value:,.2f} 元")
        print(f"  价格: {order.price}")
        print(f"  合约乘数: {order.contract_multiplier}")
        print(f"  理论手数: {order.theoretical_quantity:.6f}")
        print(f"  四舍五入: {order.rounded_quantity} 手")
        print(f"  留白: {order.fractional_part:.6f}")
        print(f"  上次留白: {order.previous_fractional:.6f}")
        print(f"  最终手数: {order.final_quantity} 手")

    # 7. 更新留白数据（模拟）
    print(f"\n💾 更新留白数据:")
    for order in orders:
        dao.update_fractional_share(
            product_name="产品A",
            asset_code=order.asset_code,
            fractional_amount=order.fractional_part
        )
        print(f"  {order.asset_code}: {order.fractional_part:.6f}")

    print("\n" + "=" * 60)
    print("✅ 测试完成")
    print("=" * 60)

if __name__ == '__main__':
    test_fund_inflow_flow()
