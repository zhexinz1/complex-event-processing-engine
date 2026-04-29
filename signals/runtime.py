"""Runtime support for researcher-authored Python signals."""

from __future__ import annotations

import ast
import json
import logging
import pickle
import queue
import threading
import time
from collections import deque
from datetime import datetime
from types import MappingProxyType
from typing import Any, Iterable

from backtest.engine import BacktestEngine
from backtest.preset_strategies import (
    PBX_MA_PRESET_CLOSES,
    fetch_adjusted_main_contract_bars,
    fetch_adjusted_main_contract_bars_multi,
    fetch_cross_section_tushare_bars,
    fetch_tushare_daily_bars,
    make_mock_bars,
    normalize_symbol_group,
    serialize_backtest_result,
)
from adapters.contract_config import get_contract_multiplier
from cep.core.context import DEFAULT_INDICATOR_REGISTRY, LocalContext
from cep.core.event_bus import EventBus
from cep.core.events import BarEvent, BaseEvent, OrderSide, SignalEvent, SignalType
from cep.triggers import BaseTrigger

from .models import SignalDiagnostic

logger = logging.getLogger(__name__)

ALLOWED_BUILTINS = MappingProxyType(
    {
        "abs": abs,
        "all": all,
        "any": any,
        "bool": bool,
        "dict": dict,
        "enumerate": enumerate,
        "float": float,
        "int": int,
        "len": len,
        "list": list,
        "max": max,
        "min": min,
        "range": range,
        "round": round,
        "str": str,
        "sum": sum,
        "tuple": tuple,
        "zip": zip,
        "__build_class__": __build_class__,
    }
)


class SignalContractValidator:
    """Validate the v1 Signal class contract before execution."""

    REQUIRED_METADATA = {"name", "symbols", "bar_freq"}
    BLOCKED_NODES = (
        ast.Import,
        ast.ImportFrom,
        ast.Global,
        ast.Nonlocal,
        ast.With,
        ast.AsyncWith,
        ast.AsyncFunctionDef,
        ast.Lambda,
        ast.Try,
        ast.Raise,
    )

    def validate(self, source_code: str) -> tuple[bool, list[SignalDiagnostic]]:
        diagnostics: list[SignalDiagnostic] = []
        logger.debug("Validating user signal source: %s characters", len(source_code))
        try:
            tree = ast.parse(source_code)
        except SyntaxError as exc:
            logger.debug("User signal syntax validation failed at line %s: %s", exc.lineno, exc.msg)
            diagnostics.append(
                SignalDiagnostic(
                    level="error",
                    message=exc.msg,
                    line=exc.lineno,
                )
            )
            return False, diagnostics

        for node in ast.walk(tree):
            if isinstance(node, self.BLOCKED_NODES):
                diagnostics.append(
                    SignalDiagnostic(
                        level="error",
                        message=f"{type(node).__name__} is not allowed in user signals",
                        line=getattr(node, "lineno", None),
                    )
                )

        signal_class = self._find_signal_class(tree)
        if signal_class is None:
            logger.debug("User signal validation failed: missing class Signal")
            diagnostics.append(SignalDiagnostic(level="error", message="source must define class Signal"))
            return False, diagnostics

        metadata = {
            node.targets[0].id
            for node in signal_class.body
            if isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
        }
        missing = sorted(self.REQUIRED_METADATA - metadata)
        if missing:
            diagnostics.append(
                SignalDiagnostic(
                    level="error",
                    message=f"class Signal is missing metadata: {', '.join(missing)}",
                    line=signal_class.lineno,
                )
            )

        methods = {node.name: node for node in signal_class.body if isinstance(node, ast.FunctionDef)}
        self._validate_method(methods, "__init__", ["self", "ctx"], diagnostics)
        self._validate_method(methods, "on_bar", ["self", "bar"], diagnostics)

        is_valid = not any(item.level == "error" for item in diagnostics)
        logger.debug(
            "User signal validation finished: valid=%s diagnostics=%s",
            is_valid,
            len(diagnostics),
        )
        return is_valid, diagnostics

    def _find_signal_class(self, tree: ast.Module) -> ast.ClassDef | None:
        for node in tree.body:
            if isinstance(node, ast.ClassDef) and node.name == "Signal":
                return node
        return None

    def _validate_method(
        self,
        methods: dict[str, ast.FunctionDef],
        name: str,
        expected_args: list[str],
        diagnostics: list[SignalDiagnostic],
    ) -> None:
        method = methods.get(name)
        if method is None:
            diagnostics.append(SignalDiagnostic(level="error", message=f"class Signal must define {name}()", line=None))
            return
        actual_args = [arg.arg for arg in method.args.args]
        if actual_args[: len(expected_args)] != expected_args or len(actual_args) != len(expected_args):
            diagnostics.append(
                SignalDiagnostic(
                    level="error",
                    message=f"{name} signature must be ({', '.join(expected_args)})",
                    line=method.lineno,
                )
            )


