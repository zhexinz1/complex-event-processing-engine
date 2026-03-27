# CEP 规则引擎 JSON 规则定义规范

## 概述

本文档定义了如何将自然语言规则转换为 JSON 格式，以便 CEP 规则引擎能够解析和执行。

## 架构流程

```
自然语言规则
    ↓
大语言模型翻译
    ↓
JSON 规则定义
    ↓
parse_ast_from_dict() 解析
    ↓
AST 树（Node 对象）
    ↓
AstRuleTrigger 触发器
    ↓
事件驱动执行
    ↓
SignalEvent 信号发射
```

## JSON Schema 定义

### 完整结构

```json
{
  "rule_id": "规则唯一标识符",
  "symbol": "标的代码（如 600519.SH）",
  "trigger_type": "触发器类型（ast_rule | deviation | cron）",
  "condition": {
    "type": "节点类型（const | var | operator | logical）",
    ...
  },
  "action": {
    "signal_type": "信号类型（TRADE_OPPORTUNITY | REBALANCE_TRIGGER | FUND_ALLOCATION）",
    "payload": {
      "自定义字段": "自定义值"
    }
  }
}
```

### 节点类型详解

#### 1. 常量节点（ConstantNode）

表示固定的数值或字符串。

```json
{
  "type": "const",
  "value": 30
}
```

**示例**：
- `{"type": "const", "value": 5.0}` → 数字 5.0
- `{"type": "const", "value": "AAPL"}` → 字符串 "AAPL"
- `{"type": "const", "value": true}` → 布尔值 true

#### 2. 变量节点（VariableNode）

从 Context 中读取数据（支持本地指标和全局宏观数据）。

```json
{
  "type": "var",
  "name": "变量名"
}
```

**本地指标示例**（从 LocalContext 读取）：
- `{"type": "var", "name": "rsi"}` → RSI 指标
- `{"type": "var", "name": "macd_golden_cross"}` → MACD 金叉状态
- `{"type": "var", "name": "turnover_rate"}` → 换手率

**全局数据示例**（从 GlobalContext 读取）：
- `{"type": "var", "name": "cpi"}` → CPI 数据
- `{"type": "var", "name": "vix"}` → VIX 恐慌指数
- `{"type": "var", "name": "interest_rate"}` → 利率

#### 3. 运算符节点（OperatorNode）

表示算术或比较运算。

```json
{
  "type": "operator",
  "op": "运算符（+, -, *, /, >, <, >=, <=, ==, !=）",
  "left": {...},
  "right": {...}
}
```

**示例**：
```json
{
  "type": "operator",
  "op": ">",
  "left": {"type": "var", "name": "rsi"},
  "right": {"type": "const", "value": 30}
}
```
表示：`rsi > 30`

#### 4. 逻辑节点（LogicalNode）

表示逻辑运算（AND、OR、NOT）。

```json
{
  "type": "logical",
  "op": "逻辑运算符（AND | OR | NOT）",
  "operands": [...]
}
```

**AND 示例**：
```json
{
  "type": "logical",
  "op": "AND",
  "operands": [
    {"type": "operator", "op": ">", "left": {...}, "right": {...}},
    {"type": "operator", "op": "<", "left": {...}, "right": {...}}
  ]
}
```

**NOT 示例**：
```json
{
  "type": "logical",
  "op": "NOT",
  "operands": [
    {"type": "var", "name": "is_trading_halted"}
  ]
}
```

## 完整示例

### 示例 1：贵州茅台买入信号

**自然语言规则**：
> 当股票贵州茅台换手率大于5%，且国家公布的CPI数据跌破2%，同时MACD金叉，则发出买入信号

**JSON 规则**：
```json
{
  "rule_id": "moutai_buy_signal_001",
  "symbol": "600519.SH",
  "trigger_type": "ast_rule",
  "condition": {
    "type": "logical",
    "op": "AND",
    "operands": [
      {
        "type": "operator",
        "op": ">",
        "left": {"type": "var", "name": "turnover_rate"},
        "right": {"type": "const", "value": 5.0}
      },
      {
        "type": "operator",
        "op": "<",
        "left": {"type": "var", "name": "cpi"},
        "right": {"type": "const", "value": 2.0}
      },
      {
        "type": "var",
        "name": "macd_golden_cross"
      }
    ]
  },
  "action": {
    "signal_type": "TRADE_OPPORTUNITY",
    "payload": {
      "direction": "BUY",
      "strategy": "moutai_macro_technical"
    }
  }
}
```

### 示例 2：超买卖出信号

**自然语言规则**：
> 当 RSI 大于 70 且价格突破布林带上轨，发出卖出信号

