"""SQLite-backed compatibility layer for the former Google Sheets API.

The Streamlit UI keeps its existing data API; all persistent rows are stored in
./data/warehouse.sqlite3. The supplied workbook is imported only when the local
SQLite table is empty.
"""
from __future__ import annotations
import json, os, sqlite3
from pathlib import Path
from typing import Any, Dict, List
import pandas as pd
import streamlit as st
from core.config import SHEETS

SCHEMA: Dict[str, List[str]] = {
    SHEETS["products"]: ["product_code","product_name","unit","current_stock","min_stock","storage_location","notes","created_at","starting_stock","total_withdrawn","date_added","manufacturer","supplier","expiry_date","added_by","category","serial_number","device_status","units_per_carton","purchase_date","last_withdraw_date","device_condition","decommission_date","decommission_reason","decommissioned_by"],
    SHEETS["orders"]: ["order_no","order_date","factory_name","responsible_person","status","notes","created_at"],
    SHEETS["order_items"]: ["item_id","order_no","product_code","product_name","unit","required_qty","withdrawn_qty","last_withdraw_date","last_withdrawn_by","created_at"],
    SHEETS["withdrawals"]: ["withdrawal_id","order_no","item_id","product_code","product_name","qty","withdraw_date","withdrawn_by","notes","created_at","supervisor_name"],
    SHEETS["stock_movements"]: ["movement_no","movement_date","movement_type","order_no","product_code","product_name","qty","balance_after","person","notes","created_at"],
    SHEETS["settings"]: ["key","value"],
    SHEETS["users"]: ["username","password_hash","role","lab_access","created_at"],
}
class DataError(Exception):
    """خطأ عام في طبقة البيانات."""

_DB_PATH = ""
def configure_database(path: str = "") -> None:
    global _DB_PATH
    # SQLite is local and requires no external service.
    raw = str(path or os.getenv("SQLITE_PATH", "") or "").strip()
    _DB_PATH = str(Path(raw).expanduser() if raw else Path(__file__).resolve().parents[1] / "data" / "warehouse.sqlite3")
    Path(_DB_PATH).parent.mkdir(parents=True, exist_ok=True)

