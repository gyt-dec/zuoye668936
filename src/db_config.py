"""数据库连接配置，只从环境变量和权限受限的临时文件读取密码。"""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass, field
from pathlib import Path


class ConfigError(RuntimeError):
    """连接配置不完整或不安全。"""


@dataclass(frozen=True)
class DatabaseConfig:
    host: str
    port: int
    user: str
    password: str = field(repr=False)
    database: str


def load_database_config() -> DatabaseConfig:
    """读取连接配置；密码文件必须只允许当前用户读写。"""

    password_file_value = os.environ.get("OB_PASSWORD_FILE")
    if not password_file_value:
        raise ConfigError("缺少OB_PASSWORD_FILE，入口脚本必须安全提供密码文件")

    password_file = Path(password_file_value)
    try:
        mode = stat.S_IMODE(password_file.stat().st_mode)
    except FileNotFoundError as exc:
        raise ConfigError("数据库密码临时文件不存在") from exc
    if mode & 0o077:
        raise ConfigError("数据库密码临时文件权限必须为600")

    password = password_file.read_text(encoding="utf-8")
    if not password:
        raise ConfigError("数据库密码不能为空")

    try:
        port = int(os.environ.get("OB_PORT", "2881"))
    except ValueError as exc:
        raise ConfigError("OB_PORT必须是整数") from exc

    return DatabaseConfig(
        host=os.environ.get("OB_HOST", "127.0.0.1"),
        port=port,
        user=os.environ.get("OB_USER", "root@coursework"),
        password=password,
        database=os.environ.get("OB_DATABASE", "phone_recharge_db"),
    )
