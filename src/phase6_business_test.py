#!/usr/bin/env python3
"""阶段6自动业务实验；所有P6数据最终回滚。"""

from __future__ import annotations

import secrets
import sys
from decimal import Decimal

from src.db import connect, savepoint
from src.db_config import load_database_config
from src.errors import BusinessError
from src.services.integrity_service import (
    EXPECTED_P4,
    p4_counts,
    p5_object_counts,
    p6_residue_count,
    scalar,
    table_count,
)
from src.services.mobile_service import create_owner_with_phones
from src.services.purchase_service import PurchaseLine, create_purchase
from src.services.query_service import (
    get_mobile_recharge_history,
    get_user_purchase_details,
)
from src.services.recharge_service import recharge_card
from src.services.user_service import register_user


def check(label: str, condition: bool, detail: object = "") -> None:
    if not condition:
        raise AssertionError(f"{label} 不符合预期：{detail}")
    print(f"PASS|{label}|{detail}")


def expect_business_error(connection, label: str, code: str, operation) -> None:
    try:
        with savepoint(connection, f"sp_{label.lower()}"):
            operation()
    except BusinessError as exc:
        check(label, exc.code == code, exc.code)
        print(f"EXPECTED_FAIL|{label}|{exc.code}")
        return
    raise AssertionError(f"{label} 应失败但实际成功")


