# 接口预留总结文档

## 概述

本文档总结了为数据库集成、前端配置和迅投 GT API 对接预留的所有接口。

---

## 一、目标权重配置接口

### 1.1 数据库表结构

```sql
CREATE TABLE target_weights (
    date DATE NOT NULL,
    product_name VARCHAR(100) NOT NULL,
    symbol VARCHAR(50) NOT NULL,
    target_weight DECIMAL(10,4) NOT NULL,
    deviation_threshold DECIMAL(10,4) NOT NULL,
    algorithm VARCHAR(20) NOT NULL,
    PRIMARY KEY (date, product_name, symbol)
);

-- 示例数据
INSERT INTO target_weights VALUES
  ('2026-03-30', '明钺全天候1号', 'AU2606.SHF', 0.2561, 0.03, 'TWAP'),
  ('2026-03-30', '明钺全天候1号', 'IC2606.CFE', 0.2048, 0.05, 'TWAP'),
  ('2026-03-30', '明钺全天候1号', 'T2605.CFE', 1.2476, 0.02, 'TWAP'),
  ('2026-03-30', '明钺全天候1号', 'M2609.DCE', 0.0781, 0.04, 'TWAP');
```

### 1.2 配置加载器接口

**文件位置**: `rebalance/target_config.py`

```python
class DatabaseConfigLoader:
    """数据库配置加载器（预留接口）"""

    def __init__(self, db_connection_string: str):
        """
        初始化数据库配置加载器。

        Args:
            db_connection_string: 数据库连接字符串
                例如: "mysql://user:pass@localhost/db"
        """
        # TODO: 实现数据库连接
        pass

    def load_product_config(
        self,
        product_name: str,
        config_date: Optional[date] = None
    ) -> Optional[ProductConfig]:
        """
        从数据库加载产品配置。

        SQL 示例:
        SELECT date, product_name, symbol, target_weight,
               deviation_threshold, algorithm
        FROM target_weights
        WHERE product_name = ? AND date = ?
        ORDER BY date DESC
        """
        # TODO: 实现数据库查询逻辑
        pass

    def save_product_config(self, config: ProductConfig) -> bool:
        """保存产品配置到数据库"""
        # TODO: 实现数据库插入/更新逻辑
        pass
```

### 1.3 使用示例

```python
from rebalance import DatabaseConfigLoader

# 创建数据库加载器
loader = DatabaseConfigLoader("mysql://user:pass@localhost/trading_db")

# 加载配置
config = loader.load_product_config("明钺全天候1号")

# 获取目标权重和偏离阈值
target_weights = config.get_target_weights()
deviation_thresholds = config.get_deviation_thresholds()
```

---

## 二、持仓数据源接口

### 2.1 迅投 GT API 接口

**文件位置**: `rebalance/position_source.py`

```python
class XunTouPositionSource:
    """迅投 GT 持仓数据源（预留接口）"""

    def __init__(
        self,
        server_addr: str,
        account_id: str,
        password: str,
        app_id: str
    ):
        """
        初始化迅投 GT 持仓数据源。

        Args:
            server_addr: 服务器地址
            account_id:  账户 ID
            password:    密码
            app_id:      应用 ID
        """
        # TODO: 初始化迅投 GT API
        # self.gt_api = GTApi()
        pass

    def connect(self) -> bool:
        """连接到迅投 GT 服务器"""
        # TODO: 实现迅投 GT 连接逻辑
        # self.gt_api.connect(self.server_addr, self.account_id, self.password)
        pass

    def fetch_positions(self) -> dict[str, Position]:
        """
        从迅投 GT API 获取所有持仓信息。

        Returns:
            持仓字典 {symbol: Position}

        实现示例:
        positions = {}
        position_list = self.gt_api.query_positions()
        for pos_data in position_list:
            position = Position(
                symbol=pos_data['symbol'],
                quantity=pos_data['quantity'],
                avg_price=pos_data['avg_price'],
                market_value=pos_data['market_value']
            )
            positions[position.symbol] = position
        return positions
        """
        # TODO: 调用迅投 GT API 查询持仓
        pass

    def fetch_account_info(self) -> dict[str, float]:
        """
        从迅投 GT API 获取账户信息。

        Returns:
            账户信息字典，包含：
            - total_nav: 总净值
            - available_cash: 可用资金
            - margin_used: 已用保证金

        实现示例:
        account_data = self.gt_api.query_account()
        return {
            'total_nav': account_data['total_nav'],
            'available_cash': account_data['available_cash'],
            'margin_used': account_data['margin_used']
        }
        """
        # TODO: 调用迅投 GT API 查询账户资金
        pass
```

