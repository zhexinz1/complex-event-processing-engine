"""
config_source.py — 配置数据源适配器

提供统一的配置数据读取接口，支持多种数据源：
- 数据库（MySQL、PostgreSQL）
- 配置文件（JSON、YAML）
- 远程配置中心（Apollo、Nacos）

设计原则：
  1. 抽象接口：定义统一的配置读取接口
  2. 热更新支持：支持配置变更通知
  3. 缓存机制：减少数据库查询压力
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 抽象基类
# ---------------------------------------------------------------------------

class ConfigSource(ABC):
    """
    配置数据源抽象基类。

    所有配置源适配器必须实现此接口。
    """

    @abstractmethod
    def load_target_weights(self, strategy_id: str) -> dict[str, float]:
        """
        加载目标权重配置。

        Args:
            strategy_id: 策略 ID，用于区分不同的配置

        Returns:
            目标权重字典，如 {"AU2606": 0.26, "P2609": 0.17}
        """
        pass

    @abstractmethod
    def save_target_weights(
        self,
        strategy_id: str,
        weights: dict[str, float]
    ) -> bool:
        """
        保存目标权重配置。

        Args:
            strategy_id: 策略 ID
            weights:     目标权重字典

        Returns:
            保存是否成功
        """
        pass

    @abstractmethod
    def load_contract_info(self, symbol: str) -> Optional[dict]:
        """
        加载合约基础信息。

        Args:
            symbol: 合约代码

        Returns:
            合约信息字典，包含 multiplier、min_tick、margin_rate 等
        """
        pass


# ---------------------------------------------------------------------------
# 数据库配置源
# ---------------------------------------------------------------------------

class DatabaseConfigSource(ConfigSource):
    """
    数据库配置源实现。

    支持从 MySQL/PostgreSQL 读取配置数据。

    表结构示例：
    ```sql
    CREATE TABLE target_weights (
        id INT PRIMARY KEY AUTO_INCREMENT,
        strategy_id VARCHAR(50) NOT NULL,
        symbol VARCHAR(20) NOT NULL,
        weight DECIMAL(10, 6) NOT NULL,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uk_strategy_symbol (strategy_id, symbol)
    );

    CREATE TABLE contract_info (
        symbol VARCHAR(20) PRIMARY KEY,
        multiplier DECIMAL(10, 2) NOT NULL,
        min_tick DECIMAL(10, 6) NOT NULL,
        margin_rate DECIMAL(10, 6) NOT NULL,
        exchange VARCHAR(20),
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    ```
    """

    def __init__(
        self,
        host: str,
        port: int,
        database: str,
        user: str,
        password: str,
        db_type: str = "mysql"
    ):
        """
        初始化数据库配置源。

        Args:
            host:     数据库主机地址
            port:     数据库端口
            database: 数据库名称
            user:     用户名
            password: 密码
            db_type:  数据库类型，"mysql" 或 "postgresql"
        """
        self.host = host
        self.port = port
        self.database = database
        self.user = user
        self.password = password
        self.db_type = db_type

        # TODO: 初始化数据库连接
        # if db_type == "mysql":
        #     import pymysql
        #     self.conn = pymysql.connect(...)
        # elif db_type == "postgresql":
        #     import psycopg2
        #     self.conn = psycopg2.connect(...)

        logger.info(f"DatabaseConfigSource initialized: {db_type}://{host}:{port}/{database}")

    def load_target_weights(self, strategy_id: str) -> dict[str, float]:
        """
        从数据库加载目标权重配置。

        Args:
            strategy_id: 策略 ID

        Returns:
            目标权重字典
        """
        # TODO: 实现数据库查询
        # query = """
        #     SELECT symbol, weight
        #     FROM target_weights
        #     WHERE strategy_id = %s
        # """
        # cursor.execute(query, (strategy_id,))
        # rows = cursor.fetchall()
        # return {row['symbol']: row['weight'] for row in rows}

        logger.warning(f"Database query not implemented, returning empty weights for {strategy_id}")
        return {}

    def save_target_weights(
        self,
        strategy_id: str,
        weights: dict[str, float]
    ) -> bool:
        """
        保存目标权重配置到数据库。

        Args:
            strategy_id: 策略 ID
            weights:     目标权重字典

        Returns:
            保存是否成功
        """
        # TODO: 实现数据库写入
        # query = """
        #     INSERT INTO target_weights (strategy_id, symbol, weight, updated_at)
        #     VALUES (%s, %s, %s, NOW())
        #     ON DUPLICATE KEY UPDATE weight = VALUES(weight), updated_at = NOW()
        # """
        # for symbol, weight in weights.items():
        #     cursor.execute(query, (strategy_id, symbol, weight))
        # conn.commit()

        logger.warning(f"Database write not implemented for {strategy_id}")
        return False

    def load_contract_info(self, symbol: str) -> Optional[dict]:
        """
        从数据库加载合约信息。

        Args:
            symbol: 合约代码

        Returns:
            合约信息字典
        """
        # TODO: 实现数据库查询
        # query = """
        #     SELECT multiplier, min_tick, margin_rate, exchange
        #     FROM contract_info
        #     WHERE symbol = %s
        # """
        # cursor.execute(query, (symbol,))
        # row = cursor.fetchone()
        # return dict(row) if row else None

        logger.warning(f"Database query not implemented for contract {symbol}")
        return None


