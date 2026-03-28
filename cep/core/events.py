"""
events.py — 标准事件载荷定义

所有在 EventBus 上流通的数据包均继承自 BaseEvent。
规则：事件是不可变的值对象（frozen dataclass），发布后不得修改。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any


# ---------------------------------------------------------------------------
# 信号类型枚举
# ---------------------------------------------------------------------------

class SignalType(str, Enum):
    """SignalEvent 的语义分类，下游 Handler 按此路由处理逻辑。"""
    TRADE_OPPORTUNITY  = "TRADE_OPPORTUNITY"   # AST 规则命中，存在交易机会
    REBALANCE_TRIGGER  = "REBALANCE_TRIGGER"   # 持仓偏离超阈值，需再平衡（已废弃，使用 REBALANCE_REQUEST）
    REBALANCE_REQUEST  = "REBALANCE_REQUEST"   # 再平衡请求（统一的再平衡信号）
    FUND_ALLOCATION    = "FUND_ALLOCATION"     # 定时资金分配指令
    RISK_ALERT         = "RISK_ALERT"          # 风控预警（预留）


# ---------------------------------------------------------------------------
# 基类
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class BaseEvent:
    """
    所有事件的根基类。

    Attributes:
        event_id:   全局唯一 ID，用于幂等去重与链路追踪。
        timestamp:  事件产生的 UTC 时间戳（精确到微秒）。
    """
    event_id:  str      = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# 行情事件
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TickEvent(BaseEvent):
    """
    Level-1 逐笔行情事件，由行情网关在每个 Tick 到达时发布。

    Attributes:
        symbol:     标的代码，如 "600519.SH"。
        last_price: 最新成交价。
        bid:        买一价。
        ask:        卖一价。
        volume:     本 Tick 成交量（手）。
        turnover:   本 Tick 成交额（元）。
    """
    symbol:     str   = ""
    last_price: float = 0.0
    bid:        float = 0.0
    ask:        float = 0.0
    volume:     int   = 0
    turnover:   float = 0.0


@dataclass(frozen=True)
class BarEvent(BaseEvent):
    """
    OHLCV K 线事件，由行情聚合器在每根 Bar 收盘时发布。

    Attributes:
        symbol:    标的代码。
        freq:      K 线周期，如 "1m", "5m", "1d"。
        open/high/low/close: 四价。
        volume:    成交量（手）。
        turnover:  成交额（元）。
        bar_time:  该 Bar 的开盘时间。
    """
    symbol:   str      = ""
    freq:     str      = "1m"
    open:     float    = 0.0
    high:     float    = 0.0
    low:      float    = 0.0
    close:    float    = 0.0
    volume:   int      = 0
    turnover: float    = 0.0
    bar_time: datetime = field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# 定时事件
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TimerEvent(BaseEvent):
    """
    定时器触发事件，由 CronScheduler 按计划发布。

    Attributes:
        timer_id:  定时器名称，如 "DAILY_REBALANCE_1430"。
        fired_at:  实际触发时间（可能与计划时间有微小偏差）。
    """
    timer_id: str      = ""
    fired_at: datetime = field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# 信号事件（规则引擎的输出）
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SignalEvent(BaseEvent):
    """
    规则触发后产生的信号包，是触发器（Trigger）唯一允许向总线发布的输出。

    设计约定：
      - Trigger 只负责"发现信号"，不做任何下单或 UI 操作。
      - 下游 Handler（如 OrderRouter、AlertService）订阅此事件并各自处理。

    Attributes:
        source:      产生信号的触发器名称，用于审计追踪。
        symbol:      相关标的代码（可为空，如全局风控信号）。
        signal_type: 信号语义分类，见 SignalType 枚举。
        payload:     附加元数据字典，内容由各触发器自定义。
        rule_id:     触发该信号的规则 ID（可选，用于回测归因）。
    """
    source:      str        = ""
    symbol:      str        = ""
    signal_type: SignalType = SignalType.TRADE_OPPORTUNITY
    payload:     dict[str, Any] = field(default_factory=dict)
    rule_id:     str        = ""
