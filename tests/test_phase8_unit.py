"""阶段8不连接数据库的代码级测试。"""
import tempfile
import unittest
from pathlib import Path

from src.phase8_index_performance import (
    INDEXES, P8_CARD_PREFIX, QUERIES, REPEATS, export_csv, median_ms,
    temporary_card_no, validate_index_state,
)


class Phase8UnitTests(unittest.TestCase):
    def test_three_queries_and_indexes(self):
        self.assertEqual(len(QUERIES), 3)
        self.assertEqual(len(INDEXES), 3)
        self.assertTrue(all(name.startswith("idx_p8_") for name in INDEXES))

    def test_median_requires_complete_samples(self):
        self.assertEqual(median_ms([5, 1, 3, 2, 4]), 3)
        with self.assertRaises(ValueError):
            median_ms([1] * (REPEATS - 1))

    def test_index_state_is_strict(self):
        self.assertEqual(validate_index_state({}), "before")
        self.assertEqual(validate_index_state(INDEXES), "after")
        with self.assertRaises(RuntimeError):
            validate_index_state({next(iter(INDEXES)): next(iter(INDEXES.values()))})

    def test_first_run_reuses_stage7_full_index_whitelist(self):
        source = Path(__file__).parents[1].joinpath("src/phase8_index_performance.py").read_text(encoding="utf-8")
        self.assertIn("reject_performance_indexes(all_index_names(connection))", source)

    def test_like_patterns_are_parameters(self):
        for sql, _ in QUERIES.values():
            self.assertNotIn("P7-", sql)
        source = Path(__file__).parents[1].joinpath("src/phase8_index_performance.py").read_text(encoding="utf-8")
        self.assertIn("LEFT(po.order_no,9)=%s", source)

    def test_write_test_rolls_back_and_no_destructive_sql(self):
        source = Path(__file__).parents[1].joinpath("src/phase8_index_performance.py").read_text(encoding="utf-8").upper()
        self.assertIn("CONNECTION.ROLLBACK()", source)
        self.assertNotIn("DROP TABLE", source)
        self.assertNotIn("TRUNCATE", source)
        self.assertNotIn("DELETE FROM", source)

    def test_temporary_card_prefix_and_residue_predicate_match(self):
        card_no = temporary_card_no(3, 17)
        self.assertEqual(P8_CARD_PREFIX, "P8-PERF-")
        self.assertEqual(card_no, "P8-PERF-03-0017")
        self.assertEqual(card_no[:len(P8_CARD_PREFIX)], P8_CARD_PREFIX)
        source = Path(__file__).parents[1].joinpath("src/phase8_index_performance.py").read_text(encoding="utf-8")
        self.assertIn("LEFT(card_no,%s)=%s", source)
        self.assertIn("(len(P8_CARD_PREFIX), P8_CARD_PREFIX)", source)

    def test_csv_reports_equal_results(self):
        before = {name: {"median_ms": 10.0, "result": {"row_count": "1"}} for name in QUERIES}
        after = {name: {"median_ms": 5.0, "result": {"row_count": "1"}} for name in QUERIES}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "result.csv"
            export_csv(path, before, after)
            text = path.read_text(encoding="utf-8-sig")
            self.assertIn("50.0,True", text)

    def test_password_not_logged_or_on_command_line(self):
        shell = Path(__file__).parents[1].joinpath("scripts/run_phase8_index_performance.sh").read_text(encoding="utf-8")
        self.assertIn("read -r -s", shell)
        self.assertIn("chmod 600", shell)
        self.assertNotIn("-p${", shell)


if __name__ == "__main__":
    unittest.main()
