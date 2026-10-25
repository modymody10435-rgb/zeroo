"""PostgreSQL-backed compatibility layer for the former Google Sheets API.

The Streamlit UI and business services keep their existing function calls, while
all persistent reads/writes are now performed against PostgreSQL.
"""
from __future__ import annotations
import json, os
from typing import Any, Dict, List
import pandas as pd
import streamlit as st
import psycopg2
from psycopg2.extras import RealDictCursor, Json
from core.config import SHEETS

SCHEMA: Dict[str, List[str]] = {
    SHEETS["products"]: [
        "product_code",
        "product_name",
        "unit",
        "current_stock",
        "min_stock",
        "storage_location",
        "notes",
        "created_at",
        "starting_stock",
        "total_withdrawn",
        "date_added",
        "manufacturer",
        "supplier",
        "expiry_date",
        "added_by",
        "category",
        "serial_number",
        "device_status",
        "units_per_carton",
        "purchase_date",
        "last_withdraw_date",
        "device_condition",
        "decommission_date",
        "decommission_reason",
        "decommissioned_by",
    ],
    SHEETS["orders"]: [
        "order_no",
        "order_date",
        "factory_name",
        "responsible_person",
        "status",
        "notes",
        "created_at",
    ],
    SHEETS["order_items"]: [
        "item_id",
        "order_no",
        "product_code",
        "product_name",
        "unit",
        "required_qty",
        "withdrawn_qty",
        "last_withdraw_date",
        "last_withdrawn_by",
        "created_at",
    ],
    SHEETS["withdrawals"]: [
        "withdrawal_id",
        "order_no",
        "item_id",
        "product_code",
        "product_name",
        "qty",
        "withdraw_date",
        "withdrawn_by",
        "notes",
        "created_at",
        "supervisor_name",
    ],
    SHEETS["stock_movements"]: [
        "movement_no",
        "movement_date",
        "movement_type",
        "order_no",
        "product_code",
        "product_name",
        "qty",
        "balance_after",
        "person",
        "notes",
        "created_at",
    ],
    SHEETS["settings"]: ["key", "value"],
    SHEETS["users"]: [
        "username",
        "password_hash",
        "role",
        "lab_access",
        "created_at",
    ],
}


class DataError(Exception):
    """خطأ عام في طبقة البيانات."""

_DSN = ""

def configure_database(dsn: str = "") -> None:
    global _DSN
    _DSN = str(dsn or os.getenv("DATABASE_URL", "")).strip()

def _connect():
    dsn = _DSN or os.getenv("DATABASE_URL", "")
    if not dsn:
        raise DataError("لم يتم إعداد DATABASE_URL لقاعدة PostgreSQL.")
    try:
        return psycopg2.connect(dsn, connect_timeout=8)
    except Exception as exc:
        raise DataError(f"تعذر الاتصال بقاعدة PostgreSQL: {exc}") from exc

def ensure_schema(key: str = "") -> None:
    """Create the table used to persist each legacy sheet as ordered JSON rows."""
    try:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute("""CREATE TABLE IF NOT EXISTS app_sheet_rows (
                id BIGSERIAL PRIMARY KEY,
                sheet_name TEXT NOT NULL,
                row_data JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )""")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_app_sheet_rows_name_id ON app_sheet_rows(sheet_name, id)")
            conn.commit()
    except Exception as exc:
        if isinstance(exc, DataError): raise
        raise DataError(f"تعذر تجهيز مخطط PostgreSQL: {exc}") from exc

def spreadsheet_info(key: str = "") -> Dict[str, str]:
    return {"title": "PostgreSQL", "url": ""}

class _DatabaseInfo:
    title = "PostgreSQL"
    url = ""

def get_spreadsheet(key: str = "") -> _DatabaseInfo:
    """Compatibility shim for the legacy settings view."""
    return _DatabaseInfo()

def _check_sheet(sheet_name: str) -> None:
    if sheet_name not in SCHEMA:
        raise DataError(f"اسم جدول غير معروف: {sheet_name}")

def _finalize(df: pd.DataFrame, sheet_name: str) -> pd.DataFrame:
    expected = SCHEMA[sheet_name]
    if df is None: return pd.DataFrame(columns=expected)
    for col in expected:
        if col not in df.columns: df[col] = ""
    return df.reindex(columns=expected)

def _clean(value: Any) -> Any:
    if value is None: return ""
    if hasattr(value, "item"):
        try: value = value.item()
        except Exception: pass
    if pd.isna(value): return ""
    if isinstance(value, (dict, list)): return value
    return str(value)

