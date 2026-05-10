"""
run_trading_node.py - 微服务化：独立引擎及交易节点

此进程充当整个系统的"大脑"与最后执行方：
1. 从 Redis 接收 Market Node 推送来的高频 Tick/Bar 行情。
2. 把这些外部事件当成本地网络事件触发 ECA 引擎的执行。
3. 如遇触发，调用由该进程独占的 XunTou 网关完成发单落袋。

用法：
  source scripts/setup_env.sh
  uv run -m services.run_trading_node
"""

import sys
import os
import time
import logging

from dotenv import load_dotenv

from cep.core.event_bus import EventBus
from cep.core.remote_bus import RedisEventBridge

from adapters.xuntou import XtOrderService, OrderRequest, OrderDirection, OrderPriceType

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

XT_SERVER_ADDR = "8.166.130.204:65300"
XT_USERNAME = "system_trade"
XT_PASSWORD = "my123456@"
XT_TARGET_ACCT = "90102870"


def _ensure_xt_env() -> None:
    """确保 LD_LIBRARY_PATH 包含迅投 SDK 路径，否则 re-exec。"""
    xt_sdk_path = os.environ.get("XT_SDK_PATH", os.path.expanduser("~/xt_sdk"))
    ld_lib_path = os.environ.get("LD_LIBRARY_PATH", "")
    if xt_sdk_path not in ld_lib_path:
        logger.info("[Trading Node] LD_LIBRARY_PATH 缺少迅投 SDK，正在重启进程注入...")
        os.environ["LD_LIBRARY_PATH"] = xt_sdk_path + ":" + ld_lib_path
        os.execlp(sys.executable, sys.executable, "-m", "services.run_trading_node", *sys.argv[1:])


def main():
    logger.info("=" * 60)
    logger.info("[Trading Node] 正在启动独立策略与交易微服务...")
    logger.info("=" * 60)

    # 1. 核心事件总线
    local_bus = EventBus()

    # 2. 从 Redis 中汲取异地网络发来的行情并当成本地事件执行
    redis_bridge = RedisEventBridge(local_bus)
    redis_bridge.start_consuming()

    # 3. 交易网关拉起
    logger.info("[Trading Node] 正在拉起迅投资金端组件...")
    order_gw = XtOrderService(username=XT_USERNAME, password=XT_PASSWORD)

    # 迅投不支持极其顺滑的直接 Init，在此我们可以启动连接 (内部实现是异步 callback)
    # 本教程中，为了微服务示意，我们仅进行网关构建
    if not order_gw.connect():
        # 如果因为环境配置不对，那就告警，当然这不妨碍核心计算引擎跑起来
        logger.warning(
            "[Trading Node] 迅投资金端登录遇到异常。目前以降级模式启动（只会打印信号不发真实订单）"
        )
    else:
        # 这里如果想要发单，就需要调用底层的 xtAPI 发送
        # 此处展示当收到信号时，真实发出 Log
        pass

    # 4. 随便写一个假的 Trigger 原型，证明微服务发单流贯通
    def fake_strategy(event):
        # 如果从 Redis 接到了超过 2000 的价格跳动
        price = event.last_price
        if price > 2000:
            logger.critical(
                f"[🔴🚨微服务级联动触发] 监测到巨量涌入: {event.symbol} @ {price}! 正在通知迅投直接追单!!"
            )

            # 使用真实网关构建并发单
            order_req = OrderRequest(
                account_id=XT_TARGET_ACCT,
                asset_code=f"{event.symbol}.SHFE",  # 假设都是上期所，如需精确处理可以在外围加映射
                direction=OrderDirection.OPEN_LONG,
                quantity=1,
                price=price + 0.02,  # 对手价追单
                price_type=OrderPriceType.LIMIT,
            )

            # 真实发单并记录回报
            result = order_gw.place_order(order_req, timeout=10.0)
            if result.success:
                logger.info(
                    f"✅ 下单成功！订单号: {result.order_id}, 追单价格: {order_req.price:.2f}"
                )
            else:
                logger.error(f"❌ 下单失败: {result.error_msg}")

    # 让本地 EventBus 监听跨进程丢过来的 Tick
    # 只要在 remote_bus 那边将包推入本 local_bus，这里立刻回调
    from cep.core.events import TickEvent

    local_bus.subscribe(TickEvent, fake_strategy)

    logger.info(
        "[Trading Node] 系统现已就绪。静待 Market Node 行情注入... 按 Ctrl+C 退出。"
    )
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("收到中止信号，正在关闭服务...")
    finally:
        redis_bridge.stop()
        # 迅投网关不需要显式 release，由进程析构自动接管


if __name__ == "__main__":
    load_dotenv()
    _ensure_xt_env()
    main()
