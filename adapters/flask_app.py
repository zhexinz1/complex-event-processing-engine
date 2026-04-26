"""
flask_app.py — 目标仓位配置 REST API

提供 target_allocations 表的 CRUD 接口，并挂载前端静态文件。

Endpoints:
    GET  /api/weights          查询（支持 target_date / product_name 过滤）
    POST /api/weights          新增或覆盖更新
    DELETE /api/weights/<id>   删除单条记录
    GET  /api/products         获取产品名称列表
    GET  /api/assets           获取资产代码白名单
    POST /api/assets           新增资产代码
    DELETE /api/assets/<code>  删除资产代码

    # 新增：净入金流程
    POST /api/fund/inflow      提交净入金并计算订单
    GET  /api/orders/pending   查询待确认订单
    POST /api/orders/confirm   确认订单并执行
    POST /api/orders/update    更新订单数量

    GET  /                     前端大屏页面
"""

from __future__ import annotations

import logging
from pathlib import Path
from decimal import Decimal
from datetime import datetime
import uuid

import pymysql
import pymysql.cursors
from flask import Flask, jsonify, request, send_from_directory

from database.dao import DatabaseDAO
from database.models import PendingOrder, OrderStatus, FundInflow, FundInflowStatus
from rebalance.rebalance_engine import RebalanceEngine, IncrementalOrder
from adapters.xuntou import XtOrderService, OrderRequest, OrderDirection, OrderPriceType
from adapters.xuntou import XtQueryService
from adapters.xuntou import get_xt_connection_manager
from adapters.price_service import get_latest_price, init_redis_market_subscriber, get_tick_cache_detail
from adapters.contract_config import get_contract_multiplier, normalize_asset_code

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 数据库连接配置
# ---------------------------------------------------------------------------

