#!/usr/bin/env python3
"""阶段10：在线DDL、数据校验及真实逻辑备份/删除/恢复。"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import stat
import threading
import time
from collections import Counter
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from src.db import connect
from src.db_config import load_database_config
from src.phase7_large_data import marker_counts, recovery_business_anomalies
from src.phase8_index_performance import INDEXES, index_metadata
from src.phase9_concurrency import p9_residue_count
from src.services.integrity_service import EXPECTED_P4, p4_counts, p5_object_counts, p6_residue_count, scalar, table_count

EXPECTED_P7 = {"app_user":100000,"owner":100000,"mobile_number":100000,"purchase_order":100000,"order_item":100000,"recharge_card":120000,"recharge_record":100000}
P10_USER = "p10_user_recovery"
P10_OWNER = "P10_OWNER_RECOVERY"
P10_PHONE = "197000000001"
P10_HASH = "p10$logical-backup$not-a-real-credential"
P10_ORDER_PREFIX = "P10-ORDER-"
P10_CARD_PREFIX = "P10-CARD-"
TABLE_ORDER = ("app_user","owner","mobile_number","purchase_order","order_item","recharge_card","recharge_record")


def secure_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
    finally:
        os.chmod(path, 0o600)


def require_mode_600(path: Path) -> None:
    if stat.S_IMODE(path.stat().st_mode) != 0o600:
        raise RuntimeError(f"文件权限不是600：{path}")


def json_value(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat(sep=" ")
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return value


def canonical_rows(rows: list[dict]) -> str:
    normalized = [{key: json_value(value) for key, value in row.items()} for row in rows]
    return json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def rows_hash(rows: list[dict]) -> str:
    return hashlib.sha256(canonical_rows(rows).encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def error_code(exc: Exception) -> str:
    return str(exc.args[0]) if exc.args and isinstance(exc.args[0], (int, str)) else type(exc).__name__


def column_definition(connection):
    with connection.cursor() as cursor:
        cursor.execute("""SELECT COLUMN_NAME,COLUMN_TYPE,IS_NULLABLE,COLUMN_DEFAULT,COLUMN_COMMENT,ORDINAL_POSITION
                          FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE()
                          AND TABLE_NAME='recharge_record' ORDER BY ORDINAL_POSITION""")
        return [{key: json_value(value) for key, value in row.items()} for row in cursor.fetchall()]


def source_column_exists(connection) -> bool:
    return int(scalar(connection, "SELECT COUNT(*) value FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='recharge_record' AND COLUMN_NAME='recharge_source'")) == 1


def p10_residue_count(connection) -> int:
    return int(scalar(connection, """SELECT
      (SELECT COUNT(*) FROM app_user WHERE login_name=%s)+
      (SELECT COUNT(*) FROM owner WHERE owner_name=%s)+
      (SELECT COUNT(*) FROM mobile_number WHERE phone_number=%s)+
      (SELECT COUNT(*) FROM purchase_order WHERE LEFT(order_no,%s)=%s)+
      (SELECT COUNT(*) FROM order_item oi JOIN purchase_order po ON po.order_id=oi.order_id WHERE LEFT(po.order_no,%s)=%s)+
      (SELECT COUNT(*) FROM recharge_card WHERE LEFT(card_no,%s)=%s)+
      (SELECT COUNT(*) FROM recharge_record rr JOIN recharge_card rc ON rc.card_id=rr.card_id WHERE LEFT(rc.card_no,%s)=%s) value""",
      (P10_USER,P10_OWNER,P10_PHONE,len(P10_ORDER_PREFIX),P10_ORDER_PREFIX,len(P10_ORDER_PREFIX),P10_ORDER_PREFIX,len(P10_CARD_PREFIX),P10_CARD_PREFIX,len(P10_CARD_PREFIX),P10_CARD_PREFIX)))


def protected_snapshot(connection) -> dict:
    return {
        "table_count": table_count(connection),
        "p4_counts": p4_counts(connection),
        "p5_objects": p5_object_counts(connection),
        "p6_residue": p6_residue_count(connection),
        "p7_counts": marker_counts(connection),
        "p7_anomalies": recovery_business_anomalies(connection),
        "p8_indexes": {name:[table,list(columns)] for name,(table,columns) in index_metadata(connection).items()},
        "p9_residue": p9_residue_count(connection),
    }


def verify_protected_baseline(connection) -> dict:
    snapshot = protected_snapshot(connection)
    if snapshot["table_count"] != 7 or snapshot["p4_counts"] != EXPECTED_P4 or snapshot["p5_objects"] != "2,2" or snapshot["p6_residue"] != 0:
        raise RuntimeError("阶段3至6保护基线改变")
    if snapshot["p7_counts"] != EXPECTED_P7 or any(snapshot["p7_anomalies"].values()):
        raise RuntimeError("阶段7数量或业务关系异常")
    expected_indexes={name:[table,list(columns)] for name,(table,columns) in INDEXES.items()}
    if snapshot["p8_indexes"] != expected_indexes or snapshot["p9_residue"] != 0:
        raise RuntimeError("阶段8索引或阶段9清理状态异常")
    return snapshot


def setup_p10(connection) -> dict:
    context = {"user_id":None,"owner_id":None,"mobile_id":None,"order_ids":[],"item_ids":[],"card_ids":[],"record_ids":[]}
    connection.begin()
    try:
        with connection.cursor() as cursor:
            cursor.execute("INSERT INTO app_user(login_name,password_hash,registered_at,user_status,display_name) VALUES(%s,%s,'2026-11-09 20:00:00','ACTIVE','P10恢复用户')", (P10_USER,P10_HASH)); context["user_id"]=int(cursor.lastrowid)
            cursor.execute("INSERT INTO owner(owner_name,contact_info) VALUES(%s,'p10@example.test')", (P10_OWNER,)); context["owner_id"]=int(cursor.lastrowid)
            cursor.execute("INSERT INTO mobile_number(owner_id,phone_number,number_status,registered_at) VALUES(%s,%s,'ACTIVE','2026-11-09 20:00:00')", (context["owner_id"],P10_PHONE)); context["mobile_id"]=int(cursor.lastrowid)
            for seq in (1,2):
                cursor.execute("INSERT INTO purchase_order(user_id,order_no,created_at,order_status,total_amount,completed_at) VALUES(%s,%s,'2026-11-09 20:00:00','COMPLETED',%s,'2026-11-09 20:00:00')", (context["user_id"],f"{P10_ORDER_PREFIX}{seq}",Decimal(seq*10))); context["order_ids"].append(int(cursor.lastrowid))
                cursor.execute("INSERT INTO order_item(order_id,denomination,quantity) VALUES(%s,%s,1)", (context["order_ids"][-1],Decimal(seq*10))); context["item_ids"].append(int(cursor.lastrowid))
                cursor.execute("INSERT INTO recharge_card(item_id,card_no,password_hash,face_value,card_status,created_at,used_at) VALUES(%s,%s,%s,%s,'UNUSED','2026-11-09 20:00:00',NULL)", (context["item_ids"][-1],f"{P10_CARD_PREFIX}{seq}",P10_HASH,Decimal(seq*10))); context["card_ids"].append(int(cursor.lastrowid))
            cursor.execute("INSERT INTO recharge_record(card_id,mobile_id,recharge_amount,recharged_at) VALUES(%s,%s,10.00,'2026-11-09 20:01:00')", (context["card_ids"][0],context["mobile_id"])); context["record_ids"].append(int(cursor.lastrowid))
        connection.commit(); return context
    except BaseException:
        connection.rollback(); raise


class ActivityMonitor:
    def __init__(self):
        self.lock=threading.Lock(); self.stop=threading.Event(); self.started=threading.Barrier(3)
        self.data={"select":{"success":0,"failure":0,"max_ms":0.0,"errors":Counter()},"update":{"success":0,"failure":0,"max_ms":0.0,"errors":Counter()}}

    def record(self, kind, elapsed, exc=None):
        with self.lock:
            bucket=self.data[kind]; bucket["max_ms"]=max(bucket["max_ms"],elapsed)
            if exc is None: bucket["success"]+=1
            else: bucket["failure"]+=1; bucket["errors"][error_code(exc)]+=1

    def result(self):
        with self.lock:
            return {kind:{"success":v["success"],"failure":v["failure"],"max_ms":round(v["max_ms"],3),"errors":dict(v["errors"])} for kind,v in self.data.items()}


def activity_worker(config, monitor, kind, record_id):
    connection=connect(config,autocommit=(kind=="select")); monitor.started.wait(timeout=20)
    try:
        while not monitor.stop.is_set():
            started=time.perf_counter(); exc=None
            try:
                with connection.cursor() as cursor:
                    if kind=="select": cursor.execute("SELECT COUNT(*) c FROM recharge_record"); cursor.fetchone()
                    else:
                        connection.begin(); cursor.execute("UPDATE recharge_record SET recharge_amount=recharge_amount WHERE recharge_id=%s",(record_id,)); connection.commit()
            except Exception as error:
                exc=error
                if kind=="update": connection.rollback()
            monitor.record(kind,(time.perf_counter()-started)*1000,exc)
    finally: connection.close()


def run_online_ddl(config, control, record_id):
    monitor=ActivityMonitor()
    threads=[threading.Thread(target=activity_worker,args=(config,monitor,kind,record_id),daemon=True) for kind in ("select","update")]
    for thread in threads: thread.start()
    monitor.started.wait(timeout=20); time.sleep(0.2)
    started=time.perf_counter()
    try:
        with control.cursor() as cursor:
            cursor.execute("ALTER TABLE recharge_record ADD COLUMN recharge_source VARCHAR(16) NULL COMMENT '充值来源，阶段10在线结构变更实验'")
    finally:
        ddl_ms=(time.perf_counter()-started)*1000; monitor.stop.set()
        for thread in threads: thread.join(timeout=40)
    result=monitor.result(); result["ddl_elapsed_ms"]=round(ddl_ms,3)
    if any(thread.is_alive() for thread in threads): raise RuntimeError("DDL监控线程未正常结束")
    if result["select"]["success"]==0 or result["update"]["success"]==0: raise RuntimeError(f"DDL期间未取得并发读写成功证据：{result}")
    return result


def select_rows(cursor, sql, params):
    cursor.execute(sql,params); return list(cursor.fetchall())


def export_consistent_snapshot(connection, context) -> dict:
    """七表必须在同一个一致性读事务中导出。"""
    connection.rollback()
    with connection.cursor() as cursor:
        cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        cursor.execute("START TRANSACTION WITH CONSISTENT SNAPSHOT")
    started=datetime.now().isoformat(sep=" ")
    try:
        with connection.cursor() as cursor:
            marks=lambda values: ",".join(["%s"]*len(values))
            tables={
                "app_user":select_rows(cursor,"SELECT * FROM app_user WHERE user_id=%s ORDER BY user_id",(context["user_id"],)),
                "owner":select_rows(cursor,"SELECT * FROM owner WHERE owner_id=%s ORDER BY owner_id",(context["owner_id"],)),
                "mobile_number":select_rows(cursor,"SELECT * FROM mobile_number WHERE mobile_id=%s ORDER BY mobile_id",(context["mobile_id"],)),
                "purchase_order":select_rows(cursor,f"SELECT * FROM purchase_order WHERE order_id IN ({marks(context['order_ids'])}) ORDER BY order_id",tuple(context["order_ids"])),
                "order_item":select_rows(cursor,f"SELECT * FROM order_item WHERE item_id IN ({marks(context['item_ids'])}) ORDER BY item_id",tuple(context["item_ids"])),
                "recharge_card":select_rows(cursor,f"SELECT * FROM recharge_card WHERE card_id IN ({marks(context['card_ids'])}) ORDER BY card_id",tuple(context["card_ids"])),
                "recharge_record":select_rows(cursor,f"SELECT * FROM recharge_record WHERE recharge_id IN ({marks(context['record_ids'])}) ORDER BY recharge_id",tuple(context["record_ids"])),
            }
        connection.commit()
    except BaseException:
        connection.rollback(); raise
    normalized={name:json.loads(canonical_rows(rows)) for name,rows in tables.items()}
    return {"snapshot_started_at":started,"transaction":"REPEATABLE READ / WITH CONSISTENT SNAPSHOT","table_count":7,"tables":normalized,"counts":{k:len(v) for k,v in normalized.items()},"table_sha256":{k:rows_hash(v) for k,v in normalized.items()}}


def validate_snapshot(snapshot):
    if set(snapshot["tables"].keys()) != set(TABLE_ORDER) or snapshot["table_count"] != 7: raise RuntimeError("备份未覆盖七张表")
    expected={"app_user":1,"owner":1,"mobile_number":1,"purchase_order":2,"order_item":2,"recharge_card":2,"recharge_record":1}
    if snapshot["counts"] != expected: raise RuntimeError(f"P10备份数量错误：{snapshot['counts']}")
    rows={name:{tuple(row.values()) for row in values} for name,values in snapshot["tables"].items()}
    # ID/FK集合显式校验，确保恢复关系不是重新生成。
    users={r["user_id"] for r in snapshot["tables"]["app_user"]}; owners={r["owner_id"] for r in snapshot["tables"]["owner"]}
    orders={r["order_id"] for r in snapshot["tables"]["purchase_order"]}; items={r["item_id"] for r in snapshot["tables"]["order_item"]}; cards={r["card_id"] for r in snapshot["tables"]["recharge_card"]}; mobiles={r["mobile_id"] for r in snapshot["tables"]["mobile_number"]}
    if any(r["user_id"] not in users for r in snapshot["tables"]["purchase_order"]): raise RuntimeError("备份订单外键错误")
    if any(r["owner_id"] not in owners for r in snapshot["tables"]["mobile_number"]): raise RuntimeError("备份手机号外键错误")
    if any(r["order_id"] not in orders for r in snapshot["tables"]["order_item"]): raise RuntimeError("备份明细外键错误")
    if any(r["item_id"] not in items for r in snapshot["tables"]["recharge_card"]): raise RuntimeError("备份卡外键错误")
    if any(r["card_id"] not in cards or r["mobile_id"] not in mobiles for r in snapshot["tables"]["recharge_record"]): raise RuntimeError("备份充值外键错误")
    return rows


def write_backup(result_dir, snapshot):
    stamp=datetime.now().strftime("%Y%m%d_%H%M%S"); backup_dir=result_dir/"backup"
    backup_path=backup_dir/f"phase10_logical_backup_{stamp}.json"
    content=json.dumps(snapshot,ensure_ascii=False,indent=2,sort_keys=True); secure_write(backup_path,content)
    digest=file_sha256(backup_path)
    manifest={"backup_file":backup_path.name,"backup_time":datetime.now().isoformat(sep=" "),"table_count":7,"counts":snapshot["counts"],"table_sha256":snapshot["table_sha256"],"backup_sha256":digest,"size_bytes":backup_path.stat().st_size}
    manifest_path=backup_dir/f"phase10_backup_manifest_{stamp}.json"; secure_write(manifest_path,json.dumps(manifest,ensure_ascii=False,indent=2,sort_keys=True))
    require_mode_600(backup_path); require_mode_600(manifest_path)
    return backup_path,manifest_path,manifest


def load_backup_file(backup_path: Path, manifest: dict) -> dict:
    """从真实JSON文件独立加载，并同时核对整文件及逐表摘要。"""
    require_mode_600(backup_path)
    actual_file_hash = file_sha256(backup_path)
    if actual_file_hash != manifest.get("backup_sha256"):
        raise RuntimeError("备份文件SHA-256与manifest不一致，拒绝恢复")
    with backup_path.open("r", encoding="utf-8") as handle:
        snapshot = json.load(handle)
    validate_snapshot(snapshot)
    actual_table_hashes = {
        table: rows_hash(snapshot["tables"][table]) for table in TABLE_ORDER
    }
    if snapshot.get("table_sha256") != actual_table_hashes:
        raise RuntimeError("备份文件内的表级SHA-256与数据不一致，拒绝恢复")
    if manifest.get("table_sha256") != actual_table_hashes:
        raise RuntimeError("备份表级SHA-256与manifest不一致，拒绝恢复")
    return snapshot


def delete_p10(connection, context):
    connection.begin()
    try:
        with connection.cursor() as cursor:
            for table,key,values in (("recharge_record","recharge_id",context["record_ids"]),("recharge_card","card_id",context["card_ids"]),("order_item","item_id",context["item_ids"]),("purchase_order","order_id",context["order_ids"]),("mobile_number","mobile_id",[context["mobile_id"]]),("owner","owner_id",[context["owner_id"]]),("app_user","user_id",[context["user_id"]])):
                marks=",".join(["%s"]*len(values)); cursor.execute(f"DELETE FROM {table} WHERE {key} IN ({marks})",tuple(values))
        connection.commit()
    except BaseException: connection.rollback(); raise


def insert_row(cursor, table, row):
    columns=list(row); marks=",".join(["%s"]*len(columns)); cursor.execute(f"INSERT INTO {table} ({','.join(columns)}) VALUES ({marks})",tuple(row[c] for c in columns))


def restore_snapshot(connection, snapshot):
    connection.begin()
    try:
        with connection.cursor() as cursor:
            for table in ("app_user","owner","mobile_number","purchase_order","order_item"):
                for row in snapshot["tables"][table]: insert_row(cursor,table,row)
            for original in snapshot["tables"]["recharge_card"]:
                row=dict(original)
                if row["card_status"]=="USED": row["card_status"]="UNUSED"; row["used_at"]=None
                insert_row(cursor,"recharge_card",row)
            for row in snapshot["tables"]["recharge_record"]: insert_row(cursor,"recharge_record",row)
        connection.commit()
    except BaseException: connection.rollback(); raise


def cleanup_after_verified_restore(connection, context, restored_snapshot, backup_snapshot):
    if restored_snapshot["counts"] != backup_snapshot["counts"] or restored_snapshot["table_sha256"] != backup_snapshot["table_sha256"]:
        raise RuntimeError("恢复校验未通过，保留P10故障现场，禁止清理")
    delete_p10(connection,context)


def save_summary(result_dir, summary):
    stamp=datetime.now().strftime("%Y%m%d_%H%M%S"); json_path=result_dir/f"phase10_summary_{stamp}.json"; csv_path=result_dir/f"phase10_validation_{stamp}.csv"
    secure_write(json_path,json.dumps(summary,ensure_ascii=False,indent=2,sort_keys=True))
    descriptor=os.open(csv_path,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    with os.fdopen(descriptor,"w",newline="",encoding="utf-8-sig") as handle:
        writer=csv.writer(handle); writer.writerow(["check","result"])
        for key,value in summary["checks"].items(): writer.writerow([key,json.dumps(value,ensure_ascii=False,sort_keys=True)])
    os.chmod(csv_path,0o600); return json_path,csv_path


def run():
    config=load_database_config(); result_dir=Path(os.environ.get("P10_RESULT_DIR","results/phase10")); result_dir.mkdir(parents=True,exist_ok=True)
    state_path=result_dir/"phase10_state.json"; control=connect(config,autocommit=True)
    try:
        baseline_before=verify_protected_baseline(control)
        if state_path.exists():
            require_mode_600(state_path); state=json.loads(state_path.read_text(encoding="utf-8"))
            if state.get("status")=="complete" and source_column_exists(control) and p10_residue_count(control)==0:
                print("PASS|阶段10已完成状态复核|complete"); return 0
            raise RuntimeError("发现未完成阶段10状态；保留备份和P10现场，禁止自动继续或清理")
        if source_column_exists(control) or p10_residue_count(control)!=0: raise RuntimeError("字段或P10数据已存在但无可信状态文件，停止")
        pre_columns=column_definition(control); context=setup_p10(control)
        secure_write(state_path,json.dumps({"status":"setup","context":context},ensure_ascii=False,indent=2)); require_mode_600(state_path)
        ddl_metrics=run_online_ddl(config,control,context["record_ids"][0])
        if not source_column_exists(control): raise RuntimeError("DDL结束后未找到recharge_source")
        with control.cursor() as cursor: cursor.execute("UPDATE recharge_record SET recharge_source='P10_TEST' WHERE recharge_id=%s",(context["record_ids"][0],))
        post_columns=column_definition(control); verify_protected_baseline(control)
        state={"status":"ddl_complete","context":context,"ddl_metrics":ddl_metrics}; secure_write(state_path,json.dumps(state,ensure_ascii=False,indent=2))
        backup_connection=connect(config,autocommit=False)
        try: backup=export_consistent_snapshot(backup_connection,context)
        finally: backup_connection.close()
        validate_snapshot(backup); backup_path,manifest_path,manifest=write_backup(result_dir,backup)
        # 后续比较、删除和恢复只使用从真实备份文件重新加载的对象。
        disk_backup=load_backup_file(backup_path,manifest)
        state.update({"status":"backup_complete","backup":str(backup_path),"manifest":str(manifest_path),"backup_sha256":manifest["backup_sha256"]}); secure_write(state_path,json.dumps(state,ensure_ascii=False,indent=2))
        current_connection=connect(config,autocommit=False)
        try: current=export_consistent_snapshot(current_connection,context)
        finally: current_connection.close()
        if current["table_sha256"]!=disk_backup["table_sha256"]: raise RuntimeError("删除前数据库快照与备份不一致")
        delete_p10(control,context)
        if p10_residue_count(control)!=0: raise RuntimeError("模拟误删除后P10仍有残留")
        # 删除后再次从磁盘读取并验证，避免使用删除前保留的内存副本恢复。
        disk_backup=load_backup_file(backup_path,manifest)
        restore_snapshot(control,disk_backup)
        restored_connection=connect(config,autocommit=False)
        try: restored=export_consistent_snapshot(restored_connection,context)
        finally: restored_connection.close()
        validate_snapshot(restored)
        cleanup_after_verified_restore(control,context,restored,disk_backup)
        if p10_residue_count(control)!=0: raise RuntimeError("验证后清理仍有P10残留")
        baseline_after=verify_protected_baseline(control)
        summary={"status":"PASS","checks":{"ddl_structure_before":pre_columns,"ddl_structure_after":post_columns,"ddl_activity":ddl_metrics,"baseline_before":baseline_before,"baseline_after":baseline_after,"backup_transaction":backup["transaction"],"backup_snapshot_started_at":backup["snapshot_started_at"],"backup_counts":backup["counts"],"backup_table_sha256":backup["table_sha256"],"backup_sha256":manifest["backup_sha256"],"backup_size_bytes":manifest["size_bytes"],"delete_residue":0,"restore_hash_equal":True,"final_p10_residue":0},"artifacts":{"backup":str(backup_path),"manifest":str(manifest_path)}}
        json_path,csv_path=save_summary(result_dir,summary)
        secure_write(state_path,json.dumps({"status":"complete","summary":str(json_path),"backup":str(backup_path),"manifest":str(manifest_path)},ensure_ascii=False,indent=2))
        print(f"PASS|在线DDL并发访问|{ddl_metrics}")
        print(f"PASS|七表一致性快照备份|sha256={manifest['backup_sha256']}|size={manifest['size_bytes']}")
        print("PASS|误删除后真实恢复|主键、外键、行数和SHA-256一致")
        print("PASS|P10最终残留|0")
        print(f"PASS|结果文件|{json_path}|{csv_path}|{backup_path}|{manifest_path}")
        print("最终状态：PASS"); return 0
    finally: control.close()


if __name__=="__main__":
    try: code=run()
    except KeyboardInterrupt: print("最终状态：FAIL｜用户中断"); raise
    except Exception as exc: print(f"最终状态：FAIL｜{type(exc).__name__}｜{exc}"); raise SystemExit(1)
    raise SystemExit(code)
