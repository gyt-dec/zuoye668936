"""阶段9不连接数据库的并发模型与安全测试。"""
import unittest
from pathlib import Path

from src.phase9_concurrency import (
    LOADS, P9_PREFIX, RequestResult, database_error_code, make_order_no, percentile95,
    summarize, wave_sizes,
)


class Phase9UnitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).parents[1]
        cls.source = root.joinpath("src/phase9_concurrency.py").read_text(encoding="utf-8")
        cls.shell = root.joinpath("scripts/run_phase9_concurrency.sh").read_text(encoding="utf-8")

    def test_loads_are_1x_10x_100x_with_bounded_workers(self):
        self.assertEqual(LOADS, (("1x", 10, 5), ("10x", 100, 10), ("100x", 1000, 20)))

    def test_wave_boundaries(self):
        self.assertEqual(wave_sizes(10, 5), [5, 5])
        self.assertEqual(wave_sizes(100, 10), [10] * 10)
        self.assertEqual(wave_sizes(1000, 20), [20] * 50)

    def test_each_round_has_independent_identifiers(self):
        names = {make_order_no(kind, strategy, load) for kind in ("LOST", "CARD") for strategy in ("unsafe", "locked") for load, _, _ in LOADS}
        self.assertEqual(len(names), 12)
        self.assertTrue(all(name.startswith(P9_PREFIX) for name in names))

    def test_result_classification_includes_competition_fields(self):
        rows = [
            RequestResult("success", 1, observed_unused=True, attempted_insert=True),
            RequestResult("business_rejected", 2),
            RequestResult("constraint_rejected", 3, observed_unused=True, attempted_insert=True),
            RequestResult("unexpected_error", 4),
        ]
        result = summarize(rows)
        self.assertEqual((result["success"], result["business_rejected"], result["constraint_rejected"], result["unexpected_errors"]), (1, 1, 1, 1))
        self.assertEqual((result["observed_unused"], result["attempted_inserts"]), (2, 2))

    def test_database_error_codes_are_aggregated_without_messages(self):
        class FakeDatabaseError(Exception):
            pass
        self.assertEqual(database_error_code(FakeDatabaseError(1062, "sensitive detail")), "1062")
        rows = [RequestResult("constraint_rejected", 1, "1062"), RequestResult("constraint_rejected", 2, "1062"), RequestResult("constraint_rejected", 3, "1644")]
        self.assertEqual(summarize(rows)["error_codes"], "1062:2,1644:1")

    def test_p95(self):
        self.assertEqual(percentile95(list(range(1, 101))), 95)

    def test_unsafe_read_barrier_and_locked_select_present(self):
        self.assertIn("barrier.wait(timeout=30)", self.source)
        self.assertIn('suffix = " FOR UPDATE" if locked else ""', self.source)
        read_pos = self.source.index('old = Decimal(cursor.fetchone()["total_amount"])')
        barrier_pos = self.source.index("barrier.wait(timeout=30)", read_pos)
        update_pos = self.source.index('cursor.execute("UPDATE purchase_order', barrier_pos)
        self.assertLess(read_pos, barrier_pos)
        self.assertLess(barrier_pos, update_pos)

    def test_cleanup_is_key_scoped_and_non_destructive(self):
        cleanup = self.source[self.source.index("def cleanup_p9"):self.source.index("def save_results")]
        self.assertIn("card_id IN", cleanup)
        self.assertIn("order_id IN", cleanup)
        self.assertNotIn("TRUNCATE", self.source.upper())
        self.assertNotIn("DROP TABLE", self.source.upper())
        self.assertNotIn("ALTER SYSTEM", self.source.upper())

    def test_protects_p7_and_phase8_indexes(self):
        self.assertIn("marker_counts(connection) != EXPECTED_P7", self.source)
        self.assertIn("index_metadata(connection) != INDEXES", self.source)

    def test_password_is_hidden_and_not_command_argument(self):
        self.assertIn("read -r -s", self.shell)
        self.assertIn("chmod 600", self.shell)
        self.assertNotIn("-p${", self.shell)

    def test_outputs_json_csv_and_text_log(self):
        self.assertIn("phase9_concurrency_", self.source)
        self.assertIn(".json", self.source)
        self.assertIn(".csv", self.source)
        self.assertIn(".txt", self.shell)


if __name__ == "__main__":
    unittest.main()
