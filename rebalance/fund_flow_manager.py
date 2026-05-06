"""
fund_flow_manager.py — 资金流动管理模块

管理客户出入金记录，结合迅投估值计算净入金，触发再平衡。

业务流程：
  1. 运营人员输入每日出入金记录
  2. 从迅投 API 获取产品估值
  3. 计算净入金 = 当前估值 - 昨日估值 - 今日盈亏
  4. 触发再平衡，按最新配置比例下单

数据库表结构：
  fund_flow_records: 出入金记录表
  product_valuation: 产品估值表（从迅投同步）
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
class FundFlowRecord:
    """
    出入金记录。

    Attributes:
        date:         日期
        product_name: 产品名称
        inflow:       入金金额（正数）
        outflow:      出金金额（正数）
        net_flow:     净入金（入金 - 出金）
        operator:     操作员
        remark:       备注
    """

    date: date
    product_name: str
    inflow: float
    outflow: float
    net_flow: float
    operator: str
    remark: str = ""


@dataclass
class ProductValuation:
    """
    产品估值。

    Attributes:
        date:         日期
        product_name: 产品名称
        nav:          净值（从迅投 API 获取）
        total_assets: 总资产
        total_liabilities: 总负债
        unit_nav:     单位净值
        pnl:          当日盈亏
        source:       数据来源（"xuntou_api" / "manual"）
    """

    date: date
    product_name: str
    nav: float
    total_assets: float = 0.0
    total_liabilities: float = 0.0
    unit_nav: float = 1.0
    pnl: float = 0.0
    source: str = "xuntou_api"


@dataclass
class NetCapitalChange:
    """
    净入金计算结果。

    Attributes:
        date:              日期
        product_name:      产品名称
        previous_nav:      昨日净值
        current_nav:       今日净值
        pnl:               今日盈亏
        fund_inflow:       今日入金
        fund_outflow:      今日出金
        net_capital_change: 净入金（= 当前净值 - 昨日净值 - 今日盈亏）
        calculation_method: 计算方法说明
    """

    date: date
    product_name: str
    previous_nav: float
    current_nav: float
    pnl: float
    fund_inflow: float
    fund_outflow: float
    net_capital_change: float
    calculation_method: str = "current_nav - previous_nav - pnl"


# ---------------------------------------------------------------------------
# 出入金数据源接口
# ---------------------------------------------------------------------------


class FundFlowDataSource(Protocol):
    """
    出入金数据源接口。

    实现此接口以支持不同的数据源：
      - DatabaseFundFlowSource: 从数据库读取
      - APIFundFlowSource: 从 REST API 读取
      - ExcelFundFlowSource: 从 Excel 文件读取
    """

    def save_fund_flow_record(self, record: FundFlowRecord) -> bool:
        """保存出入金记录"""
        ...

    def get_fund_flow_records(
        self, product_name: str, start_date: date, end_date: date
    ) -> list[FundFlowRecord]:
        """查询出入金记录"""
        ...


# ---------------------------------------------------------------------------
# 估值数据源接口
# ---------------------------------------------------------------------------


class ValuationDataSource(Protocol):
    """
    估值数据源接口。

    实现此接口以支持不同的数据源：
      - XunTouValuationSource: 从迅投 API 获取估值
      - DatabaseValuationSource: 从数据库读取历史估值
    """

    def fetch_valuation(
        self, product_name: str, valuation_date: date
    ) -> Optional[ProductValuation]:
        """从迅投 API 获取产品估值"""
        ...

    def save_valuation(self, valuation: ProductValuation) -> bool:
        """保存估值到数据库"""
        ...

    def get_valuation_history(
        self, product_name: str, start_date: date, end_date: date
    ) -> list[ProductValuation]:
        """查询历史估值"""
        ...


# ---------------------------------------------------------------------------
# 迅投估值数据源（预留接口）
# ---------------------------------------------------------------------------


class XunTouValuationSource:
    """
    迅投估值数据源（预留接口）。

    从迅投 GT API 获取产品估值信息。

    TODO: 实现迅投 GT API 对接
      - 引入迅投 GT SDK
      - 实现估值查询接口
      - 实现盈亏查询接口
    """

    def __init__(self, server_addr: str, account_id: str, password: str, app_id: str):
        """
        初始化迅投估值数据源。

        Args:
            server_addr: 服务器地址
            account_id:  账户 ID
            password:    密码
            app_id:      应用 ID
        """
        self.server_addr = server_addr
        self.account_id = account_id
        self.password = password
        self.app_id = app_id

        # TODO: 初始化迅投 GT API
        # self.gt_api = GTApi()

        logger.info(f"XunTouValuationSource initialized: {server_addr}")

    def connect(self) -> bool:
        """连接到迅投 GT 服务器"""
        # TODO: 实现迅投 GT 连接逻辑
        logger.warning("XunTou GT connection not implemented yet")
        return False

    def fetch_valuation(
        self, product_name: str, valuation_date: date
    ) -> Optional[ProductValuation]:
        """
        从迅投 GT API 获取产品估值。

        Args:
            product_name:    产品名称
            valuation_date:  估值日期

        Returns:
            产品估值对象

        实现示例:
        valuation_data = self.gt_api.query_valuation(
            product_name=product_name,
            date=valuation_date
        )
        return ProductValuation(
            date=valuation_date,
            product_name=product_name,
            nav=valuation_data['nav'],
            total_assets=valuation_data['total_assets'],
            total_liabilities=valuation_data['total_liabilities'],
            unit_nav=valuation_data['unit_nav'],
            pnl=valuation_data['pnl'],
            source='xuntou_api'
        )
        """
        # TODO: 调用迅投 GT API 查询估值
        logger.warning(f"XunTou GT fetch_valuation not implemented: {product_name}")
        return None

    def fetch_pnl(self, product_name: str, valuation_date: date) -> float:
        """
        从迅投 GT API 获取当日盈亏。

        Args:
            product_name:    产品名称
            valuation_date:  日期

        Returns:
            当日盈亏

        实现示例:
        pnl_data = self.gt_api.query_pnl(
            product_name=product_name,
            date=valuation_date
        )
        return pnl_data['pnl']
        """
        # TODO: 调用迅投 GT API 查询盈亏
        logger.warning(f"XunTou GT fetch_pnl not implemented: {product_name}")
        return 0.0


# ---------------------------------------------------------------------------
# 数据库数据源（预留接口）
# ---------------------------------------------------------------------------


class DatabaseFundFlowSource:
    """
    数据库出入金数据源（预留接口）。

    从数据库读写出入金记录。

    数据库表结构:
    CREATE TABLE fund_flow_records (
        id BIGINT PRIMARY KEY AUTO_INCREMENT,
        date DATE NOT NULL,
        product_name VARCHAR(100) NOT NULL,
        inflow DECIMAL(18,2) NOT NULL,
        outflow DECIMAL(18,2) NOT NULL,
        net_flow DECIMAL(18,2) NOT NULL,
        operator VARCHAR(50) NOT NULL,
        remark TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uk_date_product (date, product_name)
    );
    """

    def __init__(self, db_connection_string: str):
        """
        初始化数据库出入金数据源。

        Args:
            db_connection_string: 数据库连接字符串
        """
        self.db_connection_string = db_connection_string
        # TODO: 初始化数据库连接
        logger.info(f"DatabaseFundFlowSource initialized: {db_connection_string}")

    def save_fund_flow_record(self, record: FundFlowRecord) -> bool:
        """
        保存出入金记录到数据库。

        SQL 示例:
        INSERT INTO fund_flow_records
        (date, product_name, inflow, outflow, net_flow, operator, remark)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON DUPLICATE KEY UPDATE
        inflow=VALUES(inflow), outflow=VALUES(outflow),
        net_flow=VALUES(net_flow), operator=VALUES(operator),
        remark=VALUES(remark)
        """
        # TODO: 实现数据库插入逻辑
        logger.warning(
            "DatabaseFundFlowSource.save_fund_flow_record not implemented yet"
        )
        return False

    def get_fund_flow_records(
        self, product_name: str, start_date: date, end_date: date
    ) -> list[FundFlowRecord]:
        """
        从数据库查询出入金记录。

        SQL 示例:
        SELECT date, product_name, inflow, outflow, net_flow, operator, remark
        FROM fund_flow_records
        WHERE product_name = ? AND date BETWEEN ? AND ?
        ORDER BY date DESC
        """
        # TODO: 实现数据库查询逻辑
        logger.warning(
            "DatabaseFundFlowSource.get_fund_flow_records not implemented yet"
        )
        return []


class DatabaseValuationSource:
    """
    数据库估值数据源（预留接口）。

    从数据库读写估值记录。

    数据库表结构:
    CREATE TABLE product_valuation (
        id BIGINT PRIMARY KEY AUTO_INCREMENT,
        date DATE NOT NULL,
        product_name VARCHAR(100) NOT NULL,
        nav DECIMAL(18,2) NOT NULL,
        total_assets DECIMAL(18,2) NOT NULL,
        total_liabilities DECIMAL(18,2) NOT NULL,
        unit_nav DECIMAL(10,4) NOT NULL,
        pnl DECIMAL(18,2) NOT NULL,
        source VARCHAR(20) NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uk_date_product (date, product_name)
    );
    """

    def __init__(self, db_connection_string: str):
        """初始化数据库估值数据源"""
        self.db_connection_string = db_connection_string
        # TODO: 初始化数据库连接
        logger.info(f"DatabaseValuationSource initialized: {db_connection_string}")

    def save_valuation(self, valuation: ProductValuation) -> bool:
        """保存估值到数据库"""
        # TODO: 实现数据库插入逻辑
        logger.warning("DatabaseValuationSource.save_valuation not implemented yet")
        return False

    def get_valuation_history(
        self, product_name: str, start_date: date, end_date: date
    ) -> list[ProductValuation]:
        """查询历史估值"""
        # TODO: 实现数据库查询逻辑
        logger.warning(
            "DatabaseValuationSource.get_valuation_history not implemented yet"
        )
        return []


# ---------------------------------------------------------------------------
# 资金流动管理器
# ---------------------------------------------------------------------------


class FundFlowManager:
    """
    资金流动管理器。

    核心功能：
      1. 接收运营人员输入的出入金记录
      2. 从迅投 API 获取产品估值
      3. 计算净入金金额
      4. 触发再平衡
    """

    def __init__(
        self,
        fund_flow_source: FundFlowDataSource,
        valuation_source: ValuationDataSource,
    ):
        """
        初始化资金流动管理器。

        Args:
            fund_flow_source:  出入金数据源
            valuation_source:  估值数据源
        """
        self.fund_flow_source = fund_flow_source
        self.valuation_source = valuation_source
        logger.info("FundFlowManager initialized")

    def record_fund_flow(
        self,
        product_name: str,
        flow_date: date,
        inflow: float,
        outflow: float,
        operator: str,
        remark: str = "",
    ) -> bool:
        """
        记录出入金。

        Args:
            product_name: 产品名称
            flow_date:    日期
            inflow:       入金金额
            outflow:      出金金额
            operator:     操作员
            remark:       备注

        Returns:
            是否成功
        """
        net_flow = inflow - outflow

        record = FundFlowRecord(
            date=flow_date,
            product_name=product_name,
            inflow=inflow,
            outflow=outflow,
            net_flow=net_flow,
            operator=operator,
            remark=remark,
        )

        success = self.fund_flow_source.save_fund_flow_record(record)

        if success:
            logger.info(
                f"Fund flow recorded: {product_name} on {flow_date}, "
                f"inflow={inflow:,.2f}, outflow={outflow:,.2f}, net={net_flow:,.2f}"
            )
        else:
            logger.error(f"Failed to record fund flow: {product_name} on {flow_date}")

        return success

    def calculate_net_capital_change(
        self, product_name: str, calculation_date: date
    ) -> Optional[NetCapitalChange]:
        """
        计算净入金金额。

        计算公式：
        净入金 = 当前净值 - 昨日净值 - 今日盈亏

        Args:
            product_name:      产品名称
            calculation_date:  计算日期

        Returns:
            净入金计算结果
        """
        # 1. 从迅投 API 获取当前估值
        current_valuation = self.valuation_source.fetch_valuation(
            product_name, calculation_date
        )
        if not current_valuation:
            logger.error(f"Failed to fetch current valuation for {product_name}")
            return None

        # 2. 获取昨日估值
        from datetime import timedelta

        previous_date = calculation_date - timedelta(days=1)
        previous_valuation = self.valuation_source.fetch_valuation(
            product_name, previous_date
        )
        if not previous_valuation:
            logger.warning(f"No previous valuation found for {product_name}, using 0")
            previous_nav = 0.0
        else:
            previous_nav = previous_valuation.nav

        # 3. 获取出入金记录
        fund_flow_records = self.fund_flow_source.get_fund_flow_records(
            product_name, calculation_date, calculation_date
        )
        fund_inflow = sum(r.inflow for r in fund_flow_records)
        fund_outflow = sum(r.outflow for r in fund_flow_records)

        # 4. 计算净入金
        # 净入金 = 当前净值 - 昨日净值 - 今日盈亏
        net_capital_change = (
            current_valuation.nav - previous_nav - current_valuation.pnl
        )

        result = NetCapitalChange(
            date=calculation_date,
            product_name=product_name,
            previous_nav=previous_nav,
            current_nav=current_valuation.nav,
            pnl=current_valuation.pnl,
            fund_inflow=fund_inflow,
            fund_outflow=fund_outflow,
            net_capital_change=net_capital_change,
            calculation_method="current_nav - previous_nav - pnl",
        )

        logger.info(
            f"Net capital change calculated for {product_name} on {calculation_date}:\n"
            f"  Previous NAV: {previous_nav:,.2f}\n"
            f"  Current NAV:  {current_valuation.nav:,.2f}\n"
            f"  PnL:          {current_valuation.pnl:,.2f}\n"
            f"  Net Change:   {net_capital_change:,.2f}\n"
            f"  (Fund Inflow: {fund_inflow:,.2f}, Outflow: {fund_outflow:,.2f})"
        )

        return result

    def sync_valuation_from_xuntou(
        self, product_name: str, valuation_date: date
    ) -> bool:
        """
        从迅投 API 同步估值到数据库。

        Args:
            product_name:    产品名称
            valuation_date:  估值日期

        Returns:
            是否成功
        """
        # 从迅投 API 获取估值
        valuation = self.valuation_source.fetch_valuation(product_name, valuation_date)

        if not valuation:
            logger.error(f"Failed to fetch valuation from XunTou: {product_name}")
            return False

        # 保存到数据库
        success = self.valuation_source.save_valuation(valuation)

        if success:
            logger.info(
                f"Valuation synced from XunTou: {product_name} on {valuation_date}, "
                f"NAV={valuation.nav:,.2f}, PnL={valuation.pnl:,.2f}"
            )
        else:
            logger.error(f"Failed to save valuation to database: {product_name}")

        return success
