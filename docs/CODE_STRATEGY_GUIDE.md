# 代码化策略模块设计（Code Strategy Plugin）

## 1. 为什么需要代码化策略？

CEP 当前提供了两种规则表达方式：

| 方式 | 优点 | 局限 |
|---|---|---|
| 自然语言 → LLM → JSON AST | 零代码，交易员友好 | 无法表达复杂逻辑（如机器学习预测、跨品种套利、动态参数、状态机） |
| JSON AST 直接编写 | 结构清晰，可持久化 | 仍受限于预定义运算符集合 |

**代码化策略（Code Strategy）** 填补了这两种方式都无法覆盖的极客场景：

- 用 PyTorch / scikit-learn 模型预测信号
- 复杂的跨品种套利逻辑（如期现基差监控）
- 多阶段状态机（趋势确认 → 等待回调 → 入场 → 移动止损）
- 动态调参（根据市场状态实时切换参数）
- 对接外部 API（情感因子、另类数据源）

---

## 2. 架构可行性评估

**结论：完全可行，且改动极小。**

核心理由：CEP 的 `EventBus` 是一个完全解耦的广播系统，它对订阅者的"身份"**没有任何要求**。当前 `AstRuleTrigger` 能工作的根本原因，不是因为它是 AST，而是因为它实现了以下三件事：

1. 在 `register()` 里向 `EventBus` 注册监听
2. 在回调里读取 `LocalContext` 的市场数据
3. 条件成立时调用 `_emit_signal()` 发射信号

**用户自己写的 Python 代码，只要也实现了这三件事，就能无缝接入整个系统**，底层引擎一行代码不用改。

---

## 3. 设计方案

### 3.1 核心基类：`CodeStrategy`

用户只需继承 `CodeStrategy`，按需重写生命周期钩子（Hook）函数。

```python
# cep/triggers/triggers.py （新增）
class CodeStrategy(BaseTrigger):
    """
    代码化策略基类。

    用户继承此类，重写 on_bar() 或 on_tick() 方法，
    调用 self.buy() / self.sell() 发射交易信号。

    示例：
        class MyStrategy(CodeStrategy):
            def on_bar(self, bar: BarEvent, ctx: LocalContext):
                if ctx.rsi < 30:
                    self.buy(bar.symbol, reason="RSI oversold")
    """

    def __init__(
        self,
        event_bus: EventBus,
        strategy_id: str,
        local_context: LocalContext,
        subscribe_tick: bool = False,
    ):
        super().__init__(event_bus, trigger_id=strategy_id)
        self.local_context = local_context
        self._subscribe_tick = subscribe_tick

    # ---- 生命周期钩子（用户重写） ----

    def on_start(self) -> None:
        """策略启动时调用一次，用于初始化模型、加载参数等"""
        pass

    def on_bar(self, bar: BarEvent, ctx: LocalContext) -> None:
        """每根 K 线到达时触发（主要逻辑入口）"""
        pass

    def on_tick(self, tick: TickEvent, ctx: LocalContext) -> None:
        """每个 Tick 到达时触发（高频策略使用）"""
        pass

    def on_stop(self) -> None:
        """策略停止时调用，用于资源释放"""
        pass

    # ---- 用户调用的信号发射接口 ----

    def buy(self, symbol: str, reason: str = "", payload: dict | None = None) -> None:
        """发射买入信号"""
        self._emit_signal(
            symbol=symbol,
            signal_type=SignalType.TRADE_OPPORTUNITY,
            payload={"direction": "BUY", "reason": reason, **(payload or {})},
        )

    def sell(self, symbol: str, reason: str = "", payload: dict | None = None) -> None:
        """发射卖出信号"""
        self._emit_signal(
            symbol=symbol,
            signal_type=SignalType.TRADE_OPPORTUNITY,
            payload={"direction": "SELL", "reason": reason, **(payload or {})},
        )

    def alert(self, symbol: str, message: str, payload: dict | None = None) -> None:
        """发射风险预警信号"""
        self._emit_signal(
            symbol=symbol,
            signal_type=SignalType.RISK_WARNING,
            payload={"message": message, **(payload or {})},
        )

    # ---- 内部框架逻辑（用户不感知） ----

    def register(self) -> None:
        symbol = self.local_context.symbol
        self.event_bus.subscribe(BarEvent, self._on_bar_internal, symbol=symbol)
        if self._subscribe_tick:
            self.event_bus.subscribe(TickEvent, self._on_tick_internal, symbol=symbol)
        self.on_start()

    def _on_bar_internal(self, event: BarEvent) -> None:
        self.local_context.update_bar(event)
        try:
            self.on_bar(event, self.local_context)
        except Exception as e:
            logger.error(f"[{self.trigger_id}] on_bar error: {e}", exc_info=True)

    def _on_tick_internal(self, event: TickEvent) -> None:
        try:
            self.on_tick(event, self.local_context)
        except Exception as e:
            logger.error(f"[{self.trigger_id}] on_tick error: {e}", exc_info=True)
```

