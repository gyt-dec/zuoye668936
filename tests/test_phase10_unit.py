"""阶段10不连接数据库的备份、恢复与安全测试。"""
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path

from src.phase10_ddl_backup_restore import (
    TABLE_ORDER, canonical_rows, cleanup_after_verified_restore, file_sha256,
    load_backup_file, rows_hash, secure_write, validate_snapshot,
)


def sample_snapshot():
    tables={
        "app_user":[{"user_id":101,"login_name":"p10","password_hash":"hash","registered_at":"2026-01-01 00:00:00","user_status":"ACTIVE","display_name":"x"}],
        "owner":[{"owner_id":201,"owner_name":"o","contact_info":None}],
        "mobile_number":[{"mobile_id":301,"owner_id":201,"phone_number":"1","number_status":"ACTIVE","registered_at":None}],
        "purchase_order":[{"order_id":401,"user_id":101},{"order_id":402,"user_id":101}],
        "order_item":[{"item_id":501,"order_id":401},{"item_id":502,"order_id":402}],
        "recharge_card":[{"card_id":601,"item_id":501},{"card_id":602,"item_id":502}],
        "recharge_record":[{"recharge_id":701,"card_id":601,"mobile_id":301}],
    }
    return {"table_count":7,"tables":tables,"counts":{k:len(v) for k,v in tables.items()},"table_sha256":{k:rows_hash(v) for k,v in tables.items()}}


class Phase10UnitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root=Path(__file__).parents[1]
        cls.source=root.joinpath("src/phase10_ddl_backup_restore.py").read_text(encoding="utf-8")
        cls.shell=root.joinpath("scripts/run_phase10_ddl_backup_restore.sh").read_text(encoding="utf-8")

    def test_secure_files_are_mode_600_and_hashable(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"backup.json"; secure_write(path,'{"ok":true}')
            self.assertEqual(stat.S_IMODE(path.stat().st_mode),0o600)
            self.assertEqual(len(file_sha256(path)),64)

    def write_test_backup(self, directory, snapshot=None):
        snapshot = snapshot or sample_snapshot()
        path=Path(directory)/"backup.json"
        secure_write(path,json.dumps(snapshot,ensure_ascii=False,sort_keys=True))
        manifest={"backup_sha256":file_sha256(path),"table_sha256":snapshot["table_sha256"]}
        return path,manifest,snapshot

    def test_real_backup_file_is_independently_loaded(self):
        with tempfile.TemporaryDirectory() as directory:
            path,manifest,snapshot=self.write_test_backup(directory)
            loaded=load_backup_file(path,manifest)
            self.assertEqual(loaded["tables"],snapshot["tables"])
            self.assertEqual(loaded["table_sha256"],snapshot["table_sha256"])

    def test_corrupted_backup_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path,manifest,_=self.write_test_backup(directory)
            secure_write(path,path.read_text(encoding="utf-8")+"\ncorrupt")
            with self.assertRaises(RuntimeError): load_backup_file(path,manifest)

    def test_manifest_hash_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path,manifest,_=self.write_test_backup(directory)
            manifest["backup_sha256"]="0"*64
            with self.assertRaises(RuntimeError): load_backup_file(path,manifest)

    def test_canonical_hash_is_deterministic(self):
        one=[{"id":1,"amount":"10.00"}]; two=[{"amount":"10.00","id":1}]
        self.assertEqual(canonical_rows(one),canonical_rows(two)); self.assertEqual(rows_hash(one),rows_hash(two))

    def test_snapshot_covers_one_consistent_seven_table_transaction(self):
        snapshot=sample_snapshot(); validate_snapshot(snapshot)
        self.assertEqual(tuple(snapshot["tables"]),TABLE_ORDER)
        self.assertIn("START TRANSACTION WITH CONSISTENT SNAPSHOT",self.source)
        self.assertIn("REPEATABLE READ",self.source)

    def test_bad_foreign_keys_are_rejected(self):
        snapshot=sample_snapshot(); snapshot["tables"]["recharge_record"][0]["card_id"]=999
        with self.assertRaises(RuntimeError): validate_snapshot(snapshot)

    def test_original_ids_are_explicitly_restored(self):
        self.assertIn("INSERT INTO {table} ({','.join(columns)})",self.source)
        self.assertIn('row=dict(original)',self.source)
        self.assertNotIn("lastrowid",self.source[self.source.index("def restore_snapshot"):])

    def test_cleanup_requires_matching_restore_hashes(self):
        class NeverCalled: pass
        before=sample_snapshot(); after=sample_snapshot(); after["table_sha256"]=dict(after["table_sha256"]); after["table_sha256"]["app_user"]="bad"
        with self.assertRaises(RuntimeError): cleanup_after_verified_restore(NeverCalled(),{},after,before)

    def test_restore_failure_path_does_not_automatically_cleanup(self):
        run_source=self.source[self.source.index("def run()") :]
        restore_pos=run_source.index("restore_snapshot(control,disk_backup)")
        cleanup_pos=run_source.index("cleanup_after_verified_restore",restore_pos)
        self.assertLess(restore_pos,cleanup_pos)
        self.assertNotIn("finally: cleanup",run_source)

    def test_ddl_activity_records_success_failure_errors_and_max_latency(self):
        for marker in ('"success"','"failure"','"max_ms"','"errors"'):
            self.assertIn(marker,self.source)

    def test_summary_keeps_full_structure_and_validation_snapshots(self):
        for marker in ("ddl_structure_before","ddl_structure_after","baseline_before","baseline_after","backup_table_sha256"):
            self.assertIn(marker,self.source)

    def test_failure_preserves_scene_and_no_destructive_core_operations(self):
        self.assertNotIn("DROP TABLE",self.source.upper()); self.assertNotIn("TRUNCATE",self.source.upper())
        self.assertNotIn("DROP INDEX",self.source.upper()); self.assertNotIn("DROP TRIGGER",self.source.upper())
        self.assertIn("禁止自动继续或清理",self.source)

    def test_password_hidden_and_backup_ignored(self):
        self.assertIn("read -r -s",self.shell); self.assertIn("chmod 600",self.shell); self.assertNotIn("-p${",self.shell)
        ignore=Path(__file__).parents[1].joinpath(".gitignore").read_text(encoding="utf-8")
        self.assertIn("results/phase10/backup/",ignore)


if __name__=="__main__": unittest.main()