def read_sheet(key: str, sheet_name: str) -> pd.DataFrame:
    _check_sheet(sheet_name)
    try:
        with _connect() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT row_data FROM app_sheet_rows WHERE sheet_name=%s ORDER BY id", (sheet_name,))
            rows = [dict(r["row_data"] or {}) for r in cur.fetchall()]
        return _finalize(pd.DataFrame(rows), sheet_name)
    except Exception as exc:
        if isinstance(exc, DataError): raise
        raise DataError(f"تعذرت قراءة {sheet_name} من PostgreSQL: {exc}") from exc

def invalidate_cache() -> None:
    try: st.cache_data.clear()
    except Exception: pass

def _matches(row: Dict[str, Any], col: str, value: Any) -> bool:
    return str(row.get(col, "") if row.get(col, "") is not None else "").strip() == str(value if value is not None else "").strip()

def append_row(key: str, sheet_name: str, row: Dict[str, Any]) -> None:
    _check_sheet(sheet_name)
    payload = {col: _clean(row.get(col, "")) for col in SCHEMA[sheet_name]}
    try:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO app_sheet_rows(sheet_name,row_data) VALUES(%s,%s)", (sheet_name, Json(payload)))
            conn.commit()
        invalidate_cache()
    except Exception as exc: raise DataError(f"تعذر حفظ البيانات في PostgreSQL: {exc}") from exc

def append_rows(key: str, sheet_name: str, rows: List[Dict[str, Any]]) -> None:
    for row in rows: append_row(key, sheet_name, row)

def update_row(key: str, sheet_name: str, match_col: str, match_value: str, updates: Dict[str, Any]) -> bool:
    _check_sheet(sheet_name)
    changed = False
    try:
        with _connect() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT id,row_data FROM app_sheet_rows WHERE sheet_name=%s ORDER BY id", (sheet_name,))
            for rec in cur.fetchall():
                row = dict(rec["row_data"] or {})
                if _matches(row, match_col, match_value):
                    row.update({k: _clean(v) for k,v in updates.items() if k in SCHEMA[sheet_name]})
                    cur.execute("UPDATE app_sheet_rows SET row_data=%s WHERE id=%s", (Json(row), rec["id"]))
                    changed = True
            conn.commit()
        if changed: invalidate_cache()
        return changed
    except Exception as exc: raise DataError(f"تعذر تحديث البيانات في PostgreSQL: {exc}") from exc

def delete_rows_where(key: str, sheet_name: str, match_col: str, match_value: str) -> int:
    _check_sheet(sheet_name)
    try:
        with _connect() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT id,row_data FROM app_sheet_rows WHERE sheet_name=%s", (sheet_name,))
            ids = [r["id"] for r in cur.fetchall() if _matches(dict(r["row_data"] or {}), match_col, match_value)]
            if ids: cur.execute("DELETE FROM app_sheet_rows WHERE id = ANY(%s)", (ids,))
            conn.commit()
        if ids: invalidate_cache()
        return len(ids)
    except Exception as exc: raise DataError(f"تعذر حذف البيانات من PostgreSQL: {exc}") from exc

def delete_row(key: str, sheet_name: str, match_col: str, match_value: str) -> bool:
    return delete_rows_where(key, sheet_name, match_col, match_value) > 0

def clear_rows_where(key: str, sheet_name: str, match_col: str, match_value: str) -> int:
    return delete_rows_where(key, sheet_name, match_col, match_value)

def clear_sheet_rows(key: str, sheet_name: str) -> int:
    _check_sheet(sheet_name)
    try:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM app_sheet_rows WHERE sheet_name=%s", (sheet_name,))
            count = cur.rowcount
            conn.commit()
        invalidate_cache(); return count
    except Exception as exc: raise DataError(f"تعذر تفريغ البيانات في PostgreSQL: {exc}") from exc

def count_rows_where(key: str, sheet_name: str, match_col: str, match_value: str) -> int:
    df = read_sheet(key, sheet_name)
    if df.empty or match_col not in df.columns: return 0
    return int(df[match_col].map(lambda x: _matches({match_col:x}, match_col, match_value)).sum())

def sync_row(key: str, sheet_name: str, match_col: str, match_value: str, row: Dict[str, Any]) -> bool:
    if update_row(key, sheet_name, match_col, match_value, row): return True
    append_row(key, sheet_name, row); return True

def to_number(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or str(value).strip() == "": return default
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError): return default

def clear_cache() -> None:
    invalidate_cache()
