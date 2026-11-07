#!/usr/bin/env bash
# 阶段 4 一次性 CRUD 实验入口。
# 只处理带 P4/p4/1994000 标记的数据，不执行大数据、索引或并发实验。

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SQL_DIR="${ROOT_DIR}/sql"
RESULT_DIR="${ROOT_DIR}/results/phase4"
TIMESTAMP="$(date '+%Y%m%d_%H%M%S')"
LOG_FILE="${RESULT_DIR}/phase4_crud_${TIMESTAMP}.txt"
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
    echo "阶段 4 已安全停止；不要盲目重复运行。请先根据日志检查当前 P4 数据状态。" >&2
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

for file in 10_phase4_seed.sql 11_phase4_updates.sql 12_phase4_queries.sql \
            13_phase4_deletes.sql 14_phase4_verify.sql; do
    [[ -f "${SQL_DIR}/${file}" ]] || fail "缺少文件：${SQL_DIR}/${file}"
done
command -v obclient >/dev/null 2>&1 || fail "未找到 obclient"

echo "阶段 4 将一次性执行带 P4 标记的 INSERT、UPDATE、SELECT 和 DELETE。"
echo "检测到任何既有 P4 数据时都会拒绝执行；脚本不使用 DROP、TRUNCATE 或关闭外键。"
read -r -s -p "请输入 root@coursework 密码：" coursework_password
printf '\n'
[[ -n "${coursework_password}" ]] || fail "密码不能为空"
if [[ "${coursework_password}" == *"'"* || "${coursework_password}" == *"\\"* ]]; then
    fail "当前临时配置方式不接受单引号或反斜杠密码"
fi

CREDENTIAL_FILE="$(mktemp "${TMPDIR:-/tmp}/phase4-obclient.XXXXXX")"
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

echo "阶段 4 自动化开始：$(date '+%F %T %z')"
echo "日志：${LOG_FILE}"

identity="$(query_scalar "SELECT CONCAT(CURRENT_USER(), '|', VERSION(), '|', @@ob_compatibility_mode);")" \
    || fail "无法连接 root@coursework"
[[ "${identity}" == root@%\|*OceanBase*\|MYSQL ]] || fail "账户、版本或兼容模式错误：${identity}"
echo "PASS：连接验证 ${identity}"

table_count="$(query_scalar "SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA='phone_recharge_db' AND TABLE_TYPE='BASE TABLE';")"
assert_equals "业务表数量" "7" "${table_count}"

# 将各类阶段 4 标记计数相加；任意一类非零都拒绝重复写入。
existing_p4="$(query_scalar "SELECT
 (SELECT COUNT(*) FROM phone_recharge_db.app_user WHERE login_name LIKE 'p4_user_%')+
 (SELECT COUNT(*) FROM phone_recharge_db.owner WHERE owner_name LIKE 'P4_OWNER_%')+
 (SELECT COUNT(*) FROM phone_recharge_db.mobile_number WHERE phone_number LIKE '1994000%')+
 (SELECT COUNT(*) FROM phone_recharge_db.purchase_order WHERE order_no LIKE 'P4-ORDER-%')+
 (SELECT COUNT(*) FROM phone_recharge_db.recharge_card WHERE card_no LIKE 'P4-CARD-%');")"
assert_equals "执行前阶段4标记数据总数" "0" "${existing_p4}"

run_sql_file "插入阶段4数据" "${SQL_DIR}/10_phase4_seed.sql"
seed_counts="$(query_scalar "SELECT CONCAT(
 (SELECT COUNT(*) FROM phone_recharge_db.app_user WHERE login_name LIKE 'p4_user_%'),',',
 (SELECT COUNT(*) FROM phone_recharge_db.owner WHERE owner_name LIKE 'P4_OWNER_%'),',',
 (SELECT COUNT(*) FROM phone_recharge_db.mobile_number WHERE phone_number LIKE '1994000%'),',',
 (SELECT COUNT(*) FROM phone_recharge_db.purchase_order WHERE order_no LIKE 'P4-ORDER-%'),',',
 (SELECT COUNT(*) FROM phone_recharge_db.order_item oi JOIN phone_recharge_db.purchase_order po ON po.order_id=oi.order_id WHERE po.order_no LIKE 'P4-ORDER-%'),',',
 (SELECT COUNT(*) FROM phone_recharge_db.recharge_card WHERE card_no LIKE 'P4-CARD-%'),',',
 (SELECT COUNT(*) FROM phone_recharge_db.recharge_record rr JOIN phone_recharge_db.recharge_card rc ON rc.card_id=rr.card_id WHERE rc.card_no LIKE 'P4-CARD-%')); ")"
