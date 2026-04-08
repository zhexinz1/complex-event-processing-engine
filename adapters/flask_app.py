"""
flask_app.py — 目标仓位配置 REST API

提供 target_allocations 表的 CRUD 接口，并挂载前端静态文件。

Endpoints:
    GET  /api/weights          查询（支持 target_date / product_name 过滤）
    POST /api/weights          新增或覆盖更新
    DELETE /api/weights/<id>   删除单条记录
    GET  /                     前端大屏页面
"""

from __future__ import annotations

import logging
from pathlib import Path

import pymysql
import pymysql.cursors
from flask import Flask, jsonify, request, send_from_directory

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 数据库连接配置
# ---------------------------------------------------------------------------

DB_CONFIG = dict(
    host="120.25.245.137",
    port=23306,
    database="fof",
    user="cx",
    password="iyykiho4#0HO",
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

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"


def get_conn():
    return pymysql.connect(**DB_CONFIG)


def init_db() -> None:
    """建表（幂等），应用启动时调用一次。"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(CREATE_TABLE_SQL)
        conn.commit()
    logger.info("DB table target_allocations ready.")


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

    return app
