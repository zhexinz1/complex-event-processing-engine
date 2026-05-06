"""
triggers.py — 触发器/传感器实现（Trigger/Sensor）

触发器是规则引擎的"感知器官"，负责监听事件、判定条件、发射信号。
核心设计原则：
  1. 单一职责：触发器只做"条件判断 + 信号发射"，绝不直接调用下单/弹窗等业务逻辑。
  2. 依赖注入：通过构造函数注入 EventBus 和 Context，便于测试和解耦。
  3. 事件驱动：触发器订阅特定事件类型，由 EventBus 回调 on_event() 方法。

触发器类型：
  - AstRuleTrigger:     基于 AST 的代数规则触发器（技术指标组合条件）。
  - DeviationTrigger:   持仓偏离触发器（current_weight - target_weight > threshold）。
  - CronTrigger:        定时触发器（基于系统时间或 TimerEvent）。
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Optional

from cep.engine.ast_engine import Node
from cep.core.context import GlobalContext, LocalContext
from cep.core.event_bus import EventBus
from cep.core.events import (
    BarEvent,
    BaseEvent,
    SignalEvent,
    SignalType,
    TickEvent,
    TimerEvent,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 触发器基类
# ---------------------------------------------------------------------------


class BaseTrigger(ABC):
    """
    触发器抽象基类。

    所有触发器必须实现：
      1. __init__():  接收 EventBus 和必要的依赖（依赖注入）。
      2. on_event():  事件回调接口，由 EventBus 调用。
      3. register():  向 EventBus 订阅感兴趣的事件类型。

    生命周期：
      1. 实例化触发器，注入依赖（EventBus, Context, 配置参数）。
      2. 调用 register() 订阅事件。
      3. EventBus 在事件到达时回调 on_event()。
      4. 触发器判定条件，若满足则 publish(SignalEvent)。
    """

    def __init__(self, event_bus: EventBus, trigger_id: str) -> None:
        """
        初始化触发器。

        Args:
            event_bus:  全局事件总线（用于订阅和发布）。
            trigger_id: 触发器唯一标识（用于信号溯源）。
        """
        self.event_bus = event_bus
        self.trigger_id = trigger_id
        logger.info(f"Trigger '{trigger_id}' initialized.")

    @abstractmethod
    def on_event(self, event: BaseEvent) -> None:
        """
        事件回调接口（由 EventBus 调用）。

        Args:
            event: 接收到的事件实例。
        """
        pass

    @abstractmethod
    def register(self) -> None:
        """
        向 EventBus 订阅感兴趣的事件类型。

        示例：
            >>> self.event_bus.subscribe(BarEvent, self.on_event)
        """
        pass

    def _emit_signal(
        self,
        symbol: str,
        signal_type: SignalType,
        payload: dict,
        rule_id: str = "",
    ) -> None:
        """
        向 EventBus 发射信号事件（内部辅助方法）。

        Args:
            symbol:      相关标的代码。
            signal_type: 信号类型。
            payload:     附加元数据。
            rule_id:     规则 ID（可选）。
        """
        signal = SignalEvent(
            source=self.trigger_id,
            symbol=symbol,
            signal_type=signal_type,
            payload=payload,
            rule_id=rule_id,
        )
        self.event_bus.publish(signal)
        logger.info(
            f"Signal emitted: {signal_type.value} from '{self.trigger_id}' "
            f"for {symbol} (event_id={signal.event_id})"
        )


# ---------------------------------------------------------------------------
# AST 规则触发器
# ---------------------------------------------------------------------------


class AstRuleTrigger(BaseTrigger):
    """
    基于 AST 的代数规则触发器。

    工作流程：
      1. 监听 BarEvent（或 TickEvent）。
      2. 调用 AST 引擎对规则树求值（传入 LocalContext）。
      3. 若求值结果为 True，发射 TRADE_OPPORTUNITY 信号。

    典型应用：
      - 技术指标组合条件：(RSI < 30) AND (MACD > 0) AND (close > sma)
      - 形态识别：(high > boll_upper) AND (volume > avg_volume * 2)

    Attributes:
        rule_tree:     AST 根节点（Node 实例）。
        local_context: 品种级上下文（存储 K 线窗口和指标）。
        rule_id:       规则 ID（用于回测归因）。
    """

    def __init__(
        self,
        event_bus: EventBus,
        trigger_id: str,
        rule_tree: Node,
        local_context: LocalContext,
        rule_id: str = "",
        bar_freq: str | None = None,
    ) -> None:
        """
        初始化 AST 规则触发器。

        Args:
            event_bus:     全局事件总线。
            trigger_id:    触发器 ID。
            rule_tree:     AST 根节点。
            local_context: 品种级上下文。
            rule_id:       规则 ID（可选）。
        """
        super().__init__(event_bus, trigger_id)
        self.rule_tree = rule_tree
        self.local_context = local_context
        self.rule_id = rule_id or trigger_id
        self.bar_freq = bar_freq

    def register(self) -> None:
        """订阅 BarEvent（利用 EventBus 的 Topic 机制精准路由）。"""
        self.event_bus.subscribe(
            BarEvent, self.on_event, symbol=self.local_context.symbol
        )
        logger.info(
            f"AstRuleTrigger '{self.trigger_id}' subscribed to BarEvent for '{self.local_context.symbol}'."
        )

    def on_event(self, event: BaseEvent) -> None:
        """
        BarEvent 回调：更新 Context 并求值规则树。

        Args:
            event: BarEvent 实例。
        """
        if not isinstance(event, BarEvent):
            return

        # 过滤：仅处理目标品种的 Bar
        if event.symbol != self.local_context.symbol:
            return

        # 可选：仅处理指定周期的 Bar
        if self.bar_freq is not None and event.freq != self.bar_freq:
            return

        # 更新 LocalContext（触发指标缓存失效）
        self.local_context.update_bar(event)

        # 求值规则树
        try:
            result = self.rule_tree.evaluate(self.local_context)
            logger.debug(
                f"Rule '{self.rule_id}' evaluated to {result} for {event.symbol}"
            )

            if result:
                # 条件满足，发射交易机会信号
                self._emit_signal(
                    symbol=event.symbol,
                    signal_type=SignalType.TRADE_OPPORTUNITY,
                    payload={
                        "bar_time": event.bar_time.isoformat(),
                        "close": event.close,
                        "rule_tree": repr(self.rule_tree),  # 用于审计
                    },
                    rule_id=self.rule_id,
                )
        except (TypeError, ValueError) as e:
            logger.debug(
                f"Rule '{self.rule_id}' skipped on {event.symbol} during warm-up: {e}"
            )
        except Exception as e:
            logger.exception(
                f"Rule evaluation failed for '{self.rule_id}' on {event.symbol}: {e}"
            )


# ---------------------------------------------------------------------------
# 持仓偏离触发器
# ---------------------------------------------------------------------------


class DeviationTrigger(BaseTrigger):
    """
    持仓偏离触发器（用于动态再平衡）。

    工作流程：
      1. 监听 TickEvent（或资金同步事件）。
      2. 从 LocalContext 读取 current_weight，从 GlobalContext 读取 target_weight。
      3. 计算偏离度：abs(current_weight - target_weight)。
      4. 若偏离 > threshold，发射 REBALANCE_TRIGGER 信号。

    典型应用：
      - 盘中动态再平衡：当某品种因价格波动导致权重偏离目标 > 5%，触发调仓。
      - 风控止损：当某品种权重超过上限（如 > 30%），触发减仓。

    Attributes:
        local_context:  品种级上下文（存储 current_weight）。
        global_context: 全局上下文（存储 target_weights 配置）。
        threshold:      偏离阈值（0.0 ~ 1.0，如 0.05 表示 5%）。
    """

    def __init__(
        self,
        event_bus: EventBus,
        trigger_id: str,
        local_context: LocalContext,
        global_context: GlobalContext,
        threshold: float = 0.05,
    ) -> None:
        """
        初始化持仓偏离触发器。

        Args:
            event_bus:      全局事件总线。
            trigger_id:     触发器 ID。
            local_context:  品种级上下文。
            global_context: 全局上下文。
            threshold:      偏离阈值（默认 5%）。
        """
        super().__init__(event_bus, trigger_id)
        self.local_context = local_context
        self.global_context = global_context
        self.threshold = threshold

        # 冷却锁与防抖期设定
        self._last_trigger_time: float = 0.0
        self._cooldown_seconds: float = 2.0

    def register(self) -> None:
        """订阅 TickEvent（精确路由至该标的）。"""
        self.event_bus.subscribe(
            TickEvent, self.on_event, symbol=self.local_context.symbol
        )
        logger.info(
            f"DeviationTrigger '{self.trigger_id}' subscribed to TickEvent for '{self.local_context.symbol}'."
        )

    def on_event(self, event: BaseEvent) -> None:
        """
        TickEvent 回调：计算持仓偏离并判定是否触发再平衡。

        Args:
            event: TickEvent 实例。
        """
        if not isinstance(event, TickEvent):
            return

        # 过滤：仅处理目标品种的 Tick
        if event.symbol != self.local_context.symbol:
            return

        # 更新 LocalContext
        self.local_context.update_tick(event)

        # 读取当前权重和目标权重
        current_weight = self.local_context.current_weight
        target_weights = self.global_context.get("target_weights", {})
        target_weight = target_weights.get(event.symbol, 0.0)

        # 计算偏离度
        deviation = abs(current_weight - target_weight)

        import math

        # 1. IEEE 754 浮点数精度保护：使用 isclose 防误触边缘值
        if (
            math.isclose(deviation, self.threshold, rel_tol=1e-9)
            or deviation <= self.threshold
        ):
            return

        # 2. 信号防抖冷却（Debounce Lock）
        current_ts = event.timestamp.timestamp()
        if current_ts - self._last_trigger_time < self._cooldown_seconds:
            # 冷却时间内，雪崩订单抑制
            return

        logger.debug(
            f"Deviation check for {event.symbol}: "
            f"current={current_weight:.4f}, target={target_weight:.4f}, "
            f"deviation={deviation:.4f}, threshold={self.threshold:.4f}"
        )

        # 更新防抖续期时间
        self._last_trigger_time = current_ts

        if deviation > self.threshold:
            # 偏离超阈值，发射再平衡信号
            self._emit_signal(
                symbol=event.symbol,
                signal_type=SignalType.REBALANCE_TRIGGER,
                payload={
                    "current_weight": current_weight,
                    "target_weight": target_weight,
                    "deviation": deviation,
                    "last_price": event.last_price,
                },
            )


# ---------------------------------------------------------------------------
# 定时触发器
# ---------------------------------------------------------------------------


class CronTrigger(BaseTrigger):
    """
    定时触发器（基于系统时间或 TimerEvent）。

    工作流程：
      1. 监听 TimerEvent（由外部 CronScheduler 发布）。
      2. 检查 timer_id 是否匹配。
      3. 若匹配，发射指定类型的信号（如 FUND_ALLOCATION）。

    典型应用：
      - 每日 14:30 触发资金分配指令。
      - 每周五收盘前触发持仓报告生成。
      - 每月初触发策略参数重新优化。

    Attributes:
        timer_id:      监听的定时器 ID（如 "DAILY_REBALANCE_1430"）。
        signal_type:   触发时发射的信号类型。
        signal_payload: 信号附加数据（可选）。
    """

    def __init__(
        self,
        event_bus: EventBus,
        trigger_id: str,
        timer_id: str,
        signal_type: SignalType = SignalType.FUND_ALLOCATION,
        signal_payload: Optional[dict] = None,
    ) -> None:
        """
        初始化定时触发器。

        Args:
            event_bus:      全局事件总线。
            trigger_id:     触发器 ID。
            timer_id:       监听的定时器 ID。
            signal_type:    触发时发射的信号类型。
            signal_payload: 信号附加数据（可选）。
        """
        super().__init__(event_bus, trigger_id)
        self.timer_id = timer_id
        self.signal_type = signal_type
        self.signal_payload = signal_payload or {}

    def register(self) -> None:
        """订阅 TimerEvent。"""
        self.event_bus.subscribe(TimerEvent, self.on_event)
        logger.info(
            f"CronTrigger '{self.trigger_id}' subscribed to TimerEvent "
            f"(timer_id='{self.timer_id}')"
        )

    def on_event(self, event: BaseEvent) -> None:
        """
        TimerEvent 回调：检查 timer_id 并发射信号。

        Args:
            event: TimerEvent 实例。
        """
        if not isinstance(event, TimerEvent):
            return

        # 过滤：仅处理目标定时器
        if event.timer_id != self.timer_id:
            return

        logger.info(
            f"CronTrigger '{self.trigger_id}' fired by timer '{self.timer_id}' "
            f"at {event.fired_at.isoformat()}"
        )

        # 发射信号（symbol 为空，表示全局信号）
        self._emit_signal(
            symbol="",
            signal_type=self.signal_type,
            payload={
                **self.signal_payload,
                "fired_at": event.fired_at.isoformat(),
                "timer_id": event.timer_id,
            },
        )


# ---------------------------------------------------------------------------
# 触发器工厂（可选扩展）
# ---------------------------------------------------------------------------


def create_ast_trigger(
    event_bus: EventBus,
    trigger_id: str,
    rule_tree: Node,
    local_context: LocalContext,
    rule_id: str = "",
    bar_freq: str | None = None,
) -> AstRuleTrigger:
    """
    工厂函数：创建并注册 AST 规则触发器。

    Args:
        event_bus:     全局事件总线。
        trigger_id:    触发器 ID。
        rule_tree:     AST 根节点。
        local_context: 品种级上下文。
        rule_id:       规则 ID（可选）。

    Returns:
        已注册的 AstRuleTrigger 实例。
    """
    trigger = AstRuleTrigger(
        event_bus,
        trigger_id,
        rule_tree,
        local_context,
        rule_id,
        bar_freq,
    )
    trigger.register()
    return trigger


def create_deviation_trigger(
    event_bus: EventBus,
    trigger_id: str,
    local_context: LocalContext,
    global_context: GlobalContext,
    threshold: float = 0.05,
) -> DeviationTrigger:
    """
    工厂函数：创建并注册持仓偏离触发器。

    Args:
        event_bus:      全局事件总线。
        trigger_id:     触发器 ID。
        local_context:  品种级上下文。
        global_context: 全局上下文。
        threshold:      偏离阈值（默认 5%）。

    Returns:
        已注册的 DeviationTrigger 实例。
    """
    trigger = DeviationTrigger(
        event_bus, trigger_id, local_context, global_context, threshold
    )
    trigger.register()
    return trigger


def create_cron_trigger(
    event_bus: EventBus,
    trigger_id: str,
    timer_id: str,
    signal_type: SignalType = SignalType.FUND_ALLOCATION,
    signal_payload: Optional[dict] = None,
) -> CronTrigger:
    """
    工厂函数：创建并注册定时触发器。

    Args:
        event_bus:      全局事件总线。
        trigger_id:     触发器 ID。
        timer_id:       监听的定时器 ID。
        signal_type:    触发时发射的信号类型。
        signal_payload: 信号附加数据（可选）。

    Returns:
        已注册的 CronTrigger 实例。
    """
    trigger = CronTrigger(event_bus, trigger_id, timer_id, signal_type, signal_payload)
    trigger.register()
    return trigger
