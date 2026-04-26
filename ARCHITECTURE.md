# CEP 系统架构文档

## 系统组件概览

### 1. 行情接收模块
**文件**: `adapters/market_gateway.py`
- **功能**: 从招商期货仿真 CTP 接收实时行情
- **配置**:
  - 前置地址: `tcp://218.17.194.115:41413`
  - BrokerID: `8060`
  - 用户ID: `99683265`
  - 密码: `456123`
- **输出**: 发布 `TickEvent` 和 `BarEvent` 到事件总线
- **测试脚本**: `query_market.py`

### 2. 迅投交易模块

#### 2.1 下单服务
**文件**: `adapters/xt_order_service.py`
- **功能**: 封装迅投 XtTraderApi 下单功能
- **特性**:
  - 单例模式，自动连接管理
  - 支持股票交易（买入/卖出）
  - 支持期货交易（开多/平多/开空/平空）
  - 同步下单接口
- **配置**:
  - 服务器: `8.166.130.204:65300`
  - 用户名: `system_trade`
  - 密码: `my123456@`
  - 账号: `90102870` (招商期货仿真CTP)
- **测试脚本**: `test_xt_order.py`, `test_market_and_order.py`

#### 2.2 查询服务
**文件**: `query_cash.py`
- **功能**: 查询账号资金信息
- **输出**: 可用资金、总资产、持仓盈亏等

### 3. Web 前端与 API

#### 3.1 Flask 后端
**文件**: `adapters/flask_app.py`
- **端口**: `5000`
- **主要 API**:

**目标仓位配置**:
- `GET /api/weights` - 查询目标权重
- `POST /api/weights` - 新增/更新目标权重
- `DELETE /api/weights/<id>` - 删除权重配置

**产品管理**:
- `GET /api/products/list` - 获取产品列表
- `POST /api/products/add` - 添加产品
- `POST /api/products/update` - 更新产品信息

**净入金流程**:
- `POST /api/fund/inflow` - 提交净入金并计算订单
- `GET /api/orders/pending` - 查询待确认订单
- `POST /api/orders/update` - 手动调整订单数量
- `POST /api/orders/confirm` - 确认订单并执行

**迅投下单**:
- `POST /api/xt/place_order` - 迅投下单接口

#### 3.2 前端页面
**目录**: `frontend/`
- `index.html` - 主页（目标仓位配置 + 产品管理）
- `fund-inflow.html` - 净入金录入页面
- `order-confirm.html` - 订单确认页面

### 4. 数据库层

#### 4.1 DAO 层
**文件**: `database/dao.py`
- 封装所有数据库操作
- 支持事务管理

#### 4.2 数据模型
**文件**: `database/models.py`
- `Product` - 产品信息（含迅投账号、资金账号）
- `TargetAllocation` - 目标权重配置
- `FundInflow` - 净入金记录
- `PendingOrder` - 待确认订单
- `FractionalShare` - 留白数据

### 5. 再平衡引擎
**文件**: `rebalance/rebalance_engine.py`
- **功能**: 5步计算法
  1. 新目标 NAV = 当前 NAV + 净入金
  2. 目标市值 = 新 NAV × 目标权重
  3. 市值差 = 目标市值 - 当前市值
  4. 理论数量变化 = 市值差 / (价格 × 合约乘数)
  5. 离散化取整 → 整数订单数量

## 完整业务流程

### 净入金下单流程

```
1. 用户在前端录入净入金
   ↓
2. POST /api/fund/inflow
   - 读取产品配置（杠杆率、账号）
   - 读取目标权重配置
   - 读取当前持仓（TODO: 需要集成迅投持仓查询）
   - 调用 RebalanceEngine 计算订单
   ↓
3. 订单保存到 pending_orders 表
   ↓
4. 用户在订单确认页面查看
   - GET /api/orders/pending
   ↓
5. 用户可手动调整订单数量
   - POST /api/orders/update
   ↓
6. 用户确认订单
   - POST /api/orders/confirm
   - 调用 XtOrderService.place_order() 下单
   - 更新订单状态为 EXECUTED
   - 更新留白数据
```

## 待完善功能

1. **持仓查询集成**
   - 需要添加迅投持仓查询 API
   - 在计算订单前获取当前持仓

2. **订单状态跟踪**
   - 订单成交回报
   - 订单状态更新

3. **行情价格获取**
   - 当前使用固定价格
   - 需要集成 CTP 行情获取最新价

4. **错误处理**
   - 下单失败重试机制
   - 异常情况告警

## 启动命令

```bash
# 启动 Flask 服务
uv run python -m adapters.flask_app

# 测试行情接收
uv run python query_market.py

# 测试资金查询
uv run python query_cash.py

# 测试下单
uv run python test_xt_order.py

# 测试完整流程（行情+下单）
uv run python test_market_and_order.py
```

## 访问地址

- 前端主页: http://43.160.206.71:5000
- 净入金页面: http://43.160.206.71:5000/fund-inflow.html
- 订单确认页面: http://43.160.206.71:5000/order-confirm.html
