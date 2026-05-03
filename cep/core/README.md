# CEP Core

This package holds the foundational runtime pieces for the CEP engine:

- `events.py`: immutable event payloads such as `TickEvent`, `BarEvent`, and `SignalEvent`
- `event_bus.py`: publish/subscribe routing layer
- `context.py`: `GlobalContext` and `LocalContext`
- `remote_bus.py`: remote event bus support

## Context model

The engine uses a two-layer context design:

- `GlobalContext`: cross-symbol state such as macro data, account-level values, or target weights
- `LocalContext`: per-symbol runtime state used by triggers and user-authored signals

`LocalContext` is the object exposed to Python signal code as `self.ctx`.

It provides:

- public runtime fields like `symbol`, `current_weight`, `latest_tick`
- recent bar access through `get_bars()`
- passthrough access to the latest `BarEvent` fields such as `ctx.close`, `ctx.high`, `ctx.volume`
- optional passthrough access to `TickEvent` fields when a latest tick exists
- lazy indicators from `DEFAULT_INDICATOR_REGISTRY`, such as `ctx.rsi` and `ctx.sma`

## Lazy indicator behavior

`LocalContext.__getattr__()` is the key mechanism:

1. If the requested name matches the latest bar field, return that
2. Else if it matches the latest tick field, return that
3. Else if it matches a cached indicator value, return the cache
4. Else if it matches a registered indicator, compute it from `bar_window`, cache it, and return it
5. Else if a `GlobalContext` is attached, try that
6. Otherwise raise `AttributeError`

Indicator cache invalidation happens on every `update_bar()` call.

## Single source of truth for `ctx` docs

The `ctx` documentation shown in the frontend is now sourced from Python, not hardcoded in Vue.

The source of truth lives in `context.py`:

- public `LocalContext` fields are discovered from the Python class/runtime instance
- default indicator docs come from `DEFAULT_INDICATOR_REGISTRY`
- bar passthrough docs come from the `BarEvent` dataclass
- tick passthrough docs come from the `TickEvent` dataclass
- guide notes and example code are also defined in Python

`context.py` exposes:

- `get_local_context_reference()`

That function returns a frontend-friendly schema used by:

- `GET /api/signals/ctx-schema` in `adapters/flask_app.py`
- `frontend/views/SignalCtxGuideView.vue`

This means Python-side expansions to the runtime surface automatically flow into the in-app documentation.

## When adding new `ctx` capabilities

If you add a new `LocalContext` field:

1. Add the runtime field in `LocalContext`
2. Add or update its description in `LOCAL_CONTEXT_FIELD_DOCS`

If you add a new default indicator:

1. Register it in `DEFAULT_INDICATOR_REGISTRY`
2. Add or update its description in `INDICATOR_DOCS`

If you add new passthrough event fields:

1. Update the corresponding event dataclass in `events.py`
2. Add or update the matching descriptions in `BAR_EVENT_FIELD_DOCS` or `TICK_EVENT_FIELD_DOCS`

The frontend guide should then pick the new shape up automatically through the API.
