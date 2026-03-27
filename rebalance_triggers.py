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
from datetime import datetime
from typing import Optional

from event_bus import EventBus
from events import BaseEvent, SignalEvent, SignalType, TimerEvent
from portfolio_context import PortfolioContext
from triggers import BaseTrigger

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 资金申赎触发器
# ---------------------------------------------------------------------------

class FundFlowTrigger(BaseTrigger):
    """
    资金申赎触发器。

    工作流程：
      1. 监听 TimerEvent（如每日 14:30）
      2. 检查是否有新增资金（从外部系统拉取，当前模拟）
      3. 若有新增资金，发射 REBALANCE_REQUEST 信号

    典型应用：
      - 客户申购：14:30 检测到 130 万入金，触发再平衡
      - 客户赎回：检测到资金流出，触发减仓

    Attributes:
        timer_id:       监听的定时器 ID
        portfolio_ctx:  组合上下文（用于读取账户信息）
        check_interval: 检查间隔（秒）
    """

    def __init__(
        self,
        event_bus: EventBus,
        trigger_id: str,
        timer_id: str,
        portfolio_ctx: PortfolioContext,
    ) -> None:
        """
        初始化资金申赎触发器。

        Args:
            event_bus:      全局事件总线
            trigger_id:     触发器 ID
            timer_id:       监听的定时器 ID
            portfolio_ctx:  组合上下文
        """
        super().__init__(event_bus, trigger_id)
        self.timer_id = timer_id
        self.portfolio_ctx = portfolio_ctx
        self._last_nav: float = 0.0  # 记录上次净值，用于检测资金变化

    def register(self) -> None:
        """订阅 TimerEvent。"""
        self.event_bus.subscribe(TimerEvent, self.on_event)
        logger.info(
            f"FundFlowTrigger '{self.trigger_id}' subscribed to TimerEvent "
            f"(timer_id='{self.timer_id}')"
        )

    def on_event(self, event: BaseEvent) -> None:
        """
        TimerEvent 回调：检查资金变化并触发再平衡。

        Args:
            event: TimerEvent 实例
        """
        if not isinstance(event, TimerEvent):
            return

        # 过滤：仅处理目标定时器
        if event.timer_id != self.timer_id:
            return

        # TODO: 从外部系统拉取最新净值和资金变化
        # 当前模拟：假设从 portfolio_ctx 读取
        current_nav = self.portfolio_ctx.get_total_nav()

        # 检测资金变化
        if self._last_nav > 0:
            capital_change = current_nav - self._last_nav

            # 如果有显著的资金变化（> 1000 元），触发再平衡
            if abs(capital_change) > 1000:
                logger.info(
                    f"FundFlowTrigger '{self.trigger_id}' detected capital change: "
                    f"{capital_change:,.2f} (from {self._last_nav:,.2f} to {current_nav:,.2f})"
                )

                # 发射再平衡请求信号
                self._emit_signal(
                    symbol="",  # 全局信号
                    signal_type=SignalType.REBALANCE_REQUEST,
                    payload={
                        "trigger_type": "fund_flow",
                        "new_capital": capital_change,
                        "previous_nav": self._last_nav,
                        "current_nav": current_nav,
                        "fired_at": event.fired_at.isoformat(),
                    },
                )

        # 更新记录的净值
        self._last_nav = current_nav


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
    组合偏离触发器（全品种监控版本）。

    工作流程：
      1. 监听 TimerEvent（定期检查，如每分钟）
      2. 计算所有品种的当前权重 vs 目标权重
      3. 若任一品种偏离超过阈值，发射 REBALANCE_REQUEST 信号

    典型应用：
      - 盘中监控：沪金 2606 因暴涨导致权重从 26% 涨到 30%，触发再平衡
      - 风控：某品种权重超过上限，触发减仓

    Attributes:
        portfolio_ctx: 组合上下文
        threshold:     偏离阈值（如 0.03 表示 3%）
        timer_id:      监听的定时器 ID
    """

    def __init__(
        self,
        event_bus: EventBus,
        trigger_id: str,
        portfolio_ctx: PortfolioContext,
        threshold: float = 0.03,
        timer_id: str = "DEVIATION_CHECK",
    ) -> None:
        """
        初始化组合偏离触发器。

        Args:
            event_bus:      全局事件总线
            trigger_id:     触发器 ID
            portfolio_ctx:  组合上下文
            threshold:      偏离阈值（默认 3%）
            timer_id:       监听的定时器 ID
        """
        super().__init__(event_bus, trigger_id)
        self.portfolio_ctx = portfolio_ctx
        self.threshold = threshold
        self.timer_id = timer_id

        # 冷却锁与防抖期设定
        self._last_trigger_time: float = 0.0
        self._cooldown_seconds: float = 60.0  # 60 秒冷却期

    def register(self) -> None:
        """订阅 TimerEvent。"""
        self.event_bus.subscribe(TimerEvent, self.on_event)
        logger.info(
            f"PortfolioDeviationTrigger '{self.trigger_id}' subscribed to TimerEvent "
            f"(timer_id='{self.timer_id}', threshold={self.threshold})"
        )

    def on_event(self, event: BaseEvent) -> None:
        """
        TimerEvent 回调：检查全品种偏离度。

        Args:
            event: TimerEvent 实例
        """
        if not isinstance(event, TimerEvent):
            return

        # 过滤：仅处理目标定时器
        if event.timer_id != self.timer_id:
            return

        # 防抖冷却
        current_ts = event.fired_at.timestamp()
        if current_ts - self._last_trigger_time < self._cooldown_seconds:
            return

        # 计算所有品种的偏离度
        target_weights = self.portfolio_ctx.get_all_target_weights()
        current_weights = self.portfolio_ctx.calculate_all_current_weights()

        max_deviation = 0.0
        max_deviation_symbol = ""

        for symbol, target_weight in target_weights.items():
            current_weight = current_weights.get(symbol, 0.0)
            deviation = abs(current_weight - target_weight)

            if deviation > max_deviation:
                max_deviation = deviation
                max_deviation_symbol = symbol

            logger.debug(
                f"Deviation check: {symbol} current={current_weight:.4f}, "
                f"target={target_weight:.4f}, deviation={deviation:.4f}"
            )

        # 若最大偏离超过阈值，触发再平衡
        if max_deviation > self.threshold:
            logger.info(
                f"PortfolioDeviationTrigger '{self.trigger_id}' detected deviation: "
                f"{max_deviation_symbol} deviation={max_deviation:.4f} > threshold={self.threshold:.4f}"
            )

            # 更新防抖时间
            self._last_trigger_time = current_ts

            # 发射再平衡请求信号
            self._emit_signal(
                symbol="",  # 全局信号
                signal_type=SignalType.REBALANCE_REQUEST,
                payload={
                    "trigger_type": "deviation",
                    "new_capital": 0.0,
                    "max_deviation": max_deviation,
                    "max_deviation_symbol": max_deviation_symbol,
                    "fired_at": event.fired_at.isoformat(),
                },
            )
