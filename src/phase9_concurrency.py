#!/usr/bin/env python3
"""阶段9：并发丢失更新与同一卡充值竞争实验。"""

from __future__ import annotations

import csv
from collections import Counter
import json
import os
import queue
import statistics
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from src.db import connect
from src.db_config import DatabaseConfig, load_database_config
from src.phase7_large_data import marker_counts
from src.phase8_index_performance import INDEXES, index_metadata
from src.services.integrity_service import EXPECTED_P4, p4_counts, p5_object_counts, p6_residue_count, scalar, table_count

LOADS = (
    ("1x", 10, 5),
    ("10x", 100, 10),
    ("100x", 1000, 20),
)
P9_USER = "p9_user_concurrency"
P9_OWNER = "P9_OWNER_CONCURRENCY"
P9_PHONE = "197900000001"
P9_PREFIX = "P9-"
P9_HASH = "p9$concurrency$not-a-real-credential"
EXPECTED_P7 = {
    "app_user": 100000, "owner": 100000, "mobile_number": 100000,
    "purchase_order": 100000, "order_item": 100000,
    "recharge_card": 120000, "recharge_record": 100000,
}


@dataclass
class RequestResult:
    outcome: str
    elapsed_ms: float
    error_code: str = ""
    observed_unused: bool = False
    attempted_insert: bool = False


@dataclass
class RoundResult:
    experiment: str
    strategy: str
    load: str
    requests: int
    workers: int
    success: int
    business_rejected: int
    constraint_rejected: int
    unexpected_errors: int
    error_codes: str
    elapsed_ms: float
    throughput_rps: float
    median_ms: float
    p95_ms: float
    expected_value: str
    actual_value: str
    lost_updates: int
    observed_unused: int
    attempted_inserts: int
    final_records: int
    final_card_status: str
    consistent: bool


class ConnectionPool:
    """固定数量连接，避免100倍负载创建1000个并发连接。"""

    def __init__(self, config: DatabaseConfig, size: int):
        self.connections = [connect(config, autocommit=False) for _ in range(size)]
        self.available = queue.Queue()
        for connection in self.connections:
            self.available.put(connection)

    def acquire(self):
        return self.available.get()

    def release(self, connection):
        self.available.put(connection)

    def close(self):
        for connection in self.connections:
            connection.close()


def wave_sizes(requests: int, workers: int) -> list[int]:
    if requests <= 0 or workers <= 0:
        raise ValueError("请求数和并发数必须大于0")
    return [min(workers, requests - start) for start in range(0, requests, workers)]


