#!/usr/bin/env python3
"""Import an exported Google Sheets workbook into the Streamlit app's PostgreSQL store.

Preserves password_hash values exactly (the workbook contains password hashes, not
recoverable plaintext passwords). Safe by default: refuses to import into a
non-empty app_sheet_rows table unless --replace is explicitly provided.
"""
from __future__ import annotations

import argparse
import math
import os
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd

SHEET_COLUMNS = {
    "Products": [
        "product_code", "product_name", "unit", "current_stock", "min_stock",
        "storage_location", "notes", "created_at", "starting_stock",
        "total_withdrawn", "date_added", "manufacturer", "supplier",
        "expiry_date", "added_by", "category", "serial_number", "device_status",
        "units_per_carton", "purchase_date", "last_withdraw_date",
        "device_condition", "decommission_date", "decommission_reason",
        "decommissioned_by",
    ],
    "Orders": [
        "order_no", "order_date", "factory_name", "responsible_person",
        "status", "notes", "created_at",
    ],
    "Order_Items": [
        "item_id", "order_no", "product_code", "product_name", "unit",
        "required_qty", "withdrawn_qty", "last_withdraw_date",
        "last_withdrawn_by", "created_at",
    ],
    "Withdrawals": [
        "withdrawal_id", "order_no", "item_id", "product_code",
        "product_name", "qty", "withdraw_date", "withdrawn_by", "notes",
        "created_at", "supervisor_name",
    ],
    "Stock_Movements": [
        "movement_no", "movement_date", "movement_type", "order_no",
        "product_code", "product_name", "qty", "balance_after", "person",
        "notes", "created_at",
    ],
    "Settings": ["key", "value"],
    "Users": ["username", "password_hash", "role", "lab_access", "created_at"],
}


def cell_to_text(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime().isoformat(sep=" ")
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float) and math.isfinite(value) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def read_workbook(path: Path) -> dict[str, list[dict[str, str]]]:
    if not path.is_file():
        raise FileNotFoundError(f"Workbook not found: {path}")
    excel = pd.ExcelFile(path)
    result: dict[str, list[dict[str, str]]] = {}
    for sheet_name in excel.sheet_names:
        frame = pd.read_excel(excel, sheet_name=sheet_name, dtype=object)
        frame = frame.dropna(how="all")
        if frame.empty:
            continue
        if sheet_name not in SHEET_COLUMNS:
            raise ValueError(
                f"Sheet '{sheet_name}' contains data but is not mapped. "
                "Add an explicit mapping before importing so no data is silently skipped."
            )
        expected = SHEET_COLUMNS[sheet_name]
        missing = [column for column in expected if column not in frame.columns]
        if missing:
            raise ValueError(f"Sheet '{sheet_name}' is missing columns: {', '.join(missing)}")
        rows = []
        for _, source in frame.iterrows():
            row = {column: cell_to_text(source[column]) for column in expected}
            # Older exports sometimes placed created_at in lab_access for legacy
            # admin accounts and left created_at blank. Repair that known shape.
            if sheet_name == "Users" and row.get("created_at", "") == "":
                legacy_value = row.get("lab_access", "")
                if legacy_value and (
                    len(legacy_value) >= 10
                    and legacy_value[4:5] == "-"
                    and legacy_value[7:8] == "-"
                ):
                    row["created_at"] = legacy_value
                    row["lab_access"] = "All" if row.get("role", "").lower() == "admin" else ""
            # Ignore fully blank rows, but preserve rows with any actual value.
            if any(value != "" for value in row.values()):
                rows.append(row)
        result[sheet_name] = rows
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--workbook",
        default=str(Path(__file__).resolve().parents[1] / "data" / "مخزن المعمل.xlsx"),
        help="Path to the exported .xlsx workbook",
    )
    parser.add_argument("--dry-run", action="store_true", help="Validate and report counts without connecting to PostgreSQL")
    parser.add_argument("--replace", action="store_true", help="Replace imported sheet rows in PostgreSQL (destructive for these sheets)")
    args = parser.parse_args()

    try:
        data = read_workbook(Path(args.workbook))
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print("Workbook validation successful. Rows to import:")
    for sheet in SHEET_COLUMNS:
        print(f"  {sheet}: {len(data.get(sheet, []))}")
    if "Users" in data:
        print("  User password hashes will be copied unchanged; plaintext passwords are not present in the workbook.")
    if args.dry_run:
        print("DRY RUN: no database connection or changes made.")
        return 0

    dsn = os.getenv("DATABASE_URL", "").strip()
    if not dsn:
        print("ERROR: set DATABASE_URL to the target PostgreSQL connection string.", file=sys.stderr)
        return 2

    try:
        import psycopg2
        from psycopg2.extras import Json
    except ImportError:
        print("ERROR: install requirements.txt first (psycopg2-binary).", file=sys.stderr)
        return 2

    try:
        with psycopg2.connect(dsn, connect_timeout=10) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS app_sheet_rows (
                        id BIGSERIAL PRIMARY KEY,
                        sheet_name TEXT NOT NULL,
                        row_data JSONB NOT NULL DEFAULT '{}'::jsonb,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_app_sheet_rows_name_id
                    ON app_sheet_rows(sheet_name, id)
                """)
                cur.execute("SELECT COUNT(*) FROM app_sheet_rows")
                existing = int(cur.fetchone()[0])
                if existing and not args.replace:
                    raise RuntimeError(
                        f"Target app_sheet_rows already contains {existing} rows. "
                        "Review the target database; use --replace only if you intend to replace the app's imported sheet data."
                    )
                if args.replace:
                    cur.execute("DELETE FROM app_sheet_rows WHERE sheet_name = ANY(%s)", (list(SHEET_COLUMNS),))
                total = 0
                for sheet_name, columns in SHEET_COLUMNS.items():
                    for row in data.get(sheet_name, []):
                        payload = {column: row.get(column, "") for column in columns}
                        cur.execute(
                            "INSERT INTO app_sheet_rows(sheet_name, row_data) VALUES (%s, %s)",
                            (sheet_name, Json(payload)),
                        )
                        total += 1
                # Verify per-sheet row counts inside the same transaction.
                cur.execute(
                    "SELECT sheet_name, COUNT(*) FROM app_sheet_rows WHERE sheet_name = ANY(%s) GROUP BY sheet_name",
                    (list(SHEET_COLUMNS),),
                )
                imported = {name: int(count) for name, count in cur.fetchall()}
                for name in SHEET_COLUMNS:
                    if imported.get(name, 0) != len(data.get(name, [])):
                        raise RuntimeError(
                            f"Verification failed for {name}: expected {len(data.get(name, []))}, got {imported.get(name, 0)}"
                        )
            conn.commit()
        print(f"SUCCESS: imported and verified {total} rows into PostgreSQL.")
        for sheet in SHEET_COLUMNS:
            print(f"  {sheet}: {len(data.get(sheet, []))}")
        return 0
    except Exception as exc:
        print(f"ERROR: import failed and was rolled back: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