assert_equals "初始行数 users,owners,mobiles,orders,items,cards,records" \
    "12,12,13,12,13,13,12" "${seed_counts}"

run_sql_file "逐表更新" "${SQL_DIR}/11_phase4_updates.sql"
updated_count="$(query_scalar "SELECT
 (SELECT COUNT(*) FROM phone_recharge_db.app_user WHERE login_name='p4_user_01' AND display_name='阶段4用户01-已更新')+
 (SELECT COUNT(*) FROM phone_recharge_db.owner WHERE owner_name='P4_OWNER_01' AND contact_info='p4_owner01_updated@example.test')+
 (SELECT COUNT(*) FROM phone_recharge_db.mobile_number WHERE phone_number='19940000001' AND number_status='INACTIVE')+
 (SELECT COUNT(*) FROM phone_recharge_db.purchase_order WHERE order_no='P4-ORDER-01' AND total_amount=90.00)+
 (SELECT COUNT(*) FROM phone_recharge_db.order_item oi JOIN phone_recharge_db.purchase_order po ON po.order_id=oi.order_id WHERE po.order_no='P4-ORDER-01' AND oi.denomination=60.00)+
 (SELECT COUNT(*) FROM phone_recharge_db.recharge_card WHERE card_no='P4-CARD-01' AND face_value=60.00 AND password_hash='p4_card_hash_01_updated')+
 (SELECT COUNT(*) FROM phone_recharge_db.recharge_record rr JOIN phone_recharge_db.recharge_card rc ON rc.card_id=rr.card_id WHERE rc.card_no='P4-CARD-01' AND rr.recharge_amount=60.00);")"
assert_equals "7 张表更新结果命中数" "7" "${updated_count}"

run_sql_file "代表性单表与多表查询" "${SQL_DIR}/12_phase4_queries.sql"
run_sql_file "逐表删除两条数据" "${SQL_DIR}/13_phase4_deletes.sql"

deleted_count="$(query_scalar "SELECT
 (SELECT COUNT(*) FROM phone_recharge_db.app_user WHERE login_name IN ('p4_user_11','p4_user_12'))+
 (SELECT COUNT(*) FROM phone_recharge_db.owner WHERE owner_name IN ('P4_OWNER_11','P4_OWNER_12'))+
 (SELECT COUNT(*) FROM phone_recharge_db.mobile_number WHERE phone_number IN ('19940000011','19940000012'))+
 (SELECT COUNT(*) FROM phone_recharge_db.purchase_order WHERE order_no IN ('P4-ORDER-11','P4-ORDER-12'))+
 (SELECT COUNT(*) FROM phone_recharge_db.order_item oi JOIN phone_recharge_db.purchase_order po ON po.order_id=oi.order_id WHERE po.order_no IN ('P4-ORDER-11','P4-ORDER-12'))+
 (SELECT COUNT(*) FROM phone_recharge_db.recharge_card WHERE card_no IN ('P4-CARD-11','P4-CARD-12'))+
 (SELECT COUNT(*) FROM phone_recharge_db.recharge_record rr JOIN phone_recharge_db.recharge_card rc ON rc.card_id=rr.card_id WHERE rc.card_no IN ('P4-CARD-11','P4-CARD-12'));")"
assert_equals "7 张表删除目标残留数" "0" "${deleted_count}"

run_sql_file "最终只读验证" "${SQL_DIR}/14_phase4_verify.sql"

final_counts="$(query_scalar "SELECT CONCAT(
 (SELECT COUNT(*) FROM phone_recharge_db.app_user WHERE login_name LIKE 'p4_user_%'),',',
 (SELECT COUNT(*) FROM phone_recharge_db.owner WHERE owner_name LIKE 'P4_OWNER_%'),',',
 (SELECT COUNT(*) FROM phone_recharge_db.mobile_number WHERE phone_number LIKE '1994000%'),',',
 (SELECT COUNT(*) FROM phone_recharge_db.purchase_order WHERE order_no LIKE 'P4-ORDER-%'),',',
 (SELECT COUNT(*) FROM phone_recharge_db.order_item oi JOIN phone_recharge_db.purchase_order po ON po.order_id=oi.order_id WHERE po.order_no LIKE 'P4-ORDER-%'),',',
 (SELECT COUNT(*) FROM phone_recharge_db.recharge_card WHERE card_no LIKE 'P4-CARD-%'),',',
 (SELECT COUNT(*) FROM phone_recharge_db.recharge_record rr JOIN phone_recharge_db.recharge_card rc ON rc.card_id=rr.card_id WHERE rc.card_no LIKE 'P4-CARD-%')); ")"
