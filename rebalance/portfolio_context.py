"""
portfolio_context.py — 组合级上下文（Portfolio Context）

用于存储全品种的组合级数据，支持再平衡引擎的计算需求。

核心数据：
  - 目标权重配置（target_weights）：各品种的理论权重
  - 当前持仓（positions）：各品种的实际持仓量
  - 合约信息（contract_info）：合约乘数、最小变动单位等
  - 账户信息（account_info）：总净值、可用资金、保证金占用等
  - 最新行情（latest_prices）：各品种的最新价格

设计原则：
  1. 数据源留白：行情、持仓、配置的拉取接口预留，后续对接外部系统
  2. 统一管理：所有再平衡计算所需的数据集中在此管理
  3. 线程安全：当前为单线程设计，多线程需加锁
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 数据类定义
# ---------------------------------------------------------------------------


@dataclass
class ContractInfo:
    """
    合约基础信息。

    Attributes:
        symbol:         合约代码（如 "AU2606"）
        multiplier:     合约乘数（如期货 AU 乘数 1000）
        min_tick:       最小变动价位（如 0.05）
        margin_rate:    保证金率（如 0.08 表示 8%）
    """

    symbol: str
    multiplier: float = 1.0
    min_tick: float = 0.01
    margin_rate: float = 0.1


@dataclass
class Position:
    """
    持仓信息。

    Attributes:
        symbol:         合约代码
        quantity:       持仓量（正数多头，负数空头）
        avg_price:      持仓均价
        market_value:   当前市值（quantity * latest_price * multiplier）
    """

    symbol: str
    quantity: float
    avg_price: float
    market_value: float = 0.0


# ---------------------------------------------------------------------------
# 组合上下文
# ---------------------------------------------------------------------------


class PortfolioContext:
    """
    组合级上下文，存储全品种的组合数据。

    核心功能：
      1. 管理目标权重配置
      2. 管理当前持仓信息（支持从外部数据源同步）
      3. 管理合约基础信息
      4. 管理账户资金信息
      5. 管理最新行情价格

    持仓数据源：
      - 可以从迅投 GT API、CTP API 等外部系统同步持仓
      - 使用 set_position_source() 设置数据源
      - 使用 sync_positions_from_source() 同步持仓
    """

    def __init__(self, position_source=None) -> None:
        """
        初始化组合上下文。

        Args:
            position_source: 持仓数据源（可选），用于从外部系统同步持仓
                           例如：XunTouPositionSource, CTPPositionSource
        """
        # 目标权重配置：{symbol: weight}
        self._target_weights: dict[str, float] = {}

        # 当前持仓：{symbol: Position}
        self._positions: dict[str, Position] = {}

        # 合约信息：{symbol: ContractInfo}
        self._contract_info: dict[str, ContractInfo] = {}

        # 最新价格：{symbol: price}
        self._latest_prices: dict[str, float] = {}

        # 账户信息
        self._total_nav: float = 0.0  # 总净值
        self._available_cash: float = 0.0  # 可用资金
        self._margin_used: float = 0.0  # 已用保证金

        # 持仓数据源（用于从外部系统同步持仓）
        self._position_source = position_source

        logger.info("PortfolioContext initialized.")

    # -----------------------------------------------------------------------
    # 目标权重管理
    # -----------------------------------------------------------------------

    def set_target_weights(self, weights: dict[str, float]) -> None:
        """
        设置目标权重配置。

        Args:
            weights: 目标权重字典，如 {"AU2606": 0.26, "P2609": 0.17}
        """
        self._target_weights = weights.copy()
        logger.info(f"Target weights updated: {weights}")

    def get_target_weight(self, symbol: str) -> float:
        """获取指定品种的目标权重。"""
        return self._target_weights.get(symbol, 0.0)

    def get_all_target_weights(self) -> dict[str, float]:
        """获取所有目标权重配置。"""
        return self._target_weights.copy()

    # -----------------------------------------------------------------------
    # 持仓管理
    # -----------------------------------------------------------------------

    def set_position_source(self, position_source) -> None:
        """
        设置持仓数据源。

        Args:
            position_source: 持仓数据源对象（如 XunTouPositionSource）
        """
        self._position_source = position_source
        logger.info(f"Position source set: {type(position_source).__name__}")

    def sync_positions_from_source(self) -> bool:
        """
        从外部数据源同步持仓信息。

        从迅投 GT API、CTP API 等外部系统拉取最新持仓，
        并更新到 PortfolioContext 中。

        Returns:
            同步是否成功
        """
        if not self._position_source:
            logger.warning("No position source configured, cannot sync positions")
            return False

        try:
            # 从数据源获取所有持仓
            positions = self._position_source.fetch_positions()

            # 更新到上下文
            self._positions = positions
            logger.info(f"Synced {len(positions)} positions from source")

            # 同步账户信息
            account_info = self._position_source.fetch_account_info()
            self._total_nav = account_info.get("total_nav", 0.0)
            self._available_cash = account_info.get("available_cash", 0.0)
            self._margin_used = account_info.get("margin_used", 0.0)
            logger.info(
                f"Synced account info: NAV={self._total_nav:,.2f}, "
                f"Available={self._available_cash:,.2f}, Margin={self._margin_used:,.2f}"
            )

            return True

        except Exception as e:
            logger.error(f"Failed to sync positions from source: {e}")
            return False

    def update_position(self, position: Position) -> None:
        """
        更新持仓信息（手动更新，不从数据源同步）。

        Args:
            position: 持仓对象
        """
        self._positions[position.symbol] = position
        logger.debug(f"Position updated: {position.symbol}, qty={position.quantity}")

    def get_position(self, symbol: str) -> Optional[Position]:
        """获取指定品种的持仓信息。"""
        return self._positions.get(symbol)

    def get_all_positions(self) -> dict[str, Position]:
        """获取所有持仓信息。"""
        return self._positions.copy()

    # -----------------------------------------------------------------------
    # 合约信息管理
    # -----------------------------------------------------------------------

    def register_contract(self, contract: ContractInfo) -> None:
        """
        注册合约基础信息。

        Args:
            contract: 合约信息对象
        """
        self._contract_info[contract.symbol] = contract
        logger.debug(
            f"Contract registered: {contract.symbol}, multiplier={contract.multiplier}"
        )

    def get_contract_info(self, symbol: str) -> Optional[ContractInfo]:
        """获取指定合约的基础信息。"""
        return self._contract_info.get(symbol)

    # -----------------------------------------------------------------------
    # 行情管理
    # -----------------------------------------------------------------------

    def update_price(self, symbol: str, price: float) -> None:
        """
        更新最新价格。

        Args:
            symbol: 合约代码
            price:  最新价格
        """
        self._latest_prices[symbol] = price
        logger.debug(f"Price updated: {symbol}={price}")

    def get_latest_price(self, symbol: str) -> Optional[float]:
        """获取指定品种的最新价格。"""
        return self._latest_prices.get(symbol)

    # -----------------------------------------------------------------------
    # 账户信息管理
    # -----------------------------------------------------------------------

    def update_account(
        self, total_nav: float, available_cash: float, margin_used: float
    ) -> None:
        """
        更新账户信息。

        Args:
            total_nav:       总净值
            available_cash:  可用资金
            margin_used:     已用保证金
        """
        self._total_nav = total_nav
        self._available_cash = available_cash
        self._margin_used = margin_used
        logger.info(
            f"Account updated: NAV={total_nav:,.2f}, "
            f"Available={available_cash:,.2f}, Margin={margin_used:,.2f}"
        )

    def get_total_nav(self) -> float:
        """获取总净值。"""
        return self._total_nav

    def get_available_cash(self) -> float:
        """获取可用资金。"""
        return self._available_cash

    def get_margin_used(self) -> float:
        """获取已用保证金。"""
        return self._margin_used

    # -----------------------------------------------------------------------
    # 计算辅助方法
    # -----------------------------------------------------------------------

    def calculate_current_weight(self, symbol: str) -> float:
        """
        计算指定品种的当前权重（基于最新价格动态计算）。

        Args:
            symbol: 合约代码

        Returns:
            当前权重（0.0 ~ 1.0）
        """
        if self._total_nav <= 0:
            return 0.0

        position = self._positions.get(symbol)
        if not position:
            return 0.0

        # 使用最新价格动态计算市值
        latest_price = self._latest_prices.get(symbol)
        if latest_price is None:
            # 如果没有最新价格，使用持仓记录的市值
            return position.market_value / self._total_nav

        contract = self._contract_info.get(symbol)
        multiplier = contract.multiplier if contract else 1.0

        current_market_value = position.quantity * latest_price * multiplier
        return current_market_value / self._total_nav

    def calculate_all_current_weights(self) -> dict[str, float]:
        """
        计算所有品种的当前权重（基于最新价格动态计算）。

        Returns:
            当前权重字典 {symbol: weight}
        """
        if self._total_nav <= 0:
            return {}

        weights = {}
        for symbol, pos in self._positions.items():
            # 使用最新价格动态计算市值
            latest_price = self._latest_prices.get(symbol)
            if latest_price is None:
                # 如果没有最新价格，使用持仓记录的市值
                weights[symbol] = pos.market_value / self._total_nav
                continue

            contract = self._contract_info.get(symbol)
            multiplier = contract.multiplier if contract else 1.0

            current_market_value = pos.quantity * latest_price * multiplier
            weights[symbol] = current_market_value / self._total_nav

        return weights
