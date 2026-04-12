# CEP 规则触发系统（Complex Event Processing）

基于 ECA (Event-Condition-Action) 架构和事件总线的量化交易触发系统，用于私募资金的盘中异动监控和动态仓位再平衡。

## 核心设计原则

1. **极致解耦（Decoupling）**：触发器只负责判定条件并发射事件，绝不直接调用下游业务代码
2. **声明式规则（Declarative Rules）**：规则以 JSON AST 表达，可由大语言模型从自然语言编译生成
3. **事件驱动（Event-Driven）**：所有状态流转由事件（Tick, Bar, Timer）驱动，避免轮询
4. **惰性求值（Lazy Evaluation）**：技术指标按需计算并缓存，避免算力浪费

## 目录结构

```
CEP/
├── cep/                        # 核心框架包
│   ├── core/                   # 事件、事件总线、上下文黑板
│   │   ├── events.py
│   │   ├── event_bus.py
│   │   └── context.py
│   ├── engine/                 # AST 规则求值引擎
│   │   └── ast_engine.py
│   └── triggers/               # 触发器实现
│       └── triggers.py
│
├── rebalance/                  # 再平衡模块（5步计算链路）
│   ├── portfolio_context.py
│   ├── rebalance_engine.py
│   ├── rebalance_triggers.py
│   └── rebalance_handler.py
│
├── nlp/                        # 自然语言 → JSON AST 解析
│   ├── nl_parser.py
│   └── indicator_meta.py
│
├── adapters/                   # 外部接口适配器层
│   ├── market_gateway.py       # 行情网关（CTP/Mock）
│   ├── order_gateway.py        # 订单执行网关（迅投GT/Mock）
│   ├── config_source.py        # 配置数据源（DB/文件）
│   └── frontend_api.py         # RESTful 前端服务层
│
├── examples/                   # 集成示例
├── tests/                      # 单元与集成测试
├── config/                     # 策略配置文件
└── docs/                       # 核心文档
    ├── ARCHITECTURE.md         # 系统架构详细设计
    ├── INTEGRATION_GUIDE.md    # 外部接口对接指南
    └── JSON_RULE_SPECIFICATION.md  # AST JSON 规则格式规范
```

## 系统架构

```
自然语言规则
    ↓ nlp/nl_parser.py (Claude API)
JSON AST → cep/engine/ast_engine.py
    ↓
AstRuleTrigger (cep/triggers/)
    ↑ 订阅行情        ↓ 评估 AST      ↓ 发射信号
EventBus ←── adapters/market_gateway ──→ EventBus
    ↓
Handlers (rebalance_handler, 自定义)
```

## 快速开始

```bash
# 使用 uv 管理依赖
uv sync

# 运行完整集成示例
uv run -m examples.example_usage

# 运行导入验证测试
uv run tests/test_imports.py
```

> 所有文件使用绝对包路径导入，请始终从项目根目录 `/home/ubuntu/CEP` 运行。

### tushare数据API配置
先前往[个人主页](https://tushare.pro/user/token) 获取token，然后在`~/.bashrc`中添加`export TUSHARE_TOKEN=<YOUR_TOKEN>`，然后`source ~/.bashrc`生效环境变量

## 使用示例

```python
from cep.core import EventBus, GlobalContext, LocalContext
from cep.engine.ast_engine import build_and, build_comparison, Operator, parse_ast_from_dict
from cep.triggers import AstRuleTrigger
from cep.core.events import BarEvent, SignalEvent

# 1. 初始化事件总线与上下文
event_bus = EventBus()
global_ctx = GlobalContext()
global_ctx.set("cpi", 1.8)

local_ctx = LocalContext(symbol="600519.SH", global_context=global_ctx)

# 方式 A：代码构建 AST
rule_tree = build_and(
    build_comparison("rsi", Operator.LT, 30),
    build_comparison("close", Operator.GT, "sma"),
)

# 方式 B：从 LLM 生成的 JSON 加载 AST
# from nlp.nl_parser import parse_natural_language
# ast_dict = parse_natural_language("当 RSI 小于 30 且价格高于均线时买入")
# rule_tree = parse_ast_from_dict(ast_dict)

# 2. 创建并注册触发器
trigger = AstRuleTrigger(
    event_bus=event_bus,
    trigger_id="RULE_001",
    rule_tree=rule_tree,
    local_context=local_ctx,
)
trigger.register()

# 3. 订阅信号
def on_signal(signal: SignalEvent):
    print(f"Signal: {signal.signal_type} | {signal.payload}")

event_bus.subscribe(SignalEvent, on_signal)
```

## 扩展指南

### 添加自定义触发器（代码策略接口）

```python
from cep.triggers.triggers import BaseTrigger
from cep.core.events import BarEvent, SignalType

class MyMLTrigger(BaseTrigger):
    def __init__(self, event_bus, local_context, model):
        super().__init__(event_bus, trigger_id="ML_001")
        self.local_context = local_context
        self.model = model

    def register(self):
        self.event_bus.subscribe(BarEvent, self.on_event, symbol=self.local_context.symbol)

    def on_event(self, event: BarEvent):
        self.local_context.update_bar(event)
        proba = self.model.predict(self.local_context)
        if proba > 0.7:
            self._emit_signal(
                symbol=event.symbol,
                signal_type=SignalType.TRADE_OPPORTUNITY,
                payload={"confidence": proba}
            )
```

### 公共 API 导入路径

```python
from cep.core import EventBus, TickEvent, BarEvent, GlobalContext, LocalContext
from cep.engine import Node, Operator, LogicalOp
from cep.triggers import AstRuleTrigger, DeviationTrigger, CronTrigger
from rebalance import RebalanceEngine, PortfolioContext, RebalanceHandler
from nlp import parse_natural_language, validate_and_suggest, IndicatorMeta
```

## 相关文档

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — 完整的系统架构设计与数据流分析
- [`docs/INTEGRATION_GUIDE.md`](docs/INTEGRATION_GUIDE.md) — 外部接口（CTP/迅投GT/数据库）对接指南
- [`docs/JSON_RULE_SPECIFICATION.md`](docs/JSON_RULE_SPECIFICATION.md) — AST JSON 规则格式完整规范

## 技术栈

- Python 3.10+，`uv` 包管理
- 事件总线（发布/订阅 + Symbol O(1) 路由 + WeakRef 防泄漏）
- AST 规则引擎（Composite Pattern，支持 JSON 序列化/反序列化）
- Claude API（自然语言 → JSON AST 编译）
- CTP SDK（期货行情与交易接入，通过 `adapters/` 层隔离）