---

### 3.2 用户编写策略示例

**示例 A：简单技术指标策略（初学者）**

```python
# strategies/my_rsi_strategy.py
from cep.triggers.triggers import CodeStrategy
from cep.core.events import BarEvent
from cep.core.context import LocalContext

class RSIReversalStrategy(CodeStrategy):
    """RSI 超卖反转策略"""

    def on_bar(self, bar: BarEvent, ctx: LocalContext) -> None:
        rsi = ctx.rsi  # 自动惰性计算，带缓存

        if rsi < 28:
            self.buy(bar.symbol, reason=f"RSI={rsi:.1f} 深度超卖")
        elif rsi > 75:
            self.sell(bar.symbol, reason=f"RSI={rsi:.1f} 严重超买")
```

**示例 B：机器学习模型策略（进阶）**

```python
# strategies/ml_strategy.py
import numpy as np
import joblib
from cep.triggers.triggers import CodeStrategy

class XGBoostStrategy(CodeStrategy):
    """XGBoost 多因子预测策略"""

    def on_start(self):
        # 仅在启动时加载模型（避免每个 Bar 都 IO）
        self.model = joblib.load("models/xgb_au2606_v2.pkl")
        self.feature_window = 20

    def on_bar(self, bar, ctx):
        bars = list(ctx.bar_window)
        if len(bars) < self.feature_window:
            return  # 数据不足，跳过

        # 构建特征向量
        features = np.array([
            ctx.rsi,
            ctx.macd_dif,
            ctx.sma - bar.close,   # 价格偏离均线
            bars[-1].volume / max(bars[-5].volume, 1),  # 量比
        ]).reshape(1, -1)

        proba_up = self.model.predict_proba(features)[0, 1]

        if proba_up > 0.72:
            self.buy(bar.symbol, reason=f"XGB 上涨概率={proba_up:.1%}")
        elif proba_up < 0.28:
            self.sell(bar.symbol, reason=f"XGB 上涨概率={proba_up:.1%}")
```

**示例 C：跨品种套利策略（高阶）**

```python
# strategies/spread_arb_strategy.py
from cep.triggers.triggers import CodeStrategy
from cep.core.events import TickEvent

class GoldSpreadArbitrageStrategy(CodeStrategy):
    """期现基差套利策略（黄金期货 vs 现货 ETF）"""

    THRESHOLD = 2.5  # 基差阈值（元/克）

    def __init__(self, event_bus, local_context, spot_context):
        super().__init__(event_bus, "gold_spread_arb", local_context, subscribe_tick=True)
        self.spot_ctx = spot_context  # 现货 ETF 的 LocalContext

    def on_tick(self, tick, ctx):
        futures_price = tick.last_price
        spot_price = self.spot_ctx.last_tick.last_price if self.spot_ctx.last_tick else None

        if spot_price is None:
            return

        spread = futures_price - spot_price * 10  # 换算单位

        if spread > self.THRESHOLD:
            self.sell(tick.symbol, reason=f"基差={spread:.2f} 期货高估，卖期买现")
        elif spread < -self.THRESHOLD:
            self.buy(tick.symbol, reason=f"基差={spread:.2f} 期货低估，买期卖现")
```

