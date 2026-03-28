# CEP 项目目录结构

```
CEP/
├── cep/                          # 核心框架包
│   ├── __init__.py
│   ├── core/                     # 核心组件
│   │   ├── __init__.py
│   │   ├── events.py            # 事件定义（BaseEvent, TickEvent, BarEvent, etc.）
│   │   ├── event_bus.py         # 发布/订阅事件总线（二维字典 + Symbol 路由）
│   │   └── context.py           # 双层状态黑板（GlobalContext + LocalContext）
│   ├── engine/                   # 引擎模块
│   │   ├── __init__.py
│   │   └── ast_engine.py        # 抽象语法树求值器（组合模式）
│   └── triggers/                 # 触发器模块
│       ├── __init__.py
│       └── triggers.py          # 触发器实现（AstRuleTrigger, DeviationTrigger, CronTrigger）
│
├── rebalance/                    # 再平衡模块
│   ├── __init__.py
│   ├── portfolio_context.py     # 投资组合上下文
│   ├── rebalance_engine.py      # 再平衡引擎
│   ├── rebalance_handler.py     # 再平衡处理器
│   └── rebalance_triggers.py    # 再平衡触发器
│
├── nlp/                          # 自然语言解析模块
│   ├── __init__.py
│   ├── nl_parser.py             # 自然语言规则解析器
│   └── indicator_meta.py        # 指标元数据
│
├── examples/                     # 示例代码
│   ├── __init__.py
│   └── example_usage.py         # 完整的系统集成示例
│
├── tests/                        # 测试代码
│   └── __init__.py
│
├── docs/                         # 文档
│   ├── ARCHITECTURE.md          # 架构设计文档
│   ├── JSON_RULE_SPECIFICATION.md  # JSON 规则规范
│   ├── NL_PARSER_README.md      # 自然语言解析器说明
│   ├── TEST_RESULTS.md          # 测试结果
│   └── DIRECTORY_STRUCTURE.md   # 本文档
│
├── README.md                     # 项目主文档
├── reminder.txt                  # 开发提醒事项
└── .gitignore                    # Git 忽略配置
```

## 模块说明

### 1. cep/ - 核心框架
ECA (Event-Condition-Action) 架构的核心实现：
- **core/**: 事件系统、事件总线、上下文管理
- **engine/**: AST 求值引擎
- **triggers/**: 各类触发器实现

### 2. rebalance/ - 再平衡模块
动态仓位再平衡功能，用于私募资金的盘中异动监控。

### 3. nlp/ - 自然语言解析
将自然语言规则转换为 AST 的解析器。

### 4. examples/ - 示例代码
完整的使用示例，展示如何集成各个模块。

### 5. tests/ - 测试代码
单元测试和集成测试。

### 6. docs/ - 文档
所有项目文档集中管理。

## 导入示例

```python
# 导入核心组件
from cep.core import EventBus, TickEvent, GlobalContext, LocalContext

# 导入引擎
from cep.engine import AstEngine

# 导入触发器
from cep.triggers import AstRuleTrigger, DeviationTrigger

# 导入再平衡模块
from rebalance import RebalanceEngine, PortfolioContext

# 导入自然语言解析
from nlp import NLParser
```

## 设计原则

1. **模块化**: 按功能划分清晰的模块边界
2. **可扩展**: 每个模块都可以独立扩展
3. **易维护**: 相关代码集中管理，便于查找和修改
4. **标准化**: 遵循 Python 包结构规范
