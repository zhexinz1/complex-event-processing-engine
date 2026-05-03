#!/usr/bin/env bash
# 将 CTP/OpenCTP 原生 .so 覆盖到当前项目 .venv 中。
# 默认从仓库内的 ctp_package/ 读取，也兼容 openctp wheel 解压后的目录结构。
# 用法:
#   scripts/swap_openctp_so.sh
#   scripts/swap_openctp_so.sh --source ctp_package
#   scripts/swap_openctp_so.sh --source /path/to/extracted_release

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
VENV_PYTHON_DIR="$(find "${REPO_ROOT}/.venv/lib" -maxdepth 1 -mindepth 1 -type d -name 'python3.*' | head -n 1)"

if [[ -z "${VENV_PYTHON_DIR}" ]]; then
    echo "错误: 未找到 ${REPO_ROOT}/.venv/lib/python3.* 目录。请先执行 uv sync。"
    exit 1
fi

TARGET_PKG_DIR="${VENV_PYTHON_DIR}/site-packages/openctp_ctp"
TARGET_LIBS_DIR="${VENV_PYTHON_DIR}/site-packages/openctp_ctp.libs"
BACKUP_ROOT="${REPO_ROOT}/.openctp_so_backup"

SOURCE_ROOT="${REPO_ROOT}/ctp_package"

usage() {
    cat <<'EOF'
用法:
  scripts/swap_openctp_so.sh
  scripts/swap_openctp_so.sh --source <目录>

默认源目录:
  ./ctp_package

支持两种源目录结构:
  1. Python wheel 解压结构:
     openctp_ctp/_thostmduserapi.so
     openctp_ctp/_thosttraderapi.so
     openctp_ctp.libs/libthostmduserapi_se*.so
     openctp_ctp.libs/libthosttraderapi_se*.so

  2. 平铺 SDK 结构:
     thostmduserapi_se.so
     thosttraderapi_se.so

说明:
  - 若源目录只有平铺 SDK 结构，脚本会保留当前已安装的 Python wrapper
    (_thostmduserapi.so / _thosttraderapi.so)，仅替换底层核心动态库。
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --source)
            SOURCE_ROOT="${2:-}"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "错误: 未知参数: $1"
            usage
            exit 1
            ;;
    esac
done

SOURCE_ROOT="$(cd "${SOURCE_ROOT}" && pwd)"
SOURCE_PKG_DIR="${SOURCE_ROOT}/openctp_ctp"
SOURCE_LIBS_DIR="${SOURCE_ROOT}/openctp_ctp.libs"

MD_WRAPPER_SRC=""
TR_WRAPPER_SRC=""
MD_CORE_SRC=""
TR_CORE_SRC=""

if [[ -d "${SOURCE_PKG_DIR}" && -d "${SOURCE_LIBS_DIR}" ]]; then
    MD_WRAPPER_SRC="${SOURCE_PKG_DIR}/_thostmduserapi.so"
    TR_WRAPPER_SRC="${SOURCE_PKG_DIR}/_thosttraderapi.so"
    MD_CORE_SRC="$(find "${SOURCE_LIBS_DIR}" -maxdepth 1 -type f -name 'libthostmduserapi_se*.so' | head -n 1)"
    TR_CORE_SRC="$(find "${SOURCE_LIBS_DIR}" -maxdepth 1 -type f -name 'libthosttraderapi_se*.so' | head -n 1)"

    if [[ ! -f "${MD_WRAPPER_SRC}" || ! -f "${TR_WRAPPER_SRC}" || -z "${MD_CORE_SRC}" || -z "${TR_CORE_SRC}" ]]; then
        echo "错误: ${SOURCE_ROOT} 的 wheel 结构不完整。"
        exit 1
    fi
else
    MD_CORE_SRC="${SOURCE_ROOT}/thostmduserapi_se.so"
    TR_CORE_SRC="${SOURCE_ROOT}/thosttraderapi_se.so"

    if [[ ! -f "${MD_CORE_SRC}" || ! -f "${TR_CORE_SRC}" ]]; then
        echo "错误: ${SOURCE_ROOT} 不是有效的 CTP/OpenCTP 二进制目录。"
        exit 1
    fi
fi

if [[ ! -d "${TARGET_PKG_DIR}" || ! -d "${TARGET_LIBS_DIR}" ]]; then
    echo "错误: 目标目录不存在，请确认 openctp-ctp 已安装到当前 .venv。"
    exit 1
fi

TARGET_MD_CORE="$(find "${TARGET_LIBS_DIR}" -maxdepth 1 -type f -name 'libthostmduserapi_se*.so' | head -n 1)"
TARGET_TR_CORE="$(find "${TARGET_LIBS_DIR}" -maxdepth 1 -type f -name 'libthosttraderapi_se*.so' | head -n 1)"

if [[ -z "${TARGET_MD_CORE}" || -z "${TARGET_TR_CORE}" ]]; then
    echo "错误: 目标 openctp_ctp.libs 中缺少预期的核心动态库。"
    exit 1
fi

TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_DIR="${BACKUP_ROOT}/${TIMESTAMP}"

mkdir -p "${BACKUP_DIR}/openctp_ctp" "${BACKUP_DIR}/openctp_ctp.libs"

echo "=== OpenCTP .so 替换 ==="
echo "仓库: ${REPO_ROOT}"
echo "源目录: ${SOURCE_ROOT}"
echo "目标目录: ${TARGET_PKG_DIR}"
echo "备份目录: ${BACKUP_DIR}"

cp -a "${TARGET_PKG_DIR}/_thostmduserapi.so" "${BACKUP_DIR}/openctp_ctp/"
cp -a "${TARGET_PKG_DIR}/_thosttraderapi.so" "${BACKUP_DIR}/openctp_ctp/"
find "${TARGET_LIBS_DIR}" -maxdepth 1 -type f -name 'libthostmduserapi_se*.so' -exec cp -a {} "${BACKUP_DIR}/openctp_ctp.libs/" \;
find "${TARGET_LIBS_DIR}" -maxdepth 1 -type f -name 'libthosttraderapi_se*.so' -exec cp -a {} "${BACKUP_DIR}/openctp_ctp.libs/" \;

if [[ -n "${MD_WRAPPER_SRC}" && -n "${TR_WRAPPER_SRC}" ]]; then
    rm -f "${TARGET_PKG_DIR}/_thostmduserapi.so" "${TARGET_PKG_DIR}/_thosttraderapi.so"
    cp -a "${MD_WRAPPER_SRC}" "${TARGET_PKG_DIR}/"
    cp -a "${TR_WRAPPER_SRC}" "${TARGET_PKG_DIR}/"
fi

cp -a "${MD_CORE_SRC}" "${TARGET_MD_CORE}"
cp -a "${TR_CORE_SRC}" "${TARGET_TR_CORE}"

echo ""
echo "当前已安装文件:"
ls -1 "${TARGET_PKG_DIR}"/_thost*.so
ls -1 "${TARGET_LIBS_DIR}"/libthost*userapi_se*.so

echo ""
echo "校验哈希:"
sha256sum \
    "${TARGET_PKG_DIR}/_thostmduserapi.so" \
    "${TARGET_PKG_DIR}/_thosttraderapi.so" \
    "${TARGET_LIBS_DIR}"/libthostmduserapi_se*.so \
    "${TARGET_LIBS_DIR}"/libthosttraderapi_se*.so

echo ""
echo "替换完成。注意: 后续 uv sync 可能会覆盖这些文件，需要重新执行本脚本。"
