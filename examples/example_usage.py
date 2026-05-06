"""
example_usage.py — 系统集成示例

演示如何将 5 个核心模块组合使用，构建完整的规则触发系统。

示例场景：
  1. 创建 EventBus 和双层 Context。
  2. 定义 AST 规则：(RSI < 30) AND (close > SMA)。
  3. 注册 AstRuleTrigger、DeviationTrigger、CronTrigger。
  4. 模拟行情事件流，观察信号触发。
"""

import logging
from datetime import datetime, timedelta

from cep.engine.ast_engine import (
    Operator,
    build_and,
    build_comparison,
)
from cep.core.context import (
    DEFAULT_INDICATOR_REGISTRY,
    GlobalContext,
    LocalContext,
)
from cep.core.event_bus import EventBus
from cep.core.events import (
    BarEvent,
    SignalEvent,
    TickEvent,
    TimerEvent,
)
from cep.triggers.triggers import (
    create_ast_trigger,
    create_cron_trigger,
    create_deviation_trigger,
)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 信号处理器（下游业务逻辑）
# ---------------------------------------------------------------------------


def on_trade_opportunity(signal: SignalEvent) -> None:
    """
    处理交易机会信号（示例：打印日志，实际应调用下单模块）。

    Args:
        signal: SignalEvent 实例。
    """
    logger.info(
        f"🔔 TRADE OPPORTUNITY: {signal.symbol} | "
        f"Source: {signal.source} | Payload: {signal.payload}"
    )
    # 实际业务逻辑：
    # - 调用风控模块检查是否允许开仓
    # - 调用下单模块提交订单
    # - 记录信号到数据库用于回测分析


def on_rebalance_trigger(signal: SignalEvent) -> None:
    """
    处理再平衡信号（示例：打印日志，实际应调用调仓模块）。

    Args:
        signal: SignalEvent 实例。
    """
    logger.info(
        f"⚖️  REBALANCE TRIGGER: {signal.symbol} | "
        f"Deviation: {signal.payload.get('deviation', 0):.4f} | "
        f"Current: {signal.payload.get('current_weight', 0):.4f} | "
        f"Target: {signal.payload.get('target_weight', 0):.4f}"
    )
    # 实际业务逻辑：
    # - 计算需要调整的仓位数量
    # - 调用下单模块提交调仓订单
    # - 更新持仓记录


def on_fund_allocation(signal: SignalEvent) -> None:
    """
    处理资金分配信号（示例：打印日志，实际应调用资金管理模块）。

    Args:
        signal: SignalEvent 实例。
    """
    logger.info(
        f"💰 FUND ALLOCATION: Timer '{signal.payload.get('timer_id')}' fired at "
        f"{signal.payload.get('fired_at')}"
    )
    # 实际业务逻辑：
    # - 读取最新净值和目标权重配置
    # - 计算各品种应分配的资金
    # - 更新 GlobalContext 中的 target_weights


# ---------------------------------------------------------------------------
# 主函数：系统初始化与事件模拟
# ---------------------------------------------------------------------------