def load_signal_class(source_code: str) -> tuple[type, list[SignalDiagnostic]]:
    """Validate and execute signal source, returning the Signal class."""

    logger.debug("Loading user signal class")
    validator = SignalContractValidator()
    is_valid, diagnostics = validator.validate(source_code)
    if not is_valid:
        logger.debug("User signal class load blocked by contract diagnostics")
        raise ValueError(json.dumps([item.to_dict() for item in diagnostics], ensure_ascii=False))

    globals_dict: dict[str, Any] = {
        "__builtins__": ALLOWED_BUILTINS,
        "__name__": "user_signal",
        "OrderSide": OrderSide,
    }
    locals_dict: dict[str, Any] = {}
    exec(compile(source_code, "<user_signal>", "exec"), globals_dict, locals_dict)
    signal_class = locals_dict.get("Signal")
    if not isinstance(signal_class, type):
        raise ValueError("source must define class Signal")
    diagnostics.extend(_validate_runtime_metadata(signal_class))
    errors = [item for item in diagnostics if item.level == "error"]
    if errors:
        logger.debug("User signal class load blocked by runtime metadata diagnostics")
        raise ValueError(json.dumps([item.to_dict() for item in diagnostics], ensure_ascii=False))
    logger.info(
        "Loaded user signal class: name=%s symbols=%s bar_freq=%s",
        getattr(signal_class, "name", ""),
        getattr(signal_class, "symbols", []),
        getattr(signal_class, "bar_freq", ""),
    )
    return signal_class, diagnostics


def _validate_runtime_metadata(signal_class: type) -> list[SignalDiagnostic]:
    diagnostics: list[SignalDiagnostic] = []
    name = getattr(signal_class, "name", "")
    symbols = getattr(signal_class, "symbols", [])
    bar_freq = getattr(signal_class, "bar_freq", "")
    if not isinstance(name, str) or not name.strip():
        diagnostics.append(SignalDiagnostic(level="error", message="Signal.name must be a non-empty string"))
    if not isinstance(symbols, list) or not symbols or not all(isinstance(item, str) and item.strip() for item in symbols):
        diagnostics.append(SignalDiagnostic(level="error", message="Signal.symbols must be a non-empty list of strings"))
    if not isinstance(bar_freq, str) or not bar_freq.strip():
        diagnostics.append(SignalDiagnostic(level="error", message="Signal.bar_freq must be a non-empty string"))
    return diagnostics


