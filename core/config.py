"""إعدادات النظام: القراءة من Streamlit Secrets مع قيم افتراضية آمنة."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

import streamlit as st


SHEETS = {
    "products": "Products",
    "orders": "Orders",
    "order_items": "Order_Items",
    "withdrawals": "Withdrawals",
    "stock_movements": "Stock_Movements",
    "settings": "Settings",
    "users": "Users",
}


@dataclass
class AppConfig:
    spreadsheet_key: str = "sqlite"
    service_account_file: str = "service_account.json"
    service_account_info: Optional[Dict[str, Any]] = None
    username: str = "admin"
    password: str = "admin123"
    app_title: str = "نظام إدارة مخزن المعمل"
    database_path: str = ""
    database_url: str = ""


def _secret(section: str, key: str, default: Any = None) -> Any:
    try:
        value = st.secrets[section][key]
        return value
    except Exception:
        return default


def load_config() -> AppConfig:
    cfg = AppConfig()

    cfg.database_url = ""
    cfg.spreadsheet_key = "sqlite"
    default_db = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "warehouse.sqlite3")
    cfg.database_path = str(os.getenv("SQLITE_PATH", default_db)).strip()
    cfg.service_account_file = ""
    cfg.service_account_info = None

    cfg.username = str(_secret("auth", "username", os.getenv("ADMIN_USERNAME", "admin")))
    cfg.password = str(_secret("auth", "password", os.getenv("ADMIN_PASSWORD", "")))
    cfg.app_title = str(_secret("auth", "app_title", "نظام إدارة مخزن المعمل"))

    return cfg


def secrets_available() -> bool:
    return True