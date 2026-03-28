# 外部接口留白总结

## ✅ 已完成的接口留白

经过重构，CEP 系统现在已经完整预留了所有关键的外部接口：

### 1. 行情接入 ✅

**位置**: `adapters/market_gateway.py`

**抽象接口**:
```python
class MarketGateway(ABC):
    def connect(self) -> bool
    def disconnect(self) -> None
    def subscribe(self, symbols: list[str]) -> bool
    def unsubscribe(self, symbols: list[str]) -> bool
```

**已实现的适配器**:
- ✅ `CTPMarketGateway` - CTP 期货行情网关（预留，待实现）
- ✅ `MockMarketGateway` - 模拟行情网关（已实现，用于测试）

**待对接**:
- [ ] 引入 CTP SDK（openctp 或 vnpy）
- [ ] 实现 XTP 股票行情网关
- [ ] 实现 WebSocket 行情推送

---

### 2. 数据库读取权重配置 ✅

**位置**: `adapters/config_source.py`

**抽象接口**:
```python
class ConfigSource(ABC):
    def load_target_weights(self, strategy_id: str) -> dict[str, float]
    def save_target_weights(self, strategy_id: str, weights: dict[str, float]) -> bool
    def load_contract_info(self, symbol: str) -> Optional[dict]
```

**已实现的适配器**:
- ✅ `DatabaseConfigSource` - 数据库配置源（预留，待实现）
- ✅ `FileConfigSource` - 文件配置源（已实现，支持 JSON）

**数据库表结构**:
```sql
-- 目标权重配置表
CREATE TABLE target_weights (
    id INT PRIMARY KEY AUTO_INCREMENT,
    strategy_id VARCHAR(50) NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    weight DECIMAL(10, 6) NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_strategy_symbol (strategy_id, symbol)
);

-- 合约信息表
CREATE TABLE contract_info (
    symbol VARCHAR(20) PRIMARY KEY,
    multiplier DECIMAL(10, 2) NOT NULL,
    min_tick DECIMAL(10, 6) NOT NULL,
    margin_rate DECIMAL(10, 6) NOT NULL,
    exchange VARCHAR(20),
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**待对接**:
- [ ] 引入数据库驱动（pymysql 或 psycopg2）
- [ ] 实现数据库连接池
- [ ] 实现配置热更新机制

---

### 3. 前端界面入金接口 ✅

**位置**: `adapters/frontend_api.py`

**核心接口**:
```python
class FrontendAPI:
    def submit_fund_inflow(self, request: FundInFlowRequest) -> APIResponse
        """用户输入今日入金金额"""

    def get_fund_inflow_history(self, start_date, end_date) -> APIResponse
        """查询入金历史"""

    def trigger_rebalance(self, request: RebalanceRequest) -> APIResponse
        """手动触发再平衡"""

    def get_portfolio_status(self) -> APIResponse
        """查询当前持仓和权重"""

    def get_weight_deviation(self) -> APIResponse
        """查询权重偏离情况"""
```

**使用示例（Flask）**:
```python
from flask import Flask, request, jsonify
from adapters.frontend_api import FrontendAPI, FundInFlowRequest

app = Flask(__name__)
api = FrontendAPI(event_bus, portfolio_ctx)

@app.route('/api/fund/inflow', methods=['POST'])
def fund_inflow():
    data = request.json
    req = FundInFlowRequest(
        amount=data['amount'],
        remark=data.get('remark', ''),
        operator=data.get('operator', 'system')
    )
    resp = api.submit_fund_inflow(req)
    return jsonify(asdict(resp)), resp.code
```

**API 端点列表**:
| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/fund/inflow` | POST | 提交入金申请 |
| `/api/fund/history` | GET | 查询入金历史 |
| `/api/rebalance/trigger` | POST | 手动触发再平衡 |
| `/api/portfolio/status` | GET | 查询组合状态 |
| `/api/portfolio/deviation` | GET | 查询权重偏离 |
| `/api/health` | GET | 健康检查 |

