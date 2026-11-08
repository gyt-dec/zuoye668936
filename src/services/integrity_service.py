"""阶段6前后保护检查。"""

from __future__ import annotations


EXPECTED_P4 = "10,10,11,10,11,11,10"


def scalar(connection, sql: str, params: tuple | None = None):
    with connection.cursor() as cursor:
        if params is None:
            cursor.execute(sql)
        else:
            cursor.execute(sql, params)
        row = cursor.fetchone()
        return next(iter(row.values()))


def table_count(connection) -> int:
    return int(
        scalar(
            connection,
            """
            SELECT COUNT(*) AS value
            FROM information_schema.TABLES
            WHERE TABLE_SCHEMA=DATABASE() AND TABLE_TYPE='BASE TABLE'
            """,
        )
    )


def p4_counts(connection) -> str:
    return str(
        scalar(
            connection,
            """
            SELECT CONCAT(
              (SELECT COUNT(*) FROM app_user WHERE login_name LIKE %s), ',',
              (SELECT COUNT(*) FROM owner WHERE owner_name LIKE %s), ',',
              (SELECT COUNT(*) FROM mobile_number WHERE phone_number LIKE %s), ',',
              (SELECT COUNT(*) FROM purchase_order WHERE order_no LIKE %s), ',',
              (SELECT COUNT(*) FROM order_item oi JOIN purchase_order po
                 ON po.order_id=oi.order_id WHERE po.order_no LIKE %s), ',',
              (SELECT COUNT(*) FROM recharge_card WHERE card_no LIKE %s), ',',
              (SELECT COUNT(*) FROM recharge_record rr JOIN recharge_card rc
                 ON rc.card_id=rr.card_id WHERE rc.card_no LIKE %s)
            ) AS value
            """,
            (
                "p4_user_%",
                "P4_OWNER_%",
                "1994000%",
                "P4-ORDER-%",
                "P4-ORDER-%",
                "P4-CARD-%",
                "P4-CARD-%",
            ),
        )
    )


def p5_object_counts(connection) -> str:
    return str(
        scalar(
            connection,
            """
            SELECT CONCAT(
              (SELECT COUNT(*) FROM information_schema.VIEWS
                WHERE TABLE_SCHEMA=DATABASE()
                  AND TABLE_NAME IN ('v_user_card_purchase_detail',
                                     'v_mobile_recharge_history')), ',',
              (SELECT COUNT(*) FROM information_schema.TRIGGERS
                WHERE TRIGGER_SCHEMA=DATABASE()
                  AND TRIGGER_NAME IN ('trg_recharge_record_validate',
                                       'trg_recharge_record_mark_card_used'))
            ) AS value
            """,
        )
    )


def p6_residue_count(connection) -> int:
    return int(
        scalar(
            connection,
            """
            SELECT
              (SELECT COUNT(*) FROM app_user WHERE login_name LIKE %s)+
              (SELECT COUNT(*) FROM owner WHERE owner_name LIKE %s)+
              (SELECT COUNT(*) FROM mobile_number WHERE phone_number LIKE %s)+
              (SELECT COUNT(*) FROM purchase_order WHERE order_no LIKE %s)+
              (SELECT COUNT(*) FROM order_item oi JOIN purchase_order po
                 ON po.order_id=oi.order_id WHERE po.order_no LIKE %s)+
              (SELECT COUNT(*) FROM recharge_card WHERE card_no LIKE %s)+
              (SELECT COUNT(*) FROM recharge_record rr JOIN recharge_card rc
                 ON rc.card_id=rr.card_id WHERE rc.card_no LIKE %s) AS value
            """,
            (
                "p6_user_%",
                "P6_OWNER_%",
                "1996000%",
                "P6-ORDER-%",
                "P6-ORDER-%",
                "P6-CARD-%",
                "P6-CARD-%",
            ),
        )
    )
