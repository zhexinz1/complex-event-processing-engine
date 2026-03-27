"""
example_nl_parser.py — 自然语言规则解析示例

展示如何使用新的指标元数据系统和自然语言解析功能。

功能演示：
  1. 参数化指标计算（RSI(14), MACD(12,26,9)）
  2. 多值指标组件提取（MACD.DIF, KDJ.K）
  3. 自然语言规则解析（"当 RSI 小于 30 时买入"）
  4. 指标校验和建议
"""

import logging
from datetime import datetime
from collections import deque

from events import BarEvent
from context import LocalContext, GlobalContext
from ast_engine import parse_ast_from_dict, IndicatorNode, OperatorNode, Operator, ConstantNode
from indicator_meta import find_indicator, get_all_indicators, suggest_similar_indicators

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 示例 1：参数化指标计算
# ---------------------------------------------------------------------------

def example_1_parameterized_indicators():
    """演示参数化指标的使用"""
    logger.info("=" * 60)
    logger.info("示例 1：参数化指标计算")
    logger.info("=" * 60)

    # 创建上下文
    global_ctx = GlobalContext()
    local_ctx = LocalContext("600519.SH", window_size=100, global_context=global_ctx)

    # 模拟添加 K 线数据
    for i in range(50):
        bar = BarEvent(
            symbol="600519.SH",
            timestamp=datetime.now(),
            open=100.0 + i * 0.5,
            high=102.0 + i * 0.5,
            low=99.0 + i * 0.5,
            close=101.0 + i * 0.5,
            volume=1000000
        )
        local_ctx.update_bar(bar)

    # 测试不同参数的 RSI
    rsi_14 = IndicatorNode("RSI", params={"period": 14})
    rsi_20 = IndicatorNode("RSI", params={"period": 20})

    result_14 = rsi_14.evaluate(local_ctx)
    result_20 = rsi_20.evaluate(local_ctx)

    logger.info(f"RSI(14) = {result_14:.2f}")
    logger.info(f"RSI(20) = {result_20:.2f}")

    # 测试 MACD 的不同组件
    macd_dif = IndicatorNode("MACD", component="DIF")
    macd_dea = IndicatorNode("MACD", component="DEA")
    macd_macd = IndicatorNode("MACD", component="MACD")

    dif = macd_dif.evaluate(local_ctx)
    dea = macd_dea.evaluate(local_ctx)
    macd = macd_macd.evaluate(local_ctx)

    logger.info(f"MACD: DIF={dif:.4f}, DEA={dea:.4f}, MACD={macd:.4f}")


# ---------------------------------------------------------------------------
# 示例 2：JSON 规则解析
# ---------------------------------------------------------------------------

def example_2_json_rule_parsing():
    """演示从 JSON 解析规则"""
    logger.info("\n" + "=" * 60)
    logger.info("示例 2：JSON 规则解析")
    logger.info("=" * 60)

    # 创建上下文
    global_ctx = GlobalContext()
    local_ctx = LocalContext("600519.SH", window_size=100, global_context=global_ctx)

    # 模拟添加 K 线数据
    for i in range(50):
        bar = BarEvent(
            symbol="600519.SH",
            timestamp=datetime.now(),
            open=100.0 - i * 0.1,  # 下跌趋势
            high=102.0 - i * 0.1,
            low=99.0 - i * 0.1,
            close=101.0 - i * 0.1,
            volume=1000000
        )
        local_ctx.update_bar(bar)

    # 规则：RSI < 30 AND MACD 金叉
    rule_json = {
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

    # 解析并求值
    rule_ast = parse_ast_from_dict(rule_json)
    result = rule_ast.evaluate(local_ctx)

    logger.info(f"规则: RSI < 30 AND MACD金叉")
    logger.info(f"求值结果: {result}")


# ---------------------------------------------------------------------------
# 示例 3：指标查找和建议
# ---------------------------------------------------------------------------

def example_3_indicator_lookup():
    """演示指标查找和建议功能"""
    logger.info("\n" + "=" * 60)
    logger.info("示例 3：指标查找和建议")
    logger.info("=" * 60)

    # 列出所有已注册的指标
    all_indicators = get_all_indicators()
    logger.info(f"已注册指标数量: {len(all_indicators)}")
    for meta in all_indicators:
        logger.info(f"  - {meta.name}: {meta.description}")
        logger.info(f"    别名: {', '.join(meta.aliases)}")
        logger.info(f"    默认参数: {meta.default_params}")

    # 测试别名查找
    logger.info("\n测试别名查找:")
    test_names = ["RSI", "rsi", "相对强弱指标", "MACD", "kdj", "布林带"]
    for name in test_names:
        meta = find_indicator(name)
        if meta:
            logger.info(f"  '{name}' -> {meta.name}")
        else:
            logger.info(f"  '{name}' -> 未找到")

    # 测试相似指标建议
    logger.info("\n测试相似指标建议:")
    unknown_names = ["RSii", "macd", "随机", "均线"]
    for name in unknown_names:
        suggestions = suggest_similar_indicators(name)
        logger.info(f"  '{name}' -> 建议: {suggestions}")


# ---------------------------------------------------------------------------
# 示例 4：自然语言解析（需要 API Key）
# ---------------------------------------------------------------------------

def example_4_natural_language_parsing():
    """演示自然语言规则解析（需要 Anthropic API Key）"""
    logger.info("\n" + "=" * 60)
    logger.info("示例 4：自然语言规则解析")
    logger.info("=" * 60)

    import os
    from nl_parser import parse_natural_language, validate_and_suggest, ANTHROPIC_AVAILABLE

    if not ANTHROPIC_AVAILABLE:
        logger.warning("Anthropic SDK 未安装，跳过自然语言解析示例")
        logger.info("安装方法: pip install anthropic")
        return

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        logger.warning("未设置 ANTHROPIC_API_KEY 环境变量，跳过自然语言解析示例")
        logger.info("设置方法: export ANTHROPIC_API_KEY='your-api-key'")
        return

    # 测试用例
    test_rules = [
        "当 RSI 小于 30 时买入",
        "当 RSI 小于 30 且 MACD 金叉时买入",
        "当 KDJ 的 K 值大于 D 值且 J 值小于 20 时买入",
        "当价格突破布林带上轨时卖出"
    ]

    for rule_text in test_rules:
        logger.info(f"\n自然语言规则: {rule_text}")
        try:
            # 解析并验证
            result = validate_and_suggest(rule_text, api_key)

            logger.info(f"解析成功: {result['valid']}")
            if result['valid']:
                logger.info(f"AST: {result['ast']}")
            else:
                logger.warning(f"未知指标: {result['unknown_indicators']}")
                logger.info(f"建议: {result['suggestions']}")

        except Exception as e:
            logger.error(f"解析失败: {e}")


# ---------------------------------------------------------------------------
# 主函数
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    example_1_parameterized_indicators()
    example_2_json_rule_parsing()
    example_3_indicator_lookup()
    example_4_natural_language_parsing()

    logger.info("\n" + "=" * 60)
    logger.info("所有示例运行完成！")
    logger.info("=" * 60)
