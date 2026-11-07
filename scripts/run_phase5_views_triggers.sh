#!/usr/bin/env bash
# 阶段 5 一次性入口：创建并测试 2 个视图和 2 个触发器。
# 不执行大数据、索引、并发实验，不删除或清空业务表。

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SQL_DIR="${ROOT_DIR}/sql"
RESULT_DIR="${ROOT_DIR}/results/phase5"
TIMESTAMP="$(date '+%Y%m%d_%H%M%S')"
LOG_FILE="${RESULT_DIR}/phase5_views_triggers_${TIMESTAMP}.txt"
TEST_LOG="${RESULT_DIR}/phase5_trigger_tests_${TIMESTAMP}.txt"
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
        [[ -f "${LOG_FILE}" ]] && echo "请保留日志：${LOG_FILE}" >&2
    fi
}
trap cleanup EXIT
trap 'exit 130' INT TERM

fail() {
    echo "FAIL：$*" >&2
    echo "阶段 5 已安全停止。不要直接重跑；先检查视图/触发器是否已部分创建。" >&2
    exit 1
}

obclient_base() {
    obclient --defaults-extra-file="${CREDENTIAL_FILE}" -A "$@"
}

query_scalar() {
    obclient_base --batch --skip-column-names -e "$1"
}

assert_equals() {
    local label="$1" expected="$2" actual="$3"
    [[ "${actual}" == "${expected}" ]] || \
        fail "${label} 不符合预期：expected=${expected}, actual=${actual}"
    echo "PASS：${label} = ${actual}"
}

run_sql_file() {
    local label="$1" file="$2"
    echo
    echo "===== ${label} ====="
    obclient_base --batch < "${file}" || fail "${label} 出现真正错误"
    echo "PASS：${label}"
}

for required in \
    "${SQL_DIR}/20_create_phase5_views.sql" \
    "${SQL_DIR}/21_create_phase5_triggers.sql" \
    "${SQL_DIR}/22_verify_phase5_objects.sql" \
    "${SQL_DIR}/23_test_phase5_triggers.sql" \
    "${ROOT_DIR}/scripts/check_phase5_trigger_log.py"; do
    [[ -f "${required}" ]] || fail "缺少文件：${required}"
done
command -v obclient >/dev/null 2>&1 || fail "未找到 obclient"
command -v python3 >/dev/null 2>&1 || fail "未找到 python3"

echo "阶段 5 将创建 2 个视图和 2 个触发器，并在事务中测试后回滚 P5 数据。"
echo "脚本不会 DROP/TRUNCATE 业务表、不会关闭外键，也不会修改阶段 4 数据。"
read -r -s -p "请输入 root@coursework 密码：" coursework_password
printf '\n'
[[ -n "${coursework_password}" ]] || fail "密码不能为空"
if [[ "${coursework_password}" == *"'"* || "${coursework_password}" == *"\\"* ]]; then
    fail "当前临时配置方式不接受单引号或反斜杠密码"
fi

CREDENTIAL_FILE="$(mktemp "${TMPDIR:-/tmp}/phase5-obclient.XXXXXX")"
chmod 600 "${CREDENTIAL_FILE}"
{
    printf '[client]\n'
    printf 'host=127.0.0.1\nport=2881\nuser=root@coursework\n'
    printf "password='%s'\n" "${coursework_password}"
    printf 'default-character-set=utf8mb4\n'
} > "${CREDENTIAL_FILE}"
unset coursework_password

mkdir -p "${RESULT_DIR}"
exec > >(tee -a "${LOG_FILE}") 2>&1

echo "阶段 5 自动化开始：$(date '+%F %T %z')"
echo "日志：${LOG_FILE}"

identity="$(query_scalar "SELECT CONCAT(CURRENT_USER(), '|', VERSION(), '|', @@ob_compatibility_mode);")" \
    || fail "无法连接 root@coursework"
[[ "${identity}" == root@%\|*OceanBase*\|MYSQL ]] || fail "账户、版本或兼容模式错误：${identity}"
echo "PASS：连接验证 ${identity}"

table_count="$(query_scalar "SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA='phone_recharge_db' AND TABLE_TYPE='BASE TABLE';")"
assert_equals "业务表数量" "7" "${table_count}"

