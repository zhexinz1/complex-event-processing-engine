"""
rebalance_triggers.py — 再平衡触发器

实现三类再平衡触发器：
  1. FundFlowTrigger:        资金申赎触发器（定时检查新增资金）
  2. MonthlyRebalanceTrigger: 月初定期触发器（每月初强制拉回基准）
  3. PortfolioDeviationTrigger: 组合偏离触发器（监控全品种权重偏离）

设计原则：
  - 统一发射 REBALANCE_REQUEST 信号
  - 携带必要的上下文信息（如新增资金、偏离品种等）
  - 与现有触发器架构保持一致
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, date
from typing import Optional

from cep.core.event_bus import EventBus
from cep.core.events import BaseEvent, SignalEvent, SignalType, TickEvent, TimerEvent
from rebalance.portfolio_context import PortfolioContext
from cep.triggers.triggers import BaseTrigger

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 资金申赎触发器
# ---------------------------------------------------------------------------

class FundFlowTrigger(BaseTrigger):
    """
    资金申赎触发器。

    工作流程：
      1. 由外部调用 fire() 方法触发（由运营人员确认出入金后调用）
      2. 接收净入金金额（由 FundFlowManager 计算得出）
      3. 发射 REBALANCE_REQUEST 信号，携带净入金金额

    典型应用：
      - 运营人员输入入金 130 万 → FundFlowManager 计算净入金 → 触发再平衡
      - 客户赎回 50 万 → FundFlowManager 计算净出金 → 触发减仓

    与 FundFlowManager 的集成方式：
      1. 运营人员通过前端输入出入金记录
      2. FundFlowManager 从迅投 API 获取估值
      3. FundFlowManager 计算净入金
      4. FundFlowManager 调用 trigger.fire(net_capital_change)
      5. 触发器发射 REBALANCE_REQUEST 信号
      6. RebalanceHandler 按最新配置比例下单
    """

    def __init__(
        self,
        event_bus: EventBus,
        trigger_id: str,
    ) -> None:
        """
        初始化资金申赎触发器。

        Args:
            event_bus:   全局事件总线
            trigger_id:  触发器 ID
        """
        super().__init__(event_bus, trigger_id)

    def register(self) -> None:
        """资金触发器无需订阅事件，由外部 fire() 方法直接触发。"""
        logger.info(f"FundFlowTrigger '{self.trigger_id}' registered (fire-on-demand)")

    def on_event(self, event: BaseEvent) -> None:
        """不使用事件订阅，改由 fire() 方法直接触发。"""
        pass

    def fire(
        self,
        product_name: str,
        net_capital_change: float,
        previous_nav: float,
        current_nav: float,
        pnl: float,
        operator: str,
        remark: str = ""
    ) -> None:
        """
        由 FundFlowManager 调用，触发资金变动再平衡。

        Args:
            product_name:        产品名称
            net_capital_change:  净入金金额（正数入金，负数出金）
            previous_nav:        昨日净值
            current_nav:         今日净值（从迅投 API 获取）
            pnl:                 今日盈亏
            operator:            操作员
            remark:              备注
        """
        if abs(net_capital_change) < 1000:
            logger.info(
                f"FundFlowTrigger '{self.trigger_id}': net_capital_change too small "
                f"({net_capital_change:,.2f}), skipping"
            )
            return

        logger.info(
            f"FundFlowTrigger '{self.trigger_id}' fired by operator '{operator}': "
            f"product={product_name}, net_capital={net_capital_change:,.2f}, "
            f"prev_nav={previous_nav:,.2f}, curr_nav={current_nav:,.2f}, pnl={pnl:,.2f}"
        )

        self._emit_signal(
            symbol="",
            signal_type=SignalType.REBALANCE_REQUEST,
            payload={
                "trigger_type": "fund_flow",
                "product_name": product_name,
                "new_capital": net_capital_change,
                "previous_nav": previous_nav,
                "current_nav": current_nav,
                "pnl": pnl,
                "operator": operator,
                "remark": remark,
                "fired_at": datetime.now().isoformat(),
                "calculation_method": "current_nav - previous_nav - pnl",
            },
        )


# ---------------------------------------------------------------------------
# 月初定期触发器
# ---------------------------------------------------------------------------

class MonthlyRebalanceTrigger(BaseTrigger):
    """
    月初定期触发器。

    工作流程：
      1. 监听 TimerEvent（如每月 1 号 9:30）
      2. 无条件发射 REBALANCE_REQUEST 信号
      3. 强制拉回基准权重

    典型应用：
      - 每月初更新目标权重配置后，强制再平衡
      - 定期清理累积的偏离

    Attributes:
        timer_id: 监听的定时器 ID（如 "MONTHLY_REBALANCE_0930"）
    """

    def __init__(
        self,
        event_bus: EventBus,
        trigger_id: str,
        timer_id: str,
    ) -> None:
        """
        初始化月初定期触发器。

        Args:
            event_bus:  全局事件总线
            trigger_id: 触发器 ID
            timer_id:   监听的定时器 ID
        """
        super().__init__(event_bus, trigger_id)
        self.timer_id = timer_id

    def register(self) -> None:
        """订阅 TimerEvent。"""
        self.event_bus.subscribe(TimerEvent, self.on_event)
        logger.info(
            f"MonthlyRebalanceTrigger '{self.trigger_id}' subscribed to TimerEvent "
            f"(timer_id='{self.timer_id}')"
        )

    def on_event(self, event: BaseEvent) -> None:
        """
        TimerEvent 回调：无条件触发再平衡。

        Args:
            event: TimerEvent 实例
        """
        if not isinstance(event, TimerEvent):
            return

        # 过滤：仅处理目标定时器
        if event.timer_id != self.timer_id:
            return

        logger.info(
            f"MonthlyRebalanceTrigger '{self.trigger_id}' fired by timer '{self.timer_id}' "
            f"at {event.fired_at.isoformat()}"
        )

        # 发射再平衡请求信号
        self._emit_signal(
            symbol="",  # 全局信号
            signal_type=SignalType.REBALANCE_REQUEST,
            payload={
                "trigger_type": "monthly",
                "new_capital": 0.0,  # 月初定期不涉及新增资金
                "fired_at": event.fired_at.isoformat(),
                "timer_id": event.timer_id,
            },
        )


# ---------------------------------------------------------------------------
# 组合偏离触发器
# ---------------------------------------------------------------------------

class PortfolioDeviationTrigger(BaseTrigger):
    """
    组合偏离触发器（基于 TickEvent 实时监控版本）。

    工作流程：
      1. 监听 TickEvent（实时行情推送）
      2. 更新 PortfolioContext 中的最新价格
      3. 定期检查（60秒冷却）所有品种的当前权重 vs 目标权重
      4. 若任一品种偏离超过阈值，发射 REBALANCE_REQUEST 信号

    典型应用：
      - 盘中监控：沪金 2606 因暴涨导致权重从 26% 涨到 30%，触发再平衡
      - 风控：某品种权重超过上限，触发减仓

    Attributes:
        portfolio_ctx:        组合上下文
        threshold:            全局偏离阈值（如 0.03 表示 3%）
        symbol_thresholds:    每个资产的独立偏离阈值（优先级高于全局阈值）
        cooldown:             检查冷却期（秒，默认 60）
    """

    def __init__(
        self,
        event_bus: EventBus,
        trigger_id: str,
        portfolio_ctx: PortfolioContext,
        threshold: float = 0.03,
        symbol_thresholds: Optional[dict[str, float]] = None,
        cooldown: float = 60.0,
    ) -> None:
        """
        初始化组合偏离触发器。

        Args:
            event_bus:         全局事件总线
            trigger_id:        触发器 ID
            portfolio_ctx:     组合上下文
            threshold:         全局偏离阈值（默认 3%）
            symbol_thresholds: 每个资产的独立偏离阈值（可选）
                              例如：{"AU2606.SHF": 0.03, "IC2606.CFE": 0.05}
            cooldown:          检查冷却期（秒，默认 60）
        """
        super().__init__(event_bus, trigger_id)
        self.portfolio_ctx = portfolio_ctx
        self.threshold = threshold
        self.symbol_thresholds = symbol_thresholds or {}
        self.cooldown = cooldown

        # 防抖机制
        self._last_check_time: float = 0.0
        self._tick_count: int = 0  # 统计收到的 Tick 数量（用于日志）

    def register(self) -> None:
        """订阅 TickEvent（全局订阅，接收所有品种的行情）。"""
        self.event_bus.subscribe(TickEvent, self.on_event)
        logger.info(
            f"PortfolioDeviationTrigger '{self.trigger_id}' subscribed to TickEvent "
            f"(threshold={self.threshold:.2%}, cooldown={self.cooldown}s)"
        )

    def on_event(self, event: BaseEvent) -> None:
        """
        TickEvent 回调：更新价格并检查全品种偏离度。

        Args:
            event: TickEvent 实例
        """
        if not isinstance(event, TickEvent):
            return

        # 统计 Tick 数量
        self._tick_count += 1

        # 1. 更新价格到 PortfolioContext（每个 Tick 都更新）
        self.portfolio_ctx.update_price(event.symbol, event.last_price)

        # 2. 防抖检查：是否到达冷却期
        import time
        current_time = time.time()
        if current_time - self._last_check_time < self.cooldown:
            # 冷却期内，跳过偏离度检查
            return

        # 3. 执行偏离度检查
        logger.debug(
            f"Deviation check triggered by {event.symbol} tick "
            f"(received {self._tick_count} ticks since last check)"
        )
        self._check_deviation(current_time)

        # 重置 Tick 计数
        self._tick_count = 0

    def _check_deviation(self, current_time: float) -> None:
        """
        检查全品种偏离度并触发再平衡信号。

        Args:
            current_time: 当前时间戳
        """
        # 获取目标权重和当前权重
        target_weights = self.portfolio_ctx.get_all_target_weights()
        current_weights = self.portfolio_ctx.calculate_all_current_weights()

        if not target_weights:
            logger.warning("No target weights configured, skipping deviation check")
            return

        # 计算最大偏离（考虑每个资产的独立阈值）
        max_deviation = 0.0
        max_deviation_symbol = ""
        deviations = {}
        triggered_symbols = []  # 记录触发阈值的品种

        for symbol, target_weight in target_weights.items():
            current_weight = current_weights.get(symbol, 0.0)
            deviation = abs(current_weight - target_weight)
            deviations[symbol] = deviation

            # 获取该资产的偏离阈值（优先使用独立配置，否则使用全局阈值）
            symbol_threshold = self.symbol_thresholds.get(symbol, self.threshold)

            # 检查是否超过阈值
            if deviation > symbol_threshold:
                triggered_symbols.append(symbol)

            # 记录最大偏离（用于日志）
            if deviation > max_deviation:
                max_deviation = deviation
                max_deviation_symbol = symbol

            logger.debug(
                f"  {symbol}: current={current_weight:.4f}, "
                f"target={target_weight:.4f}, deviation={deviation:.4f}, "
                f"threshold={symbol_threshold:.4f}"
            )

        # 若有任何品种偏离超过阈值，触发再平衡
        if triggered_symbols:
            logger.info(
                f"PortfolioDeviationTrigger '{self.trigger_id}' detected deviation: "
                f"{len(triggered_symbols)} symbols exceeded threshold: {triggered_symbols}"
            )

            # 更新最后检查时间（开始冷却）
            self._last_check_time = current_time

            # 发射再平衡请求信号
            self._emit_signal(
                symbol="",  # 全局信号
                signal_type=SignalType.REBALANCE_REQUEST,
                payload={
                    "trigger_type": "deviation",
                    "new_capital": 0.0,
                    "max_deviation": max_deviation,
                    "max_deviation_symbol": max_deviation_symbol,
                    "triggered_symbols": triggered_symbols,
                    "all_deviations": deviations,
                    "global_threshold": self.threshold,
                    "symbol_thresholds": self.symbol_thresholds,
                },
            )
        else:
            # 未超过阈值，更新检查时间但不触发
            self._last_check_time = current_time
            logger.debug(
                f"Deviation check passed: max={max_deviation:.4f} "
                f"(symbol={max_deviation_symbol})"
            )
