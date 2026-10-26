"""SQLite initialization for the Streamlit application."""
from __future__ import annotations
import os
from typing import Dict
from core.gsheets import DataError, configure_database, ensure_schema as _ensure_schema, spreadsheet_info as _spreadsheet_info, to_number
_DB_PATH = ""
def configure(database_path: str = "") -> None:
    global _DB_PATH
    _DB_PATH = str(database_path or os.getenv("SQLITE_PATH", "")).strip()
    configure_database(_DB_PATH)
def database_path() -> str: return _DB_PATH
def ensure_schema(spreadsheet_key: str = "") -> None: _ensure_schema(spreadsheet_key)
def spreadsheet_info(spreadsheet_key: str = "") -> Dict[str, str]: return _spreadsheet_info(spreadsheet_key)
__all__ = ["DataError", "configure", "database_path", "ensure_schema", "spreadsheet_info", "to_number"]
