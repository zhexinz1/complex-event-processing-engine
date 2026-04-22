"""测试 XtQueryService 查询功能"""
import sys
import os
import logging

sys.path.insert(0, '/home/ubuntu/xt_sdk')
os.environ['LD_LIBRARY_PATH'] = '/home/ubuntu/xt_sdk:' + os.environ.get('LD_LIBRARY_PATH', '')

from adapters.xt_query_service import XtQueryService

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

def main():
    service = XtQueryService()

    print("正在连接...")
    if service.connect(timeout=30.0):
        print("连接成功！")

        # 查询产品列表
        products = service.query_products()
        print(f"\n>>> 查询到 {len(products)} 个产品:")
        for p in products:
            print(f"    - {p.product_name} (ID: {p.product_id}, 净值: {p.total_net_value:.2f})")

        # 查询可用资金
        available = service.get_available_cash()
        if available is not None:
            print(f"\n>>> 可用资金：{available:,.2f} 元\n")
        else:
            print("\n>>> 资金查询失败\n")
    else:
        print("连接失败")

if __name__ == "__main__":
    main()
