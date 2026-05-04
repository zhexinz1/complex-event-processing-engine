"""
nl_parser.py — 自然语言规则解析器

使用 LLM API（Claude）将自然语言规则转换为 JSON AST 格式。

示例：
    输入: "当 RSI 小于 30 且 KDJ 金叉时买入"
    输出: {
        "type": "logical",
        "op": "AND",
        "operands": [
            {"type": "operator", "op": "<", "left": {"type": "indicator", "name": "RSI"}, "right": {"type": "const", "value": 30}},
            {"type": "operator", "op": ">", "left": {"type": "indicator", "name": "KDJ", "component": "K"}, "right": {"type": "indicator", "name": "KDJ", "component": "D"}}
        ]
    }
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)

# 尝试导入 anthropic，如果不可用则提供降级方案
try:
    import anthropic  # pyright: ignore[reportMissingImports]
    ANTHROPIC_AVAILABLE = True
except ImportError:
    anthropic = None
    ANTHROPIC_AVAILABLE = False
    logger.warning("Anthropic SDK not available. Natural language parsing will be disabled.")


# ---------------------------------------------------------------------------
# LLM 提示词模板
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """你是一个专业的量化交易规则解析器。你的任务是将用户的自然语言规则转换为标准的 JSON AST 格式。

## 支持的指标
- RSI: 相对强弱指标（0-100）
- MACD: 指数平滑异同移动平均线（返回 DIF, DEA, MACD）
- KDJ: 随机指标（返回 K, D, J）
- SMA/MA: 简单移动平均线
- EMA: 指数移动平均线
- BOLL: 布林带（返回 upper, middle, lower）

## JSON AST 格式规范

### 节点类型
1. **常量节点**: `{"type": "const", "value": 数值}`
2. **变量节点**: `{"type": "var", "name": "变量名"}`
3. **指标节点**: `{"type": "indicator", "name": "指标名", "params": {...}, "component": "组件名"}`
4. **运算符节点**: `{"type": "operator", "op": "运算符", "left": {...}, "right": {...}}`
5. **逻辑节点**: `{"type": "logical", "op": "逻辑运算符", "operands": [...]}`

### 运算符
- 比较: `>`, `>=`, `<`, `<=`, `==`, `!=`
- 逻辑: `AND`, `OR`, `NOT`

### 指标节点说明
- 单值指标（RSI, SMA, EMA）: `{"type": "indicator", "name": "RSI", "params": {"period": 14}}`
- 多值指标（MACD, KDJ, BOLL）需要指定组件:
  - MACD: `{"type": "indicator", "name": "MACD", "component": "DIF"}` (DIF/DEA/MACD)
  - KDJ: `{"type": "indicator", "name": "KDJ", "component": "K"}` (K/D/J)
  - BOLL: `{"type": "indicator", "name": "BOLL", "component": "upper"}` (upper/middle/lower)

## 示例

输入: "当 RSI 小于 30 时买入"
输出:
```json
{
  "type": "operator",
  "op": "<",
  "left": {"type": "indicator", "name": "RSI", "params": {"period": 14}},
  "right": {"type": "const", "value": 30}
}
```

输入: "当 RSI 小于 30 且 MACD 金叉时买入"
输出:
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

## 重要规则
1. 只返回 JSON，不要有任何其他文字
2. 使用标准的指标名称（大写）
3. 金叉 = DIF > DEA，死叉 = DIF < DEA
4. 默认参数：RSI(14), SMA(20), EMA(12), MACD(12,26,9), KDJ(9,3,3), BOLL(20,2)
5. 如果用户指定了参数，使用用户的参数
"""


# ---------------------------------------------------------------------------
# 自然语言解析函数
# ---------------------------------------------------------------------------

def parse_natural_language(
    text: str,
    api_key: Optional[str] = None,
    model: str = "claude-3-5-sonnet-20241022"
) -> dict[str, Any]:
    """
    使用 Claude API 将自然语言规则转换为 JSON AST。

    Args:
        text: 自然语言规则描述。
        api_key: Anthropic API Key（若为 None 则从环境变量读取）。
        model: 使用的模型名称。

    Returns:
        JSON AST 字典。

    Raises:
        ValueError: 若解析失败或 API 不可用。
    """
    if not ANTHROPIC_AVAILABLE:
        raise ValueError(
            "Anthropic SDK not installed. "
            "Please install it with: pip install anthropic"
        )

    # 获取 API Key
    api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError(
            "ANTHROPIC_API_KEY not found. "
            "Please set it as an environment variable or pass it as a parameter."
        )

    # 调用 Claude API
    if anthropic is None:
        raise ValueError("Anthropic SDK import failed unexpectedly")
    client = anthropic.Anthropic(api_key=api_key)

    try:
        logger.info(f"Parsing natural language rule: {text}")

        message = client.messages.create(
            model=model,
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            messages=[
                {"role": "user", "content": text}
            ]
        )

        # 提取响应内容
        response_text = ""
        for block in message.content:
            if getattr(block, "type", None) == "text":
                response_text = str(getattr(block, "text")).strip()
                break
        if not response_text:
            raise ValueError("Anthropic response did not include a text block")
        logger.debug(f"LLM response: {response_text}")

        # 解析 JSON
        # 移除可能的 markdown 代码块标记
        if response_text.startswith("```"):
            lines = response_text.split("\n")
            response_text = "\n".join(lines[1:-1])

        ast_dict = json.loads(response_text)
        logger.info("Successfully parsed natural language rule to AST")

        return ast_dict

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON from LLM response: {e}")
        raise ValueError(f"LLM returned invalid JSON: {e}")

    except Exception as e:
        logger.error(f"Failed to parse natural language rule: {e}")
        raise ValueError(f"Failed to parse rule: {e}")


def validate_and_suggest(text: str, api_key: Optional[str] = None) -> dict[str, Any]:
    """
    解析自然语言规则并验证指标是否存在。

    Args:
        text: 自然语言规则描述。
        api_key: Anthropic API Key。

    Returns:
        包含 AST 和验证结果的字典：
        {
            "ast": {...},
            "valid": True/False,
            "unknown_indicators": [...],
            "suggestions": {...}
        }
    """
    from nlp.indicator_meta import find_indicator, suggest_similar_indicators

    # 解析规则
    ast_dict = parse_natural_language(text, api_key)

    # 提取所有指标
    unknown_indicators = []
    suggestions = {}

    def extract_indicators(node: dict) -> None:
        """递归提取所有指标节点"""
        if node.get("type") == "indicator":
            indicator_name = node.get("name", "")
            if not find_indicator(indicator_name):
                unknown_indicators.append(indicator_name)
                suggestions[indicator_name] = suggest_similar_indicators(indicator_name)

        # 递归处理子节点
        if "left" in node:
            extract_indicators(node["left"])
        if "right" in node:
            extract_indicators(node["right"])
        if "operands" in node:
            for operand in node["operands"]:
                extract_indicators(operand)

    extract_indicators(ast_dict)

    return {
        "ast": ast_dict,
        "valid": len(unknown_indicators) == 0,
        "unknown_indicators": unknown_indicators,
        "suggestions": suggestions
    }
