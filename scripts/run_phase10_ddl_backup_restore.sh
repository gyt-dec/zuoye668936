#!/usr/bin/env bash
# 阶段10单一入口：在线DDL、数据校验、逻辑备份、误删除和真实恢复。
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${ROOT_DIR}/.venv-phase6/bin/python"
RESULT_DIR="${ROOT_DIR}/results/phase10"
LOG_FILE="${RESULT_DIR}/phase10_ddl_backup_restore_$(date '+%Y%m%d_%H%M%S').txt"
PASSWORD_FILE=""; FINAL_STATUS="FAIL"

cleanup_secret() {
    local code=$?
    unset database_password OB_PASSWORD_FILE
    [[ -n "${PASSWORD_FILE}" && -f "${PASSWORD_FILE}" ]] && rm -f "${PASSWORD_FILE}"
    if [[ ${code} -ne 0 && "${FINAL_STATUS}" != "PASS" ]]; then
        echo "阶段10入口最终状态：FAIL（退出码 ${code}）" >&2
        echo "保留备份、状态文件和数据库现场，不要盲目重跑：${LOG_FILE}" >&2
    fi
}
trap cleanup_secret EXIT
trap 'exit 130' INT TERM
[[ $# -eq 0 ]] || { echo "阶段10入口不接受参数" >&2; exit 2; }
[[ -x "${PYTHON_BIN}" ]] || { echo "缺少阶段6虚拟环境" >&2; exit 1; }
mkdir -p "${RESULT_DIR}"
exec > >(tee -a "${LOG_FILE}") 2>&1
PYTHONPATH="${ROOT_DIR}" "${PYTHON_BIN}" -m unittest discover -s "${ROOT_DIR}/tests" -p 'test_phase10_unit.py' -v
read -r -s -p "请输入root@coursework数据库密码：" database_password; printf '\n'
[[ -n "${database_password}" ]] || { echo "数据库密码不能为空" >&2; exit 1; }
PASSWORD_FILE="$(mktemp "${TMPDIR:-/tmp}/phase10-ob-password.XXXXXX")"; chmod 600 "${PASSWORD_FILE}"
printf '%s' "${database_password}" > "${PASSWORD_FILE}"; unset database_password
export OB_PASSWORD_FILE="${PASSWORD_FILE}" OB_HOST="${OB_HOST:-127.0.0.1}" OB_PORT="${OB_PORT:-2881}"
export OB_USER="${OB_USER:-root@coursework}" OB_DATABASE="${OB_DATABASE:-phone_recharge_db}"
export P10_RESULT_DIR="${RESULT_DIR}" PYTHONPATH="${ROOT_DIR}" PYTHONUNBUFFERED=1
echo "阶段10自动化开始：$(date '+%F %T %z')"; echo "日志：${LOG_FILE}"
echo "失败时保留P10现场和0600备份；只有恢复校验完全通过后才清理P10。"
"${PYTHON_BIN}" "${ROOT_DIR}/src/phase10_ddl_backup_restore.py"
FINAL_STATUS="PASS"; echo "阶段10入口最终状态：PASS"