def main() -> None:
    """
    主函数：演示完整的系统集成流程。
    """
    logger.info("=" * 80)
    logger.info("CEP 规则触发系统启动")
    logger.info("=" * 80)

    # -----------------------------------------------------------------------
    # 1. 初始化核心组件
    # -----------------------------------------------------------------------

    # 创建全局事件总线
    event_bus = EventBus()

    # 创建全局上下文（存储宏观数据）
    global_context = GlobalContext()
    global_context.set("vix", 18.5)  # 波动率指数
    global_context.set("total_nav", 10_000_000.0)  # 总净值 1000 万
    global_context.set(
        "target_weights",
        {
            "600519.SH": 0.30,  # 贵州茅台目标权重 30%
            "000858.SZ": 0.25,  # 五粮液目标权重 25%
        },
    )

    # 创建本地上下文（品种级数据）
    local_context_maotai = LocalContext(
        symbol="600519.SH",
        window_size=100,
        indicator_registry=DEFAULT_INDICATOR_REGISTRY,
    )
    local_context_maotai.update_weight(0.28)  # 当前持仓权重 28%

    local_context_wuliangye = LocalContext(
        symbol="000858.SZ",
        window_size=100,
        indicator_registry=DEFAULT_INDICATOR_REGISTRY,
    )
    local_context_wuliangye.update_weight(0.32)  # 当前持仓权重 32%（偏离 +7%）

    # -----------------------------------------------------------------------
    # 2. 定义 AST 规则树
    # -----------------------------------------------------------------------

    # 规则：(RSI < 30) AND (close > SMA)
    # 语义：超卖且价格突破均线，视为买入机会
    rule_tree_maotai = build_and(
        build_comparison("rsi", Operator.LT, 30),
        build_comparison(
            "close", Operator.GT, "sma"
        ),  # 注意：这里 "sma" 会从 Context 读取
    )

    logger.info(f"规则树（贵州茅台）: {rule_tree_maotai}")

    # -----------------------------------------------------------------------
    # 3. 注册触发器
    # -----------------------------------------------------------------------

    # 3.1 AST 规则触发器（监听贵州茅台的 BarEvent）
    ast_trigger = create_ast_trigger(
        event_bus=event_bus,
        trigger_id="AST_MAOTAI_RSI_SMA",
        rule_tree=rule_tree_maotai,
        local_context=local_context_maotai,
        rule_id="RULE_001",
    )

    # 3.2 持仓偏离触发器（监听五粮液的 TickEvent）
    deviation_trigger = create_deviation_trigger(
        event_bus=event_bus,
        trigger_id="DEVIATION_WULIANGYE",
        local_context=local_context_wuliangye,
        global_context=global_context,
        threshold=0.05,  # 偏离阈值 5%
    )

    # 3.3 定时触发器（监听每日 14:30 的资金分配指令）
    cron_trigger = create_cron_trigger(
        event_bus=event_bus,
        trigger_id="CRON_DAILY_ALLOCATION",
        timer_id="DAILY_REBALANCE_1430",
    )

    # EventBus 使用 weakref 保存订阅者；示例中必须显式持有触发器实例。
    triggers = [ast_trigger, deviation_trigger, cron_trigger]

    # -----------------------------------------------------------------------
    # 4. 注册信号处理器（下游业务逻辑）
    # -----------------------------------------------------------------------

    # 订阅 SignalEvent，根据 signal_type 路由到不同的处理器
    def signal_router(signal: SignalEvent) -> None:
        """信号路由器：根据信号类型分发到对应处理器。"""
        from cep.core.events import SignalType

        if signal.signal_type == SignalType.TRADE_OPPORTUNITY:
            on_trade_opportunity(signal)
        elif signal.signal_type == SignalType.REBALANCE_TRIGGER:
            on_rebalance_trigger(signal)
        elif signal.signal_type == SignalType.FUND_ALLOCATION:
            on_fund_allocation(signal)
        else:
            logger.warning(f"Unknown signal type: {signal.signal_type}")

    event_bus.subscribe(SignalEvent, signal_router)

    # -----------------------------------------------------------------------
    # 5. 模拟事件流
    # -----------------------------------------------------------------------

    logger.info("\n" + "=" * 80)
    logger.info("开始模拟事件流")
    logger.info("=" * 80 + "\n")

    # 5.1 模拟贵州茅台的 K 线数据（触发 AST 规则）
    logger.info(
        ">>> 发布贵州茅台 BarEvent（使用一组可触发 RSI < 30 且 close > SMA 的 mock 数据）"
    )

    closes = [
        100.0,
        99.94,
        102.96,
        106.85,
        109.97,
        106.2,
        109.07,
        107.78,
        106.8,
        107.9,
        110.91,
        114.19,
        112.0,
        113.62,
        117.2,
        121.02,
        124.19,
        120.4,
        119.14,
        118.23,
        115.76,
        115.51,
        115.13,
        116.37,
        116.75,
        117.17,
        115.16,
        115.39,
        115.39,
        116.77,
        117.07,
    ]

    start_time = datetime(2026, 3, 27, 9, 30)
    prev_close = closes[0]
    for i, close in enumerate(closes):
        bar_time = start_time + timedelta(minutes=i)
        bar = BarEvent(
            symbol="600519.SH",
            freq="1m",
            open=prev_close,
            high=max(prev_close, close) + 0.2,
            low=min(prev_close, close) - 0.2,
            close=close,
            volume=1000 + i * 10,
            turnover=close * (1000 + i * 10),
            bar_time=bar_time,
            timestamp=bar_time,
        )
        event_bus.publish(bar)
        prev_close = close

    # 5.2 模拟五粮液的 Tick 数据（触发持仓偏离）
    logger.info("\n>>> 发布五粮液 TickEvent（当前权重 32%，目标 25%，偏离 7%）")
    tick = TickEvent(
        symbol="000858.SZ",
        last_price=180.5,
        bid_prices=(180.4, 180.3, 180.2, 180.1, 180.0),
        ask_prices=(180.6, 180.7, 180.8, 180.9, 181.0),
        volume=500,
    )
    event_bus.publish(tick)

    # 5.3 模拟定时器事件（触发资金分配）
    logger.info("\n>>> 发布 TimerEvent（每日 14:30 资金分配）")
    timer = TimerEvent(
        timer_id="DAILY_REBALANCE_1430",
        fired_at=datetime(2026, 3, 27, 14, 30),
    )
    event_bus.publish(timer)

    # -----------------------------------------------------------------------
    # 6. 系统统计
    # -----------------------------------------------------------------------

    logger.info("\n" + "=" * 80)
    logger.info("系统统计")
    logger.info("=" * 80)
    logger.info(f"BarEvent 订阅者数量: {event_bus.get_subscriber_count(BarEvent)}")
    logger.info(f"TickEvent 订阅者数量: {event_bus.get_subscriber_count(TickEvent)}")
    logger.info(f"TimerEvent 订阅者数量: {event_bus.get_subscriber_count(TimerEvent)}")
    logger.info(
        f"SignalEvent 订阅者数量: {event_bus.get_subscriber_count(SignalEvent)}"
    )
    logger.info(f"保持存活的触发器数量: {len(triggers)}")

    logger.info("\n" + "=" * 80)
    logger.info("CEP 规则触发系统演示完成")
    logger.info("=" * 80)


if __name__ == "__main__":
    main()
