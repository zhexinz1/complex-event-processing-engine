"""
order_gateway.py — 订单执行网关适配器

提供统一的订单执行接口，支持多种柜台系统：
- 迅投 GT（XunTou GT）
- CTP 柜台
- 模拟柜台（用于测试）

设计原则：
  1. 抽象接口：定义统一的下单、撤单、查询接口
  2. 异步回报：支持订单状态回调
  3. 风控前置：在网关层进行基础风控校验
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Callable, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 订单相关数据类
# ---------------------------------------------------------------------------

class OrderSide(str, Enum):
    """订单方向"""
    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(str, Enum):
    """订单状态"""
    PENDING = "PENDING"           # 待提交
    SUBMITTED = "SUBMITTED"       # 已提交
    PARTIAL_FILLED = "PARTIAL_FILLED"  # 部分成交
    FILLED = "FILLED"             # 全部成交
    CANCELLED = "CANCELLED"       # 已撤销
    REJECTED = "REJECTED"         # 已拒绝
    ERROR = "ERROR"               # 错误


@dataclass
class Order:
    """
    订单对象。

    Attributes:
        order_id:        订单 ID（系统生成）
        symbol:          合约代码
        side:            买卖方向
        quantity:        委托数量
        price:           委托价格（0 表示市价单）
        status:          订单状态
        filled_quantity: 已成交数量
        avg_filled_price: 平均成交价
        submit_time:     提交时间
        update_time:     更新时间
        error_msg:       错误信息
    """
    order_id: str
    symbol: str
    side: OrderSide
    quantity: float
    price: float = 0.0
    status: OrderStatus = OrderStatus.PENDING
    filled_quantity: float = 0.0
    avg_filled_price: float = 0.0
    submit_time: datetime = None
    update_time: datetime = None
    error_msg: str = ""


# ---------------------------------------------------------------------------
# 抽象基类
# ---------------------------------------------------------------------------

class OrderGateway(ABC):
    """
    订单执行网关抽象基类。

    所有柜台适配器必须实现此接口。
    """

    def __init__(self):
        """初始化订单网关。"""
        self._order_callback: Optional[Callable[[Order], None]] = None

    @abstractmethod
    def connect(self) -> bool:
        """
        连接到柜台系统。

        Returns:
            连接是否成功
        """
        pass

    @abstractmethod
    def disconnect(self) -> None:
        """断开柜台连接。"""
        pass

    @abstractmethod
    def submit_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        price: float = 0.0
    ) -> Optional[str]:
        """
        提交订单。

        Args:
            symbol:   合约代码
            side:     买卖方向
            quantity: 委托数量
            price:    委托价格（0 表示市价单）

        Returns:
            订单 ID，失败返回 None
        """
        pass

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """
        撤销订单。

        Args:
            order_id: 订单 ID

        Returns:
            撤单是否成功
        """
        pass

    @abstractmethod
    def query_order(self, order_id: str) -> Optional[Order]:
        """
        查询订单状态。

        Args:
            order_id: 订单 ID

        Returns:
            订单对象，不存在返回 None
        """
        pass

    def set_order_callback(self, callback: Callable[[Order], None]) -> None:
        """
        设置订单状态回调函数。

        Args:
            callback: 回调函数，接收 Order 对象
        """
        self._order_callback = callback
        logger.info("Order callback registered")

    def _notify_order_update(self, order: Order) -> None:
        """通知订单状态更新。"""
        if self._order_callback:
            self._order_callback(order)


# ---------------------------------------------------------------------------
# 迅投 GT 网关
# ---------------------------------------------------------------------------

class XunTouGTGateway(OrderGateway):
    """
    迅投 GT 柜台网关实现。

    对接迅投 GT 交易系统。

    TODO: 实现迅投 GT API 对接
    - 引入迅投 GT SDK
    - 实现订单提交、撤单、查询接口
    - 实现订单回报处理
    """

    def __init__(
        self,
        server_addr: str,
        account_id: str,
        password: str,
        app_id: str
    ):
        """
        初始化迅投 GT 网关。

        Args:
            server_addr: 服务器地址
            account_id:  账户 ID
            password:    密码
            app_id:      应用 ID
        """
        super().__init__()
        self.server_addr = server_addr
        self.account_id = account_id
        self.password = password
        self.app_id = app_id

        # TODO: 初始化迅投 GT API
        # self.gt_api = GTApi()

        logger.info(f"XunTouGTGateway initialized: {server_addr}")

    def connect(self) -> bool:
        """连接到迅投 GT 柜台。"""
        # TODO: 实现迅投 GT 连接逻辑
        # self.gt_api.connect(self.server_addr, self.account_id, self.password)
        logger.warning("XunTou GT connection not implemented yet")
        return False

    def disconnect(self) -> None:
        """断开迅投 GT 连接。"""
        # TODO: 实现断开逻辑
        logger.info("XunTou GT disconnected")

    def submit_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        price: float = 0.0
    ) -> Optional[str]:
        """提交订单到迅投 GT。"""
        # TODO: 调用迅投 GT API 下单
        # order_id = self.gt_api.insert_order(
        #     symbol=symbol,
        #     direction=1 if side == OrderSide.BUY else 2,
        #     volume=int(quantity),
        #     price=price
        # )
        logger.warning(f"XunTou GT order submission not implemented: {symbol} {side} {quantity}")
        return None

    def cancel_order(self, order_id: str) -> bool:
        """撤销迅投 GT 订单。"""
        # TODO: 调用迅投 GT API 撤单
        # self.gt_api.cancel_order(order_id)
        logger.warning(f"XunTou GT order cancellation not implemented: {order_id}")
        return False

    def query_order(self, order_id: str) -> Optional[Order]:
        """查询迅投 GT 订单状态。"""
        # TODO: 调用迅投 GT API 查询
        # order_data = self.gt_api.query_order(order_id)
        # return self._convert_to_order(order_data)
        logger.warning(f"XunTou GT order query not implemented: {order_id}")
        return None

    def _on_order_update(self, data: dict) -> None:
        """
        迅投 GT 订单回报处理。

        Args:
            data: 迅投 GT 订单回报数据
        """
        # TODO: 解析迅投 GT 回报数据，转换为 Order 对象
        # order = Order(...)
        # self._notify_order_update(order)
        pass


# ---------------------------------------------------------------------------
# 模拟订单网关（用于测试）
# ---------------------------------------------------------------------------

class MockOrderGateway(OrderGateway):
    """
    模拟订单网关，用于测试。

    特性：
    - 订单立即成交
    - 支持订单查询
    - 支持订单回调
    """

    def __init__(self):
        super().__init__()
        self._connected = False
        self._orders: dict[str, Order] = {}
        self._order_counter = 0
        logger.info("MockOrderGateway initialized")

    def connect(self) -> bool:
        """模拟连接成功。"""
        self._connected = True
        logger.info("Mock order gateway connected")
        return True

    def disconnect(self) -> None:
        """模拟断开连接。"""
        self._connected = False
        logger.info("Mock order gateway disconnected")

    def submit_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        price: float = 0.0
    ) -> Optional[str]:
        """
        提交模拟订单（立即成交）。

        Args:
            symbol:   合约代码
            side:     买卖方向
            quantity: 委托数量
            price:    委托价格

        Returns:
            订单 ID
        """
        if not self._connected:
            logger.error("Cannot submit order: not connected")
            return None

        # 生成订单 ID
        self._order_counter += 1
        order_id = f"MOCK_{self._order_counter:06d}"

        # 创建订单对象
        order = Order(
            order_id=order_id,
            symbol=symbol,
            side=side,
            quantity=quantity,
            price=price,
            status=OrderStatus.SUBMITTED,
            submit_time=datetime.now(),
            update_time=datetime.now()
        )

        self._orders[order_id] = order
        logger.info(f"Mock order submitted: {order_id} {symbol} {side} {quantity} @ {price}")

        # 模拟立即成交
        self._simulate_fill(order_id)

        return order_id

    def cancel_order(self, order_id: str) -> bool:
        """撤销模拟订单。"""
        order = self._orders.get(order_id)
        if not order:
            logger.error(f"Order not found: {order_id}")
            return False

        if order.status in [OrderStatus.FILLED, OrderStatus.CANCELLED]:
            logger.warning(f"Cannot cancel order in status {order.status}: {order_id}")
            return False

        order.status = OrderStatus.CANCELLED
        order.update_time = datetime.now()
        self._notify_order_update(order)

        logger.info(f"Mock order cancelled: {order_id}")
        return True

    def query_order(self, order_id: str) -> Optional[Order]:
        """查询模拟订单状态。"""
        order = self._orders.get(order_id)
        if order:
            logger.debug(f"Mock order queried: {order_id} status={order.status}")
        else:
            logger.warning(f"Mock order not found: {order_id}")
        return order

    def _simulate_fill(self, order_id: str) -> None:
        """模拟订单成交。"""
        order = self._orders.get(order_id)
        if not order:
            return

        # 模拟全部成交
        order.status = OrderStatus.FILLED
        order.filled_quantity = order.quantity
        order.avg_filled_price = order.price if order.price > 0 else 100.0  # 市价单使用默认价格
        order.update_time = datetime.now()

        self._notify_order_update(order)
        logger.info(
            f"Mock order filled: {order_id} {order.filled_quantity} @ {order.avg_filled_price}"
        )
