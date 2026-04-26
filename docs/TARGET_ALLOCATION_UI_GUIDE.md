# 目标仓位配置大屏 — 设计与实现文档

## 概述

本模块为 CEP 量化交易引擎提供了一个精美的 Web 前端界面，用于管理目标仓位配置（`target_allocations` 表）。采用深色金融极客美学，支持 CRUD 操作，并与阿里云 FOF 数据库无缝集成。

---

## 架构设计

### 技术栈

**后端**：
- Flask 3.1.3 — 轻量级 Web 框架
- PyMySQL 1.4.6 — MySQL 数据库驱动
- Python 3.13

**前端**：
- Vue 3 (CDN) — 响应式框架
- Tailwind CSS (CDN) — 原子化 CSS
- TypeScript + Vite + npm 管理

**数据库**：
- MySQL 5.7+ (阿里云 RDS)
- 表名：`target_allocations`

---

## 数据库设计

### 表结构

```sql
CREATE TABLE IF NOT EXISTS target_allocations (
    id            INT PRIMARY KEY AUTO_INCREMENT,
    target_date   DATE           NOT NULL COMMENT '目标日期',
    product_name  VARCHAR(100)   NOT NULL COMMENT '产品名称/策略ID',
    asset_code    VARCHAR(50)    NOT NULL COMMENT '资产代码（如 AU2606）',
    weight_ratio  DECIMAL(12, 6) NOT NULL COMMENT '目标比例（0.2561 表示 25.61%）',
    algo_type     VARCHAR(20)    NOT NULL DEFAULT 'TWAP' COMMENT '执行算法',
    created_at    TIMESTAMP      DEFAULT CURRENT_TIMESTAMP,
    updated_at    TIMESTAMP      DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_date_product_asset (target_date, product_name, asset_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### 字段说明

| 字段 | 类型 | 说明 | 示例 |
|------|------|------|------|
| `id` | INT | 主键 | 1 |
| `target_date` | DATE | 目标日期 | 2026-04-08 |
| `product_name` | VARCHAR(100) | 产品名称 | 明诚全天候1号 |
| `asset_code` | VARCHAR(50) | 资产代码 | AU2606 |
| `weight_ratio` | DECIMAL(12,6) | 目标比例 | 0.256100 (25.61%) |
| `algo_type` | VARCHAR(20) | 执行算法 | TWAP / VWAP |

### 联合唯一索引

`(target_date, product_name, asset_code)` — 同一日期、同一产品、同一资产只能有一条记录。

### 资产代码白名单库 (allowed_assets)

```sql
CREATE TABLE IF NOT EXISTS allowed_assets (
    id          INT PRIMARY KEY AUTO_INCREMENT,
    asset_code  VARCHAR(50)  NOT NULL,
    created_at  TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_asset_code (asset_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

为了防止操作员配置时拼写错误（Typo），系统强制维护一份可交易品种资产白名单字典库。前端仅允许从这些经过备案的品种进行选取配置。

---

## 后端实现

### 文件结构

```
database/
└── config.py             # 数据库连接配置单一来源

adapters/
├── config_source.py      # MySQLConfigSource 类（供引擎读取配置）
├── flask_app.py          # Flask REST API（供前端调用）
└── __init__.py           # 导出 MySQLConfigSource

examples/
└── run_ui_server.py      # 一键启动脚本
```

### MySQLConfigSource 类

**位置**：`adapters/config_source.py`

**作用**：实现 `ConfigSource` 接口，供 `RebalanceEngine` 读取目标权重。

数据库连接参数来自 `.env` 的 `DB_HOST` / `DB_PORT` / `DB_USER` / `DB_PASS` / `DB_NAME`，应用、DAO、初始化脚本和配置源统一通过 `database/config.py` 读取。

**核心方法**：

```python
def load_target_weights(self, strategy_id: str) -> dict[str, float]:
    """
    返回指定产品在最新日期下的权重字典。

    Args:
        strategy_id: 产品名称（如 "明诚全天候1号"）

    Returns:
        {"AU2606": 0.2561, "IC2606": 0.2048, ...}
    """
```

**SQL 逻辑**：

```sql
SELECT asset_code, weight_ratio
FROM target_allocations
WHERE product_name = %s
  AND target_date = (
      SELECT MAX(target_date)
      FROM target_allocations
      WHERE product_name = %s
  )
```

### Flask REST API

**位置**：`adapters/flask_app.py`

**端点列表**：

| 方法 | 路径 | 功能 | 请求体 | 响应 |
|------|------|------|--------|------|
| GET | `/` | 前端页面 | - | HTML |
| GET | `/api/weights` | 查询配置 | `?target_date=&product_name=` | JSON |
| POST | `/api/weights` | 新增/更新 | `{target_date, product_name, asset_code, weight_ratio, algo_type?}` | JSON |
| DELETE | `/api/weights/<id>` | 删除 | - | JSON |
| GET | `/api/products` | 产品列表 | - | JSON |
| GET | `/api/assets` | 资产代码白名单列表 | - | JSON |
| POST | `/api/assets` | 新增资产代码 | `{asset_code}` | JSON |
| DELETE| `/api/assets/<asset_code>` | 删除资产代码 | - | JSON |

**响应格式**：

```json
{
  "success": true,
  "message": "操作成功",
  "data": [...],
  "total": 10
}
```

**错误处理**：

所有数据库操作均包裹在 `try-except` 中，连接失败时返回 HTTP 503：

```json
{
  "success": false,
  "message": "数据库连接失败: (1045, 'Access denied...')",
  "data": []
}
```

### 启动脚本

**位置**：`examples/run_ui_server.py`

**用法**：

```bash
# 首次运行或前端代码变更后，先构建 TypeScript/Vite 前端
npm install
npm run frontend:build

uv run -m examples.run_ui_server
```

**启动流程**：

1. 尝试初始化数据库（建表）
2. 如果 DB 连接失败，记录警告但继续启动
3. 创建 Flask app
4. 监听 `0.0.0.0:5000`

---

## 前端实现

前端已迁移为 Vue 3 + TypeScript + Vite。`frontend/index.html` 只保留 Vite HTML shell 和 `#app` 挂载点，页面模板位于 `frontend/App.vue`，状态和业务动作拆分到 `frontend/composables/`。

简化后的结构、运行命令和核心模块说明见 [`frontend/README.md`](../frontend/README.md)。本设计文档只保留目标仓位 UI 的业务背景和接口说明，避免与前端源码结构文档重复。

---

## 部署指南

### 1. 安装依赖

```bash
# 安装 uv（如果未安装）
curl -LsSf https://astral.sh/uv/install.sh | sh

# 同步依赖
uv sync
```

### 2. 配置数据库访问

数据库配置会自动从 .env文件中读取到`database/config.py`作为中心化的默认配置。所有连接DB的模块都会直接引用它。

### 3. 配置安全组

**阿里云 ECS 安全组规则**：

- 协议类型：TCP
- 端口范围：`5000/5000`
- 授权对象：`0.0.0.0/0`（或指定 IP）

### 4. 启动服务

```bash
# 后台启动
.venv/bin/python examples/run_ui_server.py > /tmp/flask_server.log 2>&1 &

# 查看日志
tail -f /tmp/flask_server.log

# 停止服务
pkill -f run_ui_server
```

### 5. 访问界面

**本地访问**：
```
http://localhost:5000
```

**远程访问**：
```
http://<服务器公网IP>:5000
```

**SSH 端口转发**（推荐）：
```bash
ssh -L 5000:localhost:5000 ubuntu@<服务器IP>
# 然后访问 http://localhost:5000
```

---

## 与 CEP 引擎集成

### 在 Rebalance 流程中使用

```python
from adapters import MySQLConfigSource
from rebalance import RebalanceEngine

# 初始化配置源
config_source = MySQLConfigSource()

# 加载目标权重
target_weights = config_source.load_target_weights("明诚全天候1号")
# 返回: {"AU2606": 0.2561, "IC2606": 0.2048, ...}

# 传递给 RebalanceEngine
engine = RebalanceEngine(
    portfolio_ctx=portfolio_ctx,
    target_weights=target_weights,
    new_capital=1000000.0
)

orders = engine.calculate()
```

### 配置热更新

`MySQLConfigSource` 每次调用 `load_target_weights()` 都会实时查询数据库，无需重启引擎即可获取最新配置。

---

## 故障排查

### 问题 1：数据库连接失败

**错误信息**：
```
Access denied for user 'cx'@'<IP>' (using password: YES)
```

**解决方案**：
1. 检查 RDS 白名单是否包含服务器 IP
2. 检查用户名/密码是否正确
3. 检查数据库名称是否为 `fof`

### 问题 2：前端显示 DB CONNECTED 但无数据

**原因**：之前的 bug（已修复），`fetch` 不会在 HTTP 503 时抛异常。

**解决方案**：已在 `fetchData()` 中添加 `json.success` 检查。

### 问题 3：无法通过公网 IP 访问

**检查清单**：
1. Flask 是否监听 `0.0.0.0`（而非 `127.0.0.1`）
2. 阿里云安全组是否放行 5000 端口
3. 服务器防火墙是否关闭（`ufw status`）

### 问题 4：权重总和不等于 100%

**说明**：系统不强制要求总和为 100%，仅在前端显示黄色预警。如需严格校验，可在后端 API 添加验证逻辑。

---

## 性能优化建议

### 数据库层

1. **索引优化**：
   - 已有联合唯一索引 `(target_date, product_name, asset_code)`
   - 如需按日期范围查询，可添加单列索引 `target_date`

2. **连接池**：
   - 当前每次请求创建新连接，高并发场景建议使用 `pymysql` 连接池或 `SQLAlchemy`

### 前端层

1. **分页加载**：
   - 当前一次性加载所有数据，数据量大时可实现分页

2. **防抖/节流**：
   - 筛选器输入时可添加 300ms 防抖，减少 API 调用

3. **缓存策略**：
   - 产品列表可缓存 5 分钟，减少重复查询

---

## 扩展功能建议

### 1. 批量导入

支持 Excel/CSV 文件上传，批量导入配置。

### 2. 历史版本对比

展示同一产品不同日期的权重变化趋势（折线图）。

### 3. 权重总和校验

后端 API 添加可选的严格校验：同一日期、同一产品的所有资产权重总和必须为 100%。

### 4. 权限管理

添加用户登录、角色权限（只读/编辑/管理员）。

### 5. 审计日志

记录所有配置变更操作（操作人、时间、变更内容）。

### 6. WebSocket 实时推送

当配置变更时，自动推送到所有在线用户，无需手动刷新。

### 7. 品种真实性校验 (CTP / 本地行情网关接口)

**【TODO】** 目前 `allowed_assets` 白名单品种的录入在 `flask_app.py` 内部仅做了重名防重提交（抛 409 异常）。未来在 `/api/assets` 录入操作（POST）内，应当实际连接底层的 CTP 或迅投行情 API 进行即时校验。如品种由于摘牌/写错在物理引擎内找不到实体时应予以抛 422 状态码拒绝。

---

## 代码规范

### Python 代码

- 遵循 PEP 8
- 使用 `ruff` 格式化
- 使用 `pyright` 类型检查
- 所有函数添加类型提示和 docstring

### 前端代码

- 使用 ES6+ 语法
- Vue 3 Composition API
- 变量命名：驼峰式（`camelCase`）
- 常量命名：大写下划线（`UPPER_SNAKE_CASE`）

---

## 维护清单

### 日常维护

- [ ] 定期检查数据库连接状态
- [ ] 监控 Flask 进程是否存活
- [ ] 查看日志文件 `/tmp/flask_server.log`

### 定期任务

- [ ] 每月清理过期配置（可选）
- [ ] 备份 `target_allocations` 表
- [ ] 更新依赖包版本

### 安全检查

- [ ] 定期更换数据库密码
- [ ] 审查安全组规则
- [ ] 检查 SQL 注入风险（已使用参数化查询）

---

## 附录

### A. 数据库连接配置

**位置**：`adapters/flask_app.py` 和 `adapters/config_source.py`

```python
DB_CONFIG = dict(
    host="120.25.245.137",
    port=23306,
    database="fof",
    user="cx",
    password="iyykiho4#0HO",
    charset="utf8mb4",
)
```

### B. 依赖清单

```toml
[project]
dependencies = [
    "flask>=3.0.0",
    "pymysql>=1.1.0",
    # ... 其他依赖
]
```

### C. 文件清单

```
adapters/
├── config_source.py       (新增 MySQLConfigSource 类)
├── flask_app.py           (新建)
└── __init__.py            (更新导出)

frontend/
└── index.html             (新建)

examples/
└── run_ui_server.py       (新建)

docs/
└── TARGET_ALLOCATION_UI_GUIDE.md  (本文档)

pyproject.toml             (更新依赖)
```

---

## 更新日志

### v1.2.0 (2026-04-11)
- 新增backtest页面
- 显著重构，模块化拆分当前UI，并改用现代化的typescript编写

### v1.1.0 (2026-04-10)

- ✅ 完成企业级浅白浅灰专业视觉换标与重构 (Light Mode UI Re-design)
- ✅ 优化前端下拉框强验证设计，封堵操作员输入 Typo
- ✅ 新增资产字典库表结构 (`allowed_assets`)
- ✅ 提供 `/api/assets` 对外配套管理 API 组件服务

### v1.0.0 (2026-04-08)

- ✅ 初始版本发布
- ✅ 实现 MySQLConfigSource 类
- ✅ 实现 Flask REST API
- ✅ 实现赛博金融大屏极客风 UI
- ✅ 修复 DB 状态指示器误报问题
- ✅ 添加完整的错误处理和友好提示

---

## 联系方式

如有问题或建议，请提交 Issue 或联系开发团队。
