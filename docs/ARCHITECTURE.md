# CEP 系统架构设计文档

## 目录
1. [系统概述](#系统概述)
2. [设计理念](#设计理念)
3. [核心模块](#核心模块)
4. [再平衡引擎](#再平衡引擎)
5. [数据流转](#数据流转)
6. [完整执行流程](#完整执行流程)
7. [交互时序图](#交互时序图)
8. [扩展性设计](#扩展性设计)

---

## 系统概述

CEP (Complex Event Processing) 是一个基于事件驱动的量化交易规则引擎，用于私募资金的盘中异动监控和动态仓位再平衡。

### 核心能力
- **自然语言规则输入**：交易员用中文描述规则，系统自动转换为可执行代码
- **实时事件处理**：基于 ECA (Event-Condition-Action) 模式
- **技术指标计算**：支持 RSI、MACD、KDJ 等常用指标
- **信号生成与推送**：满足条件时生成交易信号，推送给交易员
- **动态再平衡引擎**：自动计算调仓订单，支持资金申赎、定期对齐、偏离触发

### 技术栈
- Python 3.10+
- 事件总线（发布/订阅模式）
- AST（抽象语法树）规则引擎
- Claude API（自然语言解析）

---

## 设计理念

### 1. 极致解耦
```
触发器 → 发射事件 → 事件总线 → 订阅者处理
```
触发器只负责判定条件并发射事件，不直接调用下游业务代码。

### 2. 事件驱动
避免 `while True` 轮询，所有状态流转由事件驱动：
- **TickEvent**：逐笔行情到达
- **BarEvent**：K 线数据更新
- **SignalEvent**：交易信号生成

### 3. 惰性求值
技术指标按需计算，避免算力浪费：
```python
context.rsi  # 首次访问触发计算
context.rsi  # 再次访问返回缓存
```

### 4. 声明式规则
规则以 JSON AST 表达，易于序列化、可视化和持久化：
```json
{
  "type": "operator",
  "op": "<",
  "left": {"type": "indicator", "name": "RSI"},
  "right": {"type": "const", "value": 30}
}
```

---

## 核心模块

### 模块架构图
```
┌─────────────────────────────────────────────────────────┐
│                    交易员输入层                          │
│  "当 RSI 小于 30 且 MACD 金叉时买入"                     │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│              nl_parser.py (自然语言解析)                 │
│  - 调用 Claude API                                       │
│  - 转换为 JSON AST                                       │
│  - 校验指标是否存在                                      │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│           indicator_meta.py (指标元数据)                 │
│  - 指标注册表（RSI, MACD, KDJ...）                       │
│  - 别名查找（"相对强弱指标" → RSI）                      │
│  - 参数默认值                                            │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│            ast_engine.py (AST 求值引擎)                  │
│  - IndicatorNode（指标节点）                             │
│  - OperatorNode（运算符节点）                            │
│  - LogicalNode（逻辑节点）                               │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│              triggers.py (触发器)                        │
│  - AstRuleTrigger（规则触发器）                          │
│  - 订阅 BarEvent                                         │
│  - 求值 AST 树                                           │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│              context.py (状态黑板)                       │
│  - LocalContext（品种级数据）                            │
│  - K 线窗口、最新 Tick                                   │
│  - 惰性指标计算                                          │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│            event_bus.py (事件总线)                       │
│  - 发布/订阅模式                                         │
│  - Symbol 路由（O(1) 精准定位）                          │
│  - 弱引用防内存泄漏                                      │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│                  交易员接收层                            │
│  - SignalEvent（买入/卖出信号）                          │
│  - 推送到交易终端/钉钉/邮件                              │
└─────────────────────────────────────────────────────────┘
```

---

## 核心模块详解

### 1. events.py - 事件定义
```python
@dataclass(frozen=True)
class BarEvent(BaseEvent):
    """K 线事件"""
    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int

@dataclass(frozen=True)
class SignalEvent(BaseEvent):
    """交易信号事件"""
    symbol: str
    signal_type: str  # "BUY" / "SELL"
    reason: str       # 触发原因
    timestamp: datetime
```

**设计要点**：
- 使用 `@dataclass(frozen=True)` 确保事件不可变
- 所有事件继承 `BaseEvent`
- 包含完整的时间戳和标的信息

### 2. event_bus.py - 事件总线
```python
class EventBus:
    def __init__(self):
        # 二维字典：{EventType: {symbol: set[weakref]}}
        self._subscribers: dict[type, dict[str, set]] = {}

    def subscribe(self, event_type, handler, symbol=None):
        """订阅事件（支持 Symbol 路由）"""

    def publish(self, event):
        """发布事件（O(1) 精准定位订阅者）"""
```

**设计要点**：
- **Symbol 路由**：从 O(N) 遍历优化到 O(1) 精准定位
- **弱引用**：使用 `weakref.WeakMethod` 防止内存泄漏
- **精准订阅**：`subscribe(TickEvent, handler, symbol="600519.SH")`

### 3. context.py - 状态黑板
```python
class LocalContext:
    def __init__(self, symbol, window_size=100):
        self.symbol = symbol
        self.bar_window = deque(maxlen=window_size)
        self._cache = {}  # 指标缓存
        self._indicator_registry = {}  # 指标计算函数

    def __getattr__(self, name):
        """惰性指标计算"""
        if name in self._cache:
            return self._cache[name]

        # 查找指标元数据
        meta = find_indicator(name)
        if meta:
            result = meta.compute_func(self.bar_window, **meta.default_params)
            self._cache[name] = result
            return result

        raise AttributeError(f"Unknown indicator: {name}")
```

**设计要点**：
- **双层黑板**：GlobalContext（宏观数据）+ LocalContext（品种数据）
- **惰性求值**：通过 `__getattr__` 魔术方法实现
- **缓存失效**：新 Bar 到达时清空缓存

### 4. indicator_meta.py - 指标元数据
```python
@dataclass(frozen=True)
class IndicatorMeta:
    name: str                    # "RSI"
    aliases: tuple[str, ...]     # ("rsi", "相对强弱指标")
    default_params: dict         # {"period": 14}
    compute_func: Callable       # 计算函数
    required_bars: int           # 最少 K 线数量
    output_type: str             # "single" / "multi"
    description: str             # 中文描述

# 全局注册表
_INDICATOR_REGISTRY = {
    "RSI": IndicatorMeta(...),
    "MACD": IndicatorMeta(...),
    "KDJ": IndicatorMeta(...),
}
```

**设计要点**：
- **元数据驱动**：所有指标信息集中管理
- **别名支持**：中英文、大小写不敏感
- **参数化**：支持动态覆盖默认参数
- **可扩展**：用户可注册自定义指标

### 5. ast_engine.py - AST 求值引擎
```python
class IndicatorNode(Node):
    def __init__(self, name, params=None, component=None):
        self.name = name
        self.params = params or {}
        self.component = component  # 多值指标组件

    def evaluate(self, context):
        meta = find_indicator(self.name)

        # 检查数据充足性
        if len(context.bar_window) < meta.required_bars:
            raise ValueError("数据不足")

        # 计算指标
        result = meta.compute_func(context.bar_window, **self.params)

        # 提取组件（MACD.DIF, KDJ.K）
        if meta.output_type == "multi":
            return result[component_index]

        return result
```

**设计要点**：
- **组合模式**：所有节点实现 `evaluate(context)` 接口
- **递归求值**：树形结构自动递归计算
- **类型安全**：编译期可检查节点类型

### 6. nl_parser.py - 自然语言解析
```python
def parse_natural_language(text, api_key):
    """使用 Claude API 解析自然语言"""
    client = anthropic.Anthropic(api_key=api_key)

    message = client.messages.create(
        model="claude-3-5-sonnet-20241022",
        system=SYSTEM_PROMPT,  # 包含指标列表和 JSON 格式规范
        messages=[{"role": "user", "content": text}]
    )

    # 提取 JSON AST
    response_text = message.content[0].text
    ast_dict = json.loads(response_text)

    return ast_dict
```

**设计要点**：
- **提示词工程**：详细的 JSON 格式规范和示例
- **自动校验**：解析后验证指标是否存在
- **错误提示**：提供相似指标建议

### 7. triggers.py - 触发器
```python
class AstRuleTrigger:
    def __init__(self, rule_ast, event_bus, context):
        self.rule_ast = rule_ast
        self.event_bus = event_bus
        self.context = context

        # 订阅 BarEvent
        event_bus.subscribe(BarEvent, self._on_bar, symbol=context.symbol)

    def _on_bar(self, event):
        """K 线更新时触发"""
        # 更新上下文
        self.context.update_bar(event)

        # 求值规则
        result = self.rule_ast.evaluate(self.context)

        # 满足条件则发射信号
        if result:
            signal = SignalEvent(
                symbol=event.symbol,
                signal_type="BUY",
                reason="RSI < 30 AND MACD金叉",
                timestamp=event.timestamp
            )
            self.event_bus.publish(signal)
```

**设计要点**：
- **防抖机制**：2 秒冷却期，防止高频信号雪崩
- **解耦设计**：触发器只发射事件，不直接调用下游
- **Symbol 路由**：只订阅特定品种的事件

---

## 再平衡引擎

### 概述

再平衡引擎是 CEP 系统的核心扩展，实现了从触发条件到订单生成的完整自动化流程。与技术指标规则（如 MACD 金叉）保持统一的架构设计，所有触发器都通过事件总线发射信号，由专门的处理器执行业务逻辑。

### 设计理念

**统一的规则触发架构**：
```
规则条件满足 → 触发器发射信号 → 下游 Handler 执行业务逻辑
```

无论是技术指标规则还是再平衡规则，都使用同一套触发器-信号-处理器机制。

### 核心模块

#### 1. portfolio_context.py - 组合级上下文

管理全品种的组合级数据，支持再平衡引擎的计算需求。

```python
class PortfolioContext:
    """
    组合级上下文，存储全品种的组合数据。

    核心数据：
      - 目标权重配置：各品种的理论权重
      - 当前持仓：各品种的实际持仓量
      - 合约信息：合约乘数、最小变动单位、保证金率
      - 账户信息：总净值、可用资金、保证金占用
      - 最新行情：各品种的最新价格
    """
```

**数据类定义**：
- `ContractInfo`：合约基础信息（乘数、最小变动价位、保证金率）
- `Position`：持仓信息（数量、均价、市值）

**核心方法**：
- `set_target_weights()`：设置目标权重配置
- `update_position()`：更新持仓信息
- `register_contract()`：注册合约基础信息
- `update_price()`：更新最新价格
- `update_account()`：更新账户信息
- `calculate_current_weight()`：计算当前权重

#### 2. rebalance_engine.py - 核心计算引擎

实现从目标权重到具体订单的完整计算链路（5 步计算）。

**5 步计算链路**：
```
步骤1: 计算新目标总资产
       当前净值 + 待入账新增资金 → 新目标总资产

步骤2: 计算单品种目标市值
       新目标总资产 × 目标权重 → 品种目标市值

步骤3: 计算市值差额
       品种目标市值 - 当前真实市值 → 市值差额

步骤4: 理论增减换算
       市值差额 / 最新价 / 合约乘数 → 理论增减量

步骤5: 离散化与舍入处理
       理论增减量 → 离散化舍入 → 整数订单量
```

**数据类定义**：
- `RebalanceOrder`：再平衡订单（品种、方向、数量、价格、原因）
- `RebalanceResult`：计算结果（订单列表、所需保证金、计算详情）

**核心方法**：
- `calculate()`：执行完整的 5 步计算链路
- `validate_orders()`：校验订单是否满足资金约束

#### 3. rebalance_triggers.py - 再平衡触发器

实现三类再平衡触发器，统一发射 `REBALANCE_REQUEST` 信号。

**FundFlowTrigger - 资金申赎触发器**：
```python
工作流程：
  1. 监听 TimerEvent（如每日 14:30）
  2. 检查是否有新增资金（检测净值变化）
  3. 若有新增资金，发射 REBALANCE_REQUEST 信号

典型应用：
  - 客户申购：14:30 检测到 130 万入金，触发再平衡
  - 客户赎回：检测到资金流出，触发减仓
```

**MonthlyRebalanceTrigger - 月初定期触发器**：
```python
工作流程：
  1. 监听 TimerEvent（如每月 1 号 9:30）
  2. 无条件发射 REBALANCE_REQUEST 信号
  3. 强制拉回基准权重

典型应用：
  - 每月初更新目标权重配置后，强制再平衡
  - 定期清理累积的偏离
```

**PortfolioDeviationTrigger - 组合偏离触发器**：
```python
工作流程：
  1. 监听 TimerEvent（定期检查，如每分钟）
  2. 计算所有品种的当前权重 vs 目标权重
  3. 若任一品种偏离超过阈值，发射 REBALANCE_REQUEST 信号

典型应用：
  - 盘中监控：沪金 2606 因暴涨导致权重从 26% 涨到 30%，触发再平衡
  - 风控：某品种权重超过上限，触发减仓

特性：
  - 60 秒冷却期，防止高频触发
  - 全品种监控，找出最大偏离品种
```

#### 4. rebalance_handler.py - 信号处理器

订阅 `REBALANCE_REQUEST` 信号，调用 RebalanceEngine 计算，生成订单并执行。

```python
class RebalanceHandler:
    """
    再平衡信号处理器。

    工作流程：
      1. 接收 REBALANCE_REQUEST 信号
      2. 从信号 payload 中提取参数（如新增资金）
      3. 调用 RebalanceEngine 执行计算
      4. 校验订单（资金约束、防重等）
      5. 发送订单到柜台（当前模拟）
    """
```

**安全机制**：
- 防重机制：10 秒最小执行间隔
- 资金约束校验：确保保证金不超过可用资金

### 再平衡数据流

```
┌─────────────────────────────────────────────────────────┐
│                    触发源                                │
│  T1: 资金申赎 (14:30 检测到 130万入金)                   │
│  T2: 月初定期 (每月1号 9:30)                             │
│  T3: 盘中偏离 (沪金权重 30% vs 目标 26%)                 │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│              触发器发射信号                              │
│  SignalEvent(type=REBALANCE_REQUEST)                    │
│  payload: {trigger_type, new_capital, ...}              │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│              RebalanceHandler                           │
│  - 订阅 REBALANCE_REQUEST 信号                          │
│  - 提取参数（新增资金、触发原因）                        │
│  - 调用 RebalanceEngine 计算                            │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│              RebalanceEngine                            │
│  步骤1: 当前净值 + 新增资金 → 新目标总资产              │
│  步骤2: 新目标总资产 × 目标权重 → 品种目标市值          │
│  步骤3: 品种目标市值 - 当前市值 → 市值差额              │
│  步骤4: 市值差额 / 最新价 / 合约乘数 → 理论增减量       │
│  步骤5: 理论增减量 → 离散化舍入 → 整数订单量            │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│              数据源（预留接口）                          │
│  - 投研配置库：读取目标权重                             │
│  - 迅投GT柜台：拉取持仓、净值、可用资金                  │
│  - 极速行情：拉取最新价格                               │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│              订单生成与校验                              │
│  - 生成一揽子订单列表                                   │
│  - 资金约束校验（保证金 < 可用资金）                     │
│  - 防重校验（10秒最小间隔）                             │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│              订单执行（预留接口）                        │
│  - 发送到 GT 柜台执行                                   │
│  - 等待成交回报                                         │
│  - 更新持仓状态                                         │
└─────────────────────────────────────────────────────────┘
```

### 应用场景示例

#### 场景 1：客户申购 130 万

```python
# 1. 14:30 定时器触发
timer_event = TimerEvent(timer_id="DAILY_FUND_CHECK_1430")
event_bus.publish(timer_event)

# 2. FundFlowTrigger 检测到净值变化
# 当前净值：1000万 → 1130万（+130万）

# 3. 发射 REBALANCE_REQUEST 信号
signal = SignalEvent(
    signal_type=SignalType.REBALANCE_REQUEST,
    payload={
        "trigger_type": "fund_flow",
        "new_capital": 1_300_000,
        "previous_nav": 10_000_000,
        "current_nav": 11_300_000
    }
)

# 4. RebalanceHandler 处理信号
# 5. RebalanceEngine 计算订单
# 新目标总资产 = 1130万
# 沪金目标市值 = 1130万 × 26% = 293.8万
# 当前市值 = 260万
# 市值差额 = 33.8万
# 理论增减 = 33.8万 / 520 / 1000 = 0.65手
# 整数订单 = 1手（买入）

# 6. 生成订单
orders = [
    RebalanceOrder(symbol="AU2606", side="BUY", quantity=1, price=520.0),
    RebalanceOrder(symbol="P2609", side="BUY", quantity=3, price=8500),
    RebalanceOrder(symbol="IM2606", side="BUY", quantity=2, price=1080),
]

# 7. 发送到柜台执行
```

#### 场景 2：月初定期再平衡

```python
# 1. 每月 1 号 9:30 定时器触发
timer_event = TimerEvent(timer_id="MONTHLY_REBALANCE_0930")
event_bus.publish(timer_event)

# 2. MonthlyRebalanceTrigger 无条件触发
signal = SignalEvent(
    signal_type=SignalType.REBALANCE_REQUEST,
    payload={
        "trigger_type": "monthly",
        "new_capital": 0.0  # 月初定期不涉及新增资金
    }
)

# 3. 强制拉回基准权重
# 计算所有品种的偏离，生成调仓订单
```

#### 场景 3：盘中偏离触发

```python
# 1. 沪金价格暴涨 10%
# 520 → 572，市值从 260万 → 286万
# 当前权重：286万 / 1000万 = 28.6%
# 目标权重：26%
# 偏离度：2.6% < 3%（未触发）

# 2. 继续上涨，权重达到 30%
# 偏离度：4% > 3%（触发）

# 3. PortfolioDeviationTrigger 发射信号
signal = SignalEvent(
    signal_type=SignalType.REBALANCE_REQUEST,
    payload={
        "trigger_type": "deviation",
        "max_deviation": 0.04,
        "max_deviation_symbol": "AU2606"
    }
)

# 4. 全品种重新平衡，生成调仓订单
```

### 预留接口

以下接口已预留，等待后续对接外部系统：

1. **行情接入**：`portfolio_ctx.update_price()` - 对接极速行情系统
2. **持仓拉取**：`portfolio_ctx.update_position()` - 对接迅投 GT 柜台
3. **配置拉取**：`portfolio_ctx.set_target_weights()` - 对接投研配置库
4. **订单执行**：`rebalance_handler._execute_orders()` - 对接 GT 柜台下单接口

### 关键设计亮点

1. **统一架构**：技术指标规则和再平衡规则使用同一套触发器-信号-处理器机制
2. **极致解耦**：触发器只负责判定条件，计算引擎只负责计算，处理器只负责协调
3. **可测试性**：每个模块都可独立测试，计算链路清晰可审计
4. **可扩展性**：新增触发器或修改计算逻辑都很容易
5. **安全机制**：资金约束校验、防重机制、冷却期保护

---

## 数据流转

### 完整数据流
```
1. 行情数据到达
   TickEvent/BarEvent → EventBus

2. 触发器接收事件
   EventBus → AstRuleTrigger._on_bar()

3. 更新上下文
   BarEvent → LocalContext.update_bar()
   → 清空指标缓存

4. 求值规则
   AstRuleTrigger → rule_ast.evaluate(context)
   → IndicatorNode.evaluate()
   → LocalContext.__getattr__("rsi")
   → 查找指标元数据
   → 计算 RSI
   → 缓存结果

5. 生成信号
   满足条件 → SignalEvent → EventBus

6. 推送交易员
   EventBus → SignalHandler
   → 钉钉/邮件/交易终端
```

---

## 完整执行流程

### 场景：交易员输入规则到信号推送

#### 第 1 步：交易员输入自然语言规则
```
交易员输入：
"当贵州茅台的 RSI 小于 30 且 MACD 金叉时买入"
```

#### 第 2 步：自然语言解析
```python
# nl_parser.py
ast_dict = parse_natural_language(
    "当贵州茅台的 RSI 小于 30 且 MACD 金叉时买入"
)

# Claude API 返回：
{
  "type": "logical",
  "op": "AND",
  "operands": [
    {
      "type": "operator",
      "op": "<",
      "left": {"type": "indicator", "name": "RSI", "params": {"period": 14}},
      "right": {"type": "const", "value": 30}
    },
    {
      "type": "operator",
      "op": ">",
      "left": {"type": "indicator", "name": "MACD", "component": "DIF"},
      "right": {"type": "indicator", "name": "MACD", "component": "DEA"}
    }
  ]
}
```

#### 第 3 步：指标校验
```python
# indicator_meta.py
result = validate_and_suggest(ast_dict)

# 检查所有指标是否存在
# RSI → ✅ 已注册
# MACD → ✅ 已注册

result = {
    "valid": True,
    "unknown_indicators": [],
    "suggestions": {}
}
```

#### 第 4 步：构建 AST 树
```python
# ast_engine.py
rule_ast = parse_ast_from_dict(ast_dict)

# 树结构：
LogicalNode(AND)
├── OperatorNode(<)
│   ├── IndicatorNode("RSI", params={"period": 14})
│   └── ConstantNode(30)
└── OperatorNode(>)
    ├── IndicatorNode("MACD", component="DIF")
    └── IndicatorNode("MACD", component="DEA")
```

#### 第 5 步：创建触发器
```python
# triggers.py
event_bus = EventBus()
local_ctx = LocalContext("600519.SH", window_size=100)

trigger = AstRuleTrigger(
    rule_ast=rule_ast,
    event_bus=event_bus,
    context=local_ctx
)

# 触发器自动订阅 BarEvent
# event_bus.subscribe(BarEvent, trigger._on_bar, symbol="600519.SH")
```

#### 第 6 步：行情数据到达
```python
# 模拟行情网关推送 K 线
bar = BarEvent(
    symbol="600519.SH",
    timestamp=datetime.now(),
    open=1850.0,
    high=1860.0,
    low=1845.0,
    close=1855.0,
    volume=1000000
)

event_bus.publish(bar)
```

#### 第 7 步：触发器处理事件
```python
# triggers.py - AstRuleTrigger._on_bar()

# 1. 更新上下文
self.context.update_bar(bar)  # 添加到 K 线窗口，清空缓存

# 2. 求值规则
result = self.rule_ast.evaluate(self.context)

# 求值过程：
# LogicalNode(AND).evaluate()
#   → OperatorNode(<).evaluate()
#       → IndicatorNode("RSI").evaluate()
#           → LocalContext.__getattr__("rsi")
#               → find_indicator("RSI")
#               → compute_rsi(bars, period=14)
#               → 返回 28.5
#       → ConstantNode(30).evaluate()
#           → 返回 30
#       → 28.5 < 30 → True
#   → OperatorNode(>).evaluate()
#       → IndicatorNode("MACD", "DIF").evaluate()
#           → compute_macd(bars) → (0.5, 0.3, 0.4)
#           → 返回 0.5
#       → IndicatorNode("MACD", "DEA").evaluate()
#           → 从缓存读取 MACD → (0.5, 0.3, 0.4)
#           → 返回 0.3
#       → 0.5 > 0.3 → True
#   → True AND True → True

# 3. 满足条件，发射信号
if result:
    signal = SignalEvent(
        symbol="600519.SH",
        signal_type="BUY",
        reason="RSI < 30 AND MACD金叉",
        timestamp=bar.timestamp
    )
    self.event_bus.publish(signal)
```

#### 第 8 步：信号推送给交易员
```python
# 信号处理器订阅 SignalEvent
class SignalHandler:
    def __init__(self, event_bus):
        event_bus.subscribe(SignalEvent, self.on_signal)

    def on_signal(self, signal):
        # 推送到钉钉
        send_dingtalk_message(
            f"【买入信号】{signal.symbol}\n"
            f"原因：{signal.reason}\n"
            f"时间：{signal.timestamp}"
        )

        # 推送到交易终端
        send_to_trading_terminal(signal)

        # 记录到数据库
        save_to_database(signal)

# 交易员收到通知：
"""
【买入信号】600519.SH
原因：RSI < 30 AND MACD金叉
时间：2026-03-28 14:30:00
"""
```

---

## 交互时序图

```
交易员          nl_parser      indicator_meta    ast_engine      triggers        context         event_bus       交易员
  │                │                 │                │               │               │               │              │
  │  输入规则      │                 │                │               │               │               │              │
  ├───────────────>│                 │                │               │               │               │              │
  │                │  校验指标       │                │               │               │               │              │
  │                ├────────────────>│                │               │               │               │              │
  │                │<────────────────┤                │               │               │               │              │
  │                │  返回 JSON AST  │                │               │               │               │              │
  │<───────────────┤                 │                │               │               │               │              │
  │                │                 │                │               │               │               │              │
  │  创建触发器    │                 │                │               │               │               │              │
  ├───────────────────────────────────────────────────>│               │               │              │              │
  │                │                 │                │  订阅 BarEvent│               │              │              │
  │                │                 │                ├───────────────────────────────>│              │              │
  │                │                 │                │               │               │              │              │
  │  行情到达      │                 │                │               │               │              │              │
  ├───────────────────────────────────────────────────────────────────────────────────>│              │              │
  │                │                 │                │  通知触发器   │               │              │              │
  │                │                 │                │<──────────────────────────────┤              │              │
  │                │                 │                │  更新 K 线    │               │              │              │
  │                │                 │                ├───────────────>│               │              │              │
  │                │                 │                │  求值 AST     │               │              │              │
  │                │                 │                │  计算 RSI     │               │              │              │
  │                │                 │                ├───────────────>│               │              │              │
  │                │                 │                │<───────────────┤               │              │              │
  │                │                 │                │  计算 MACD    │               │              │              │
  │                │                 │                ├───────────────>│               │              │              │
  │                │                 │                │<───────────────┤               │              │              │
  │                │                 │                │  发射信号     │               │              │              │
  │                │                 │                ├───────────────────────────────>│              │              │
  │                │                 │                │               │               │  推送信号    │              │
  │                │                 │                │               │               ├──────────────────────────────>│
  │                │                 │                │               │               │              │  收到通知    │
```

---

## 扩展性设计

### 1. 添加新指标
```python
# 定义计算函数
def compute_atr(bars, period=14):
    # ATR 计算逻辑
    return atr_value

# 注册指标
register_indicator(IndicatorMeta(
    name="ATR",
    aliases=("atr", "真实波幅"),
    default_params={"period": 14},
    compute_func=compute_atr,
    required_bars=14,
    output_type="single",
    description="平均真实波幅，衡量市场波动性"
))

# 立即可用
"当 ATR 大于 50 时减仓"  # 自然语言解析自动支持
```

### 2. 集成 TA-Lib
```python
# 替换简化实现为 TA-Lib
import talib

def compute_rsi_talib(bars, period=14):
    closes = np.array([bar.close for bar in bars])
    return talib.RSI(closes, timeperiod=period)[-1]

# 更新注册表
register_indicator(IndicatorMeta(
    name="RSI",
    compute_func=compute_rsi_talib,  # 替换计算函数
    # 其他参数不变
))
```

### 3. 添加新的触发器类型
```python
class TimeWindowTrigger:
    """时间窗口触发器：仅在特定时间段内生效"""
    def __init__(self, rule_ast, start_time, end_time):
        self.rule_ast = rule_ast
        self.start_time = start_time
        self.end_time = end_time

    def _on_bar(self, event):
        # 检查时间窗口
        if not (self.start_time <= event.timestamp.time() <= self.end_time):
            return

        # 求值规则
        result = self.rule_ast.evaluate(self.context)
        if result:
            self.event_bus.publish(SignalEvent(...))
```

### 4. 多策略组合
```python
# 策略 A：RSI 超卖买入
rule_a = parse_natural_language("当 RSI 小于 30 时买入")

# 策略 B：MACD 金叉买入
rule_b = parse_natural_language("当 MACD 金叉时买入")

# 策略 C：组合策略（A OR B）
rule_c = {
    "type": "logical",
    "op": "OR",
    "operands": [rule_a, rule_b]
}

# 创建触发器
trigger = AstRuleTrigger(parse_ast_from_dict(rule_c), event_bus, context)
```

---

## 性能优化

### 1. Symbol 路由（已实现）
- **优化前**：O(N) 遍历所有订阅者
- **优化后**：O(1) 精准定位特定品种的订阅者
- **效果**：1000+ 品种场景下性能提升显著

### 2. 防抖机制（已实现）
- **问题**：高频信号雪崩（1 秒内触发 100 次）
- **方案**：2 秒冷却期，同一触发器 2 秒内只发射一次信号
- **效果**：避免信号风暴

### 3. 增量指标计算（待实现）
- **问题**：每次 Bar 更新全量重算所有指标（O(N)）
- **方案**：状态机增量计算（O(1)）
- **示例**：
  ```python
  # 当前：全量计算
  sma = sum(closes[-20:]) / 20

  # 优化：增量更新
  sma_new = sma_old + (new_close - old_close) / 20
  ```

### 4. 异步事件总线（待实现）
- **问题**：同步处理阻塞主线程
- **方案**：使用 `asyncio` 实现异步事件总线
- **效果**：提升并发处理能力

---

## 总结

### 核心优势
1. **自然语言输入**：交易员无需编程，用中文描述规则
2. **智能校验**：自动检测未知指标，提供相似建议
3. **极致解耦**：事件驱动架构，模块间松耦合
4. **高性能**：Symbol 路由、惰性求值、防抖机制
5. **可扩展**：用户可注册自定义指标和触发器

### 技术亮点
- **AST 求值引擎**：声明式规则，易于序列化和可视化
- **指标元数据系统**：零配置，支持 150+ 指标（可扩展 TA-Lib）
- **事件总线优化**：O(1) Symbol 路由，弱引用防内存泄漏
- **LLM 集成**：Claude API 实现自然语言解析

### 应用场景
- 私募资金盘中异动监控
- 动态仓位再平衡
- 多因子量化策略
- 风控规则引擎

---

**文档版本**：v1.0
**最后更新**：2026-03-28
**作者**：CEP 开发团队