def percentile95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return round(ordered[max(0, (95 * len(ordered) + 99) // 100 - 1)], 3)


def summarize(results: list[RequestResult]) -> dict[str, int | float]:
    elapsed = [row.elapsed_ms for row in results]
    return {
        "success": sum(row.outcome == "success" for row in results),
        "business_rejected": sum(row.outcome == "business_rejected" for row in results),
        "constraint_rejected": sum(row.outcome == "constraint_rejected" for row in results),
        "unexpected_errors": sum(row.outcome == "unexpected_error" for row in results),
        "observed_unused": sum(row.observed_unused for row in results),
        "attempted_inserts": sum(row.attempted_insert for row in results),
        "median_ms": round(statistics.median(elapsed), 3) if elapsed else 0.0,
        "p95_ms": percentile95(elapsed),
        "error_codes": ",".join(f"{code}:{count}" for code, count in sorted(Counter(row.error_code for row in results if row.error_code).items())),
    }


def p9_residue_count(connection) -> int:
    return int(scalar(connection, """SELECT
      (SELECT COUNT(*) FROM app_user WHERE login_name=%s)+
      (SELECT COUNT(*) FROM owner WHERE owner_name=%s)+
      (SELECT COUNT(*) FROM mobile_number WHERE phone_number=%s)+
      (SELECT COUNT(*) FROM purchase_order WHERE LEFT(order_no,%s)=%s)+
      (SELECT COUNT(*) FROM order_item oi JOIN purchase_order po ON po.order_id=oi.order_id WHERE LEFT(po.order_no,%s)=%s)+
      (SELECT COUNT(*) FROM recharge_card WHERE LEFT(card_no,%s)=%s)+
      (SELECT COUNT(*) FROM recharge_record rr JOIN recharge_card rc ON rc.card_id=rr.card_id WHERE LEFT(rc.card_no,%s)=%s) value""",
      (P9_USER, P9_OWNER, P9_PHONE, len(P9_PREFIX), P9_PREFIX,
       len(P9_PREFIX), P9_PREFIX, len(P9_PREFIX), P9_PREFIX,
       len(P9_PREFIX), P9_PREFIX)))


def verify_protected_baseline(connection):
    if table_count(connection) != 7 or p4_counts(connection) != EXPECTED_P4:
        raise RuntimeError("阶段3/4表或数据基线改变")
    if p5_object_counts(connection) != "2,2" or p6_residue_count(connection) != 0:
        raise RuntimeError("阶段5/6保护基线改变")
    if marker_counts(connection) != EXPECTED_P7:
        raise RuntimeError("阶段7数据基线改变")
    if index_metadata(connection) != INDEXES:
        raise RuntimeError("阶段8三个性能索引缺失或定义改变")


def make_order_no(experiment: str, strategy: str, load: str) -> str:
    return f"P9-{experiment}-{strategy}-{load}"


def setup_data(connection) -> dict:
    """一次事务创建各轮独立订单、卡和共享P9手机号。"""
    context = {"order_ids": {}, "card_ids": {}, "item_ids": [], "mobile_id": None, "user_id": None, "owner_id": None}
    connection.begin()
    try:
        with connection.cursor() as cursor:
            cursor.execute("INSERT INTO app_user(login_name,password_hash,registered_at,user_status,display_name) VALUES(%s,%s,NOW(6),'ACTIVE','P9并发用户')", (P9_USER, P9_HASH))
            context["user_id"] = int(cursor.lastrowid)
            cursor.execute("INSERT INTO owner(owner_name,contact_info) VALUES(%s,'p9@example.test')", (P9_OWNER,))
            context["owner_id"] = int(cursor.lastrowid)
            cursor.execute("INSERT INTO mobile_number(owner_id,phone_number,number_status,registered_at) VALUES(%s,%s,'ACTIVE',NOW(6))", (context["owner_id"], P9_PHONE))
            context["mobile_id"] = int(cursor.lastrowid)
            for load, _, _ in LOADS:
                for strategy in ("unsafe", "locked"):
                    lost_order = make_order_no("LOST", strategy, load)
                    cursor.execute("INSERT INTO purchase_order(user_id,order_no,created_at,order_status,total_amount,completed_at) VALUES(%s,%s,NOW(6),'COMPLETED',0.00,NOW(6))", (context["user_id"], lost_order))
                    context["order_ids"][lost_order] = int(cursor.lastrowid)

                    card_order = make_order_no("CARD", strategy, load)
                    cursor.execute("INSERT INTO purchase_order(user_id,order_no,created_at,order_status,total_amount,completed_at) VALUES(%s,%s,NOW(6),'COMPLETED',10.00,NOW(6))", (context["user_id"], card_order))
                    order_id = int(cursor.lastrowid)
                    context["order_ids"][card_order] = order_id
                    cursor.execute("INSERT INTO order_item(order_id,denomination,quantity) VALUES(%s,10.00,1)", (order_id,))
                    item_id = int(cursor.lastrowid)
                    context["item_ids"].append(item_id)
                    card_no = f"P9-CARD-{strategy}-{load}"
                    cursor.execute("INSERT INTO recharge_card(item_id,card_no,password_hash,face_value,card_status,created_at,used_at) VALUES(%s,%s,%s,10.00,'UNUSED',NOW(6),NULL)", (item_id, card_no, P9_HASH))
                    context["card_ids"][card_no] = int(cursor.lastrowid)
        connection.commit()
        return context
    except BaseException:
        connection.rollback()
        raise


def _lost_worker(pool, order_id: int, barrier: threading.Barrier, locked: bool) -> RequestResult:
    connection = pool.acquire()
    started = time.perf_counter()
    try:
        if locked:
            barrier.wait(timeout=30)
        connection.begin()
        with connection.cursor() as cursor:
            suffix = " FOR UPDATE" if locked else ""
            cursor.execute("SELECT total_amount FROM purchase_order WHERE order_id=%s" + suffix, (order_id,))
            old = Decimal(cursor.fetchone()["total_amount"])
            if not locked:
                # 确保同一波次全部读取相同旧值后才写入，确定性复现丢失更新。
                barrier.wait(timeout=30)
            cursor.execute("UPDATE purchase_order SET total_amount=%s WHERE order_id=%s", (old + Decimal("1.00"), order_id))
        connection.commit()
        return RequestResult("success", (time.perf_counter() - started) * 1000)
    except Exception as exc:
        connection.rollback()
        return RequestResult("unexpected_error", (time.perf_counter() - started) * 1000, database_error_code(exc))
    finally:
        pool.release(connection)


def run_lost_round(config, control, strategy: str, load: str, requests: int, workers: int) -> RoundResult:
    order_no = make_order_no("LOST", strategy, load)
    order_id = int(scalar(control, "SELECT order_id value FROM purchase_order WHERE order_no=%s", (order_no,)))
    pool = ConnectionPool(config, workers)
    results, started = [], time.perf_counter()
    try:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            for size in wave_sizes(requests, workers):
                barrier = threading.Barrier(size)
                futures = [executor.submit(_lost_worker, pool, order_id, barrier, strategy == "locked") for _ in range(size)]
                results.extend(future.result() for future in futures)
    finally:
        pool.close()
    total_ms = (time.perf_counter() - started) * 1000
    stats = summarize(results)
    actual = Decimal(str(scalar(control, "SELECT total_amount value FROM purchase_order WHERE order_id=%s", (order_id,))))
    expected = Decimal(requests)
    lost = int(expected - actual)
    consistent = stats["unexpected_errors"] == 0 and (actual < expected if strategy == "unsafe" else actual == expected)
    return RoundResult("lost_update", strategy, load, requests, workers,
        int(stats["success"]), int(stats["business_rejected"]), int(stats["constraint_rejected"]), int(stats["unexpected_errors"]), str(stats["error_codes"]),
        round(total_ms, 3), round(requests / (total_ms / 1000), 3), float(stats["median_ms"]), float(stats["p95_ms"]),
        f"{expected:.2f}", f"{actual:.2f}", lost, 0, 0, 0, "", consistent)


def classify_constraint(exc: Exception) -> bool:
    text = str(exc)
    return exc.__class__.__name__ == "IntegrityError" or "P5_" in text or "Duplicate entry" in text


def database_error_code(exc: Exception) -> str:
    """只记录错误编号/类型，不把SQL、连接信息或密码写入结果。"""
    if exc.args and isinstance(exc.args[0], (int, str)):
        return str(exc.args[0])
    return type(exc).__name__


def _card_worker(pool, card_id: int, mobile_id: int, barrier: threading.Barrier, locked: bool) -> RequestResult:
    connection = pool.acquire()
    started = time.perf_counter()
    observed, attempted = False, False
    try:
        if locked:
            barrier.wait(timeout=30)
        connection.begin()
        with connection.cursor() as cursor:
            suffix = " FOR UPDATE" if locked else ""
            cursor.execute("SELECT card_status,face_value FROM recharge_card WHERE card_id=%s" + suffix, (card_id,))
            card = cursor.fetchone()
            observed = bool(card and card["card_status"] == "UNUSED")
            if not locked:
                # 所有请求完成状态读取后再决定是否插入，记录真实竞争窗口。
                barrier.wait(timeout=30)
            if not observed:
                connection.rollback()
                return RequestResult("business_rejected", (time.perf_counter() - started) * 1000, "CARD_ALREADY_USED", observed, False)
            attempted = True
            cursor.execute("INSERT INTO recharge_record(card_id,mobile_id,recharge_amount,recharged_at) VALUES(%s,%s,%s,NOW(6))", (card_id, mobile_id, card["face_value"]))
        connection.commit()
        return RequestResult("success", (time.perf_counter() - started) * 1000, observed_unused=observed, attempted_insert=attempted)
    except Exception as exc:
        connection.rollback()
        outcome = "constraint_rejected" if classify_constraint(exc) else "unexpected_error"
        return RequestResult(outcome, (time.perf_counter() - started) * 1000, database_error_code(exc), observed, attempted)
    finally:
        pool.release(connection)


def run_card_round(config, control, strategy: str, load: str, requests: int, workers: int) -> RoundResult:
    card_no = f"P9-CARD-{strategy}-{load}"
    with control.cursor() as cursor:
        cursor.execute("SELECT card_id FROM recharge_card WHERE card_no=%s", (card_no,))
        card_id = int(cursor.fetchone()["card_id"])
        cursor.execute("SELECT mobile_id FROM mobile_number WHERE phone_number=%s", (P9_PHONE,))
        mobile_id = int(cursor.fetchone()["mobile_id"])
    pool = ConnectionPool(config, workers)
    results, started = [], time.perf_counter()
    try:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            for size in wave_sizes(requests, workers):
                barrier = threading.Barrier(size)
                futures = [executor.submit(_card_worker, pool, card_id, mobile_id, barrier, strategy == "locked") for _ in range(size)]
                results.extend(future.result() for future in futures)
    finally:
        pool.close()
    total_ms = (time.perf_counter() - started) * 1000
    stats = summarize(results)
    with control.cursor() as cursor:
        cursor.execute("""SELECT rc.card_status,COUNT(rr.recharge_id) record_count,
                          SUM(CASE WHEN rc.used_at=rr.recharged_at THEN 1 ELSE 0 END) time_match
                          FROM recharge_card rc LEFT JOIN recharge_record rr ON rr.card_id=rc.card_id
                          WHERE rc.card_id=%s GROUP BY rc.card_id,rc.card_status""", (card_id,))
        final = cursor.fetchone()
    records, status = int(final["record_count"]), final["card_status"]
    consistent = (stats["unexpected_errors"] == 0 and stats["success"] == 1 and records == 1 and status == "USED" and int(final["time_match"] or 0) == 1)
    if strategy == "unsafe":
        consistent = consistent and stats["observed_unused"] > 1 and stats["constraint_rejected"] > 0
    else:
        consistent = consistent and stats["constraint_rejected"] == 0 and stats["business_rejected"] == requests - 1
    return RoundResult("same_card", strategy, load, requests, workers,
        int(stats["success"]), int(stats["business_rejected"]), int(stats["constraint_rejected"]), int(stats["unexpected_errors"]), str(stats["error_codes"]),
        round(total_ms, 3), round(requests / (total_ms / 1000), 3), float(stats["median_ms"]), float(stats["p95_ms"]),
        "USED/1", f"{status}/{records}", 0, int(stats["observed_unused"]), int(stats["attempted_inserts"]), records, status, consistent)


def cleanup_p9(connection, context):
    """只按本次创建并保存的主键反向删除P9对象。"""
    connection.begin()
    try:
        with connection.cursor() as cursor:
            card_ids = tuple(context["card_ids"].values())
            order_ids = tuple(context["order_ids"].values())
            if card_ids:
                marks = ",".join(["%s"] * len(card_ids))
                cursor.execute(f"DELETE FROM recharge_record WHERE card_id IN ({marks})", card_ids)
                cursor.execute(f"DELETE FROM recharge_card WHERE card_id IN ({marks})", card_ids)
            if context["item_ids"]:
                marks = ",".join(["%s"] * len(context["item_ids"]))
                cursor.execute(f"DELETE FROM order_item WHERE item_id IN ({marks})", tuple(context["item_ids"]))
            marks = ",".join(["%s"] * len(order_ids))
            cursor.execute(f"DELETE FROM purchase_order WHERE order_id IN ({marks})", order_ids)
            cursor.execute("DELETE FROM mobile_number WHERE mobile_id=%s", (context["mobile_id"],))
            cursor.execute("DELETE FROM owner WHERE owner_id=%s", (context["owner_id"],))
            cursor.execute("DELETE FROM app_user WHERE user_id=%s", (context["user_id"],))
        connection.commit()
    except BaseException:
        connection.rollback()
        raise


def save_results(result_dir: Path, rounds: list[RoundResult]):
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = result_dir / f"phase9_concurrency_{stamp}.json"
    csv_path = result_dir / f"phase9_concurrency_{stamp}.csv"
    payload = {"environment": "OceanBase CE 5.0.1.0 / MySQL", "loads": [list(row) for row in LOADS], "rounds": [asdict(row) for row in rounds]}
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(asdict(rounds[0]).keys()))
        writer.writeheader()
        writer.writerows(asdict(row) for row in rounds)
    return json_path, csv_path


def run() -> int:
    config = load_database_config()
    result_dir = Path(os.environ.get("P9_RESULT_DIR", "results/phase9"))
    result_dir.mkdir(parents=True, exist_ok=True)
    control = connect(config, autocommit=True)
    context = None
    try:
        version = str(scalar(control, "SELECT VERSION() value"))
        mode = str(scalar(control, "SELECT @@ob_compatibility_mode value"))
        if "OceanBase_CE-v5.0.1.0" not in version or mode.upper() != "MYSQL":
            raise RuntimeError(f"环境不符合阶段9要求：{version},{mode}")
        verify_protected_baseline(control)
        if p9_residue_count(control) != 0:
            raise RuntimeError("检测到P9残留；为避免误删，普通入口拒绝继续")
        print(f"PASS|环境与阶段3-8保护基线|{version}|MYSQL")
        context = setup_data(control)
        rounds = []
        for load, requests, workers in LOADS:
            for strategy in ("unsafe", "locked"):
                result = run_lost_round(config, control, strategy, load, requests, workers)
                rounds.append(result)
                print(f"ROUND|lost_update|{strategy}|{load}|success={result.success}|lost={result.lost_updates}|elapsed_ms={result.elapsed_ms}|consistent={result.consistent}")
                if not result.consistent:
                    raise RuntimeError(f"丢失更新轮次验证失败：{strategy}/{load}")
            for strategy in ("unsafe", "locked"):
                result = run_card_round(config, control, strategy, load, requests, workers)
                rounds.append(result)
                print(f"ROUND|same_card|{strategy}|{load}|unused_reads={result.observed_unused}|attempts={result.attempted_inserts}|success={result.success}|business_rejected={result.business_rejected}|constraint_rejected={result.constraint_rejected}|records={result.final_records}|status={result.final_card_status}|elapsed_ms={result.elapsed_ms}|consistent={result.consistent}")
                if not result.consistent:
                    raise RuntimeError(f"同卡竞争轮次验证失败：{strategy}/{load}")
        json_path, csv_path = save_results(result_dir, rounds)
        cleanup_p9(control, context)
        context = None
        if p9_residue_count(control) != 0:
            raise RuntimeError("阶段9清理后仍有P9残留")
        verify_protected_baseline(control)
        print(f"PASS|12轮并发实验|{len(rounds)}")
        print("PASS|P9最终残留|0")
        print(f"PASS|结果文件|{json_path}|{csv_path}")
        print("最终状态：PASS")
        return 0
    finally:
        if context is not None:
            try:
                cleanup_p9(control, context)
                print("RECOVERY|已清理本次创建的P9对象")
            except Exception as exc:
                print(f"RECOVERY_FAIL|{type(exc).__name__}|请保留日志并停止重试")
        control.close()


if __name__ == "__main__":
    try:
        code = run()
    except KeyboardInterrupt:
        print("最终状态：FAIL｜用户中断")
        raise
    except Exception as exc:
        print(f"最终状态：FAIL｜{type(exc).__name__}｜{exc}")
        raise SystemExit(1)
    raise SystemExit(code)
