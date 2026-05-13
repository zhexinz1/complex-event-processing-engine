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

    # 净入金流程
    POST /api/fund/inflow      提交净入金并计算订单
    GET  /api/orders/pending   查询待确认订单
    POST /api/orders/confirm   确认订单并执行
    POST /api/orders/update    更新订单数量

    # 回测
    GET  /api/backtests/presets 获取可回测预设策略列表
    GET  /api/backtests/history 获取历史回测日志
    POST /api/backtests/run     运行预设策略回测
    GET  /api/stocks/search     搜索本地 A 股股票索引
    GET  /                     前端大屏页面
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from decimal import Decimal
import uuid
from typing import Any, cast

import pymysql
import pymysql.cursors
from flask import (
    Flask,
    Response,
    jsonify,
    request,
    send_from_directory,
    stream_with_context,
)

from backtest.preset_strategies import (
    PRESET_STRATEGIES,
    run_preset_backtest,
    serialize_backtest_result,
)
from backtest.trade_log import list_backtest_trade_logs, read_backtest_trade_log
from data_provider import search_stocks

from database.config import (
    CONNECT_TIMEOUT_SECONDS,
    DB_CONFIG as DATABASE_CONFIG,
    READ_TIMEOUT_SECONDS,
    WRITE_TIMEOUT_SECONDS,
)
from database.dao import DatabaseDAO
from database.models import (
    PendingOrder,
    OrderStatus,
    FundInflow,
    FundInflowStatus,
    UserSignalDefinition,
    UserSignalStatus,
)
from adapters.xuntou import XtOrderService, OrderRequest, OrderDirection, OrderPriceType
from adapters.xuntou import XtQueryService
from adapters.xuntou import get_xt_connection_manager
from adapters.price_service import get_latest_price, get_tick_cache_detail
from adapters.contract_config import get_contract_multiplier, normalize_asset_code
from cep.core.context import get_local_context_reference
from signals import (
    LiveSignalMonitor,
    SignalContractValidator,
    load_signal_class,
    run_user_signal_backtest,
)
from backtest.broker import ExecutionTiming

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 数据库连接配置
# ---------------------------------------------------------------------------

DB_CONFIG: dict[str, Any] = {
    "host": DATABASE_CONFIG.host,
    "port": DATABASE_CONFIG.port,
    "database": DATABASE_CONFIG.database,
    "user": DATABASE_CONFIG.user,
    "password": DATABASE_CONFIG.password,
    "charset": DATABASE_CONFIG.charset,
    "cursorclass": pymysql.cursors.DictCursor,
    "autocommit": False,
    "connect_timeout": CONNECT_TIMEOUT_SECONDS,
    "read_timeout": READ_TIMEOUT_SECONDS,
    "write_timeout": WRITE_TIMEOUT_SECONDS,
}

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

