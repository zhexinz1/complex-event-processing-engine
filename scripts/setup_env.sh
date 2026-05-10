#!/usr/bin/env bash
# scripts/setup_env.sh — 统一设置项目运行所需的环境变量
#
# 用途：在部署或开发前运行此脚本，确保所有依赖路径和配置正确。
#
# 使用方式：
#   source scripts/setup_env.sh          # 当前终端生效
#   source scripts/setup_env.sh --check  # 仅检查，不设置
#
# 说明：
#   本脚本统一管理以下环境变量：
#     XT_SDK_PATH       - 迅投 SDK 安装路径（默认 ~/xt_sdk）
#     LD_LIBRARY_PATH   - 动态链接库搜索路径（自动追加 XT_SDK_PATH）
#
# 生产部署时请确保先 source 此脚本，以验证所有依赖是否就绪。

set -euo pipefail

CHECK_ONLY=false
if [[ "${1:-}" == "--check" ]]; then
    CHECK_ONLY=true
fi

# ---- 迅投 SDK 路径 ----
XT_SDK_PATH="${XT_SDK_PATH:-$HOME/xt_sdk}"

if [[ ! -d "$XT_SDK_PATH" ]]; then
    echo "❌ 迅投 SDK 目录不存在: $XT_SDK_PATH"
    echo "   请安装 SDK 或设置 XT_SDK_PATH 环境变量指向正确路径。"
    if $CHECK_ONLY; then
        return 1 2>/dev/null || exit 1
    fi
else
    echo "✅ 迅投 SDK 目录: $XT_SDK_PATH"
fi

# ---- LD_LIBRARY_PATH ----
if [[ ":${LD_LIBRARY_PATH:-}:" != *":$XT_SDK_PATH:"* ]]; then
    if $CHECK_ONLY; then
        echo "⚠️  LD_LIBRARY_PATH 未包含 $XT_SDK_PATH"
    else
        export LD_LIBRARY_PATH="${XT_SDK_PATH}:${LD_LIBRARY_PATH:-}"
        echo "✅ LD_LIBRARY_PATH 已追加: $XT_SDK_PATH"
    fi
else
    echo "✅ LD_LIBRARY_PATH 已包含: $XT_SDK_PATH"
fi

# ---- 导出 XT_SDK_PATH ----
if ! $CHECK_ONLY; then
    export XT_SDK_PATH
    echo "✅ XT_SDK_PATH=$XT_SDK_PATH"
fi

# ---- .env 文件检查 ----
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
ENV_FILE="$PROJECT_ROOT/.env"

if [[ -f "$ENV_FILE" ]]; then
    echo "✅ .env 文件: $ENV_FILE"
else
    echo "⚠️  .env 文件不存在: $ENV_FILE（非必须，但建议配置数据库等连接参数）"
fi

echo ""
echo "环境变量设置完成。可以启动服务了。"