def _connect():
    path = _DB_PATH or str(Path(__file__).resolve().parents[1] / "data" / "warehouse.sqlite3")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    try:
        conn = sqlite3.connect(path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("PRAGMA journal_mode=WAL")
        return conn
    except Exception as exc:
        raise DataError(f"تعذر فتح قاعدة SQLite: {exc}") from exc

def _cell(value: Any) -> str:
    if value is None: return ""
    try:
        if pd.isna(value): return ""
    except (TypeError, ValueError): pass
    if isinstance(value, pd.Timestamp): return value.to_pydatetime().isoformat(sep=" ")
    if hasattr(value, "item"):
        try: value = value.item()
        except Exception: pass
    if isinstance(value, float) and value.is_integer(): return str(int(value))
    return str(value).strip()

def _import_workbook_if_empty(conn: sqlite3.Connection) -> int:
    cur = conn.execute("SELECT COUNT(*) FROM app_sheet_rows")
    if int(cur.fetchone()[0]) > 0: return 0
    candidates = []
    env_path = os.getenv("WORKBOOK_PATH", "").strip()
    if env_path: candidates.append(Path(env_path))
    root = Path(__file__).resolve().parents[1]
    candidates += [root / "data" / "مخزن المعمل.xlsx", root / "data" / "warehouse.xlsx"]
    workbook = next((p for p in candidates if p.is_file()), None)
    if workbook is None: return 0
    try: excel = pd.ExcelFile(workbook)
    except Exception as exc: raise DataError(f"تعذر قراءة ملف Excel {workbook.name}: {exc}") from exc
    total = 0
    for sheet_name in excel.sheet_names:
        if sheet_name not in SCHEMA: continue
        frame = pd.read_excel(excel, sheet_name=sheet_name, dtype=object).dropna(how="all")
        if frame.empty: continue
        expected = SCHEMA[sheet_name]
        missing = [c for c in expected if c not in frame.columns]
        if missing:
            raise DataError(f"الورقة {sheet_name} ينقصها أعمدة: {', '.join(missing)}")
        for _, source in frame.iterrows():
            row = {c: _cell(source[c]) for c in expected}
            if sheet_name == "Users" and not row.get("created_at"):
                legacy = row.get("lab_access", "")
                if len(legacy) >= 10 and legacy[4:5] == "-" and legacy[7:8] == "-":
                    row["created_at"] = legacy
                    row["lab_access"] = "All" if row.get("role", "").lower() == "admin" else ""
            if not any(v != "" for v in row.values()): continue
            conn.execute("INSERT INTO app_sheet_rows(sheet_name,row_data) VALUES (?,?)", (sheet_name, json.dumps(row, ensure_ascii=False)))
            total += 1
    return total

def ensure_schema(key: str = "") -> None:
    try:
        with _connect() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS app_sheet_rows (id INTEGER PRIMARY KEY AUTOINCREMENT, sheet_name TEXT NOT NULL, row_data TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_app_sheet_rows_name_id ON app_sheet_rows(sheet_name,id)")
            imported = _import_workbook_if_empty(conn)
            conn.commit()
        if imported: print(f"SQLite import completed: {imported} rows imported from workbook.")
    except Exception as exc:
        if isinstance(exc, DataError): raise
        raise DataError(f"تعذر تجهيز قاعدة SQLite: {exc}") from exc

def spreadsheet_info(key: str = "") -> Dict[str, str]: return {"title": "SQLite", "url": _DB_PATH}
class _DatabaseInfo:
    title = "SQLite"
    url = ""
def get_spreadsheet(key: str = "") -> _DatabaseInfo:
    obj = _DatabaseInfo(); obj.url = _DB_PATH; return obj

def _check_sheet(sheet_name: str) -> None:
    if sheet_name not in SCHEMA: raise DataError(f"اسم جدول غير معروف: {sheet_name}")
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
    try:
        if pd.isna(value): return ""
    except (TypeError, ValueError): pass
    if isinstance(value, (dict, list)): return value
    return str(value)
def _matches(row: Dict[str, Any], col: str, value: Any) -> bool:
    return str(row.get(col, "") if row.get(col, "") is not None else "").strip() == str(value if value is not None else "").strip()
def read_sheet(key: str, sheet_name: str) -> pd.DataFrame:
    _check_sheet(sheet_name)
    try:
        with _connect() as conn:
            records = conn.execute("SELECT row_data FROM app_sheet_rows WHERE sheet_name=? ORDER BY id", (sheet_name,)).fetchall()
        rows = [json.loads(r["row_data"] or "{}") for r in records]
        return _finalize(pd.DataFrame(rows), sheet_name)
    except Exception as exc:
        if isinstance(exc, DataError): raise
        raise DataError(f"تعذرت قراءة {sheet_name} من SQLite: {exc}") from exc
def invalidate_cache() -> None:
    try: st.cache_data.clear()
    except Exception: pass
def append_row(key: str, sheet_name: str, row: Dict[str, Any]) -> None:
    _check_sheet(sheet_name); payload = {c: _clean(row.get(c, "")) for c in SCHEMA[sheet_name]}
    try:
        with _connect() as conn: conn.execute("INSERT INTO app_sheet_rows(sheet_name,row_data) VALUES (?,?)", (sheet_name, json.dumps(payload, ensure_ascii=False)))
        invalidate_cache()
    except Exception as exc: raise DataError(f"تعذر حفظ البيانات في SQLite: {exc}") from exc
def append_rows(key: str, sheet_name: str, rows: List[Dict[str, Any]]) -> None:
    for row in rows: append_row(key, sheet_name, row)
def update_row(key: str, sheet_name: str, match_col: str, match_value: str, updates: Dict[str, Any]) -> bool:
    _check_sheet(sheet_name); changed = False
    try:
        with _connect() as conn:
            records = conn.execute("SELECT id,row_data FROM app_sheet_rows WHERE sheet_name=? ORDER BY id", (sheet_name,)).fetchall()
            for rec in records:
                row = json.loads(rec["row_data"] or "{}")
                if _matches(row, match_col, match_value):
                    row.update({k: _clean(v) for k,v in updates.items() if k in SCHEMA[sheet_name]})
                    conn.execute("UPDATE app_sheet_rows SET row_data=? WHERE id=?", (json.dumps(row, ensure_ascii=False), rec["id"])); changed = True
        if changed: invalidate_cache()
        return changed
    except Exception as exc: raise DataError(f"تعذر تحديث البيانات في SQLite: {exc}") from exc
def delete_rows_where(key: str, sheet_name: str, match_col: str, match_value: str) -> int:
    _check_sheet(sheet_name); deleted = 0
    try:
        with _connect() as conn:
            records = conn.execute("SELECT id,row_data FROM app_sheet_rows WHERE sheet_name=?", (sheet_name,)).fetchall()
            ids = [r["id"] for r in records if _matches(json.loads(r["row_data"] or "{}"), match_col, match_value)]
            for row_id in ids: conn.execute("DELETE FROM app_sheet_rows WHERE id=?", (row_id,))
            deleted = len(ids)
        if deleted: invalidate_cache()
        return deleted
    except Exception as exc: raise DataError(f"تعذر حذف البيانات من SQLite: {exc}") from exc
def delete_row(key: str, sheet_name: str, match_col: str, match_value: str) -> bool: return delete_rows_where(key, sheet_name, match_col, match_value) > 0
def clear_rows_where(key: str, sheet_name: str, match_col: str, match_value: str) -> int: return delete_rows_where(key, sheet_name, match_col, match_value)
def clear_sheet_rows(key: str, sheet_name: str) -> int:
    _check_sheet(sheet_name)
    try:
        with _connect() as conn:
            cur = conn.execute("DELETE FROM app_sheet_rows WHERE sheet_name=?", (sheet_name,)); count = cur.rowcount
        invalidate_cache(); return count
    except Exception as exc: raise DataError(f"تعذر تفريغ البيانات في SQLite: {exc}") from exc
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
def clear_cache() -> None: invalidate_cache()