**JSON 规则**：
```json
{
  "rule_id": "overbought_sell_001",
  "symbol": "000001.SZ",
  "trigger_type": "ast_rule",
  "condition": {
    "type": "logical",
    "op": "AND",
    "operands": [
      {
        "type": "operator",
        "op": ">",
        "left": {"type": "var", "name": "rsi"},
        "right": {"type": "const", "value": 70}
      },
      {
        "type": "operator",
        "op": ">",
        "left": {"type": "var", "name": "close"},
        "right": {"type": "var", "name": "boll_upper"}
      }
    ]
  },
  "action": {
    "signal_type": "TRADE_OPPORTUNITY",
    "payload": {
      "direction": "SELL",
      "strategy": "overbought_reversal"
    }
  }
}
```

### 示例 3：复杂组合条件

**自然语言规则**：
> 当（RSI < 30 或 MACD 金叉）且成交量大于平均成交量的 2 倍，且 VIX 低于 20，发出买入信号

**JSON 规则**：
```json
{
  "rule_id": "complex_buy_001",
  "symbol": "600000.SH",
  "trigger_type": "ast_rule",
  "condition": {
    "type": "logical",
    "op": "AND",
    "operands": [
      {
        "type": "logical",
        "op": "OR",
        "operands": [
          {
            "type": "operator",
            "op": "<",
            "left": {"type": "var", "name": "rsi"},
            "right": {"type": "const", "value": 30}
          },
          {
            "type": "var",
            "name": "macd_golden_cross"
          }
        ]
      },
      {
        "type": "operator",
        "op": ">",
        "left": {"type": "var", "name": "volume"},
        "right": {
          "type": "operator",
          "op": "*",
          "left": {"type": "var", "name": "avg_volume"},
          "right": {"type": "const", "value": 2.0}
        }
      },
      {
        "type": "operator",
        "op": "<",
        "left": {"type": "var", "name": "vix"},
        "right": {"type": "const", "value": 20}
      }
    ]
  },
  "action": {
    "signal_type": "TRADE_OPPORTUNITY",
    "payload": {
      "direction": "BUY",
      "strategy": "complex_technical"
    }
  }
}
```

## 系统处理流程

### 1. JSON 解析阶段

```python
import json
from ast_engine import parse_ast_from_dict

# 加载 JSON 规则
rule_dict = json.loads(rule_json)

# 解析为 AST 树
rule_tree = parse_ast_from_dict(rule_dict["condition"])
```

### 2. 环境准备阶段

```python
from context import GlobalContext, LocalContext
from event_bus import EventBus
from advanced_indicators import ADVANCED_INDICATOR_REGISTRY

# 创建全局上下文（宏观数据）
global_context = GlobalContext()
global_context.set("cpi", 1.8)
global_context.set("vix", 15.5)

# 创建本地上下文（品种数据 + 指标）
local_context = LocalContext(
    symbol="600519.SH",
    indicator_registry=ADVANCED_INDICATOR_REGISTRY,
    global_context=global_context  # 关键：传入全局上下文引用
)
```

### 3. 触发器创建阶段

```python
from triggers import AstRuleTrigger

# 创建触发器
trigger = AstRuleTrigger(
    event_bus=event_bus,
    trigger_id="trigger_001",
    rule_tree=rule_tree,
    local_context=local_context,
    rule_id=rule_dict["rule_id"]
)

# 注册到事件总线
trigger.register()
```

### 4. 运行时执行阶段

```
BarEvent 到达
    ↓
EventBus 路由到 AstRuleTrigger
    ↓
local_context.update_bar(event)  # 更新 K 线窗口，清空缓存
    ↓
rule_tree.evaluate(local_context)  # 递归求值 AST 树
    ↓
    ├─ VariableNode("turnover_rate") → 惰性计算换手率
    ├─ VariableNode("cpi") → 从 global_context 读取
    └─ VariableNode("macd_golden_cross") → 惰性计算金叉状态
    ↓
若结果为 True → 发射 SignalEvent
```

## 数据源说明

### 本地指标（LocalContext）

需要在 `indicator_registry` 中注册计算函数：

```python
def compute_turnover_rate(bars: list[BarEvent]) -> float:
    # 计算换手率逻辑
    ...

def compute_macd_golden_cross(bars: list[BarEvent]) -> bool:
    # 判断 MACD 金叉逻辑
    ...

indicator_registry = {
    "turnover_rate": compute_turnover_rate,
    "macd_golden_cross": compute_macd_golden_cross,
    "rsi": compute_rsi,
    "sma": compute_sma,
}
```

### 全局数据（GlobalContext）

