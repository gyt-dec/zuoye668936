"""订单、多明细和多张充值卡的原子购买业务。"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from src.db import is_integrity_error
from src.errors import BusinessError
from src.security import hash_secret


@dataclass(frozen=True)
class PurchaseLine:
    denomination: Decimal
    card_numbers: tuple[str, ...]
    card_password: str


def create_purchase(
    connection, login_name: str, order_no: str, lines: list[PurchaseLine]
) -> dict[str, object]:
    if not order_no.strip() or not lines:
        raise BusinessError("INVALID_ORDER", "订单号或明细无效")

    total_amount = sum(
        (line.denomination * len(line.card_numbers) for line in lines), Decimal("0.00")
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT user_id FROM app_user WHERE login_name=%s", (login_name,)
            )
            user = cursor.fetchone()
            if not user:
                raise BusinessError("USER_NOT_FOUND", "购买用户不存在")

            cursor.execute(
                """
                INSERT INTO purchase_order
                    (user_id, order_no, created_at, order_status,
                     total_amount, completed_at)
                VALUES (%s, %s, NOW(6), 'COMPLETED', %s, NOW(6))
                """,
                (user["user_id"], order_no, total_amount),
            )
            order_id = int(cursor.lastrowid)
            card_ids: list[int] = []
            for line in lines:
                if line.denomination <= 0 or not line.card_numbers:
                    raise BusinessError("INVALID_LINE", "面额和购卡数量必须大于0")
                cursor.execute(
                    """
                    INSERT INTO order_item (order_id, denomination, quantity)
                    VALUES (%s, %s, %s)
                    """,
                    (order_id, line.denomination, len(line.card_numbers)),
                )
                item_id = int(cursor.lastrowid)
                for card_no in line.card_numbers:
                    if not card_no.strip():
                        raise BusinessError("INVALID_CARD_NO", "充值卡号不能为空")
                    cursor.execute(
                        """
                        INSERT INTO recharge_card
                            (item_id, card_no, password_hash, face_value,
                             card_status, created_at, used_at)
                        VALUES (%s, %s, %s, %s, 'UNUSED', NOW(6), NULL)
                        """,
                        (item_id, card_no, hash_secret(line.card_password), line.denomination),
                    )
                    card_ids.append(int(cursor.lastrowid))
        return {
            "order_id": order_id,
            "order_no": order_no,
            "total_amount": total_amount,
            "card_ids": card_ids,
        }
    except BusinessError:
        raise
    except Exception as exc:
        if is_integrity_error(exc):
            raise BusinessError("PURCHASE_CONSTRAINT", "购卡数据违反数据库约束") from exc
        raise
