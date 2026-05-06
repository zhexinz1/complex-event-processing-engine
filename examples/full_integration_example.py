"""
完整系统集成示例（包含外部接口）

演示如何将所有模块组合使用，包括：
1. 行情网关接入
2. 配置数据源加载
3. 订单执行网关
4. 前端 API 接口
5. 事件驱动的再平衡流程
"""

import logging
import time

from cep.core.event_bus import EventBus
from adapters.market_gateway import MockMarketGateway
from adapters.config_source import FileConfigSource
from adapters.order_gateway import MockOrderGateway, Order
from adapters.frontend_api import FrontendAPI, FundInFlowRequest, RebalanceRequest
from rebalance.portfolio_context import PortfolioContext, ContractInfo, Position
from rebalance.rebalance_handler import RebalanceHandler
from rebalance.rebalance_triggers import FundFlowTrigger, PortfolioDeviationTrigger

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)


def main() -> None:
    """完整系统集成示例。"""

    logger.info("=" * 80)
    logger.info("CEP 系统启动 - 完整集成示例")
    logger.info("=" * 80)

    # -----------------------------------------------------------------------
    # 1. 初始化核心组件
    # -----------------------------------------------------------------------

    # 创建事件总线
    event_bus = EventBus()

    # 创建组合上下文
    portfolio_ctx = PortfolioContext()

    # -----------------------------------------------------------------------
    # 2. 初始化外部接口适配器
    # -----------------------------------------------------------------------

    # 2.1 配置数据源（从文件加载）
    config_source = FileConfigSource("config/strategy_config.json")

    # 加载目标权重配置
    target_weights = config_source.load_target_weights("strategy_001")
    if not target_weights:
        # 如果配置文件不存在，使用默认配置
        target_weights = {
            "AU2606": 0.26,
            "P2609": 0.17,
            "RB2610": 0.15,
            "HC2610": 0.12,
            "I2609": 0.10,
            "JM2609": 0.10,
            "J2609": 0.10,
        }
        config_source.save_target_weights("strategy_001", target_weights)

    portfolio_ctx.set_target_weights(target_weights)
    logger.info(f"目标权重配置已加载: {target_weights}")

    # 2.2 行情网关（模拟）
    market_gateway = MockMarketGateway(event_bus)
    market_gateway.connect()

    # 订阅行情
    symbols = list(target_weights.keys())
    market_gateway.subscribe(symbols)

    # 2.3 订单执行网关（模拟）
    order_gateway = MockOrderGateway()
    order_gateway.connect()

    # 设置订单回调
    def on_order_update(order: Order) -> None:
        logger.info(f"📋 订单更新: {order.order_id} {order.symbol} {order.status}")

    order_gateway.set_order_callback(on_order_update)

    # 2.4 前端 API 接口
    frontend_api = FrontendAPI(event_bus, portfolio_ctx)

    # -----------------------------------------------------------------------
    # 3. 初始化组合数据
    # -----------------------------------------------------------------------

    # 注册合约信息
    contracts = {
        "AU2606": ContractInfo(
            "AU2606", multiplier=1000, min_tick=0.05, margin_rate=0.08
        ),
        "P2609": ContractInfo("P2609", multiplier=10, min_tick=2, margin_rate=0.08),
        "RB2610": ContractInfo("RB2610", multiplier=10, min_tick=1, margin_rate=0.09),
        "HC2610": ContractInfo("HC2610", multiplier=10, min_tick=1, margin_rate=0.09),
        "I2609": ContractInfo("I2609", multiplier=100, min_tick=0.5, margin_rate=0.08),
        "JM2609": ContractInfo("JM2609", multiplier=60, min_tick=0.5, margin_rate=0.08),
        "J2609": ContractInfo("J2609", multiplier=100, min_tick=0.5, margin_rate=0.08),
    }

    for contract in contracts.values():
        portfolio_ctx.register_contract(contract)

    # 初始化账户信息
    initial_nav = 10_000_000.0  # 1000 万初始资金
    portfolio_ctx.update_account(
        total_nav=initial_nav, available_cash=initial_nav, margin_used=0.0
    )

    # 初始化持仓（空仓）
    for symbol in symbols:
        portfolio_ctx.update_position(
            Position(symbol=symbol, quantity=0.0, avg_price=0.0, market_value=0.0)
        )

    # -----------------------------------------------------------------------
    # 4. 注册再平衡处理器和触发器
    # -----------------------------------------------------------------------

    # 创建再平衡处理器
    RebalanceHandler(event_bus, portfolio_ctx).register()

    # 创建资金流触发器
    fund_flow_trigger = FundFlowTrigger(
        event_bus=event_bus,
        trigger_id="FUND_FLOW_MANUAL",
    )
    fund_flow_trigger.register()

    # 创建组合偏离触发器
    PortfolioDeviationTrigger(
        event_bus=event_bus,
        trigger_id="PORTFOLIO_DEVIATION",
        portfolio_ctx=portfolio_ctx,
        threshold=0.05,  # 5% 偏离阈值
    ).register()

    # -----------------------------------------------------------------------
    # 5. 模拟行情推送
    # -----------------------------------------------------------------------

    logger.info("\n" + "=" * 80)
    logger.info("推送初始行情数据")
    logger.info("=" * 80)

    # 推送初始价格
    initial_prices = {
        "AU2606": 580.50,
        "P2609": 8200.0,
        "RB2610": 3450.0,
        "HC2610": 3200.0,
        "I2609": 750.0,
        "JM2609": 1850.0,
        "J2609": 2100.0,
    }

    for symbol, price in initial_prices.items():
        market_gateway.push_tick(symbol, price)
        portfolio_ctx.update_price(symbol, price)

    # -----------------------------------------------------------------------
    # 6. 模拟前端用户操作
    # -----------------------------------------------------------------------

    logger.info("\n" + "=" * 80)
    logger.info("场景 1: 用户通过前端输入入金金额")
    logger.info("=" * 80)

    # 用户输入入金 200 万
    fund_request = FundInFlowRequest(
        amount=2_000_000.0, remark="客户追加投资", operator="张三"
    )

    response = frontend_api.submit_fund_inflow(fund_request)
    logger.info(f"API 响应: {response.message}")

    # 等待再平衡处理完成（实际系统中是异步的）
    time.sleep(1)

    # -----------------------------------------------------------------------
    # 7. 查询组合状态
    # -----------------------------------------------------------------------

    logger.info("\n" + "=" * 80)
    logger.info("场景 2: 查询当前组合状态")
    logger.info("=" * 80)

    response = frontend_api.get_portfolio_status()
    if response.success:
        account = response.data["account"]
        logger.info(f"总净值: {account['total_nav']:,.2f}")
        logger.info(f"可用资金: {account['available_cash']:,.2f}")
        logger.info(f"已用保证金: {account['margin_used']:,.2f}")

        logger.info("\n持仓明细:")
        for pos in response.data["positions"]:
            logger.info(
                f"  {pos['symbol']}: 数量={pos['quantity']:.2f}, "
                f"当前权重={pos['current_weight']:.2%}, "
                f"目标权重={pos['target_weight']:.2%}"
            )

    # -----------------------------------------------------------------------
    # 8. 查询权重偏离
    # -----------------------------------------------------------------------

    logger.info("\n" + "=" * 80)
    logger.info("场景 3: 查询权重偏离情况")
    logger.info("=" * 80)

    response = frontend_api.get_weight_deviation()
    if response.success:
        logger.info(f"发现 {len(response.data['deviations'])} 个品种:")
        for dev in response.data["deviations"][:5]:  # 只显示前 5 个
            logger.info(
                f"  {dev['symbol']}: 偏离 {dev['deviation']:+.2%} "
                f"(目标 {dev['target_weight']:.2%} vs 当前 {dev['current_weight']:.2%})"
            )

    # -----------------------------------------------------------------------
    # 9. 手动触发再平衡
    # -----------------------------------------------------------------------

    logger.info("\n" + "=" * 80)
    logger.info("场景 4: 用户手动触发再平衡")
    logger.info("=" * 80)

    rebalance_request = RebalanceRequest(
        reason="手动调仓", new_capital=0.0, operator="李四"
    )

    response = frontend_api.trigger_rebalance(rebalance_request)
    logger.info(f"API 响应: {response.message}")

    time.sleep(1)

    # -----------------------------------------------------------------------
    # 10. 健康检查
    # -----------------------------------------------------------------------

    logger.info("\n" + "=" * 80)
    logger.info("场景 5: 系统健康检查")
    logger.info("=" * 80)

    response = frontend_api.health_check()
    logger.info(f"健康状态: {response.data['status']}")

    # -----------------------------------------------------------------------
    # 11. 清理资源
    # -----------------------------------------------------------------------

    logger.info("\n" + "=" * 80)
    logger.info("系统关闭")
    logger.info("=" * 80)

    market_gateway.disconnect()
    order_gateway.disconnect()

    logger.info("CEP 系统已停止")


if __name__ == "__main__":
    main()
