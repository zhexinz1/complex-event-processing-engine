# CEP 量化交易系统

基于 ECA (Event-Condition-Action) 架构的量化交易触发与订单管理系统，用于私募 A 股及期货的盘中异动监控和动态仓位再平衡。

## 目录

- [系统架构总览](#系统架构总览)
- [环境与依赖](#环境与依赖)
- [XunTou SDK 安装](#xuntou-sdk-安装)
- [CTP 行情接入 (OpenCTP)](#ctp-行情接入-openctp)
- [LD_LIBRARY_PATH 环境隔离](#ld_library_path-环境隔离)
- [数据库配置](#数据库配置)
- [Redis 跨进程桥接](#redis-跨进程桥接)
- [系统启动运行](#系统启动运行)
- [前端页面](#前端页面)
- [目录结构](#目录结构)
- [核心设计原则](#核心设计原则)
- [Hidden Knowledge 与踩坑记录](#hidden-knowledge-与踩坑记录)

---

## 系统架构总览

系统采用**微服务架构**，通过 Redis Pub/Sub 实现进程间通信，物理隔离 CTP 行情与 XunTou 交易两个相互冲突的 C++ SDK：

```
┌─────────────────────┐     Redis Pub/Sub      ┌──────────────────────┐
│   Market Node       │ ─── cep_events 频道 ──→ │   Web Node           │
│   (CTP 行情接入)     │                         │   (Flask + 迅投交易)   │
│                     │                         │                      │
│  - openctp-ctp SDK  │                         │  - XtTraderPyApi SDK │
│  - 无 xt_sdk 环境   │                         │  - Flask 5000 端口    │
│  - Tick/Bar → Redis │                         │  - 订单管理 / 对账     │
└─────────────────────┘                         └──────────────────────┘
         │                                               │
         └──────── 共享 MySQL (阿里云 fof 库) ─────────────┘
```

**关键约束**：CTP 和 XunTou 的 C++ 底层库**不能在同一进程中共存**，否则会触发 `SIGSEGV (exit code 139)` 段错误。

---

## 环境与依赖

### 基础环境

| 组件 | 版本 | 说明 |
|------|------|------|
| OS | Ubuntu (x86_64 Linux) | 阿里云 ECS |
| Python | 3.13 (`.python-version`) | 系统自带 3.12，uv 管理的 venv 为 3.13 |
| uv | 0.11.4+ | Python 包管理器，替代 pip |
| Redis | 7.0.15 | 本机 `localhost:6379`，用于跨进程行情桥接 |
| MySQL | 阿里云 RDS | `120.25.245.137:23306`，数据库名 `fof` |

### 安装依赖

```bash
# 安装 uv (如果未安装)
curl -LsSf https://astral.sh/uv/install.sh | sh

# 同步所有依赖到 .venv
cd /home/ubuntu/CEP
uv sync
```

> **PyPI 镜像**：项目已配置清华镜像 `https://pypi.tuna.tsinghua.edu.cn/simple`（见 `pyproject.toml`）。
>
> **Apple Silicon / ARM 开发说明**：`openctp-ctp` 现在仅在 `Linux x86_64` 环境安装。Mac ARM 上执行 `uv sync` 时会自动跳过该依赖，因此可以继续开发回测和前端相关功能；但 CTP 实时行情能力在该环境下不可用。

---

## XunTou SDK 安装

### SDK 位置

XunTou (迅投) 交易 SDK 是**闭源 C++ 动态库**，不在 PyPI 上分发，需要从迅投官方获取并手动部署。

```
/home/ubuntu/xt_sdk/
├── XtTraderPyApi.cpython-312-x86_64-linux-gnu.so   # Python binding (多版本)
├── XtTraderPyApi.cpython-313-x86_64-linux-gnu.so
├── libXtTraderApi.so                                 # 核心交易 API (64MB)
├── libHsFutuSystemInfo.so                            # 恒生期货系统信息采集
├── libLinuxDataCollect.so                            # Linux 数据采集
├── libboost_*.so.1.58.0                              # Boost 依赖 (1.58)
├── libicudata.so.50 / libicui18n.so.50 / libicuuc.so.50  # ICU 依赖
├── liblua.so.5.1 / libluabind.so                     # Lua 脚本引擎
├── libz.so.1                                         # zlib
├── config/
│   ├── traderApi.ini                                 # 连接配置
│   ├── traderApi.log4cxx                             # 日志配置
│   └── server.crt                                    # SSL 证书
└── userdata/                                         # 运行时数据
```

### SDK 导入方式

代码中通过 `sys.path.insert(0, '/home/ubuntu/xt_sdk')` 动态注入路径（见 `adapters/xuntou/base_service.py`）：

```python
import sys
sys.path.insert(0, '/home/ubuntu/xt_sdk')

from XtTraderPyApi import XtTraderApi, XtTraderApiCallback, XtError
```

### 连接配置

迅投 GT 服务器连接参数（见 `services/run_trading_node.py`）：

| 参数 | 值 | 说明 |
|------|------|------|
| 服务器地址 | `8.166.130.204:65300` | 迅投 GT 仿真服务器 |
| 用户名 | `system_trade` | 交易账号 |
| 资金账号 | `90102870` | 期货资金账号 |
| config 路径 | `/home/ubuntu/xt_sdk/config` | `traderApi.ini` 所在目录 |

### traderApi.ini 关键配置

```ini
[app]
appName = trader
netThreadNum = 5           # 网络线程数
reconnectSecond = 3        # 断线重连间隔
timeoutSecond = 60         # 连接超时
isReturnAcccountKey = 1    # 返回 account_key (必须开启!)

[threadPools]
callback = 5               # 回调线程池大小
```

> **⚠️ 重要**：`isReturnAcccountKey = 1` 必须开启，否则 `onRtnLoginStatus` 回调中拿不到 `account_key`，后续所有交易接口调用都会失败。

### LD_LIBRARY_PATH 要求

XunTou SDK 要求运行时 `LD_LIBRARY_PATH` 包含 `/home/ubuntu/xt_sdk`，否则 `libXtTraderApi.so` 无法找到其 Boost/ICU 等依赖。

**但是**，这个路径**会污染 CTP 进程**（见下文隔离章节）。

---

## CTP 行情接入 (OpenCTP)

### openctp-ctp

这是 [OpenCTP](https://github.com/openctp) 社区维护的 CTP Python 封装，提供与上期技术官方 CTP SDK 兼容的 API。

项目代码已对该依赖做运行时隔离：当 `openctp-ctp` 缺失或底层 `.so` 无法加载时，回测、前端和其他非 CTP 模块仍可正常导入；只有 `CTPMarketGateway` 连接实时行情会被禁用并输出日志。

### ⚠️ 关键：底层 .so 文件替换与环境切换

`openctp-ctp` PyPI 包安装后，其底层 C++ 动态库 (`libthostmduserapi_se.so`, `libthosttraderapi_se.so`) 默认对接的是 **SimNow 仿真环境**。连接生产环境（主席系统），需要手动将其替换成对应的版本。

```bash
git-lfs pull # 先下载相应so
```

仓库内提供了两个辅助脚本，用于在不同环境间切换：

- **切换至仿真环境 (OpenCTP 7x24 / SimNow)**:
  ```bash
  bash scripts/swap_openctp_so.sh
  ```
- **切换至生产环境 (Broker 实盘/主席系统)**:
  ```bash
  bash scripts/swap_prod_ctp_so.sh
  ```

> **⚠️ 每次 `uv sync` 或重装 `openctp-ctp` 后，`.so` 文件会被还原为默认版本，需要根据目标环境重新执行上述脚本！**

### 启动行情节点 (Market Node)

`run_market_node.py` 支持通过命令行参数灵活切换接入环境：

```bash
# 启动并连接仿真环境 (默认)
uv run -m services.run_market_node

# 启动并连接生产环境
uv run -m services.run_market_node \
    --front "tcp://140.206.80.228:41213" \
    --broker "8060" \
    --user "你的生产账号" \
    --password "你的生产密码"
```

| 参数 | 说明 | 默认值 (仿真) |
|------|------|------|
| `--front` | CTP 行情前置地址 | `tcp://218.17.194.115:41413` |
| `--broker` | 经纪商代码 BrokerID | `8060` |
| `--user` | 投资者账号 UserID | `99683265` |
| `--password` | 账号密码 Password | `456123` |
| `flow_path` | 会话文件存储目录 | `./ctp_flow/` |

### CTP 行情订阅机制

- CTP `subscribe()` 接收的是**纯合约代码**（如 `au2606`），不带交易所后缀
- 合约代码必须是**小写**（CTP 底层区分大小写）
- 系统每 30 秒从 MySQL `target_assets` 表同步最新合约列表，增量订阅新合约
- Tick 数据自动聚合为 1 分钟 Bar（使用差分法将 CTP 累计量转换为分钟增量）

---

## LD_LIBRARY_PATH 环境隔离

这是整个系统**最关键的 hidden knowledge**。XunTou SDK 和 CTP SDK 的 C++ 底层库会发生符号冲突：

### 问题根源

- XunTou SDK 依赖的 `libboost_*.so.1.58.0`、`libz.so.1` 等版本与系统默认版本冲突
- 如果 `LD_LIBRARY_PATH` 包含 `/home/ubuntu/xt_sdk`，CTP 的 `_thostmduserapi.so` 加载时会链接到错误版本的共享库
- 结果：**进程启动即段错误 (SIGSEGV, exit code 139)**

### 解决方案：进程级隔离 + exec 跳板

#### Market Node (行情进程) — 净化 xt_sdk 污染

`services/run_market_node.py` 在 `import` 任何模块之前，检测并清除 `LD_LIBRARY_PATH` 中的 xt_sdk 路径：

```python
_inherited_ld = os.environ.get("LD_LIBRARY_PATH", "")
if "xt_sdk" in _inherited_ld:
    _clean_paths = [p for p in _inherited_ld.split(":") if "xt_sdk" not in p]
    os.environ["LD_LIBRARY_PATH"] = ":".join(_clean_paths)
    os.execlp(sys.executable, sys.executable, "-m", "services.run_market_node")
```

`os.execlp` 会**替换当前进程镜像**，使新的 `LD_LIBRARY_PATH` 在链接器层面生效。

#### Trading Node (交易进程) — 注入 xt_sdk 路径

`services/run_trading_node.py` 做相反操作：如果 `LD_LIBRARY_PATH` 不包含 xt_sdk，自动注入后用 `os.execlp` 重启：

```python
if "/home/ubuntu/xt_sdk" not in _ld_lib_path:
    os.environ["LD_LIBRARY_PATH"] = "/home/ubuntu/xt_sdk:" + _ld_lib_path
    os.execlp(sys.executable, sys.executable, "-m", "services.run_trading_node")
```

#### Web Node — 无需 exec 跳板

`services/run_web_node.py` 不直接 import CTP 模块（行情通过 Redis 间接获取），也不在代码顶层 import XunTou（XunTou 通过 `sys.path.insert` 运行时注入），因此不需要 exec 跳板。

但 `adapters/market_gateway.py` 内部仍有一层防御性清理：

```python
_inherited_ld = os.environ.get("LD_LIBRARY_PATH", "")
if "xt_sdk" in _inherited_ld:
    _clean_paths = [p for p in _inherited_ld.split(":") if "xt_sdk" not in p]
    os.environ["LD_LIBRARY_PATH"] = ":".join(_clean_paths)
```

#### bashrc 注意事项

**绝不要**在 `~/.bashrc` 中全局 export `LD_LIBRARY_PATH=/home/ubuntu/xt_sdk`。当前已注释掉：

```bash
# export LD_LIBRARY_PATH=~/xt_sdk:$LD_LIBRARY_PATH
```

如果误开，所有新 shell 启动的 CTP 进程都会段错误。

---

## 数据库配置

### 连接信息

| 参数 | 值 |
|------|------|
| Host | `120.25.245.137` |
| Port | `23306` |
| Database | `fof` |
| User | `cx` |
| Charset | `utf8mb4` |

连接参数集中定义在 `.env` 的 `DB_HOST` / `DB_PORT` / `DB_USER` / `DB_PASS` / `DB_NAME`。Python 代码统一通过 `database/config.py` 读取。

### 核心表

| 表名 | 用途 |
|------|------|
| `products` | 产品配置（产品名、迅投账号、杠杆率等） |
| `target_assets` | 目标合约池（合约代码、合约乘数） |
| `target_allocations` | 目标权重配置（产品 × 合约 × 权重比例） |
| `pending_orders` | 订单管理（含 `xt_status` / `xt_error_msg` / `xt_traded_volume` / `xt_traded_price` / `order_price_type`） |
| `fund_inflows` | 净入金记录 |
| `fractional_shares` | 余手数据（跨批次的小数手位传递） |

### 订单状态追踪 (xt_status)

订单状态通过**回调驱动**自动更新，无需轮询：

| xt_status | 含义 | 触发方式 |
|-----------|------|----------|
| `not_sent` | 未发送 | 默认值 |
| `send_failed` | 发送失败 | 下单 API 调用失败时写入 |
| `sent` | 已发送 | 下单成功后写入 |
| `running` | 运行中 | SDK `onOrderEvent` 回调 |
| `rejected` | 已驳回 | SDK `onOrderEvent` 回调 |
| `filled` | 已完成 | SDK `onOrderEvent` 回调 |
| `partial` | 部分成交 | SDK `onOrderEvent` 回调 |
| `cancelled` | 已撤单 | SDK `onOrderEvent` 回调 |
| `stopped` | 已停止 | SDK `onOrderEvent` 回调 / 对账 |

---

## Redis 跨进程桥接

### 架构

```
Market Node                    Web Node / Trading Node
EventBus.publish(TickEvent)    Redis Pub/Sub → pickle.loads → EventBus.publish
    ↓                                ↑
RedisEventBridge._on_local_event     RedisEventBridge._on_redis_message
    ↓                                ↑
pickle.dumps → redis.publish   redis.subscribe("cep_events")
```

### 配置

| 参数 | 值 |
|------|------|
| Redis URL | `redis://localhost:6379/0` |
| 频道名 | `cep_events` |
| 序列化 | `pickle` (直接序列化 dataclass) |

### 实现

- `cep/core/remote_bus.py` — `RedisEventBridge` 类
- Market Node 调用 `bridge.start_publishing([TickEvent, BarEvent])`
- Web Node 通过 `adapters/price_service.py` 订阅 Redis 维护本地 Tick 缓存

---

## 系统启动运行

### 启动顺序

系统由**两个独立进程**组成，必须分别在不同终端启动：

```bash
# 终端 1：启动行情节点（必须先启动）
cd /home/ubuntu/CEP
uv run -m services.run_market_node

# 终端 2：启动 Web 节点（行情通过 Redis 接收）
cd /home/ubuntu/CEP
uv run -m services.run_web_node
```

> **Trading Node** (`run_trading_node.py`) 是独立交易引擎节点，目前 Web Node 已整合了交易功能，日常运行中不需要单独启动。

### 启动验证

**Market Node 正常输出**：
```
[Market Node] 正在启动独立行情微服务...
CTP: 前置连接成功，发起登录...
CTP: 登录成功
CTP: 订阅成功 au2606
CTP: 订阅成功 p2609
[Market Node] 系统现已就绪。所有行情将通过 Redis 实时向全网分发。
```

**Web Node 正常输出**：
```
[Web Node] 正在启动前端测控微服务...
[PriceService] Redis 行情订阅已连接: channel=cep_events
📍 欢迎访问 CEP 网页控制台:
  - 目标资产配置: http://<服务器IP>:5000/
```

### 常见启动问题

| 问题 | 原因 | 解决方案 |
|------|------|----------|
| Market Node exit code 139 | LD_LIBRARY_PATH 包含 xt_sdk | 确保 `~/.bashrc` 中没有 export xt_sdk 路径 |
| CTP 登录失败 | 仿真前置地址变更 / .so 文件未替换 | 检查 OpenCTP 官网最新前置地址 |
| Web Node 无行情 | Redis 未启动 / Market Node 未启动 | `redis-cli ping` 检查 Redis |
| XunTou 连接超时 | 首次连接较慢 / 服务器维护 | 等待 60 秒超时后重试 |

---

## 前端页面

Flask 服务 5000 端口，静态文件位于 `frontend/`：

| 页面 | 路径 | 功能 |
|------|------|------|
| 目标资产配置 | `/` → `index.html` | 产品管理、合约池、目标权重配置 |
| 净入金流程 | `/fund-inflow.html` | 输入资金 → 计算调仓 → 生成订单 |
| 订单确认 | `/order-confirm.html` | 选择下单方式（限价/市价/TWAP/VWAP）→ 迅投发单 |
| 订单列表 | `/order-list.html` | 查看订单状态 (DB 直读)、手动对账 |
| 行情健康 | `/health.html` | 实时行情通道监控 |

---

## 目录结构

```
CEP/
├── cep/                        # 核心 CEP 框架
│   ├── core/                   # 事件、事件总线、上下文黑板、Redis 桥接
│   ├── engine/                 # AST 规则求值引擎
│   └── triggers/               # 触发器实现 (AST/Deviation/Cron)
│
├── adapters/                   # 外部接口适配器层
│   ├── market_gateway.py       # CTP 行情网关
│   ├── flask_app.py            # Flask Web 控制台 (REST API)
│   ├── price_service.py        # Redis 行情缓存服务
│   ├── config_source.py        # 数据库配置源 (MySQL)
│   ├── contract_config.py      # 合约配置
│   └── xuntou/                 # 迅投 SDK 封装
│       ├── base_service.py     # 连接管理和回调基类
│       ├── order_service.py    # 下单服务 (OrderRequest/OrderResult)
│       ├── query_service.py    # 查询服务 (指令/委托/持仓)
│       └── connection_manager.py  # 连接池 (单例)
│
├── database/                   # 数据库层
│   ├── models.py               # 数据模型 (Product/PendingOrder/XtStatus/...)
│   └── dao.py                  # 数据访问对象 (CRUD)
│
├── services/                   # 微服务入口
│   ├── run_market_node.py      # 行情节点 (CTP → Redis)
│   ├── run_web_node.py         # Web 节点 (Flask + 迅投)
│   └── run_trading_node.py     # 交易节点 (Redis → 策略 → 迅投)
│
├── rebalance/                  # 再平衡引擎 (5步计算链路)
├── nlp/                        # 自然语言 → JSON AST (Claude API)
├── frontend/                   # 静态 HTML 前端
├── config/                     # 策略配置文件
├── archive/                    # 历史测试脚本归档
└── migrations/                 # 数据库迁移
```

---

## 核心设计原则

1. **极致解耦**：触发器只发射 SignalEvent，绝不直接调用下游业务逻辑
2. **依赖注入**：EventBus、Context、DAO 均通过构造函数注入，无模块级单例
3. **事件不可变**：Event dataclass 使用 `frozen=True`，发布后禁止修改
4. **WeakRef 防泄漏**：EventBus 使用 `weakref.WeakMethod` 防止订阅者内存泄漏
5. **回调驱动状态**：订单状态由 XunTou SDK 回调实时写入 DB，前端直读 DB
6. **对账兜底**：手动对账按钮用于进程重启后同步 DB 与迅投服务器的状态差异

---

## Hidden Knowledge 与踩坑记录

### 1. openctp .so 替换必须匹配 Python 版本

替换 `_thostmduserapi.so` 和 `_thosttraderapi.so` 时，必须下载与 `.venv` 中 Python 版本 (3.13) 匹配的二进制文件。如果用了 3.12 的 .so 会直接 `ImportError`。

### 2. 迅投合约代码必须小写

XunTou SDK 的 `COrdinaryOrder.m_strInstrument` 必须传入**小写**合约代码（如 `au2606`），大写会导致找不到合约。代码中已在 `order_service.py` 做了 `.lower()` 处理。

### 3. 市价单价格设为 0

市价单 (`EPriceType.PRTP_MARKET`) 时，`order.m_dPrice` 应设为 `0.0`。CTP/CTP 仿真后端会自动根据涨停/跌停价挂单。实际委托价格可能与订单记录中的 `price`（计算参考价）不同。

### 4. CTP flow 目录

CTP SDK 启动时会在 `flow_path` 目录写入会话文件。多个 CTP 实例**不能共用同一个 flow 目录**，否则会相互覆盖导致断线。目前使用 `./ctp_flow/`，已在 `.gitignore` 中排除。

### 5. XunTou 回调的 DAO 注入

`_OrderCallback.onOrderEvent` / `onTradeEvent` 是在 XunTou SDK 的 C++ 线程中执行的。DAO 通过构造函数注入到回调类中。注意 PyMySQL 的连接不是线程安全的，每次回调都会新建短连接。

### 6. redis-cli 可能误报

系统 Redis 已正常运行在 `127.0.0.1:6379`，但某些终端环境下 `redis-cli` 命令可能因 PATH 问题找不到。可用 `ss -tlnp | grep 6379` 验证端口监听状态。

### 7. uv sync 后记得重新替换 .so

每次执行 `uv sync` 或升级 `openctp-ctp` 版本后，底层 `.so` 文件会被还原为默认版本（指向 SimNow），需要重新用 OpenCTP 7x24 仿真版本覆盖。

### 8. 前端行情健康检查依赖 Market Node

`health.html` 页面轮询 `/api/market/health`，该接口从 Redis 行情缓存中读取最新 Tick 时间戳。如果 Market Node 未启动或 Redis 不通，所有合约都会显示为"离线"。

### 9. 数据库连接超时

阿里云 RDS 有空闲连接自动断开的策略。如果长时间无查询（>10分钟），PyMySQL 连接会被服务端断开，表现为 `Lost connection to MySQL server during query (timed out)`。当前 DAO 采用短连接模式（每次操作新建连接），已规避此问题。

### 10. 新增合约后无需重启 Market Node

Market Node 每 30 秒自动从 DB `target_assets` 表同步合约列表并增量订阅。在 Web 控制台添加新合约后，最多等待 30 秒即可自动生效。

### 11. CTP依赖中文字符集

Linux下安装后，需要安装中文字符集，否则导入时报错：
```bash
>>> import openctp_ctp
terminate called after throwing an instance of 'std::runtime_error'
what():  locale::facet::_S_create_c_locale name not valid
Aborted
```

需要安装 GB18030 字符集
```bash
# Ubuntu (20.04)
sudo apt-get install -y locales
sudo locale-gen zh_CN.GB18030
```
