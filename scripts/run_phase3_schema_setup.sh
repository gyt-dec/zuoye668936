#!/usr/bin/env bash
# 阶段 3 一次性初始化：建库、建表、结构验证和约束验证。
# 不执行阶段 4 CRUD、大数据、索引或并发实验。

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SQL_DIR="${ROOT_DIR}/sql"
RESULT_DIR="${ROOT_DIR}/results/phase3"
TIMESTAMP="$(date '+%Y%m%d_%H%M%S')"
LOG_FILE="${RESULT_DIR}/phase3_schema_setup_${TIMESTAMP}.txt"
CONSTRAINT_LOG="${RESULT_DIR}/constraint_expected_failures_${TIMESTAMP}.txt"
FK_LOG="${RESULT_DIR}/foreign_key_expected_failures_${TIMESTAMP}.txt"
CREDENTIAL_FILE=""
FINAL_STATUS="FAIL"

cleanup() {
    local exit_code=$?
    unset coursework_password
    if [[ -n "${CREDENTIAL_FILE}" && -f "${CREDENTIAL_FILE}" ]]; then
        rm -f "${CREDENTIAL_FILE}"
    fi
    if [[ ${exit_code} -ne 0 && "${FINAL_STATUS}" != "PASS" ]]; then
        echo "最终状态：FAIL（退出码 ${exit_code}）" >&2
        if [[ -n "${LOG_FILE}" && -f "${LOG_FILE}" ]]; then
            echo "请保留日志：${LOG_FILE}" >&2
        fi
    fi
}
trap cleanup EXIT
trap 'exit 130' INT TERM

fail() {
    echo "FAIL：$*" >&2
    echo "阶段 3 初始化已安全停止。请保留日志：${LOG_FILE}" >&2
    exit 1
}

require_file() {
    [[ -f "$1" ]] || fail "缺少文件：$1"
}

obclient_base() {
    obclient --defaults-extra-file="${CREDENTIAL_FILE}" -A "$@"
}

query_scalar() {
    obclient_base --batch --skip-column-names -e "$1"
}

assert_equals() {
    local label="$1"
    local expected="$2"
    local actual="$3"
    if [[ "${actual}" != "${expected}" ]]; then
        fail "${label} 不符合预期：expected=${expected}, actual=${actual}"
    fi
    echo "PASS：${label} = ${actual}"
}

run_strict_sql_file() {
    local label="$1"
    local file="$2"
    echo
    echo "===== ${label} ====="
    if ! obclient_base --batch < "${file}"; then
        fail "${label} 执行出现真正错误"
    fi
    echo "PASS：${label}"
}

for required in \
    "${SQL_DIR}/00_create_database.sql" \
    "${SQL_DIR}/01_create_schema.sql" \
    "${SQL_DIR}/02_verify_schema.sql" \
    "${SQL_DIR}/03_verify_constraints.sql" \
    "${SQL_DIR}/04_verify_foreign_keys.sql" \
    "${ROOT_DIR}/scripts/check_expected_failures.py"; do
    require_file "${required}"
done

command -v obclient >/dev/null 2>&1 || fail "未找到 obclient"
command -v python3 >/dev/null 2>&1 || fail "未找到 python3"

echo "阶段 3 一次性初始化将创建 phone_recharge_db 和 7 张空业务表。"
echo "若数据库已经存在，脚本会拒绝继续；脚本不会执行 DROP 或 TRUNCATE。"
read -r -s -p "请输入 root@coursework 密码：" coursework_password
printf '\n'

if [[ -z "${coursework_password}" ]]; then
    fail "密码不能为空"
fi
if [[ "${coursework_password}" == *"'"* || "${coursework_password}" == *"\\"* ]]; then
    fail "当前安全配置文件方式不接受单引号或反斜杠密码"
fi

CREDENTIAL_FILE="$(mktemp "${TMPDIR:-/tmp}/phase3-obclient.XXXXXX")"
chmod 600 "${CREDENTIAL_FILE}"
{
    printf '[client]\n'
    printf 'host=127.0.0.1\n'
    printf 'port=2881\n'
    printf 'user=root@coursework\n'
    printf "password='%s'\n" "${coursework_password}"
    printf 'default-character-set=utf8mb4\n'
} > "${CREDENTIAL_FILE}"
unset coursework_password

mkdir -p "${RESULT_DIR}"
exec > >(tee -a "${LOG_FILE}") 2>&1

echo "阶段 3 自动化开始：$(date '+%F %T %z')"
echo "仓库：${ROOT_DIR}"
echo "日志：${LOG_FILE}"

identity="$(query_scalar "SELECT CONCAT(CURRENT_USER(), '|', VERSION(), '|', @@ob_compatibility_mode);")" \
    || fail "无法连接 root@coursework"
echo "连接验证：${identity}"
[[ "${identity}" == root@%\|*OceanBase*\|MYSQL ]] \
    || fail "账户、OceanBase 版本或 MYSQL 兼容模式不符合预期"
echo "PASS：root@coursework 连接、OceanBase 版本和 MYSQL 模式"

database_count="$(query_scalar "SELECT COUNT(*) FROM information_schema.SCHEMATA WHERE SCHEMA_NAME='phone_recharge_db';")" \
    || fail "无法检查数据库是否存在"