**待对接**:
- [ ] 添加用户认证和鉴权
- [ ] 实现 API 限流
- [ ] 添加 WebSocket 推送
- [ ] 添加 Swagger 文档

---

### 4. 下单到迅投 GT ✅

**位置**: `adapters/order_gateway.py`

**抽象接口**:
```python
class OrderGateway(ABC):
    def connect(self) -> bool
    def disconnect(self) -> None
    def submit_order(self, symbol, side, quantity, price) -> Optional[str]
    def cancel_order(self, order_id: str) -> bool
    def query_order(self, order_id: str) -> Optional[Order]
    def set_order_callback(self, callback: Callable[[Order], None]) -> None
```

**已实现的适配器**:
- ✅ `XunTouGTGateway` - 迅投 GT 柜台网关（预留，待实现）
- ✅ `MockOrderGateway` - 模拟订单网关（已实现，用于测试）

**订单状态流转**:
```
PENDING → SUBMITTED → PARTIAL_FILLED → FILLED
                   ↘ CANCELLED
                   ↘ REJECTED
                   ↘ ERROR
```

**待对接**:
- [ ] 引入迅投 GT SDK
- [ ] 实现订单提交、撤单、查询接口
- [ ] 实现订单回报处理
- [ ] 添加订单风控前置校验
- [ ] 实现订单持久化

---

## 📁 新增的目录结构

```
CEP/
├── adapters/                     # 外部接口适配器层（新增）
│   ├── __init__.py
│   ├── market_gateway.py        # 行情网关
│   ├── config_source.py         # 配置数据源
│   ├── order_gateway.py         # 订单执行网关
│   └── frontend_api.py          # 前端 API 接口
│
├── config/                       # 配置文件目录（新增）
│   └── strategy_config.json     # 策略配置文件
│
├── cep/                          # 核心框架
├── rebalance/                    # 再平衡模块
├── nlp/                          # 自然语言解析
├── examples/                     # 示例代码
│   └── full_integration_example.py  # 完整集成示例（新增）
├── tests/                        # 测试代码
└── docs/                         # 文档
    └── INTEGRATION_GUIDE.md     # 集成指南（新增）
```

---

## 🎯 设计原则

1. **抽象接口 + 具体实现** - 所有外部接口都采用抽象基类定义，方便替换和扩展
2. **依赖注入** - 通过构造函数注入依赖，避免全局单例
3. **事件驱动** - 外部数据通过事件总线流转，保持模块解耦
4. **可测试性** - 提供 Mock 实现，支持单元测试和集成测试
5. **可插拔** - 支持运行时切换不同的适配器实现

---

## 📝 使用示例

完整的系统集成示例请参见：`examples/full_integration_example.py`

运行示例：
```bash
export PYTHONPATH=/home/ubuntu/CEP
python3 examples/full_integration_example.py
```

---

## 📚 相关文档

- `docs/INTEGRATION_GUIDE.md` - 详细的外部接口对接指南
- `docs/DIRECTORY_STRUCTURE.md` - 项目目录结构说明
- `REFACTORING_SUMMARY.md` - 重构总结

---

## ✅ 总结

所有关键的外部接口都已经完整预留：

| 接口 | 状态 | 文件位置 |
|------|------|----------|
| ✅ 行情接入 | 已留白 | `adapters/market_gateway.py` |
| ✅ 数据库读取权重 | 已留白 | `adapters/config_source.py` |
| ✅ 前端入金接口 | 已留白 | `adapters/frontend_api.py` |
| ✅ 下单到迅投 GT | 已留白 | `adapters/order_gateway.py` |

**下一步工作**：
1. 引入相应的 SDK（CTP、迅投 GT、数据库驱动）
2. 实现具体的适配器逻辑
3. 添加单元测试和集成测试
4. 部署前端界面（React/Vue + Flask/FastAPI）
