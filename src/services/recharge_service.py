"""充值业务：Python做友好前置检查，数据库触发器负责最终约束和状态更新。"""

from __future__ import annotations

from decimal import Decimal

from src.db import is_integrity_error
from src.errors import BusinessError
from src.security import verify_secret


def recharge_card(
    connection, card_no: str, card_password: str, phone_number: str
) -> dict[str, object]:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT card_id, password_hash, face_value, card_status
            FROM recharge_card
            WHERE card_no=%s
            FOR UPDATE
            """,
            (card_no,),
        )
        card = cursor.fetchone()
        if not card:
            raise BusinessError("CARD_NOT_FOUND", "充值卡不存在")
        if not verify_secret(card_password, card["password_hash"]):
            raise BusinessError("INVALID_CARD_CREDENTIAL", "充值卡凭据错误")
        if card["card_status"] != "UNUSED":
            raise BusinessError("CARD_ALREADY_USED", "充值卡已经使用")

        cursor.execute(
            "SELECT mobile_id FROM mobile_number WHERE phone_number=%s",
            (phone_number,),
        )
        mobile = cursor.fetchone()
        if not mobile:
            raise BusinessError("MOBILE_NOT_FOUND", "手机号不存在")

        amount = Decimal(card["face_value"])
        try:
            cursor.execute(
                """
                INSERT INTO recharge_record
                    (card_id, mobile_id, recharge_amount, recharged_at)
                VALUES (%s, %s, %s, NOW(6))
                """,
                (card["card_id"], mobile["mobile_id"], amount),
            )
            recharge_id = int(cursor.lastrowid)
        except Exception as exc:
            if is_integrity_error(exc):
                raise BusinessError("RECHARGE_CONSTRAINT", "充值被数据库完整性约束拒绝") from exc
            # 触发器SIGNAL在PyMySQL中通常是OperationalError，转换为友好错误但保留原因链。
            if "P5_" in str(exc):
                raise BusinessError("RECHARGE_TRIGGER_REJECTED", "充值被数据库触发器拒绝") from exc
            raise

        cursor.execute(
            "SELECT card_status, used_at FROM recharge_card WHERE card_id=%s",
            (card["card_id"],),
        )
        changed_card = cursor.fetchone()
        if not changed_card or changed_card["card_status"] != "USED":
            raise BusinessError("CARD_STATE_ERROR", "充值记录已写入但卡状态未正确更新")

    return {
        "recharge_id": recharge_id,
        "card_id": int(card["card_id"]),
        "amount": amount,
        "card_status": changed_card["card_status"],
        "used_at": changed_card["used_at"],
    }
