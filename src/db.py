"""OceanBase连接及事务工具。"""

from __future__ import annotations

import re
from contextlib import contextmanager
from typing import Iterator

from src.db_config import DatabaseConfig


def connect(config: DatabaseConfig, *, autocommit: bool = False):
    """延迟导入PyMySQL，便于在未安装驱动时执行纯代码单元测试。"""

    try:
        import pymysql
        from pymysql.cursors import DictCursor
    except ImportError as exc:
        raise RuntimeError("缺少PyMySQL，请通过阶段6入口脚本准备隔离环境") from exc

    return pymysql.connect(
        host=config.host,
        port=config.port,
        user=config.user,
        password=config.password,
        database=config.database,
        charset="utf8mb4",
        autocommit=autocommit,
        cursorclass=DictCursor,
        connect_timeout=10,
        read_timeout=30,
        write_timeout=30,
    )


@contextmanager
def transaction(connection) -> Iterator[None]:
    """生产CLI事务：成功提交，任意异常回滚。"""

    connection.begin()
    try:
        yield
        connection.commit()
    except BaseException:
        connection.rollback()
        raise


_SAVEPOINT_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")


@contextmanager
def savepoint(connection, name: str) -> Iterator[None]:
    """测试事务内的业务边界；名称经过白名单校验后才进入SQL。"""

    if not _SAVEPOINT_NAME.fullmatch(name):
        raise ValueError("非法SAVEPOINT名称")
    with connection.cursor() as cursor:
        cursor.execute(f"SAVEPOINT {name}")
    try:
        yield
    except BaseException:
        with connection.cursor() as cursor:
            cursor.execute(f"ROLLBACK TO SAVEPOINT {name}")
            cursor.execute(f"RELEASE SAVEPOINT {name}")
        raise
    else:
        with connection.cursor() as cursor:
            cursor.execute(f"RELEASE SAVEPOINT {name}")


def is_integrity_error(exc: BaseException) -> bool:
    """避免在模块导入阶段依赖PyMySQL，同时识别其完整性异常。"""

    return exc.__class__.__name__ == "IntegrityError" and exc.__class__.__module__.startswith(
        "pymysql"
    )