CREATE_USER_SIGNALS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS user_signal_definitions (
    id           INT PRIMARY KEY AUTO_INCREMENT,
    name         VARCHAR(120) NOT NULL,
    symbols      JSON         NOT NULL,
    bar_freq     VARCHAR(20)  NOT NULL DEFAULT '1m',
    source_code  MEDIUMTEXT   NOT NULL,
    status       VARCHAR(20)  NOT NULL DEFAULT 'disabled',
    created_by   VARCHAR(100) NOT NULL DEFAULT 'system',
    created_at   TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    updated_at   TIMESTAMP    DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""

FRONTEND_DIST_DIR = Path(__file__).parent.parent / "frontend" / "dist"

# 全局 DAO 实例（在 create_app 中初始化）
dao: DatabaseDAO = cast(DatabaseDAO, None)
live_signal_monitor = LiveSignalMonitor()


def is_frontend_built() -> bool:
    return (FRONTEND_DIST_DIR / "index.html").exists()


def get_frontend_dir() -> Path:
    """Return the compiled Vite app directory."""
    return FRONTEND_DIST_DIR


def frontend_setup_response() -> Any:
    message = {
        "success": False,
        "message": (
            "Frontend bundle not found. Run `npm install` and `npm run frontend:build` "
            "from the project root, then reload this page."
        ),
    }
    return jsonify(message), 503


# 全局 DAO 实例
dao = None

def get_conn() -> Any:
    global dao
    if dao is not None:
        return dao._get_connection()
    return pymysql.connect(**DB_CONFIG)


def init_db() -> None:
    """建表（幂等），应用启动时调用一次。"""
    # 初始化 DAO，这样 get_conn 就能利用连接池
    global dao
    if dao is None:
        dao = DatabaseDAO()
        logger.info("DatabaseDAO initialized.")

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(CREATE_TABLE_SQL)
            cur.execute(CREATE_ASSETS_TABLE_SQL)
            cur.execute(CREATE_USER_SIGNALS_TABLE_SQL)
        conn.commit()
    logger.info(
        "DB tables target_allocations, allowed_assets and user_signal_definitions ready."
    )


def _serialize_user_signal(signal: UserSignalDefinition) -> dict[str, Any]:
    return {
        "id": signal.id,
        "name": signal.name,
        "symbols": signal.symbols,
        "bar_freq": signal.bar_freq,
        "source_code": signal.source_code,
        "status": signal.status.value,
        "created_by": signal.created_by,
        "created_at": signal.created_at.isoformat() if signal.created_at else None,
        "updated_at": signal.updated_at.isoformat() if signal.updated_at else None,
    }


def _parse_signal_payload(
    body: dict[str, Any], existing: UserSignalDefinition | None = None
) -> UserSignalDefinition:
    raw_symbols = body.get("symbols", existing.symbols if existing else [])
    if isinstance(raw_symbols, str):
        symbols = [part.strip() for part in raw_symbols.split(",") if part.strip()]
    else:
        symbols = [str(part).strip() for part in raw_symbols or [] if str(part).strip()]
    status_text = str(
        body.get(
            "status",
            existing.status.value if existing else UserSignalStatus.DISABLED.value,
        )
    )
    return UserSignalDefinition(
        id=existing.id if existing else None,
        name=str(body.get("name", existing.name if existing else "")).strip(),
        symbols=symbols,
        bar_freq=str(
            body.get("bar_freq", existing.bar_freq if existing else "1m")
        ).strip(),
        source_code=str(
            body.get("source_code", existing.source_code if existing else "")
        ),
        status=UserSignalStatus(status_text),
        created_by=str(
            body.get("created_by", existing.created_by if existing else "system")
        ).strip()
        or "system",
        created_at=existing.created_at if existing else None,
        updated_at=existing.updated_at if existing else None,
    )


def _reload_live_signal_monitor() -> None:
    if dao is None:
        return
    enabled = dao.list_user_signals(UserSignalStatus.ENABLED)
    live_signal_monitor.load_definitions(enabled)


def _parse_bool_arg(value: Any, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"无法解析布尔值: {value}")


def _parse_execution_timing(
    value: Any, default: ExecutionTiming = "next_bar"
) -> ExecutionTiming:
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in {"current_bar", "next_bar"}:
        return cast(ExecutionTiming, text)
    raise ValueError(
        f"无法解析 execution_timing: {value}，可选值为 current_bar / next_bar"
    )


# ---------------------------------------------------------------------------
# Flask 应用工厂
# ---------------------------------------------------------------------------


def create_app() -> Flask:
    app = Flask(__name__, static_folder=None)

    # 初始化数据库和 DAO
    init_db()
    _reload_live_signal_monitor()
    live_signal_monitor.start_redis_subscriber(
        redis_url=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
        channel=os.environ.get("CEP_REDIS_CHANNEL", "cep_events"),
    )

    # -----------------------------------------------------------------------
    # 前端静态文件
    # -----------------------------------------------------------------------

    @app.route("/")
    def index():
        if not is_frontend_built():
            return frontend_setup_response()
        return send_from_directory(str(get_frontend_dir()), "index.html")

    @app.route("/<path:filename>")
    def static_files(filename: str):
        if not is_frontend_built():
            return frontend_setup_response()
        # 尝试直接提供静态文件（JS/CSS/图片等）
        frontend_dir = get_frontend_dir()
        file_path = frontend_dir / filename
        if file_path.is_file():
            return send_from_directory(str(frontend_dir), filename)
        # 非 API 路径且文件不存在 → SPA fallback 到 index.html
        return send_from_directory(str(frontend_dir), "index.html")

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
                    rows = cast(list[dict[str, Any]], cur.fetchall())
        except Exception as e:
            return jsonify(
                {"success": False, "message": f"数据库连接失败: {e}", "data": []}
            ), 503

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

        # 校验合约代码格式：不允许带交易所后缀（股票 .SH / .SZ 除外）
        asset_code = (body["asset_code"] or "").strip()
        is_stock = asset_code.endswith(".SH") or asset_code.endswith(".SZ")
        if not is_stock and "." in asset_code:
            return jsonify(
                {
                    "success": False,
                    "message": f"期货合约代码不应包含交易所后缀，请输入纯合约代码 (如 {asset_code.split('.')[0]})",
                }
            ), 400

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
                    cur.execute(
                        "DELETE FROM target_allocations WHERE id = %s", (record_id,)
                    )
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
                    rows = cast(list[dict[str, Any]], cur.fetchall())
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
            return jsonify(
                {
                    "success": True,
                    "products": [
                        {
                            "product_name": p.product_name,
                            "leverage_ratio": float(p.leverage_ratio),
                            "fund_account": p.fund_account,
                            "xt_username": p.xt_username,
                            "xt_password": p.xt_password,
                            "status": p.status.value,
                        }
                        for p in products
                    ],
                }
            )
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
        fund_account = data.get("fund_account", "").strip()
        xt_username = data.get("xt_username", "").strip() or None
        xt_password = data.get("xt_password", "").strip() or None

        if not product_name or not leverage_ratio or not fund_account:
            return jsonify({"success": False, "message": "参数不完整"}), 400

        try:
            # 检查产品是否已存在
            existing = dao.get_product_by_name(product_name)
            if existing:
                return jsonify(
                    {"success": False, "message": f"产品 {product_name} 已存在"}
                ), 409

            # 插入数据库
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO products (product_name, leverage_ratio, fund_account, xt_username, xt_password, status)
                        VALUES (%s, %s, %s, %s, %s, 'active')
                        """,
                        (
                            product_name,
                            leverage_ratio,
                            fund_account,
                            xt_username,
                            xt_password,
                        ),
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

            if "fund_account" in data:
                updates.append("fund_account = %s")
                params.append(data["fund_account"])

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
                    rows = cast(list[dict[str, Any]], cur.fetchall())
        except Exception as e:
            return jsonify(
                {"success": False, "message": f"数据库连接失败: {e}", "data": []}
            ), 503
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

        # 校验：合约代码不能带交易所后缀（如 ".SHFE"）
        # 但如果是股票，则必须带 .SH 或 .SZ 后缀
        is_stock = asset_code.endswith(".SH") or asset_code.endswith(".SZ")
        
        if not is_stock:
            if "." in asset_code:
                return jsonify(
                    {
                        "success": False,
                        "message": f"期货合约代码不应包含交易所后缀 (如 .SHFE)，请输入纯合约代码 (如 {asset_code.split('.')[0]})",
                    }
                ), 400

            # 校验：期货合约代码应为字母+数字格式
            import re

            if not re.match(r"^[a-zA-Z]+\d+$", asset_code):
                return jsonify(
                    {
                        "success": False,
                        "message": f"期货合约代码格式不正确: {asset_code}，应为品种+月份格式（如 ag2606、rb2510）",
                    }
                ), 400

        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO allowed_assets (asset_code) VALUES (%s)",
                        (asset_code,),
                    )
                conn.commit()
        except pymysql.err.IntegrityError:
            return jsonify(
                {"success": False, "message": f"资产代码 {asset_code} 已存在"}
            ), 409
        except Exception as e:
            return jsonify({"success": False, "message": f"数据库错误: {e}"}), 503

        return jsonify(
            {"success": True, "message": f"已添加资产代码 {asset_code}"}
        ), 201

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
                        "DELETE FROM allowed_assets WHERE asset_code = %s",
                        (asset_code,),
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

            return jsonify(
                {
                    "success": True,
                    "inflows": [
                        {
                            "batch_id": inf.batch_id,
                            "product_name": inf.product_name,
                            "net_inflow": str(inf.net_inflow),
                            "leverage_ratio": str(inf.leverage_ratio),
                            "leveraged_amount": str(inf.leveraged_amount),
                            "input_by": inf.input_by or "",
                            "input_at": inf.input_at.isoformat()
                            if inf.input_at
                            else "",
                            "confirmed_by": inf.confirmed_by or "",
                            "confirmed_at": inf.confirmed_at.isoformat()
                            if inf.confirmed_at
                            else "",
                            "status": inf.status.value,
                        }
                        for inf in inflows
                    ],
                }
            )

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
            "input_by": "周哲鑫"
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
                return jsonify(
                    {"success": False, "message": f"产品 {product_name} 不存在"}
                ), 404

            leverage_ratio = product.leverage_ratio

            # 2. 查询目标权重配置（从 target_allocations 表，只取最新日期）
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT asset_code, weight_ratio
                        FROM target_allocations
                        WHERE product_name = %s
                          AND target_date = (
                              SELECT MAX(target_date)
                              FROM target_allocations
                              WHERE product_name = %s
                          )
                        """,
                        (product_name, product_name),
                    )
                    rows = cur.fetchall()

            if not rows:
                return jsonify(
                    {
                        "success": False,
                        "message": f"产品 {product_name} 没有配置目标权重",
                    }
                ), 404

            target_weights = {
                row["asset_code"]: Decimal(str(row["weight_ratio"])) for row in rows
            }

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
                previous_fractionals[asset_code] = dao.get_fractional_share(
                    product_name, asset_code
                )

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
                previous_fractionals=previous_fractionals,
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
                status=FundInflowStatus.PENDING,
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
                    status=OrderStatus.PENDING,
                )
                dao.create_pending_order(pending_order)

            # 9. 返回结果
            return jsonify(
                {
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
                            "final_quantity": o.final_quantity,
                        }
                        for o in orders
                    ],
                }
            )

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

                    where_sql = (
                        " WHERE " + " AND ".join(where_clauses) if where_clauses else ""
                    )

                    # 查询总数
                    count_sql = (
                        f"SELECT COUNT(*) as total FROM pending_orders{where_sql}"
                    )
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
                            "xt_traded_price": float(
                                row.get("xt_traded_price", 0) or 0
                            ),
                            "order_price_type": row.get("order_price_type", "limit"),
                            "created_at": row["created_at"].isoformat()
                            if row["created_at"]
                            else None,
                            "confirmed_at": row.get("confirmed_at").isoformat()
                            if row.get("confirmed_at")
                            else None,
                        }
                        for row in rows
                    ]

                    return jsonify(
                        {
                            "success": True,
                            "orders": orders,
                            "total": total,
                            "limit": limit,
                            "offset": offset,
                        }
                    )

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
                return jsonify(
                    {"success": False, "message": "请提供 batch_id 或 product_name"}
                ), 400

            # 查询批次的净入金汇总信息
            inflow_info = dao.get_fund_inflow_by_batch(batch_id) if batch_id else None

            # 批次已确认执行后，过滤掉手数为0的订单（无需展示）
            batch_confirmed = (
                inflow_info is not None
                and inflow_info.status == FundInflowStatus.CONFIRMED
            )
            if batch_confirmed:
                orders = [o for o in orders if o.final_quantity != 0]

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
                        "xt_order_id": o.xt_order_id,
                        "xt_status": o.xt_status,
                        "xt_error_msg": o.xt_error_msg,
                        "xt_traded_volume": o.xt_traded_volume,
                        "xt_traded_price": float(o.xt_traded_price) if o.xt_traded_price else 0.0,
                        "order_price_type": o.order_price_type,
                        "created_at": o.created_at.isoformat()
                        if o.created_at
                        else None,
                    }
                    for o in orders
                ],
            }

            if inflow_info:
                resp["batch_id"] = inflow_info.batch_id
                resp["product_name"] = inflow_info.product_name
                resp["net_inflow"] = float(inflow_info.net_inflow)
                resp["leverage_ratio"] = float(inflow_info.leverage_ratio)
                resp["leveraged_amount"] = float(inflow_info.leveraged_amount)
                resp["input_by"] = inflow_info.input_by or ""
                resp["input_at"] = (
                    inflow_info.input_at.isoformat() if inflow_info.input_at else ""
                )
                resp["status"] = inflow_info.status.value

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
        更新订单的最终数量和价格（交易员手动调整）。

        请求体:
        {
            "order_id": 123,
            "final_quantity": 2,
            "price": 37000.00
        }
        """
        data = request.get_json()
        order_id = data.get("order_id")
        final_quantity = data.get("final_quantity")
        price = data.get("price")

        if order_id is None or final_quantity is None:
            return jsonify({"success": False, "message": "参数错误"}), 400

        try:
            if price is not None:
                dao.update_order_final_quantity_and_price(order_id, final_quantity, float(price))
            else:
                dao.update_order_final_quantity(order_id, final_quantity)
            return jsonify({"success": True, "message": "订单已更新"})

        except Exception as e:
            logger.exception("更新订单失败")
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
            dao.update_fund_inflow_status(
                batch_id, FundInflowStatus.CONFIRMED, confirmed_by
            )

            # 3. 执行订单（调用迅投API）
            executed_orders = []
            failed_orders = []

            for order in orders:
                order_id = order.id
                if order_id is None:
                    failed_orders.append(
                        {"asset_code": order.asset_code, "error": "订单缺少数据库ID"}
                    )
                    continue

                if order.final_quantity == 0:
                    # 跳过数量为0的订单
                    dao.update_order_status(order_id, OrderStatus.CANCELLED)
                    continue

                # 记录订单价格类型到 DB
                try:
                    conn = dao._get_connection()
                    with conn.cursor() as cursor:
                        cursor.execute(
                            "UPDATE pending_orders SET order_price_type = %s WHERE id = %s",
                            (price_type_str, order_id),
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
                        timeout=30.0,
                        dao=dao,
                    )

                    if not xt_service:
                        raise RuntimeError(f"无法连接迅投账号: {product.xt_username}")

                    # 标准化资产代码（自动添加交易所后缀）
                    normalized_code = normalize_asset_code(order.asset_code)

                    # 解析资产代码（如 "AG2606.SHFE" -> instrument="AG2606", market="SHFE"）
                    parts = normalized_code.split(".")
                    if len(parts) != 2:
                        raise ValueError(
                            f"资产代码格式错误: {order.asset_code} (标准化后: {normalized_code})"
                        )
                    instrument, market = parts[0], parts[1]

                    # 判断资产类型和买卖方向
                    # 期货市场：CFFEX(中金所), DCE(大商所), CZCE(郑商所), SHFE(上期所), INE(能源中心)
                    is_futures = market.upper() in [
                        "CFFEX",
                        "DCE",
                        "CZCE",
                        "SHFE",
                        "INE",
                    ]

                    if order.final_quantity > 0:
                        # 正数：买入/开多
                        direction = (
                            OrderDirection.OPEN_LONG
                            if is_futures
                            else OrderDirection.BUY
                        )
                        quantity = order.final_quantity
                    else:
                        # 负数：卖出/平多
                        direction = (
                            OrderDirection.CLOSE_LONG
                            if is_futures
                            else OrderDirection.SELL
                        )
                        quantity = abs(order.final_quantity)

                    # 对于限价单，直接使用数据库中保存的 price（用户可能在前端修改了）
                    # 对于市价单等，获取最新实时价格作为参考价格
                    if selected_price_type == OrderPriceType.LIMIT:
                        live_price = float(order.price) if order.price else 0.0
                    else:
                        try:
                            live_price = float(get_latest_price(order.asset_code))
                        except ValueError:
                            live_price = float(order.price) if order.price else 0.0

                    # 构造下单请求
                    order_req = OrderRequest(
                        account_id=product.fund_account,
                        asset_code=normalized_code,  # 使用标准化后的代码
                        direction=direction,
                        quantity=quantity,
                        price=live_price,
                        price_type=selected_price_type,
                        market=market,
                        instrument=instrument,
                    )

                    # 调用迅投API下单
                    result = xt_service.place_order(order_req)

                    if result.success:
                        # 仅标记为"已确认提交"，而非"已执行"
                        # 真正的终态（EXECUTED/FAILED/CANCELLED）由回调/对账更新
                        dao.update_order_status(order_id, OrderStatus.CONFIRMED)
                        executed_orders.append(order.asset_code)

                        # 将迅投返回的指令ID写入数据库（同时标记 xt_status='sent'）
                        if result.order_id:
                            dao.update_order_xt_id(order_id, result.order_id)

                        # 更新留白数据
                        dao.update_fractional_share(
                            order.product_name, order.asset_code, order.fractional_part
                        )
                    else:
                        # SDK 调用返回失败 — 记录 xt_status='send_failed'
                        error_msg = result.error_msg or "下单失败"
                        dao.update_order_xt_send_failed(order_id, error_msg)
                        raise RuntimeError(error_msg)

                except Exception as e:
                    logger.exception(f"执行订单失败: {order.asset_code}")
                    dao.update_order_status(order_id, OrderStatus.FAILED, str(e))
                    failed_orders.append(
                        {"asset_code": order.asset_code, "error": str(e)}
                    )

            return jsonify(
                {
                    "success": True,
                    "executed_orders": executed_orders,
                    "failed_orders": failed_orders,
                }
            )

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
                    cursor.execute("SELECT DISTINCT asset_code FROM target_allocations")
                    rows = cursor.fetchall()
                    for row in rows:
                        # 期货 asset_code 可能带后缀，如 ag2606.SHFE，取前缀
                        # 股票 asset_code 必须保留后缀，如 563360.SH
                        code = row["asset_code"]
                        if not (code.endswith(".SH") or code.endswith(".SZ")):
                            code = code.split(".")[0]
                        expected_symbols.add(code)
                conn.close()
            except Exception as e:
                logger.error("查询目标合约失败: %s", e)

            # 缓存中的合约集合
            cached_symbols = set(detail["symbols"].keys())

            # 计算缺失的合约
            missing_symbols = []
            for sym in expected_symbols:
                if sym not in cached_symbols:
                    missing_symbols.append(sym)

            # 总体健康状态
            is_healthy = (
                detail["subscriber_alive"]
                and len(missing_symbols) == 0
                and detail["cached_count"] > 0
            )

            return jsonify(
                {
                    "success": True,
                    "healthy": is_healthy,
                    "subscriber_alive": detail["subscriber_alive"],
                    "cached_count": detail["cached_count"],
                    "symbols": detail["symbols"],
                    "expected_symbols": sorted(expected_symbols),
                    "missing_symbols": missing_symbols,
                }
            )

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
                return jsonify({"success": False, "message": "连接迅投服务器失败"}), 500

            # 查询产品列表
            products = xt_query.query_products()

            # 不断开连接，保持复用

            # 转换为字典列表
            product_list = [
                {
                    "product_id": p.product_id,
                    "product_name": p.product_name,
                    "product_code": p.product_code,
                    "total_net_value": p.total_net_value,
                }
                for p in products
            ]

            return jsonify({"success": True, "products": product_list})

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
                return jsonify(
                    {"success": False, "message": "请指定产品名称 (product_name)"}
                ), 400

            product = dao.get_product_by_name(product_name)
            if not product:
                return jsonify(
                    {"success": False, "message": f"产品 {product_name} 不存在"}
                ), 404

            if not product.xt_username or not product.xt_password:
                return jsonify(
                    {"success": False, "message": f"产品 {product_name} 未配置迅投账号"}
                ), 400

            # 获取迅投连接
            xt_manager = get_xt_connection_manager()
            xt_service = xt_manager.get_connection(
                username=product.xt_username,
                password=product.xt_password,
                timeout=30.0,
                dao=dao,
            )
            if not xt_service:
                return jsonify(
                    {
                        "success": False,
                        "message": f"无法连接迅投账号: {product.xt_username}",
                    }
                ), 500

            # 1. 拉取迅投当日全部指令
            instructions = xt_service.query_instructions(account_id=product.fund_account)
            logger.info(
                "对账: 迅投返回 %d 条指令 (account_id=%s)",
                len(instructions),
                product.fund_account,
            )

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

                    if new_status != order.xt_status or error_msg != (
                        order.xt_error_msg or ""
                    ):
                        dao.update_order_xt_status(
                            xt_order_id=order.xt_order_id,
                            xt_status=new_status,
                            xt_error_msg=error_msg,
                        )
                        updated += 1
                        logger.info(
                            "对账更新: xt_order_id=%s, %s → %s, error=%s",
                            order.xt_order_id,
                            order.xt_status,
                            new_status,
                            error_msg,
                        )
                    else:
                        already_ok += 1
                else:
                    # 迅投没有这笔指令 — 保持不变
                    not_found += 1

            return jsonify(
                {
                    "success": True,
                    "message": f"对账完成: 更新 {updated} 笔, 一致 {already_ok} 笔, 未找到 {not_found} 笔",
                    "reconcile_summary": {
                        "xt_instructions_count": len(instructions),
                        "pending_orders_count": len(pending_orders),
                        "updated": updated,
                        "already_ok": already_ok,
                        "not_found": not_found,
                    },
                    "account_id": product.fund_account,
                    "product_name": product_name,
                }
            )

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
                return jsonify(
                    {"success": False, "message": "请指定 product_name"}
                ), 400

            product = dao.get_product_by_name(product_name)
            if not product:
                return jsonify(
                    {"success": False, "message": f"产品 {product_name} 不存在"}
                ), 404
            if not product.xt_username or not product.xt_password:
                return jsonify(
                    {"success": False, "message": f"产品 {product_name} 未配置迅投账号"}
                ), 400

            xt_manager = get_xt_connection_manager()
            xt_service = xt_manager.get_connection(
                username=product.xt_username,
                password=product.xt_password,
                timeout=30.0,
            )
            if not xt_service:
                return jsonify({"success": False, "message": "无法连接迅投"}), 500
            if xt_service._api is None:
                return jsonify({"success": False, "message": "迅投 API 未初始化"}), 500

            try:
                from XtTraderPyApi import XtError as _XtError
            except ImportError as exc:
                return jsonify(
                    {"success": False, "message": f"迅投 SDK 不可用: {exc}"}
                ), 500

            xt_api = xt_service._api

            account_key = xt_service._account_ready.get(product.fund_account)

            result = {
                "account_id": product.fund_account,
                "account_key": account_key[:30] + "..." if account_key else None,
                "logined": xt_service._logined,
                "account_ready_keys": list(xt_service._account_ready.keys()),
            }

            # 方法1: reqOrderDetailSync (当日委托)
            try:
                error = _XtError(0, "")
                orders = xt_api.reqOrderDetailSync(
                    product.fund_account, error, account_key
                )
                result["method1_reqOrderDetailSync"] = {
                    "isSuccess": error.isSuccess(),
                    "errorMsg": error.errorMsg(),
                    "count": len(orders) if orders else 0,
                    "type": type(orders).__name__,
                }
                if orders:
                    result["method1_first_order_attrs"] = {}
                    for attr in dir(orders[0]):
                        if attr.startswith("m_"):
                            try:
                                val = getattr(orders[0], attr)
                                result["method1_first_order_attrs"][attr] = str(val)
                            except Exception:
                                pass
            except Exception as e:
                result["method1_error"] = str(e)

            # 方法2: reqOrderDetailSyncByOrderID (按指令ID查)
            if target_order_id:
                try:
                    error2 = _XtError(0, "")
                    orders2 = xt_api.reqOrderDetailSyncByOrderID(
                        product.fund_account, error2, target_order_id, account_key
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
                            if attr.startswith("m_"):
                                try:
                                    val = getattr(orders2[0], attr)
                                    result["method2_first_attrs"][attr] = str(val)
                                except Exception:
                                    pass
                except Exception as e:
                    result["method2_error"] = str(e)

            # 方法3: reqDealDetailSync (成交明细)
            try:
                error3 = _XtError(0, "")
                deals = xt_api.reqDealDetailSync(product.fund_account, error3, account_key)
                result["method3_reqDealDetail"] = {
                    "isSuccess": error3.isSuccess(),
                    "errorMsg": error3.errorMsg(),
                    "count": len(deals) if deals else 0,
                }
                if deals:
                    result["method3_first_deal_attrs"] = {}
                    for attr in dir(deals[0]):
                        if attr.startswith("m_"):
                            try:
                                val = getattr(deals[0], attr)
                                result["method3_first_deal_attrs"][attr] = str(val)
                            except Exception:
                                pass
            except Exception as e:
                result["method3_error"] = str(e)

            # 方法4: reqCommandsInfoSync (指令查询 - 不需要account_id)
            try:
                error4 = _XtError(0, "")
                cmds = xt_api.reqCommandsInfoSync(error4)
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
                            if attr.startswith("m_"):
                                try:
                                    val = getattr(cmd, attr)
                                    cmd_info[attr] = str(val)
                                except Exception:
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
                    return jsonify(
                        {"success": False, "message": f"缺少必填字段: {field}"}
                    ), 400

            # 构造下单请求
            direction = (
                OrderDirection.BUY
                if data["direction"].lower() == "buy"
                else OrderDirection.SELL
            )
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
                price_type=price_type,
            )

            # 获取服务实例并连接
            xt_service = XtOrderService()
            if not xt_service._logined:
                logger.info("首次下单，连接迅投服务器...")
                if not xt_service.connect(timeout=30.0):
                    return jsonify(
                        {"success": False, "message": "连接迅投服务器失败"}
                    ), 500

            # 执行下单
            result = xt_service.place_order(order_req, timeout=10.0)

            if result.success:
                return jsonify(
                    {
                        "success": True,
                        "order_id": result.order_id,
                        "message": "下单成功",
                    }
                )
            else:
                return jsonify({"success": False, "message": result.error_msg}), 400

        except Exception as e:
            logger.exception("下单接口异常")
            return jsonify({"success": False, "message": f"服务器错误: {str(e)}"}), 500

    # ---------------------------------------------------------------------------
    # 调试接口：查看行情缓存
    # ---------------------------------------------------------------------------

    @app.route("/api/debug/market_cache", methods=["GET"])
    def debug_market_cache():
        """查看当前行情缓存（调试用）"""
        detail = get_tick_cache_detail()
        cache_data = detail.get("symbols", {})
        return jsonify(
            {"success": True, "cache_size": len(cache_data), "data": cache_data}
        )

    # -----------------------------------------------------------------------
    # GET /api/backtests/presets — 获取可回测预设策略
    # -----------------------------------------------------------------------

    @app.route("/api/backtests/presets", methods=["GET"])
    def get_backtest_presets():
        return jsonify({"success": True, "data": list(PRESET_STRATEGIES.values())})

    @app.route("/api/backtests/history", methods=["GET"])
    def get_backtest_history():
        raw_limit = request.args.get("limit", "100")
        try:
            limit = max(1, min(int(raw_limit), 500))
        except ValueError:
            return jsonify(
                {"success": False, "message": "limit 必须是整数", "data": []}
            ), 400

        try:
            records = list_backtest_trade_logs(limit=limit)
        except Exception as e:
            logger.exception("Backtest history failed: %s", e)
            return jsonify(
                {"success": False, "message": f"加载回测历史失败: {e}", "data": []}
            ), 500
        return jsonify({"success": True, "data": records, "total": len(records)})

    @app.route("/api/backtests/history/<log_id>", methods=["GET"])
    def get_backtest_history_detail(log_id: str):
        raw_equity_points = request.args.get("equity_points", "48")
        try:
            equity_points = max(1, min(int(raw_equity_points), 2000))
        except ValueError:
            return jsonify(
                {"success": False, "message": "equity_points 必须是整数"}
            ), 400

        try:
            record = read_backtest_trade_log(log_id, equity_points=equity_points)
        except ValueError:
            return jsonify({"success": False, "message": "回测日志 ID 无效"}), 400
        except Exception as e:
            logger.exception("Backtest history detail failed: %s", e)
            return jsonify({"success": False, "message": f"加载回测详情失败: {e}"}), 500
        if record is None:
            return jsonify({"success": False, "message": "回测日志不存在"}), 404
        return jsonify({"success": True, "data": record})

    # -----------------------------------------------------------------------
    # GET /api/stocks/search — 搜索本地 A 股股票索引
    # -----------------------------------------------------------------------

    @app.route("/api/stocks/search", methods=["GET"])
    def search_stock_index():
        keyword = request.args.get("q", "").strip()
        raw_limit = request.args.get("limit", "20")
        try:
            limit = int(raw_limit)
        except ValueError:
            return jsonify(
                {"success": False, "message": "limit 必须是整数", "data": []}
            ), 400

        try:
            rows = search_stocks(keyword, limit=limit)
        except Exception as e:
            logger.exception("Stock search failed: %s", e)
            return jsonify(
                {"success": False, "message": f"股票搜索失败: {e}", "data": []}
            ), 500

        logger.info(
            "Stock search: q=%s, limit=%s, results=%s", keyword, limit, len(rows)
        )
        return jsonify({"success": True, "data": rows, "total": len(rows)})

    # -----------------------------------------------------------------------
    # POST /api/backtests/run — 运行预设策略回测
    # -----------------------------------------------------------------------

    @app.route("/api/backtests/run", methods=["POST"])
    def run_backtest():
        body = request.get_json(force=True, silent=True) or {}
        strategy_id = str(body.get("strategy_id", "pbx_ma")).strip()
        data_source = str(body.get("data_source", "mock")).strip().lower()
        ts_code = body.get("ts_code")
        symbols = body.get("symbols", body.get("ts_codes"))
        start_date = body.get("start_date")
        end_date = body.get("end_date")
        write_trade_log = _parse_bool_arg(body.get("write_trade_log"), True)
        logger.info(
            "Backtest API request: strategy_id=%s, data_source=%s, ts_code=%s, symbols=%s, "
            "start_date=%s, end_date=%s, write_trade_log=%s, raw_body=%s",
            strategy_id,
            data_source,
            ts_code,
            symbols,
            start_date,
            end_date,
            write_trade_log,
            body,
        )
        try:
            result = run_preset_backtest(
                strategy_id=strategy_id,
                data_source=data_source,
                ts_code=ts_code,
                symbols=symbols,
                start_date=start_date,
                end_date=end_date,
                write_trade_log=write_trade_log,
            )
        except ValueError as e:
            return jsonify({"success": False, "message": str(e)}), 400
        except Exception as e:
            logger.exception("Preset backtest failed: %s", e)
            return jsonify({"success": False, "message": f"回测失败: {e}"}), 500

        logger.info(
            "Backtest API result: strategy_id=%s, data_source=%s, "
            "market_events=%s, signals=%s, trades=%s, final_equity=%.2f",
            strategy_id,
            data_source,
            result.market_events_processed,
            len(result.signals),
            len(result.trades),
            result.final_equity,
        )
        return jsonify(
            {
                "success": True,
                "message": "回测完成",
                "data": serialize_backtest_result(result),
            }
        )

    # -----------------------------------------------------------------------
    # 用户 Python 信号
    # -----------------------------------------------------------------------

    @app.route("/api/signals", methods=["GET"])
    def list_user_signals():
        try:
            status_arg = request.args.get("status")
            status = UserSignalStatus(status_arg) if status_arg else None
            signals = dao.list_user_signals(status)
            return jsonify(
                {
                    "success": True,
                    "data": [_serialize_user_signal(item) for item in signals],
                }
            )
        except Exception as e:
            logger.exception("查询用户信号失败")
            return jsonify(
                {"success": False, "message": f"查询用户信号失败: {e}", "data": []}
            ), 500

    @app.route("/api/signals", methods=["POST"])
    def create_user_signal():
        body = request.get_json(force=True, silent=True) or {}
        try:
            signal = _parse_signal_payload(body)
            if not signal.name or not signal.symbols or not signal.source_code:
                return jsonify(
                    {"success": False, "message": "name、symbols、source_code 不能为空"}
                ), 400
            try:
                load_signal_class(signal.source_code)
            except ValueError as e:
                return jsonify(
                    {
                        "success": False,
                        "message": "信号代码未通过校验",
                        "diagnostics": str(e),
                    }
                ), 400
            new_id = dao.create_user_signal(signal)
            _reload_live_signal_monitor()
            saved = dao.get_user_signal(new_id)
            return jsonify(
                {
                    "success": True,
                    "message": "信号已保存",
                    "data": _serialize_user_signal(saved) if saved else {"id": new_id},
                }
            )
        except ValueError as e:
            return jsonify({"success": False, "message": str(e)}), 400
        except Exception as e:
            logger.exception("创建用户信号失败")
            return jsonify({"success": False, "message": f"创建用户信号失败: {e}"}), 500

    @app.route("/api/signals/<int:signal_id>", methods=["PUT"])
    def update_user_signal(signal_id: int):
        body = request.get_json(force=True, silent=True) or {}
        existing = dao.get_user_signal(signal_id)
        if not existing:
            return jsonify({"success": False, "message": "信号不存在"}), 404
        try:
            signal = _parse_signal_payload(body, existing)
            if not signal.name or not signal.symbols or not signal.source_code:
                return jsonify(
                    {"success": False, "message": "name、symbols、source_code 不能为空"}
                ), 400
            try:
                load_signal_class(signal.source_code)
            except ValueError as e:
                return jsonify(
                    {
                        "success": False,
                        "message": "信号代码未通过校验",
                        "diagnostics": str(e),
                    }
                ), 400
            dao.update_user_signal(signal_id, signal)
            _reload_live_signal_monitor()
            saved = dao.get_user_signal(signal_id)
            return jsonify(
                {
                    "success": True,
                    "message": "信号已更新",
                    "data": _serialize_user_signal(saved) if saved else None,
                }
            )
        except ValueError as e:
            return jsonify({"success": False, "message": str(e)}), 400
        except Exception as e:
            logger.exception("更新用户信号失败")
            return jsonify({"success": False, "message": f"更新用户信号失败: {e}"}), 500

    @app.route("/api/signals/<int:signal_id>/status", methods=["POST"])
    def update_user_signal_status(signal_id: int):
        body = request.get_json(force=True, silent=True) or {}
        try:
            status = UserSignalStatus(
                str(body.get("status", UserSignalStatus.DISABLED.value))
            )
            updated = dao.update_user_signal_status(signal_id, status)
            if not updated:
                return jsonify({"success": False, "message": "信号不存在"}), 404
            _reload_live_signal_monitor()
            return jsonify({"success": True, "message": "状态已更新"})
        except ValueError:
            return jsonify(
                {"success": False, "message": "status 必须是 enabled 或 disabled"}
            ), 400
        except Exception as e:
            logger.exception("更新用户信号状态失败")
            return jsonify(
                {"success": False, "message": f"更新用户信号状态失败: {e}"}
            ), 500

    @app.route("/api/signals/validate", methods=["POST"])
    def validate_user_signal():
        body = request.get_json(force=True, silent=True) or {}
        source_code = str(body.get("source_code", ""))
        is_valid, diagnostics = SignalContractValidator().validate(source_code)
        return jsonify(
            {
                "success": is_valid,
                "message": "校验通过" if is_valid else "校验失败",
                "diagnostics": [item.to_dict() for item in diagnostics],
            }
        ), 200 if is_valid else 400

    @app.route("/api/signals/ctx-schema", methods=["GET"])
    def get_signal_ctx_schema():
        return jsonify({"success": True, "data": get_local_context_reference()})

    @app.route("/api/backtests/run-user-signal", methods=["POST"])
    def run_user_signal_backtest_api():
        body = request.get_json(force=True, silent=True) or {}
        source_code = str(body.get("source_code", ""))
        signal_id = body.get("signal_id")
        if signal_id and not source_code:
            signal = dao.get_user_signal(int(signal_id))
            if not signal:
                return jsonify({"success": False, "message": "信号不存在"}), 404
            source_code = signal.source_code

        if not source_code:
            return jsonify(
                {"success": False, "message": "source_code 或 signal_id 必填"}
            ), 400

        try:
            data = run_user_signal_backtest(
                source_code=source_code,
                data_source=str(body.get("data_source", "mock")).strip().lower(),
                backtest_freq=body.get("backtest_freq"),
                ts_code=body.get("ts_code"),
                symbols=body.get("symbols", body.get("ts_codes")),
                start_date=body.get("start_date"),
                end_date=body.get("end_date"),
                initial_cash=float(body.get("initial_cash", 1_000_000.0)),
                commission_rate=float(body.get("commission_rate", 0.0)),
                write_trade_log=_parse_bool_arg(body.get("write_trade_log"), True),
                execution_timing=_parse_execution_timing(
                    body.get("execution_timing"), "next_bar"
                ),
            )
            return jsonify({"success": True, "message": "回测完成", "data": data})
        except ValueError as e:
            return jsonify({"success": False, "message": str(e)}), 400
        except Exception as e:
            logger.exception("用户信号回测失败")
            return jsonify({"success": False, "message": f"回测失败: {e}"}), 500

    @app.route("/api/signals/live/recent", methods=["GET"])
    def get_recent_live_signals():
        return jsonify({"success": True, "data": live_signal_monitor.get_recent()})

    @app.route("/api/signals/live/stream", methods=["GET"])
    def stream_live_signals():
        listener = live_signal_monitor.add_listener()

        def generate():
            try:
                yield from live_signal_monitor.stream(listener)
            finally:
                live_signal_monitor.remove_listener(listener)

        return Response(
            stream_with_context(generate()),
            mimetype="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return app