if [[ "${database_count}" != "0" ]]; then
    fail "phone_recharge_db 已存在；本脚本是一次性初始化脚本，不会覆盖或清空已有环境"
fi
echo "PASS：执行前确认 phone_recharge_db 不存在"

run_strict_sql_file "创建 phone_recharge_db" "${SQL_DIR}/00_create_database.sql"
run_strict_sql_file "创建 7 张业务表" "${SQL_DIR}/01_create_schema.sql"
run_strict_sql_file "输出 Schema 验证详情" "${SQL_DIR}/02_verify_schema.sql"

table_count="$(query_scalar "SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA='phone_recharge_db' AND TABLE_TYPE='BASE TABLE';")"
pk_count="$(query_scalar "SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS WHERE CONSTRAINT_SCHEMA='phone_recharge_db' AND CONSTRAINT_TYPE='PRIMARY KEY';")"
unique_count="$(query_scalar "SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS WHERE CONSTRAINT_SCHEMA='phone_recharge_db' AND CONSTRAINT_TYPE='UNIQUE';")"
fk_count="$(query_scalar "SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS WHERE CONSTRAINT_SCHEMA='phone_recharge_db' AND CONSTRAINT_TYPE='FOREIGN KEY';")"
check_count="$(query_scalar "SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS WHERE CONSTRAINT_SCHEMA='phone_recharge_db' AND CONSTRAINT_TYPE='CHECK';")"
restrict_count="$(query_scalar "SELECT COUNT(*) FROM information_schema.REFERENTIAL_CONSTRAINTS WHERE CONSTRAINT_SCHEMA='phone_recharge_db' AND UPDATE_RULE='RESTRICT' AND DELETE_RULE='RESTRICT';")"

assert_equals "业务表数量" "7" "${table_count}"
assert_equals "主键数量" "7" "${pk_count}"
assert_equals "UNIQUE 数量" "6" "${unique_count}"
assert_equals "外键数量" "6" "${fk_count}"
assert_equals "CHECK 数量" "18" "${check_count}"
assert_equals "ON UPDATE/DELETE RESTRICT 外键数量" "6" "${restrict_count}"

echo
echo "===== UNIQUE 与 CHECK 预期失败测试 ====="
set +e
obclient_base --force --unbuffered --batch < "${SQL_DIR}/03_verify_constraints.sql" 2>&1 \
    | tee "${CONSTRAINT_LOG}"
constraint_client_rc=${PIPESTATUS[0]}
set -e
echo "obclient 返回码（包含预期错误）：${constraint_client_rc}"
python3 "${ROOT_DIR}/scripts/check_expected_failures.py" "${CONSTRAINT_LOG}" \
    --expected "U01,U02,U03,U04,U05,U06,C01,C02,C03,C04,C05" \
    || fail "UNIQUE/CHECK 预期失败分类未通过"

constraint_residue="$(query_scalar "SELECT (SELECT COUNT(*) FROM phone_recharge_db.app_user WHERE login_name='__p3_user__') + (SELECT COUNT(*) FROM phone_recharge_db.purchase_order WHERE order_no='__P3_ORDER__') + (SELECT COUNT(*) FROM phone_recharge_db.recharge_card WHERE card_no LIKE '__P3_CARD_%');")"
assert_equals "UNIQUE/CHECK 测试回滚残留行数" "0" "${constraint_residue}"

echo
echo "===== 外键与 RESTRICT 预期失败测试 ====="
set +e
obclient_base --force --unbuffered --batch < "${SQL_DIR}/04_verify_foreign_keys.sql" 2>&1 \
    | tee "${FK_LOG}"
fk_client_rc=${PIPESTATUS[0]}
set -e
echo "obclient 返回码（包含预期错误）：${fk_client_rc}"
python3 "${ROOT_DIR}/scripts/check_expected_failures.py" "${FK_LOG}" \
    --expected "F01,F02,F03,F04,F05,F06,R01,R02,R03,R04,R05,R06" \
    || fail "外键/RESTRICT 预期失败分类未通过"

fk_residue="$(query_scalar "SELECT (SELECT COUNT(*) FROM phone_recharge_db.app_user WHERE login_name='__p3_fk_user__') + (SELECT COUNT(*) FROM phone_recharge_db.purchase_order WHERE order_no='__P3_FK_ORDER__') + (SELECT COUNT(*) FROM phone_recharge_db.recharge_card WHERE card_no LIKE '__P3_FK_CARD_%');")"
assert_equals "外键测试回滚残留行数" "0" "${fk_residue}"

FINAL_STATUS="PASS"
echo
echo "========== 阶段 3 汇总 =========="
echo "PASS：phone_recharge_db 创建成功"
echo "PASS：7 张业务表创建成功"
echo "PASS：7 PK / 6 UNIQUE / 18 CHECK"
echo "PASS：6 FK，且 UPDATE_RULE/DELETE_RULE 均为 RESTRICT"
echo "PASS：11 个 UNIQUE/CHECK 预期失败均被正确识别"
echo "PASS：12 个 FK/RESTRICT 预期失败均被正确识别"
echo "PASS：两个事务测试均无残留数据"
echo "日志：${LOG_FILE}"
echo "最终状态：${FINAL_STATUS}"
