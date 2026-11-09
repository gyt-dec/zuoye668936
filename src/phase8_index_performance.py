#!/usr/bin/env python3
"""阶段8：在固定P7数据上完成索引前后查询、EXPLAIN和写入代价对比。"""

from __future__ import annotations

import csv
import json
import os
import statistics
import time
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from src.db import connect
from src.db_config import load_database_config
from src.phase7_large_data import marker_counts, reject_performance_indexes
from src.services.integrity_service import EXPECTED_P4, p4_counts, p5_object_counts, p6_residue_count, scalar, table_count

REPEATS = 5
WARMUPS = 1
P8_CARD_PREFIX = "P8-PERF-"
EXPECTED_P7 = {
    "app_user": 100000, "owner": 100000, "mobile_number": 100000,
    "purchase_order": 100000, "order_item": 100000,
    "recharge_card": 120000, "recharge_record": 100000,
}
INDEXES = {
    "idx_p8_card_status_created": ("recharge_card", ("card_status", "created_at", "card_id")),
    "idx_p8_record_time_mobile": ("recharge_record", ("recharged_at", "mobile_id", "card_id")),
    "idx_p8_order_status_created": ("purchase_order", ("order_status", "created_at", "user_id", "order_id")),
}
QUERIES = {
    "Q1_unused_cards": (
        "SELECT COUNT(*) row_count,COALESCE(SUM(face_value),0) total_amount "
        "FROM recharge_card WHERE card_status=%s AND created_at BETWEEN %s AND %s",
        ("UNUSED", "2026-07-12 00:00:00", "2026-08-31 23:59:59"),
    ),
    "Q2_recharge_history": (
        "SELECT COUNT(*) row_count,COUNT(DISTINCT rr.mobile_id) mobile_count,"
        "COALESCE(SUM(rr.recharge_amount),0) total_amount "
        "FROM recharge_record rr JOIN mobile_number mn ON mn.mobile_id=rr.mobile_id "
        "JOIN owner o ON o.owner_id=mn.owner_id JOIN recharge_card rc ON rc.card_id=rr.card_id "
        "WHERE rr.recharged_at BETWEEN %s AND %s",
        ("2026-06-15 00:00:00", "2026-07-20 23:59:59"),
    ),
    "Q3_order_card_join": (
        "SELECT COUNT(*) row_count,COUNT(DISTINCT po.order_id) order_count,"
        "COALESCE(SUM(rc.face_value),0) total_amount "
        "FROM purchase_order po JOIN app_user u ON u.user_id=po.user_id "
        "JOIN order_item oi ON oi.order_id=po.order_id "
        "JOIN recharge_card rc ON rc.item_id=oi.item_id "
        "WHERE po.order_status=%s AND po.created_at BETWEEN %s AND %s",
        ("COMPLETED", "2026-06-10 00:00:00", "2026-07-25 23:59:59"),
    ),
}


def median_ms(samples: list[float]) -> float:
    if len(samples) != REPEATS or any(value < 0 for value in samples):
        raise ValueError("计时样本不完整")
    return round(statistics.median(samples), 3)


def temporary_card_no(repeat: int, sequence: int) -> str:
    """生成只用于回滚写入测试的卡号。"""
    return f"{P8_CARD_PREFIX}{repeat:02d}-{sequence:04d}"


def index_metadata(connection) -> dict[str, tuple[str, tuple[str, ...]]]:
    sql = """SELECT TABLE_NAME,INDEX_NAME,SEQ_IN_INDEX,COLUMN_NAME
             FROM information_schema.STATISTICS
             WHERE TABLE_SCHEMA=DATABASE() AND INDEX_NAME LIKE 'idx_p8_%'
             ORDER BY INDEX_NAME,SEQ_IN_INDEX"""
    with connection.cursor() as cursor:
        cursor.execute(sql)
        rows = cursor.fetchall()
    grouped: dict[str, tuple[str, list[str]]] = {}
    for row in rows:
        name = row["INDEX_NAME"]
        if name not in grouped:
            grouped[name] = (row["TABLE_NAME"], [])
        grouped[name][1].append(row["COLUMN_NAME"])
    return {name: (table, tuple(columns)) for name, (table, columns) in grouped.items()}


