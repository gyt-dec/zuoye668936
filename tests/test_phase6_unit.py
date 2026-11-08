"""不连接数据库的阶段6代码级正反测试。"""

from __future__ import annotations

import os
import ast
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from src.cli import parse_lines
from src.db import savepoint, transaction
from src.db_config import ConfigError, load_database_config
from src.errors import BusinessError
from src.security import hash_secret, verify_secret


class FakeCursor:
    def __init__(self, statements: list[str]):
        self.statements = statements

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, sql, params=None):
        self.statements.append(sql)


class FakeConnection:
    def __init__(self, *, fail_commit: bool = False):
        self.events: list[str] = []
        self.statements: list[str] = []
        self.fail_commit = fail_commit

    def begin(self):
        self.events.append("begin")

    def commit(self):
        self.events.append("commit")
        if self.fail_commit:
            raise RuntimeError("commit failed")

    def rollback(self):
        self.events.append("rollback")

    def cursor(self):
        return FakeCursor(self.statements)


class SecurityTests(unittest.TestCase):
    def test_hash_and_verify(self):
        encoded = hash_secret("coursework-secret")
        self.assertNotIn("coursework-secret", encoded)
        self.assertTrue(verify_secret("coursework-secret", encoded))
        self.assertFalse(verify_secret("wrong", encoded))

    def test_empty_secret_rejected(self):
        with self.assertRaises(ValueError):
            hash_secret("")


class ConfigTests(unittest.TestCase):
    def test_password_file_mode_and_repr(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "password"
            path.write_text("db-secret", encoding="utf-8")
            path.chmod(0o600)
            with patch.dict(
                os.environ,
                {"OB_PASSWORD_FILE": str(path), "OB_PORT": "2881"},
                clear=True,
            ):
                config = load_database_config()
            self.assertEqual(config.password, "db-secret")
            self.assertNotIn("db-secret", repr(config))

    def test_insecure_password_file_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "password"
            path.write_text("db-secret", encoding="utf-8")
            path.chmod(0o644)
            with patch.dict(os.environ, {"OB_PASSWORD_FILE": str(path)}, clear=True):
                with self.assertRaises(ConfigError):
                    load_database_config()


class TransactionTests(unittest.TestCase):
    def test_transaction_commits_on_success(self):
        connection = FakeConnection()
        with transaction(connection):
            pass
        self.assertEqual(connection.events, ["begin", "commit"])

    def test_transaction_rolls_back_on_failure(self):
        connection = FakeConnection()
        with self.assertRaises(RuntimeError):
            with transaction(connection):
                raise RuntimeError("expected")
        self.assertEqual(connection.events, ["begin", "rollback"])

    def test_transaction_rolls_back_when_commit_fails(self):
        connection = FakeConnection(fail_commit=True)
        with self.assertRaises(RuntimeError):
            with transaction(connection):
                pass
        self.assertEqual(connection.events, ["begin", "commit", "rollback"])

    def test_savepoint_success_and_failure(self):
        connection = FakeConnection()
        with savepoint(connection, "valid_name"):
            pass
        self.assertEqual(
            connection.statements,
            ["SAVEPOINT valid_name", "RELEASE SAVEPOINT valid_name"],
        )

        connection = FakeConnection()
        with self.assertRaises(BusinessError):
            with savepoint(connection, "valid_name"):
                raise BusinessError("EXPECTED", "expected")
        self.assertEqual(
            connection.statements,
            [
                "SAVEPOINT valid_name",
                "ROLLBACK TO SAVEPOINT valid_name",
                "RELEASE SAVEPOINT valid_name",
            ],
        )

    def test_invalid_savepoint_name_rejected(self):
        with self.assertRaises(ValueError):
            with savepoint(FakeConnection(), "bad;DROP"):
                pass


class CliInputTests(unittest.TestCase):
    def test_purchase_line_parsing(self):
        lines = parse_lines(["20:2", "30:1"], "P6-CARD", "card-secret")
        self.assertEqual(lines[0].denomination, Decimal("20"))
        self.assertEqual(len(lines[0].card_numbers), 2)
        self.assertEqual(len(lines[1].card_numbers), 1)

    def test_bad_purchase_line_rejected(self):
        with self.assertRaises(BusinessError):
            parse_lines(["bad"], "P6-CARD", "card-secret")


class SqlSafetyTests(unittest.TestCase):
    def test_business_execute_calls_do_not_use_f_strings(self):
        service_root = Path(__file__).parents[1] / "src" / "services"
        for path in service_root.glob("*.py"):
            source = path.read_text(encoding="utf-8")
            self.assertNotIn("execute(f", source, path.name)
            self.assertNotIn("execute(F", source, path.name)

    def test_business_sql_text_is_static_and_values_are_parameterized(self):
        service_root = Path(__file__).parents[1] / "src" / "services"
        for path in service_root.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "execute"
                ):
                    self.assertTrue(node.args, path.name)
                    if path.name == "integrity_service.py":
                        self.assertIsInstance(node.args[0], ast.Name, path.name)
                    else:
                        self.assertIsInstance(node.args[0], ast.Constant, path.name)

    def test_recharge_locks_card_row(self):
        service = (
            Path(__file__).parents[1] / "src" / "services" / "recharge_service.py"
        ).read_text(encoding="utf-8")
        self.assertIn("FOR UPDATE", service)


if __name__ == "__main__":
    unittest.main()
