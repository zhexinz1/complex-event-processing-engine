"""
rebalance_handler.py — 再平衡信号处理器

订阅 REBALANCE_REQUEST 信号，调用 RebalanceEngine 计算，生成订单并执行。

工作流程：
  1. 接收 REBALANCE_REQUEST 信号
  2. 从信号 payload 中提取参数（如新增资金）
  3. 调用 RebalanceEngine 执行计算
  4. 校验订单（资金约束、防重等）
  5. 发送订单到柜台（当前模拟）

设计原则：
  - 单一职责：只负责协调再平衡流程，不做具体计算
  - 可扩展：预留订单执行接口，后续对接真实柜台
"""

from __future__ import annotations

import logging
from typing import Optional

from cep.core.event_bus import EventBus
from cep.core.events import SignalEvent, SignalType
from rebalance.portfolio_context import PortfolioContext
from rebalance.rebalance_engine import RebalanceEngine, RebalanceOrder, RebalanceResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 再平衡信号处理器
# ---------------------------------------------------------------------------

class RebalanceHandler:
    """
    再平衡信号处理器。

    核心方法：
      - on_rebalance_signal(): 处理 REBALANCE_REQUEST 信号
    """

    def __init__(
        self,
        event_bus: EventBus,
        portfolio_ctx: PortfolioContext,
    ) -> None:
        """
        初始化再平衡处理器。

        Args:
            event_bus:      全局事件总线
            portfolio_ctx:  组合上下文
        """
        self.event_bus = event_bus
        self.portfolio_ctx = portfolio_ctx
        self.rebalance_engine = RebalanceEngine(portfolio_ctx)

        # 防重机制：记录最近一次执行的时间戳
        self._last_execution_time: float = 0.0
        self._min_execution_interval: float = 10.0  # 最小执行间隔（秒）

        logger.info("RebalanceHandler initialized.")

    def register(self) -> None:
        """订阅 REBALANCE_REQUEST 信号。"""
        self.event_bus.subscribe(SignalEvent, self.on_rebalance_signal)
        logger.info("RebalanceHandler subscribed to SignalEvent (REBALANCE_REQUEST).")

    def on_rebalance_signal(self, signal: SignalEvent) -> None:
        """
        处理 REBALANCE_REQUEST 信号。

        Args:
            signal: SignalEvent 实例
        """
        # 过滤：仅处理 REBALANCE_REQUEST 信号
        if signal.signal_type != SignalType.REBALANCE_REQUEST:
            return

        logger.info(
            f"Received REBALANCE_REQUEST signal from '{signal.source}' "
            f"(event_id={signal.event_id})"
        )

        # 防重校验
        current_time = signal.timestamp.timestamp()
        if current_time - self._last_execution_time < self._min_execution_interval:
            logger.warning(
                f"Rebalance request ignored: too soon after last execution "
                f"({current_time - self._last_execution_time:.1f}s < {self._min_execution_interval}s)"
            )
            return

        # 提取参数
        trigger_type = signal.payload.get("trigger_type", "unknown")
        new_capital = signal.payload.get("new_capital", 0.0)

        logger.info(
            f"Processing rebalance request: trigger_type={trigger_type}, "
            f"new_capital={new_capital:,.2f}"
        )

        # 调用再平衡引擎计算
        try:
            result = self.rebalance_engine.calculate(
                new_capital=new_capital,
                reason=trigger_type
            )

            # 校验订单
            is_valid, error_msg = self.rebalance_engine.validate_orders(result)
            if not is_valid:
                logger.error(f"订单校验失败: {error_msg}")
                return

            # 执行订单
            self._execute_orders(result)

            # 更新最后执行时间
            self._last_execution_time = current_time

        except Exception as e:
            logger.exception(f"Rebalance calculation failed: {e}")

    def _execute_orders(self, result: RebalanceResult) -> None:
        """
        执行订单（当前模拟，后续对接真实柜台）。

        Args:
            result: 再平衡计算结果
        """
        if not result.orders:
            logger.info("No orders to execute (portfolio already balanced).")
            return

        logger.info(f"Executing {len(result.orders)} orders...")

        for order in result.orders:
            # TODO: 对接真实柜台 API
            # 当前模拟：打印订单信息
            logger.info(
                f"  📋 ORDER: {order.symbol} {order.side} {order.quantity} @ {order.estimated_price:.2f} "
                f"(reason: {order.reason})"
            )

            # 模拟订单执行成功，更新持仓（实际应等待柜台回报）
            self._simulate_order_execution(order)

        logger.info(f"✅ All orders executed successfully.")

    def _simulate_order_execution(self, order: RebalanceOrder) -> None:
        """
        模拟订单执行（更新持仓）。

        Args:
            order: 订单对象
        """
        # 获取当前持仓
        position = self.portfolio_ctx.get_position(order.symbol)
        current_quantity = position.quantity if position else 0.0

        # 计算新持仓量
        if order.side == "BUY":
            new_quantity = current_quantity + order.quantity
        else:  # SELL
            new_quantity = current_quantity - order.quantity

        # 获取合约信息
        contract_info = self.portfolio_ctx.get_contract_info(order.symbol)
        if not contract_info:
            logger.warning(f"Contract info not found for {order.symbol}, cannot update position.")
            return

        # 计算新市值
        new_market_value = new_quantity * order.estimated_price * contract_info.multiplier

        # 更新持仓
        from rebalance.portfolio_context import Position
        new_position = Position(
            symbol=order.symbol,
            quantity=new_quantity,
            avg_price=order.estimated_price,  # 简化：使用当前价格作为均价
            market_value=new_market_value
        )
        self.portfolio_ctx.update_position(new_position)

        logger.debug(
            f"Position updated: {order.symbol} quantity={new_quantity:.2f}, "
            f"market_value={new_market_value:,.2f}"
        )
