"""阶段7不连接数据库的生成、恢复和安全测试。"""

from __future__ import annotations

import unittest
import json
import os
import tempfile
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import src.phase7_large_data as phase7
from src.phase7_large_data import (
    BATCH_SIZE,
    batch_ranges,
    card_range_for_order,
    denomination_for_order,
    execute_batch,
    expected_card_count,
    order_for_card,
    owner_row,
    phone_for_seq,
    quantity_for_order,
    require_no_anomalies,
    estimate_full_space,
    pilot_resume_action,
    reject_performance_indexes,
    validate_saved_estimate,
    validate_view_counts,
    user_row,
    validate_prefix_stats,
    cleanup_item_is_expected,
    cleanup_record_is_expected,
)


class BatchCursor:
    def __init__(self, fail=False):
        self.fail = fail

    def __enter__(self): return self
    def __exit__(self, *args): return False
    def executemany(self, sql, rows):
        if self.fail:
            raise RuntimeError("expected batch failure")


class BatchConnection:
    def __init__(self, fail=False):
        self.fail = fail
        self.events = []

    def begin(self): self.events.append("begin")
    def commit(self): self.events.append("commit")
    def rollback(self): self.events.append("rollback")
    def cursor(self): return BatchCursor(self.fail)


class GenerationTests(unittest.TestCase):
    def test_deterministic_generation(self):
        self.assertEqual(user_row(1), user_row(1))
        self.assertEqual(owner_row(100000), owner_row(100000))
        self.assertEqual(phone_for_seq(1), "198700000001")
        self.assertEqual(denomination_for_order(1), Decimal("10.00"))

    def test_card_and_order_distribution(self):
        self.assertEqual(quantity_for_order(20000), 2)
        self.assertEqual(quantity_for_order(20001), 1)
        self.assertEqual(expected_card_count(100000), 120000)
        self.assertEqual(card_range_for_order(1), (1, 2))
        self.assertEqual(order_for_card(40001), 20001)
        self.assertEqual(order_for_card(120000), 100000)

    def test_order_amount_item_and_card_value_formula(self):
        for seq in (1, 20000, 20001, 100000):
            denomination = denomination_for_order(seq)
            total = denomination * quantity_for_order(seq)
            self.assertEqual(total / quantity_for_order(seq), denomination)


class BatchAndRecoveryTests(unittest.TestCase):
    def test_default_500_batch_boundaries(self):
        self.assertEqual(BATCH_SIZE, 500)
        self.assertEqual(list(batch_ranges(1, 1001)), [(1, 500), (501, 1000), (1001, 1001)])

    def test_complete_prefix_resume(self):
        self.assertEqual(validate_prefix_stats("orders", 1000, 1, 1000, 1000, 100000), 1000)

    def test_prefix_hole_is_rejected(self):
        with self.assertRaises(RuntimeError):
            validate_prefix_stats("orders", 999, 1, 1000, 999, 100000)

    def test_failed_batch_rolls_back(self):
        connection = BatchConnection(fail=True)
        with self.assertRaises(RuntimeError):
            execute_batch(connection, "test", "INSERT", [(1,)])
        self.assertEqual(connection.events, ["begin", "rollback"])

    def test_parent_child_anomaly_is_rejected(self):
        require_no_anomalies("relations", {"mobile_parent": 0, "order_parent": 0})
        with self.assertRaises(RuntimeError):
            require_no_anomalies("relations", {"mobile_parent": 1})


class StaticSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).parents[1]
        cls.python_source = (root / "src/phase7_large_data.py").read_text(encoding="utf-8")
        cls.shell_source = (root / "scripts/run_phase7_large_data.sh").read_text(encoding="utf-8")

    def test_seven_table_insert_order(self):
        labels = ['"app_user"', '"owner"', '"mobile_number"', '"purchase_order"', '"order_item"', '"recharge_card"', '"recharge_record"']
        positions = [self.python_source.index(label, self.python_source.index("def insert_to_target")) for label in labels]
        self.assertEqual(positions, sorted(positions))

    def test_parent_child_amount_and_state_validation_present(self):
        for marker in ("one_item", "card_quantity", "order_amount", "card_amount", "record_relation", "used_state", "duplicate_record"):
            self.assertIn(f'"{marker}"', self.python_source)

    def test_cleanup_is_scoped_and_confirmed(self):
        self.assertIn("DELETE P7 DATA", self.python_source)
        self.assertIn("--cleanup", self.shell_source)
        self.assertNotIn("TRUNCATE", self.python_source.upper())
        self.assertNotIn("DROP TABLE", self.python_source.upper())
        self.assertIn('("recharge_record"', self.python_source)
        self.assertIn('("app_user"', self.python_source)

    def test_password_is_not_logged_or_command_argument(self):
        self.assertIn("read -r -s", self.shell_source)
        self.assertIn("chmod 600", self.shell_source)
        self.assertNotIn("-p${", self.shell_source)
        self.assertNotIn("echo \"${database_password}", self.shell_source)

    def test_resource_probe_and_no_resource_mutation(self):
        self.assertIn("GV$OB_SERVERS", self.python_source)
        for forbidden in ("memory_limit=", "ALTER SYSTEM", "resource_hard_limit="):
            self.assertNotIn(forbidden, self.python_source)

    def test_pilot_space_shortage_blocks_full_insert(self):
        gib = 1024**3
        before = {"data_used": gib, "data_filesystem_free": 10*gib, "data_capacity": 8*gib, "log_capacity": 4*gib, "log_used": gib}
        after = {"data_used": int(1.1*gib), "data_filesystem_free": int(9.9*gib), "data_capacity": 8*gib, "log_capacity": 4*gib, "log_used": gib}
        with self.assertRaises(RuntimeError):
            estimate_full_space(before, after)

    def test_space_estimation_failure_stops(self):
        snapshot = {"data_used": 100, "data_filesystem_free": 1000, "data_capacity": 10000, "log_capacity": 10000, "log_used": 1}
        with self.assertRaises(RuntimeError):
            estimate_full_space(snapshot, dict(snapshot))

    def test_used_at_must_equal_recharged_at(self):
        self.assertIn("rc.used_at<>rr.recharged_at", self.python_source)

    def test_cleanup_branch_precedes_normal_data_threshold(self):
        run_source = self.python_source[self.python_source.index("def run(cleanup_mode") :]
        self.assertLess(run_source.index("if cleanup_mode"), run_source.index("resource_before = resource_snapshot"))
        self.assertIn("enforce_data=False", run_source)

    def test_view_counts(self):
        validate_view_counts(120000, 100000, 100000)
        with self.assertRaises(RuntimeError):
            validate_view_counts(119999, 100000, 100000)

    def test_performance_index_is_rejected(self):
        reject_performance_indexes({"PRIMARY", "uk_recharge_card_no"})
        with self.assertRaises(RuntimeError):
            reject_performance_indexes({"PRIMARY", "idx_card_status_created"})

    def test_recovery_checks_internal_relationships(self):
        self.assertIn("recovery_business_anomalies", self.python_source)
        for marker in ("mobile_sequence", "order_sequence", "card_sequence", "record_sequence"):
            self.assertIn(marker, self.python_source)

    def test_cleanup_rejects_non_p7_children(self):
        self.assertIn("cleanup_inbound_anomalies", self.python_source)
        self.assertIn("non_p7_mobile_to_p7_owner", self.python_source)

    def test_resume_space_shortage_and_missing_fields_stop(self):
        gib = 1024**3
        snapshot = {"data_used": 6*gib, "data_filesystem_free": 3*gib, "data_capacity": 8*gib, "log_capacity": 4*gib, "log_used": gib}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "estimate.json"
            old = os.environ.get("P7_ESTIMATE_FILE")
            os.environ["P7_ESTIMATE_FILE"] = str(path)
            try:
                path.write_text(json.dumps({"per_group_data": 1000000, "per_group_filesystem": 1000000}))
                with self.assertRaises(RuntimeError): validate_saved_estimate(snapshot, 1000)
                path.write_text(json.dumps({"per_group_data": 1}))
                with self.assertRaises(RuntimeError): validate_saved_estimate(snapshot, 1000)
            finally:
                if old is None: os.environ.pop("P7_ESTIMATE_FILE", None)
                else: os.environ["P7_ESTIMATE_FILE"] = old

    def test_completed_pilot_reuses_estimate_or_stops_if_missing(self):
        counts = {"app_user":1000,"owner":1000,"mobile_number":1000,"purchase_order":1000,"order_item":1000,"recharge_card":2000,"recharge_record":1000}
        self.assertEqual(pilot_resume_action(counts, True), "reuse_pilot")
        with self.assertRaises(RuntimeError): pilot_resume_action(counts, False)

    def test_exact_prefix_predicates_and_cleanup_guards(self):
        self.assertNotIn(" LIKE ", self.python_source)
        self.assertIn("LEFT(login_name,8)=%s", self.python_source)
        self.assertIn("non_p7_item_to_p7_order", self.python_source)
        self.assertIn("non_p7_record_to_p7_card", self.python_source)

    def test_actual_oceanbase_mount_paths_required(self):
        self.assertIn('pick_path("DATA_DISK_PATH")', self.python_source)
        self.assertIn('pick_path("LOG_DISK_PATH")', self.python_source)
        self.assertNotIn('disk_usage("/")', self.python_source)

    def test_single_wrong_item_is_rejected_and_normal_item_passes(self):
        self.assertFalse(cleanup_item_is_expected(1, Decimal("20.00"), 2, 1))
        self.assertTrue(cleanup_item_is_expected(1, Decimal("10.00"), 2, 1))

    def test_wrong_mobile_record_is_rejected_and_normal_record_passes(self):
        expected_time = datetime(2026, 6, 1, 0, 0, 37)
        self.assertFalse(cleanup_record_is_expected(1, "198700000002", Decimal("10.00"), expected_time, Decimal("10.00"), "USED", expected_time, 1))
        self.assertTrue(cleanup_record_is_expected(1, "198700000001", Decimal("10.00"), expected_time, Decimal("10.00"), "USED", expected_time, 1))

    def test_cleanup_refuses_item_anomaly_before_confirmation(self):
        with patch.object(phase7, "marker_counts", return_value={}), patch.object(phase7, "reference_anomalies", return_value={}), patch.object(phase7, "cleanup_inbound_anomalies", return_value={"non_p7_item_to_p7_order": 1}), patch("builtins.input") as prompt:
            with self.assertRaises(RuntimeError): phase7.cleanup(object())
            prompt.assert_not_called()

    def test_cleanup_refuses_record_anomaly_before_confirmation(self):
        with patch.object(phase7, "marker_counts", return_value={}), patch.object(phase7, "reference_anomalies", return_value={}), patch.object(phase7, "cleanup_inbound_anomalies", return_value={"non_p7_record_to_p7_card": 1}), patch("builtins.input") as prompt:
            with self.assertRaises(RuntimeError): phase7.cleanup(object())
            prompt.assert_not_called()

    def test_normal_cleanup_relationships_reach_confirmation(self):
        with patch.object(phase7, "marker_counts", return_value={}), patch.object(phase7, "reference_anomalies", return_value={}), patch.object(phase7, "cleanup_inbound_anomalies", return_value={}), patch("builtins.input", return_value="STOP") as prompt:
            with self.assertRaises(RuntimeError): phase7.cleanup(object())
            prompt.assert_called_once()


if __name__ == "__main__":
    unittest.main()
