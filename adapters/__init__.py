"""
外部系统适配器层

提供与外部系统对接的抽象接口和具体实现：
- 行情网关（Market Data Gateway）
- 配置数据源（Config Data Source）
- 迅投交易服务（XunTou Trading Service）
- 前端 API 接口（Frontend API）
"""

from .market_gateway import MarketGateway, CTPMarketGateway, MockMarketGateway
from .config_source import ConfigSource, DatabaseConfigSource, FileConfigSource, MySQLConfigSource
from .xt_query_service import XtQueryService
from .xt_order_service import XtOrderService
from .xt_connection_manager import XtConnectionManager, get_xt_connection_manager
from .frontend_api import FrontendAPI

__all__ = [
    "MarketGateway",
    "CTPMarketGateway",
    "MockMarketGateway",
    "ConfigSource",
    "DatabaseConfigSource",
    "FileConfigSource",
    "MySQLConfigSource",
    "XtQueryService",
    "XtOrderService",
    "XtConnectionManager",
    "get_xt_connection_manager",
    "FrontendAPI",
]
