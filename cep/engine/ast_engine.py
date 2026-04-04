"""
ast_engine.py — 抽象语法树求值器（代数型规则引擎）

基于组合模式（Composite Pattern）实现的 AST 树结构，用于表达和求值复杂的条件逻辑。
典型应用场景：
  - 技术指标组合条件：(RSI < 30) AND (MACD > 0) AND (close > sma)
  - 风控规则：(drawdown > 0.1) OR (leverage > 3.0)

设计优势：
  1. 声明式：规则以树结构表达，易于序列化（JSON/YAML）和可视化。
  2. 可组合：通过 LogicalNode 嵌套，支持任意复杂的布尔逻辑。
  3. 类型安全：每个节点有明确的求值语义，编译期可检查。

核心类：
  - Node:          抽象基类，定义 evaluate(context) 接口。
  - ConstantNode:  常量节点（如 30, 0.5, "AAPL"）。
  - VariableNode:  变量节点（从 Context 读取，如 "rsi", "close"）。
  - OperatorNode:  算术/比较运算符（+, -, *, /, >, <, ==, !=）。
  - LogicalNode:   逻辑运算符（AND, OR, NOT）。
"""

from __future__ import annotations

import logging
import operator
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Callable

from cep.core.context import LocalContext, GlobalContext

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 运算符枚举
# ---------------------------------------------------------------------------

class Operator(str, Enum):
    """算术和比较运算符。"""
    # 算术运算
    ADD = "+"
    SUB = "-"
    MUL = "*"
    DIV = "/"
    MOD = "%"

    # 比较运算
    GT  = ">"
    GE  = ">="
    LT  = "<"
    LE  = "<="
    EQ  = "=="
    NE  = "!="


class LogicalOp(str, Enum):
    """逻辑运算符。"""
    AND = "AND"
    OR  = "OR"
    NOT = "NOT"


# ---------------------------------------------------------------------------
# 运算符映射表（Operator -> Python 函数）
# ---------------------------------------------------------------------------

OPERATOR_MAP: dict[Operator, Callable[[Any, Any], Any]] = {
    Operator.ADD: operator.add,
    Operator.SUB: operator.sub,
    Operator.MUL: operator.mul,
    Operator.DIV: operator.truediv,
    Operator.MOD: operator.mod,
    Operator.GT:  operator.gt,
    Operator.GE:  operator.ge,
    Operator.LT:  operator.lt,
    Operator.LE:  operator.le,
    Operator.EQ:  operator.eq,
    Operator.NE:  operator.ne,
}


# ---------------------------------------------------------------------------
# AST 节点基类
# ---------------------------------------------------------------------------

class Node(ABC):
    """
    AST 节点抽象基类。

    所有节点必须实现 evaluate() 方法，接收 Context 并返回求值结果。
    """

    @abstractmethod
    def evaluate(self, context: LocalContext | GlobalContext) -> Any:
        """
        递归求值当前节点。

        Args:
            context: 上下文对象（LocalContext 或 GlobalContext）。

        Returns:
            求值结果（类型取决于节点类型）。
        """
        pass

    def __repr__(self) -> str:
        """返回节点的字符串表示（用于调试）。"""
        return f"{self.__class__.__name__}()"


# ---------------------------------------------------------------------------
# 叶子节点：常量和变量
# ---------------------------------------------------------------------------

class ConstantNode(Node):
    """
    常量节点，直接返回预设值。

    示例：
        >>> node = ConstantNode(30)
        >>> node.evaluate(context)  # 返回 30
    """

    def __init__(self, value: Any) -> None:
        self.value = value

    def evaluate(self, context: LocalContext | GlobalContext) -> Any:
        return self.value

    def __repr__(self) -> str:
        return f"ConstantNode({self.value!r})"


class VariableNode(Node):
    """
    变量节点，从 Context 中读取指定属性。

    示例：
        >>> node = VariableNode("rsi")
        >>> node.evaluate(local_context)  # 返回 context.rsi（触发惰性计算）
    """

    def __init__(self, var_name: str) -> None:
        self.var_name = var_name

    def evaluate(self, context: LocalContext | GlobalContext) -> Any:
        """
        从 Context 读取变量值。

        若变量不存在，抛出 AttributeError（由 Context.__getattr__ 处理）。
        """
        try:
            return getattr(context, self.var_name)
        except AttributeError as e:
            logger.error(f"Variable '{self.var_name}' not found in context: {e}")
            raise

    def __repr__(self) -> str:
        return f"VariableNode({self.var_name!r})"


