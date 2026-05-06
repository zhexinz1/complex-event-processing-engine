"""
rebalance_engine.py — 再平衡核心计算引擎

实现从目标权重到具体订单的完整计算链路（5 步计算）：
  步骤1: 计算新目标总资产 (当前净值 + 待入账新增资金)
  步骤2: 计算单品种目标市值 (新目标总资产 * 目标权重)
  步骤3: 计算市值差额 (品种目标市值 - 当前真实市值)
  步骤4: 理论增减换算 (市值差额 / 最新价 / 合约乘数)
  步骤5: 离散化与舍入处理 (将理论值转化为计划整数)

设计原则：
  1. 纯计算逻辑：不依赖外部系统，所有数据通过参数传入
  2. 可测试性：每一步计算都可独立测试
  3. 可审计性：返回完整的计算中间结果
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any
from decimal import Decimal

from rebalance.portfolio_context import PortfolioContext

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 数据类定义
# ---------------------------------------------------------------------------


@dataclass
class RebalanceOrder:
    """
    再平衡订单。

    Attributes:
        symbol:           合约代码
        side:             方向（"BUY" / "SELL"）
        quantity:         数量（整数）
        estimated_price:  预估价格（用于资金校验）
        reason:           调仓原因（用于审计）
    """

    symbol: str
    side: str  # "BUY" or "SELL"
    quantity: int
    estimated_price: float
    reason: str = ""


@dataclass
class RebalanceResult:
    """
    再平衡计算结果。

    Attributes:
        orders:              订单列表
        total_margin_needed: 所需总保证金
        calculation_details: 计算中间结果（用于审计）
    """

    orders: list[RebalanceOrder]
    total_margin_needed: float
    calculation_details: dict[str, Any]


@dataclass
class IncrementalOrder:
    """
    增量买入订单（净入金场景）。

    Attributes:
        asset_code:           合约代码
        target_market_value:  目标市值（元）
        price:                计算时使用的价格（卖1价）
        contract_multiplier:  合约乘数
        theoretical_quantity: 理论手数（未取整）
        rounded_quantity:     四舍五入后的手数
        fractional_part:      留白部分（小数）
        previous_fractional:  上次留白累积
        final_quantity:       最终手数（rounded_quantity，可手动调整）
    """

    asset_code: str
    target_market_value: Decimal
    price: Decimal
    contract_multiplier: int
    theoretical_quantity: Decimal
    rounded_quantity: int
    fractional_part: Decimal
    previous_fractional: Decimal
    final_quantity: int


# ---------------------------------------------------------------------------
# 再平衡引擎
# ---------------------------------------------------------------------------


class RebalanceEngine:
    """
    再平衡核心计算引擎。

    核心方法：
      - calculate(): 执行完整的 5 步计算链路
    """

    def __init__(self, portfolio_ctx: PortfolioContext | None = None) -> None:
        """
        初始化再平衡引擎。

        Args:
            portfolio_ctx: 组合上下文（增量买入场景可以为 None）
        """
        self.portfolio_ctx = portfolio_ctx
        logger.info("RebalanceEngine initialized.")

    def calculate(
        self, new_capital: float = 0.0, reason: str = "rebalance"
    ) -> RebalanceResult:
        """
        执行再平衡计算（5 步链路）。

        Args:
            new_capital: 新增资金（如申购 130 万）
            reason:      调仓原因（用于审计）

        Returns:
            RebalanceResult: 计算结果（包含订单列表和中间结果）
        """
        logger.info(
            f"Starting rebalance calculation: new_capital={new_capital:,.2f}, reason={reason}"
        )

        # 步骤 1: 计算新目标总资产
        if self.portfolio_ctx is None:
            raise ValueError("portfolio_ctx is required for full rebalance calculation")

        current_nav = self.portfolio_ctx.get_total_nav()
        new_target_nav = current_nav + new_capital
        logger.info(
            f"Step 1: Current NAV={current_nav:,.2f}, New Capital={new_capital:,.2f}, "
            f"New Target NAV={new_target_nav:,.2f}"
        )

        # 步骤 2-5: 为每个品种计算调仓量
        orders = []
        calculation_details = {
            "current_nav": current_nav,
            "new_capital": new_capital,
            "new_target_nav": new_target_nav,
            "symbols": {},
        }

        target_weights = self.portfolio_ctx.get_all_target_weights()

        for symbol, target_weight in target_weights.items():
            # 获取必要数据
            contract_info = self.portfolio_ctx.get_contract_info(symbol)
            if not contract_info:
                logger.warning(f"Contract info not found for {symbol}, skipping.")
                continue

            latest_price = self.portfolio_ctx.get_latest_price(symbol)
            if not latest_price or latest_price <= 0:
                logger.warning(f"Invalid price for {symbol}, skipping.")
                continue

            position = self.portfolio_ctx.get_position(symbol)
            current_quantity = position.quantity if position else 0.0
            current_market_value = position.market_value if position else 0.0

            # 步骤 2: 计算目标市值
            target_market_value = new_target_nav * target_weight

            # 步骤 3: 计算市值差额
            market_value_diff = target_market_value - current_market_value

            # 步骤 4: 理论增减换算
            theoretical_quantity_change = market_value_diff / (
                latest_price * contract_info.multiplier
            )

            # 步骤 5: 离散化舍入
            quantity_change = self._round_quantity(theoretical_quantity_change)

            # 记录计算详情
            calculation_details["symbols"][symbol] = {
                "target_weight": target_weight,
                "target_market_value": target_market_value,
                "current_market_value": current_market_value,
                "market_value_diff": market_value_diff,
                "theoretical_quantity_change": theoretical_quantity_change,
                "quantity_change": quantity_change,
                "current_quantity": current_quantity,
                "latest_price": latest_price,
                "multiplier": contract_info.multiplier,
            }

            # 生成订单
            if quantity_change != 0:
                order = RebalanceOrder(
                    symbol=symbol,
                    side="BUY" if quantity_change > 0 else "SELL",
                    quantity=abs(quantity_change),
                    estimated_price=latest_price,
                    reason=reason,
                )
                orders.append(order)
                logger.info(
                    f"Order generated: {symbol} {order.side} {order.quantity} @ {latest_price:.2f} "
                    f"(理论: {theoretical_quantity_change:.2f})"
                )

        # 计算所需保证金
        total_margin_needed = self._calculate_margin_needed(orders)

        logger.info(
            f"Rebalance calculation completed: {len(orders)} orders, "
            f"margin_needed={total_margin_needed:,.2f}"
        )

        return RebalanceResult(
            orders=orders,
            total_margin_needed=total_margin_needed,
            calculation_details=calculation_details,
        )

    def _round_quantity(self, theoretical_quantity: float) -> int:
        """
        离散化舍入：将理论数量转化为整数。

        策略：
          - 四舍五入到最接近的整数
          - 可扩展为更复杂的舍入策略（如向下舍入、最小交易单位等）

        Args:
            theoretical_quantity: 理论数量（可能是小数）

        Returns:
            整数数量
        """
        return round(theoretical_quantity)

    def _calculate_margin_needed(self, orders: list[RebalanceOrder]) -> float:
        """
        计算执行订单所需的保证金。

        Args:
            orders: 订单列表

        Returns:
            所需总保证金
        """
        total_margin = 0.0
        if self.portfolio_ctx is None:
            raise ValueError("portfolio_ctx is required to calculate margin")

        for order in orders:
            contract_info = self.portfolio_ctx.get_contract_info(order.symbol)
            if not contract_info:
                continue

            # 保证金 = 数量 * 价格 * 合约乘数 * 保证金率
            margin = (
                order.quantity
                * order.estimated_price
                * contract_info.multiplier
                * contract_info.margin_rate
            )
            total_margin += margin

        return total_margin

    def validate_orders(self, result: RebalanceResult) -> tuple[bool, str]:
        """
        校验订单是否满足资金约束。

        Args:
            result: 再平衡计算结果

        Returns:
            (是否通过, 错误信息)
        """
        if self.portfolio_ctx is None:
            return False, "portfolio_ctx is required to validate orders"

        available_cash = self.portfolio_ctx.get_available_cash()

        if result.total_margin_needed > available_cash:
            error_msg = (
                f"资金不足: 所需保证金 {result.total_margin_needed:,.2f} > "
                f"可用资金 {available_cash:,.2f}"
            )
            logger.error(error_msg)
            return False, error_msg

        logger.info(
            f"订单校验通过: 所需保证金 {result.total_margin_needed:,.2f}, "
            f"可用资金 {available_cash:,.2f}"
        )
        return True, ""

    # ---------------------------------------------------------------------------
    # 增量买入逻辑（净入金场景）
    # ---------------------------------------------------------------------------

    def calculate_incremental_orders(
        self,
        net_inflow: Decimal,
        leverage_ratio: Decimal,
        target_weights: dict[str, Decimal],
        market_prices: dict[str, Decimal],
        contract_multipliers: dict[str, int],
        previous_fractionals: dict[str, Decimal],
    ) -> list[IncrementalOrder]:
        """
        计算增量买入订单（净入金场景）。

        Args:
            net_inflow: 净入金金额（元）
            leverage_ratio: 杠杆倍数（如 2.0 表示2倍杠杆）
            target_weights: 目标权重字典 {asset_code: weight}
            market_prices: 市场价格字典 {asset_code: 卖1价}
            contract_multipliers: 合约乘数字典 {asset_code: multiplier}
            previous_fractionals: 上次留白数据 {asset_code: fractional_amount}

        Returns:
            增量订单列表

        计算步骤：
            1. 杠杆后市值 = 净入金 × 杠杆倍数
            2. 标的分配市值 = 杠杆后市值 × 目标权重
            3. 理论手数 = (标的分配市值 + 上次留白市值) / (卖1价 × 合约乘数)
            4. 四舍五入 + 留白存储
        """
        logger.info(f"开始计算增量买入订单: 净入金={net_inflow}, 杠杆={leverage_ratio}")

        # 步骤1: 计算杠杆后市值
        leveraged_amount = net_inflow * leverage_ratio
        logger.info(f"杠杆后市值: {leveraged_amount}")

        orders = []

        for asset_code, weight in target_weights.items():
            # 步骤2: 标的分配市值
            target_market_value = leveraged_amount * weight

            # 获取价格和合约乘数
            price = market_prices.get(asset_code)
            multiplier = contract_multipliers.get(asset_code)

            if price is None or multiplier is None:
                logger.warning(f"跳过 {asset_code}: 缺少价格或合约乘数")
                continue

            # 获取上次留白
            previous_fractional = previous_fractionals.get(asset_code, Decimal("0.0"))

            # 步骤3: 计算理论手数（包含上次留白）
            # 上次留白对应的市值
            previous_fractional_value = (
                previous_fractional * price * Decimal(multiplier)
            )

            # 总目标市值 = 本次分配市值 + 上次留白市值
            total_target_value = target_market_value + previous_fractional_value

            # 理论手数
            theoretical_quantity = total_target_value / (price * Decimal(multiplier))

            # 步骤4: 四舍五入
            rounded_quantity = int(round(theoretical_quantity))

            # 留白部分 = 理论手数 - 四舍五入后的手数
            fractional_part = theoretical_quantity - Decimal(rounded_quantity)

            # 最终手数（初始值等于四舍五入后的值，可由交易员手动调整）
            final_quantity = rounded_quantity

            order = IncrementalOrder(
                asset_code=asset_code,
                target_market_value=target_market_value,
                price=price,
                contract_multiplier=multiplier,
                theoretical_quantity=theoretical_quantity,
                rounded_quantity=rounded_quantity,
                fractional_part=fractional_part,
                previous_fractional=previous_fractional,
                final_quantity=final_quantity,
            )

            orders.append(order)

            logger.info(
                f"{asset_code}: 目标市值={target_market_value:.2f}, "
                f"价格={price}, 乘数={multiplier}, "
                f"理论手数={theoretical_quantity:.6f}, "
                f"四舍五入={rounded_quantity}, "
                f"留白={fractional_part:.6f}, "
                f"上次留白={previous_fractional:.6f}"
            )

        return orders
