# CEP 规则触发系统（Complex Event Processing）

基于 ECA (Event-Condition-Action) 架构和事件总线的量化交易触发系统，用于私募资金的盘中异动监控和动态仓位再平衡。

## 核心设计原则

1. **极致解耦（Decoupling）**：触发器只负责判定条件并发射事件，绝不直接调用下游业务代码
2. **事件驱动（Event-Driven）**：所有状态流转由事件（Tick, Bar, Timer）驱动，避免轮询
3. **惰性求值（Lazy Evaluation）**：技术指标按需计算，避免算力浪费

## 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                        EventBus                              │
│                    (发布/订阅中枢)                            │
└─────────────────────────────────────────────────────────────┘
         ▲                    │                    ▲
         │ publish            │ subscribe          │
         │                    ▼                    │
┌────────┴────────┐   ┌──────────────┐   ┌───────┴────────┐
│   Triggers      │   │   Handlers   │   │  Market Data   │
│  (规则引擎)      │   │ (业务逻辑)    │   │   Gateway      │
├─────────────────┤   ├──────────────┤   ├────────────────┤
│ AstRuleTrigger  │   │ OrderRouter  │   │ TickEvent      │
│ DeviationTrigger│   │ AlertService │   │ BarEvent       │
│ CronTrigger     │   │ RiskControl  │   │ TimerEvent     │
└─────────────────┘   └──────────────┘   └────────────────┘
         │
         │ read
         ▼
┌─────────────────────────────────────────────────────────────┐
│                    Context (状态黑板)                         │
├─────────────────────────────────────────────────────────────┤
│  GlobalContext: VIX, 总净值, 目标权重配置                      │
│  LocalContext:  K线窗口, 最新Tick, 当前持仓, 技术指标(惰性)    │
└─────────────────────────────────────────────────────────────┘
```

## 核心模块

### 1. events.py - 标准事件载荷
定义系统中流通的所有事件类型：
- `BaseEvent`: 所有事件的基类
- `TickEvent`: 逐笔行情事件
- `BarEvent`: K线事件
- `TimerEvent`: 定时器事件
- `SignalEvent`: 规则触发产生的信号包

### 2. event_bus.py - 全局事件总线
基于发布/订阅模式的事件总线：
- `subscribe(event_type, handler)`: 订阅事件
- `publish(event)`: 发布事件
- 支持同步调用，预留异步扩展接口

### 3. context.py - 双层状态黑板
- `GlobalContext`: 存储宏观数据（VIX、总净值、目标权重）
- `LocalContext`: 存储品种级数据（K线窗口、Tick、持仓）
- 支持惰性指标计算（通过 `__getattr__` 魔术方法）

### 4. ast_engine.py - 抽象语法树求值器
基于组合模式的 AST 树结构：
- `ConstantNode`: 常量节点
- `VariableNode`: 变量节点（从 Context 读取）
- `OperatorNode`: 算术/比较运算符
- `LogicalNode`: 逻辑运算符（AND, OR, NOT）

### 5. triggers.py - 触发器实现
- `AstRuleTrigger`: 基于 AST 的代数规则触发器
- `DeviationTrigger`: 持仓偏离触发器
- `CronTrigger`: 定时触发器

## 快速开始

```bash
# 运行示例代码
python example_usage.py
```

## 使用示例

```python
from event_bus import EventBus
from context import GlobalContext, LocalContext, DEFAULT_INDICATOR_REGISTRY
from ast_engine import build_and, build_comparison, Operator
from triggers import create_ast_trigger
from events import SignalEvent

# 1. 创建事件总线
event_bus = EventBus()

# 2. 创建上下文
global_context = GlobalContext()
local_context = LocalContext(
    symbol="600519.SH",
    indicator_registry=DEFAULT_INDICATOR_REGISTRY
)

# 3. 定义规则：(RSI < 30) AND (close > SMA)
rule_tree = build_and(
    build_comparison("rsi", Operator.LT, 30),
    build_comparison("close", Operator.GT, "sma"),
)

# 4. 创建并注册触发器
trigger = create_ast_trigger(
    event_bus=event_bus,
    trigger_id="MY_RULE",
    rule_tree=rule_tree,
    local_context=local_context,
)

# 5. 订阅信号并处理
def on_signal(signal):
    print(f"Signal received: {signal}")

event_bus.subscribe(SignalEvent, on_signal)

# 6. 发布行情事件
from events import BarEvent
bar = BarEvent(symbol="600519.SH", close=1850.0)
event_bus.publish(bar)
```

## 依赖注入设计

系统采用依赖注入（Dependency Injection）模式，所有组件通过构造函数接收依赖：

```python
# ✅ 推荐：依赖注入
trigger = AstRuleTrigger(
    event_bus=my_event_bus,  # 注入依赖
    trigger_id="RULE_001",
    rule_tree=rule_tree,
    local_context=local_context,
)

# ❌ 避免：全局单例
# from event_bus import global_event_bus  # 难以测试
```

## 扩展指南

### 添加自定义技术指标

```python
def compute_custom_indicator(bars: list[BarEvent]) -> float:
    # 自定义计算逻辑
    return result

# 注册到 LocalContext
indicator_registry = {
    "my_indicator": compute_custom_indicator,
}

local_context = LocalContext(
    symbol="600519.SH",
    indicator_registry=indicator_registry,
)

# 在规则中使用
rule = build_comparison("my_indicator", Operator.GT, 100)
```

### 添加自定义触发器

```python
from triggers import BaseTrigger

class MyCustomTrigger(BaseTrigger):
    def register(self):
        self.event_bus.subscribe(MyEvent, self.on_event)

    def on_event(self, event):
        # 自定义逻辑
        if condition:
            self._emit_signal(...)
```

## 技术栈

- Python 3.10+
- dataclasses (事件定义)
- typing (类型提示)
- abc (抽象基类)
- logging (日志)

## Troubleshooting

### CTP 环境前置检查

 `openctp-ctp`包含本地 C++ 扩展，在部分 Linux 主机上会依赖系统 locale `zh_CN.GB18030`。如果该 locale 未安装，程序可能在示例启动早期直接退出，并打印：

```text
terminate called after throwing an instance of 'std::runtime_error'
  what():  locale::facet::_S_create_c_locale name not valid
Aborted (core dumped)
```

建议在运行 CTP 示例前先检查：

```bash
locale -a | grep -i zh_CN
```

若结果中没有 `zh_CN.GB18030`，请先在宿主机生成 locale，再启动程序：

```bash
sudo locale-gen zh_CN.GB18030
```

## 许可证

MIT License
