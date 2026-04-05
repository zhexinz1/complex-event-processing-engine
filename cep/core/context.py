"""
context.py — 双层状态黑板（Global + Local Context）

Context 是规则引擎的"记忆"，存储所有用于条件判断的状态数据。
设计分为两层：
  1. GlobalContext:  宏观数据（VIX、总净值、目标权重配置等）。
  2. LocalContext:   品种级数据（K 线窗口、最新 Tick、当前持仓等）。

核心特性：
  - 惰性求值（Lazy Evaluation）：技术指标按需计算，避免算力浪费。
  - 魔术方法：通过 __getattr__ 实现类似 context.macd 的语法糖。
  - 缓存机制：计算结果缓存在 _cache 中，避免重复计算。
"""

from __future__ import annotations

import logging
from collections import deque
from typing import Any, Callable, Deque, Optional

from cep.core.events import BarEvent, TickEvent

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 全局上下文（宏观数据）
# ---------------------------------------------------------------------------

class GlobalContext:
    """
    全局上下文，存储跨品种的宏观数据和系统级配置。

    典型用途：
      - 市场情绪指标（VIX、恐慌指数）。
      - 账户总净值、可用资金。
      - 目标权重配置（target_weights: dict[symbol, weight]）。
      - 全局风控参数（最大回撤阈值、杠杆上限等）。
    """

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        logger.info("GlobalContext initialized.")

    def set(self, key: str, value: Any) -> None:
        """
        设置全局变量。

        Args:
            key:   变量名（如 "vix", "total_nav", "target_weights"）。
            value: 变量值（任意类型）。
        """
        self._data[key] = value
        logger.debug(f"GlobalContext.set: {key} = {value}")

    def get(self, key: str, default: Any = None) -> Any:
        """
        获取全局变量。

        Args:
            key:     变量名。
            default: 若变量不存在，返回此默认值。

        Returns:
            变量值或默认值。
        """
        return self._data.get(key, default)

    def __getattr__(self, name: str) -> Any:
        """
        魔术方法：支持 context.vix 语法糖（等价于 context.get("vix")）。

        Args:
            name: 属性名。

        Returns:
            对应的全局变量值。

        Raises:
            AttributeError: 若变量不存在。
        """
        if name.startswith("_"):
            # 避免与内部属性冲突
            raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")
        if name in self._data:
            return self._data[name]
        raise AttributeError(f"GlobalContext has no attribute '{name}'")


# ---------------------------------------------------------------------------
# 本地上下文（品种级数据 + 惰性指标计算）
# ---------------------------------------------------------------------------