class UserSignalTrigger(BaseTrigger):
    """Adapt a researcher Signal class into the CEP trigger contract."""

    def __init__(
        self,
        event_bus: EventBus,
        trigger_id: str,
        signal_class: type,
        symbols: list[str] | None = None,
        bar_freq: str | None = None,
        window_size: int = 100,
    ) -> None:
        super().__init__(event_bus, trigger_id)
        self.signal_class = signal_class
        self.symbols = symbols or list(getattr(signal_class, "symbols", []))
        self.bar_freq = bar_freq or str(getattr(signal_class, "bar_freq", "1m"))
        self.diagnostics: list[SignalDiagnostic] = []
        self._contexts = {
            symbol: LocalContext(
                symbol=symbol,
                window_size=window_size,
                indicator_registry=DEFAULT_INDICATOR_REGISTRY,
            )
            for symbol in self.symbols
        }
        self._instances = {
            symbol: signal_class(self._contexts[symbol])
            for symbol in self.symbols
        }
        logger.info(
            "UserSignalTrigger initialized: trigger_id=%s symbols=%s bar_freq=%s",
            self.trigger_id,
            self.symbols,
            self.bar_freq,
        )

    def register(self) -> None:
        for symbol in self.symbols:
            self.event_bus.subscribe(BarEvent, self.on_event, symbol=symbol)
        logger.info("UserSignalTrigger registered: trigger_id=%s subscriptions=%s", self.trigger_id, len(self.symbols))

    def on_event(self, event: BaseEvent) -> None:
        if not isinstance(event, BarEvent):
            return
        if event.symbol not in self._contexts or event.freq != self.bar_freq:
            logger.debug(
                "UserSignalTrigger ignored bar: trigger_id=%s symbol=%s freq=%s expected_symbols=%s expected_freq=%s",
                self.trigger_id,
                event.symbol,
                event.freq,
                self.symbols,
                self.bar_freq,
            )
            return

        ctx = self._contexts[event.symbol]
        ctx.update_bar(event)
        logger.debug(
            "UserSignalTrigger evaluating bar: trigger_id=%s symbol=%s bar_time=%s close=%.4f bars=%s",
            self.trigger_id,
            event.symbol,
            event.bar_time.isoformat(),
            event.close,
            len(ctx.bar_window),
        )
        try:
            result = self._instances[event.symbol].on_bar(event)
        except Exception as exc:
            logger.exception("User signal on_bar failed: trigger_id=%s symbol=%s", self.trigger_id, event.symbol)
            self.diagnostics.append(
                SignalDiagnostic(
                    level="error",
                    message=f"on_bar failed: {exc}",
                    symbol=event.symbol,
                    timestamp=event.timestamp.isoformat(),
                )
            )
            return

        if result is None:
            logger.debug(
                "UserSignalTrigger produced no signal: trigger_id=%s symbol=%s bar_time=%s",
                self.trigger_id,
                event.symbol,
                event.bar_time.isoformat(),
            )
            return
        if not isinstance(result, dict):
            logger.warning(
                "User signal returned invalid payload type: trigger_id=%s symbol=%s type=%s",
                self.trigger_id,
                event.symbol,
                type(result).__name__,
            )
            self.diagnostics.append(
                SignalDiagnostic(
                    level="error",
                    message="on_bar must return dict or None",
                    symbol=event.symbol,
                    timestamp=event.timestamp.isoformat(),
                )
            )
            return

        payload = dict(result)
        side = payload.get("side")
        if side is not None:
            side_text = str(side).upper()
            if side_text not in {OrderSide.BUY.value, OrderSide.SELL.value}:
                logger.warning(
                    "User signal returned invalid side: trigger_id=%s symbol=%s side=%s",
                    self.trigger_id,
                    event.symbol,
                    side,
                )
                self.diagnostics.append(
                    SignalDiagnostic(
                        level="error",
                        message="payload.side must be BUY or SELL when provided",
                        symbol=event.symbol,
                        timestamp=event.timestamp.isoformat(),
                    )
                )
                return
            payload["side"] = side_text

        payload.setdefault("bar_time", event.bar_time.isoformat())
        payload.setdefault("close", event.close)
        logger.info(
            "UserSignalTrigger emitting signal: trigger_id=%s symbol=%s side=%s reason=%s close=%.4f",
            self.trigger_id,
            event.symbol,
            payload.get("side", "ALERT"),
            payload.get("reason", ""),
            event.close,
        )
        signal = SignalEvent(
            source=self.trigger_id,
            symbol=event.symbol,
            signal_type=SignalType.TRADE_OPPORTUNITY,
            payload=payload,
            rule_id=self.trigger_id,
            timestamp=event.timestamp,
        )
        self.event_bus.publish(signal)
        logger.info(
            "User signal event published: trigger_id=%s symbol=%s event_id=%s timestamp=%s",
            self.trigger_id,
            event.symbol,
            signal.event_id,
            signal.timestamp.isoformat(),
        )


