"""
更新产品配置，添加迅投账号凭证
"""
import pymysql

DB_CONFIG = {
    'host': '120.25.245.137',
    'port': 23306,
    'user': 'cx',
    'password': 'cC3z#,2?od)gn7Nhd2L1',
    'database': 'fof',
    'charset': 'utf8mb4'
}

def update_product_credentials():
    """更新产品的迅投账号凭证"""
    conn = pymysql.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cursor:
            print("=== 更新产品迅投账号凭证 ===\n")

            # 更新测试产品D（使用真实的迅投账号）
            product_name = "测试产品D"
            xt_username = "system_trade"
            xt_password = "my123456@"
            account_id = "100000002"  # 真实的资金账号

            print(f"更新产品: {product_name}")
            cursor.execute("""
                UPDATE products
                SET xt_username = %s,
                    xt_password = %s,
                    account_id = %s
                WHERE product_name = %s
            """, (xt_username, xt_password, account_id, product_name))

            print(f"  ✓ 迅投用户: {xt_username}")
            print(f"  ✓ 资金账号: {account_id}")
            print("  ✓ 密码: 已设置")

            conn.commit()
            print("\n=== 更新完成 ===")

            # 验证更新
            print("\n=== 验证更新 ===")
            cursor.execute("""
                SELECT product_name, account_id, xt_username
                FROM products
                WHERE product_name = %s
            """, (product_name,))
            result = cursor.fetchone()
            if result:
                print(f"产品: {result[0]}")
                print(f"账号: {result[1]}")
                print(f"用户: {result[2]}")

    except Exception as e:
        conn.rollback()
        print(f"✗ 更新失败: {e}")
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    update_product_credentials()