### 2.2 PortfolioContext 集成

**文件位置**: `rebalance/portfolio_context.py`

```python
class PortfolioContext:
    """组合级上下文"""

    def __init__(self, position_source=None):
        """
        初始化组合上下文。

        Args:
            position_source: 持仓数据源（可选）
                           例如：XunTouPositionSource, CTPPositionSource
        """
        self._position_source = position_source

    def set_position_source(self, position_source) -> None:
        """设置持仓数据源"""
        self._position_source = position_source

    def sync_positions_from_source(self) -> bool:
        """
        从外部数据源同步持仓信息。

        从迅投 GT API、CTP API 等外部系统拉取最新持仓，
        并更新到 PortfolioContext 中。

        Returns:
            同步是否成功
        """
        if not self._position_source:
            return False

        # 从数据源获取持仓
        positions = self._position_source.fetch_positions()
        self._positions = positions

        # 同步账户信息
        account_info = self._position_source.fetch_account_info()
        self._total_nav = account_info.get('total_nav', 0.0)
        self._available_cash = account_info.get('available_cash', 0.0)
        self._margin_used = account_info.get('margin_used', 0.0)

        return True
```

### 2.3 使用示例

```python
from rebalance import PortfolioContext, XunTouPositionSource

# 1. 创建迅投 GT 持仓数据源
position_source = XunTouPositionSource(
    server_addr="tcp://xxx.xxx.xxx.xxx:xxxx",
    account_id="your_account_id",
    password="your_password",
    app_id="your_app_id"
)
position_source.connect()

# 2. 创建组合上下文并设置数据源
portfolio_ctx = PortfolioContext(position_source=position_source)

# 3. 定期同步持仓（如每 5 秒）
import time
while True:
    success = portfolio_ctx.sync_positions_from_source()
    if success:
        print("持仓同步成功")
    time.sleep(5)
```

---

## 三、再平衡触发器

### 3.1 偏离度触发器（基于实时持仓）

**文件位置**: `rebalance/rebalance_triggers.py`

```python
class PortfolioDeviationTrigger(BaseTrigger):
    """
    组合偏离触发器（基于 TickEvent 实时监控版本）。

    特性：
    - 监听 CTP 实时行情 Tick 事件
    - 每次收到 Tick 自动更新价格
    - 基于最新价格和实时持仓计算偏离度
    - 支持每个资产独立配置偏离阈值
    - 60 秒防抖冷却期
    """

    def __init__(
        self,
        event_bus: EventBus,
        trigger_id: str,
        portfolio_ctx: PortfolioContext,
        threshold: float = 0.03,
        symbol_thresholds: Optional[dict[str, float]] = None,
        cooldown: float = 60.0,
    ):
        """
        初始化组合偏离触发器。

        Args:
            event_bus:         全局事件总线
            trigger_id:        触发器 ID
            portfolio_ctx:     组合上下文（包含实时持仓）
            threshold:         全局偏离阈值（默认 3%）
            symbol_thresholds: 每个资产的独立偏离阈值
                              例如：{"AU2606.SHF": 0.03, "IC2606.CFE": 0.05}
            cooldown:          检查冷却期（秒，默认 60）
        """
```

**使用场景**：
- 盘中实时监控组合偏离度
- 当任一资产偏离超过阈值时触发再平衡
- 基于从迅投 GT API 同步的实时持仓计算

### 3.2 月初定时触发器（强制再平衡）

**文件位置**: `rebalance/rebalance_triggers.py`

```python
class MonthlyRebalanceTrigger(BaseTrigger):
    """
    月初定期触发器。

    特性：
    - 监听 TimerEvent（如每月 1 号 9:30）
    - 无条件发射 REBALANCE_REQUEST 信号
    - 不管偏离度是多少，强制拉回基准权重
    """

    def __init__(
        self,
        event_bus: EventBus,
        trigger_id: str,
        timer_id: str,
    ):
        """
        初始化月初定期触发器。

        Args:
            event_bus:  全局事件总线
            trigger_id: 触发器 ID
            timer_id:   监听的定时器 ID（如 "MONTHLY_REBALANCE_0930"）
        """
```