def run_user_signal_backtest(
    source_code: str,
    data_source: str = "mock",
    ts_code: str | None = None,
    symbols: Any = None,
    start_date: str | None = None,
    end_date: str | None = None,
    initial_cash: float = 1_000_000.0,
    write_trade_log: bool = True,
) -> dict[str, Any]:
    """Run a user-authored Signal class through BacktestEngine."""

    logger.info(
        "Starting user signal backtest: data_source=%s ts_code=%s symbols=%s start_date=%s end_date=%s initial_cash=%.2f",
        data_source,
        ts_code,
        symbols,
        start_date,
        end_date,
        initial_cash,
    )
    signal_class, diagnostics = load_signal_class(source_code)
    signal_symbols = list(getattr(signal_class, "symbols"))
    bar_freq = str(getattr(signal_class, "bar_freq"))

    if data_source == "mock":
        symbol = signal_symbols[0]
        bars = make_mock_bars(symbol, PBX_MA_PRESET_CLOSES)
        run_symbols = [symbol]
        effective_freq = "1m"
    elif data_source == "adjusted_main_contract":
        if not start_date or not end_date:
            raise ValueError("adjusted_main_contract 回测需要 start_date、end_date")
        run_symbols = normalize_symbol_group(symbols, use_tushare_format=False) if symbols else [symbol.upper() for symbol in signal_symbols]
        if len(run_symbols) == 1:
            bars = fetch_adjusted_main_contract_bars(run_symbols[0], start_date, end_date)
        else:
            bars = fetch_adjusted_main_contract_bars_multi(run_symbols, start_date, end_date)
        effective_freq = "1m"
    elif data_source == "tushare":
        if not start_date or not end_date:
            raise ValueError("Tushare 回测需要 start_date、end_date")
        run_symbols = normalize_symbol_group(symbols) if symbols else signal_symbols
        if len(run_symbols) == 1:
            bars = fetch_tushare_daily_bars(ts_code or run_symbols[0], start_date, end_date)
        else:
            bars = fetch_cross_section_tushare_bars(run_symbols, start_date, end_date)
        effective_freq = "1d"
    else:
        raise ValueError(f"Unsupported backtest data source: {data_source}")

    logger.info(
        "Prepared user signal backtest data: bars=%s run_symbols=%s effective_freq=%s signal_bar_freq=%s",
        len(bars),
        run_symbols,
        effective_freq,
        bar_freq,
    )
    multiplier_symbols = {bar.symbol for bar in bars} or set(run_symbols)
    contract_multipliers = {
        symbol: float(get_contract_multiplier(symbol))
        for symbol in multiplier_symbols
    }
    engine = BacktestEngine(
        initial_cash=initial_cash,
        base_bar_freq=effective_freq,
        contract_multipliers=contract_multipliers,
        write_trade_log=write_trade_log,
    )
    trigger = UserSignalTrigger(
        event_bus=engine.event_bus,
        trigger_id=f"USER_SIGNAL_{getattr(signal_class, 'name', 'Signal')}",
        signal_class=signal_class,
        symbols=run_symbols,
        bar_freq=effective_freq if data_source != "mock" else bar_freq,
    )
    trigger.register()
    engine._components.append(trigger)
    engine.ingest_bars(bars, assume_sorted=True)
    result = engine.run()
    payload = serialize_backtest_result(result)
    payload["diagnostics"] = [item.to_dict() for item in [*diagnostics, *trigger.diagnostics]]
    logger.info(
        "Finished user signal backtest: market_events=%s signals=%s trades=%s diagnostics=%s final_equity=%.2f",
        payload["market_events_processed"],
        len(payload["signals"]),
        len(payload["trades"]),
        len(payload["diagnostics"]),
        payload["final_equity"],
    )
    return payload


def serialize_signal_event(signal: SignalEvent) -> dict[str, Any]:
    """Convert a SignalEvent to JSON-ready data."""

    return {
        "event_id": signal.event_id,
        "timestamp": signal.timestamp.isoformat(),
        "symbol": signal.symbol,
        "source": signal.source,
        "rule_id": signal.rule_id,
        "signal_type": signal.signal_type.value,
        "payload": signal.payload,
    }


