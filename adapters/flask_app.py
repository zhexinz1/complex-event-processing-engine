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
    GET  /api/backtests/presets 获取可回测预设策略列表
    POST /api/backtests/run     运行预设策略回测；mock body: {"strategy_id": "pbx_ma"}
                                tushare body: {"strategy_id": "pbx_ma", "data_source": "tushare",
                                "ts_code": "000001.SZ", "start_date": "20240101", "end_date": "20241231"}
    GET  /api/stocks/search     搜索本地 A 股股票索引（query: q, limit）
    GET  /                     前端大屏页面
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, cast

import pymysql
import pymysql.cursors
from flask import Flask, jsonify, request, send_from_directory

from backtest.preset_strategies import (
    PRESET_STRATEGIES,
    run_preset_backtest,
    serialize_backtest_result,
)
from data_provider import search_stocks

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 数据库连接配置
# ---------------------------------------------------------------------------

DB_CONFIG: dict[str, Any] = dict(
    host="120.25.245.137",
    port=23306,
    database="fof",
    user="cx",
    password="cC3z#,2?od)gn7Nhd2L1",
    charset="utf8mb4",
    cursorclass=pymysql.cursors.DictCursor,
    autocommit=False,
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


def get_conn() -> Any:
    return pymysql.connect(**DB_CONFIG)


def init_db() -> None:
    """建表（幂等），应用启动时调用一次。"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(CREATE_TABLE_SQL)
            cur.execute(CREATE_ASSETS_TABLE_SQL)
        conn.commit()
    logger.info("DB tables target_allocations and allowed_assets ready.")


# ---------------------------------------------------------------------------
# Flask 应用工厂
# ---------------------------------------------------------------------------

def create_app() -> Flask:
    app = Flask(__name__, static_folder=None)

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
                    rows = cast(list[dict[str, Any]], cur.fetchall())
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
                    rows = cast(list[dict[str, Any]], cur.fetchall())
        except Exception:
            return jsonify({"success": True, "data": []})
        return jsonify({"success": True, "data": [r["product_name"] for r in rows]})

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
        asset_code = (body.get("asset_code") or "").strip().upper()
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
        asset_code = asset_code.upper()
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
    # GET /api/backtests/presets — 获取可回测预设策略
    # -----------------------------------------------------------------------

    @app.route("/api/backtests/presets", methods=["GET"])
    def get_backtest_presets():
        return jsonify({"success": True, "data": list(PRESET_STRATEGIES.values())})

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
            return jsonify({"success": False, "message": "limit 必须是整数", "data": []}), 400

        try:
            rows = search_stocks(keyword, limit=limit)
        except Exception as e:
            logger.exception("Stock search failed: %s", e)
            return jsonify({"success": False, "message": f"股票搜索失败: {e}", "data": []}), 500

        logger.info("Stock search: q=%s, limit=%s, results=%s", keyword, limit, len(rows))
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
        logger.info(
            "Backtest API request: strategy_id=%s, data_source=%s, ts_code=%s, symbols=%s, "
            "start_date=%s, end_date=%s, raw_body=%s",
            strategy_id,
            data_source,
            ts_code,
            symbols,
            start_date,
            end_date,
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

    return app
