"""
测试账号就绪状态
"""
import sys
import os
sys.path.insert(0, '/home/ubuntu/xt_sdk')
os.environ['LD_LIBRARY_PATH'] = '/home/ubuntu/xt_sdk:' + os.environ.get('LD_LIBRARY_PATH', '')

from database.dao import DatabaseDAO
from adapters.xt_connection_manager import get_xt_connection_manager
import time

DB_CONFIG = {
    'host': '120.25.245.137',
    'port': 23306,
    'user': 'cx',
    'password': 'cC3z#,2?od)gn7Nhd2L1',
    'database': 'fof'
}

def test_account_ready():
    """测试账号就绪状态"""
    print("=== 测试账号就绪状态 ===\n")

    dao = DatabaseDAO(**DB_CONFIG)
    product = dao.get_product_by_name("测试产品D")

    if not product:
        print("✗ 产品不存在")
        return

    print(f"产品: {product.product_name}")
    print(f"账号: {product.account_id}")
    print(f"用户: {product.xt_username}\n")

    # 连接
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

    print(f"✓ 连接成功")
    print(f"登录状态: {xt_service._logined}\n")

    # 等待账号就绪
    print("等待账号就绪...")
    for i in range(10):
        time.sleep(1)
        account_key = xt_service._account_ready.get(product.account_id)
        if account_key:
            print(f"✓ 账号就绪")
            print(f"  账号ID: {product.account_id}")
            print(f"  account_key: {account_key}")
            break
        else:
            print(f"  等待中... ({i+1}/10)")
    else:
        print(f"✗ 账号未就绪")
        print(f"  当前就绪账号: {list(xt_service._account_ready.keys())}")

    print("\n=== 测试完成 ===")

if __name__ == "__main__":
    test_account_ready()
