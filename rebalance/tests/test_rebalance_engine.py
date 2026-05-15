"""
test_rebalance_engine.py — 待调余量累积逻辑测试

覆盖场景：
  1. 基础正常下单（无历史余量）
  2. 向上舍入后产生负余量，下一次被抵消
  3. 向下舍入后产生正余量，下一次被累加触发下单
  4. 连续三次场景（0.75 → 0.70 → 0.40）
  5. 余量归零场景（0.5 + 0.5 = 1.0 精准下单）
  6. 价格为 0 时产生 placeholder 订单
  7. 多资产独立累积互不干扰
  8. 纯出金（无历史余量）正常减仓
  9. 出金 + 欠买余量：余量抵减卖出数量
  10. 出金量小于欠买余量：理论为正（不卖反买）
  11. 跨天场景：入金产生欠买 → 第二天出金自动抵消
"""

from decimal import Decimal

import pytest

from rebalance.rebalance_engine import RebalanceEngine


def make_engine() -> RebalanceEngine:
    return RebalanceEngine(portfolio_ctx=None)


def run_round(
    engine: RebalanceEngine,
    net_inflow: float,
    weights: dict[str, float],
    prices: dict[str, float],
    multipliers: dict[str, int],
    prev_fracs: dict[str, float],
) -> list:
    """辅助函数：运行一次增量计算。"""
    return engine.calculate_incremental_orders(
        net_inflow=Decimal(str(net_inflow)),
        leverage_ratio=Decimal("1"),  # 权重已含杠杆
        target_weights={k: Decimal(str(v)) for k, v in weights.items()},
        market_prices={k: Decimal(str(v)) for k, v in prices.items()},
        contract_multipliers=multipliers,
        previous_fractionals={k: Decimal(str(v)) for k, v in prev_fracs.items()},
    )


# ---------------------------------------------------------------------------
# 测试 1：基础场景 — 无历史余量，精准整数下单
# ---------------------------------------------------------------------------
def test_basic_exact_order():
    """目标市值恰好能整除，理论手数为整数，无余量。"""
    engine = make_engine()
    # 净入金 10000，权重 100%，价格 100，乘数 10
    # 理论手数 = 10000 / (100 * 10) = 10.0 → 下单10手，余量=0
    orders = run_round(engine, 10000, {"AU2609": 1.0}, {"AU2609": 100.0}, {"AU2609": 10}, {"AU2609": 0.0})
    assert len(orders) == 1
    o = orders[0]
    assert o.rounded_quantity == 10
    assert float(o.fractional_part) == pytest.approx(0.0)
    assert o.final_quantity == 10


# ---------------------------------------------------------------------------
# 测试 2：向上舍入产生负余量，第二轮被抵消
# ---------------------------------------------------------------------------
def test_round_up_creates_negative_fractional_which_offsets_next_round():
    """
    第一次：理论 0.75 → 下单 1，余量 -0.25
    第二次：0.7 + (-0.25) = 0.45 → 下单 0，余量 +0.45
    """
    engine = make_engine()
    # 假设 price=1, multiplier=1，方便直接看手数
    # 第一次：net_inflow = 0.75, weight = 1.0
    orders1 = run_round(engine, 0.75, {"X": 1.0}, {"X": 1.0}, {"X": 1}, {"X": 0.0})
    o1 = orders1[0]
    assert o1.rounded_quantity == 1
    assert float(o1.fractional_part) == pytest.approx(-0.25, abs=1e-6)

    # 第二次：使用第一次的余量
    orders2 = run_round(engine, 0.70, {"X": 1.0}, {"X": 1.0}, {"X": 1}, {"X": float(o1.fractional_part)})
    o2 = orders2[0]
    # 合计理论 = 0.70 + (-0.25) = 0.45 → round → 0
    assert o2.rounded_quantity == 0
    assert float(o2.fractional_part) == pytest.approx(0.45, abs=1e-6)


# ---------------------------------------------------------------------------
# 测试 3：向下舍入产生正余量，第二轮触发额外下单
# ---------------------------------------------------------------------------
def test_round_down_creates_positive_fractional_triggers_extra_buy():
    """
    第一次：理论 0.3 → 下单 0，余量 +0.3
    第二次：0.3 + 0.3 = 0.6 → 下单 1，余量 -0.4
    """
    engine = make_engine()
    orders1 = run_round(engine, 0.3, {"X": 1.0}, {"X": 1.0}, {"X": 1}, {"X": 0.0})
    o1 = orders1[0]
    assert o1.rounded_quantity == 0
    assert float(o1.fractional_part) == pytest.approx(0.3, abs=1e-6)

    orders2 = run_round(engine, 0.3, {"X": 1.0}, {"X": 1.0}, {"X": 1}, {"X": float(o1.fractional_part)})
    o2 = orders2[0]
    # 合计理论 = 0.3 + 0.3 = 0.6 → round → 1
    assert o2.rounded_quantity == 1
    assert float(o2.fractional_part) == pytest.approx(-0.4, abs=1e-6)