def all_index_names(connection) -> set[str]:
    with connection.cursor() as cursor:
        cursor.execute("""SELECT DISTINCT INDEX_NAME FROM information_schema.STATISTICS
                          WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME IN
                          ('app_user','owner','mobile_number','purchase_order','order_item',
                           'recharge_card','recharge_record')""")
        return {row["INDEX_NAME"] for row in cursor.fetchall()}


def validate_index_state(actual, expected=INDEXES) -> str:
    if not actual:
        return "before"
    if actual == expected:
        return "after"
    raise RuntimeError(f"阶段8索引处于不完整或定义不符状态：{actual}")


def explain(connection, sql, params):
    with connection.cursor() as cursor:
        cursor.execute("EXPLAIN " + sql, params)
        return cursor.fetchall()


def execute_query(connection, sql, params):
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        return cursor.fetchone()


def benchmark_queries(connection):
    result = {}
    for name, (sql, params) in QUERIES.items():
        for _ in range(WARMUPS):
            execute_query(connection, sql, params)
        samples = []
        expected = None
        for _ in range(REPEATS):
            started = time.perf_counter()
            row = execute_query(connection, sql, params)
            samples.append((time.perf_counter() - started) * 1000)
            normalized = {key: str(value) for key, value in row.items()}
            if expected is not None and normalized != expected:
                raise RuntimeError(f"{name}重复查询结果不一致")
            expected = normalized
        result[name] = {
            "samples_ms": [round(value, 3) for value in samples],
            "median_ms": median_ms(samples), "result": expected,
            "explain": explain(connection, sql, params),
        }
        print(f"PASS|{name}|median_ms={result[name]['median_ms']}|rows={expected.get('row_count')}")
    return result


def table_index_length(connection) -> int:
    value = scalar(connection, "SELECT COALESCE(SUM(INDEX_LENGTH),0) value FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE()")
    return int(value or 0)


def write_benchmark(connection):
    with connection.cursor() as cursor:
        cursor.execute("""SELECT oi.item_id,oi.denomination FROM order_item oi
                          JOIN purchase_order po ON po.order_id=oi.order_id
                          WHERE LEFT(po.order_no,9)=%s ORDER BY po.order_id LIMIT 1""", ("P7-ORDER-",))
        parent = cursor.fetchone()
    if not parent:
        raise RuntimeError("找不到P7订单明细，无法执行写入代价测试")
    samples = []
    for repeat in range(REPEATS):
        rows = [(parent["item_id"], temporary_card_no(repeat, seq), "p8$temporary$hash", parent["denomination"], "UNUSED", "2026-09-01 00:00:00", None) for seq in range(200)]
        connection.begin()
        try:
            started = time.perf_counter()
            with connection.cursor() as cursor:
                cursor.executemany("""INSERT INTO recharge_card
                    (item_id,card_no,password_hash,face_value,card_status,created_at,used_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s)""", rows)
            samples.append((time.perf_counter() - started) * 1000)
        finally:
            connection.rollback()
    residue = int(scalar(
        connection,
        "SELECT COUNT(*) value FROM recharge_card WHERE LEFT(card_no,%s)=%s",
        (len(P8_CARD_PREFIX), P8_CARD_PREFIX),
    ))
    if residue != 0:
        raise RuntimeError(f"写入测试回滚后仍有P8残留：{residue}")
    return {"rows_per_repeat": 200, "samples_ms": [round(v, 3) for v in samples], "median_ms": median_ms(samples)}


def create_indexes(connection):
    statements = [
        "CREATE INDEX idx_p8_card_status_created ON recharge_card (card_status, created_at, card_id)",
        "CREATE INDEX idx_p8_record_time_mobile ON recharge_record (recharged_at, mobile_id, card_id)",
        "CREATE INDEX idx_p8_order_status_created ON purchase_order (order_status, created_at, user_id, order_id)",
    ]
    with connection.cursor() as cursor:
        for statement in statements:
            cursor.execute(statement)
            print(f"PASS|创建索引|{statement.split()[2]}")


