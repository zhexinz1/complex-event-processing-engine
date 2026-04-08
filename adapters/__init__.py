"""
外部系统适配器层

提供与外部系统对接的抽象接口和具体实现：
- 行情网关（Market Data Gateway）
- 配置数据源（Config Data Source）
- 订单执行网关（Order Execution Gateway）
- 前端 API 接口（Frontend API）
"""

from .market_gateway import MarketGateway, CTPMarketGateway, MockMarketGateway
from .config_source import ConfigSource, DatabaseConfigSource, FileConfigSource, MySQLConfigSource
from .order_gateway import OrderGateway, XunTouGTGateway, MockOrderGateway
from .frontend_api import FrontendAPI

__all__ = [
    "MarketGateway",
    "CTPMarketGateway",
    "MockMarketGateway",
    "ConfigSource",
    "DatabaseConfigSource",
    "FileConfigSource",
    "MySQLConfigSource",
    "OrderGateway",
    "XunTouGTGateway",
    "MockOrderGateway",
    "FrontendAPI",
]