# ---------------------------------------------------------------------------
# 测试 4：连续三轮场景（用户问题中的例子：0.75 → 0.70 → 0.40）
# ---------------------------------------------------------------------------
def test_three_round_scenario_075_070_040():
    """
    第1次：0.75 → 下单1，余量-0.25
    第2次：0.70 + (-0.25) = 0.45 → 下单0，余量+0.45
    第3次：0.40 + 0.45 = 0.85 → 下单1，余量-0.15

    累计理论 = 0.75 + 0.70 + 0.40 = 1.85
    累计实际 = 1 + 0 + 1 = 2
    最终余量 = -0.15，即 2 + (-0.15) = 1.85 ✓
    """
    engine = make_engine()

    orders1 = run_round(engine, 0.75, {"X": 1.0}, {"X": 1.0}, {"X": 1}, {"X": 0.0})
    o1 = orders1[0]
    assert o1.rounded_quantity == 1
    frac1 = float(o1.fractional_part)
    assert frac1 == pytest.approx(-0.25, abs=1e-6)

    orders2 = run_round(engine, 0.70, {"X": 1.0}, {"X": 1.0}, {"X": 1}, {"X": frac1})
    o2 = orders2[0]
    assert o2.rounded_quantity == 0
    frac2 = float(o2.fractional_part)
    assert frac2 == pytest.approx(0.45, abs=1e-6)

    orders3 = run_round(engine, 0.40, {"X": 1.0}, {"X": 1.0}, {"X": 1}, {"X": frac2})
    o3 = orders3[0]
    assert o3.rounded_quantity == 1
    frac3 = float(o3.fractional_part)
    assert frac3 == pytest.approx(-0.15, abs=1e-6)

    # 守恒性验证：累计实际 + 最终余量 = 累计理论
    total_ordered = o1.rounded_quantity + o2.rounded_quantity + o3.rounded_quantity
    total_theory = 0.75 + 0.70 + 0.40
    assert total_ordered + frac3 == pytest.approx(total_theory, abs=1e-6)


# ---------------------------------------------------------------------------
# 测试 5：两次 0.5，余量正好消除，精准下单1
# ---------------------------------------------------------------------------
def test_half_lot_two_rounds():
    """
    第1次：0.5 → 下单0（Python banker's rounding: round(0.5)=0），余量+0.5
    第2次：0.5 + 0.5 = 1.0 → 下单1，余量0

    注：Python round(0.5) = 0（银行家舍入），round(1.5) = 2
    """
    engine = make_engine()

    orders1 = run_round(engine, 0.5, {"X": 1.0}, {"X": 1.0}, {"X": 1}, {"X": 0.0})
    o1 = orders1[0]
    # Python banker's rounding: round(0.5) = 0
    assert o1.rounded_quantity == 0
    assert float(o1.fractional_part) == pytest.approx(0.5, abs=1e-6)

    orders2 = run_round(engine, 0.5, {"X": 1.0}, {"X": 1.0}, {"X": 1}, {"X": float(o1.fractional_part)})
    o2 = orders2[0]
    # 1.0 → 下单1，余量归零
    assert o2.rounded_quantity == 1
    assert float(o2.fractional_part) == pytest.approx(0.0, abs=1e-6)


# ---------------------------------------------------------------------------
# 测试 6：价格为 0 时产生 placeholder 订单
# ---------------------------------------------------------------------------
def test_zero_price_produces_placeholder():
    """价格为0时，所有手数以0填充，余量也为0（等待行情刷新）。"""
    engine = make_engine()
    orders = run_round(engine, 10000, {"X": 1.0}, {"X": 0.0}, {"X": 1}, {"X": 0.5})
    assert len(orders) == 1
    o = orders[0]
    assert o.rounded_quantity == 0
    assert o.final_quantity == 0
    assert float(o.fractional_part) == 0.0
    # placeholder 时不消耗之前的余量，previous_fractional 保持不变
    assert float(o.previous_fractional) == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# 测试 7：多资产独立余量互不干扰