DB_CONFIG = dict(
    host="120.25.245.137",
    port=23306,
    database="fof",
    user="cx",
    password="cC3z#,2?od)gn7Nhd2L1",
    charset="utf8mb4",
    cursorclass=pymysql.cursors.DictCursor,
    autocommit=False,
    connect_timeout=10,  # 连接超时10秒
    read_timeout=10,     # 读取超时10秒
    write_timeout=10,    # 写入超时10秒
)

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS target_allocations (
    id            INT PRIMARY KEY AUTO_INCREMENT,
    target_date   DATE           NOT NULL,
    product_name  VARCHAR(100)   NOT NULL,
    asset_code    VARCHAR(50)    NOT NULL,
    weight_ratio  DECIMAL(12, 6) NOT NULL,
    algo_type     VARCHAR(20)    NOT NULL DEFAULT 'TWAP',
    created_at    TIMESTAMP      DEFAULT CURRENT_TIMESTAMP,
    updated_at    TIMESTAMP      DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_date_product_asset (target_date, product_name, asset_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""

CREATE_ASSETS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS allowed_assets (
    id          INT PRIMARY KEY AUTO_INCREMENT,
    asset_code  VARCHAR(50)  NOT NULL,
    created_at  TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_asset_code (asset_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"

# 全局 DAO 实例（在 create_app 中初始化）
dao: DatabaseDAO = None


def get_conn():
    return pymysql.connect(**DB_CONFIG)


def init_db() -> None:
    """建表（幂等），应用启动时调用一次。"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(CREATE_TABLE_SQL)
            cur.execute(CREATE_ASSETS_TABLE_SQL)
        conn.commit()
    logger.info("DB tables target_allocations and allowed_assets ready.")

    # 初始化 DAO
    global dao
    dao = DatabaseDAO(
        host=DB_CONFIG['host'],
        port=DB_CONFIG['port'],
        user=DB_CONFIG['user'],
        password=DB_CONFIG['password'],
        database=DB_CONFIG['database']
    )
    logger.info("DatabaseDAO initialized.")


# ---------------------------------------------------------------------------
# Flask 应用工厂
# ---------------------------------------------------------------------------

def create_app() -> Flask:
    app = Flask(__name__, static_folder=None)

    # 初始化数据库和 DAO
    init_db()

    # -----------------------------------------------------------------------
    # 前端静态文件
    # -----------------------------------------------------------------------

    @app.route("/")
    def index():
        return send_from_directory(str(FRONTEND_DIR), "index.html")

    @app.route("/<path:filename>")
    def static_files(filename: str):
        return send_from_directory(str(FRONTEND_DIR), filename)

    # -----------------------------------------------------------------------
    # GET /api/weights
    # -----------------------------------------------------------------------

    @app.route("/api/weights", methods=["GET"])
    def get_weights():
        target_date = request.args.get("target_date")
        product_name = request.args.get("product_name")

        conditions = []
        params: list = []
        if target_date:
            conditions.append("target_date = %s")
            params.append(target_date)
        if product_name:
            conditions.append("product_name = %s")
            params.append(product_name)

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        sql = f"""
            SELECT id, DATE_FORMAT(target_date, '%%Y-%%m-%%d') AS target_date,
                   product_name, asset_code, weight_ratio, algo_type,
                   created_at, updated_at
            FROM target_allocations
            {where}
            ORDER BY target_date DESC, product_name, asset_code
        """
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, params)
                    rows = cur.fetchall()
        except Exception as e:
            return jsonify({"success": False, "message": f"数据库连接失败: {e}", "data": []}), 503

        # Decimal → float for JSON serialisation
        for row in rows:
            row["weight_ratio"] = float(row["weight_ratio"])
            if row.get("created_at"):
                row["created_at"] = str(row["created_at"])
            if row.get("updated_at"):
                row["updated_at"] = str(row["updated_at"])

        return jsonify({"success": True, "data": rows, "total": len(rows)})

    # -----------------------------------------------------------------------
    # POST /api/weights
    # -----------------------------------------------------------------------

    @app.route("/api/weights", methods=["POST"])
    def upsert_weight():
        body = request.get_json(force=True)
        required = ("target_date", "product_name", "asset_code", "weight_ratio")
        missing = [f for f in required if f not in body]
        if missing:
            return jsonify({"success": False, "message": f"缺少字段: {missing}"}), 400

        sql = """
            INSERT INTO target_allocations
                (target_date, product_name, asset_code, weight_ratio, algo_type)
            VALUES (%s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                weight_ratio = VALUES(weight_ratio),
                algo_type    = VALUES(algo_type),
                updated_at   = NOW()
        """
        params = (
            body["target_date"],
            body["product_name"],
            body["asset_code"],
            body["weight_ratio"],
            body.get("algo_type", "TWAP"),
        )
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, params)
                    new_id = cur.lastrowid
                conn.commit()
        except Exception as e:
            return jsonify({"success": False, "message": f"数据库错误: {e}"}), 503

        return jsonify({"success": True, "message": "保存成功", "id": new_id}), 200

    # -----------------------------------------------------------------------
    # DELETE /api/weights/<id>
    # -----------------------------------------------------------------------

    @app.route("/api/weights/<int:record_id>", methods=["DELETE"])
    def delete_weight(record_id: int):
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM target_allocations WHERE id = %s", (record_id,))
                    affected = cur.rowcount
                conn.commit()
        except Exception as e:
            return jsonify({"success": False, "message": f"数据库连接失败: {e}"}), 503

        if affected == 0:
            return jsonify({"success": False, "message": "记录不存在"}), 404
        return jsonify({"success": True, "message": "删除成功"})

    # -----------------------------------------------------------------------
    # GET /api/products  — 产品名称列表（供前端下拉框使用）
    # -----------------------------------------------------------------------

    @app.route("/api/products", methods=["GET"])
    def get_products():
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT DISTINCT product_name FROM target_allocations ORDER BY product_name"
                    )
                    rows = cur.fetchall()
        except Exception:
            return jsonify({"success": True, "data": []})
        return jsonify({"success": True, "data": [r["product_name"] for r in rows]})

    # -----------------------------------------------------------------------
    # GET /api/products/list  — 产品详细列表（含杠杆配置）
    # -----------------------------------------------------------------------

    @app.route("/api/products/list", methods=["GET"])
    def get_products_list():
        """获取产品详细列表（含杠杆倍数、账号等信息）"""
        try:
            products = dao.list_active_products()
            return jsonify({
                "success": True,
                "products": [
                    {
                        "product_name": p.product_name,
                        "leverage_ratio": float(p.leverage_ratio),
                        "account_id": p.account_id,
                        "fund_account": p.fund_account,
                        "status": p.status.value
                    }
                    for p in products
                ]
            })
        except Exception as e:
            logger.exception("查询产品列表失败")
            return jsonify({"success": False, "message": f"服务器错误: {str(e)}"}), 500

    # -----------------------------------------------------------------------
    # POST /api/products/add  — 新增产品
    # -----------------------------------------------------------------------

    @app.route("/api/products/add", methods=["POST"])
    def add_product():
        """新增产品"""
        data = request.get_json()
        product_name = data.get("product_name", "").strip()
        leverage_ratio = data.get("leverage_ratio")
        account_id = data.get("account_id", "").strip()
        fund_account = data.get("fund_account", "").strip() or None
        xt_username = data.get("xt_username", "").strip() or None
        xt_password = data.get("xt_password", "").strip() or None

        if not product_name or not leverage_ratio or not account_id:
            return jsonify({"success": False, "message": "参数不完整"}), 400

        try:
            # 检查产品是否已存在
            existing = dao.get_product_by_name(product_name)
            if existing:
                return jsonify({"success": False, "message": f"产品 {product_name} 已存在"}), 409

            # 插入数据库
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO products (product_name, leverage_ratio, account_id, fund_account, xt_username, xt_password, status)
                        VALUES (%s, %s, %s, %s, %s, %s, 'active')
                        """,
                        (product_name, leverage_ratio, account_id, fund_account, xt_username, xt_password)
                    )
                conn.commit()

            return jsonify({"success": True, "message": f"产品 {product_name} 已添加"})
        except Exception as e:
            logger.exception("添加产品失败")
            return jsonify({"success": False, "message": f"服务器错误: {str(e)}"}), 500

    # -----------------------------------------------------------------------
    # POST /api/products/update  — 更新产品信息
    # -----------------------------------------------------------------------

    @app.route("/api/products/update", methods=["POST"])
    def update_product():
        """更新产品信息"""
        data = request.get_json()
        product_name = data.get("product_name", "").strip()

        if not product_name:
            return jsonify({"success": False, "message": "产品名称不能为空"}), 400

        try:
            # 构建更新语句
            updates = []
            params = []

            if "leverage_ratio" in data:
                updates.append("leverage_ratio = %s")
                params.append(data["leverage_ratio"])

            if "account_id" in data:
                updates.append("account_id = %s")
                params.append(data["account_id"])

            if "fund_account" in data:
                updates.append("fund_account = %s")
                params.append(data["fund_account"] if data["fund_account"] else None)

            if "xt_username" in data:
                updates.append("xt_username = %s")
                params.append(data["xt_username"] if data["xt_username"] else None)

            if "xt_password" in data:
                updates.append("xt_password = %s")
                params.append(data["xt_password"] if data["xt_password"] else None)

            if "status" in data:
                updates.append("status = %s")
                params.append(data["status"])

            if not updates:
                return jsonify({"success": False, "message": "没有需要更新的字段"}), 400

            params.append(product_name)

            with get_conn() as conn:
                with conn.cursor() as cur:
                    sql = f"UPDATE products SET {', '.join(updates)} WHERE product_name = %s"
                    cur.execute(sql, params)
                conn.commit()

            return jsonify({"success": True, "message": f"产品 {product_name} 已更新"})
        except Exception as e:
            logger.exception("更新产品失败")
            return jsonify({"success": False, "message": f"服务器错误: {str(e)}"}), 500

    # -----------------------------------------------------------------------
    # GET /api/assets  — 获取资产代码白名单
    # -----------------------------------------------------------------------

    @app.route("/api/assets", methods=["GET"])
    def get_assets():
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT asset_code, created_at FROM allowed_assets ORDER BY asset_code"
                    )
                    rows = cur.fetchall()
        except Exception as e:
            return jsonify({"success": False, "message": f"数据库连接失败: {e}", "data": []}), 503
        for row in rows:
            if row.get("created_at"):
                row["created_at"] = str(row["created_at"])
        return jsonify({"success": True, "data": rows})

    # -----------------------------------------------------------------------
    # POST /api/assets  — 新增资产代码
    # -----------------------------------------------------------------------

    @app.route("/api/assets", methods=["POST"])
    def add_asset():
        body = request.get_json(force=True)
        asset_code = (body.get("asset_code") or "").strip()
        if not asset_code:
            return jsonify({"success": False, "message": "asset_code 不能为空"}), 400

        # TODO: 校验品种是否存在（未来挂载 CTP/实盘接口查验交易所品种）
        # is_valid = ctp_gateway.check_symbol(asset_code)
        # if not is_valid:
        #     return jsonify({"success": False, "message": f"品种 {asset_code} 在交易所不存在"}), 422

        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO allowed_assets (asset_code) VALUES (%s)",
                        (asset_code,),
                    )
                conn.commit()
        except pymysql.err.IntegrityError:
            return jsonify({"success": False, "message": f"资产代码 {asset_code} 已存在"}), 409
        except Exception as e:
            return jsonify({"success": False, "message": f"数据库错误: {e}"}), 503

        return jsonify({"success": True, "message": f"已添加资产代码 {asset_code}"}), 201

    # -----------------------------------------------------------------------
    # DELETE /api/assets/<asset_code>  — 删除资产代码
    # -----------------------------------------------------------------------

    @app.route("/api/assets/<asset_code>", methods=["DELETE"])
    def delete_asset(asset_code: str):
        # 保持原始大小写直接进入数据库匹配
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "DELETE FROM allowed_assets WHERE asset_code = %s", (asset_code,)
                    )
                    affected = cur.rowcount
                conn.commit()
        except Exception as e:
            return jsonify({"success": False, "message": f"数据库连接失败: {e}"}), 503

        if affected == 0:
            return jsonify({"success": False, "message": "资产代码不存在"}), 404
        return jsonify({"success": True, "message": f"已删除资产代码 {asset_code}"})

    # -----------------------------------------------------------------------
    # GET /api/fund/inflows — 查询所有净入金批次列表
    # -----------------------------------------------------------------------

    @app.route("/api/fund/inflows", methods=["GET"])
    def list_fund_inflows():
        """
        查询所有净入金批次，按创建时间倒序返回。
        可选参数: limit (默认50)
        """
        try:
            limit = request.args.get("limit", 50, type=int)
            inflows = dao.list_fund_inflows(limit=limit)

            return jsonify({
                "success": True,
                "inflows": [
                    {
                        "batch_id": inf.batch_id,
                        "product_name": inf.product_name,
                        "net_inflow": str(inf.net_inflow),
                        "leverage_ratio": str(inf.leverage_ratio),
                        "leveraged_amount": str(inf.leveraged_amount),
                        "input_by": inf.input_by or "",
                        "input_at": inf.input_at.isoformat() if inf.input_at else "",
                        "confirmed_by": inf.confirmed_by or "",
                        "confirmed_at": inf.confirmed_at.isoformat() if inf.confirmed_at else "",
                        "status": inf.status.value,
                    }
                    for inf in inflows
                ]
            })

        except Exception as e:
            logger.exception("查询净入金列表失败")
            return jsonify({"success": False, "message": str(e)}), 500

    # -----------------------------------------------------------------------
    # GET /api/prices/realtime — 查询多合约实时行情
    # -----------------------------------------------------------------------

    @app.route("/api/prices/realtime", methods=["GET"])
    def prices_realtime():
        """
        返回指定合约的实时价格（从 Redis Tick 缓存取）。
        参数: symbols=ag2606,au2606  (逗号分隔)
        """
        symbols_param = request.args.get("symbols", "")
        if not symbols_param:
            return jsonify({"success": False, "message": "请提供 symbols 参数"}), 400

        symbols = [s.strip() for s in symbols_param.split(",") if s.strip()]

        detail = get_tick_cache_detail()
        result = {}
        for sym in symbols:
            info = detail["symbols"].get(sym)
            if info:
                result[sym] = {
                    "last_price": info["last_price"],
                    "bid1": info["bid1"],
                    "ask1": info["ask1"],
                    "bid1_vol": info.get("bid1_vol", 0),
                    "ask1_vol": info.get("ask1_vol", 0),
                    "update_time": info.get("update_time", ""),
                }
            else:
                result[sym] = None

        return jsonify({"success": True, "prices": result})

    # -----------------------------------------------------------------------
    # POST /api/fund/inflow — 提交净入金并计算订单
    # -----------------------------------------------------------------------

    @app.route("/api/fund/inflow", methods=["POST"])
    def submit_fund_inflow():
        """
        提交净入金，计算增量买入订单。

        请求体:
        {
            "product_name": "产品A",
            "net_inflow": 1000000.00,
            "input_by": "张三"
        }

        返回:
        {
            "success": true,
            "batch_id": "uuid",
            "orders": [
                {
                    "asset_code": "AU2609",
                    "target_market_value": 500000.00,
                    "price": 450.50,
                    "contract_multiplier": 1000,
                    "theoretical_quantity": 1.109,
                    "rounded_quantity": 1,
                    "fractional_part": 0.109,
                    "previous_fractional": 0.0,
                    "final_quantity": 1
                }
            ]
        }
        """
        data = request.get_json()
        product_name = data.get("product_name")
        net_inflow = Decimal(str(data.get("net_inflow")))
        input_by = data.get("input_by", "")

        if not product_name or net_inflow <= 0:
            return jsonify({"success": False, "message": "参数错误"}), 400

        try:
            # 1. 查询产品配置（杠杆倍数）
            product = dao.get_product_by_name(product_name)
            if not product:
                return jsonify({"success": False, "message": f"产品 {product_name} 不存在"}), 404

            leverage_ratio = product.leverage_ratio

            # 2. 查询目标权重配置（从 target_allocations 表）
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT asset_code, weight_ratio
                        FROM target_allocations
                        WHERE product_name = %s
                        ORDER BY target_date DESC
                        LIMIT 100
                        """,
                        (product_name,)
                    )
                    rows = cur.fetchall()

            if not rows:
                return jsonify({"success": False, "message": f"产品 {product_name} 没有配置目标权重"}), 404

            target_weights = {row['asset_code']: Decimal(str(row['weight_ratio'])) for row in rows}

            # 3. 从行情缓存获取市场价格和合约乘数（无缓存时用模拟价格）
            market_prices = {}
            contract_multipliers = {}

            for asset_code in target_weights.keys():
                price = get_latest_price(asset_code)
                market_prices[asset_code] = price
                contract_multipliers[asset_code] = get_contract_multiplier(asset_code)

            # 4. 获取留白数据
            previous_fractionals = {}
            for asset_code in target_weights.keys():
                previous_fractionals[asset_code] = dao.get_fractional_share(product_name, asset_code)

            # 5. 调用 RebalanceEngine 计算增量订单
            # 注意：这里不需要 PortfolioContext，因为是纯增量计算
            from rebalance.rebalance_engine import RebalanceEngine
            engine = RebalanceEngine(portfolio_ctx=None)  # 增量计算不需要 portfolio_ctx

            orders = engine.calculate_incremental_orders(
                net_inflow=net_inflow,
                leverage_ratio=leverage_ratio,
                target_weights=target_weights,
                market_prices=market_prices,
                contract_multipliers=contract_multipliers,
                previous_fractionals=previous_fractionals
            )

            # 6. 生成批次ID
            batch_id = str(uuid.uuid4())

            # 7. 保存净入金记录
            fund_inflow = FundInflow(
                id=None,
                batch_id=batch_id,
                product_name=product_name,
                net_inflow=net_inflow,
                leverage_ratio=leverage_ratio,
                leveraged_amount=net_inflow * leverage_ratio,
                input_by=input_by,
                status=FundInflowStatus.PENDING
            )
            dao.create_fund_inflow(fund_inflow)

            # 8. 保存待确认订单
            for order in orders:
                pending_order = PendingOrder(
                    id=None,
                    batch_id=batch_id,
                    product_name=product_name,
                    asset_code=order.asset_code,
                    target_market_value=order.target_market_value,
                    price=order.price,
                    contract_multiplier=order.contract_multiplier,
                    theoretical_quantity=order.theoretical_quantity,
                    rounded_quantity=order.rounded_quantity,
                    fractional_part=order.fractional_part,
                    final_quantity=order.final_quantity,
                    status=OrderStatus.PENDING
                )
                dao.create_pending_order(pending_order)

            # 9. 返回结果
            return jsonify({
                "success": True,
                "batch_id": batch_id,
                "product_name": product_name,
                "net_inflow": float(net_inflow),
                "leverage_ratio": float(leverage_ratio),
                "leveraged_amount": float(net_inflow * leverage_ratio),
                "orders": [
                    {
                        "asset_code": o.asset_code,
                        "target_market_value": float(o.target_market_value),
                        "price": float(o.price),
                        "contract_multiplier": o.contract_multiplier,
                        "theoretical_quantity": float(o.theoretical_quantity),
                        "rounded_quantity": o.rounded_quantity,
                        "fractional_part": float(o.fractional_part),
                        "previous_fractional": float(o.previous_fractional),
                        "final_quantity": o.final_quantity
                    }
                    for o in orders
                ]
            })

        except Exception as e:
            logger.exception("提交净入金失败")
            return jsonify({"success": False, "message": f"服务器错误: {str(e)}"}), 500

    # -----------------------------------------------------------------------
    # GET /api/orders/all — 查询所有订单（用于订单列表页面）
    # -----------------------------------------------------------------------

    @app.route("/api/orders/all", methods=["GET"])
    def get_all_orders():
        """
        查询所有订单，支持分页和过滤。

        查询参数:
            product_name: 产品名称（可选）
            status: 订单状态（可选）
            limit: 每页数量（默认50）
            offset: 偏移量（默认0）
        """
        product_name = request.args.get("product_name")
        status = request.args.get("status")
        limit = int(request.args.get("limit", 50))
        offset = int(request.args.get("offset", 0))

        try:
            conn = get_conn()
            try:
                with conn.cursor() as cursor:
                    # 构建查询条件
                    where_clauses = []
                    params = []

                    if product_name:
                        where_clauses.append("product_name = %s")
                        params.append(product_name)

                    if status:
                        where_clauses.append("status = %s")
                        params.append(status)

                    where_sql = " WHERE " + " AND ".join(where_clauses) if where_clauses else ""

                    # 查询总数
                    count_sql = f"SELECT COUNT(*) as total FROM pending_orders{where_sql}"
                    cursor.execute(count_sql, params)
                    total = cursor.fetchone()["total"]

                    # 查询订单列表
                    sql = f"""
                        SELECT * FROM pending_orders
                        {where_sql}
                        ORDER BY created_at DESC
                        LIMIT %s OFFSET %s
                    """
                    cursor.execute(sql, params + [limit, offset])
                    rows = cursor.fetchall()

                    orders = [
                        {
                            "id": row["id"],
                            "batch_id": row["batch_id"],
                            "product_name": row["product_name"],
                            "asset_code": row["asset_code"],
                            "target_market_value": float(row["target_market_value"]),
                            "price": float(row["price"]),
                            "contract_multiplier": row["contract_multiplier"],
                            "theoretical_quantity": float(row["theoretical_quantity"]),
                            "rounded_quantity": row["rounded_quantity"],
                            "fractional_part": float(row["fractional_part"]),
                            "final_quantity": row["final_quantity"],
                            "status": row["status"],
                            "xt_order_id": row.get("xt_order_id"),
                            "xt_status": row.get("xt_status", "not_sent"),
                            "xt_error_msg": row.get("xt_error_msg", ""),
                            "xt_traded_volume": row.get("xt_traded_volume", 0),
                            "xt_traded_price": float(row.get("xt_traded_price", 0) or 0),
                            "order_price_type": row.get("order_price_type", "limit"),
                            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                            "confirmed_at": row.get("confirmed_at").isoformat() if row.get("confirmed_at") else None,
                        }
                        for row in rows
                    ]

                    return jsonify({
                        "success": True,
                        "orders": orders,
                        "total": total,
                        "limit": limit,
                        "offset": offset
                    })

            finally:
                conn.close()

        except Exception as e:
            logger.exception("查询所有订单失败")
            return jsonify({"success": False, "message": f"服务器错误: {str(e)}"}), 500

    # -----------------------------------------------------------------------
    # GET /api/orders/pending — 查询待确认订单
    # -----------------------------------------------------------------------

    @app.route("/api/orders/pending", methods=["GET"])
    def get_pending_orders():
        """
        查询待确认订单。

        查询参数:
            batch_id: 批次ID（可选）
            product_name: 产品名称（可选）
        """
        batch_id = request.args.get("batch_id")
        product_name = request.args.get("product_name")

        try:
            if batch_id:
                orders = dao.get_pending_orders_by_batch(batch_id)
            elif product_name:
                orders = dao.get_pending_orders_by_product(product_name)
            else:
                return jsonify({"success": False, "message": "请提供 batch_id 或 product_name"}), 400

            # 查询批次的净入金汇总信息
            inflow_info = dao.get_fund_inflow_by_batch(batch_id) if batch_id else None

            resp: dict = {
                "success": True,
                "orders": [
                    {
                        "id": o.id,
                        "batch_id": o.batch_id,
                        "product_name": o.product_name,
                        "asset_code": o.asset_code,
                        "target_market_value": float(o.target_market_value),
                        "price": float(o.price),
                        "contract_multiplier": o.contract_multiplier,
                        "theoretical_quantity": float(o.theoretical_quantity),
                        "rounded_quantity": o.rounded_quantity,
                        "fractional_part": float(o.fractional_part),
                        "previous_fractional": 0.0,
                        "final_quantity": o.final_quantity,
                        "status": o.status.value,
                        "created_at": o.created_at.isoformat() if o.created_at else None
                    }
                    for o in orders
                ]
            }

            if inflow_info:
                resp["batch_id"] = inflow_info.batch_id
                resp["product_name"] = inflow_info.product_name
                resp["net_inflow"] = float(inflow_info.net_inflow)
                resp["leverage_ratio"] = float(inflow_info.leverage_ratio)
                resp["leveraged_amount"] = float(inflow_info.leveraged_amount)
                resp["input_by"] = inflow_info.input_by or ""
                resp["input_at"] = inflow_info.input_at.isoformat() if inflow_info.input_at else ""

            return jsonify(resp)

        except Exception as e:
            logger.exception("查询待确认订单失败")
            return jsonify({"success": False, "message": f"服务器错误: {str(e)}"}), 500

    # -----------------------------------------------------------------------
    # POST /api/orders/update — 更新订单数量（交易员手动调整）
    # -----------------------------------------------------------------------

    @app.route("/api/orders/update", methods=["POST"])
    def update_order_quantity():
        """
        更新订单的最终数量（交易员手动调整）。

        请求体:
        {
            "order_id": 123,
            "final_quantity": 2
        }
        """
        data = request.get_json()
        order_id = data.get("order_id")
        final_quantity = data.get("final_quantity")

        if order_id is None or final_quantity is None:
            return jsonify({"success": False, "message": "参数错误"}), 400

        try:
            dao.update_order_final_quantity(order_id, final_quantity)
            return jsonify({"success": True, "message": "订单数量已更新"})

        except Exception as e:
            logger.exception("更新订单数量失败")
            return jsonify({"success": False, "message": f"服务器错误: {str(e)}"}), 500

    # -----------------------------------------------------------------------
    # POST /api/orders/confirm — 确认订单并执行
    # -----------------------------------------------------------------------

    @app.route("/api/orders/confirm", methods=["POST"])
    def confirm_orders():
        """
        确认订单并调用迅投API执行。

        请求体:
        {
            "batch_id": "uuid",
            "confirmed_by": "交易员姓名"
        }

        返回:
        {
            "success": true,
            "executed_orders": [...],
            "failed_orders": [...]
        }
        """
        data = request.get_json()
        batch_id = data.get("batch_id")
        confirmed_by = data.get("confirmed_by", "")
        price_type_str = data.get("price_type", "limit")  # 前端传来的价格类型

        # 映射价格类型
        price_type_map = {
            "limit": OrderPriceType.LIMIT,
            "market": OrderPriceType.MARKET,
            "best": OrderPriceType.BEST_PRICE,
            "twap": OrderPriceType.TWAP,
            "vwap": OrderPriceType.VWAP,
        }
        selected_price_type = price_type_map.get(price_type_str, OrderPriceType.LIMIT)

        if not batch_id:
            return jsonify({"success": False, "message": "参数错误"}), 400

        try:
            # 1. 查询待确认订单
            orders = dao.get_pending_orders_by_batch(batch_id)
            if not orders:
                return jsonify({"success": False, "message": "批次不存在或已处理"}), 404

            # 2. 更新净入金记录状态
            dao.update_fund_inflow_status(batch_id, FundInflowStatus.CONFIRMED, confirmed_by)

            # 3. 执行订单（调用迅投API）
            executed_orders = []
            failed_orders = []

            for order in orders:
                if order.final_quantity == 0:
                    # 跳过数量为0的订单
                    dao.update_order_status(order.id, OrderStatus.CANCELLED)
                    continue

                # 记录订单价格类型到 DB
                try:
                    conn = dao._get_connection()
                    with conn.cursor() as cursor:
                        cursor.execute(
                            "UPDATE pending_orders SET order_price_type = %s WHERE id = %s",
                            (price_type_str, order.id)
                        )
                    conn.commit()
                    conn.close()
                except Exception:
                    pass  # 非关键字段，失败不阻断下单流程

                try:
                    # 获取产品配置以获取迅投账号信息
                    product = dao.get_product_by_name(order.product_name)
                    if not product:
                        raise ValueError(f"产品不存在: {order.product_name}")

                    if not product.xt_username or not product.xt_password:
                        raise ValueError(f"产品 {order.product_name} 未配置迅投账号")

                    # 获取或创建迅投连接
                    xt_manager = get_xt_connection_manager()
                    xt_service = xt_manager.get_connection(
                        username=product.xt_username,
                        password=product.xt_password,
                        account_id=product.account_id,
                        timeout=30.0,
                        dao=dao,
                    )

                    if not xt_service:
                        raise RuntimeError(f"无法连接迅投账号: {product.xt_username}")

                    # 标准化资产代码（自动添加交易所后缀）
                    normalized_code = normalize_asset_code(order.asset_code)

                    # 解析资产代码（如 "AG2606.SHFE" -> instrument="AG2606", market="SHFE"）
                    parts = normalized_code.split('.')
                    if len(parts) != 2:
                        raise ValueError(f"资产代码格式错误: {order.asset_code} (标准化后: {normalized_code})")
                    instrument, market = parts[0], parts[1]

                    # 判断资产类型和买卖方向
                    # 期货市场：CFFEX(中金所), DCE(大商所), CZCE(郑商所), SHFE(上期所), INE(能源中心)
                    is_futures = market.upper() in ['CFFEX', 'DCE', 'CZCE', 'SHFE', 'INE']

                    if order.final_quantity > 0:
                        # 正数：买入/开多
                        direction = OrderDirection.OPEN_LONG if is_futures else OrderDirection.BUY
                        quantity = order.final_quantity
                    else:
                        # 负数：卖出/平多
                        direction = OrderDirection.CLOSE_LONG if is_futures else OrderDirection.SELL
                        quantity = abs(order.final_quantity)

                    # 获取最新实时价格（而不是录入时的快照价格）
                    try:
                        live_price = float(get_latest_price(order.asset_code))
                    except ValueError:
                        live_price = float(order.price) if order.price else 0.0

                    # 构造下单请求
                    # 注意：account_id 应该使用 fund_account（真实账号ID），而不是 product.account_id（可能是用户名）
                    actual_account_id = product.fund_account if product.fund_account else product.account_id
                    order_req = OrderRequest(
                        account_id=actual_account_id,
                        asset_code=normalized_code,  # 使用标准化后的代码
                        direction=direction,
                        quantity=quantity,
                        price=live_price,
                        price_type=selected_price_type,
                        market=market,
                        instrument=instrument
                    )

                    # 调用迅投API下单
                    result = xt_service.place_order(order_req)

                    if result.success:
                        dao.update_order_status(order.id, OrderStatus.EXECUTED)
                        executed_orders.append(order.asset_code)

                        # 将迅投返回的指令ID写入数据库（同时标记 xt_status='sent'）
                        if result.order_id:
                            dao.update_order_xt_id(order.id, result.order_id)

                        # 更新留白数据
                        dao.update_fractional_share(
                            order.product_name,
                            order.asset_code,
                            order.fractional_part
                        )
                    else:
                        # SDK 调用返回失败 — 记录 xt_status='send_failed'
                        error_msg = result.error_msg or "下单失败"
                        dao.update_order_xt_send_failed(order.id, error_msg)
                        raise RuntimeError(error_msg)

                except Exception as e:
                    logger.exception(f"执行订单失败: {order.asset_code}")
                    dao.update_order_status(order.id, OrderStatus.FAILED, str(e))
                    failed_orders.append({"asset_code": order.asset_code, "error": str(e)})

            return jsonify({
                "success": True,
                "executed_orders": executed_orders,
                "failed_orders": failed_orders
            })

        except Exception as e:
            logger.exception("确认订单失败")
            return jsonify({"success": False, "message": f"服务器错误: {str(e)}"}), 500

    # ---------------------------------------------------------------------------
    # 行情健康检查 API
    # ---------------------------------------------------------------------------

    @app.route("/api/market/health", methods=["GET"])
    def market_health():
        """
        查询行情数据健康状态。
        返回 Redis 行情订阅线程状态、缓存合约列表及其最新价格，
        并与数据库配置的目标合约对比，检查是否有缺失。
        """
        try:
            detail = get_tick_cache_detail()

            # 查询数据库中配置的所有目标合约（来自 target_allocations 表）
            expected_symbols = set()
            try:
                conn = get_conn()
                with conn.cursor() as cursor:
                    cursor.execute(
                        "SELECT DISTINCT asset_code FROM target_allocations"
                    )
                    rows = cursor.fetchall()
                    for row in rows:
                        # asset_code 可能带后缀，如 ag2606.SHFE，取前缀
                        code = row['asset_code'].split('.')[0]
                        expected_symbols.add(code)
                conn.close()
            except Exception as e:
                logger.error("查询目标合约失败: %s", e)

            # 缓存中的合约集合
            cached_symbols = set(detail['symbols'].keys())

            # 计算缺失的合约
            missing_symbols = []
            for sym in expected_symbols:
                if sym not in cached_symbols:
                    missing_symbols.append(sym)

            # 总体健康状态
            is_healthy = (
                detail['subscriber_alive']
                and len(missing_symbols) == 0
                and detail['cached_count'] > 0
            )

            return jsonify({
                "success": True,
                "healthy": is_healthy,
                "subscriber_alive": detail['subscriber_alive'],
                "cached_count": detail['cached_count'],
                "symbols": detail['symbols'],
                "expected_symbols": sorted(expected_symbols),
                "missing_symbols": missing_symbols,
            })

        except Exception as e:
            logger.exception("行情健康检查异常")
            return jsonify({"success": False, "message": str(e)}), 500

    # ---------------------------------------------------------------------------
    # 迅投查询 API
    # ---------------------------------------------------------------------------

    @app.route("/api/xt/products", methods=["GET"])
    def xt_query_products():
        """
        查询迅投系统中的产品列表

        返回:
        {
            "success": true,
            "products": [
                {
                    "product_id": 1,
                    "product_name": "产品A",
                    "product_code": "PROD_A",
                    "total_net_value": 1000000.0
                }
            ]
        }
        """
        try:
            xt_query = XtQueryService()

            # 连接迅投服务器（单例模式，只连接一次）
            if not xt_query.connect(timeout=30.0):
                return jsonify({
                    "success": False,
                    "message": "连接迅投服务器失败"
                }), 500

            # 查询产品列表
            products = xt_query.query_products(timeout=10.0)

            # 不断开连接，保持复用

            # 转换为字典列表
            product_list = [
                {
                    "product_id": p.product_id,
                    "product_name": p.product_name,
                    "product_code": p.product_code,
                    "total_net_value": p.total_net_value
                }
                for p in products
            ]

            return jsonify({
                "success": True,
                "products": product_list
            })

        except Exception as e:
            logger.exception("查询迅投产品异常")
            return jsonify({"success": False, "message": f"服务器错误: {str(e)}"}), 500

    @app.route("/api/xt/orders", methods=["GET"])
    def xt_reconcile_orders():
        """
        手动对账接口 — 从迅投拉取当日指令，与 DB 精确匹配并更新状态

        查询参数:
            product_name: 产品名称（必选）

        执行逻辑:
            1. 调一次 reqCommandsInfoSync() 拿到当日全部指令
            2. 逐笔与 DB 中 xt_status='sent'/'running' 的订单按 xt_order_id 精确匹配
            3. 更新 DB 中的 xt_status 和 xt_error_msg
            4. 返回对账摘要
        """
        try:
            product_name = request.args.get("product_name")
            if not product_name:
                return jsonify({"success": False, "message": "请指定产品名称 (product_name)"}), 400

            product = dao.get_product_by_name(product_name)
            if not product:
                return jsonify({"success": False, "message": f"产品 {product_name} 不存在"}), 404

            if not product.xt_username or not product.xt_password:
                return jsonify({"success": False, "message": f"产品 {product_name} 未配置迅投账号"}), 400

            # 获取迅投连接
            xt_manager = get_xt_connection_manager()
            xt_service = xt_manager.get_connection(
                username=product.xt_username,
                password=product.xt_password,
                account_id=product.account_id,
                timeout=30.0,
                dao=dao,
            )
            if not xt_service:
                return jsonify({"success": False, "message": f"无法连接迅投账号: {product.xt_username}"}), 500

            actual_account_id = product.fund_account if product.fund_account else product.account_id

            # 1. 拉取迅投当日全部指令
            instructions = xt_service.query_instructions(account_id=actual_account_id)
            logger.info("对账: 迅投返回 %d 条指令 (account_id=%s)", len(instructions), actual_account_id)

            # 构建 order_id → instruction 索引
            instr_map = {}
            for instr in instructions:
                instr_map[instr["order_id"]] = instr

            # 2. 从 DB 取出未终结的订单
            pending_statuses = ["sent", "running"]
            pending_orders = dao.get_orders_by_xt_status(pending_statuses)

            # 3. 逐笔精确匹配并更新
            # 指令状态字符串 → 我们的 XtStatus 映射
            _INSTR_STATUS_MAP = {
                "OCS_FINISHED": "filled",
                "OCS_RUNNING": "running",
                "OCS_STOPPED": "stopped",
                "OCS_REJECTED": "rejected",
                "OCS_CHECKING": "running",
                "OCS_APPROVING": "running",
                "OCS_CANCELING": "cancelled",
            }

            updated = 0
            not_found = 0
            already_ok = 0

            for order in pending_orders:
                if order.xt_order_id is None:
                    continue

                matched = instr_map.get(order.xt_order_id)
                if matched:
                    new_status = _INSTR_STATUS_MAP.get(matched["status"], "sent")
                    error_msg = matched.get("error_msg", "")

                    if new_status != order.xt_status or error_msg != (order.xt_error_msg or ""):
                        dao.update_order_xt_status(
                            xt_order_id=order.xt_order_id,
                            xt_status=new_status,
                            xt_error_msg=error_msg,
                        )
                        updated += 1
                        logger.info(
                            "对账更新: xt_order_id=%s, %s → %s, error=%s",
                            order.xt_order_id, order.xt_status, new_status, error_msg,
                        )
                    else:
                        already_ok += 1
                else:
                    # 迅投没有这笔指令 — 保持不变
                    not_found += 1

            return jsonify({
                "success": True,
                "message": f"对账完成: 更新 {updated} 笔, 一致 {already_ok} 笔, 未找到 {not_found} 笔",
                "reconcile_summary": {
                    "xt_instructions_count": len(instructions),
                    "pending_orders_count": len(pending_orders),
                    "updated": updated,
                    "already_ok": already_ok,
                    "not_found": not_found,
                },
                "account_id": actual_account_id,
                "product_name": product_name,
            })

        except Exception as e:
            logger.exception("对账异常")
            return jsonify({"success": False, "message": f"服务器错误: {str(e)}"}), 500

    @app.route("/api/xt/debug_query")
    def xt_debug_query():
        """
        诊断接口：直接用多种方式查询迅投订单，返回原始SDK结果
        参数: product_name, order_id (可选，指定单笔查询)
        """
        try:
            product_name = request.args.get("product_name")
            target_order_id = request.args.get("order_id", type=int)
            if not product_name:
                return jsonify({"success": False, "message": "请指定 product_name"}), 400

            product = dao.get_product_by_name(product_name)
            if not product:
                return jsonify({"success": False, "message": f"产品 {product_name} 不存在"}), 404

            xt_manager = get_xt_connection_manager()
            xt_service = xt_manager.get_connection(
                username=product.xt_username,
                password=product.xt_password,
                account_id=product.account_id,
                timeout=30.0
            )
            if not xt_service:
                return jsonify({"success": False, "message": "无法连接迅投"}), 500

            actual_account_id = product.fund_account if product.fund_account else product.account_id
            account_key = xt_service._account_ready.get(actual_account_id)

            result = {
                "account_id": actual_account_id,
                "account_key": account_key[:30] + "..." if account_key else None,
                "logined": xt_service._logined,
                "account_ready_keys": list(xt_service._account_ready.keys()),
            }

            # 方法1: reqOrderDetailSync (当日委托)
            try:
                from XtTraderPyApi import XtError as _XtError
                error = _XtError(0, "")
                orders = xt_service._api.reqOrderDetailSync(actual_account_id, error, account_key)
                result["method1_reqOrderDetailSync"] = {
                    "isSuccess": error.isSuccess(),
                    "errorMsg": error.errorMsg(),
                    "count": len(orders) if orders else 0,
                    "type": type(orders).__name__,
                }
                if orders:
                    result["method1_first_order_attrs"] = {}
                    for attr in dir(orders[0]):
                        if attr.startswith('m_'):
                            try:
                                val = getattr(orders[0], attr)
                                result["method1_first_order_attrs"][attr] = str(val)
                            except:
                                pass
            except Exception as e:
                result["method1_error"] = str(e)

            # 方法2: reqOrderDetailSyncByOrderID (按指令ID查)
            if target_order_id:
                try:
                    error2 = _XtError(0, "")
                    orders2 = xt_service._api.reqOrderDetailSyncByOrderID(
                        actual_account_id, error2, target_order_id, account_key
                    )
                    result["method2_reqByOrderID"] = {
                        "order_id": target_order_id,
                        "isSuccess": error2.isSuccess(),
                        "errorMsg": error2.errorMsg(),
                        "count": len(orders2) if orders2 else 0,
                    }
                    if orders2:
                        result["method2_first_attrs"] = {}
                        for attr in dir(orders2[0]):
                            if attr.startswith('m_'):
                                try:
                                    val = getattr(orders2[0], attr)
                                    result["method2_first_attrs"][attr] = str(val)
                                except:
                                    pass
                except Exception as e:
                    result["method2_error"] = str(e)

            # 方法3: reqDealDetailSync (成交明细)
            try:
                error3 = _XtError(0, "")
                deals = xt_service._api.reqDealDetailSync(actual_account_id, error3, account_key)
                result["method3_reqDealDetail"] = {
                    "isSuccess": error3.isSuccess(),
                    "errorMsg": error3.errorMsg(),
                    "count": len(deals) if deals else 0,
                }
                if deals:
                    result["method3_first_deal_attrs"] = {}
                    for attr in dir(deals[0]):
                        if attr.startswith('m_'):
                            try:
                                val = getattr(deals[0], attr)
                                result["method3_first_deal_attrs"][attr] = str(val)
                            except:
                                pass
            except Exception as e:
                result["method3_error"] = str(e)

            # 方法4: reqCommandsInfoSync (指令查询 - 不需要account_id)
            try:
                error4 = _XtError(0, "")
                cmds = xt_service._api.reqCommandsInfoSync(error4)
                result["method4_reqCommandsInfo"] = {
                    "isSuccess": error4.isSuccess(),
                    "errorMsg": error4.errorMsg(),
                    "count": len(cmds) if cmds else 0,
                }
                if cmds:
                    # 只取最近10条指令
                    cmd_list = []
                    for cmd in cmds[-10:]:
                        cmd_info = {}
                        for attr in dir(cmd):
                            if attr.startswith('m_'):
                                try:
                                    val = getattr(cmd, attr)
                                    cmd_info[attr] = str(val)
                                except:
                                    pass
                        cmd_list.append(cmd_info)
                    result["method4_recent_commands"] = cmd_list
            except Exception as e:
                result["method4_error"] = str(e)

            return jsonify({"success": True, "debug": result})

        except Exception as e:
            logger.exception("诊断查询异常")
            return jsonify({"success": False, "message": str(e)}), 500

    # ---------------------------------------------------------------------------
    # 迅投下单 API
    # ---------------------------------------------------------------------------

    @app.route("/api/xt/place_order", methods=["POST"])
    def xt_place_order():
        """
        迅投下单接口

        请求体:
        {
            "account_id": "90102870",
            "asset_code": "600519.SH",
            "direction": "buy",  // buy 或 sell
            "quantity": 100,
            "price": 1850.50,  // 限价单必填，市价单可为0
            "price_type": "limit",  // limit/market/best
            "business_type": "STOCK"  // STOCK/FUTURES
        }
        """
        try:
            data = request.get_json()

            # 参数验证
            required_fields = ["account_id", "asset_code", "direction", "quantity"]
            for field in required_fields:
                if field not in data:
                    return jsonify({"success": False, "message": f"缺少必填字段: {field}"}), 400

            # 构造下单请求
            direction = OrderDirection.BUY if data["direction"].lower() == "buy" else OrderDirection.SELL
            price_type_str = data.get("price_type", "limit").lower()
            price_type_map = {
                "limit": OrderPriceType.LIMIT,
                "market": OrderPriceType.MARKET,
                "best": OrderPriceType.BEST_PRICE,
            }
            price_type = price_type_map.get(price_type_str, OrderPriceType.LIMIT)

            order_req = OrderRequest(
                account_id=data["account_id"],
                asset_code=data["asset_code"],
                direction=direction,
                quantity=int(data["quantity"]),
                price=float(data.get("price", 0.0)),
                price_type=price_type
            )

            # 获取服务实例并连接
            xt_service = XtOrderService()
            if not xt_service._logined:
                logger.info("首次下单，连接迅投服务器...")
                if not xt_service.connect(timeout=30.0):
                    return jsonify({"success": False, "message": "连接迅投服务器失败"}), 500

            # 执行下单
            result = xt_service.place_order(order_req, timeout=10.0)

            if result.success:
                return jsonify({
                    "success": True,
                    "order_id": result.order_id,
                    "message": "下单成功"
                })
            else:
                return jsonify({
                    "success": False,
                    "message": result.error_msg
                }), 400

        except Exception as e:
            logger.exception("下单接口异常")
            return jsonify({"success": False, "message": f"服务器错误: {str(e)}"}), 500

    # ---------------------------------------------------------------------------
    # 调试接口：查看行情缓存
    # ---------------------------------------------------------------------------

    @app.route("/api/debug/market_cache", methods=["GET"])
    def debug_market_cache():
        """查看当前行情缓存（调试用）"""
        with _tick_cache_lock:
            cache_data = {
                symbol: {
                    "last_price": float(tick.last_price),
                    "ask1": float(tick.ask_prices[0]) if tick.ask_prices[0] > 0 else None,
                    "bid1": float(tick.bid_prices[0]) if tick.bid_prices[0] > 0 else None,
                    "timestamp": tick.timestamp.isoformat() if tick.timestamp else None
                }
                for symbol, tick in _tick_cache.items()
            }
        return jsonify({
            "success": True,
            "cache_size": len(cache_data),
            "data": cache_data
        })

    return app
