#!/usr/bin/env bash
# 阶段6单一入口：隔离Python依赖、隐藏读取密码并运行核心业务自动实验。

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${ROOT_DIR}/.venv-phase6"
PYTHON_BIN="${VENV_DIR}/bin/python"
RESULT_DIR="${ROOT_DIR}/results/phase6"
TIMESTAMP="$(date '+%Y%m%d_%H%M%S')"
LOG_FILE="${RESULT_DIR}/phase6_python_business_${TIMESTAMP}.txt"
PASSWORD_FILE=""
FINAL_STATUS="FAIL"

cleanup() {
    local exit_code=$?
    unset database_password OB_PASSWORD_FILE
    if [[ -n "${PASSWORD_FILE}" && -f "${PASSWORD_FILE}" ]]; then
        rm -f "${PASSWORD_FILE}"
    fi
    if [[ ${exit_code} -ne 0 && "${FINAL_STATUS}" != "PASS" ]]; then
        echo "最终状态：FAIL（退出码 ${exit_code}）" >&2
        [[ -f "${LOG_FILE}" ]] && echo "请保留日志：${LOG_FILE}" >&2
    fi
}
trap cleanup EXIT
trap 'exit 130' INT TERM

fail() {
    echo "FAIL：$*" >&2
    exit 1
}

command -v python3 >/dev/null 2>&1 || fail "未找到python3"

python_version="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' \
    || fail "需要Python 3.10或更高版本，当前为${python_version}"

if [[ ! -x "${PYTHON_BIN}" ]]; then
    echo "未检测到阶段6隔离环境，将创建：${VENV_DIR}"
    if ! python3 -m venv "${VENV_DIR}"; then
        fail "无法创建虚拟环境；请检查Ubuntu是否安装python3-venv"
    fi
fi

installed_version="$(${PYTHON_BIN} -c "import importlib.metadata as m; print(m.version('PyMySQL'))" 2>/dev/null || true)"
if [[ "${installed_version}" != "1.1.1" ]]; then
    echo "将在项目专用虚拟环境安装requirements.txt中的固定依赖，不修改系统Python。"
    "${PYTHON_BIN}" -m pip install --disable-pip-version-check \
        --requirement "${ROOT_DIR}/requirements.txt" \
        || fail "依赖安装失败；请保存pip错误并检查WSL网络"
fi

actual_version="$(${PYTHON_BIN} -c "import importlib.metadata as m; print(m.version('PyMySQL'))")"
[[ "${actual_version}" == "1.1.1" ]] || fail "PyMySQL版本错误：${actual_version}"

mkdir -p "${RESULT_DIR}"
exec > >(tee -a "${LOG_FILE}") 2>&1

echo "Python环境检查通过：Python ${python_version}，PyMySQL ${actual_version}"

echo "正在运行不连接数据库的阶段6单元测试。"
PYTHONPATH="${ROOT_DIR}" "${PYTHON_BIN}" -m unittest discover \
    -s "${ROOT_DIR}/tests" -p 'test_phase6_unit.py' -v \
    || fail "阶段6单元测试失败"

read -r -s -p "请输入root@coursework数据库密码：" database_password
printf '\n'
[[ -n "${database_password}" ]] || fail "数据库密码不能为空"

PASSWORD_FILE="$(mktemp "${TMPDIR:-/tmp}/phase6-ob-password.XXXXXX")"
chmod 600 "${PASSWORD_FILE}"
printf '%s' "${database_password}" > "${PASSWORD_FILE}"
unset database_password

export OB_PASSWORD_FILE="${PASSWORD_FILE}"
export OB_HOST="${OB_HOST:-127.0.0.1}"
export OB_PORT="${OB_PORT:-2881}"
export OB_USER="${OB_USER:-root@coursework}"
export OB_DATABASE="${OB_DATABASE:-phone_recharge_db}"
export PYTHONPATH="${ROOT_DIR}"
export PYTHONUNBUFFERED=1

echo "阶段6自动化开始：$(date '+%F %T %z')"
echo "日志：${LOG_FILE}"
echo "数据库密码仅保存在权限600的临时文件中，不写入日志或命令行。"

if ! "${PYTHON_BIN}" "${ROOT_DIR}/src/phase6_business_test.py"; then
    fail "Python业务自动实验失败；连接关闭时未提交事务会由数据库回滚"
fi

FINAL_STATUS="PASS"
echo "阶段6入口脚本最终状态：PASS"
