#!/usr/bin/env bash
# 阶段9单一入口：丢失更新、事务锁和同卡并发充值实验。
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${ROOT_DIR}/.venv-phase6/bin/python"
RESULT_DIR="${ROOT_DIR}/results/phase9"
LOG_FILE="${RESULT_DIR}/phase9_concurrency_$(date '+%Y%m%d_%H%M%S').txt"
PASSWORD_FILE=""
FINAL_STATUS="FAIL"

cleanup_secret() {
    local code=$?
    unset database_password OB_PASSWORD_FILE
    [[ -n "${PASSWORD_FILE}" && -f "${PASSWORD_FILE}" ]] && rm -f "${PASSWORD_FILE}"
    if [[ ${code} -ne 0 && "${FINAL_STATUS}" != "PASS" ]]; then
        echo "阶段9入口最终状态：FAIL（退出码 ${code}）" >&2
        echo "请保留日志：${LOG_FILE}" >&2
    fi
}
trap cleanup_secret EXIT
trap 'exit 130' INT TERM

[[ $# -eq 0 ]] || { echo "阶段9入口不接受参数" >&2; exit 2; }
[[ -x "${PYTHON_BIN}" ]] || { echo "缺少阶段6虚拟环境" >&2; exit 1; }
mkdir -p "${RESULT_DIR}"
exec > >(tee -a "${LOG_FILE}") 2>&1
echo "正在运行阶段9代码级测试。"
PYTHONPATH="${ROOT_DIR}" "${PYTHON_BIN}" -m unittest discover -s "${ROOT_DIR}/tests" -p 'test_phase9_unit.py' -v

read -r -s -p "请输入root@coursework数据库密码：" database_password
printf '\n'
[[ -n "${database_password}" ]] || { echo "数据库密码不能为空" >&2; exit 1; }
PASSWORD_FILE="$(mktemp "${TMPDIR:-/tmp}/phase9-ob-password.XXXXXX")"
chmod 600 "${PASSWORD_FILE}"
printf '%s' "${database_password}" > "${PASSWORD_FILE}"
unset database_password

export OB_PASSWORD_FILE="${PASSWORD_FILE}"
export OB_HOST="${OB_HOST:-127.0.0.1}"
export OB_PORT="${OB_PORT:-2881}"
export OB_USER="${OB_USER:-root@coursework}"
export OB_DATABASE="${OB_DATABASE:-phone_recharge_db}"
export P9_RESULT_DIR="${RESULT_DIR}"
export PYTHONPATH="${ROOT_DIR}"
export PYTHONUNBUFFERED=1

echo "阶段9自动化开始：$(date '+%F %T %z')"
echo "日志：${LOG_FILE}"
echo "负载依次为10、100、1000请求，最大并发连接依次为5、10、20。"
"${PYTHON_BIN}" "${ROOT_DIR}/src/phase9_concurrency.py"
FINAL_STATUS="PASS"
echo "阶段9入口最终状态：PASS"
