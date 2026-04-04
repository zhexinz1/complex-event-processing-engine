# 配置加载器使用指南

## 概述

为了支持从数据库或前端加载目标权重配置，系统提供了灵活的配置加载器接口。每个资产可以独立配置偏离阈值和执行算法。

## 数据库表结构

目标权重配置表结构示例：

| 字段 | 类型 | 说明 | 示例 |
|------|------|------|------|
| date | DATE | 配置日期 | 2026-03-30 |
| product_name | VARCHAR(100) | 产品名称 | 明钺全天候1号 |
| symbol | VARCHAR(50) | 资产代码 | AU2606.SHF |
| target_weight | DECIMAL(10,4) | 目标比例 | 0.2561 (25.61%) |
| deviation_threshold | DECIMAL(10,4) | 偏离阈值 | 0.03 (3%) |
| algorithm | VARCHAR(20) | 执行算法 | TWAP |

### 示例数据

```sql
INSERT INTO target_weights VALUES
  ('2026-03-30', '明钺全天候1号', 'AU2606.SHF', 0.2561, 0.03, 'TWAP'),
  ('2026-03-30', '明钺全天候1号', 'IC2606.CFE', 0.2048, 0.05, 'TWAP'),
  ('2026-03-30', '明钺全天候1号', 'T2605.CFE', 1.2476, 0.02, 'TWAP'),
  ('2026-03-30', '明钺全天候1号', 'M2609.DCE', 0.0781, 0.04, 'TWAP');
```

## 配置加载器接口

### 1. TargetConfigLoader 协议

所有配置加载器必须实现此接口：

```python
class TargetConfigLoader(Protocol):
    def load_product_config(
        self,
        product_name: str,
        config_date: Optional[date] = None
    ) -> Optional[ProductConfig]:
        """加载指定产品的目标权重配置"""
        ...

    def save_product_config(self, config: ProductConfig) -> bool:
        """保存产品配置"""
        ...
```

### 2. 数据类

#### TargetWeightConfig

单个资产的配置：

```python
@dataclass
class TargetWeightConfig:
    date: date                    # 配置日期
    product_name: str             # 产品名称
    symbol: str                   # 资产代码
    target_weight: float          # 目标比例（0.2561 = 25.61%）
    deviation_threshold: float    # 偏离阈值（0.03 = 3%）
    algorithm: str                # 执行算法（TWAP/VWAP/POV）
```

#### ProductConfig

产品级配置（包含多个资产）：

```python
@dataclass
class ProductConfig:
    product_name: str             # 产品名称
    date: date                    # 配置日期
    assets: list[TargetWeightConfig]  # 资产配置列表
    global_threshold: float       # 全局偏离阈值（默认 5%）

    def get_target_weights(self) -> dict[str, float]:
        """获取所有资产的目标权重字典"""
        ...

    def get_deviation_thresholds(self) -> dict[str, float]:
        """获取所有资产的偏离阈值字典"""
        ...

    def get_algorithms(self) -> dict[str, str]:
        """获取所有资产的执行算法字典"""
        ...
```

## 实现示例

### 1. 内存配置加载器（测试用）

```python
from rebalance import InMemoryConfigLoader, ProductConfig, TargetWeightConfig
from datetime import date

# 创建加载器
loader = InMemoryConfigLoader()

# 创建配置
config = ProductConfig(
    product_name="明钺全天候1号",
    date=date(2026, 3, 30),
    assets=[
        TargetWeightConfig(
            date=date(2026, 3, 30),
            product_name="明钺全天候1号",
            symbol="AU2606.SHF",
            target_weight=0.2561,
            deviation_threshold=0.03,
            algorithm="TWAP"
        ),
        # ... 更多资产
    ],
    global_threshold=0.05
)

# 保存配置
loader.save_product_config(config)

# 加载配置
loaded_config = loader.load_product_config("明钺全天候1号")
```

### 2. 数据库配置加载器（预留接口）

