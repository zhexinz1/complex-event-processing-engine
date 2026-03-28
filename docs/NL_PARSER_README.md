# 自然语言规则解析系统

## 概述

本系统实现了从自然语言到 JSON AST 的规则解析，支持参数化技术指标和智能校验。

## 核心模块

### 1. `indicator_meta.py` - 指标元数据系统

**功能**：
- 指标注册表，预注册 6 个常用指标（RSI, MACD, KDJ, SMA, EMA, BOLL）
- 支持中英文别名（大小写不敏感）
- 参数化指标计算
- 相似指标建议

**已注册指标**：
```python
RSI   - 相对强弱指标（别名：rsi, 相对强弱指标）
MACD  - 指数平滑异同移动平均线（别名：macd, 指数平滑异同移动平均线）
KDJ   - 随机指标（别名：kdj, 随机指标, stoch）
SMA   - 简单移动平均线（别名：sma, ma, 简单移动平均, 均线）
EMA   - 指数移动平均线（别名：ema, 指数移动平均）
BOLL  - 布林带（别名：boll, 布林带, bollinger）
```

**使用示例**：
```python
from indicator_meta import find_indicator, suggest_similar_indicators

# 查找指标（支持别名）
meta = find_indicator("相对强弱指标")  # 返回 RSI 的元数据
meta = find_indicator("kdj")           # 返回 KDJ 的元数据

# 获取相似指标建议
suggestions = suggest_similar_indicators("均线")  # 返回 ['SMA', 'MACD']
```

### 2. `ast_engine.py` - AST 引擎扩展

**新增节点类型**：
- `IndicatorNode` - 支持参数化指标计算

**使用示例**：
```python
from ast_engine import IndicatorNode, parse_ast_from_dict

# 参数化 RSI
rsi_node = IndicatorNode("RSI", params={"period": 20})
result = rsi_node.evaluate(local_context)

# MACD 组件提取
macd_dif = IndicatorNode("MACD", component="DIF")
dif_value = macd_dif.evaluate(local_context)

# 从 JSON 解析
rule_json = {
    "type": "operator",
    "op": "<",
    "left": {"type": "indicator", "name": "RSI", "params": {"period": 14}},
    "right": {"type": "const", "value": 30}
}
rule_ast = parse_ast_from_dict(rule_json)
```

### 3. `nl_parser.py` - 自然语言解析器

**功能**：
- 使用 Claude API 将自然语言转换为 JSON AST
- 自动校验指标是否存在
- 提供相似指标建议

**环境要求**：
```bash
# 安装依赖
pip install anthropic

# 设置 API Key
export ANTHROPIC_API_KEY='your-api-key'
```

**使用示例**：
```python
from nl_parser import parse_natural_language, validate_and_suggest

# 基础解析
ast = parse_natural_language("当 RSI 小于 30 时买入")

# 解析 + 校验
result = validate_and_suggest("当 RSI 小于 30 且 MACD 金叉时买入")
print(result['valid'])              # True/False
print(result['ast'])                # JSON AST
print(result['unknown_indicators']) # 未知指标列表
print(result['suggestions'])        # 相似指标建议
```

**支持的自然语言模式**：
```
✅ "当 RSI 小于 30 时买入"
✅ "当 RSI 小于 30 且 MACD 金叉时买入"
✅ "当 KDJ 的 K 值大于 D 值且 J 值小于 20 时买入"
✅ "当价格突破布林带上轨时卖出"
```

## 完整示例

运行示例代码：
```bash
python3 example_nl_parser.py
```

示例包含：
1. 参数化指标计算（RSI(14) vs RSI(20)）
2. JSON 规则解析和求值
3. 指标查找和别名测试
4. 自然语言规则解析（需要 API Key）

## JSON AST 格式规范

### 指标节点
```json
{
  "type": "indicator",
  "name": "RSI",
  "params": {"period": 14},
  "component": "DIF"  // 仅多值指标需要
}
```

### 完整规则示例
```json
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

## 扩展指标

添加自定义指标：
```python
from indicator_meta import register_indicator, IndicatorMeta

def compute_custom_indicator(bars, param1=10):
    # 自定义计算逻辑
    return result

# 注册指标
register_indicator(IndicatorMeta(
    name="CUSTOM",
    aliases=("custom", "自定义指标"),
    default_params={"param1": 10},
    compute_func=compute_custom_indicator,
    required_bars=10,
    output_type="single",
    description="自定义指标描述"
))
```

## 优势

1. **零配置**：预注册常用指标，开箱即用
2. **类型安全**：启动时校验元数据完整性
3. **友好错误**：提示相似指标和可用参数
4. **可扩展**：用户可注册自定义指标
5. **多语言**：支持中英文别名
6. **参数化**：支持动态指定指标参数
7. **智能校验**：自动检测未知指标并提供建议

## 注意事项

1. **指标计算**：当前使用简化的 Python 实现，生产环境建议集成 TA-Lib
2. **API 调用**：自然语言解析需要 Anthropic API Key
3. **数据充足性**：指标计算前会自动检查 K 线数量是否充足
4. **多值指标**：MACD、KDJ、BOLL 需要指定 component 参数

## 测试结果

✅ 参数化指标计算正常
✅ JSON 规则解析正常
✅ 指标查找和别名匹配正常
✅ 相似指标建议正常
⚠️ 自然语言解析需要安装 Anthropic SDK
