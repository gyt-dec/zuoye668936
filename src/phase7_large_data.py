#!/usr/bin/env python3
"""阶段7：可恢复的10万级关联数据批量生成。"""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import time
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

from src.db import connect
from src.db_config import load_database_config
from src.services.integrity_service import EXPECTED_P4, p4_counts, p5_object_counts, p6_residue_count, scalar, table_count

BATCH_SIZE = 500
PILOT_ORDERS = 1_000
FULL_ORDERS = 100_000
DOUBLE_CARD_ORDERS = 20_000
FULL_CARDS = 120_000
DENOMINATIONS = (Decimal("10.00"), Decimal("20.00"), Decimal("30.00"), Decimal("50.00"), Decimal("100.00"))
P7_HASH = "p7$synthetic$pbkdf2-sha256$not-a-real-credential"
DATA_RESERVE = 2 * 1024**3
LOG_RESERVE = 1024**3
BATCH_COUNTER = 0
ESTIMATE_REQUIRED_FIELDS = {
    "pilot_groups", "pilot_growth", "pilot_filesystem_growth",
    "per_group_data", "per_group_filesystem", "estimated_remaining",
    "estimated_remaining_filesystem", "data_safety", "filesystem_safety",
    "log_safety",
}


def batch_ranges(start: int, stop: int, size: int = BATCH_SIZE):
    if size <= 0:
        raise ValueError("批次大小必须大于0")
    current = start
    while current <= stop:
        end = min(current + size - 1, stop)
        yield current, end
        current = end + 1


def quantity_for_order(seq: int) -> int:
    return 2 if seq <= DOUBLE_CARD_ORDERS else 1


def denomination_for_order(seq: int) -> Decimal:
    return DENOMINATIONS[(seq - 1) % len(DENOMINATIONS)]


def card_range_for_order(seq: int) -> tuple[int, int]:
    if seq <= DOUBLE_CARD_ORDERS:
        return 2 * seq - 1, 2 * seq
    card_seq = seq + DOUBLE_CARD_ORDERS
    return card_seq, card_seq


def order_for_card(card_seq: int) -> int:
    if card_seq <= DOUBLE_CARD_ORDERS * 2:
        return (card_seq + 1) // 2
    return card_seq - DOUBLE_CARD_ORDERS


def expected_card_count(order_count: int) -> int:
    return order_count + min(order_count, DOUBLE_CARD_ORDERS)


def validate_prefix_stats(label: str, count: int, minimum: int | None, maximum: int | None, distinct: int, target: int) -> int:
    if count == 0:
        return 0
    if count > target or minimum != 1 or maximum != count or distinct != count:
        raise RuntimeError(f"{label}不是从1开始的完整唯一前缀：count={count},min={minimum},max={maximum},distinct={distinct}")
    return count


def deterministic_time(seq: int) -> datetime:
    return datetime(2026, 6, 1) + timedelta(seconds=seq * 37)


def user_row(seq: int):
    return (f"p7_user_{seq:08d}", P7_HASH, deterministic_time(seq), "ACTIVE", f"P7用户{seq:08d}")


def owner_row(seq: int):
    return (f"P7_OWNER_{seq:08d}", f"p7_owner_{seq:08d}@example.test")


def phone_for_seq(seq: int) -> str:
    return f"1987{seq:08d}"


def marker_counts(connection) -> dict[str, int]:
    queries = {
        "app_user": "SELECT COUNT(*) value FROM app_user WHERE LEFT(login_name,8)=%s",
        "owner": "SELECT COUNT(*) value FROM owner WHERE LEFT(owner_name,9)=%s",
        "mobile_number": "SELECT COUNT(*) value FROM mobile_number mn JOIN owner o ON o.owner_id=mn.owner_id WHERE LEFT(o.owner_name,9)=%s",
        "purchase_order": "SELECT COUNT(*) value FROM purchase_order WHERE LEFT(order_no,9)=%s",
        "order_item": "SELECT COUNT(*) value FROM order_item oi JOIN purchase_order po ON po.order_id=oi.order_id WHERE LEFT(po.order_no,9)=%s",
        "recharge_card": "SELECT COUNT(*) value FROM recharge_card WHERE LEFT(card_no,8)=%s",
        "recharge_record": "SELECT COUNT(*) value FROM recharge_record rr JOIN recharge_card rc ON rc.card_id=rr.card_id WHERE LEFT(rc.card_no,8)=%s",
    }
    patterns = {"app_user": "p7_user_", "owner": "P7_OWNER_", "mobile_number": "P7_OWNER_", "purchase_order": "P7-ORDER-", "order_item": "P7-ORDER-", "recharge_card": "P7-CARD-", "recharge_record": "P7-CARD-"}
    return {name: int(scalar(connection, sql, (patterns[name],))) for name, sql in queries.items()}


