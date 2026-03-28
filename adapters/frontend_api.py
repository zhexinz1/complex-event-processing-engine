"""
frontend_api.py — 前端 API 接口

提供 RESTful API 接口，供前端界面调用：
- 用户输入今日入金金额
- 查询当前持仓和权重
- 手动触发再平衡
- 查询历史订单和信号

设计原则：
  1. RESTful 风格：使用标准的 HTTP 方法和状态码
  2. 异步处理：长时间操作返回任务 ID，支持轮询查询
  3. 权限控制：预留认证和鉴权接口
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Optional

from cep.core.event_bus import EventBus
from cep.core.events import SignalEvent, SignalType
from rebalance.portfolio_context import PortfolioContext

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# API 请求/响应数据类
# ---------------------------------------------------------------------------

@dataclass
class FundInFlowRequest:
    """
    入金请求。

    Attributes:
        amount:      入金金额（元）
        remark:      备注信息
        operator:    操作人
        timestamp:   操作时间
    """
    amount: float
    remark: str = ""
    operator: str = "system"
    timestamp: datetime = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()


@dataclass
class RebalanceRequest:
    """
    手动再平衡请求。

    Attributes:
        reason:      触发原因
        new_capital: 新增资金（可选）
        operator:    操作人
    """
    reason: str = "manual"
    new_capital: float = 0.0
    operator: str = "system"


@dataclass
class APIResponse:
    """
    统一 API 响应格式。

    Attributes:
        success:  是否成功
        message:  响应消息
        data:     响应数据
        code:     状态码
    """
    success: bool
    message: str
    data: Any = None
    code: int = 200


# ---------------------------------------------------------------------------
# 前端 API 接口
# ---------------------------------------------------------------------------

class FrontendAPI:
    """
    前端 API 接口实现。

    提供 HTTP API 供前端调用，可以使用 Flask/FastAPI 等框架封装。

    使用示例（Flask）：
    ```python
    from flask import Flask, request, jsonify

    app = Flask(__name__)
    api = FrontendAPI(event_bus, portfolio_ctx)

    @app.route('/api/fund/inflow', methods=['POST'])
    def fund_inflow():
        data = request.json
        req = FundInFlowRequest(**data)
        resp = api.submit_fund_inflow(req)
        return jsonify(asdict(resp)), resp.code

    @app.route('/api/rebalance/trigger', methods=['POST'])
    def trigger_rebalance():
        data = request.json
        req = RebalanceRequest(**data)
        resp = api.trigger_rebalance(req)
        return jsonify(asdict(resp)), resp.code
    ```
    """

    def __init__(
        self,
        event_bus: EventBus,
        portfolio_ctx: PortfolioContext
    ):
        """
        初始化前端 API。

        Args:
            event_bus:      全局事件总线
            portfolio_ctx:  组合上下文
        """
        self.event_bus = event_bus
        self.portfolio_ctx = portfolio_ctx

        # 入金记录（实际应存储到数据库）
        self._fund_inflow_history: list[FundInFlowRequest] = []

        logger.info("FrontendAPI initialized")

    # -----------------------------------------------------------------------
    # 入金管理
    # -----------------------------------------------------------------------

    def submit_fund_inflow(self, request: FundInFlowRequest) -> APIResponse:
        """
        提交入金申请。

        前端用户输入今日入金金额后，调用此接口。
        系统会：
        1. 记录入金信息
        2. 发射 REBALANCE_REQUEST 信号
        3. 触发再平衡流程

        Args:
            request: 入金请求对象

        Returns:
            API 响应
        """
        try:
            # 校验入金金额
            if request.amount <= 0:
                return APIResponse(
                    success=False,
                    message="入金金额必须大于 0",
                    code=400
                )

            # 记录入金信息（实际应存储到数据库）
            self._fund_inflow_history.append(request)

            logger.info(
                f"Fund inflow submitted: amount={request.amount:,.2f}, "
                f"operator={request.operator}, remark={request.remark}"
            )

            # 发射再平衡请求信号
            signal = SignalEvent(
                source="FrontendAPI",
                symbol="",
                signal_type=SignalType.REBALANCE_REQUEST,
                payload={
                    "trigger_type": "fund_inflow",
                    "new_capital": request.amount,
                    "operator": request.operator,
                    "remark": request.remark
                },
                timestamp=datetime.now()
            )
            self.event_bus.publish(signal)

            return APIResponse(
                success=True,
                message=f"入金申请已提交，金额：{request.amount:,.2f} 元",
                data={
                    "amount": request.amount,
                    "timestamp": request.timestamp.isoformat()
                }
            )

        except Exception as e:
            logger.exception(f"Failed to submit fund inflow: {e}")
            return APIResponse(
                success=False,
                message=f"入金申请失败：{str(e)}",
                code=500
            )

    def get_fund_inflow_history(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> APIResponse:
        """
        查询入金历史记录。

        Args:
            start_date: 开始日期（可选）
            end_date:   结束日期（可选）

        Returns:
            API 响应，包含入金历史列表
        """
        try:
            # 过滤日期范围
            history = self._fund_inflow_history
            if start_date:
                history = [r for r in history if r.timestamp >= start_date]
            if end_date:
                history = [r for r in history if r.timestamp <= end_date]

            # 转换为字典列表
            data = [
                {
                    "amount": r.amount,
                    "remark": r.remark,
                    "operator": r.operator,
                    "timestamp": r.timestamp.isoformat()
                }
                for r in history
            ]

            return APIResponse(
                success=True,
                message=f"查询到 {len(data)} 条入金记录",
                data=data
            )

        except Exception as e:
            logger.exception(f"Failed to query fund inflow history: {e}")
            return APIResponse(
                success=False,
                message=f"查询失败：{str(e)}",
                code=500
            )

    # -----------------------------------------------------------------------
    # 再平衡管理
    # -----------------------------------------------------------------------

    def trigger_rebalance(self, request: RebalanceRequest) -> APIResponse:
        """
        手动触发再平衡。

        前端用户点击"立即再平衡"按钮时调用此接口。

        Args:
            request: 再平衡请求对象

        Returns:
            API 响应
        """
        try:
            logger.info(
                f"Manual rebalance triggered: reason={request.reason}, "
                f"new_capital={request.new_capital:,.2f}, operator={request.operator}"
            )

            # 发射再平衡请求信号
            signal = SignalEvent(
                source="FrontendAPI",
                symbol="",
                signal_type=SignalType.REBALANCE_REQUEST,
                payload={
                    "trigger_type": request.reason,
                    "new_capital": request.new_capital,
                    "operator": request.operator
                },
                timestamp=datetime.now()
            )
            self.event_bus.publish(signal)

            return APIResponse(
                success=True,
                message="再平衡请求已提交",
                data={
                    "reason": request.reason,
                    "new_capital": request.new_capital,
                    "timestamp": datetime.now().isoformat()
                }
            )

        except Exception as e:
            logger.exception(f"Failed to trigger rebalance: {e}")
            return APIResponse(
                success=False,
                message=f"再平衡触发失败：{str(e)}",
                code=500
            )

    # -----------------------------------------------------------------------
    # 持仓和权重查询
    # -----------------------------------------------------------------------

    def get_portfolio_status(self) -> APIResponse:
        """
        查询当前组合状态。

        返回：
        - 总净值
        - 可用资金
        - 各品种持仓
        - 各品种当前权重 vs 目标权重

        Returns:
            API 响应，包含组合状态信息
        """
        try:
            # 获取账户信息
            total_nav = self.portfolio_ctx.get_total_nav()
            available_cash = self.portfolio_ctx.get_available_cash()
            margin_used = self.portfolio_ctx.get_margin_used()

            # 获取持仓信息
            positions = self.portfolio_ctx.get_all_positions()
            position_list = [
                {
                    "symbol": pos.symbol,
                    "quantity": pos.quantity,
                    "avg_price": pos.avg_price,
                    "market_value": pos.market_value,
                    "current_weight": self.portfolio_ctx.calculate_current_weight(pos.symbol),
                    "target_weight": self.portfolio_ctx.get_target_weight(pos.symbol)
                }
                for pos in positions.values()
            ]

            return APIResponse(
                success=True,
                message="组合状态查询成功",
                data={
                    "account": {
                        "total_nav": total_nav,
                        "available_cash": available_cash,
                        "margin_used": margin_used
                    },
                    "positions": position_list,
                    "timestamp": datetime.now().isoformat()
                }
            )

        except Exception as e:
            logger.exception(f"Failed to query portfolio status: {e}")
            return APIResponse(
                success=False,
                message=f"查询失败：{str(e)}",
                code=500
            )

    def get_weight_deviation(self) -> APIResponse:
        """
        查询权重偏离情况。

        返回各品种的当前权重与目标权重的偏离度。

        Returns:
            API 响应，包含权重偏离信息
        """
        try:
            # 计算所有品种的权重偏离
            target_weights = self.portfolio_ctx.get_all_target_weights()
            current_weights = self.portfolio_ctx.calculate_all_current_weights()

            deviations = []
            for symbol in target_weights.keys():
                target = target_weights.get(symbol, 0.0)
                current = current_weights.get(symbol, 0.0)
                deviation = current - target

                deviations.append({
                    "symbol": symbol,
                    "target_weight": target,
                    "current_weight": current,
                    "deviation": deviation,
                    "deviation_pct": (deviation / target * 100) if target > 0 else 0.0
                })

            # 按偏离度绝对值排序
            deviations.sort(key=lambda x: abs(x["deviation"]), reverse=True)

            return APIResponse(
                success=True,
                message=f"查询到 {len(deviations)} 个品种的权重偏离",
                data={
                    "deviations": deviations,
                    "timestamp": datetime.now().isoformat()
                }
            )

        except Exception as e:
            logger.exception(f"Failed to query weight deviation: {e}")
            return APIResponse(
                success=False,
                message=f"查询失败：{str(e)}",
                code=500
            )

    # -----------------------------------------------------------------------
    # 健康检查
    # -----------------------------------------------------------------------

    def health_check(self) -> APIResponse:
        """
        健康检查接口。

        Returns:
            API 响应
        """
        return APIResponse(
            success=True,
            message="系统运行正常",
            data={
                "status": "healthy",
                "timestamp": datetime.now().isoformat()
            }
        )
