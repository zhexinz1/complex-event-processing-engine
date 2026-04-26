"""
更新产品的正确账号ID
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

def update_account_id():
    """更新为正确的账号ID"""
    conn = pymysql.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cursor:
            print("=== 更新账号ID ===\n")

            product_name = "测试产品D"
            correct_account_id = "90102870"  # 真实的账号ID

            print(f"更新产品: {product_name}")
            print(f"新账号ID: {correct_account_id}")

            cursor.execute("""
                UPDATE products
                SET account_id = %s
                WHERE product_name = %s
            """, (correct_account_id, product_name))

            conn.commit()
            print(f"✓ 更新成功\n")

            # 验证
            cursor.execute("""
                SELECT product_name, account_id, xt_username
                FROM products
                WHERE product_name = %s
            """, (product_name,))
            result = cursor.fetchone()
            if result:
                print("验证:")
                print(f"  产品: {result[0]}")
                print(f"  账号: {result[1]}")
                print(f"  用户: {result[2]}")

    except Exception as e:
        conn.rollback()
        print(f"✗ 更新失败: {e}")
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    update_account_id()