class LiveSignalMonitor:
    """In-process live signal monitor with an SSE fanout queue."""

    def __init__(self, event_bus: EventBus | None = None, max_recent: int = 200) -> None:
        self.event_bus = event_bus or EventBus()
        self.recent_signals: deque[dict[str, Any]] = deque(maxlen=max_recent)
        self.diagnostics: deque[dict[str, Any]] = deque(maxlen=max_recent)
        self._triggers: dict[int, UserSignalTrigger] = {}
        self._listeners: list[queue.Queue[dict[str, Any]]] = []
        self._lock = threading.Lock()
        self._redis_thread: threading.Thread | None = None
        self.event_bus.subscribe(SignalEvent, self._on_signal)

    def load_definitions(self, definitions: Iterable[Any]) -> None:
        with self._lock:
            self._triggers.clear()
            for definition in definitions:
                if definition.id is None:
                    continue
                try:
                    signal_class, diagnostics = load_signal_class(definition.source_code)
                    trigger = UserSignalTrigger(
                        event_bus=self.event_bus,
                        trigger_id=f"USER_SIGNAL_{definition.id}",
                        signal_class=signal_class,
                        symbols=definition.symbols,
                        bar_freq=definition.bar_freq,
                    )
                    trigger.register()
                    self._triggers[definition.id] = trigger
                    for item in diagnostics:
                        self.diagnostics.append(item.to_dict())
                except Exception as exc:
                    self.diagnostics.append(
                        {
                            "level": "error",
                            "message": f"加载信号 {definition.name} 失败: {exc}",
                            "timestamp": datetime.now().isoformat(),
                        }
                    )

    def publish_bar(self, bar: BarEvent) -> None:
        self.event_bus.publish(bar)

    def start_redis_subscriber(self, redis_url: str, channel: str = "cep_events") -> None:
        """Subscribe to Redis-published BarEvent objects for live monitoring."""

        if self._redis_thread and self._redis_thread.is_alive():
            return
        self._redis_thread = threading.Thread(
            target=self._redis_loop,
            args=(redis_url, channel),
            daemon=True,
            name="live-signal-bar-subscriber",
        )
        self._redis_thread.start()

    def _redis_loop(self, redis_url: str, channel: str) -> None:
        try:
            import redis

            client = redis.from_url(redis_url)
            pubsub = client.pubsub()
            pubsub.subscribe(channel)
            logger.info("[LiveSignalMonitor] Redis subscriber connected: channel=%s", channel)
            for message in pubsub.listen():
                if message.get("type") != "message":
                    continue
                try:
                    event = pickle.loads(message["data"])
                except Exception as exc:
                    logger.warning("[LiveSignalMonitor] failed to decode Redis event: %s", exc)
                    continue
                if isinstance(event, BarEvent):
                    self.publish_bar(event)
        except Exception as exc:
            logger.error("[LiveSignalMonitor] Redis subscriber exited: %s", exc)

    def add_listener(self) -> queue.Queue[dict[str, Any]]:
        listener: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=100)
        with self._lock:
            self._listeners.append(listener)
        return listener

    def remove_listener(self, listener: queue.Queue[dict[str, Any]]) -> None:
        with self._lock:
            if listener in self._listeners:
                self._listeners.remove(listener)

    def get_recent(self) -> list[dict[str, Any]]:
        return list(self.recent_signals)

    def stream(self, listener: queue.Queue[dict[str, Any]]):
        while True:
            try:
                item = listener.get(timeout=15)
                yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
            except queue.Empty:
                yield f": heartbeat {int(time.time())}\n\n"

    def _on_signal(self, signal: SignalEvent) -> None:
        item = serialize_signal_event(signal)
        self.recent_signals.appendleft(item)
        with self._lock:
            listeners = list(self._listeners)
        for listener in listeners:
            try:
                listener.put_nowait(item)
            except queue.Full:
                pass
