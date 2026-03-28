# 外部接口集成指南

本文档说明如何对接 CEP 系统的外部接口。

## 概述

CEP 系统通过适配器模式（Adapter Pattern）提供了四大外部接口：

1. **行情网关** (`MarketGateway`) - 接入实时行情数据
2. **配置数据源** (`ConfigSource`) - 读取权重配置和合约信息
3. **订单执行网关** (`OrderGateway`) - 发送订单到柜台系统
4. **前端 API** (`FrontendAPI`) - 提供 HTTP 接口供前端调用

所有接口都位于 `adapters/` 目录下。

---

## 1. 行情网关接入

### 接口定义

```python
from adapters.market_gateway import MarketGateway

class MarketGateway(ABC):
    def connect(self) -> bool:
        """连接到行情服务器"""

    def disconnect(self) -> None:
        """断开行情连接"""

    def subscribe(self, symbols: list[str]) -> bool:
        """订阅行情"""

    def unsubscribe(self, symbols: list[str]) -> bool:
        """取消订阅"""
```

### 实现示例：CTP 行情网关

```python
from adapters.market_gateway import CTPMarketGateway

# 初始化 CTP 行情网关
market_gateway = CTPMarketGateway(
    event_bus=event_bus,
    front_addr="tcp://180.168.146.187:10131",
    broker_id="9999",
    user_id="your_user_id",
    password="your_password"
)

# 连接并订阅
market_gateway.connect()
market_gateway.subscribe(["AU2606", "P2609", "RB2610"])
```

### 对接要点

1. **继承 `MarketGateway` 基类**
2. **实现 4 个抽象方法**：`connect()`, `disconnect()`, `subscribe()`, `unsubscribe()`
3. **在收到行情数据时调用 `_publish_tick()` 或 `_publish_bar()`** 发布到事件总线
4. **处理断线重连逻辑**

### TODO 清单

- [ ] 引入 CTP SDK（openctp 或 vnpy）
- [ ] 实现 `OnRtnDepthMarketData` 回调
- [ ] 实现断线重连机制
- [ ] 添加行情数据校验（价格合理性检查）

---

## 2. 配置数据源对接

### 接口定义

```python
from adapters.config_source import ConfigSource

class ConfigSource(ABC):
    def load_target_weights(self, strategy_id: str) -> dict[str, float]:
        """加载目标权重配置"""

    def save_target_weights(self, strategy_id: str, weights: dict[str, float]) -> bool:
        """保存目标权重配置"""

    def load_contract_info(self, symbol: str) -> Optional[dict]:
        """加载合约基础信息"""
```

### 实现示例：数据库配置源

```python
from adapters.config_source import DatabaseConfigSource

# 初始化数据库配置源
config_source = DatabaseConfigSource(
    host="localhost",
    port=3306,
    database="cep_config",
    user="root",
    password="password",
    db_type="mysql"
)

# 加载配置
target_weights = config_source.load_target_weights("strategy_001")
contract_info = config_source.load_contract_info("AU2606")
```

### 数据库表结构

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

### TODO 清单

- [ ] 引入数据库驱动（pymysql 或 psycopg2）
- [ ] 实现数据库连接池
- [ ] 实现配置热更新（监听数据库变更）
- [ ] 添加配置缓存机制

---

## 3. 订单执行网关对接

### 接口定义

```python
from adapters.order_gateway import OrderGateway

class OrderGateway(ABC):
    def connect(self) -> bool:
        """连接到柜台系统"""

    def disconnect(self) -> None:
        """断开柜台连接"""

    def submit_order(self, symbol: str, side: OrderSide, quantity: float, price: float) -> Optional[str]:
        """提交订单"""

    def cancel_order(self, order_id: str) -> bool:
        """撤销订单"""

    def query_order(self, order_id: str) -> Optional[Order]:
        """查询订单状态"""
```

### 实现示例：迅投 GT 网关

```python
from adapters.order_gateway import XunTouGTGateway

# 初始化迅投 GT 网关
order_gateway = XunTouGTGateway(
    server_addr="tcp://192.168.1.100:8888",
    account_id="your_account",
    password="your_password",
    app_id="your_app_id"
)

# 连接并下单
order_gateway.connect()

# 设置订单回调
def on_order_update(order):
    print(f"订单更新: {order.order_id} {order.status}")

order_gateway.set_order_callback(on_order_update)

# 提交订单
order_id = order_gateway.submit_order(
    symbol="AU2606",
    side=OrderSide.BUY,
    quantity=10,
    price=580.50
)
```

