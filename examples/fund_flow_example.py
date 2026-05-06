"""
fund_flow_example.py — 资金流动管理完整示例

演示运营人员输入出入金 → 从迅投获取估值 → 计算净入金 → 触发再平衡的完整流程。

业务场景：
  1. 运营人员在前端输入：明钺全天候1号，今日入金 130 万
  2. 系统从迅投 API 获取产品估值
  3. 系统计算净入金 = 当前净值 - 昨日净值 - 今日盈亏
  4. 触发再平衡，按数据库配置的最新比例下单

运行：
  cd /home/ubuntu/CEP
  python -m examples.fund_flow_example
"""

import logging
from datetime import date, timedelta

from cep.core.event_bus import EventBus
from rebalance import (
    PortfolioContext,
    ContractInfo,
    Position,
    RebalanceHandler,
    FundFlowTrigger,
    FundFlowManager,
    FundFlowRecord,
    ProductValuation,
    InMemoryConfigLoader,
    ProductConfig,
    TargetWeightConfig,
    MockPositionSource,
)

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("fund_flow_example")


# ---------------------------------------------------------------------------
# 模拟数据源（生产环境替换为真实数据源）
# ---------------------------------------------------------------------------


class MockFundFlowSource:
    """模拟出入金数据源"""

    def __init__(self):
        self.records = []

    def save_fund_flow_record(self, record: FundFlowRecord) -> bool:
        self.records.append(record)
        return True

    def get_fund_flow_records(
        self, product_name: str, start_date: date, end_date: date
    ):
        return [
            r
            for r in self.records
            if r.product_name == product_name and start_date <= r.date <= end_date
        ]


class MockValuationSource:
    """模拟估值数据源（生产环境替换为 XunTouValuationSource）"""

    def __init__(self):
        self.valuations = {}

    def fetch_valuation(self, product_name: str, valuation_date: date):
        key = (product_name, valuation_date)
        return self.valuations.get(key)

    def save_valuation(self, valuation: ProductValuation) -> bool:
        key = (valuation.product_name, valuation.date)
        self.valuations[key] = valuation
        return True

    def get_valuation_history(
        self, product_name: str, start_date: date, end_date: date
    ):
        return [
            v
            for (pn, d), v in self.valuations.items()
            if pn == product_name and start_date <= d <= end_date
        ]


