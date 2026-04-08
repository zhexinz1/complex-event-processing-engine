# 迅投 XtTrader Python API SDK 部署指南

SDK 二进制文件不提交到 Git（已在 `.gitignore` 中排除），在每台机器上按本文档独立部署。

## 快速安装（推荐）

```bash
bash scripts/install_xt_sdk.sh
source ~/.bashrc
```

脚本会自动完成：下载 → 解压到 `~/xt_sdk/` → 匹配当前 Python 版本的 `.so` 文件 → 配置 `LD_LIBRARY_PATH` → 验证 import。

## 手动安装

### 1. 下载并解压

```bash
SDK_URL="https://download.thinkfunds.cn:8080/directlink/API/XtTraderApi_V1.6_20260303.zip"
curl -fsSL "${SDK_URL}" -o /tmp/XtTraderApi.zip
unzip /tmp/XtTraderApi.zip -d ~/xt_sdk/
mkdir -p ~/xt_sdk/userdata/log
```

### 2. 配置动态库路径

```bash
echo 'export LD_LIBRARY_PATH=~/xt_sdk:$LD_LIBRARY_PATH' >> ~/.bashrc
source ~/.bashrc
```

### 3. 验证

```bash
cd ~/xt_sdk
python3 -c "from XtTraderPyApi import XtTraderApi; print('XtTraderApi import OK')"
```

## 在项目代码中引用

```python
import sys
import os

sys.path.insert(0, '/home/ubuntu/xt_sdk')
os.environ['LD_LIBRARY_PATH'] = '/home/ubuntu/xt_sdk:' + os.environ.get('LD_LIBRARY_PATH', '')

from XtTraderPyApi import XtTraderApi
```

初始化时使用绝对路径：

```python
api = XtTraderApi()
api.init("/home/ubuntu/xt_sdk/config")
```

## SDK 版本信息

| 字段 | 值 |
|------|-----|
| 版本 | V1.6_20260303 |
| 下载地址 | https://download.thinkfunds.cn:8080/directlink/API/XtTraderApi_V1.6_20260303.zip |
| 支持 Python 版本 | 3.6、3.7、3.8、3.9、3.10、3.11、3.12、3.13 |
| 平台 | Linux x86_64 |
| 本地部署路径 | `~/xt_sdk/` |

## 目录结构说明

```
~/xt_sdk/
├── config/
│   ├── traderApi.ini        # 服务端连接配置
│   ├── traderApi.log4cxx    # 日志格式配置
│   └── server.crt           # TLS 证书
├── userdata/
│   └── log/                 # SDK 运行时日志输出目录
├── XtTraderPyApi.cpython-312-x86_64-linux-gnu.so  # Python 扩展（按版本选择）
├── libXtTraderApi.so        # 核心交易库
├── libboost_*.so.*          # Boost 依赖
├── libicu*.so.*             # ICU 依赖
└── ...                      # 其他依赖库
```

## 常见问题

**`cannot open shared object file: libXXX.so`**
→ `LD_LIBRARY_PATH` 未生效，执行 `source ~/.bashrc`

**`No module named 'XtTraderPyApi'`**
→ 未在 `~/xt_sdk/` 目录下运行，或未添加 `sys.path`

**`version GLIBC_X.XX not found`**
→ 系统 glibc 版本过低，联系迅投获取兼容版本
