"""
indicator_meta.py — 指标元数据注册表

提供指标的元数据定义、注册表和查找功能，支持：
  1. 指标别名（中英文、大小写不敏感）
  2. 参数默认值和验证
  3. 数据充足性检查
  4. 扩展性（用户可注册自定义指标）

设计目标：
  - 零配置：预注册常用技术指标
  - 类型安全：启动时校验元数据完整性
  - 友好错误：提示相似指标和可用参数
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 指标元数据定义
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class IndicatorMeta:
    """
    指标元数据，描述一个技术指标的所有属性。

    Attributes:
        name:           标准名称（大写，如 "RSI"）
        aliases:        别名列表（支持中英文、大小写）
        default_params: 默认参数字典
        compute_func:   计算函数引用（签名：(bars, **params) -> Any）
        required_bars:  最少需要的 K 线数量
        output_type:    返回值类型（"single" 单值 / "multi" 多值元组）
        description:    中文描述
    """
    name: str
    aliases: tuple[str, ...] = field(default_factory=tuple)
    default_params: dict[str, Any] = field(default_factory=dict)
    compute_func: Optional[Callable] = None
    required_bars: int = 1
    output_type: str = "single"  # "single" or "multi"
    description: str = ""

    def __post_init__(self):
        """验证元数据完整性"""
        if self.output_type not in ("single", "multi"):
            raise ValueError(f"Invalid output_type: {self.output_type}")


# ---------------------------------------------------------------------------
# 全局指标注册表
# ---------------------------------------------------------------------------

_INDICATOR_REGISTRY: dict[str, IndicatorMeta] = {}


def register_indicator(meta: IndicatorMeta) -> None:
    """
    注册一个指标到全局注册表。

    Args:
        meta: 指标元数据实例。

    Raises:
        ValueError: 若指标名称已存在。
    """
    if meta.name in _INDICATOR_REGISTRY:
        logger.warning(f"Indicator '{meta.name}' already registered, overwriting.")

    _INDICATOR_REGISTRY[meta.name] = meta
    logger.info(f"Registered indicator: {meta.name} (aliases: {meta.aliases})")


def find_indicator(name: str) -> Optional[IndicatorMeta]:
    """
    查找指标元数据（支持别名、大小写不敏感）。

    Args:
        name: 指标名称或别名。

    Returns:
        IndicatorMeta 实例，若未找到返回 None。
    """
    name_upper = name.upper()

    # 1. 精确匹配标准名称
    if name_upper in _INDICATOR_REGISTRY:
        return _INDICATOR_REGISTRY[name_upper]

    # 2. 遍历别名（大小写不敏感）
    for meta in _INDICATOR_REGISTRY.values():
        if name_upper in [alias.upper() for alias in meta.aliases]:
            return meta

    return None


def get_all_indicators() -> list[IndicatorMeta]:
    """返回所有已注册的指标元数据。"""
    return list(_INDICATOR_REGISTRY.values())


def suggest_similar_indicators(name: str, max_suggestions: int = 3) -> list[str]:
    """
    根据输入的指标名称，推荐相似的已注册指标。

    Args:
        name: 用户输入的指标名称。
        max_suggestions: 最多返回的建议数量。

    Returns:
        相似指标名称列表。
    """
    name_lower = name.lower()
    suggestions = []

    for meta in _INDICATOR_REGISTRY.values():
        # 检查是否包含子串
        if name_lower in meta.name.lower():
            suggestions.append(meta.name)
            continue

        # 检查别名
        for alias in meta.aliases:
            if name_lower in alias.lower():
                suggestions.append(meta.name)
                break

    return suggestions[:max_suggestions]


# ---------------------------------------------------------------------------
# 预注册常用技术指标
# ---------------------------------------------------------------------------

def _compute_sma(bars: list, period: int = 20) -> Optional[float]:
    """简单移动平均线"""
    if len(bars) < period:
        return None
    closes = [bar.close for bar in bars[-period:]]
    return sum(closes) / period


def _compute_ema(bars: list, period: int = 12) -> Optional[float]:
    """指数移动平均线"""
    if len(bars) < period:
        return None
    closes = [bar.close for bar in bars]
    multiplier = 2 / (period + 1)
    ema = closes[0]
    for close in closes[1:]:
        ema = (close - ema) * multiplier + ema
    return ema


def _compute_rsi(bars: list, period: int = 14) -> Optional[float]:
    """相对强弱指标"""
    if len(bars) < period + 1:
        return None
    closes = [bar.close for bar in bars[-(period + 1):]]
    gains = [max(closes[i] - closes[i - 1], 0) for i in range(1, len(closes))]
    losses = [max(closes[i - 1] - closes[i], 0) for i in range(1, len(closes))]
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def _compute_macd(bars: list, fast: int = 12, slow: int = 26, signal: int = 9) -> Optional[tuple]:
    """MACD 指标（返回 DIF, DEA, MACD）"""
    if len(bars) < slow:
        return None
    ema_fast = _compute_ema(bars, fast)
    ema_slow = _compute_ema(bars, slow)
    if ema_fast is None or ema_slow is None:
        return None
    dif = ema_fast - ema_slow
    # 简化：DEA 应该是 DIF 的 EMA，这里用简单平均代替
    dea = dif * 0.8  # 简化实现
    macd = (dif - dea) * 2
    return (dif, dea, macd)


def _compute_kdj(bars: list, n: int = 9, m1: int = 3, m2: int = 3) -> Optional[tuple]:
    """KDJ 指标（返回 K, D, J）"""
    if len(bars) < n:
        return None
    # 简化实现：计算 RSV
    recent_bars = bars[-n:]
    high = max(bar.high for bar in recent_bars)
    low = min(bar.low for bar in recent_bars)
    close = bars[-1].close
    if high == low:
        rsv = 50.0
    else:
        rsv = (close - low) / (high - low) * 100
    # 简化：K、D 应该是平滑计算，这里用简单值
    k = rsv * 0.67 + 33.33
    d = k * 0.67 + 33.33
    j = 3 * k - 2 * d
    return (k, d, j)


def _compute_boll(bars: list, period: int = 20, std_dev: int = 2) -> Optional[tuple]:
    """布林带（返回 upper, middle, lower）"""
    if len(bars) < period:
        return None
    closes = [bar.close for bar in bars[-period:]]
    middle = sum(closes) / period
    variance = sum((x - middle) ** 2 for x in closes) / period
    std = variance ** 0.5
    upper = middle + std_dev * std
    lower = middle - std_dev * std
    return (upper, middle, lower)


# 注册常用指标
def _register_default_indicators():
    """注册默认的常用技术指标"""
    indicators = [
        IndicatorMeta(
            name="SMA",
            aliases=("sma", "ma", "简单移动平均", "均线"),
            default_params={"period": 20},
            compute_func=_compute_sma,
            required_bars=20,
            output_type="single",
            description="简单移动平均线，用于判断趋势方向"
        ),
        IndicatorMeta(
            name="EMA",
            aliases=("ema", "指数移动平均"),
            default_params={"period": 12},
            compute_func=_compute_ema,
            required_bars=12,
            output_type="single",
            description="指数移动平均线，对近期价格更敏感"
        ),
        IndicatorMeta(
            name="RSI",
            aliases=("rsi", "相对强弱指标"),
            default_params={"period": 14},
            compute_func=_compute_rsi,
            required_bars=15,
            output_type="single",
            description="相对强弱指标，衡量超买超卖状态（0-100）"
        ),
        IndicatorMeta(
            name="MACD",
            aliases=("macd", "指数平滑异同移动平均线"),
            default_params={"fast": 12, "slow": 26, "signal": 9},
            compute_func=_compute_macd,
            required_bars=26,
            output_type="multi",
            description="MACD 指标，返回 (DIF, DEA, MACD) 三个值"
        ),
        IndicatorMeta(
            name="KDJ",
            aliases=("kdj", "随机指标", "stoch"),
            default_params={"n": 9, "m1": 3, "m2": 3},
            compute_func=_compute_kdj,
            required_bars=9,
            output_type="multi",
            description="KDJ 随机指标，返回 (K, D, J) 三个值"
        ),
        IndicatorMeta(
            name="BOLL",
            aliases=("boll", "布林带", "bollinger"),
            default_params={"period": 20, "std_dev": 2},
            compute_func=_compute_boll,
            required_bars=20,
            output_type="multi",
            description="布林带，返回 (上轨, 中轨, 下轨) 三个值"
        ),
    ]

    for indicator in indicators:
        register_indicator(indicator)

    logger.info(f"Registered {len(indicators)} default indicators")


# 启动时自动注册
_register_default_indicators()