def prefix_stat(connection, table: str) -> tuple[int, int | None, int | None, int]:
    definitions = {
        "app_user": ("app_user", "login_name", "p7_user_", 9),
        "owner": ("owner", "owner_name", "P7_OWNER_", 10),
        "purchase_order": ("purchase_order", "order_no", "P7-ORDER-", 10),
        "recharge_card": ("recharge_card", "card_no", "P7-CARD-", 9),
    }
    if table == "mobile_number":
        sql, pattern = "SELECT COUNT(*) c,MIN(CAST(SUBSTRING(o.owner_name,10) AS UNSIGNED)) mn,MAX(CAST(SUBSTRING(o.owner_name,10) AS UNSIGNED)) mx,COUNT(DISTINCT o.owner_name) d FROM mobile_number mn JOIN owner o ON o.owner_id=mn.owner_id WHERE LEFT(o.owner_name,9)=%s", "P7_OWNER_"
    elif table == "order_item":
        sql, pattern = "SELECT COUNT(*) c,MIN(CAST(SUBSTRING(po.order_no,10) AS UNSIGNED)) mn,MAX(CAST(SUBSTRING(po.order_no,10) AS UNSIGNED)) mx,COUNT(DISTINCT po.order_no) d FROM order_item oi JOIN purchase_order po ON po.order_id=oi.order_id WHERE LEFT(po.order_no,9)=%s", "P7-ORDER-"
    elif table == "recharge_record":
        sql, pattern = "SELECT COUNT(*) c,MIN(CAST(SUBSTRING(rc.card_no,9) AS UNSIGNED)) mn,MAX(CAST(SUBSTRING(rc.card_no,9) AS UNSIGNED)) mx,COUNT(DISTINCT rc.card_no) d FROM recharge_record rr JOIN recharge_card rc ON rc.card_id=rr.card_id WHERE LEFT(rc.card_no,8)=%s", "P7-CARD-"
    else:
        source, column, pattern, start = definitions[table]
        sql = f"SELECT COUNT(*) c, MIN(CAST(SUBSTRING({column},{start}) AS UNSIGNED)) mn, MAX(CAST(SUBSTRING({column},{start}) AS UNSIGNED)) mx, COUNT(DISTINCT {column}) d FROM {source} WHERE LEFT({column},{start-1})=%s"
    with connection.cursor() as cursor:
        cursor.execute(sql, (pattern,))
        row = cursor.fetchone()
    return int(row["c"]), row["mn"], row["mx"], int(row["d"])


def fetch_ids(connection, table: str, key_column: str, id_column: str, keys: list[str]) -> dict[str, int]:
    placeholders = ",".join(["%s"] * len(keys))
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT {id_column}, {key_column} FROM {table} WHERE {key_column} IN ({placeholders})", tuple(keys))
        rows = cursor.fetchall()
    result = {str(row[key_column]): int(row[id_column]) for row in rows}
    if len(result) != len(keys):
        raise RuntimeError(f"{table}父键映射不完整：expected={len(keys)},actual={len(result)}")
    return result


def execute_batch(connection, label: str, sql: str, rows: list[tuple]) -> None:
    global BATCH_COUNTER
    started = time.perf_counter()
    try:
        connection.begin()
        with connection.cursor() as cursor:
            cursor.executemany(sql, rows)
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    print(f"BATCH|{label}|rows={len(rows)}|seconds={time.perf_counter()-started:.6f}")
    BATCH_COUNTER += 1
    if BATCH_COUNTER % 20 == 0:
        resource_snapshot(connection)


def insert_simple(connection, label: str, current: int, target: int, sql: str, row_factory) -> None:
    for start, end in batch_ranges(current + 1, target):
        execute_batch(connection, label, sql, [row_factory(seq) for seq in range(start, end + 1)])


def insert_to_target(connection, order_target: int) -> None:
    counts = marker_counts(connection)
    insert_simple(connection, "app_user", counts["app_user"], order_target,
        "INSERT INTO app_user(login_name,password_hash,registered_at,user_status,display_name) VALUES(%s,%s,%s,%s,%s)", user_row)
    insert_simple(connection, "owner", counts["owner"], order_target,
        "INSERT INTO owner(owner_name,contact_info) VALUES(%s,%s)", owner_row)

    for start, end in batch_ranges(counts["mobile_number"] + 1, order_target):
        keys = [f"P7_OWNER_{seq:08d}" for seq in range(start, end + 1)]
        parents = fetch_ids(connection, "owner", "owner_name", "owner_id", keys)
        rows = [(parents[f"P7_OWNER_{seq:08d}"], phone_for_seq(seq), "ACTIVE", deterministic_time(seq)) for seq in range(start, end + 1)]
        execute_batch(connection, "mobile_number", "INSERT INTO mobile_number(owner_id,phone_number,number_status,registered_at) VALUES(%s,%s,%s,%s)", rows)

    for start, end in batch_ranges(counts["purchase_order"] + 1, order_target):
        keys = [f"p7_user_{seq:08d}" for seq in range(start, end + 1)]
        parents = fetch_ids(connection, "app_user", "login_name", "user_id", keys)
        rows = []
        for seq in range(start, end + 1):
            denomination = denomination_for_order(seq)
            rows.append((parents[f"p7_user_{seq:08d}"], f"P7-ORDER-{seq:08d}", deterministic_time(seq), "COMPLETED", denomination * quantity_for_order(seq), deterministic_time(seq)))
        execute_batch(connection, "purchase_order", "INSERT INTO purchase_order(user_id,order_no,created_at,order_status,total_amount,completed_at) VALUES(%s,%s,%s,%s,%s,%s)", rows)

    for start, end in batch_ranges(counts["order_item"] + 1, order_target):
        keys = [f"P7-ORDER-{seq:08d}" for seq in range(start, end + 1)]
        parents = fetch_ids(connection, "purchase_order", "order_no", "order_id", keys)
        rows = [(parents[f"P7-ORDER-{seq:08d}"], denomination_for_order(seq), quantity_for_order(seq)) for seq in range(start, end + 1)]
        execute_batch(connection, "order_item", "INSERT INTO order_item(order_id,denomination,quantity) VALUES(%s,%s,%s)", rows)

    card_target = expected_card_count(order_target)
    for start, end in batch_ranges(counts["recharge_card"] + 1, card_target):
        order_seqs = sorted({order_for_card(seq) for seq in range(start, end + 1)})
        order_keys = [f"P7-ORDER-{seq:08d}" for seq in order_seqs]
        placeholders = ",".join(["%s"] * len(order_keys))
        with connection.cursor() as cursor:
            cursor.execute(f"SELECT oi.item_id,po.order_no FROM order_item oi JOIN purchase_order po ON po.order_id=oi.order_id WHERE po.order_no IN ({placeholders})", tuple(order_keys))
            items = {row["order_no"]: int(row["item_id"]) for row in cursor.fetchall()}
        if len(items) != len(order_keys):
            raise RuntimeError("充值卡批次的订单明细映射不完整")
        rows = []
        for card_seq in range(start, end + 1):
            order_seq = order_for_card(card_seq)
            rows.append((items[f"P7-ORDER-{order_seq:08d}"], f"P7-CARD-{card_seq:08d}", P7_HASH, denomination_for_order(order_seq), "UNUSED", deterministic_time(card_seq), None))
        execute_batch(connection, "recharge_card", "INSERT INTO recharge_card(item_id,card_no,password_hash,face_value,card_status,created_at,used_at) VALUES(%s,%s,%s,%s,%s,%s,%s)", rows)

    for start, end in batch_ranges(counts["recharge_record"] + 1, order_target):
        card_keys = [f"P7-CARD-{seq:08d}" for seq in range(start, end + 1)]
        phone_keys = [phone_for_seq(seq) for seq in range(start, end + 1)]
        cards = fetch_ids(connection, "recharge_card", "card_no", "card_id", card_keys)
        mobiles = fetch_ids(connection, "mobile_number", "phone_number", "mobile_id", phone_keys)
        rows = []
        for seq in range(start, end + 1):
            order_seq = order_for_card(seq)
            rows.append((cards[f"P7-CARD-{seq:08d}"], mobiles[phone_for_seq(seq)], denomination_for_order(order_seq), deterministic_time(seq)))
        execute_batch(connection, "recharge_record", "INSERT INTO recharge_record(card_id,mobile_id,recharge_amount,recharged_at) VALUES(%s,%s,%s,%s)", rows)


