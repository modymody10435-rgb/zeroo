#!/usr/bin/env python3
"""Seed PostgreSQL from the bundled Google Sheets export on first deployment only."""
from __future__ import annotations
import os, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    if os.getenv('AUTO_IMPORT_WORKBOOK', '1').strip().lower() not in {'1','true','yes','on'}:
        print('Workbook auto-import disabled (AUTO_IMPORT_WORKBOOK=0).')
        return 0
    dsn = os.getenv('DATABASE_URL', '').strip()
    if not dsn:
        print('ERROR: DATABASE_URL is not set; cannot import bundled workbook.', file=sys.stderr)
        return 2
    workbook = Path(os.getenv('WORKBOOK_PATH', str(ROOT / 'data' / 'مخزن المعمل.xlsx')))
    if not workbook.is_absolute(): workbook = ROOT / workbook
    if not workbook.is_file():
        print(f'ERROR: bundled workbook not found: {workbook}', file=sys.stderr)
        return 2
    try:
        import psycopg2
    except ImportError:
        print('ERROR: psycopg2-binary is missing.', file=sys.stderr)
        return 2
    try:
        with psycopg2.connect(dsn, connect_timeout=10) as conn:
            with conn.cursor() as cur:
                cur.execute('CREATE TABLE IF NOT EXISTS app_sheet_rows (id BIGSERIAL PRIMARY KEY, sheet_name TEXT NOT NULL, row_data JSONB NOT NULL DEFAULT \'{}\'::jsonb, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())')
                cur.execute('CREATE INDEX IF NOT EXISTS idx_app_sheet_rows_name_id ON app_sheet_rows(sheet_name, id)')
                cur.execute('SELECT COUNT(*) FROM app_sheet_rows')
                count = int(cur.fetchone()[0])
                conn.commit()
        if count:
            print(f'Existing PostgreSQL data detected ({count} rows); skipping workbook import to prevent duplicates or overwrites.')
            return 0
        from scripts.import_google_sheets_workbook import read_workbook, SHEET_COLUMNS
        from psycopg2.extras import Json
        data = read_workbook(workbook)
        total = 0
        with psycopg2.connect(dsn, connect_timeout=10) as conn:
            with conn.cursor() as cur:
                for sheet_name, columns in SHEET_COLUMNS.items():
                    for row in data.get(sheet_name, []):
                        cur.execute('INSERT INTO app_sheet_rows(sheet_name, row_data) VALUES (%s, %s)', (sheet_name, Json({column: row.get(column, '') for column in columns})))
                        total += 1
                cur.execute('SELECT sheet_name, COUNT(*) FROM app_sheet_rows GROUP BY sheet_name')
                counts = {name: int(n) for name, n in cur.fetchall()}
                for sheet_name in SHEET_COLUMNS:
                    expected = len(data.get(sheet_name, []))
                    if counts.get(sheet_name, 0) != expected:
                        raise RuntimeError(f'Verification failed for {sheet_name}: expected {expected}, got {counts.get(sheet_name, 0)}')
        print(f'Initial import successful: {total} records imported and verified from {workbook.name}.')
        for sheet_name in SHEET_COLUMNS:
            print(f'  {sheet_name}: {len(data.get(sheet_name, []))}')
        print('User password hashes were copied unchanged from the workbook.')
        return 0
    except Exception as exc:
        print(f'ERROR: initial workbook import failed: {exc}', file=sys.stderr)
        return 1

if __name__ == '__main__':
    raise SystemExit(main())
