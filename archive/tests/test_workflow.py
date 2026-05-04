"""
测试完整业务流程
"""

import requests

API_BASE = "http://localhost:5000/api"

def test_workflow():
    print("=" * 60)
    print("测试完整业务流程")
    print("=" * 60)

    # 1. 查询迅投产品列表
    print("\n1. 查询迅投产品列表")
    resp = requests.get(f"{API_BASE}/xt/products")
    data = resp.json()
    print(f"   成功: {data['success']}")
    if data['success']:
        for prod in data['products']:
            print(f"   - {prod['product_name']} (ID: {prod['product_id']}, 代码: {prod['product_code']}, 净值: {prod['total_net_value']:.2f})")

    # 2. 查询已添加的产品
    print("\n2. 查询产品管理中的产品")
    resp = requests.get(f"{API_BASE}/products/list")
    data = resp.json()
    print(f"   成功: {data['success']}")
    if data['success']:
        for prod in data['products']:
            print(f"   - {prod['product_name']} (杠杆: {prod['leverage_ratio']}x, 账号: {prod['account_id']})")

    # 3. 查询目标权重配置
    print("\n3. 查询目标权重配置")
    resp = requests.get(f"{API_BASE}/weights")
    data = resp.json()
    print(f"   成功: {data['success']}, 总数: {data['total']}")
    if data['success'] and data['data']:
        for weight in data['data']:
            print(f"   - {weight['product_name']}: {weight['asset_code']} = {weight['weight_ratio']*100:.2f}%")

    # 4. 测试净入金流程（使用产品A）
    print("\n4. 测试净入金流程")
    product_name = "产品A"
    net_inflow = 100000.0

    print(f"   产品: {product_name}")
    print(f"   净入金: {net_inflow:.2f} 元")

    payload = {
        "product_name": product_name,
        "net_inflow": net_inflow,
        "input_by": "测试用户"
    }

    resp = requests.post(f"{API_BASE}/fund/inflow", json=payload)
    data = resp.json()

    print(f"   成功: {data['success']}")
    if data['success']:
        print(f"   批次ID: {data['batch_id']}")
        print(f"   杠杆倍数: {data['leverage_ratio']}x")
        print(f"   杠杆后金额: {data['leveraged_amount']:.2f} 元")
        print(f"   计算的订单数: {len(data['orders'])}")
        for order in data['orders']:
            print(f"   - {order['asset_code']}: 最终数量 {order['final_quantity']} 手 @ {order['price']:.2f} (理论: {order['theoretical_quantity']:.4f})")
    else:
        print(f"   错误: {data.get('message', '未知错误')}")

    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)

if __name__ == "__main__":
    test_workflow()
