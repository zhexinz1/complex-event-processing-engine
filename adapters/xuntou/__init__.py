"""
adapters.xuntou — 迅投交易服务包

提供与迅投 XtTraderApi 的完整交互能力：
- XtBaseService: 基础连接管理
- XtOrderService: 下单/撤单
- XtQueryService: 查询（委托/指令/产品/资金）
- XtConnectionManager: 连接池管理

用法：
    from adapters.xuntou import get_xt_connection_manager
    from adapters.xuntou import XtOrderService, OrderRequest, OrderDirection
    from adapters.xuntou import XtQueryService, OrderDetail
"""

from adapters.xuntou.base_service import XtBaseService
from adapters.xuntou.order_service import (
    XtOrderService,
    OrderRequest,
    OrderResult,
    OrderDirection,
    OrderPriceType,
)
from adapters.xuntou.query_service import (
    XtQueryService,
    OrderDetail,
    ProductInfo,
    AccountDetail,
)
from adapters.xuntou.connection_manager import (
    XtConnectionManager,
    get_xt_connection_manager,
)

__all__ = [
    "XtBaseService",
    "XtOrderService",
    "OrderRequest",
    "OrderResult",
    "OrderDirection",
    "OrderPriceType",
    "XtQueryService",
    "OrderDetail",
    "ProductInfo",
    "AccountDetail",
    "XtConnectionManager",
    "get_xt_connection_manager",
]
