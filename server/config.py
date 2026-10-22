from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _as_int(value: str | None, default: int) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def _path(value: str | None, default: Path) -> Path:
    if not value:
        return default
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        candidate = ROOT_DIR / candidate
    return candidate.resolve()


APP_TITLE = os.getenv("APP_TITLE", "نظام إدارة مخزن المعمل")
APP_VERSION = "2.0.0"

DB_PATH = _path(os.getenv("WAREHOUSE_DB_PATH"), ROOT_DIR / "data" / "warehouse.sqlite3")
OFFLINE_DB_PATH = _path(os.getenv("OFFLINE_DB_PATH"), ROOT_DIR / "data" / "offline.db")
MIGRATE_OFFLINE_DB = _as_bool(os.getenv("MIGRATE_OFFLINE_DB"), True)

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
SESSION_DAYS = max(1, _as_int(os.getenv("SESSION_DAYS"), 14))
COOKIE_NAME = os.getenv("COOKIE_NAME", "warehouse_session")
COOKIE_SECURE = _as_bool(os.getenv("COOKIE_SECURE"), False)
COOKIE_SAMESITE = os.getenv("COOKIE_SAMESITE", "lax")
TRUSTED_ORIGINS = [
    item.strip()
    for item in os.getenv("TRUSTED_ORIGINS", "").split(",")
    if item.strip()
]

HOST = os.getenv("WAREHOUSE_HOST", "0.0.0.0")
PORT = _as_int(os.getenv("WAREHOUSE_PORT"), 8000)
FORWARDED_ALLOW_IPS = os.getenv("FORWARDED_ALLOW_IPS", "127.0.0.1")
FRONTEND_DIR = ROOT_DIR / "frontend"