class IndicatorNode(Node):
    """
    指标节点，支持参数化的技术指标计算。

    示例：
        >>> # RSI(14)
        >>> node = IndicatorNode("RSI", params={"period": 14})
        >>> node.evaluate(local_context)  # 返回 RSI 值

        >>> # MACD 的 DIF 组件
        >>> node = IndicatorNode("MACD", component="DIF")
        >>> node.evaluate(local_context)  # 返回 MACD 的 DIF 值
    """

    def __init__(
        self,
        name: str,
        params: dict[str, Any] | None = None,
        component: str | None = None
    ) -> None:
        """
        初始化指标节点。

        Args:
            name: 指标名称（如 "RSI", "MACD", "KDJ"）。
            params: 指标参数（如 {"period": 14}），若为 None 则使用默认参数。
            component: 多值指标的组件名（如 MACD 的 "DIF"/"DEA"/"MACD"）。
        """
        self.name = name
        self.params = params or {}
        self.component = component

    def evaluate(self, context: LocalContext | GlobalContext) -> Any:
        """
        计算指标值。

        Returns:
            指标计算结果（单值或多值元组的某个组件）。

        Raises:
            AttributeError: 若指标未注册。
            ValueError: 若数据不足或参数错误。
        """
        from nlp.indicator_meta import find_indicator

        # 查找指标元数据
        meta = find_indicator(self.name)
        if not meta:
            raise AttributeError(f"Unknown indicator: {self.name}")

        # 检查是否是 LocalContext
        if not isinstance(context, LocalContext):
            raise ValueError(f"Indicator '{self.name}' can only be evaluated on LocalContext")

        # 合并参数（用户参数覆盖默认参数）
        final_params = {**meta.default_params, **self.params}

        # 检查数据充足性
        if len(context.bar_window) < meta.required_bars:
            raise ValueError(
                f"Indicator '{self.name}' requires at least {meta.required_bars} bars, "
                f"but only {len(context.bar_window)} available"
            )

        # 计算指标
        bars = list(context.bar_window)
        if meta.compute_func is None:
            raise ValueError(f"Indicator '{self.name}' has no compute function registered")
        result = meta.compute_func(bars, **final_params)

        # 处理多值指标的组件提取
        if meta.output_type == "multi":
            if self.component is None:
                raise ValueError(
                    f"Indicator '{self.name}' returns multiple values. "
                    f"Please specify a component (e.g., component='DIF')"
                )

            # 根据指标类型提取组件
            if self.name.upper() == "MACD":
                component_map = {"DIF": 0, "DEA": 1, "MACD": 2}
            elif self.name.upper() == "KDJ":
                component_map = {"K": 0, "D": 1, "J": 2}
            elif self.name.upper() == "BOLL":
                component_map = {"upper": 0, "middle": 1, "lower": 2}
            else:
                raise ValueError(f"Unknown component mapping for indicator '{self.name}'")

            component_upper = self.component.upper() if self.name.upper() != "BOLL" else self.component.lower()
            if component_upper not in component_map:
                raise ValueError(
                    f"Invalid component '{self.component}' for indicator '{self.name}'. "
                    f"Valid components: {list(component_map.keys())}"
                )

            result = result[component_map[component_upper]]

        logger.debug(f"IndicatorNode: {self.name}{self.params} = {result}")
        return result

    def __repr__(self) -> str:
        component_str = f", component={self.component!r}" if self.component else ""
        return f"IndicatorNode({self.name!r}, params={self.params!r}{component_str})"


# ---------------------------------------------------------------------------
# 运算符节点
# ---------------------------------------------------------------------------

class OperatorNode(Node):
    """
    二元运算符节点（算术或比较）。

    示例：
        >>> # 表达式：rsi < 30
        >>> node = OperatorNode(
        ...     op=Operator.LT,
        ...     left=VariableNode("rsi"),
        ...     right=ConstantNode(30)
        ... )
        >>> node.evaluate(context)  # 返回 True 或 False
    """

    def __init__(self, op: Operator, left: Node, right: Node) -> None:
        self.op = op
        self.left = left
        self.right = right

    def evaluate(self, context: LocalContext | GlobalContext) -> Any:
        """
        递归求值左右子节点，然后应用运算符。

        Returns:
            运算结果（数值或布尔值）。
        """
        left_val = self.left.evaluate(context)
        right_val = self.right.evaluate(context)

        op_func = OPERATOR_MAP[self.op]
        result = op_func(left_val, right_val)

        logger.debug(
            f"OperatorNode: {left_val} {self.op.value} {right_val} = {result}"
        )
        return result

    def __repr__(self) -> str:
        return f"OperatorNode({self.op.value}, {self.left!r}, {self.right!r})"


# ---------------------------------------------------------------------------
# 逻辑运算符节点
# ---------------------------------------------------------------------------