def relationship_anomalies(connection) -> dict[str, int]:
    queries = {
        "mobile_parent": "SELECT COUNT(*) value FROM mobile_number mn JOIN owner o ON o.owner_id=mn.owner_id WHERE LEFT(mn.phone_number,4)=%s AND LEFT(o.owner_name,9)<>%s",
        "mobile_sequence": "SELECT COUNT(*) value FROM mobile_number mn JOIN owner o ON o.owner_id=mn.owner_id WHERE LEFT(o.owner_name,9)=%s AND CAST(SUBSTRING(o.owner_name,10) AS UNSIGNED)<>CAST(SUBSTRING(mn.phone_number,5) AS UNSIGNED)",
        "order_parent": "SELECT COUNT(*) value FROM purchase_order po JOIN app_user u ON u.user_id=po.user_id WHERE LEFT(po.order_no,9)=%s AND LEFT(u.login_name,8)<>%s",
        "order_sequence": "SELECT COUNT(*) value FROM purchase_order po JOIN app_user u ON u.user_id=po.user_id WHERE LEFT(po.order_no,9)=%s AND CAST(SUBSTRING(po.order_no,10) AS UNSIGNED)<>CAST(SUBSTRING(u.login_name,9) AS UNSIGNED)",
        "one_item": "SELECT COUNT(*) value FROM (SELECT po.order_id FROM purchase_order po LEFT JOIN order_item oi ON oi.order_id=po.order_id WHERE LEFT(po.order_no,9)=%s GROUP BY po.order_id HAVING COUNT(oi.item_id)<>1) x",
        "card_quantity": "SELECT COUNT(*) value FROM (SELECT oi.item_id,oi.quantity,COUNT(rc.card_id) c FROM order_item oi JOIN purchase_order po ON po.order_id=oi.order_id LEFT JOIN recharge_card rc ON rc.item_id=oi.item_id WHERE LEFT(po.order_no,9)=%s GROUP BY oi.item_id,oi.quantity HAVING c<>oi.quantity) x",
        "order_amount": "SELECT COUNT(*) value FROM purchase_order po JOIN order_item oi ON oi.order_id=po.order_id WHERE LEFT(po.order_no,9)=%s AND (po.total_amount<>oi.denomination*oi.quantity)",
        "card_amount": "SELECT COUNT(*) value FROM recharge_card rc JOIN order_item oi ON oi.item_id=rc.item_id WHERE LEFT(rc.card_no,8)=%s AND rc.face_value<>oi.denomination",
        "card_sequence": "SELECT COUNT(*) value FROM recharge_card rc JOIN order_item oi ON oi.item_id=rc.item_id JOIN purchase_order po ON po.order_id=oi.order_id WHERE LEFT(rc.card_no,8)=%s AND CAST(SUBSTRING(po.order_no,10) AS UNSIGNED)<>CASE WHEN CAST(SUBSTRING(rc.card_no,9) AS UNSIGNED)<=40000 THEN (CAST(SUBSTRING(rc.card_no,9) AS UNSIGNED)+1) DIV 2 ELSE CAST(SUBSTRING(rc.card_no,9) AS UNSIGNED)-20000 END",
        "record_relation": "SELECT COUNT(*) value FROM recharge_record rr JOIN recharge_card rc ON rc.card_id=rr.card_id JOIN mobile_number mn ON mn.mobile_id=rr.mobile_id WHERE LEFT(rc.card_no,8)=%s AND (LEFT(mn.phone_number,4)<>%s OR rr.recharge_amount<>rc.face_value)",
        "record_sequence": "SELECT COUNT(*) value FROM recharge_record rr JOIN recharge_card rc ON rc.card_id=rr.card_id JOIN mobile_number mn ON mn.mobile_id=rr.mobile_id WHERE LEFT(rc.card_no,8)=%s AND CAST(SUBSTRING(rc.card_no,9) AS UNSIGNED)<>CAST(SUBSTRING(mn.phone_number,5) AS UNSIGNED)",
        "used_state": "SELECT COUNT(*) value FROM recharge_card rc LEFT JOIN recharge_record rr ON rr.card_id=rc.card_id WHERE LEFT(rc.card_no,8)=%s AND ((rr.recharge_id IS NOT NULL AND (rc.card_status<>'USED' OR rc.used_at IS NULL OR rc.used_at<>rr.recharged_at)) OR (rr.recharge_id IS NULL AND (rc.card_status<>'UNUSED' OR rc.used_at IS NOT NULL)))",
        "duplicate_record": "SELECT COUNT(*) value FROM (SELECT rr.card_id FROM recharge_record rr JOIN recharge_card rc ON rc.card_id=rr.card_id WHERE LEFT(rc.card_no,8)=%s GROUP BY rr.card_id HAVING COUNT(*)<>1) x",
    }
    params = {
        "mobile_parent": ("1987", "P7_OWNER_"), "mobile_sequence": ("P7_OWNER_",),
        "order_parent": ("P7-ORDER-", "p7_user_"), "order_sequence": ("P7-ORDER-",),
        "one_item": ("P7-ORDER-",), "card_quantity": ("P7-ORDER-",), "order_amount": ("P7-ORDER-",),
        "card_amount": ("P7-CARD-",), "card_sequence": ("P7-CARD-",),
        "record_relation": ("P7-CARD-", "1987"), "record_sequence": ("P7-CARD-",),
        "used_state": ("P7-CARD-",), "duplicate_record": ("P7-CARD-",),
    }
    return {name: int(scalar(connection, sql, params[name])) for name, sql in queries.items()}