def main():
    logger.info("=" * 80)
    logger.info("资金流动管理完整示例")
    logger.info("=" * 80)

    # -----------------------------------------------------------------------
    # 1. 创建事件总线和组合上下文
    # -----------------------------------------------------------------------
    bus = EventBus()

    # 创建持仓数据源（模拟迅投 GT API）
    position_source = MockPositionSource()
    position_source.set_position(
        Position(
            symbol="AU2606.SHF",
            quantity=40,
            avg_price=580.0,
            market_value=40 * 580.0 * 1000,
        )
    )
    position_source.set_position(
        Position(
            symbol="IC2606.CFE",
            quantity=15,
            avg_price=6500.0,
            market_value=15 * 6500.0 * 200,
        )
    )
    position_source.set_account_info(
        total_nav=10_000_000.0, available_cash=5_000_000.0, margin_used=2_000_000.0
    )

    portfolio_ctx = PortfolioContext(position_source=position_source)

    # 加载目标权重配置
    config_loader = InMemoryConfigLoader()
    config = ProductConfig(
        product_name="明钺全天候1号",
        date=date.today(),
        assets=[
            TargetWeightConfig(
                date=date.today(),
                product_name="明钺全天候1号",
                symbol="AU2606.SHF",
                target_weight=0.30,
                deviation_threshold=0.03,
                algorithm="TWAP",
            ),
            TargetWeightConfig(
                date=date.today(),
                product_name="明钺全天候1号",
                symbol="IC2606.CFE",
                target_weight=0.20,
                deviation_threshold=0.05,
                algorithm="TWAP",
            ),
        ],
        global_threshold=0.05,
    )
    config_loader.save_product_config(config)

    portfolio_ctx.set_target_weights(config.get_target_weights())

    # 注册合约信息
    contracts = {
        "AU2606.SHF": ContractInfo("AU2606.SHF", multiplier=1000, margin_rate=0.08),
        "IC2606.CFE": ContractInfo("IC2606.CFE", multiplier=200, margin_rate=0.12),
    }
    for contract in contracts.values():
        portfolio_ctx.register_contract(contract)

    # 同步持仓
    portfolio_ctx.sync_positions_from_source()

    # -----------------------------------------------------------------------
    # 2. 创建资金流动管理器
    # -----------------------------------------------------------------------
    fund_flow_source = MockFundFlowSource()
    valuation_source = MockValuationSource()

    # 模拟昨日估值（生产环境从迅投 API 获取）
    yesterday = date.today() - timedelta(days=1)
    yesterday_valuation = ProductValuation(
        date=yesterday,
        product_name="明钺全天候1号",
        nav=10_000_000.0,
        total_assets=10_500_000.0,
        total_liabilities=500_000.0,
        unit_nav=1.0,
        pnl=0.0,
        source="xuntou_api",
    )
    valuation_source.save_valuation(yesterday_valuation)

    # 模拟今日估值（生产环境从迅投 API 获取）
    today = date.today()
    today_valuation = ProductValuation(
        date=today,
        product_name="明钺全天候1号",
        nav=11_350_000.0,  # 当前净值
        total_assets=11_900_000.0,
        total_liabilities=550_000.0,
        unit_nav=1.135,
        pnl=50_000.0,  # 今日盈亏 5 万
        source="xuntou_api",
    )
    valuation_source.save_valuation(today_valuation)

    fund_flow_manager = FundFlowManager(fund_flow_source, valuation_source)

    # -----------------------------------------------------------------------
    # 3. 创建再平衡处理器和触发器
    # -----------------------------------------------------------------------
    rebalance_handler = RebalanceHandler(bus, portfolio_ctx)
    rebalance_handler.register()

    fund_flow_trigger = FundFlowTrigger(event_bus=bus, trigger_id="fund_flow")
    fund_flow_trigger.register()

    # -----------------------------------------------------------------------
    # 4. 场景模拟：运营人员输入出入金
    # -----------------------------------------------------------------------
    logger.info("\n" + "=" * 80)
    logger.info("场景 1: 运营人员输入出入金记录")
    logger.info("=" * 80)

    # 运营人员通过前端输入：今日入金 130 万
    success = fund_flow_manager.record_fund_flow(
        product_name="明钺全天候1号",
        flow_date=today,
        inflow=1_300_000.0,  # 入金 130 万
        outflow=0.0,
        operator="张三",
        remark="客户追加投资",
    )

    if success:
        logger.info("✅ 出入金记录已保存")
    else:
        logger.error("❌ 出入金记录保存失败")

    # -----------------------------------------------------------------------
    # 5. 计算净入金
    # -----------------------------------------------------------------------
    logger.info("\n" + "=" * 80)
    logger.info("场景 2: 从迅投 API 获取估值，计算净入金")
    logger.info("=" * 80)

    net_capital_change = fund_flow_manager.calculate_net_capital_change(
        product_name="明钺全天候1号", calculation_date=today
    )

    if not net_capital_change:
        logger.error("❌ 净入金计算失败")
        return

    logger.info("\n净入金计算结果:")
    logger.info(f"  昨日净值:   {net_capital_change.previous_nav:>12,.2f}")
    logger.info(f"  今日净值:   {net_capital_change.current_nav:>12,.2f}")
    logger.info(f"  今日盈亏:   {net_capital_change.pnl:>12,.2f}")
    logger.info(f"  入金金额:   {net_capital_change.fund_inflow:>12,.2f}")
    logger.info(f"  出金金额:   {net_capital_change.fund_outflow:>12,.2f}")
    logger.info(f"  净入金:     {net_capital_change.net_capital_change:>12,.2f}")
    logger.info(f"  计算方法:   {net_capital_change.calculation_method}")

    # 验证计算
    expected_net_capital = (
        net_capital_change.current_nav
        - net_capital_change.previous_nav
        - net_capital_change.pnl
    )
    logger.info(
        f"\n验证: {net_capital_change.current_nav:,.2f} - "
        f"{net_capital_change.previous_nav:,.2f} - "
        f"{net_capital_change.pnl:,.2f} = "
        f"{expected_net_capital:,.2f}"
    )

    # -----------------------------------------------------------------------
    # 6. 触发再平衡
    # -----------------------------------------------------------------------
    logger.info("\n" + "=" * 80)
    logger.info("场景 3: 触发再平衡，按最新配置比例下单")
    logger.info("=" * 80)

    # 更新持仓价格（模拟实时行情）
    portfolio_ctx.update_price("AU2606.SHF", 585.0)
    portfolio_ctx.update_price("IC2606.CFE", 6520.0)

    # 触发再平衡
    fund_flow_trigger.fire(
        product_name="明钺全天候1号",
        net_capital_change=net_capital_change.net_capital_change,
        previous_nav=net_capital_change.previous_nav,
        current_nav=net_capital_change.current_nav,
        pnl=net_capital_change.pnl,
        operator="张三",
        remark="客户追加投资 130 万",
    )

    # -----------------------------------------------------------------------
    # 7. 总结
    # -----------------------------------------------------------------------
    logger.info("\n" + "=" * 80)
    logger.info("示例完成")
    logger.info("=" * 80)

    logger.info("\n生产环境集成步骤:")
    logger.info("1. 前端提供出入金录入界面")
    logger.info("   POST /api/fund-flow/record")
    logger.info("   {product_name, date, inflow, outflow, operator, remark}")
    logger.info("")
    logger.info("2. 后端调用 FundFlowManager.record_fund_flow()")
    logger.info("   保存到数据库 fund_flow_records 表")
    logger.info("")
    logger.info("3. 后端调用 XunTouValuationSource.fetch_valuation()")
    logger.info("   从迅投 GT API 获取产品估值")
    logger.info("")
    logger.info("4. 后端调用 FundFlowManager.calculate_net_capital_change()")
    logger.info("   计算净入金 = 当前净值 - 昨日净值 - 今日盈亏")
    logger.info("")
    logger.info("5. 后端调用 FundFlowTrigger.fire()")
    logger.info("   触发再平衡，按数据库配置的最新比例下单")
    logger.info("")
    logger.info("6. RebalanceHandler 接收信号，调用迅投 API 下单")


if __name__ == "__main__":
    main()
