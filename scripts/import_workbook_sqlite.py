#!/usr/bin/env python3
"""Validate or import the exported Google Sheets workbook into local SQLite."""
import argparse, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.gsheets import configure_database, ensure_schema, read_sheet, SCHEMA
from core.config import SHEETS
import pandas as pd

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--workbook', default=str(ROOT/'data'/'مخزن المعمل.xlsx'))
    p.add_argument('--dry-run', action='store_true')
    args=p.parse_args()
    wb=Path(args.workbook)
    if not wb.is_file(): print(f'ERROR: workbook not found: {wb}', file=sys.stderr); return 2
    try:
        xl=pd.ExcelFile(wb); counts={}
        for name in xl.sheet_names:
            if name not in SCHEMA: continue
            frame=pd.read_excel(xl,sheet_name=name,dtype=object).dropna(how='all')
            if not frame.empty:
                missing=[c for c in SCHEMA[name] if c not in frame.columns]
                if missing: raise ValueError(f'{name}: missing columns {missing}')
            counts[name]=len(frame)
        print('Workbook validation successful:')
        for n in SCHEMA: print(f'  {n}: {counts.get(n,0)}')
        if args.dry_run: return 0
        configure_database(str(ROOT/'data'/'warehouse.sqlite3')); ensure_schema('sqlite')
        print('SQLite row counts after initialization:')
        for n in SCHEMA: print(f'  {n}: {len(read_sheet("sqlite",n))}')
        print('Import is automatic only when SQLite is empty; existing data was not overwritten.')
        return 0
    except Exception as e: print(f'ERROR: {e}',file=sys.stderr); return 1
if __name__=='__main__': raise SystemExit(main())
