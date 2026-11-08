"""OceanBase连接及事务工具。"""

from __future__ import annotations

import re
from contextlib import contextmanager
from typing import Iterator

from src.db_config import DatabaseConfig


def encode_password_for_pymysql(password: str) -> bytes:
    """按入口文件的UTF-8编码还原密码字节，绕开PyMySQL的latin-1转换。

    PyMySQL 1.1.1会对str密码固定调用encode("latin1")。密码临时文件由
    Bash原样写入，并由db_config按UTF-8读取，因此这里重新编码为UTF-8字节，
    可以保留非ASCII密码的原始字节。PyMySQL原生接受bytes密码。
    """

    return password.encode("utf-8")


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
        # 传入bytes，避免PyMySQL 1.1.1对str密码强制使用latin-1编码。
        password=encode_password_for_pymysql(config.password),
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