def require_no_anomalies(label: str, anomalies: dict[str, int]) -> None:
    if any(anomalies.values()):
        raise RuntimeError(f"{label}：{anomalies}")


def reference_anomalies(connection) -> dict[str, int]:
    """恢复和清理前只检查已经存在的子记录是否引用P7父记录。"""
    queries = {
        "mobile_to_non_p7_owner": ("SELECT COUNT(*) value FROM mobile_number mn JOIN owner o ON o.owner_id=mn.owner_id WHERE LEFT(mn.phone_number,4)=%s AND LEFT(o.owner_name,9)<>%s", ("1987", "P7_OWNER_")),
        "order_to_non_p7_user": ("SELECT COUNT(*) value FROM purchase_order po JOIN app_user u ON u.user_id=po.user_id WHERE LEFT(po.order_no,9)=%s AND LEFT(u.login_name,8)<>%s", ("P7-ORDER-", "p7_user_")),
        "item_to_non_p7_order": ("SELECT COUNT(*) value FROM order_item oi JOIN purchase_order po ON po.order_id=oi.order_id WHERE oi.item_id IN (SELECT rc.item_id FROM recharge_card rc WHERE LEFT(rc.card_no,8)=%s) AND LEFT(po.order_no,9)<>%s", ("P7-CARD-", "P7-ORDER-")),
        "card_to_non_p7_order": ("SELECT COUNT(*) value FROM recharge_card rc JOIN order_item oi ON oi.item_id=rc.item_id JOIN purchase_order po ON po.order_id=oi.order_id WHERE LEFT(rc.card_no,8)=%s AND LEFT(po.order_no,9)<>%s", ("P7-CARD-", "P7-ORDER-")),
        "record_to_non_p7_mobile": ("SELECT COUNT(*) value FROM recharge_record rr JOIN recharge_card rc ON rc.card_id=rr.card_id JOIN mobile_number mn ON mn.mobile_id=rr.mobile_id WHERE LEFT(rc.card_no,8)=%s AND LEFT(mn.phone_number,4)<>%s", ("P7-CARD-", "1987")),
    }
    return {name: int(scalar(connection, sql, params)) for name, (sql, params) in queries.items()}


def recovery_business_anomalies(connection) -> dict[str, int]:
    anomalies = relationship_anomalies(connection)
    anomalies.pop("one_item", None)
    anomalies.pop("card_quantity", None)
    return anomalies


def expected_item_values(order_seq: int) -> tuple[Decimal, int]:
    return denomination_for_order(order_seq), quantity_for_order(order_seq)


def cleanup_item_is_expected(order_seq: int, denomination: Decimal, quantity: int, item_count: int = 1) -> bool:
    expected_denomination, expected_quantity = expected_item_values(order_seq)
    return item_count == 1 and Decimal(denomination) == expected_denomination and quantity == expected_quantity


def cleanup_record_is_expected(card_seq: int, phone_number: str | None, amount: Decimal | None, recharged_at: datetime | None, face_value: Decimal, card_status: str, used_at: datetime | None, record_count: int) -> bool:
    if card_seq > FULL_ORDERS:
        return record_count == 0 and card_status == "UNUSED" and used_at is None
    expected_time = deterministic_time(card_seq)
    return (record_count == 1 and phone_number == phone_for_seq(card_seq)
            and Decimal(amount) == Decimal(face_value) and recharged_at == expected_time
            and card_status == "USED" and used_at == expected_time)


