"""
数据库访问层 (DAO)
提供对产品、留白数据、待确认订单、净入金记录的 CRUD 操作
"""
import pymysql
from decimal import Decimal
from typing import List, Optional
from datetime import datetime
import uuid

from database.models import (
    Product, ProductStatus,
    FractionalShare,
    PendingOrder, OrderStatus,
    FundInflow, FundInflowStatus
)


class DatabaseDAO:
    """数据库访问对象"""

    def __init__(self, host: str, port: int, user: str, password: str, database: str):
        self.connection_params = {
            'host': host,
            'port': port,
            'user': user,
            'password': password,
            'database': database,
            'charset': 'utf8mb4',
            'cursorclass': pymysql.cursors.DictCursor
        }

    def _get_connection(self):
        """获取数据库连接"""
        return pymysql.connect(**self.connection_params)

    # ==================== 产品管理 ====================

    def get_product_by_name(self, product_name: str) -> Optional[Product]:
        """根据产品名称查询产品"""
        conn = self._get_connection()
        try:
            with conn.cursor() as cursor:
                sql = "SELECT * FROM products WHERE product_name = %s"
                cursor.execute(sql, (product_name,))
                row = cursor.fetchone()
                if row:
                    return Product(
                        id=row['id'],
                        product_name=row['product_name'],
                        leverage_ratio=row['leverage_ratio'],
                        account_id=row['account_id'],
                        fund_account=row.get('fund_account'),
                        xt_username=row.get('xt_username'),
                        xt_password=row.get('xt_password'),
                        status=ProductStatus(row['status']),
                        created_at=row['created_at'],
                        updated_at=row['updated_at']
                    )
                return None
        finally:
            conn.close()

    def list_active_products(self) -> List[Product]:
        """查询所有活跃产品"""
        conn = self._get_connection()
        try:
            with conn.cursor() as cursor:
                sql = "SELECT * FROM products WHERE status = 'active' ORDER BY product_name"
                cursor.execute(sql)
                rows = cursor.fetchall()
                return [
                    Product(
                        id=row['id'],
                        product_name=row['product_name'],
                        leverage_ratio=row['leverage_ratio'],
                        account_id=row['account_id'],
                        fund_account=row.get('fund_account'),
                        xt_username=row.get('xt_username'),
                        xt_password=row.get('xt_password'),
                        status=ProductStatus(row['status']),
                        created_at=row['created_at'],
                        updated_at=row['updated_at']
                    )
                    for row in rows
                ]
        finally:
            conn.close()

    # ==================== 留白数据管理 ====================

    def get_fractional_share(self, product_name: str, asset_code: str) -> Decimal:
        """获取留白数据（不存在则返回0）"""
        conn = self._get_connection()
        try:
            with conn.cursor() as cursor:
                sql = "SELECT fractional_amount FROM fractional_shares WHERE product_name = %s AND asset_code = %s"
                cursor.execute(sql, (product_name, asset_code))
                row = cursor.fetchone()
                return row['fractional_amount'] if row else Decimal('0.0')
        finally:
            conn.close()

    def update_fractional_share(self, product_name: str, asset_code: str, fractional_amount: Decimal):
        """更新留白数据（INSERT ON DUPLICATE KEY UPDATE）"""
        conn = self._get_connection()
        try:
            with conn.cursor() as cursor:
                sql = """
                INSERT INTO fractional_shares (product_name, asset_code, fractional_amount)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE fractional_amount = %s, last_updated = CURRENT_TIMESTAMP
                """
                cursor.execute(sql, (product_name, asset_code, fractional_amount, fractional_amount))
            conn.commit()
        finally:
            conn.close()

    # ==================== 待确认订单管理 ====================

    def create_pending_order(self, order: PendingOrder) -> int:
        """创建待确认订单"""
        conn = self._get_connection()
        try:
            with conn.cursor() as cursor:
                sql = """
                INSERT INTO pending_orders (
                    batch_id, product_name, asset_code, target_market_value,
                    price, contract_multiplier, theoretical_quantity,
                    rounded_quantity, fractional_part, final_quantity, status,
                    order_price_type
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """
                cursor.execute(sql, (
                    order.batch_id, order.product_name, order.asset_code,
                    order.target_market_value, order.price, order.contract_multiplier,
                    order.theoretical_quantity, order.rounded_quantity,
                    order.fractional_part, order.final_quantity, order.status.value,
                    order.order_price_type
                ))
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    def get_pending_orders_by_batch(self, batch_id: str) -> List[PendingOrder]:
        """根据批次ID查询待确认订单"""
        conn = self._get_connection()
        try:
            with conn.cursor() as cursor:
                sql = "SELECT * FROM pending_orders WHERE batch_id = %s ORDER BY id"
                cursor.execute(sql, (batch_id,))
                rows = cursor.fetchall()
                return [self._row_to_pending_order(row) for row in rows]
        finally:
            conn.close()

    def get_pending_orders_by_product(self, product_name: str, status: Optional[OrderStatus] = None) -> List[PendingOrder]:
        """根据产品名称查询待确认订单"""
        conn = self._get_connection()
        try:
            with conn.cursor() as cursor:
                if status:
                    sql = "SELECT * FROM pending_orders WHERE product_name = %s AND status = %s ORDER BY created_at DESC"
                    cursor.execute(sql, (product_name, status.value))
                else:
                    sql = "SELECT * FROM pending_orders WHERE product_name = %s ORDER BY created_at DESC"
                    cursor.execute(sql, (product_name,))
                rows = cursor.fetchall()
                return [self._row_to_pending_order(row) for row in rows]
        finally:
            conn.close()

    def _row_to_pending_order(self, row: dict) -> PendingOrder:
        """将数据库行转换为 PendingOrder 对象"""
        return PendingOrder(
            id=row['id'],
            batch_id=row['batch_id'],
            product_name=row['product_name'],
            asset_code=row['asset_code'],
            target_market_value=row['target_market_value'],
            price=row['price'],
            contract_multiplier=row['contract_multiplier'],
            theoretical_quantity=row['theoretical_quantity'],
            rounded_quantity=row['rounded_quantity'],
            fractional_part=row['fractional_part'],
            final_quantity=row['final_quantity'],
            status=OrderStatus(row['status']),
            created_at=row['created_at'],
            confirmed_at=row['confirmed_at'],
            executed_at=row['executed_at'],
            error_msg=row['error_msg'],
            xt_order_id=row.get('xt_order_id'),
            xt_status=row.get('xt_status', 'not_sent'),
            xt_error_msg=row.get('xt_error_msg'),
            xt_traded_volume=row.get('xt_traded_volume', 0),
            xt_traded_price=row.get('xt_traded_price', 0.0),
            order_price_type=row.get('order_price_type', 'limit'),
        )

    def update_order_final_quantity(self, order_id: int, final_quantity: int):
        """更新订单的最终手数（交易员手动调整）"""
        conn = self._get_connection()
        try:
            with conn.cursor() as cursor:
                sql = "UPDATE pending_orders SET final_quantity = %s WHERE id = %s"
                cursor.execute(sql, (final_quantity, order_id))
            conn.commit()
        finally:
            conn.close()

    def update_order_status(self, order_id: int, status: OrderStatus,
                           confirmed_by: Optional[str] = None,
                           error_msg: Optional[str] = None):
        """更新订单状态"""
        conn = self._get_connection()
        try:
            with conn.cursor() as cursor:
                if status == OrderStatus.CONFIRMED:
                    sql = """
                    UPDATE pending_orders
                    SET status = %s, confirmed_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                    """
                    cursor.execute(sql, (status.value, order_id))
                elif status == OrderStatus.EXECUTED:
                    sql = """
                    UPDATE pending_orders
                    SET status = %s, executed_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                    """
                    cursor.execute(sql, (status.value, order_id))
                elif status == OrderStatus.FAILED:
                    sql = """
                    UPDATE pending_orders
                    SET status = %s, error_msg = %s
                    WHERE id = %s
                    """
                    cursor.execute(sql, (status.value, error_msg, order_id))
                else:
                    sql = "UPDATE pending_orders SET status = %s WHERE id = %s"
                    cursor.execute(sql, (status.value, order_id))
            conn.commit()
        finally:
            conn.close()

    def update_order_xt_id(self, order_id: int, xt_order_id: int):
        """下单成功后将迅投返回的指令ID写入数据库，同时标记 xt_status='sent'"""
        conn = self._get_connection()
        try:
            with conn.cursor() as cursor:
                sql = "UPDATE pending_orders SET xt_order_id = %s, xt_status = 'sent' WHERE id = %s"
                cursor.execute(sql, (xt_order_id, order_id))
            conn.commit()
        finally:
            conn.close()

    def update_order_xt_send_failed(self, order_id: int, error_msg: str):
        """SDK 调用失败时标记 xt_status='send_failed'"""
        conn = self._get_connection()
        try:
            with conn.cursor() as cursor:
                sql = "UPDATE pending_orders SET xt_status = 'send_failed', xt_error_msg = %s WHERE id = %s"
                cursor.execute(sql, (error_msg, order_id))
            conn.commit()
        finally:
            conn.close()

    # 迅投终态 → 业务状态映射
    _XT_TERMINAL_STATUS_MAP: dict[str, str] = {
        "filled": "executed",
        "rejected": "failed",
        "cancelled": "cancelled",
        "stopped": "failed",
    }

    def update_order_xt_status(self, xt_order_id: int, xt_status: str,
                               xt_error_msg: str = ""):
        """根据迅投指令ID更新订单的迅投侧状态（回调 / 对账使用）

        当 xt_status 到达终态（filled/rejected/cancelled/stopped）时，
        同步更新业务 status 字段，保持两个状态一致。
        """
        import logging as _logging
        _logger = _logging.getLogger(__name__)

        conn = self._get_connection()
        try:
            with conn.cursor() as cursor:
                # 检查是否为终态，需要同步更新业务 status
                biz_status = self._XT_TERMINAL_STATUS_MAP.get(xt_status)
                if biz_status:
                    sql = """UPDATE pending_orders
                             SET xt_status = %s, xt_error_msg = %s, status = %s
                             WHERE xt_order_id = %s"""
                    cursor.execute(sql, (xt_status, xt_error_msg, biz_status, xt_order_id))
                else:
                    sql = """UPDATE pending_orders
                             SET xt_status = %s, xt_error_msg = %s
                             WHERE xt_order_id = %s"""
                    cursor.execute(sql, (xt_status, xt_error_msg, xt_order_id))
                if cursor.rowcount == 0:
                    _logger.debug("update_order_xt_status: xt_order_id=%s 未匹配到订单", xt_order_id)
                elif biz_status:
                    _logger.info("update_order_xt_status: xt_order_id=%s 终态同步 status → %s", xt_order_id, biz_status)
            conn.commit()
        finally:
            conn.close()

    def update_order_xt_trade(self, xt_order_id: int, traded_volume: int,
                              traded_price: float):
        """成交回报写入（回调使用）"""
        conn = self._get_connection()
        try:
            with conn.cursor() as cursor:
                sql = """UPDATE pending_orders
                         SET xt_traded_volume = %s, xt_traded_price = %s
                         WHERE xt_order_id = %s"""
                cursor.execute(sql, (traded_volume, traded_price, xt_order_id))
            conn.commit()
        finally:
            conn.close()

    def get_orders_by_xt_status(self, statuses: List[str]) -> List[PendingOrder]:
        """查询指定迅投状态的订单（用于对账）"""
        if not statuses:
            return []
        conn = self._get_connection()
        try:
            with conn.cursor() as cursor:
                placeholders = ', '.join(['%s'] * len(statuses))
                sql = f"SELECT * FROM pending_orders WHERE xt_status IN ({placeholders})"
                cursor.execute(sql, statuses)
                return [self._row_to_pending_order(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    # ==================== 净入金记录管理 ====================

    def create_fund_inflow(self, inflow: FundInflow) -> str:
        """创建净入金记录，返回 batch_id"""
        conn = self._get_connection()
        try:
            with conn.cursor() as cursor:
                sql = """
                INSERT INTO fund_inflows (
                    batch_id, product_name, net_inflow, leverage_ratio,
                    leveraged_amount, input_by, status
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                """
                cursor.execute(sql, (
                    inflow.batch_id, inflow.product_name, inflow.net_inflow,
                    inflow.leverage_ratio, inflow.leveraged_amount,
                    inflow.input_by, inflow.status.value
                ))
            conn.commit()
            return inflow.batch_id
        finally:
            conn.close()

    def get_fund_inflow_by_batch(self, batch_id: str) -> Optional[FundInflow]:
        """根据批次ID查询净入金记录"""
        conn = self._get_connection()
        try:
            with conn.cursor() as cursor:
                sql = "SELECT * FROM fund_inflows WHERE batch_id = %s"
                cursor.execute(sql, (batch_id,))
                row = cursor.fetchone()
                if row:
                    return FundInflow(
                        id=row['id'],
                        batch_id=row['batch_id'],
                        product_name=row['product_name'],
                        net_inflow=row['net_inflow'],
                        leverage_ratio=row['leverage_ratio'],
                        leveraged_amount=row['leveraged_amount'],
                        input_by=row['input_by'],
                        input_at=row['input_at'],
                        confirmed_by=row['confirmed_by'],
                        confirmed_at=row['confirmed_at'],
                        status=FundInflowStatus(row['status'])
                    )
                return None
        finally:
            conn.close()

    def list_fund_inflows(self, limit: int = 50) -> list[FundInflow]:
        """查询所有净入金记录，按创建时间倒序排列"""
        conn = self._get_connection()
        try:
            with conn.cursor() as cursor:
                sql = "SELECT * FROM fund_inflows ORDER BY input_at DESC LIMIT %s"
                cursor.execute(sql, (limit,))
                rows = cursor.fetchall()
                return [
                    FundInflow(
                        id=row['id'],
                        batch_id=row['batch_id'],
                        product_name=row['product_name'],
                        net_inflow=row['net_inflow'],
                        leverage_ratio=row['leverage_ratio'],
                        leveraged_amount=row['leveraged_amount'],
                        input_by=row['input_by'],
                        input_at=row['input_at'],
                        confirmed_by=row['confirmed_by'],
                        confirmed_at=row['confirmed_at'],
                        status=FundInflowStatus(row['status'])
                    )
                    for row in rows
                ]
        finally:
            conn.close()

    def update_fund_inflow_status(self, batch_id: str, status: FundInflowStatus,
                                  confirmed_by: Optional[str] = None):
        """更新净入金状态"""
        conn = self._get_connection()
        try:
            with conn.cursor() as cursor:
                if status == FundInflowStatus.CONFIRMED:
                    sql = """
                    UPDATE fund_inflows
                    SET status = %s, confirmed_by = %s, confirmed_at = CURRENT_TIMESTAMP
                    WHERE batch_id = %s
                    """
                    cursor.execute(sql, (status.value, confirmed_by, batch_id))
                else:
                    sql = "UPDATE fund_inflows SET status = %s WHERE batch_id = %s"
                    cursor.execute(sql, (status.value, batch_id))
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def generate_batch_id() -> str:
        """生成批次ID（时间戳 + UUID）"""
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        short_uuid = str(uuid.uuid4())[:8]
        return f"{timestamp}_{short_uuid}"

    # ==================== 行情资产管理 ====================

    def get_all_target_assets(self) -> List[str]:
        """获取全网需要监听行情的目标资产合约代码列表"""
        import logging as _logging
        _logger = _logging.getLogger(__name__)

        conn = self._get_connection()
        try:
            with conn.cursor() as cursor:
                sql = "SELECT DISTINCT asset_code FROM target_allocations"
                cursor.execute(sql)
                rows = cursor.fetchall()
                if rows:
                    return [row['asset_code'] for row in rows]
                return []
        except Exception as e:
            _logger.error("get_all_target_assets 查询异常（可能连接超时）: %s", e)
            return []
        finally:
            conn.close()
