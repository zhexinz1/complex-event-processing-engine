"""
查询数据库中的产品列表
"""
import pymysql

DB_CONFIG = {
    'host': '120.25.245.137',
    'port': 23306,
    'user': 'cx',
    'password': 'cC3z#,2?od)gn7Nhd2L1',
    'database': 'fof',
    'charset': 'utf8mb4',
    'cursorclass': pymysql.cursors.DictCursor
}

def check_products():
    """查询产品列表"""
    conn = pymysql.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cursor:
            # 检查表结构
            cursor.execute("SHOW COLUMNS FROM products")
            columns = cursor.fetchall()
            print("=== products 表结构 ===")
            for col in columns:
                print(f"  {col['Field']}: {col['Type']}")

            # 查询产品
            print("\n=== 产品列表 ===")
            cursor.execute("SELECT * FROM products LIMIT 5")
            products = cursor.fetchall()

            if not products:
                print("  数据库中没有产品")
            else:
                for p in products:
                    print(f"\n产品: {p.get('product_name')}")
                    print(f"  账号ID: {p.get('account_id')}")
                    print(f"  迅投用户: {p.get('xt_username', '未配置')}")
                    print(f"  密码: {'已配置' if p.get('xt_password') else '未配置'}")
    finally:
        conn.close()

if __name__ == "__main__":
    check_products()