def cleanup_inbound_anomalies(connection) -> dict[str, int]:
    queries = {
        "non_p7_mobile_to_p7_owner": ("SELECT COUNT(*) value FROM mobile_number mn JOIN owner o ON o.owner_id=mn.owner_id WHERE LEFT(o.owner_name,9)=%s AND LEFT(mn.phone_number,4)<>%s", ("P7_OWNER_", "1987")),
        "non_p7_order_to_p7_user": ("SELECT COUNT(*) value FROM purchase_order po JOIN app_user u ON u.user_id=po.user_id WHERE LEFT(u.login_name,8)=%s AND LEFT(po.order_no,9)<>%s", ("p7_user_", "P7-ORDER-")),
        "non_p7_item_to_p7_order": ("SELECT COUNT(*) value FROM (SELECT po.order_id,CAST(SUBSTRING(po.order_no,10) AS UNSIGNED) seq,COUNT(oi.item_id) item_count,SUM(CASE WHEN oi.denomination=CASE MOD(CAST(SUBSTRING(po.order_no,10) AS UNSIGNED)-1,5) WHEN 0 THEN 10.00 WHEN 1 THEN 20.00 WHEN 2 THEN 30.00 WHEN 3 THEN 50.00 ELSE 100.00 END AND oi.quantity=CASE WHEN CAST(SUBSTRING(po.order_no,10) AS UNSIGNED)<=20000 THEN 2 ELSE 1 END THEN 1 ELSE 0 END) expected_count FROM purchase_order po LEFT JOIN order_item oi ON oi.order_id=po.order_id WHERE LEFT(po.order_no,9)=%s GROUP BY po.order_id,seq HAVING item_count<>1 OR expected_count<>1) x", ("P7-ORDER-",)),
        "non_p7_card_to_p7_item": ("SELECT COUNT(*) value FROM recharge_card rc JOIN order_item oi ON oi.item_id=rc.item_id JOIN purchase_order po ON po.order_id=oi.order_id WHERE LEFT(po.order_no,9)=%s AND LEFT(rc.card_no,8)<>%s", ("P7-ORDER-", "P7-CARD-")),
        "non_p7_record_to_p7_card": ("SELECT COUNT(*) value FROM (SELECT rc.card_id,CAST(SUBSTRING(rc.card_no,9) AS UNSIGNED) seq,rc.face_value,rc.card_status,rc.used_at,COUNT(rr.recharge_id) record_count,SUM(CASE WHEN CAST(SUBSTRING(mn.phone_number,5) AS UNSIGNED)=CAST(SUBSTRING(rc.card_no,9) AS UNSIGNED) AND rr.recharge_amount=rc.face_value AND rr.recharged_at=TIMESTAMPADD(SECOND,CAST(SUBSTRING(rc.card_no,9) AS UNSIGNED)*37,CAST('2026-06-01 00:00:00.000000' AS DATETIME(6))) AND rc.card_status='USED' AND rc.used_at=rr.recharged_at THEN 1 ELSE 0 END) expected_count FROM recharge_card rc LEFT JOIN recharge_record rr ON rr.card_id=rc.card_id LEFT JOIN mobile_number mn ON mn.mobile_id=rr.mobile_id WHERE LEFT(rc.card_no,8)=%s GROUP BY rc.card_id,seq,rc.face_value,rc.card_status,rc.used_at HAVING (seq<=100000 AND (record_count<>1 OR expected_count<>1)) OR (seq>100000 AND (record_count<>0 OR rc.card_status<>'UNUSED' OR rc.used_at IS NOT NULL))) x", ("P7-CARD-",)),
        "non_p7_record_to_p7_mobile": ("SELECT COUNT(*) value FROM recharge_record rr JOIN mobile_number mn ON mn.mobile_id=rr.mobile_id JOIN owner o ON o.owner_id=mn.owner_id JOIN recharge_card rc ON rc.card_id=rr.card_id WHERE LEFT(o.owner_name,9)=%s AND LEFT(rc.card_no,8)<>%s", ("P7_OWNER_", "P7-CARD-")),
    }
    return {name: int(scalar(connection, sql, params)) for name, (sql, params) in queries.items()}


def validate_dataset(connection, order_target: int) -> None:
    counts = marker_counts(connection)
    expected = {"app_user": order_target, "owner": order_target, "mobile_number": order_target, "purchase_order": order_target, "order_item": order_target, "recharge_card": expected_card_count(order_target), "recharge_record": order_target}
    if counts != expected:
        raise RuntimeError(f"P7数量不符合目标：actual={counts},expected={expected}")
    require_no_anomalies("P7父子关系或金额状态异常", relationship_anomalies(connection))
    used = int(scalar(connection, "SELECT COUNT(*) value FROM recharge_card WHERE LEFT(card_no,8)=%s AND card_status='USED'", ("P7-CARD-",)))
    unused = int(scalar(connection, "SELECT COUNT(*) value FROM recharge_card WHERE LEFT(card_no,8)=%s AND card_status='UNUSED'", ("P7-CARD-",)))
    if used != order_target or unused != expected_card_count(order_target) - order_target:
        raise RuntimeError(f"P7卡状态数量错误：used={used},unused={unused}")
    print(f"PASS|P7数据校验|counts={counts}|used={used}|unused={unused}")


def validate_prefixes(connection, order_target: int) -> None:
    for table, target in (("app_user", order_target), ("owner", order_target), ("mobile_number", order_target), ("purchase_order", order_target), ("order_item", order_target), ("recharge_card", expected_card_count(order_target)), ("recharge_record", order_target)):
        validate_prefix_stats(table, *prefix_stat(connection, table), target)
    counts = marker_counts(connection)
    if counts["mobile_number"] > counts["owner"] or counts["purchase_order"] > counts["app_user"] or counts["order_item"] > counts["purchase_order"] or counts["recharge_record"] > counts["recharge_card"]:
        raise RuntimeError(f"P7子表记录超前：{counts}")
    require_no_anomalies("P7恢复检查发现父子或业务关系异常", recovery_business_anomalies(connection))