### 对接要点

1. **继承 `OrderGateway` 基类**
2. **实现 5 个抽象方法**
3. **在收到订单回报时调用 `_notify_order_update()`** 通知订阅者
4. **处理订单状态转换**：PENDING → SUBMITTED → FILLED/CANCELLED/REJECTED

### TODO 清单

- [ ] 引入迅投 GT SDK
- [ ] 实现订单提交、撤单、查询接口
- [ ] 实现订单回报处理
- [ ] 添加订单风控前置校验
- [ ] 实现订单持久化（存储到数据库）

---

## 4. 前端 API 接口

### 接口定义

```python
from adapters.frontend_api import FrontendAPI

class FrontendAPI:
    def submit_fund_inflow(self, request: FundInFlowRequest) -> APIResponse:
        """提交入金申请"""

    def trigger_rebalance(self, request: RebalanceRequest) -> APIResponse:
        """手动触发再平衡"""

    def get_portfolio_status(self) -> APIResponse:
        """查询组合状态"""

    def get_weight_deviation(self) -> APIResponse:
        """查询权重偏离"""
```

### 使用示例：Flask 封装

```python
from flask import Flask, request, jsonify
from adapters.frontend_api import FrontendAPI, FundInFlowRequest

app = Flask(__name__)
api = FrontendAPI(event_bus, portfolio_ctx)

@app.route('/api/fund/inflow', methods=['POST'])
def fund_inflow():
    """用户输入入金金额"""
    data = request.json
    req = FundInFlowRequest(
        amount=data['amount'],
        remark=data.get('remark', ''),
        operator=data.get('operator', 'system')
    )
    resp = api.submit_fund_inflow(req)
    return jsonify(asdict(resp)), resp.code

@app.route('/api/rebalance/trigger', methods=['POST'])
def trigger_rebalance():
    """手动触发再平衡"""
    data = request.json
    req = RebalanceRequest(
        reason=data.get('reason', 'manual'),
        new_capital=data.get('new_capital', 0.0),
        operator=data.get('operator', 'system')
    )
    resp = api.trigger_rebalance(req)
    return jsonify(asdict(resp)), resp.code

@app.route('/api/portfolio/status', methods=['GET'])
def portfolio_status():
    """查询组合状态"""
    resp = api.get_portfolio_status()
    return jsonify(asdict(resp)), resp.code

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
```

### API 端点列表

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/fund/inflow` | POST | 提交入金申请 |
| `/api/fund/history` | GET | 查询入金历史 |
| `/api/rebalance/trigger` | POST | 手动触发再平衡 |
| `/api/portfolio/status` | GET | 查询组合状态 |
| `/api/portfolio/deviation` | GET | 查询权重偏离 |
| `/api/health` | GET | 健康检查 |

### TODO 清单

- [ ] 添加用户认证和鉴权
- [ ] 实现 API 限流（防止恶意请求）
- [ ] 添加 API 日志记录
- [ ] 实现 WebSocket 推送（实时更新）
- [ ] 添加 API 文档（Swagger/OpenAPI）

---

## 完整集成示例

参见 `examples/full_integration_example.py`，展示了如何将所有外部接口集成到系统中。

运行示例：

```bash
# 设置 PYTHONPATH
export PYTHONPATH=/home/ubuntu/CEP

# 运行完整集成示例
python3 examples/full_integration_example.py
```

---

## 接口留白总结

| 接口 | 状态 | 说明 |
|------|------|------|
| ✅ 行情网关 | 已留白 | 提供抽象接口，支持 CTP/XTP/模拟行情 |
| ✅ 配置数据源 | 已留白 | 支持数据库/文件/远程配置中心 |
| ✅ 订单执行网关 | 已留白 | 支持迅投 GT/CTP/模拟柜台 |
| ✅ 前端 API | 已留白 | 提供 RESTful 接口，支持 Flask/FastAPI 封装 |

所有接口都采用**抽象基类 + 具体实现**的设计模式，方便后续扩展和替换。