baseline_p4="$(query_scalar "SELECT CONCAT(
 (SELECT COUNT(*) FROM phone_recharge_db.app_user WHERE login_name LIKE 'p4_user_%'),',',
 (SELECT COUNT(*) FROM phone_recharge_db.owner WHERE owner_name LIKE 'P4_OWNER_%'),',',
 (SELECT COUNT(*) FROM phone_recharge_db.mobile_number WHERE phone_number LIKE '1994000%'),',',
 (SELECT COUNT(*) FROM phone_recharge_db.purchase_order WHERE order_no LIKE 'P4-ORDER-%'),',',
 (SELECT COUNT(*) FROM phone_recharge_db.order_item oi JOIN phone_recharge_db.purchase_order po ON po.order_id=oi.order_id WHERE po.order_no LIKE 'P4-ORDER-%'),',',
 (SELECT COUNT(*) FROM phone_recharge_db.recharge_card WHERE card_no LIKE 'P4-CARD-%'),',',
 (SELECT COUNT(*) FROM phone_recharge_db.recharge_record rr JOIN phone_recharge_db.recharge_card rc ON rc.card_id=rr.card_id WHERE rc.card_no LIKE 'P4-CARD-%')); ")"
assert_equals "阶段4基准行数" "10,10,11,10,11,11,10" "${baseline_p4}"

existing_p5="$(query_scalar "SELECT
 (SELECT COUNT(*) FROM phone_recharge_db.app_user WHERE login_name LIKE 'p5_user_%')+
 (SELECT COUNT(*) FROM phone_recharge_db.owner WHERE owner_name LIKE 'P5_OWNER_%')+
 (SELECT COUNT(*) FROM phone_recharge_db.mobile_number WHERE phone_number LIKE '1995000%')+
 (SELECT COUNT(*) FROM phone_recharge_db.purchase_order WHERE order_no LIKE 'P5-ORDER-%')+
 (SELECT COUNT(*) FROM phone_recharge_db.recharge_card WHERE card_no LIKE 'P5-CARD-%');")"
assert_equals "执行前P5标记数据总数" "0" "${existing_p5}"

existing_objects="$(query_scalar "SELECT
 (SELECT COUNT(*) FROM information_schema.VIEWS WHERE TABLE_SCHEMA='phone_recharge_db' AND TABLE_NAME IN ('v_user_card_purchase_detail','v_mobile_recharge_history'))+
 (SELECT COUNT(*) FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA='phone_recharge_db' AND TRIGGER_NAME IN ('trg_recharge_record_validate','trg_recharge_record_mark_card_used'));")"
assert_equals "执行前阶段5对象数量" "0" "${existing_objects}"

run_sql_file "创建两个视图" "${SQL_DIR}/20_create_phase5_views.sql"

view_count="$(query_scalar "SELECT COUNT(*) FROM information_schema.VIEWS WHERE TABLE_SCHEMA='phone_recharge_db' AND TABLE_NAME IN ('v_user_card_purchase_detail','v_mobile_recharge_history');")"
view_columns="$(query_scalar "SELECT CONCAT(
 (SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA='phone_recharge_db' AND TABLE_NAME='v_user_card_purchase_detail'),',',
 (SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA='phone_recharge_db' AND TABLE_NAME='v_mobile_recharge_history'));")"
view_rows="$(query_scalar "SELECT CONCAT(
 (SELECT COUNT(*) FROM phone_recharge_db.v_user_card_purchase_detail WHERE card_no LIKE 'P4-CARD-%'),',',
 (SELECT COUNT(*) FROM phone_recharge_db.v_mobile_recharge_history WHERE card_no LIKE 'P4-CARD-%'));")"
assert_equals "视图数量" "2" "${view_count}"
assert_equals "视图列数 purchase,recharge" "15,11" "${view_columns}"
assert_equals "视图中的阶段4行数 purchase,recharge" "11,10" "${view_rows}"

run_sql_file "创建两个触发器" "${SQL_DIR}/21_create_phase5_triggers.sql"

trigger_count="$(query_scalar "SELECT COUNT(*) FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA='phone_recharge_db' AND TRIGGER_NAME IN ('trg_recharge_record_validate','trg_recharge_record_mark_card_used');")"
before_count="$(query_scalar "SELECT COUNT(*) FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA='phone_recharge_db' AND TRIGGER_NAME='trg_recharge_record_validate' AND ACTION_TIMING='BEFORE' AND EVENT_MANIPULATION='INSERT' AND EVENT_OBJECT_TABLE='recharge_record';")"
after_count="$(query_scalar "SELECT COUNT(*) FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA='phone_recharge_db' AND TRIGGER_NAME='trg_recharge_record_mark_card_used' AND ACTION_TIMING='AFTER' AND EVENT_MANIPULATION='INSERT' AND EVENT_OBJECT_TABLE='recharge_record';")"
assert_equals "触发器数量" "2" "${trigger_count}"
assert_equals "BEFORE INSERT 触发器元数据" "1" "${before_count}"
assert_equals "AFTER INSERT 触发器元数据" "1" "${after_count}"

run_sql_file "输出视图和触发器验证详情" "${SQL_DIR}/22_verify_phase5_objects.sql"

echo
echo "===== 触发器正常路径与预期失败测试 ====="
set +e
obclient_base --force --unbuffered --batch < "${SQL_DIR}/23_test_phase5_triggers.sql" 2>&1 \
    | tee "${TEST_LOG}"
test_client_rc=${PIPESTATUS[0]}
set -e
echo "obclient 返回码（包含预期业务错误）：${test_client_rc}"
python3 "${ROOT_DIR}/scripts/check_phase5_trigger_log.py" "${TEST_LOG}" \
    || fail "触发器正常路径或预期失败分类未通过"

p5_residue="$(query_scalar "SELECT
 (SELECT COUNT(*) FROM phone_recharge_db.app_user WHERE login_name LIKE 'p5_user_%')+
 (SELECT COUNT(*) FROM phone_recharge_db.owner WHERE owner_name LIKE 'P5_OWNER_%')+
 (SELECT COUNT(*) FROM phone_recharge_db.mobile_number WHERE phone_number LIKE '1995000%')+
 (SELECT COUNT(*) FROM phone_recharge_db.purchase_order WHERE order_no LIKE 'P5-ORDER-%')+
 (SELECT COUNT(*) FROM phone_recharge_db.order_item oi JOIN phone_recharge_db.purchase_order po ON po.order_id=oi.order_id WHERE po.order_no LIKE 'P5-ORDER-%')+
 (SELECT COUNT(*) FROM phone_recharge_db.recharge_card WHERE card_no LIKE 'P5-CARD-%')+
 (SELECT COUNT(*) FROM phone_recharge_db.recharge_record rr JOIN phone_recharge_db.recharge_card rc ON rc.card_id=rr.card_id WHERE rc.card_no LIKE 'P5-CARD-%');")"
assert_equals "测试回滚后P5残留行数" "0" "${p5_residue}"

after_p4="$(query_scalar "SELECT CONCAT(
 (SELECT COUNT(*) FROM phone_recharge_db.app_user WHERE login_name LIKE 'p4_user_%'),',',
 (SELECT COUNT(*) FROM phone_recharge_db.owner WHERE owner_name LIKE 'P4_OWNER_%'),',',
 (SELECT COUNT(*) FROM phone_recharge_db.mobile_number WHERE phone_number LIKE '1994000%'),',',
 (SELECT COUNT(*) FROM phone_recharge_db.purchase_order WHERE order_no LIKE 'P4-ORDER-%'),',',
 (SELECT COUNT(*) FROM phone_recharge_db.order_item oi JOIN phone_recharge_db.purchase_order po ON po.order_id=oi.order_id WHERE po.order_no LIKE 'P4-ORDER-%'),',',
 (SELECT COUNT(*) FROM phone_recharge_db.recharge_card WHERE card_no LIKE 'P4-CARD-%'),',',
 (SELECT COUNT(*) FROM phone_recharge_db.recharge_record rr JOIN phone_recharge_db.recharge_card rc ON rc.card_id=rr.card_id WHERE rc.card_no LIKE 'P4-CARD-%')); ")"
assert_equals "测试后阶段4基准行数" "${baseline_p4}" "${after_p4}"

FINAL_STATUS="PASS"
echo
echo "========== 阶段 5 汇总 =========="
echo "PASS：2 个视图创建成功，元数据和阶段4查询结果正确"
echo "PASS：2 个触发器创建成功，BEFORE/AFTER INSERT 元数据正确"
echo "PASS：正常充值成功并自动把充值卡改为 USED、记录 used_at"
echo "PASS：金额不符、已使用卡和同一卡重复充值均被正确拒绝"
echo "PASS：P5 测试数据全部回滚，阶段4基准数据未改变"
echo "日志：${LOG_FILE}"
echo "最终状态：${FINAL_STATUS}"
