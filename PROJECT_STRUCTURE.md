# 项目结构

## 核心目录

```
CEP/
├── adapters/              # 外部服务适配器
│   ├── flask_app.py      # Flask REST API服务
│   ├── market_gateway.py # 行情网关
│   ├── xt_order_service.py        # 迅投下单服务
│   ├── xt_connection_manager.py   # 迅投连接管理器
│   └── xt_trader_service.py       # 迅投交易服务
│
├── database/             # 数据库层
│   ├── dao.py           # 数据访问对象
│   └── models.py        # 数据模型
│
├── migrations/          # 数据库迁移脚本
│   └── add_xt_credentials_to_products.sql
│
├── frontend/            # 前端界面
│   ├── index.html
│   └── ...
│
├── cep/                 # CEP引擎核心
│   ├── core/           # 核心组件
│   ├── engine/         # 事件处理引擎
│   └── triggers/       # 触发器
│
├── ctp_flow/           # CTP行情流
├── rebalance/          # 再平衡逻辑
├── nlp/                # 自然语言处理
├── config/             # 配置文件
├── scripts/            # 工具脚本
├── docs/               # 文档
├── examples/           # 示例代码
│
└── archive/            # 归档文件
    ├── tests/          # 旧测试文件
    └── tests_and_demos/  # 测试和演示脚本

## 主要文件

- `run_server.py` - 启动Flask服务器
- `pyproject.toml` - 项目依赖配置
- `README.md` - 项目说明
- `ARCHITECTURE.md` - 架构文档
- `CLAUDE.md` - Claude AI配置

## 启动服务

```bash
# 启动Flask API服务
python run_server.py
```

## 核心功能

1. **多账号支持** - 支持多个迅投账号管理和交易
2. **订单管理** - 净入金触发的增量买入流程
3. **行情接入** - CTP行情数据处理
4. **REST API** - 提供完整的HTTP接口
5. **前端界面** - Web管理界面

## 归档说明

`archive/` 目录包含：
- 历史测试文件
- 临时演示脚本
- 开发过程中的实验代码

这些文件已不再需要，但保留用于参考。