assert_equals "最终行数 users,owners,mobiles,orders,items,cards,records" \
    "10,10,11,10,11,11,10" "${final_counts}"

orphan_count="$(query_scalar "SELECT
 (SELECT COUNT(*) FROM phone_recharge_db.mobile_number mn LEFT JOIN phone_recharge_db.owner o ON o.owner_id=mn.owner_id WHERE o.owner_id IS NULL)+
 (SELECT COUNT(*) FROM phone_recharge_db.purchase_order po LEFT JOIN phone_recharge_db.app_user u ON u.user_id=po.user_id WHERE u.user_id IS NULL)+
 (SELECT COUNT(*) FROM phone_recharge_db.order_item oi LEFT JOIN phone_recharge_db.purchase_order po ON po.order_id=oi.order_id WHERE po.order_id IS NULL)+
 (SELECT COUNT(*) FROM phone_recharge_db.recharge_card rc LEFT JOIN phone_recharge_db.order_item oi ON oi.item_id=rc.item_id WHERE oi.item_id IS NULL)+
 (SELECT COUNT(*) FROM phone_recharge_db.recharge_record rr LEFT JOIN phone_recharge_db.recharge_card rc ON rc.card_id=rr.card_id WHERE rc.card_id IS NULL)+
 (SELECT COUNT(*) FROM phone_recharge_db.recharge_record rr LEFT JOIN phone_recharge_db.mobile_number mn ON mn.mobile_id=rr.mobile_id WHERE mn.mobile_id IS NULL);")"
assert_equals "全库孤儿记录总数" "0" "${orphan_count}"

business_errors="$(query_scalar "SELECT
 (SELECT COUNT(*) FROM phone_recharge_db.recharge_card rc JOIN phone_recharge_db.order_item oi ON oi.item_id=rc.item_id WHERE rc.card_no LIKE 'P4-CARD-%' AND rc.face_value<>oi.denomination)+
 (SELECT COUNT(*) FROM phone_recharge_db.recharge_record rr JOIN phone_recharge_db.recharge_card rc ON rc.card_id=rr.card_id WHERE rc.card_no LIKE 'P4-CARD-%' AND rr.recharge_amount<>rc.face_value)+
 (SELECT COUNT(*) FROM phone_recharge_db.purchase_order po JOIN (SELECT order_id,SUM(denomination*quantity) amount FROM phone_recharge_db.order_item GROUP BY order_id) x ON x.order_id=po.order_id WHERE po.order_no LIKE 'P4-ORDER-%' AND po.total_amount<>x.amount)+
 (SELECT COUNT(*) FROM phone_recharge_db.recharge_card rc LEFT JOIN phone_recharge_db.recharge_record rr ON rr.card_id=rc.card_id WHERE rc.card_no LIKE 'P4-CARD-%' AND ((rc.card_status='USED' AND rr.recharge_id IS NULL) OR (rc.card_status='UNUSED' AND rr.recharge_id IS NOT NULL)))+
 (SELECT COUNT(*) FROM (SELECT card_id,COUNT(*) c FROM phone_recharge_db.recharge_record GROUP BY card_id HAVING COUNT(*)>1) d);")"
assert_equals "金额、状态及一卡一记录异常总数" "0" "${business_errors}"

relationship_counts="$(query_scalar "SELECT CONCAT(
 (SELECT COUNT(*) FROM phone_recharge_db.mobile_number mn JOIN phone_recharge_db.owner o ON o.owner_id=mn.owner_id WHERE o.owner_name='P4_OWNER_01'),',',
 (SELECT COUNT(*) FROM phone_recharge_db.order_item oi JOIN phone_recharge_db.purchase_order po ON po.order_id=oi.order_id WHERE po.order_no='P4-ORDER-01'));")"
assert_equals "一对多示例 owner01号码数,order01明细数" "2,2" "${relationship_counts}"

FINAL_STATUS="PASS"
echo
echo "========== 阶段 4 汇总 =========="
echo "PASS：7 张表初始插入均不少于 12 条阶段4数据"
echo "PASS：7 张表 UPDATE 均验证成功"
echo "PASS：7 张表各 DELETE 2 条，最终各保留不少于 10 条"
echo "PASS：单表查询与多表 JOIN 查询完成"
echo "PASS：无孤儿记录，金额、状态和一卡一记录规则一致"
echo "PASS：Owner 1:N MobileNumber 与 Order 1:N OrderItem 示例成立"
echo "日志：${LOG_FILE}"
echo "最终状态：${FINAL_STATUS}"
