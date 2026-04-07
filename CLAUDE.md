# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running & Testing

Manage dependencies with uv. If not installed, install with `curl -LsSf https://astral.sh/uv/install.sh | sh`.

```bash
uv sync
# Run the full integration example (requires being in the repo root)
uv run -m examples.example_usage

# Run import tests
uv run tests/test_imports.py

# Run a specific example
uv run -m examples.full_integration_example
```

All Python files use absolute module imports (e.g., `from cep.core.events import ...`), so always run from the project root `/home/ubuntu/CEP`.

The NLP module (`nlp/nl_parser.py`) requires `ANTHROPIC_API_KEY` set in the environment and the `anthropic` package installed. It degrades gracefully if the SDK is absent.

## Architecture

This is a **Complex Event Processing (CEP)** system for quantitative trading (A-shares and futures), built on the ECA (Event–Condition–Action) pattern with a publish/subscribe event bus.

### Data Flow

```
MarketGateway → EventBus → Triggers → EventBus → Handlers
                               ↕
                           Context (状态黑板)
```

1. **MarketGateway** (`adapters/`) pushes `TickEvent` / `BarEvent` to the `EventBus`.
2. **Triggers** (`cep/triggers/`) subscribe to these events, read state from `Context`, and publish `SignalEvent` when conditions are met.
3. **Handlers** (e.g., `rebalance/rebalance_handler.py`) subscribe to `SignalEvent` and execute business logic.

### Core Packages

| Package | Purpose |
|---|---|
| `cep/core/` | Foundational layer: events, event bus, context |
| `cep/engine/` | AST rule evaluator |
| `cep/triggers/` | Trigger implementations (AST, Deviation, Cron) |
| `rebalance/` | Portfolio rebalance engine and triggers |
| `nlp/` | Natural language → JSON AST via Claude API |
| `adapters/` | External interfaces (market gateway, order gateway, config, frontend API) |

### Key Design Constraints

- **Triggers never call business logic directly.** They only emit `SignalEvent`. Downstream handlers decide what to do.
- **Dependency injection everywhere.** `EventBus`, `Context`, and config are constructor-injected — no module-level singletons.
- **Events are immutable** (`frozen=True` dataclasses). Never mutate an event after publishing.
- **EventBus uses weak references** (`weakref.WeakMethod` / `weakref.ref`) to prevent memory leaks. Keep trigger/handler objects alive by holding a reference in the calling scope.
- **EventBus routing is two-dimensional:** `{EventType: {symbol: set[handler_refs]}}`. Subscribe with `symbol=""` for global (all-symbol) subscription; subscribe with a specific symbol for per-instrument precision routing.

### Context System

`LocalContext` uses `__getattr__` to lazily compute technical indicators:
- Accessing `ctx.rsi` triggers the registered `compute_func` if not cached.
- Cache invalidates on every `update_bar()` call.
- `LocalContext` can transparently fall through to `GlobalContext` for macro data (VIX, total NAV, target weights).
- Indicator compute functions signature: `(bars: list[BarEvent]) -> Any`.

### Rebalance Engine (5-Step Calculation)

`rebalance/rebalance_engine.py`:
1. New target NAV = current NAV + new capital
2. Target market value per symbol = new NAV × target weight
3. Market value delta = target MV − current MV
4. Theoretical quantity change = MV delta / (price × multiplier)
5. Discrete rounding → integer order quantity

### Adding a New Trigger

Subclass `BaseTrigger` from `cep/triggers/triggers.py`:
```python
class MyTrigger(BaseTrigger):
    def register(self):
        self.event_bus.subscribe(BarEvent, self.on_event, symbol="600519.SH")

    def on_event(self, event):
        if condition_met:
            self._emit_signal(symbol, SignalType.TRADE_OPPORTUNITY, payload={...})
```
Always call `trigger.register()` after instantiation (or use the factory functions like `create_ast_trigger()`).

### AST Rule Building

```python
from cep.engine.ast_engine import build_and, build_comparison, Operator

rule = build_and(
    build_comparison("rsi", Operator.LT, 30),
    build_comparison("close", Operator.GT, "sma"),  # "sma" resolves via LocalContext
)
```

Rules can also be deserialized from JSON dicts via `parse_ast_from_dict(spec)`.

### DeviationTrigger Behavior

- Has a 2-second cooldown (`_cooldown_seconds`) to prevent signal avalanche on high-frequency ticks.
- Uses `math.isclose` for float boundary protection.
- Reads `target_weights` from `GlobalContext` keyed by symbol string.

## Module Imports

Public APIs are re-exported via `__init__.py` files:
- `from cep.core import EventBus, TickEvent, BarEvent, GlobalContext, LocalContext`
- `from cep.engine import Node, Operator, LogicalOp`
- `from cep.triggers import AstRuleTrigger, DeviationTrigger, CronTrigger`
- `from rebalance import RebalanceEngine, PortfolioContext, RebalanceHandler, FundFlowTrigger, MonthlyRebalanceTrigger, PortfolioDeviationTrigger`
- `from nlp import parse_natural_language, validate_and_suggest, IndicatorMeta`

## Coding Guidelines
- Run `ruff` and `pyright` before every commit, and fix all reported errors.
- A change is not ready to commit if `ruff` reports violations or `pyright` reports type-checking errors.
- Recommended pre-commit verification from the repo root:
