"""网络用户注册业务。"""

from __future__ import annotations

from src.db import is_integrity_error
from src.errors import BusinessError
from src.security import hash_secret


def register_user(connection, login_name: str, password: str, display_name: str) -> int:
    if not login_name.strip():
        raise BusinessError("INVALID_USER", "登录名不能为空")
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO app_user
                    (login_name, password_hash, registered_at, user_status, display_name)
                VALUES (%s, %s, NOW(6), 'ACTIVE', %s)
                """,
                (login_name, hash_secret(password), display_name),
            )
            return int(cursor.lastrowid)
    except Exception as exc:
        if is_integrity_error(exc):
            raise BusinessError("DUPLICATE_USER", "登录名已存在") from exc
        raise
