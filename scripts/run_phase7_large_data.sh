#!/usr/bin/env bash
# 阶段7单一入口：1000组预实验后可恢复地续跑至10万级数据。
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${ROOT_DIR}/.venv-phase6/bin/python"
RESULT_DIR="${ROOT_DIR}/results/phase7"
LOG_FILE="${RESULT_DIR}/phase7_large_data_$(date '+%Y%m%d_%H%M%S').txt"
PASSWORD_FILE=""
FINAL_STATUS="FAIL"

cleanup_secret() {
    local code=$?
    unset database_password OB_PASSWORD_FILE
    [[ -n "${PASSWORD_FILE}" && -f "${PASSWORD_FILE}" ]] && rm -f "${PASSWORD_FILE}"
    if [[ ${code} -ne 0 && "${FINAL_STATUS}" != "PASS" ]]; then
        echo "阶段7入口最终状态：FAIL（退出码 ${code}）" >&2
        [[ -f "${LOG_FILE}" ]] && echo "请保留日志：${LOG_FILE}" >&2
    fi
}
trap cleanup_secret EXIT
trap 'exit 130' INT TERM

[[ $# -le 1 ]] || { echo "仅支持无参数、--pilot-only或--cleanup" >&2; exit 2; }
MODE="${1:-}"
[[ -z "${MODE}" || "${MODE}" == "--pilot-only" || "${MODE}" == "--cleanup" ]] || { echo "未知参数：${MODE}" >&2; exit 2; }
[[ -x "${PYTHON_BIN}" ]] || { echo "缺少阶段6虚拟环境，请先确认阶段6环境" >&2; exit 1; }
"${PYTHON_BIN}" -c "import importlib.metadata as m; assert m.version('PyMySQL') == '1.1.1'" || { echo "PyMySQL依赖不符合要求" >&2; exit 1; }

mkdir -p "${RESULT_DIR}"
exec > >(tee -a "${LOG_FILE}") 2>&1
echo "正在运行阶段7代码级测试。"
PYTHONPATH="${ROOT_DIR}" "${PYTHON_BIN}" -m unittest discover -s "${ROOT_DIR}/tests" -p 'test_phase7_unit.py' -v

if [[ "${MODE}" == "--cleanup" ]]; then
    echo "清理模式连接后会先只读预览并校验P7范围，再要求确认；此时尚不会删除数据。"
elif [[ "${MODE}" == "--pilot-only" ]]; then
    echo "仅预实验模式最多生成1000组数据，校验并保存空间估算后立即退出。"
fi

read -r -s -p "请输入root@coursework数据库密码：" database_password
printf '\n'
[[ -n "${database_password}" ]] || { echo "数据库密码不能为空" >&2; exit 1; }
PASSWORD_FILE="$(mktemp "${TMPDIR:-/tmp}/phase7-ob-password.XXXXXX")"
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
export P7_ESTIMATE_FILE="${RESULT_DIR}/phase7_space_estimate.json"

echo "阶段7自动化开始：$(date '+%F %T %z')"
echo "日志：${LOG_FILE}"
echo "密码只存在权限600的临时文件中。默认批次500行，不修改OceanBase资源参数。"
"${PYTHON_BIN}" "${ROOT_DIR}/src/phase7_large_data.py" ${MODE:+"${MODE}"}
FINAL_STATUS="PASS"
echo "阶段7入口最终状态：PASS"
