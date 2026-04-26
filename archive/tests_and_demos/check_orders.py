#!/usr/bin/env python3
"""查询数据库中的订单记录"""

import pymysql
from datetime import datetime

# 数据库连接配置
DB_CONFIG = {
    'host': '120.25.245.137',
    'port': 23306,
    'user': 'cx',
    'password': 'cC3z#,2?od)gn7Nhd2L1',
    'database': 'fof',
    'charset': 'utf8mb4',
}

def main():
    conn = pymysql.connect(**DB_CONFIG)
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            # 查询最近的订单
            sql = """
                SELECT * FROM pending_orders
                ORDER BY created_at DESC
                LIMIT 10
            """
            cursor.execute(sql)
            orders = cursor.fetchall()

            print(f"\n最近的 {len(orders)} 笔订单:")
            print("=" * 120)

            for order in orders:
                print(f"\nID: {order['id']}")
                print(f"  批次ID: {order['batch_id']}")
                print(f"  产品: {order['product_name']}")
                print(f"  合约: {order['asset_code']}")
                print(f"  数量: {order['final_quantity']}")
                print(f"  价格: {order['price']}")
                print(f"  状态: {order['status']}")
                print(f"  创建时间: {order['created_at']}")
                print(f"  确认时间: {order.get('confirmed_at', 'N/A')}")
                if 'confirmed_by' in order:
                    print(f"  确认人: {order['confirmed_by']}")

            # 查询最近的净入金记录
            print("\n\n最近的净入金记录:")
            print("=" * 120)

            sql = """
                SELECT * FROM fund_inflows
                ORDER BY created_at DESC
                LIMIT 5
            """
            cursor.execute(sql)
            inflows = cursor.fetchall()

            for inflow in inflows:
                print(f"\nID: {inflow['id']}")
                print(f"  批次ID: {inflow['batch_id']}")
                print(f"  产品: {inflow['product_name']}")
                print(f"  净入金: {inflow['net_inflow']}")
                print(f"  杠杆倍数: {inflow['leverage_ratio']}")
                print(f"  状态: {inflow['status']}")
                print(f"  创建时间: {inflow['created_at']}")

    finally:
        conn.close()

if __name__ == '__main__':
    main()