```python
from rebalance import DatabaseConfigLoader

# 创建数据库加载器
loader = DatabaseConfigLoader("mysql://user:pass@localhost/db")

# 加载配置（从数据库查询）
config = loader.load_product_config("明钺全天候1号")

# TODO: 实现数据库查询逻辑
# 示例 SQL:
# SELECT date, product_name, symbol, target_weight,
#        deviation_threshold, algorithm
# FROM target_weights
# WHERE product_name = ? AND date = ?
# ORDER BY date DESC
```

## 与偏离触发器集成

### 使用配置加载器创建触发器

```python
from cep.core.event_bus import EventBus
from rebalance import (
    PortfolioContext,
    PortfolioDeviationTrigger,
    InMemoryConfigLoader
)

# 1. 加载配置
loader = InMemoryConfigLoader()
config = loader.load_product_config("明钺全天候1号")

# 2. 设置组合上下文
bus = EventBus()
portfolio_ctx = PortfolioContext()
portfolio_ctx.set_target_weights(config.get_target_weights())

# 3. 创建偏离触发器（使用独立阈值）
trigger = PortfolioDeviationTrigger(
    event_bus=bus,
    trigger_id="portfolio_deviation",
    portfolio_ctx=portfolio_ctx,
    threshold=config.global_threshold,           # 全局默认阈值
    symbol_thresholds=config.get_deviation_thresholds(),  # 每个资产的独立阈值
    cooldown=60.0
)
trigger.register()
```

### 偏离检测逻辑

触发器会为每个资产使用独立的偏离阈值：

```python
# 伪代码
for symbol, target_weight in target_weights.items():
    current_weight = calculate_current_weight(symbol)
    deviation = abs(current_weight - target_weight)

    # 优先使用资产独立阈值，否则使用全局阈值
    threshold = symbol_thresholds.get(symbol, global_threshold)

    if deviation > threshold:
        trigger_rebalance(symbol)
```

## 前端集成接口

### 1. 获取当前配置

```python
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
```

### 2. 更新配置

```python
POST /api/config/{product_name}

Request:
{
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

Response:
{
  "success": true,
  "message": "配置已更新"
}
```

### 3. 获取偏离度实时监控

```python
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
```

## 执行算法支持

系统预留了执行算法字段，支持以下算法：

| 算法 | 说明 | 适用场景 |
|------|------|----------|
| TWAP | 时间加权平均价格 | 均匀分散执行，减少市场冲击 |
| VWAP | 成交量加权平均价格 | 跟随市场成交量分布 |
| POV | 成交量百分比 | 按市场成交量比例执行 |
| LIMIT | 限价单 | 指定价格执行 |
| MARKET | 市价单 | 立即执行 |

### 算法配置示例

```python
TargetWeightConfig(
    symbol="AU2606.SHF",
    target_weight=0.2561,
    deviation_threshold=0.03,
    algorithm="TWAP"  # 使用 TWAP 算法执行
)
```

## 完整示例

参考 `examples/config_loader_example.py` 查看完整的集成示例。

## 待实现功能

### DatabaseConfigLoader

需要实现以下方法：

1. **load_product_config**: 从数据库查询配置
   - 支持按产品名称和日期查询
   - 支持查询最新配置（date=None）
   - 解析数据库记录并构造 ProductConfig 对象

2. **save_product_config**: 保存配置到数据库
   - 支持插入新配置
   - 支持更新现有配置
   - 事务处理确保数据一致性

### 前端 API

需要实现以下接口：

1. **GET /api/config/{product_name}**: 获取配置
2. **POST /api/config/{product_name}**: 更新配置
3. **GET /api/deviation/{product_name}**: 获取实时偏离度
4. **WebSocket /ws/deviation**: 实时推送偏离度变化

## 注意事项

1. **权重可以超过 100%**：期货产品支持杠杆，总权重可以超过 100%（如示例中的 T2605.CFE 为 124.76%）

2. **独立阈值优先级**：每个资产的独立阈值优先级高于全局阈值

3. **配置更新**：配置更新后需要重新创建触发器或调用 `trigger.update_config()` 方法

4. **线程安全**：当前实现为单线程设计，多线程环境需要加锁保护

5. **数据验证**：保存配置前应验证：
   - 权重总和是否合理
   - 偏离阈值是否在合理范围（0-1）
   - 资产代码是否有效