**使用场景**：
- 每月初强制再平衡，拉回基准权重
- 不管当前偏离度是多少，都会触发
- 需要定时器模块定期发送 `TimerEvent`

### 3.3 定时器模块（需要实现）

**预留接口**：需要实现一个定时器模块，定期发送 `TimerEvent`

```python
import threading
from datetime import datetime
from cep.core.event_bus import EventBus
from cep.core.events import TimerEvent

class SimpleTimer:
    """简单定时器（预留接口）"""

    def __init__(self, event_bus: EventBus, timer_id: str, interval: int):
        """
        初始化定时器。

        Args:
            event_bus: 事件总线
            timer_id:  定时器 ID
            interval:  触发间隔（秒）
        """
        self.event_bus = event_bus
        self.timer_id = timer_id
        self.interval = interval
        self._running = False
        self._thread = None

    def start(self):
        """启动定时器"""
        self._running = True
        self._thread = threading.Thread(target=self._run)
        self._thread.daemon = True
        self._thread.start()

    def _run(self):
        """定时器主循环"""
        while self._running:
            time.sleep(self.interval)
            self.event_bus.publish(TimerEvent(
                timer_id=self.timer_id,
                fired_at=datetime.now()
            ))

    def stop(self):
        """停止定时器"""
        self._running = False
```

**使用示例**：

```python
# 创建月初定时器（每月 1 号 9:30 触发）
# TODO: 实现更精确的定时逻辑（cron 表达式）
timer = SimpleTimer(
    event_bus=bus,
    timer_id="MONTHLY_REBALANCE_0930",
    interval=86400  # 每天检查一次
)
timer.start()

# 创建月初触发器
monthly_trigger = MonthlyRebalanceTrigger(
    event_bus=bus,
    trigger_id="monthly_rebalance",
    timer_id="MONTHLY_REBALANCE_0930"
)
monthly_trigger.register()
```

---

## 四、前端 API 接口

### 4.1 配置管理接口

```python
# 获取产品配置
GET /api/config/{product_name}

Response:
{
  "product_name": "明钺全天候1号",
  "date": "2026-03-30",
  "assets": [
    {
      "symbol": "AU2606.SHF",
      "target_weight": 0.2561,
      "deviation_threshold": 0.03,
      "algorithm": "TWAP"
    },
    ...
  ],
  "global_threshold": 0.05
}

# 更新产品配置
POST /api/config/{product_name}

Request:
{
  "date": "2026-03-30",
  "assets": [...],
  "global_threshold": 0.05
}

Response:
{
  "success": true,
  "message": "配置已更新"
}
```

### 4.2 实时偏离度监控接口

```python
# 获取实时偏离度
GET /api/deviation/{product_name}

Response:
{
  "product_name": "明钺全天候1号",
  "timestamp": "2026-03-30T14:30:00",
  "deviations": [
    {
      "symbol": "AU2606.SHF",
      "target_weight": 0.2561,
      "current_weight": 0.2890,
      "deviation": 0.0329,
      "threshold": 0.03,
      "exceeded": true
    },
    ...
  ]
}

# WebSocket 实时推送
WebSocket /ws/deviation

Message:
{
  "type": "deviation_update",
  "product_name": "明钺全天候1号",
  "symbol": "AU2606.SHF",
  "deviation": 0.0329,
  "exceeded": true
}
```

---

## 五、完整集成流程

### 5.1 系统启动流程