# ---------------------------------------------------------------------------
# 文件配置源
# ---------------------------------------------------------------------------

class FileConfigSource(ConfigSource):
    """
    文件配置源实现。

    支持从 JSON/YAML 文件读取配置数据。

    文件格式示例（JSON）：
    ```json
    {
        "target_weights": {
            "strategy_001": {
                "AU2606": 0.26,
                "P2609": 0.17,
                "RB2610": 0.15
            }
        },
        "contract_info": {
            "AU2606": {
                "multiplier": 1000,
                "min_tick": 0.05,
                "margin_rate": 0.08
            }
        }
    }
    ```
    """

    def __init__(self, config_file: str):
        """
        初始化文件配置源。

        Args:
            config_file: 配置文件路径
        """
        self.config_file = Path(config_file)
        self._config_data: dict = {}
        self._load_file()

        logger.info(f"FileConfigSource initialized: {config_file}")

    def _load_file(self) -> None:
        """加载配置文件。"""
        if not self.config_file.exists():
            logger.warning(f"Config file not found: {self.config_file}")
            self._config_data = {"target_weights": {}, "contract_info": {}}
            return

        try:
            with open(self.config_file, "r", encoding="utf-8") as f:
                if self.config_file.suffix == ".json":
                    self._config_data = json.load(f)
                elif self.config_file.suffix in [".yaml", ".yml"]:
                    # TODO: 添加 YAML 支持
                    # import yaml
                    # self._config_data = yaml.safe_load(f)
                    raise NotImplementedError("YAML support not implemented yet")
                else:
                    raise ValueError(f"Unsupported file format: {self.config_file.suffix}")

            logger.info(f"Config file loaded: {self.config_file}")

        except Exception as e:
            logger.error(f"Failed to load config file: {e}")
            self._config_data = {"target_weights": {}, "contract_info": {}}

    def load_target_weights(self, strategy_id: str) -> dict[str, float]:
        """
        从文件加载目标权重配置。

        Args:
            strategy_id: 策略 ID

        Returns:
            目标权重字典
        """
        weights = self._config_data.get("target_weights", {}).get(strategy_id, {})
        logger.info(f"Loaded target weights for {strategy_id}: {weights}")
        return weights

    def save_target_weights(
        self,
        strategy_id: str,
        weights: dict[str, float]
    ) -> bool:
        """
        保存目标权重配置到文件。

        Args:
            strategy_id: 策略 ID
            weights:     目标权重字典

        Returns:
            保存是否成功
        """
        try:
            if "target_weights" not in self._config_data:
                self._config_data["target_weights"] = {}

            self._config_data["target_weights"][strategy_id] = weights

            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(self._config_data, f, indent=2, ensure_ascii=False)

            logger.info(f"Target weights saved for {strategy_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to save target weights: {e}")
            return False

    def load_contract_info(self, symbol: str) -> Optional[dict]:
        """
        从文件加载合约信息。

        Args:
            symbol: 合约代码

        Returns:
            合约信息字典
        """
        contract_info = self._config_data.get("contract_info", {}).get(symbol)
        if contract_info:
            logger.debug(f"Loaded contract info for {symbol}: {contract_info}")
        else:
            logger.warning(f"Contract info not found for {symbol}")
        return contract_info

    def reload(self) -> None:
        """重新加载配置文件（支持热更新）。"""
        logger.info("Reloading config file...")
        self._load_file()


