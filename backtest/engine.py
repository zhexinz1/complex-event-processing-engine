"""回测引擎编排层。"""

from __future__ import annotations

import logging
import time

from typing import Any, Iterable, Optional

from cep.core.context import DEFAULT_INDICATOR_REGISTRY, LocalContext
from cep.core.event_bus import EventBus
from cep.core.events import BarEvent, TickEvent
from cep.engine.ast_engine import Node
from cep.triggers.triggers import AstRuleTrigger

from .aggregation import MultiTimeframeBarAggregator
from .broker import ExecutionTiming, SimulatedBroker, _validate_execution_timing
from .models import BacktestResult
from .parser import HistoricalDataParser
from .portfolio import PortfolioLedger
from .queue import Dispatcher, EventQueue
from .recorder import PerformanceRecorder
from .trade_log import write_backtest_trade_log


class BacktestEngine:
    """真实事件驱动语义下的回测引擎。"""

    def __init__(
        self,
        initial_cash: float = 1_000_000.0,
        base_bar_freq: str = "1m",
        aggregate_freqs: Optional[list[str]] = None,
        contract_multipliers: Optional[dict[str, float]] = None,
        default_order_quantity: float = 1.0,
        commission_rate: float = 0.0,
        write_trade_log: bool = False,
        execution_timing: ExecutionTiming = "next_bar",
        target_asset_size: float | None = None,
    ) -> None:
        execution_timing = _validate_execution_timing(execution_timing)
        self.initial_cash = initial_cash
        self.event_bus = EventBus()
        self.event_queue = EventQueue()
        self.parser = HistoricalDataParser()
        self.dispatcher = Dispatcher(self.event_bus)
        self.portfolio = PortfolioLedger(
            event_bus=self.event_bus,
            initial_cash=initial_cash,
            contract_multipliers=contract_multipliers,
        )
        self.recorder = PerformanceRecorder(self.event_bus, self.portfolio)
        self.broker = SimulatedBroker(
            event_bus=self.event_bus,
            portfolio=self.portfolio,
            default_quantity=default_order_quantity,
            commission_rate=commission_rate,
            contract_multipliers=contract_multipliers,
            execution_timing=execution_timing,
            target_asset_size=target_asset_size or initial_cash,
        )
        self.aggregator = MultiTimeframeBarAggregator(
            event_bus=self.event_bus,
            base_freq=base_bar_freq,
            target_freqs=aggregate_freqs,
        )
        self.write_trade_log = write_trade_log
        self.execution_timing = execution_timing

        # EventBus 保存弱引用，必须显式持有这些对象。
        self._components = [self.portfolio, self.recorder, self.broker, self.aggregator]
        self._triggers: list[AstRuleTrigger] = []
        self._contexts: dict[str, LocalContext] = {}

    def register_component(self, component: object) -> object:
        """Keep an event-bus component strongly referenced for the engine lifetime."""
        self._components.append(component)
        return component

    def register_ast_rule(
        self,
        symbol: str,
        rule_tree: Node,
        trigger_id: str,
        rule_id: str = "",
        bar_freq: str | None = "1m",
        window_size: int = 100,
    ) -> AstRuleTrigger:
        """注册一个基于 AST 的回测规则。"""
        local_context = LocalContext(
            symbol=symbol,
            window_size=window_size,
            indicator_registry=DEFAULT_INDICATOR_REGISTRY,
        )
        trigger = AstRuleTrigger(
            event_bus=self.event_bus,
            trigger_id=trigger_id,
            rule_tree=rule_tree,
            local_context=local_context,
            rule_id=rule_id or trigger_id,
            bar_freq=bar_freq,
        )
        trigger.register()

        self._contexts[symbol] = local_context
        self._triggers.append(trigger)
        return trigger

    def ingest_bars(
        self,
        raw_bars: Iterable[BarEvent | dict[str, Any]],
        *,
        assume_sorted: bool = False,
    ) -> None:
        """导入历史 Bar 到事件队列。"""
        parsed = self.parser.parse_bars(raw_bars, assume_sorted=assume_sorted)
        if assume_sorted:
            self.event_queue.extend_sorted(parsed)
            return
        self.event_queue.extend(parsed)

    def get_context(self, symbol: str) -> Optional[LocalContext]:
        """返回指定标的对应的 LocalContext。"""
        return self._contexts.get(symbol)

    def run(self) -> BacktestResult:
        """运行回测。"""
        _logger = logging.getLogger(__name__)
        market_events_processed = 0
        last_timestamp = None
        total_events = len(self.event_queue)
        t0 = time.monotonic()
        _logger.info("BacktestEngine.run(): starting, total_events=%s", total_events)

        while not self.event_queue.empty():
            next_event = self.event_queue.peek()

            # 在分发前捕获快照，记录"成交前"的账户状态
            if isinstance(next_event, (BarEvent, TickEvent)):
                self.recorder.capture_snapshot(next_event.timestamp)

            event = self.dispatcher.dispatch_next(self.event_queue)

            if isinstance(event, (BarEvent, TickEvent)):
                market_events_processed += 1
                last_timestamp = event.timestamp
                if market_events_processed % 50_000 == 0:
                    elapsed = time.monotonic() - t0
                    pct = (
                        market_events_processed / total_events * 100
                        if total_events
                        else 0
                    )
                    _logger.info(
                        "BacktestEngine progress: %d/%d events (%.1f%%) elapsed=%.1fs",
                        market_events_processed,
                        total_events,
                        pct,
                        elapsed,
                    )

        self.aggregator.flush()
        self.broker.finalize()
        elapsed = time.monotonic() - t0
        _logger.info(
            "BacktestEngine.run(): engine loop finished, events=%d signals=%d trades=%d elapsed=%.1fs",
            market_events_processed,
            len(self.recorder.signals),
            len(self.recorder.trades),
            elapsed,
        )

        # 记录最后一步执行后的状态，防止最终权益变化未能反映在序列中
        if last_timestamp is not None:
            self.recorder.capture_snapshot(last_timestamp)

        result = BacktestResult(
            market_events_processed=market_events_processed,
            signals=list(self.recorder.signals),
            orders=list(self.recorder.orders),
            trades=list(self.recorder.trades),
            snapshots=list(self.recorder.snapshots),
            initial_cash=self.initial_cash,
            final_cash=self.portfolio.cash,
            final_market_value=self.portfolio.market_value,
            final_equity=self.portfolio.equity,
            realized_pnl=self.portfolio.realized_pnl,
            unrealized_pnl=self.portfolio.unrealized_pnl,
            positions=self.portfolio.snapshot_positions(),
        )
        if self.write_trade_log:
            log_path = write_backtest_trade_log(result)
            result.trade_log_path = str(log_path)
        return result