# ---------------------------------------------------------------------------
def test_multiple_assets_independent_fractionals():
    """
    两个资产 A 和 B，各自有不同的余量和权重，互不影响。
    A: 理论 0.75 + 0.3(余量) = 1.05 → 下单1，余量+0.05
    B: 理论 0.4  + 0.0(余量) = 0.40 → 下单0，余量+0.40
    """
    engine = make_engine()
    # net_inflow = 1, 权重 A=0.75, B=0.4（权重总和不必为1，已含杠杆）
    orders = run_round(
        engine,
        net_inflow=1.0,
        weights={"A": 0.75, "B": 0.4},
        prices={"A": 1.0, "B": 1.0},
        multipliers={"A": 1, "B": 1},
        prev_fracs={"A": 0.3, "B": 0.0},
    )
    by_code = {o.asset_code: o for o in orders}
    assert "A" in by_code and "B" in by_code

    oa = by_code["A"]
    # A: 0.75 + 0.3 = 1.05 → round(1.05) = 1, frac = 0.05
    assert oa.rounded_quantity == 1
    assert float(oa.fractional_part) == pytest.approx(0.05, abs=1e-6)

    ob = by_code["B"]
    # B: 0.4 + 0.0 = 0.4 → round(0.4) = 0, frac = 0.4
    assert ob.rounded_quantity == 0
    assert float(ob.fractional_part) == pytest.approx(0.4, abs=1e-6)


# ---------------------------------------------------------------------------
# 测试 8：纯出金（无历史余量）正常减仓
# ---------------------------------------------------------------------------
def test_outflow_basic_sell():
    """
    出金 = -1.5 手理论，上次余量 = 0
    理论 = -1.5 → round(-1.5) = -2（银行家舍入），frac = -1.5 - (-2) = +0.5
    """
    engine = make_engine()
    orders = run_round(engine, -1.5, {"X": 1.0}, {"X": 1.0}, {"X": 1}, {"X": 0.0})
    o = orders[0]
    assert o.rounded_quantity == -2
    assert o.final_quantity == -2
    assert float(o.fractional_part) == pytest.approx(0.5, abs=1e-6)


# ---------------------------------------------------------------------------
# 测试 9：出金 + 欠买余量：余量抵减卖出数量
# ---------------------------------------------------------------------------
def test_outflow_with_under_bought_residual_reduces_sell():
    """
    出金 = -1.6 手，欠买余量 = +0.4
    理论 = -1.6 + 0.4 = -1.2 → round(-1.2) = -1，frac = -1.2 - (-1) = -0.2
    出金体量 = 1 手（欠买抵消了 0.4 的卖出）
    """
    engine = make_engine()
    orders = run_round(engine, -1.6, {"X": 1.0}, {"X": 1.0}, {"X": 1}, {"X": 0.4})
    o = orders[0]
    assert o.rounded_quantity == -1
    assert float(o.fractional_part) == pytest.approx(-0.2, abs=1e-6)


# ---------------------------------------------------------------------------
# 测试 10：出金量小于欠买余量：理论为正（单仳不卖反买）
# ---------------------------------------------------------------------------
def test_outflow_smaller_than_residual_no_sell():
    """
    出金 = -0.1 手，欠买余量 = +0.4
    理论 = -0.1 + 0.4 = +0.3 → round(0.3) = 0
    理论为正但被舍入为0，不产生买单也不卖出。余量 = +0.3
    """
    engine = make_engine()
    orders = run_round(engine, -0.1, {"X": 1.0}, {"X": 1.0}, {"X": 1}, {"X": 0.4})
    o = orders[0]
    # 不应下单（不卖出也不补买）
    assert o.rounded_quantity == 0
    assert float(o.fractional_part) == pytest.approx(0.3, abs=1e-6)


# ---------------------------------------------------------------------------
# 测试 11：跨天场景——入金产生欠买，第二天出金自动抗消
# ---------------------------------------------------------------------------
def test_cross_day_inflow_then_outflow():
    """
    天 1 入金：理论 0.4 → round(0.4)=0，余量 = +0.4
    天 2 出金：理论 = -1.0 + 0.4 = -0.6 → round(-0.6)=-1，余量 = -0.6-(-1) = +0.4
    天 2 卖出 1 手而非 1.4 手，因为欠买抵消了 0.4 的卖出
    欢应守恒性：累计出金量 1 + 余量 0.4 = 理论 1.4 ✓
    """
    engine = make_engine()

    # 天 1：小入金产生欠买
    orders1 = run_round(engine, 0.4, {"X": 1.0}, {"X": 1.0}, {"X": 1}, {"X": 0.0})
    o1 = orders1[0]
    assert o1.rounded_quantity == 0
    frac1 = float(o1.fractional_part)
    assert frac1 == pytest.approx(0.4, abs=1e-6)

    # 天 2：出金，欠买余量抵消部分卖出
    orders2 = run_round(engine, -1.0, {"X": 1.0}, {"X": 1.0}, {"X": 1}, {"X": frac1})
    o2 = orders2[0]
    # 理论 = -1.0 + 0.4 = -0.6 → round = -1
    assert o2.rounded_quantity == -1
    frac2 = float(o2.fractional_part)
    assert frac2 == pytest.approx(0.4, abs=1e-6)

    # 守恒性：天1理论(0.4) + 天2理论(-0.6) = -0.2，天2下单-1 + 余量0.4 = -0.6≡-0.6→OK
    assert (o2.rounded_quantity + frac2) == pytest.approx(-1.0 + 0.4, abs=1e-6)