---

### 3.3 策略热加载器（Plugin Loader）

为了让用户把代码文件扔进指定文件夹后自动生效（无需重启服务），平台可以提供一个 `StrategyLoader`：

```python
# cep/strategy_loader.py
import importlib.util
import inspect
from pathlib import Path
from cep.triggers.triggers import CodeStrategy

class StrategyLoader:
    """
    从指定目录动态扫描并加载用户策略。

    用法：
        loader = StrategyLoader(strategy_dir="strategies/")
        loader.load_all(event_bus=bus, context_manager=ctx_mgr)
    """

    def __init__(self, strategy_dir: str = "strategies/"):
        self.strategy_dir = Path(strategy_dir)

    def load_all(self, event_bus, context_manager) -> list[CodeStrategy]:
        loaded = []
        for py_file in self.strategy_dir.glob("*.py"):
            if py_file.name.startswith("_"):
                continue  # 跳过 __init__.py 等

            strategies = self._load_from_file(py_file, event_bus, context_manager)
            loaded.extend(strategies)

        return loaded

    def _load_from_file(self, path: Path, event_bus, context_manager) -> list[CodeStrategy]:
        spec = importlib.util.spec_from_file_location(path.stem, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        instances = []
        for name, cls in inspect.getmembers(module, inspect.isclass):
            if issubclass(cls, CodeStrategy) and cls is not CodeStrategy:
                # 从 context_manager 拿到对应品种的 LocalContext
                symbol = getattr(cls, "SYMBOL", None)
                if symbol:
                    ctx = context_manager.get_or_create(symbol)
                    instance = cls(event_bus=event_bus, local_context=ctx)
                    instance.register()
                    instances.append(instance)

        return instances
```

**用户只需两步：**
1. 在类上声明 `SYMBOL = "AU2606.SHF"`
2. 把 `.py` 文件扔进 `strategies/` 目录

---

## 4. 与 AST 规则的共存关系

代码化策略与 JSON AST 规则**完全互不干扰**，均通过 `EventBus` 驱动：

```
行情网关
    │ BarEvent / TickEvent
    ▼
EventBus（总线，O(1) 路由）
    ├──→ AstRuleTrigger（自然语言 → LLM → JSON AST 规则）
    ├──→ CodeStrategy（用户自写 Python 策略）
    ├──→ DeviationTrigger（再平衡偏离触发）
    └──→ CronTrigger（定时触发）
            │ 所有触发器统一发射 SignalEvent
            ▼
    RebalanceHandler / OrderRouter / AlertService（下游处理器）
```

**两种模式可以并存，同一品种可以同时挂多个触发器（AST + 代码策略），互不影响。**

---

## 5. 安全与隔离建议

用户代码具有完整的 Python 执行能力，在多租户 SaaS 场景下需要考虑以下安全措施：

| 风险 | 缓解方案 |
|---|---|
| 用户代码死循环阻塞 EventBus | 在 `_on_bar_internal` 里加超时保护（`concurrent.futures.ThreadPoolExecutor` + timeout） |
| 用户代码访问其他用户数据 | 每个用户的 `LocalContext` 独立实例化，不共享引用 |
| 用户代码调用系统命令 | 在沙箱环境运行（如 RestrictedPython 或独立子进程） |
| 用户代码内存泄漏 | 使用独立线程 + 内存限制（cgroups / ulimit） |

> 对于私有部署（单租户）场景，上述隔离可以放宽，直接信任用户代码即可。

---

## 6. 落地路线图

| 阶段 | 工作内容 | 预计周期 |
|---|---|---|
| **Phase 1** | 实现 `CodeStrategy` 基类，合并进 `cep/triggers/triggers.py` | 1 天 |
| **Phase 2** | 实现 `StrategyLoader` 热加载器 | 2 天 |
| **Phase 3** | 编写 3 个示例策略（RSI 均值回归、MACD 动量、跨品种基差）放进 `examples/strategies/` | 2 天 |
| **Phase 4**（可选） | 接入 RestrictedPython 沙箱，支持多租户隔离 | 1 周 |
