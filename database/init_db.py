"""
初始化数据库表结构
执行 database/schema.sql 中的建表语句
"""
import os
import pymysql

DB_CONFIG = {
    'host': os.environ.get('DB_HOST', '127.0.0.1'),
    'port': int(os.environ.get('DB_PORT', '3306')),
    'user': os.environ.get('DB_USER', 'root'),
    'password': os.environ.get('DB_PASS', ''),
    'database': os.environ.get('DB_NAME', 'fof'),
    'charset': 'utf8mb4'
}

def init_database():
    """初始化数据库表"""
    # 读取 SQL 文件
    with open('database/schema.sql', 'r', encoding='utf-8') as f:
        sql_script = f.read()

    # 连接数据库
    conn = pymysql.connect(**DB_CONFIG)

    try:
        with conn.cursor() as cursor:
            # 分割并执行每条 SQL 语句
            statements = sql_script.split(';')
            for statement in statements:
                statement = statement.strip()
                if statement:
                    print(f"执行: {statement[:80]}...")
                    cursor.execute(statement)

        conn.commit()
        print("\n✅ 数据库表初始化成功！")

    except Exception as e:
        print(f"\n❌ 初始化失败: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == '__main__':
    init_database()
