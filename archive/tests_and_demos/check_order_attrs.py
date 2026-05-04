#!/usr/bin/env python3
"""检查 COrderDetail 对象的属性"""

import sys
sys.path.append("/home/ubuntu/minitrader/userdata_mini/sdk")

from xttrader.xttrader import XtTraderApi
from xttrader.xttype import XtError

# 创建 API 实例
api = XtTraderApi()

# 查询订单（不需要登录，只是为了获取对象类型）
error = XtError(0, "")

# 打印 COrderDetail 的所有属性
print("尝试获取 COrderDetail 类的属性...")

# 从 xttype 导入
try:
    from xttrader import xttype

    # 查找 COrderDetail 类
    if hasattr(xttype, 'COrderDetail'):
        print("\n找到 COrderDetail 类")
        order_class = xttype.COrderDetail
        print(f"类型: {order_class}")
        print("\n所有属性:")
        for attr in dir(order_class):
            if not attr.startswith('_'):
                print(f"  - {attr}")
    else:
        print("未找到 COrderDetail 类")
        print("xttype 模块的所有内容:")
        for name in dir(xttype):
            if 'Order' in name or 'order' in name:
                print(f"  - {name}")

except Exception as e:
    print(f"错误: {e}")
    import traceback
    traceback.print_exc()
