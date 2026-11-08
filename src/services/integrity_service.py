"""阶段6前后保护检查。"""

from __future__ import annotations


EXPECTED_P4 = "10,10,11,10,11,11,10"


def scalar(connection, sql: str, params: tuple = ()):
    with connection.cursor() as cursor:
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
              (SELECT COUNT(*) FROM app_user WHERE login_name LIKE 'p4_user_%'), ',',
              (SELECT COUNT(*) FROM owner WHERE owner_name LIKE 'P4_OWNER_%'), ',',
              (SELECT COUNT(*) FROM mobile_number WHERE phone_number LIKE '1994000%'), ',',
              (SELECT COUNT(*) FROM purchase_order WHERE order_no LIKE 'P4-ORDER-%'), ',',
              (SELECT COUNT(*) FROM order_item oi JOIN purchase_order po
                 ON po.order_id=oi.order_id WHERE po.order_no LIKE 'P4-ORDER-%'), ',',
              (SELECT COUNT(*) FROM recharge_card WHERE card_no LIKE 'P4-CARD-%'), ',',
              (SELECT COUNT(*) FROM recharge_record rr JOIN recharge_card rc
                 ON rc.card_id=rr.card_id WHERE rc.card_no LIKE 'P4-CARD-%')
            ) AS value
            """,
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
              (SELECT COUNT(*) FROM app_user WHERE login_name LIKE 'p6_user_%')+
              (SELECT COUNT(*) FROM owner WHERE owner_name LIKE 'P6_OWNER_%')+
              (SELECT COUNT(*) FROM mobile_number WHERE phone_number LIKE '1996000%')+
              (SELECT COUNT(*) FROM purchase_order WHERE order_no LIKE 'P6-ORDER-%')+
              (SELECT COUNT(*) FROM order_item oi JOIN purchase_order po
                 ON po.order_id=oi.order_id WHERE po.order_no LIKE 'P6-ORDER-%')+
              (SELECT COUNT(*) FROM recharge_card WHERE card_no LIKE 'P6-CARD-%')+
              (SELECT COUNT(*) FROM recharge_record rr JOIN recharge_card rc
                 ON rc.card_id=rr.card_id WHERE rc.card_no LIKE 'P6-CARD-%') AS value
            """,
        )
    )