class LocalContext:
    """
    本地上下文，存储特定品种的实时数据和技术指标。

    核心功能：
      1. 维护 K 线窗口（固定长度的 deque）。
      2. 缓存最新 Tick 数据。
      3. 惰性计算技术指标（如 MACD、RSI、布林带）。

    惰性求值机制：
      - 当规则引擎访问 context.macd 时，若缓存未命中，自动调用注册的计算函数。
      - 计算结果存入 _cache，下次访问直接返回（直到 K 线更新触发缓存失效）。

    Attributes:
        symbol:         标的代码。
        bar_window:     K 线窗口（deque，固定长度）。
        latest_tick:    最新 Tick 数据。
        current_weight: 当前持仓权重（0.0 ~ 1.0）。
        _cache:         指标缓存字典。
        _indicator_registry: 指标计算函数注册表。
    """

    def __init__(
        self,
        symbol: str,
        window_size: int = 100,
        indicator_registry: Optional[dict[str, Callable]] = None,
        global_context: Optional[GlobalContext] = None,
    ) -> None:
        """
        初始化本地上下文。

        Args:
            symbol:              标的代码。
            window_size:         K 线窗口大小（默认 100 根）。
            indicator_registry:  指标计算函数字典，格式为 {name: compute_func}。
                                 compute_func 签名为 (bars: list[BarEvent]) -> Any。
            global_context:      全局上下文引用（用于访问宏观数据如CPI、VIX等）。
        """
        self.symbol = symbol
        self.bar_window: Deque[BarEvent] = deque(maxlen=window_size)
        self.latest_tick: Optional[TickEvent] = None
        self.current_weight: float = 0.0  # 当前持仓权重
        self.global_context = global_context  # 新增：全局上下文引用

        self._cache: dict[str, Any] = {}
        self._indicator_registry = indicator_registry or {}

        logger.info(f"LocalContext initialized for {symbol} (window_size={window_size})")

    # -----------------------------------------------------------------------
    # 数据更新接口
    # -----------------------------------------------------------------------

    def update_tick(self, tick: TickEvent) -> None:
        """
        更新最新 Tick 数据。

        Args:
            tick: TickEvent 实例。
        """
        if tick.symbol != self.symbol:
            logger.warning(
                f"Symbol mismatch: expected {self.symbol}, got {tick.symbol}"
            )
            return
        self.latest_tick = tick
        # Tick 更新不触发缓存失效（仅 Bar 更新时失效）

    def update_bar(self, bar: BarEvent) -> None:
        """
        更新 K 线窗口，并清空指标缓存（触发惰性重算）。

        Args:
            bar: BarEvent 实例。
        """
        if bar.symbol != self.symbol:
            logger.warning(
                f"Symbol mismatch: expected {self.symbol}, got {bar.symbol}"
            )
            return

        self.bar_window.append(bar)
        self._cache.clear()  # 新 Bar 到达，所有指标缓存失效
        logger.debug(f"Bar updated for {self.symbol}, cache cleared.")

    def update_weight(self, weight: float) -> None:
        """
        更新当前持仓权重。

        Args:
            weight: 权重值（0.0 ~ 1.0）。
        """
        self.current_weight = weight
        logger.debug(f"Weight updated for {self.symbol}: {weight:.4f}")

    # -----------------------------------------------------------------------
    # 惰性指标计算（魔术方法）
    # -----------------------------------------------------------------------

    def __getattr__(self, name: str) -> Any:
        """
        魔术方法：实现惰性指标计算，支持跨Context数据访问。

        工作流程：
          1. 若 name 在 _cache 中，直接返回缓存值。
          2. 若 name 在 _indicator_registry 中，调用计算函数并缓存结果。
          3. 若 name 在 global_context 中，从全局上下文读取（如CPI、VIX等宏观数据）。
          4. 否则抛出 AttributeError。

        示例：
            >>> context.macd  # 首次访问，触发计算
            >>> context.macd  # 再次访问，返回缓存值
            >>> context.cpi   # 从 global_context 读取宏观数据

        Args:
            name: 指标名称（如 "macd", "rsi", "boll"）或全局变量名（如 "cpi", "vix"）。

        Returns:
            指标计算结果（类型由计算函数决定）。

        Raises:
            AttributeError: 若指标未注册且全局上下文中也不存在。
        """
        if name.startswith("_"):
            # 避免与内部属性冲突
            raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")

        # 1. 检查缓存
        if name in self._cache:
            logger.debug(f"Cache hit for indicator '{name}' on {self.symbol}")
            return self._cache[name]

        # 2. 检查本地指标注册表
        if name in self._indicator_registry:
            compute_func = self._indicator_registry[name]
            logger.debug(f"Computing indicator '{name}' for {self.symbol}")

            # [高频计算优化注]：当前由于底层 compute_func 签名需要全量窗口传入，
            # 采用 O(N) 的 list(deque) 强转及全指标重算，这在微秒级高频下是"伪惰性求值"。
            # 实盘中应重构 compute_func 使其接收 (new_bar, last_state) 进行 O(1) 增量状态机计算。
            # 为了保持既有业务逻辑（如默认 SMA/RSI 示例）兼容，此处暂保留 List 转换逻辑。
            bars = list(self.bar_window)
            result = compute_func(bars)

            # 缓存结果
            self._cache[name] = result
            return result

        # 3. 检查全局上下文（新增：支持跨Context数据访问）
        if self.global_context:
            try:
                value = getattr(self.global_context, name)
                logger.debug(f"Fetched '{name}' from GlobalContext for {self.symbol}")
                return value
            except AttributeError:
                pass  # 继续抛出更详细的错误

        # 4. 未找到
        available = list(self._indicator_registry.keys())
        if self.global_context:
            available.extend([f"global.{k}" for k in self.global_context._data.keys()])
        raise AttributeError(
            f"LocalContext for {self.symbol} has no indicator '{name}'. "
            f"Available: {available}"
        )

    # -----------------------------------------------------------------------
    # 工具方法
    # -----------------------------------------------------------------------

    def get_bars(self, count: int = -1) -> list[BarEvent]:
        """
        获取最近 N 根 K 线（用于手动计算指标）。

        Args:
            count: 返回的 K 线数量，-1 表示全部。

        Returns:
            K 线列表（按时间升序）。
        """
        bars = list(self.bar_window)
        return bars if count == -1 else bars[-count:]

    def clear_cache(self) -> None:
        """
        手动清空指标缓存（用于调试或强制重算）。
        """
        self._cache.clear()
        logger.debug(f"Cache manually cleared for {self.symbol}")


# ---------------------------------------------------------------------------
# 示例：指标计算函数（实际项目中应调用 TA-Lib）
# ---------------------------------------------------------------------------

def compute_sma(bars: list[BarEvent], period: int = 20) -> Optional[float]:
    """
    简单移动平均线（Simple Moving Average）。

    Args:
        bars:   K 线列表。
        period: 周期（默认 20）。

    Returns:
        SMA 值，若数据不足返回 None。
    """
    if len(bars) < period:
        return None
    closes = [bar.close for bar in bars[-period:]]
    return sum(closes) / period


def compute_rsi(bars: list[BarEvent], period: int = 14) -> Optional[float]:
    """
    相对强弱指标（Relative Strength Index）。

    注意：这是简化实现，实际应使用 TA-Lib 的 talib.RSI()。

    Args:
        bars:   K 线列表。
        period: 周期（默认 14）。

    Returns:
        RSI 值（0 ~ 100），若数据不足返回 None。
    """
    if len(bars) < period + 1:
        return None

    # 简化计算：仅作示例，实际需用 Wilder's Smoothing
    closes = [bar.close for bar in bars[-(period + 1):]]
    gains = [max(closes[i] - closes[i - 1], 0) for i in range(1, len(closes))]
    losses = [max(closes[i - 1] - closes[i], 0) for i in range(1, len(closes))]

    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


# ---------------------------------------------------------------------------
# 默认指标注册表（可在初始化时传入 LocalContext）
# ---------------------------------------------------------------------------

DEFAULT_INDICATOR_REGISTRY: dict[str, Callable] = {
    "sma": lambda bars: compute_sma(bars, period=20),
    "rsi": lambda bars: compute_rsi(bars, period=14),
    # 可继续添加：macd, boll, atr, etc.
}