# ---------------------------------------------------------------------------
# MySQL 配置源（连接阿里云 FOF 数据库）
# ---------------------------------------------------------------------------

class MySQLConfigSource(ConfigSource):
    """
    MySQL 配置源，读取 target_allocations 表中的目标仓位配置。

    load_target_weights 返回指定产品在最新日期下的权重字典，
    供 RebalanceEngine 直接使用。
    """

    DB_HOST = "120.25.245.137"
    DB_PORT = 23306
    DB_NAME = "fof"
    DB_USER = "cx"
    DB_PASS = "iyykiho4#0HO"

    CREATE_TABLE_SQL = """
    CREATE TABLE IF NOT EXISTS target_allocations (
        id            INT PRIMARY KEY AUTO_INCREMENT,
        target_date   DATE         NOT NULL,
        product_name  VARCHAR(100) NOT NULL,
        asset_code    VARCHAR(50)  NOT NULL,
        weight_ratio  DECIMAL(12, 6) NOT NULL,
        algo_type     VARCHAR(20)  NOT NULL DEFAULT 'TWAP',
        created_at    TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
        updated_at    TIMESTAMP    DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        UNIQUE KEY uk_date_product_asset (target_date, product_name, asset_code)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """

    def __init__(self) -> None:
        import pymysql
        self._pymysql = pymysql
        self._ensure_table()
        logger.info("MySQLConfigSource initialized: %s:%s/%s", self.DB_HOST, self.DB_PORT, self.DB_NAME)

    def _connect(self):
        return self._pymysql.connect(
            host=self.DB_HOST,
            port=self.DB_PORT,
            database=self.DB_NAME,
            user=self.DB_USER,
            password=self.DB_PASS,
            charset="utf8mb4",
            cursorclass=self._pymysql.cursors.DictCursor,
            autocommit=False,
        )

    def _ensure_table(self) -> None:
        """建表（幂等）。"""
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(self.CREATE_TABLE_SQL)
            conn.commit()

    # ------------------------------------------------------------------
    # ConfigSource 接口实现
    # ------------------------------------------------------------------

    def load_target_weights(self, strategy_id: str) -> dict[str, float]:
        """
        返回 strategy_id（即 product_name）在最新 target_date 下的权重字典。

        Returns:
            {"AU2606": 0.2561, "IC2606": 0.2048, ...}
        """
        sql = """
            SELECT asset_code, weight_ratio
            FROM target_allocations
            WHERE product_name = %s
              AND target_date = (
                  SELECT MAX(target_date)
                  FROM target_allocations
                  WHERE product_name = %s
              )
        """
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (strategy_id, strategy_id))
                rows = cur.fetchall()

        result = {row["asset_code"]: float(row["weight_ratio"]) for row in rows}
        logger.info("Loaded %d weights for '%s'", len(result), strategy_id)
        return result

    def save_target_weights(self, strategy_id: str, weights: dict[str, float]) -> bool:
        """
        将权重字典以今日日期写入 target_allocations（冲突则覆盖）。
        """
        from datetime import date
        today = date.today().isoformat()
        sql = """
            INSERT INTO target_allocations (target_date, product_name, asset_code, weight_ratio)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE weight_ratio = VALUES(weight_ratio), updated_at = NOW()
        """
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    for asset_code, ratio in weights.items():
                        cur.execute(sql, (today, strategy_id, asset_code, ratio))
                conn.commit()
            logger.info("Saved %d weights for '%s'", len(weights), strategy_id)
            return True
        except Exception:
            logger.exception("Failed to save weights for '%s'", strategy_id)
            return False

    def load_contract_info(self, symbol: str) -> Optional[dict]:
        """target_allocations 表不含合约信息，返回 None。"""
        return None