def parse_obd_storage_paths(config_text: str) -> tuple[Path, Path]:
    home_paths: set[str] = set()
    oceanbase_component_count = 0
    in_oceanbase_component = False
    for raw_line in config_text.splitlines():
        if raw_line and not raw_line[0].isspace():
            header = raw_line.split("#", 1)[0].strip()
            if header.endswith(":"):
                component = header[:-1].strip().strip("'\"")
                in_oceanbase_component = component == "oceanbase-ce"
                if in_oceanbase_component:
                    oceanbase_component_count += 1
                continue
        if not in_oceanbase_component:
            continue
        line = raw_line.strip()
        if line.startswith("home_path:"):
            value = line.split(":", 1)[1].split(" #", 1)[0].strip().strip("'\"")
            if value:
                home_paths.add(value)
    if oceanbase_component_count != 1 or len(home_paths) != 1:
        raise RuntimeError(
            f"OBD配置未提供唯一oceanbase-ce组件及home_path："
            f"components={oceanbase_component_count},home_paths={home_paths}"
        )
    home_path = Path(next(iter(home_paths))).expanduser()
    if not home_path.is_absolute() or not home_path.is_dir():
        raise RuntimeError(f"OBD配置中的home_path不是实际存在的绝对目录：{home_path}")
    data_path, log_path = home_path / "store", home_path / "store" / "clog"
    if not data_path.is_dir() or not log_path.is_dir():
        raise RuntimeError(f"OceanBase实际store/clog目录不存在：data={data_path},log={log_path}")
    return data_path.resolve(), log_path.resolve()


def local_obd_resource_snapshot() -> dict[str, object]:
    cluster = os.environ.get("OBD_CLUSTER_NAME", "demo")
    config_path = Path(os.environ.get(
        "OBD_CONFIG_FILE", str(Path.home() / ".obd" / "cluster" / cluster / "config.yaml")
    )).expanduser()
    try:
        config_text = config_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(f"读取OBD配置失败：path={config_path}；{exc.__class__.__name__}: {exc}") from exc
    data_path, log_path = parse_obd_storage_paths(config_text)
    data_usage, log_usage = shutil.disk_usage(data_path), shutil.disk_usage(log_path)
    same_filesystem = data_path.stat().st_dev == log_path.stat().st_dev
    return {
        "source": f"obd_config:{config_path}", "data_path": str(data_path),
        "log_path": str(log_path), "data_capacity": int(data_usage.total),
        "data_used": int(data_usage.used), "log_capacity": int(log_usage.total),
        "log_used": int(log_usage.used), "data_filesystem_free": int(data_usage.free),
        "log_filesystem_free": int(log_usage.free), "same_filesystem": same_filesystem,
    }


def resource_snapshot(connection, *, enforce_data: bool = True) -> dict[str, object]:
    database_error: Exception | None = None
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM oceanbase.GV$OB_SERVERS")
            row = cursor.fetchone()
    except Exception as exc:
        database_error = exc
        row = None
    if not row:
        try:
            result = local_obd_resource_snapshot()
        except Exception as obd_error:
            db_detail = (f"{database_error.__class__.__name__}: {database_error}"
                         if database_error else "GV$OB_SERVERS未返回资源数据")
            raise RuntimeError(
                f"资源检查失败；数据库底层错误=[{db_detail}]；"
                f"OBD底层错误=[{obd_error.__class__.__name__}: {obd_error}]"
            ) from obd_error
        return validate_resource_limits(result, enforce_data=enforce_data)
    def pick(*names):
        for name in names:
            if name in row and row[name] is not None:
                return int(row[name])
        raise RuntimeError(f"OceanBase资源视图缺少字段：{names}")
    def pick_path(name):
        value = row.get(name)
        if not value or not Path(str(value)).exists():
            raise RuntimeError(f"无法确认OceanBase实际存储挂载点：{name}={value}")
        return str(value)
    data_path, log_path = pick_path("DATA_DISK_PATH"), pick_path("LOG_DISK_PATH")
    result: dict[str, object] = {
        "source": "GV$OB_SERVERS",
        "data_capacity": pick("DATA_DISK_CAPACITY"),
        "data_used": pick("DATA_DISK_IN_USE"),
        "log_capacity": pick("LOG_DISK_CAPACITY"),
        "log_used": pick("LOG_DISK_IN_USE"),
        "data_filesystem_free": int(shutil.disk_usage(data_path).free),
        "log_filesystem_free": int(shutil.disk_usage(log_path).free),
        "same_filesystem": Path(data_path).stat().st_dev == Path(log_path).stat().st_dev,
    }
    return validate_resource_limits(result, enforce_data=enforce_data)


def validate_resource_limits(result: dict[str, object], *, enforce_data: bool = True) -> dict[str, object]:
    if int(result["log_capacity"]) - int(result["log_used"]) < LOG_RESERVE:
        raise RuntimeError(f"OceanBase日志盘安全余量不足：{result}")
    filesystem_reserve = DATA_RESERVE + LOG_RESERVE if result.get("same_filesystem") else DATA_RESERVE
    if enforce_data and (int(result["data_capacity"]) - int(result["data_used"]) < DATA_RESERVE or int(result["data_filesystem_free"]) < filesystem_reserve):
        raise RuntimeError(f"OceanBase数据盘或日志盘余量不足：{result}")
    print(f"RESOURCE|{result}")
    return result


def estimate_full_space(before: dict[str, int], after: dict[str, int]) -> dict[str, int]:
    growth = after["data_used"] - before["data_used"]
    fs_growth = before["data_filesystem_free"] - after["data_filesystem_free"]
    if growth <= 0 or fs_growth < 0:
        raise RuntimeError("无法根据1000组预实验估算空间")
    remaining = FULL_ORDERS - PILOT_ORDERS
    estimated = math.ceil(growth * remaining / PILOT_ORDERS * 1.5)
    estimated_fs = math.ceil(max(growth, fs_growth) * remaining / PILOT_ORDERS * 1.5)
    data_free = after["data_capacity"] - after["data_used"]
    log_free = after["log_capacity"] - after["log_used"]
    filesystem_reserve = DATA_RESERVE + LOG_RESERVE if after.get("same_filesystem") else DATA_RESERVE
    if data_free - estimated < DATA_RESERVE or after["data_filesystem_free"] - estimated_fs < filesystem_reserve or log_free < LOG_RESERVE:
        raise RuntimeError("预实验估算显示完整数据空间不足")
    result = {"pilot_groups": PILOT_ORDERS, "pilot_growth": growth, "pilot_filesystem_growth": fs_growth, "per_group_data": growth/PILOT_ORDERS, "per_group_filesystem": max(growth,fs_growth)/PILOT_ORDERS, "estimated_remaining": estimated, "estimated_remaining_filesystem": estimated_fs, "data_safety": data_free-estimated, "filesystem_safety": after["data_filesystem_free"]-estimated_fs, "log_safety": log_free}
    print(f"SPACE_ESTIMATE|{result}")
    estimate_file = os.environ.get("P7_ESTIMATE_FILE")
    if estimate_file:
        Path(estimate_file).write_text(json.dumps(result), encoding="utf-8")
    return result


