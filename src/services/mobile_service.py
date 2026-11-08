"""机主和手机号业务。"""

from __future__ import annotations

from collections.abc import Sequence

from src.db import is_integrity_error
from src.errors import BusinessError


def create_owner_with_phones(
    connection, owner_name: str, contact_info: str | None, phone_numbers: Sequence[str]
) -> tuple[int, list[int]]:
    if not owner_name.strip() or not phone_numbers:
        raise BusinessError("INVALID_OWNER", "机主姓名或手机号列表无效")
    if len(set(phone_numbers)) != len(phone_numbers):
        raise BusinessError("DUPLICATE_PHONE_INPUT", "手机号输入重复")
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO owner (owner_name, contact_info) VALUES (%s, %s)",
                (owner_name, contact_info),
            )
            owner_id = int(cursor.lastrowid)
            mobile_ids: list[int] = []
            for phone_number in phone_numbers:
                if not phone_number.isdigit() or not 6 <= len(phone_number) <= 32:
                    raise BusinessError("INVALID_PHONE", "手机号格式无效")
                cursor.execute(
                    """
                    INSERT INTO mobile_number
                        (owner_id, phone_number, number_status, registered_at)
                    VALUES (%s, %s, 'ACTIVE', NOW(6))
                    """,
                    (owner_id, phone_number),
                )
                mobile_ids.append(int(cursor.lastrowid))
        return owner_id, mobile_ids
    except BusinessError:
        raise
    except Exception as exc:
        if is_integrity_error(exc):
            raise BusinessError("MOBILE_CONSTRAINT", "机主或手机号违反数据库约束") from exc
        raise
