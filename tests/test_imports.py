"""
测试所有模块的导入是否正常工作
"""

def test_core_imports():
    """测试核心模块导入"""
    from cep.core import EventBus, TickEvent, BarEvent, GlobalContext, LocalContext
    print("✓ 核心模块导入成功")


def test_engine_imports():
    """测试引擎模块导入"""
    from cep.engine import Node, Operator, LogicalOp
    print("✓ 引擎模块导入成功")


def test_triggers_imports():
    """测试触发器模块导入"""
    from cep.triggers import AstRuleTrigger, DeviationTrigger, CronTrigger
    print("✓ 触发器模块导入成功")


def test_rebalance_imports():
    """测试再平衡模块导入"""
    from rebalance import (
        RebalanceEngine,
        PortfolioContext,
        RebalanceHandler,
        FundFlowTrigger,
        MonthlyRebalanceTrigger,
        PortfolioDeviationTrigger,
    )
    print("✓ 再平衡模块导入成功")


def test_nlp_imports():
    """测试 NLP 模块导入"""
    from nlp import parse_natural_language, validate_and_suggest, IndicatorMeta
    print("✓ NLP 模块导入成功")


if __name__ == "__main__":
    test_core_imports()
    test_engine_imports()
    test_triggers_imports()
    test_rebalance_imports()
    test_nlp_imports()
    print("\n✅ 所有模块导入测试通过！")