class LogicalNode(Node):
    """
    逻辑运算符节点（AND, OR, NOT）。

    示例：
        >>> # 表达式：(rsi < 30) AND (macd > 0)
        >>> node = LogicalNode(
        ...     op=LogicalOp.AND,
        ...     operands=[
        ...         OperatorNode(Operator.LT, VariableNode("rsi"), ConstantNode(30)),
        ...         OperatorNode(Operator.GT, VariableNode("macd"), ConstantNode(0)),
        ...     ]
        ... )
        >>> node.evaluate(context)  # 返回 True 或 False
    """

    def __init__(self, op: LogicalOp, operands: list[Node]) -> None:
        """
        初始化逻辑节点。

        Args:
            op:       逻辑运算符（AND, OR, NOT）。
            operands: 子节点列表（AND/OR 至少 2 个，NOT 必须 1 个）。
        """
        self.op = op
        self.operands = operands

        # 参数校验
        if op == LogicalOp.NOT and len(operands) != 1:
            raise ValueError("NOT operator requires exactly 1 operand")
        if op in (LogicalOp.AND, LogicalOp.OR) and len(operands) < 2:
            raise ValueError(f"{op.value} operator requires at least 2 operands")

    def evaluate(self, context: LocalContext | GlobalContext) -> bool:
        """
        递归求值所有子节点，然后应用逻辑运算。

        Returns:
            布尔值。
        """
        if self.op == LogicalOp.AND:
            # 短路求值：遇到 False 立即返回
            for operand in self.operands:
                if not operand.evaluate(context):
                    return False
            return True

        elif self.op == LogicalOp.OR:
            # 短路求值：遇到 True 立即返回
            for operand in self.operands:
                if operand.evaluate(context):
                    return True
            return False

        elif self.op == LogicalOp.NOT:
            return not self.operands[0].evaluate(context)

        else:
            raise ValueError(f"Unknown logical operator: {self.op}")

    def __repr__(self) -> str:
        return f"LogicalNode({self.op.value}, {self.operands!r})"


# ---------------------------------------------------------------------------
# AST 构建辅助函数（Builder Pattern）
# ---------------------------------------------------------------------------

def build_comparison(
    var_name: str,
    op: Operator,
    value: Any,
) -> OperatorNode:
    """
    快速构建比较表达式：var_name op value。

    示例：
        >>> build_comparison("rsi", Operator.LT, 30)
        # 等价于：OperatorNode(Operator.LT, VariableNode("rsi"), ConstantNode(30))

    Args:
        var_name: 变量名。
        op:       比较运算符。
        value:    常量值。

    Returns:
        OperatorNode 实例。
    """
    return OperatorNode(
        op=op,
        left=VariableNode(var_name),
        right=ConstantNode(value),
    )


def build_and(*conditions: Node) -> LogicalNode:
    """
    快速构建 AND 逻辑表达式。

    示例：
        >>> build_and(
        ...     build_comparison("rsi", Operator.LT, 30),
        ...     build_comparison("macd", Operator.GT, 0),
        ... )

    Args:
        *conditions: 子条件节点（至少 2 个）。

    Returns:
        LogicalNode 实例。
    """
    return LogicalNode(LogicalOp.AND, list(conditions))


def build_or(*conditions: Node) -> LogicalNode:
    """
    快速构建 OR 逻辑表达式。

    Args:
        *conditions: 子条件节点（至少 2 个）。

    Returns:
        LogicalNode 实例。
    """
    return LogicalNode(LogicalOp.OR, list(conditions))


def build_not(condition: Node) -> LogicalNode:
    """
    快速构建 NOT 逻辑表达式。

    Args:
        condition: 子条件节点（必须 1 个）。

    Returns:
        LogicalNode 实例。
    """
    return LogicalNode(LogicalOp.NOT, [condition])


# ---------------------------------------------------------------------------
# 示例：从 JSON 反序列化 AST（可选扩展）
# ---------------------------------------------------------------------------

def parse_ast_from_dict(spec: dict) -> Node:
    """
    从字典结构解析 AST（用于从配置文件加载规则）。

    示例 JSON：
        {
            "type": "logical",
            "op": "AND",
            "operands": [
                {"type": "indicator", "name": "RSI", "params": {"period": 14}},
                {"type": "operator", "op": ">", "left": {"type": "var", "name": "macd"}, "right": {"type": "const", "value": 0}}
            ]
        }

    Args:
        spec: 字典结构（需符合上述格式）。

    Returns:
        Node 实例。

    Raises:
        ValueError: 若格式不合法。
    """
    node_type = spec.get("type")

    if node_type == "const":
        return ConstantNode(spec["value"])

    elif node_type == "var":
        return VariableNode(spec["name"])

    elif node_type == "indicator":
        return IndicatorNode(
            name=spec["name"],
            params=spec.get("params"),
            component=spec.get("component")
        )

    elif node_type == "operator":
        op = Operator(spec["op"])
        left = parse_ast_from_dict(spec["left"])
        right = parse_ast_from_dict(spec["right"])
        return OperatorNode(op, left, right)

    elif node_type == "logical":
        op = LogicalOp(spec["op"])
        operands = [parse_ast_from_dict(child) for child in spec["operands"]]
        return LogicalNode(op, operands)

    else:
        raise ValueError(f"Unknown node type: {node_type}")