需要提前设置到全局上下文：

```python
global_context.set("cpi", 1.8)
global_context.set("gdp_growth", 5.2)
global_context.set("vix", 15.5)
global_context.set("interest_rate", 3.5)
```

## 支持的运算符

### 算术运算符
- `+` 加法
- `-` 减法
- `*` 乘法
- `/` 除法
- `%` 取模

### 比较运算符
- `>` 大于
- `>=` 大于等于
- `<` 小于
- `<=` 小于等于
- `==` 等于
- `!=` 不等于

### 逻辑运算符
- `AND` 逻辑与（所有条件必须为真）
- `OR` 逻辑或（至少一个条件为真）
- `NOT` 逻辑非（取反）

## 信号类型

```python
class SignalType(str, Enum):
    TRADE_OPPORTUNITY = "TRADE_OPPORTUNITY"      # 交易机会
    REBALANCE_TRIGGER = "REBALANCE_TRIGGER"      # 再平衡触发
    FUND_ALLOCATION = "FUND_ALLOCATION"          # 资金分配
    RISK_WARNING = "RISK_WARNING"                # 风险预警
```

## 注意事项

### 1. 跨 Context 数据访问

✅ **正确做法**：LocalContext 持有 GlobalContext 引用

```python
local_context = LocalContext(
    symbol="600519.SH",
    global_context=global_context  # 传入引用
)
```

❌ **错误做法**：不传入 global_context，导致无法访问宏观数据

### 2. 复杂指标计算

对于"MACD 金叉"这种状态判断，需要注册为布尔型指标：

```python
def compute_macd_golden_cross(bars: list[BarEvent]) -> bool:
    # 计算当前和前一根 K 线的 MACD
    macd_curr, signal_curr = compute_macd(bars)
    macd_prev, signal_prev = compute_macd(bars[:-1])

    # 金叉：前一根 MACD < Signal，当前 MACD > Signal
    return macd_prev <= signal_prev and macd_curr > signal_curr
```

### 3. 数据不足处理

指标计算函数应该处理数据不足的情况：

```python
def compute_rsi(bars: list[BarEvent], period: int = 14) -> Optional[float]:
    if len(bars) < period + 1:
        return None  # 数据不足，返回 None
    # ... 计算逻辑
```

当指标返回 `None` 时，比较运算会抛出 `TypeError`，触发器会捕获异常并记录日志。

### 4. 惰性求值机制

指标只在被访问时才计算，计算结果会缓存：

```python
# 首次访问，触发计算
rsi_value = local_context.rsi

# 再次访问，返回缓存值（不重新计算）
rsi_value_again = local_context.rsi

# 新 Bar 到达，缓存失效，下次访问会重新计算
local_context.update_bar(new_bar)
```

## 扩展指南

### 添加新指标

1. 在 `advanced_indicators.py` 中定义计算函数：

```python
def compute_my_indicator(bars: list[BarEvent]) -> float:
    # 你的计算逻辑
    return result
```

2. 注册到指标表：

```python
ADVANCED_INDICATOR_REGISTRY = {
    "my_indicator": compute_my_indicator,
    ...
}
```

3. 在 JSON 规则中使用：

```json
{
  "type": "var",
  "name": "my_indicator"
}
```

### 添加新的全局数据源

```python
# 定期更新全局数据
global_context.set("new_macro_data", value)

# 在规则中使用
{
  "type": "var",
  "name": "new_macro_data"
}
```

## 性能优化建议

1. **指标计算优化**：对于高频场景，考虑实现增量计算（O(1)）而非全量重算（O(N)）
2. **缓存策略**：合理设置 K 线窗口大小，避免内存浪费
3. **事件路由**：利用 EventBus 的 Symbol 路由机制，避免无效回调
4. **防抖机制**：对于高频信号，添加冷却期防止雪崩

## 测试验证

完整的测试代码见 `test_json_rule_complete.py`，包括：
- 跨 Context 数据访问测试
- JSON 解析和 AST 构建测试
- 完整的规则执行流程测试

运行测试：
```bash
python3 test_json_rule_complete.py
```

## 总结

CEP 规则引擎的 JSON 规则定义提供了：
- ✅ 声明式的规则表达（易于序列化和存储）
- ✅ 灵活的条件组合（支持任意复杂的布尔逻辑）
- ✅ 跨 Context 数据访问（本地指标 + 全局宏观数据）
- ✅ 惰性求值机制（按需计算，避免浪费）
- ✅ 事件驱动架构（解耦良好，易于扩展）

通过这套规范，大语言模型可以将自然语言规则准确翻译为 JSON，系统能够正确解析和执行。
