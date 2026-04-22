"""
数据库模型定义
用于净入金触发的增量买入流程
"""
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional


class ProductStatus(str, Enum):
    """产品状态"""
    ACTIVE = "active"
    INACTIVE = "inactive"


class OrderStatus(str, Enum):
    """订单状态"""
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    EXECUTED = "executed"
    FAILED = "failed"


class FundInflowStatus(str, Enum):
    """净入金状态"""
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


@dataclass
class Product:
    """产品配置"""
    id: Optional[int]
    product_name: str
    leverage_ratio: Decimal  # 杠杆倍数
    account_id: str  # 迅投资金账号ID（用于下单）
    fund_account: Optional[str] = None  # 资金账号（备用字段）
    xt_username: Optional[str] = None  # 迅投登录用户名
    xt_password: Optional[str] = None  # 迅投登录密码（加密存储）
    status: ProductStatus = ProductStatus.ACTIVE
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class FractionalShare:
    """留白数据（合约维度）"""
    id: Optional[int]
    product_name: str
    asset_code: str  # 合约代码
    fractional_amount: Decimal  # 累积的小数手数
    last_updated: Optional[datetime] = None


@dataclass
class PendingOrder:
    """待确认订单"""
    id: Optional[int]
    batch_id: str  # 批次ID
    product_name: str
    asset_code: str
    target_market_value: Decimal  # 目标市值
    price: Decimal  # 计算时使用的价格（卖1价）
    contract_multiplier: int  # 合约乘数
    theoretical_quantity: Decimal  # 理论手数（未取整）
    rounded_quantity: int  # 四舍五入后的手数
    fractional_part: Decimal  # 留白部分
    final_quantity: int  # 最终确认的手数（可手动调整）
    status: OrderStatus
    created_at: Optional[datetime] = None
    confirmed_at: Optional[datetime] = None
    executed_at: Optional[datetime] = None
    error_msg: Optional[str] = None
    xt_order_id: Optional[int] = None  # 迅投返回的指令ID，用于精确匹配迅投订单状态


@dataclass
class FundInflow:
    """净入金记录"""
    id: Optional[int]
    batch_id: str
    product_name: str
    net_inflow: Decimal  # 净入金金额
    leverage_ratio: Decimal  # 杠杆倍数
    leveraged_amount: Decimal  # 杠杆后金额
    input_by: Optional[str] = None  # 录入人
    input_at: Optional[datetime] = None
    confirmed_by: Optional[str] = None  # 确认人
    confirmed_at: Optional[datetime] = None
    status: FundInflowStatus = FundInflowStatus.PENDING
