"""
target_config.py — 目标权重配置管理

支持从数据库或配置文件加载目标权重配置，包括：
  - 产品名称
  - 资产代码
  - 目标比例
  - 偏离阈值（每个资产独立配置）
  - 执行算法（TWAP、VWAP 等）

数据库表结构示例：
  日期        产品名称           资产            比例      偏离阈值    算法
  2026/3/30  明钺全天候1号    AU2606.SHF    25.61%    3%        TWAP
  2026/3/30  明钺全天候1号    IC2606.CFE    20.48%    5%        TWAP
  2026/3/30  明钺全天候1号    T2605.CFE     124.76%   2%        TWAP
  2026/3/30  明钺全天候1号    M2609.DCE     7.81%     4%        TWAP
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import Optional, Protocol

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 数据类定义
# ---------------------------------------------------------------------------


@dataclass
class TargetWeightConfig:
    """
    单个资产的目标权重配置。

    Attributes:
        date:               配置日期
        product_name:       产品名称（如 "明钺全天候1号"）
        symbol:             资产代码（如 "AU2606.SHF"）
        target_weight:      目标比例（如 0.2561 表示 25.61%）
        deviation_threshold: 偏离阈值（如 0.03 表示 3%）
        algorithm:          执行算法（如 "TWAP", "VWAP", "POV"）
    """

    date: date
    product_name: str
    symbol: str
    target_weight: float
    deviation_threshold: float = 0.05  # 默认 5%
    algorithm: str = "TWAP"


@dataclass
class ProductConfig:
    """
    产品级配置（包含多个资产）。

    Attributes:
        product_name:       产品名称
        date:               配置日期
        assets:             资产配置列表
        global_threshold:   全局偏离阈值（如果资产未单独配置，使用此值）
    """

    product_name: str
    date: date
    assets: list[TargetWeightConfig]
    global_threshold: float = 0.05  # 默认 5%

    def get_target_weights(self) -> dict[str, float]:
        """获取所有资产的目标权重字典。"""
        return {asset.symbol: asset.target_weight for asset in self.assets}

    def get_deviation_thresholds(self) -> dict[str, float]:
        """获取所有资产的偏离阈值字典。"""
        return {asset.symbol: asset.deviation_threshold for asset in self.assets}

    def get_algorithms(self) -> dict[str, str]:
        """获取所有资产的执行算法字典。"""
        return {asset.symbol: asset.algorithm for asset in self.assets}


# ---------------------------------------------------------------------------
# 配置加载接口（抽象协议）
# ---------------------------------------------------------------------------


class TargetConfigLoader(Protocol):
    """
    目标权重配置加载器接口。

    实现此接口以支持不同的数据源：
      - DatabaseConfigLoader: 从数据库加载
      - FileConfigLoader: 从 JSON/YAML 文件加载
      - APIConfigLoader: 从 REST API 加载
    """

    def load_product_config(
        self, product_name: str, config_date: Optional[date] = None
    ) -> Optional[ProductConfig]:
        """
        加载指定产品的目标权重配置。

        Args:
            product_name: 产品名称
            config_date:  配置日期（None 表示使用最新配置）

        Returns:
            产品配置对象，不存在返回 None
        """
        ...

    def save_product_config(self, config: ProductConfig) -> bool:
        """
        保存产品配置。

        Args:
            config: 产品配置对象

        Returns:
            保存是否成功
        """
        ...


# ---------------------------------------------------------------------------
# 内存配置加载器（用于测试和简单场景）
# ---------------------------------------------------------------------------


class InMemoryConfigLoader:
    """
    内存配置加载器（用于测试和简单场景）。

    将配置存储在内存中，不持久化。
    """

    def __init__(self):
        """初始化内存配置加载器。"""
        # 存储格式：{(product_name, date): ProductConfig}
        self._configs: dict[tuple[str, date], ProductConfig] = {}
        logger.info("InMemoryConfigLoader initialized")

    def load_product_config(
        self, product_name: str, config_date: Optional[date] = None
    ) -> Optional[ProductConfig]:
        """
        加载指定产品的目标权重配置。

        Args:
            product_name: 产品名称
            config_date:  配置日期（None 表示使用最新配置）

        Returns:
            产品配置对象，不存在返回 None
        """
        if config_date is None:
            # 查找最新配置
            matching_configs = [
                (d, cfg) for (pn, d), cfg in self._configs.items() if pn == product_name
            ]
            if not matching_configs:
                logger.warning(f"No config found for product: {product_name}")
                return None

            # 返回最新日期的配置
            config_date, config = max(matching_configs, key=lambda x: x[0])
            logger.info(f"Loaded latest config for {product_name} (date={config_date})")
            return config

        # 查找指定日期的配置
        key = (product_name, config_date)
        config = self._configs.get(key)

        if config:
            logger.info(f"Loaded config for {product_name} (date={config_date})")
        else:
            logger.warning(f"No config found for {product_name} on {config_date}")

        return config

    def save_product_config(self, config: ProductConfig) -> bool:
        """
        保存产品配置。

        Args:
            config: 产品配置对象

        Returns:
            保存是否成功
        """
        key = (config.product_name, config.date)
        self._configs[key] = config
        logger.info(
            f"Saved config for {config.product_name} (date={config.date}, "
            f"{len(config.assets)} assets)"
        )
        return True


# ---------------------------------------------------------------------------
# 数据库配置加载器（预留接口）
# ---------------------------------------------------------------------------


class DatabaseConfigLoader:
    """
    数据库配置加载器（预留接口）。

    TODO: 实现从数据库加载配置的逻辑
      - 连接数据库（MySQL/PostgreSQL/SQLite）
      - 查询目标权重表
      - 解析数据并构造 ProductConfig 对象
    """

    def __init__(self, db_connection_string: str):
        """
        初始化数据库配置加载器。

        Args:
            db_connection_string: 数据库连接字符串
        """
        self.db_connection_string = db_connection_string
        # TODO: 初始化数据库连接
        # self.db = connect(db_connection_string)
        logger.info(
            f"DatabaseConfigLoader initialized (connection: {db_connection_string})"
        )

    def load_product_config(
        self, product_name: str, config_date: Optional[date] = None
    ) -> Optional[ProductConfig]:
        """
        从数据库加载指定产品的目标权重配置。

        Args:
            product_name: 产品名称
            config_date:  配置日期（None 表示使用最新配置）

        Returns:
            产品配置对象，不存在返回 None
        """
        # TODO: 实现数据库查询逻辑
        # 示例 SQL:
        # SELECT date, product_name, symbol, target_weight, deviation_threshold, algorithm
        # FROM target_weights
        # WHERE product_name = ? AND date = ?
        # ORDER BY date DESC

        logger.warning("DatabaseConfigLoader.load_product_config not implemented yet")
        return None

    def save_product_config(self, config: ProductConfig) -> bool:
        """
        保存产品配置到数据库。

        Args:
            config: 产品配置对象

        Returns:
            保存是否成功
        """
        # TODO: 实现数据库插入/更新逻辑
        logger.warning("DatabaseConfigLoader.save_product_config not implemented yet")
        return False


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------


def create_sample_config() -> ProductConfig:
    """
    创建示例配置（用于测试）。

    Returns:
        示例产品配置
    """
    assets = [
        TargetWeightConfig(
            date=date(2026, 3, 30),
            product_name="明钺全天候1号",
            symbol="AU2606.SHF",
            target_weight=0.2561,
            deviation_threshold=0.03,
            algorithm="TWAP",
        ),
        TargetWeightConfig(
            date=date(2026, 3, 30),
            product_name="明钺全天候1号",
            symbol="IC2606.CFE",
            target_weight=0.2048,
            deviation_threshold=0.05,
            algorithm="TWAP",
        ),
        TargetWeightConfig(
            date=date(2026, 3, 30),
            product_name="明钺全天候1号",
            symbol="T2605.CFE",
            target_weight=1.2476,  # 注意：可以超过 100%（杠杆）
            deviation_threshold=0.02,
            algorithm="TWAP",
        ),
        TargetWeightConfig(
            date=date(2026, 3, 30),
            product_name="明钺全天候1号",
            symbol="M2609.DCE",
            target_weight=0.0781,
            deviation_threshold=0.04,
            algorithm="TWAP",
        ),
    ]

    return ProductConfig(
        product_name="明钺全天候1号",
        date=date(2026, 3, 30),
        assets=assets,
        global_threshold=0.05,
    )
