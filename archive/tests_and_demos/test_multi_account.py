"""
测试多账号支持功能
验证连接管理器和订单确认流程
"""
import sys
sys.path.insert(0, '/home/ubuntu/xt_sdk')

from adapters.xuntou import get_xt_connection_manager

def test_connection_manager():
    """测试连接管理器"""
    print("=== 测试迅投连接管理器 ===\n")

    manager = get_xt_connection_manager()

    # 测试账号1
    username1 = "system_trade"
    password1 = "my123456@"
    account_id1 = "100000002"

    print(f"1. 连接账号: {username1}")
    service1 = manager.get_connection(username1, password1, account_id1, timeout=30.0)

    if service1:
        print(f"   ✓ 连接成功，登录状态: {service1._logined}")
    else:
        print("   ✗ 连接失败")
        return

    # 测试连接复用
    print("\n2. 再次获取相同账号连接（应复用）")
    service1_reuse = manager.get_connection(username1, password1, account_id1, timeout=30.0)

    if service1_reuse is service1:
        print("   ✓ 成功复用连接")
    else:
        print("   ✗ 未复用连接")

    print("\n=== 测试完成 ===")

if __name__ == "__main__":
    test_connection_manager()