def validate_baseline(connection):
    version = scalar(connection, "SELECT VERSION() value")
    mode = scalar(connection, "SELECT @@ob_compatibility_mode value")
    database = scalar(connection, "SELECT DATABASE() value")
    if "OceanBase_CE-v5.0.1.0" not in str(version) or str(mode).upper() != "MYSQL" or database != "phone_recharge_db":
        raise RuntimeError(f"环境不符合阶段8要求：{version},{mode},{database}")
    if table_count(connection) != 7 or p4_counts(connection) != EXPECTED_P4 or p5_object_counts(connection) != (2, 2) or p6_residue_count(connection) != 0:
        raise RuntimeError("阶段3至6保护基线不符合预期")
    counts = marker_counts(connection)
    if counts != EXPECTED_P7:
        raise RuntimeError(f"阶段7数据量不符合目标：{counts}")
    print(f"PASS|环境与P3-P7基线|{version}|P7={','.join(str(counts[k]) for k in counts)}")


def json_safe(value):
    if isinstance(value, (datetime,)):
        return value.isoformat(sep=" ")
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(type(value).__name__)


def save_json(path: Path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=json_safe), encoding="utf-8")


def export_csv(path: Path, before, after):
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(["query", "before_median_ms", "after_median_ms", "change_percent", "result_equal"])
        for name in QUERIES:
            old, new = before[name]["median_ms"], after[name]["median_ms"]
            change = round((old - new) / old * 100, 2) if old else 0
            writer.writerow([name, old, new, change, before[name]["result"] == after[name]["result"]])


def run():
    result_dir = Path(os.environ.get("P8_RESULT_DIR", "results/phase8"))
    result_dir.mkdir(parents=True, exist_ok=True)
    state_path = result_dir / "phase8_baseline_state.json"
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    connection = connect(load_database_config(), autocommit=True)
    try:
        validate_baseline(connection)
        state = validate_index_state(index_metadata(connection))
        if state == "before":
            # 复用阶段7的严格白名单，防止其他名称的普通索引污染无索引基线。
            reject_performance_indexes(all_index_names(connection))
            before = {"queries": benchmark_queries(connection), "write": write_benchmark(connection), "index_length": table_index_length(connection)}
            save_json(state_path, before)
            print(f"PASS|无性能索引基线已保存|{state_path}")
            create_indexes(connection)
        else:
            if not state_path.exists():
                raise RuntimeError("性能索引已存在，但缺少可信的无索引基线状态文件")
            before = json.loads(state_path.read_text(encoding="utf-8"))
            print("PASS|恢复模式|复用已保存的无索引基线")
        if validate_index_state(index_metadata(connection)) != "after":
            raise RuntimeError("三个阶段8索引未完整创建")
        after = {"queries": benchmark_queries(connection), "write": write_benchmark(connection), "index_length": table_index_length(connection)}
        for name in QUERIES:
            if before["queries"][name]["result"] != after["queries"][name]["result"]:
                raise RuntimeError(f"{name}索引前后结果不一致")
        validate_baseline(connection)
        detail = {"before": before, "after": after, "indexes": index_metadata(connection)}
        detail_path = result_dir / f"phase8_index_detail_{stamp}.json"
        csv_path = result_dir / f"phase8_index_comparison_{stamp}.csv"
        save_json(detail_path, detail)
        export_csv(csv_path, before["queries"], after["queries"])
        print(f"PASS|索引前后查询结果一致|{len(QUERIES)}")
        print(f"PASS|P8临时写入最终残留|0")
        print(f"PASS|结果文件|{detail_path}|{csv_path}")
        print("最终状态：PASS")
        return 0
    finally:
        connection.close()


if __name__ == "__main__":
    try:
        exit_code = run()
    except KeyboardInterrupt:
        print("最终状态：FAIL｜用户中断")
        raise
    except Exception as exc:
        print(f"最终状态：FAIL｜{type(exc).__name__}｜{exc}")
        raise SystemExit(1)
    raise SystemExit(exit_code)
