# User-Coded Signal Rules

This v1 feature lets internal researchers save Python `Signal` classes, validate them, backtest them, and enable them for live monitoring.

## Contract

```python
class Signal:
    name = "沪金RSI超卖"
    symbols = ["au2506"]
    bar_freq = "1m"

    def __init__(self, ctx):
        self.ctx = ctx

    def on_bar(self, bar):
        if self.ctx.rsi is not None and self.ctx.rsi < 30:
            return {"side": "BUY", "reason": "rsi_oversold", "price": bar.close}
        return None
```

`ctx` is `LocalContext`, so existing lazy indicators such as `ctx.rsi` and latest bar fields such as `ctx.close` are available. `on_bar` must return either `None` or a dictionary copied into `SignalEvent.payload`. `side` is optional; when present it must be `BUY` or `SELL`.

## Runtime

- Code is executed in-process after AST contract checks.
- Imports and several dynamic Python constructs are blocked.
- The loader exposes only a small builtin allowlist and `OrderSide`.
- Runtime errors are captured as diagnostics and do not crash the event bus.

## APIs

- `GET /api/signals`
- `POST /api/signals`
- `PUT /api/signals/<id>`
- `POST /api/signals/<id>/status`
- `POST /api/signals/validate`
- `POST /api/backtests/run-user-signal`
- `GET /api/signals/live/recent`
- `GET /api/signals/live/stream`

Live monitoring subscribes to Redis-published `BarEvent` objects on `CEP_REDIS_CHANNEL` (`cep_events` by default). Tick-to-bar aggregation is expected to happen upstream.
