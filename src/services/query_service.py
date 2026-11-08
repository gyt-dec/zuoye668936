"""通过阶段5视图查询购卡明细和充值历史。"""

from __future__ import annotations


def get_user_purchase_details(connection, login_name: str) -> list[dict]:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT login_name, order_no, denomination, quantity,
                   card_no, face_value, card_status
            FROM v_user_card_purchase_detail
            WHERE login_name=%s
            ORDER BY order_no, denomination, card_no
            """,
            (login_name,),
        )
        return list(cursor.fetchall())


def get_mobile_recharge_history(connection, phone_number: str) -> list[dict]:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT owner_name, phone_number, card_no, card_status,
                   recharge_amount, recharged_at
            FROM v_mobile_recharge_history
            WHERE phone_number=%s
            ORDER BY recharged_at, card_no
            """,
            (phone_number,),
        )
        return list(cursor.fetchall())
