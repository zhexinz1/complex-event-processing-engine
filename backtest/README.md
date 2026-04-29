# Backtest Module

The `backtest/` package provides an event-driven backtesting engine for the CEP system.

Its purpose is not just to "replay bars and call strategy functions", but to preserve the same architectural style used in the live system:

- historical market data is converted into standard events
- those events are pushed through an event queue
- the queue is dispatched into the shared `EventBus`
- triggers, broker simulation, portfolio accounting, and performance recording all react by subscribing to events

That means backtests use the same flow shape as production:

```text
HistoricalDataParser
  -> EventQueue
  -> Dispatcher
  -> EventBus
  -> Triggers / Aggregator / Broker / Portfolio / Recorder
```

## Why This Matters

This design keeps backtest behavior close to real behavior.

Instead of introducing a separate "strategy callback only" execution path, we reuse the CEP event model:

- `BarEvent` / `TickEvent` represent market data
- `SignalEvent` represents trigger output
- `OrderEvent` represents simulated order lifecycle updates
- `TradeEvent` represents simulated fills

Because the `EventBus` is used in backtest just like in the live engine, we get a few important benefits:

- rule triggers are exercised in the same way as production
- event ordering is explicit and inspectable
- downstream consumers can be tested with realistic event flows
- backtest and live architecture stay aligned instead of drifting apart

## Module Layout

- `engine.py`: top-level `BacktestEngine` orchestration
- `parser.py`: historical data parsing into standard events
- `queue.py`: priority queue and dispatcher
- `aggregation.py`: multi-timeframe bar aggregation
- `broker.py`: simulated broker that turns signals into order/trade events
- `portfolio.py`: portfolio ledger that updates cash, positions, and equity from trades
- `recorder.py`: captures signals, orders, trades, and equity snapshots
- `models.py`: result and state models

## Core Flow

1. Load historical data as `BarEvent`s.
2. Push those events into `EventQueue`.
3. `Dispatcher` publishes each event to `EventBus`.
4. `AstRuleTrigger` listens for relevant market events and emits `SignalEvent`.
5. `SimulatedBroker` listens for signals and emits `OrderEvent` and `TradeEvent`.
6. `PortfolioLedger` listens for trade events and updates positions and cash.
7. `PerformanceRecorder` listens across the bus and records the full path.

## Example

See:

- `examples/backtest_example.py`
- `tests/test_mock_backtest.py`

Typical usage:

```python
from backtest import BacktestEngine
from cep.engine.ast_engine import Operator, build_and, build_comparison

engine = BacktestEngine(initial_cash=1_000_000.0)

rule_tree = build_and(
    build_comparison("rsi", Operator.LT, 30),
    build_comparison("close", Operator.GT, "sma"),
)

engine.register_ast_rule(
    symbol="600519.SH",
    rule_tree=rule_tree,
    trigger_id="BACKTEST_RULE",
    bar_freq="1m",
)

engine.ingest_bars(bars)
result = engine.run()
```

## Current Scope

The current module supports:

- event-driven bar replay
- local `adjusted_main_contract` CSV history as a reusable 1-minute data source
- AST-triggered signal generation
- simulated market-order execution
- invalid-order rejection for malformed, over-budget, and over-positioned trades
- portfolio cash/position updates
- equity snapshots and event capture

The current module does not yet fully model:

- limit orders
- partial fills
- slippage and latency models
- advanced performance analytics
- risk engine constraints during backtest

Those can be added incrementally without changing the central design: everything should continue to flow through `EventBus`.

## Next step
- support adding new strategies on the fly
- support data selection (stock, commodity, data interval)

## Local Historical CSV

The repository supports direct backtest loading from `adjusted_main_contract/*.csv`.
There is no intermediate SQLite build step: backtests read the requested symbol CSVs directly.

Runtime entry points that understand this data source:

- `backtest.preset_strategies.run_preset_backtest(..., data_source="adjusted_main_contract")`
- `signals.runtime.run_user_signal_backtest(..., data_source="adjusted_main_contract")`

## Trade Logs

Each completed backtest now writes a JSON trade log into `backtest/logs/`.
That folder is gitignored so runs stay local to the workspace.

The log includes:

- summary metrics
- positions
- signals
- orders, including rejected orders
- trades
- equity curve