```python
# 1. 创建事件总线
bus = EventBus()

# 2. 创建迅投 GT 持仓数据源
position_source = XunTouPositionSource(
    server_addr="tcp://xxx.xxx.xxx.xxx:xxxx",
    account_id="your_account_id",
    password="your_password",
    app_id="your_app_id"
)
position_source.connect()

# 3. 创建组合上下文
portfolio_ctx = PortfolioContext(position_source=position_source)

# 4. 从数据库加载配置
config_loader = DatabaseConfigLoader("mysql://user:pass@localhost/db")
config = config_loader.load_product_config("明钺全天候1号")

# 5. 设置目标权重
portfolio_ctx.set_target_weights(config.get_target_weights())

# 6. 注册合约信息
for asset in config.assets:
    contract = ContractInfo(asset.symbol, multiplier=..., margin_rate=...)
    portfolio_ctx.register_contract(contract)

# 7. 创建再平衡处理器
rebalance_handler = RebalanceHandler(bus, portfolio_ctx)
rebalance_handler.register()

# 8. 创建偏离触发器
deviation_trigger = PortfolioDeviationTrigger(
    event_bus=bus,
    trigger_id="portfolio_deviation",
    portfolio_ctx=portfolio_ctx,
    threshold=config.global_threshold,
    symbol_thresholds=config.get_deviation_thresholds(),
    cooldown=60.0
)
deviation_trigger.register()

# 9. 创建月初定时触发器
monthly_trigger = MonthlyRebalanceTrigger(
    event_bus=bus,
    trigger_id="monthly_rebalance",
    timer_id="MONTHLY_REBALANCE_0930"
)
monthly_trigger.register()

# 10. 连接 CTP 行情网关
ctp_gateway = CTPMarketGateway(
    event_bus=bus,
    front_addr="tcp://...",
    broker_id="9999",
    user_id="...",
    password="..."
)
ctp_gateway.connect()
ctp_gateway.subscribe(list(config.get_target_weights().keys()))

# 11. 启动定时器（月初触发）
timer = SimpleTimer(bus, "MONTHLY_REBALANCE_0930", interval=86400)
timer.start()

# 12. 定期同步持仓（后台线程）
def sync_positions_loop():
    while True:
        portfolio_ctx.sync_positions_from_source()
        time.sleep(5)  # 每 5 秒同步一次

threading.Thread(target=sync_positions_loop, daemon=True).start()
```

### 5.2 数据流

```
┌─────────────────┐
│ 迅投 GT API     │ ← 每 5 秒同步持仓
└────────┬────────┘
         ↓
┌─────────────────┐
│ PortfolioContext│ ← 存储实时持仓
└────────┬────────┘
         ↓
┌─────────────────┐
│ CTP 行情推送    │ → TickEvent
└────────┬────────┘
         ↓
┌─────────────────────────┐
│ PortfolioDeviationTrigger│ ← 更新价格 + 检查偏离度
└────────┬────────────────┘
         ↓ (偏离超过阈值)
┌─────────────────┐
│ REBALANCE_REQUEST│
└────────┬────────┘
         ↓
┌─────────────────┐
│ RebalanceHandler│ → 生成订单
└─────────────────┘
```

---

## 六、待实现清单

### 6.1 高优先级

- [ ] **DatabaseConfigLoader**: 实现数据库配置加载器
  - 连接数据库（MySQL/PostgreSQL）
  - 实现 `load_product_config()` 方法
  - 实现 `save_product_config()` 方法

- [ ] **XunTouPositionSource**: 实现迅投 GT 持仓数据源
  - 引入迅投 GT SDK
  - 实现 `connect()` 方法
  - 实现 `fetch_positions()` 方法
  - 实现 `fetch_account_info()` 方法

- [ ] **SimpleTimer**: 实现定时器模块
  - 支持 cron 表达式
  - 支持月初定时触发（每月 1 号 9:30）

### 6.2 中优先级

- [ ] **前端 API**: 实现配置管理和偏离度监控接口
  - GET /api/config/{product_name}
  - POST /api/config/{product_name}
  - GET /api/deviation/{product_name}
  - WebSocket /ws/deviation

- [ ] **CTPPositionSource**: 实现 CTP 持仓数据源（备选）

### 6.3 低优先级

- [ ] **执行算法**: 实现 TWAP、VWAP、POV 等执行算法
- [ ] **风控模块**: 实现订单前风控检查
- [ ] **持久化**: 实现信号事件存储到数据库

---

## 七、参考文档

- **配置加载器使用指南**: `docs/CONFIG_LOADER_GUIDE.md`
- **示例代码**:
  - `examples/config_loader_example.py` - 配置加载器示例
  - `examples/position_source_example.py` - 持仓数据源示例
  - `examples/ctp_deviation_trigger_example.py` - CTP + 偏离触发器示例
