"""
执行数据库迁移：添加 xt_username 和 xt_password 字段
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

def run_migration():
    """执行迁移"""
    conn = pymysql.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cursor:
            print("=== 执行数据库迁移 ===\n")

            # 检查字段是否已存在
            cursor.execute("SHOW COLUMNS FROM products LIKE 'xt_username'")
            if cursor.fetchone():
                print("✓ xt_username 字段已存在，跳过")
            else:
                print("添加 xt_username 字段...")
                cursor.execute("""
                    ALTER TABLE products
                    ADD COLUMN xt_username VARCHAR(100) DEFAULT NULL COMMENT '迅投登录用户名'
                """)
                print("✓ xt_username 字段添加成功")

            cursor.execute("SHOW COLUMNS FROM products LIKE 'xt_password'")
            if cursor.fetchone():
                print("✓ xt_password 字段已存在，跳过")
            else:
                print("添加 xt_password 字段...")
                cursor.execute("""
                    ALTER TABLE products
                    ADD COLUMN xt_password VARCHAR(255) DEFAULT NULL COMMENT '迅投登录密码'
                """)
                print("✓ xt_password 字段添加成功")

            conn.commit()
            print("\n=== 迁移完成 ===")

    except Exception as e:
        conn.rollback()
        print(f"✗ 迁移失败: {e}")
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    run_migration()
