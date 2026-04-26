"""
Single source of truth for database connection settings.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
from dotenv import load_dotenv
load_dotenv()

@dataclass(frozen=True)
class DatabaseConfig:
    host: str
    port: int
    user: str
    password: str
    database: str
    charset: str = "utf8mb4"


CONNECT_TIMEOUT_SECONDS = 10
READ_TIMEOUT_SECONDS = 10
WRITE_TIMEOUT_SECONDS = 10

_REQUIRED_KEYS = ("DB_HOST", "DB_PORT", "DB_USER", "DB_PASS", "DB_NAME")

def _get_required_env(key: str, error_msg: str) -> str:
    value = os.getenv(key)
    if value is None:
        raise ValueError(error_msg)
    return value

DB_CONFIG = DatabaseConfig(
    host=_get_required_env("DB_HOST", "环境变量 DB_HOST 未设置"),
    port=int(_get_required_env("DB_PORT", "环境变量 DB_PORT 未设置")),
    user=_get_required_env("DB_USER", "环境变量 DB_USER 未设置"),
    password=_get_required_env("DB_PASS", "环境变量 DB_PASS 未设置"),
    database=_get_required_env("DB_NAME", "环境变量 DB_NAME 未设置"),
)