def run() -> int:
    config = load_database_config()
    connection = connect(config, autocommit=False)
    test_transaction_started = False
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT CURRENT_USER() AS account, VERSION() AS version,
                       @@ob_compatibility_mode AS compatibility_mode,
                       DATABASE() AS current_database
                """
            )
            environment = cursor.fetchone()
        check("OceanBase连接", "OceanBase" in environment["version"], environment["version"])
        check("MYSQL兼容模式", environment["compatibility_mode"] == "MYSQL", environment["compatibility_mode"])
        check("当前数据库", environment["current_database"] == "phone_recharge_db", environment["current_database"])
        initial_table_count = table_count(connection)
        initial_p4 = p4_counts(connection)
        initial_p5 = p5_object_counts(connection)
        initial_p6 = p6_residue_count(connection)
        check("7张业务表", initial_table_count == 7, initial_table_count)
        check("阶段4基准", initial_p4 == EXPECTED_P4, initial_p4)
        check("阶段5对象", initial_p5 == "2,2", initial_p5)
        check("执行前P6残留", initial_p6 == 0, initial_p6)
        connection.rollback()

        user_password = secrets.token_urlsafe(18)
        card_password = secrets.token_urlsafe(18)
        login_name = "p6_user_01"
        phone_one = "19960000001"
        phone_two = "19960000002"

        connection.begin()
        test_transaction_started = True

        with savepoint(connection, "sp_register"):
            user_id = register_user(connection, login_name, user_password, "阶段6用户")
        check("用户注册", user_id > 0, "created")

        expect_business_error(
            connection,
            "DUPLICATE_USER",
            "DUPLICATE_USER",
            lambda: register_user(connection, login_name, user_password, "重复用户"),
        )

        with savepoint(connection, "sp_owner_mobile"):
            owner_id, mobile_ids = create_owner_with_phones(
                connection,
                "P6_OWNER_01",
                "p6_owner01@example.test",
                (phone_one, phone_two),
            )
        check("一个机主多个手机号", owner_id > 0 and len(mobile_ids) == 2, len(mobile_ids))

        failed_lines = [
            PurchaseLine(Decimal("20.00"), ("P6-CARD-FAIL-DUP",), card_password),
            PurchaseLine(Decimal("30.00"), ("P6-CARD-FAIL-DUP",), card_password),
        ]
        expect_business_error(
            connection,
            "PURCHASE_ROLLBACK",
            "PURCHASE_CONSTRAINT",
            lambda: create_purchase(
                connection, login_name, "P6-ORDER-FAIL", failed_lines
            ),
        )
        failed_order_count = scalar(
            connection,
            "SELECT COUNT(*) AS value FROM purchase_order WHERE order_no=%s",
            ("P6-ORDER-FAIL",),
        )
        failed_card_count = scalar(
            connection,
            "SELECT COUNT(*) AS value FROM recharge_card WHERE card_no=%s",
            ("P6-CARD-FAIL-DUP",),
        )
        check(
            "购卡失败无半成品",
            int(failed_order_count) == 0 and int(failed_card_count) == 0,
            f"orders={failed_order_count},cards={failed_card_count}",
        )

        successful_lines = [
            PurchaseLine(
                Decimal("20.00"),
                ("P6-CARD-20-01", "P6-CARD-20-02"),
                card_password,
            ),
            PurchaseLine(Decimal("30.00"), ("P6-CARD-30-01",), card_password),
        ]
        with savepoint(connection, "sp_purchase_success"):
            purchase = create_purchase(
                connection, login_name, "P6-ORDER-OK", successful_lines
            )
        check(
            "一次购买多张卡",
            len(purchase["card_ids"]) == 3
            and purchase["total_amount"] == Decimal("70.00"),
            f"cards={len(purchase['card_ids'])},total={purchase['total_amount']}",
        )
        purchase_rows = get_user_purchase_details(connection, login_name)
        check("购卡视图查询", len(purchase_rows) == 3, len(purchase_rows))

        expect_business_error(
            connection,
            "INVALID_CARD",
            "CARD_NOT_FOUND",
            lambda: recharge_card(
                connection, "P6-CARD-NOT-EXISTS", card_password, phone_one
            ),
        )
        expect_business_error(
            connection,
            "WRONG_CREDENTIAL",
            "INVALID_CARD_CREDENTIAL",
            lambda: recharge_card(
                connection, "P6-CARD-20-01", "wrong-card-password", phone_one
            ),
        )
        expect_business_error(
            connection,
            "MOBILE_NOT_FOUND",
            "MOBILE_NOT_FOUND",
            lambda: recharge_card(
                connection, "P6-CARD-20-02", card_password, "19969999999"
            ),
        )

        untouched_state = scalar(
            connection,
            """
            SELECT CONCAT(rc.card_status, ',', COUNT(rr.recharge_id)) AS value
            FROM recharge_card rc
            LEFT JOIN recharge_record rr ON rr.card_id=rc.card_id
            WHERE rc.card_no=%s
            GROUP BY rc.card_id, rc.card_status
            """,
            ("P6-CARD-20-02",),
        )
        check("充值失败状态一致", untouched_state == "UNUSED,0", untouched_state)

        with savepoint(connection, "sp_recharge_success"):
            recharge = recharge_card(
                connection, "P6-CARD-20-01", card_password, phone_one
            )
        check(
            "正常充值及触发器状态",
            recharge["card_status"] == "USED"
            and recharge["amount"] == Decimal("20.00"),
            f"status={recharge['card_status']},amount={recharge['amount']}",
        )

        expect_business_error(
            connection,
            "USED_CARD",
            "CARD_ALREADY_USED",
            lambda: recharge_card(
                connection, "P6-CARD-20-01", card_password, phone_two
            ),
        )
        expect_business_error(
            connection,
            "DUPLICATE_RECHARGE",
            "CARD_ALREADY_USED",
            lambda: recharge_card(
                connection, "P6-CARD-20-01", card_password, phone_one
            ),
        )
        history_rows = get_mobile_recharge_history(connection, phone_one)
        check("充值历史视图查询", len(history_rows) == 1, len(history_rows))

        used_state = scalar(
            connection,
            """
            SELECT CONCAT(rc.card_status, ',', COUNT(rr.recharge_id)) AS value
            FROM recharge_card rc
            LEFT JOIN recharge_record rr ON rr.card_id=rc.card_id
            WHERE rc.card_no=%s
            GROUP BY rc.card_id, rc.card_status
            """,
            ("P6-CARD-20-01",),
        )
        check("重复充值后状态一致", used_state == "USED,1", used_state)

        in_transaction_rows = p6_residue_count(connection)
        check("P6事务内关联总行数", in_transaction_rows == 11, in_transaction_rows)
        connection.rollback()
        test_transaction_started = False
        print("PASS|P6测试事务最终回滚|done")
    except BaseException:
        if test_transaction_started:
            connection.rollback()
        raise
    finally:
        connection.close()

    verify_connection = connect(config, autocommit=True)
    try:
        final_p6 = p6_residue_count(verify_connection)
        final_p4 = p4_counts(verify_connection)
        final_p5 = p5_object_counts(verify_connection)
        check("P6最终残留", final_p6 == 0, final_p6)
        check("测试后阶段4基准", final_p4 == EXPECTED_P4, final_p4)
        check("测试后阶段5对象", final_p5 == "2,2", final_p5)
    finally:
        verify_connection.close()

    print("========== 阶段6汇总 ==========")
    print("PASS|用户、机主、手机号、购卡、充值和两个视图业务测试|complete")
    print("PASS|全部预期失败被正确分类且无半成品数据|complete")
    print("PASS|P6数据最终回滚，P4基准和P5对象未改变|complete")
    print("最终状态：PASS")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(run())
    except BaseException as exc:
        # 不打印连接配置、密码或完整对象repr。
        print(f"最终状态：FAIL｜{exc.__class__.__name__}｜{exc}", file=sys.stderr)
        raise SystemExit(1)
