#!/usr/bin/env bash
# 迅投 XtTrader Python API SDK 一键安装脚本
# SDK 下载地址: https://download.thinkfunds.cn:8080/directlink/API/XtTraderApi_V1.6_20260303.zip

set -euo pipefail

SDK_URL="https://download.thinkfunds.cn:8080/directlink/API/XtTraderApi_V1.6_20260303.zip"
SDK_DIR="${HOME}/xt_sdk"
ZIP_FILE="/tmp/XtTraderApi.zip"

echo "=== 迅投 XtTrader SDK 安装脚本 ==="

# 检查 Python 版本
PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}{sys.version_info.minor}')")
PYTHON_VERSION_FULL=$(python3 --version)
echo "[1/5] 检测到 Python 版本: ${PYTHON_VERSION_FULL}"

# 下载 SDK
echo "[2/5] 正在下载 SDK..."
if ! curl -fsSL "${SDK_URL}" -o "${ZIP_FILE}"; then
    echo "错误: 下载失败，请检查网络连接或手动下载："
    echo "  ${SDK_URL}"
    echo "下载后放置到 /tmp/XtTraderApi.zip 并重新运行本脚本。"
    exit 1
fi
echo "      下载完成: ${ZIP_FILE}"

# 解压
echo "[3/5] 正在解压到 ${SDK_DIR}..."
mkdir -p "${SDK_DIR}"
unzip -o "${ZIP_FILE}" -d "${SDK_DIR}"
rm -f "${ZIP_FILE}"

# 创建运行时必要目录
mkdir -p "${SDK_DIR}/userdata/log"
echo "      解压完成"

# 检查对应 .so 文件是否存在
SO_FILE="${SDK_DIR}/XtTraderPyApi.cpython-${PYTHON_VERSION}-x86_64-linux-gnu.so"
if [ ! -f "${SO_FILE}" ]; then
    echo "警告: 未找到 Python ${PYTHON_VERSION_FULL} 对应的 .so 文件: ${SO_FILE}"
    echo "      SDK 中包含以下版本:"
    ls "${SDK_DIR}"/XtTraderPyApi.cpython-*.so 2>/dev/null || echo "      未找到任何 .so 文件"
    exit 1
fi
echo "      找到对应 .so 文件: $(basename ${SO_FILE})"

# 配置 LD_LIBRARY_PATH
BASHRC="${HOME}/.bashrc"
LD_LINE='export LD_LIBRARY_PATH=~/xt_sdk:$LD_LIBRARY_PATH'
if grep -q "LD_LIBRARY_PATH.*xt_sdk" "${BASHRC}" 2>/dev/null; then
    echo "[4/5] LD_LIBRARY_PATH 已配置，跳过"
else
    echo "[4/5] 写入 LD_LIBRARY_PATH 到 ${BASHRC}..."
    echo "${LD_LINE}" >> "${BASHRC}"
fi
export LD_LIBRARY_PATH="${SDK_DIR}:${LD_LIBRARY_PATH:-}"

# 验证 import
echo "[5/5] 验证 import..."
cd "${SDK_DIR}"
if python3 -c "from XtTraderPyApi import XtTraderApi; print('XtTraderApi import OK')"; then
    echo ""
    echo "=== 安装成功 ==="
    echo "SDK 路径: ${SDK_DIR}"
    echo "请执行 'source ~/.bashrc' 使环境变量在当前终端生效。"
else
    echo "错误: import 验证失败，请检查上方错误信息。"
    exit 1
fi