def validate_saved_estimate(snapshot: dict[str, int], committed_groups: int) -> None:
    path = Path(os.environ.get("P7_ESTIMATE_FILE", ""))
    if not path.is_file():
        raise RuntimeError("恢复完整插入时缺少1000组空间估算文件，停止续跑")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not ESTIMATE_REQUIRED_FIELDS.issubset(data):
            raise ValueError("必要字段不完整")
        pilot_groups = data["pilot_groups"]
        if (isinstance(pilot_groups, bool) or not isinstance(pilot_groups, (int, float))
                or not math.isfinite(float(pilot_groups)) or float(pilot_groups) != PILOT_ORDERS):
            raise ValueError("pilot_groups与预实验规模不一致")
        per_data = float(data["per_group_data"])
        per_fs = float(data["per_group_filesystem"])
        if not math.isfinite(per_data) or per_data <= 0:
            raise ValueError("per_group_data必须是有限正数")
        if not math.isfinite(per_fs) or per_fs <= 0:
            raise ValueError("per_group_filesystem必须是有限正数")
    except (KeyError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise RuntimeError("空间估算文件缺失必要字段或已损坏") from exc
    remaining = max(0, FULL_ORDERS - committed_groups)
    estimated = math.ceil(per_data * remaining * 1.5)
    estimated_fs = math.ceil(per_fs * remaining * 1.5)
    data_free = snapshot["data_capacity"] - snapshot["data_used"]
    log_free = snapshot["log_capacity"] - snapshot["log_used"]
    filesystem_reserve = DATA_RESERVE + LOG_RESERVE if snapshot.get("same_filesystem") else DATA_RESERVE
    if data_free-estimated < DATA_RESERVE or snapshot["data_filesystem_free"]-estimated_fs < filesystem_reserve or log_free < LOG_RESERVE:
        raise RuntimeError("恢复时预计剩余空间不足")
    print(f"SPACE_ESTIMATE_REUSED|committed={committed_groups}|remaining={remaining}|estimated={estimated}|estimated_fs={estimated_fs}")


def committed_group_prefix(counts: dict[str, int]) -> int:
    card_groups = counts["recharge_card"] // 2 if counts["recharge_card"] <= 40000 else counts["recharge_card"] - 20000
    return min(counts["app_user"], counts["owner"], counts["mobile_number"], counts["purchase_order"], counts["order_item"], card_groups, counts["recharge_record"])


def pilot_resume_action(counts: dict[str, int], estimate_exists: bool) -> str:
    expected = {"app_user": PILOT_ORDERS, "owner": PILOT_ORDERS, "mobile_number": PILOT_ORDERS, "purchase_order": PILOT_ORDERS, "order_item": PILOT_ORDERS, "recharge_card": expected_card_count(PILOT_ORDERS), "recharge_record": PILOT_ORDERS}
    if counts == expected:
        if not estimate_exists:
            raise RuntimeError("1000组预实验已完成但空间估算文件缺失")
        return "reuse_pilot"
    if max(counts.values(), default=0) <= expected_card_count(PILOT_ORDERS):
        return "complete_pilot"
    if not estimate_exists:
        raise RuntimeError("恢复完整插入时空间估算文件缺失")
    return "resume_full"


def reject_performance_indexes(index_names: set[str]) -> None:
    allowed = {"PRIMARY", "uk_app_user_login_name", "uk_mobile_number_phone", "uk_purchase_order_no", "uk_order_item_order_denomination", "uk_recharge_card_no", "uk_recharge_record_card", "fk_mobile_number_owner", "fk_purchase_order_user", "fk_order_item_order", "fk_recharge_card_item", "fk_recharge_record_card", "fk_recharge_record_mobile"}
    unexpected = index_names - allowed
    if unexpected:
        raise RuntimeError(f"检测到阶段8性能索引：{sorted(unexpected)}")


def validate_index_baseline(connection) -> None:
    with connection.cursor() as cursor:
        cursor.execute("SELECT DISTINCT INDEX_NAME FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME IN ('app_user','owner','mobile_number','purchase_order','order_item','recharge_card','recharge_record')")
        reject_performance_indexes({row["INDEX_NAME"] for row in cursor.fetchall()})


def validate_views(connection, order_target: int) -> None:
    purchase = int(scalar(connection, "SELECT COUNT(*) value FROM v_user_card_purchase_detail WHERE LEFT(order_no,9)=%s", ("P7-ORDER-",)))
    recharge = int(scalar(connection, "SELECT COUNT(*) value FROM v_mobile_recharge_history WHERE LEFT(phone_number,4)=%s", ("1987",)))
    validate_view_counts(purchase, recharge, order_target)


def validate_view_counts(purchase: int, recharge: int, order_target: int) -> None:
    if purchase != expected_card_count(order_target) or recharge != order_target:
        raise RuntimeError(f"阶段5视图P7数量错误：purchase={purchase},recharge={recharge}")


def delete_ids(connection, table: str, id_column: str, select_sql: str, params: tuple) -> None:
    while True:
        with connection.cursor() as cursor:
            cursor.execute(select_sql + " LIMIT 500", params)
            ids = [int(next(iter(row.values()))) for row in cursor.fetchall()]
        if not ids:
            return
        placeholders = ",".join(["%s"] * len(ids))
        try:
            connection.begin()
            with connection.cursor() as cursor:
                cursor.execute(f"DELETE FROM {table} WHERE {id_column} IN ({placeholders})", tuple(ids))
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        print(f"CLEANUP|{table}|rows={len(ids)}")


def cleanup(connection) -> None:
    counts = marker_counts(connection)
    print(f"CLEANUP_PREVIEW|{counts}")
    require_no_anomalies("清理前发现P7子记录错误引用，拒绝删除", reference_anomalies(connection))
    require_no_anomalies("清理前发现非P7子记录引用P7父记录，拒绝删除", cleanup_inbound_anomalies(connection))
    confirmation = input("请输入完整确认文本 DELETE P7 DATA：")
    if confirmation != "DELETE P7 DATA":
        raise RuntimeError("确认文本不匹配，未删除任何数据")
    steps = [
        ("recharge_record", "recharge_id", "SELECT rr.recharge_id FROM recharge_record rr JOIN recharge_card rc ON rc.card_id=rr.card_id WHERE LEFT(rc.card_no,8)=%s", ("P7-CARD-",)),
        ("recharge_card", "card_id", "SELECT card_id FROM recharge_card WHERE LEFT(card_no,8)=%s", ("P7-CARD-",)),
        ("order_item", "item_id", "SELECT oi.item_id FROM order_item oi JOIN purchase_order po ON po.order_id=oi.order_id WHERE LEFT(po.order_no,9)=%s", ("P7-ORDER-",)),
        ("purchase_order", "order_id", "SELECT order_id FROM purchase_order WHERE LEFT(order_no,9)=%s", ("P7-ORDER-",)),
        ("mobile_number", "mobile_id", "SELECT mn.mobile_id FROM mobile_number mn JOIN owner o ON o.owner_id=mn.owner_id WHERE LEFT(o.owner_name,9)=%s", ("P7_OWNER_",)),
        ("owner", "owner_id", "SELECT owner_id FROM owner WHERE LEFT(owner_name,9)=%s", ("P7_OWNER_",)),
        ("app_user", "user_id", "SELECT user_id FROM app_user WHERE LEFT(login_name,8)=%s", ("p7_user_",)),
    ]
    for args in steps:
        delete_ids(connection, *args)
    if any(marker_counts(connection).values()):
        raise RuntimeError("P7清理后仍有残留")
    print("PASS|P7清理完成|all=0")


def protect_baseline(connection) -> None:
    if table_count(connection) != 7 or p4_counts(connection) != EXPECTED_P4 or p5_object_counts(connection) != "2,2" or p6_residue_count(connection) != 0:
        raise RuntimeError("P4/P5/P6保护基线不符合预期")


def execute_pilot_phase(connection, resource_before: dict[str, int]) -> dict[str, int]:
    existing = marker_counts(connection)
    estimate_path = Path(os.environ.get("P7_ESTIMATE_FILE", ""))
    action = pilot_resume_action(existing, estimate_path.is_file())
    if action == "reuse_pilot":
        print("PILOT_COMPLETE|复用已完成的1000组预实验")
        validate_dataset(connection, PILOT_ORDERS)
        validate_saved_estimate(resource_before, PILOT_ORDERS)
    elif action == "complete_pilot":
        print("阶段7开始1000组小规模预实验/恢复检查")
        insert_to_target(connection, PILOT_ORDERS)
        validate_dataset(connection, PILOT_ORDERS)
        pilot_after = resource_snapshot(connection)
        estimate_full_space(resource_before, pilot_after)
    else:
        print(f"PILOT_SKIPPED|检测到已超过1000组的合法恢复前缀|{existing}")
        validate_saved_estimate(resource_before, committed_group_prefix(existing))
    return marker_counts(connection)


def run(cleanup_mode: bool, pilot_only: bool = False) -> int:
    if cleanup_mode and pilot_only:
        raise ValueError("--pilot-only与--cleanup互斥")
    config = load_database_config()
    connection = connect(config, autocommit=False)
    started = time.perf_counter()
    try:
        protect_baseline(connection)
        if cleanup_mode:
            resource_snapshot(connection, enforce_data=False)
            cleanup(connection)
            protect_baseline(connection)
            return 0
        validate_index_baseline(connection)
        resource_before = resource_snapshot(connection)
        validate_prefixes(connection, FULL_ORDERS)
        execute_pilot_phase(connection, resource_before)
        if pilot_only:
            protect_baseline(connection)
            print("PILOT_ONLY_PASS")
            return 0
        print("阶段7开始续跑至10万组关联数据")
        insert_to_target(connection, FULL_ORDERS)
        validate_dataset(connection, FULL_ORDERS)
        validate_views(connection, FULL_ORDERS)
        protect_baseline(connection)
        resource_after = resource_snapshot(connection)
        print(f"SPACE_CHANGE|data={resource_after['data_used']-resource_before['data_used']}|log={resource_after['log_used']-resource_before['log_used']}")
        print(f"TOTAL_SECONDS|{time.perf_counter()-started:.6f}")
        print("最终状态：PASS")
        return 0
    finally:
        connection.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="阶段7大规模数据自动实验")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--cleanup", action="store_true")
    modes.add_argument("--pilot-only", action="store_true")
    args = parser.parse_args()
    try:
        return run(args.cleanup, args.pilot_only)
    except Exception as exc:
        print(f"最终状态：FAIL｜{exc.__class__.__name__}｜{exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
