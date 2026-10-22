from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

from server import config
from server.constants import (
    AUTHORITY_FORMS_SETTING,
    CATEGORY_GENERAL,
    CATEGORY_STORAGE,
    ORDER_STATUS_OPEN,
)
from server.security import hash_password

LOGGER = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS app_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'user',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_code TEXT NOT NULL UNIQUE COLLATE NOCASE,
    product_name TEXT NOT NULL,
    unit TEXT NOT NULL DEFAULT '',
    current_stock REAL NOT NULL DEFAULT 0,
    min_stock REAL NOT NULL DEFAULT 0,
    storage_location TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    starting_stock REAL NOT NULL DEFAULT 0,
    total_withdrawn REAL NOT NULL DEFAULT 0,
    date_added TEXT NOT NULL DEFAULT '',
    manufacturer TEXT NOT NULL DEFAULT '',
    supplier TEXT NOT NULL DEFAULT '',
    expiry_date TEXT NOT NULL DEFAULT '',
    added_by TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT 'عام',
    serial_number TEXT NOT NULL DEFAULT '',
    device_status TEXT NOT NULL DEFAULT '',
    units_per_carton REAL NOT NULL DEFAULT 0,
    purchase_date TEXT NOT NULL DEFAULT '',
    last_withdraw_date TEXT NOT NULL DEFAULT '',
    device_condition TEXT NOT NULL DEFAULT '',
    decommission_date TEXT NOT NULL DEFAULT '',
    decommission_reason TEXT NOT NULL DEFAULT '',
    decommissioned_by TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_no TEXT NOT NULL UNIQUE,
    order_date TEXT NOT NULL DEFAULT '',
    factory_name TEXT NOT NULL DEFAULT '',
    responsible_person TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'مفتوحة',
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS order_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id TEXT NOT NULL UNIQUE,
    order_no TEXT NOT NULL,
    product_code TEXT NOT NULL,
    product_name TEXT NOT NULL DEFAULT '',
    unit TEXT NOT NULL DEFAULT '',
    required_qty REAL NOT NULL DEFAULT 0,
    withdrawn_qty REAL NOT NULL DEFAULT 0,
    last_withdraw_date TEXT NOT NULL DEFAULT '',
    last_withdrawn_by TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS withdrawals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    withdrawal_id TEXT NOT NULL UNIQUE,
    order_no TEXT NOT NULL DEFAULT '',
    item_id TEXT NOT NULL DEFAULT '',
    product_code TEXT NOT NULL,
    product_name TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT '',
    qty REAL NOT NULL DEFAULT 0,
    withdraw_date TEXT NOT NULL,
    withdrawn_by TEXT NOT NULL DEFAULT '',
    supervisor_name TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS stock_movements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    movement_no TEXT NOT NULL UNIQUE,
    movement_date TEXT NOT NULL,
    movement_type TEXT NOT NULL DEFAULT 'سحب',
    order_no TEXT NOT NULL DEFAULT '',
    product_code TEXT NOT NULL DEFAULT '',
    product_name TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT '',
    qty REAL NOT NULL DEFAULT 0,
    balance_after REAL NOT NULL DEFAULT 0,
    person TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    withdrawal_id TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS counters (
    key TEXT PRIMARY KEY,
    value INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_products_category ON products(category);
CREATE INDEX IF NOT EXISTS idx_products_name ON products(product_name);
CREATE INDEX IF NOT EXISTS idx_order_items_order ON order_items(order_no);
CREATE INDEX IF NOT EXISTS idx_order_items_product ON order_items(product_code);
CREATE INDEX IF NOT EXISTS idx_withdrawals_order ON withdrawals(order_no);
CREATE INDEX IF NOT EXISTS idx_withdrawals_product ON withdrawals(product_code);
CREATE INDEX IF NOT EXISTS idx_withdrawals_date ON withdrawals(withdraw_date);
CREATE INDEX IF NOT EXISTS idx_movements_date ON stock_movements(movement_date);
CREATE INDEX IF NOT EXISTS idx_movements_product ON stock_movements(product_code);
CREATE INDEX IF NOT EXISTS idx_movements_type ON stock_movements(movement_type);
"""


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(
        str(config.DB_PATH), timeout=30, check_same_thread=False
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


@contextmanager
def get_db() -> Iterator[sqlite3.Connection]:
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()


def meta_get(conn: sqlite3.Connection, key: str) -> str:
    row = conn.execute("SELECT value FROM app_meta WHERE key = ?", (key,)).fetchone()
    return str(row["value"]) if row else ""


def meta_set(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO app_meta (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


def _text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"nan", "none", "null"} else text


def _num(value: Any, default: float = 0.0) -> float:
    try:
        text = _text(value).replace(",", "")
        return float(text) if text else default
    except (TypeError, ValueError):
        return default


def _normalize_category(value: Any) -> str:
    text = _text(value)
    if not text:
        return CATEGORY_GENERAL
    if text.upper() == "PCR":
        return "PCR"
    mapping = {
        "chemicals": "كيماويات",
        "chemical": "كيماويات",
        "كيماويات": "كيماويات",
        "office": "المكتبية",
        "stationery": "المكتبية",
        "المكتبية": "المكتبية",
        "computer": "مستلزمات الكمبيوتر",
        "computers": "مستلزمات الكمبيوتر",
        "مستلزمات الكمبيوتر": "مستلزمات الكمبيوتر",
    }
    return mapping.get(text.lower(), text)


def _snapshot_rows(source: sqlite3.Connection, sheet: str) -> list[dict[str, Any]]:
    try:
        row = source.execute(
            "SELECT payload FROM snapshot WHERE sheet = ?", (sheet,)
        ).fetchone()
    except sqlite3.Error:
        return []
    if row is None:
        return []
    try:
        data = json.loads(row[0])
    except (TypeError, ValueError):
        return []
    return data if isinstance(data, list) else []


def _migrate_offline(conn: sqlite3.Connection) -> None:
    if not config.MIGRATE_OFFLINE_DB:
        return
    if meta_get(conn, "offline_migrated"):
        return
    if conn.execute("SELECT COUNT(*) FROM products").fetchone()[0] > 0:
        with conn:
            meta_set(conn, "offline_migrated", now_str())
        return

    source_path = Path(config.OFFLINE_DB_PATH)
    if not source_path.is_file():
        return

    try:
        source = sqlite3.connect(f"file:{source_path.as_posix()}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        LOGGER.warning("offline migration: cannot open %s: %s", source_path, exc)
        return

    users = _snapshot_rows(source, "Users")
    products = _snapshot_rows(source, "Products")
    orders = _snapshot_rows(source, "Orders")
    order_items = _snapshot_rows(source, "Order_Items")
    withdrawals = _snapshot_rows(source, "Withdrawals")
    movements = _snapshot_rows(source, "Stock_Movements")
    settings = _snapshot_rows(source, "Settings")

    if not users:
        try:
            cache = source.execute(
                "SELECT username, password_hash, role, updated_at FROM auth_cache"
            ).fetchall()
            users = [
                {
                    "username": row[0],
                    "password_hash": row[1],
                    "role": row[2],
                    "created_at": row[3],
                }
                for row in cache
            ]
        except sqlite3.Error:
            users = []

    with conn:
        for user in users:
            username = _text(user.get("username"))
            password_hash = _text(user.get("password_hash"))
            if not username or not password_hash:
                continue
            conn.execute(
                "INSERT OR IGNORE INTO users (username, password_hash, role, created_at) "
                "VALUES (?, ?, ?, ?)",
                (
                    username,
                    password_hash,
                    _text(user.get("role")) or "user",
                    _text(user.get("created_at")) or now_str(),
                ),
            )

        if users and config.ADMIN_PASSWORD:
            conn.execute(
                "UPDATE users SET password_hash = ?, role = 'admin' WHERE username = ? COLLATE NOCASE",
                (hash_password(config.ADMIN_PASSWORD), config.ADMIN_USERNAME),
            )

        for product in products:
            code = _text(product.get("product_code"))
            name = _text(product.get("product_name"))
            if not code or not name:
                continue
            category = _normalize_category(product.get("category"))
            location = _text(product.get("storage_location")) or CATEGORY_STORAGE.get(
                category, ""
            )
            conn.execute(
                """
                INSERT OR IGNORE INTO products (
                    product_code, product_name, unit, current_stock, min_stock,
                    storage_location, notes, created_at, starting_stock, total_withdrawn,
                    date_added, manufacturer, supplier, expiry_date, added_by, category,
                    serial_number, device_status, units_per_carton, purchase_date,
                    last_withdraw_date, device_condition, decommission_date,
                    decommission_reason, decommissioned_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    code,
                    name,
                    _text(product.get("unit")),
                    _num(product.get("current_stock")),
                    _num(product.get("min_stock")),
                    location,
                    _text(product.get("notes")),
                    _text(product.get("created_at")) or now_str(),
                    _num(product.get("starting_stock")),
                    _num(product.get("total_withdrawn")),
                    _text(product.get("date_added")),
                    _text(product.get("manufacturer")),
                    _text(product.get("supplier")),
                    _text(product.get("expiry_date")),
                    _text(product.get("added_by")),
                    category,
                    _text(product.get("serial_number")),
                    _text(product.get("device_status")),
                    _num(product.get("units_per_carton")),
                    _text(product.get("purchase_date")),
                    _text(product.get("last_withdraw_date")),
                    _text(product.get("device_condition")),
                    _text(product.get("decommission_date")),
                    _text(product.get("decommission_reason")),
                    _text(product.get("decommissioned_by")),
                ),
            )

        for order in orders:
            order_no = _text(order.get("order_no"))
            if not order_no:
                continue
            conn.execute(
                "INSERT OR IGNORE INTO orders (order_no, order_date, factory_name, "
                "responsible_person, status, notes, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    order_no,
                    _text(order.get("order_date")),
                    _text(order.get("factory_name")),
                    _text(order.get("responsible_person")),
                    _text(order.get("status")) or ORDER_STATUS_OPEN,
                    _text(order.get("notes")),
                    _text(order.get("created_at")) or now_str(),
                ),
            )

        for index, item in enumerate(order_items, start=1):
            order_no = _text(item.get("order_no"))
            code = _text(item.get("product_code"))
            if not order_no or not code:
                continue
            item_id = _text(item.get("item_id")) or f"{order_no}-{code}-{index}"
            conn.execute(
                """
                INSERT OR IGNORE INTO order_items (
                    item_id, order_no, product_code, product_name, unit, required_qty,
                    withdrawn_qty, last_withdraw_date, last_withdrawn_by, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item_id,
                    order_no,
                    code,
                    _text(item.get("product_name")),
                    _text(item.get("unit")),
                    _num(item.get("required_qty")),
                    _num(item.get("withdrawn_qty")),
                    _text(item.get("last_withdraw_date")),
                    _text(item.get("last_withdrawn_by")),
                    _text(item.get("created_at")) or now_str(),
                ),
            )

        for index, item in enumerate(withdrawals, start=1):
            withdrawal_id = _text(item.get("withdrawal_id")) or f"W-{index:06d}"
            code = _text(item.get("product_code"))
            if not code:
                continue
            conn.execute(
                """
                INSERT OR IGNORE INTO withdrawals (
                    withdrawal_id, order_no, item_id, product_code, product_name, category,
                    qty, withdraw_date, withdrawn_by, supervisor_name, notes, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    withdrawal_id,
                    _text(item.get("order_no")),
                    _text(item.get("item_id")),
                    code,
                    _text(item.get("product_name")),
                    _normalize_category(item.get("category")),
                    _num(item.get("qty")),
                    _text(item.get("withdraw_date")) or now_str(),
                    _text(item.get("withdrawn_by")),
                    _text(item.get("supervisor_name")),
                    _text(item.get("notes")),
                    _text(item.get("created_at")) or now_str(),
                ),
            )

        max_movement = 0
        for item in movements:
            movement_no = _text(item.get("movement_no"))
            if not movement_no:
                continue
            conn.execute(
                """
                INSERT OR IGNORE INTO stock_movements (
                    movement_no, movement_date, movement_type, order_no, product_code,
                    product_name, category, qty, balance_after, person, notes,
                    withdrawal_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    movement_no,
                    _text(item.get("movement_date")) or now_str(),
                    _text(item.get("movement_type")),
                    _text(item.get("order_no")),
                    _text(item.get("product_code")),
                    _text(item.get("product_name")),
                    _normalize_category(item.get("category")),
                    _num(item.get("qty")),
                    _num(item.get("balance_after")),
                    _text(item.get("person")),
                    _text(item.get("notes")),
                    _text(item.get("withdrawal_id")),
                    _text(item.get("created_at")) or now_str(),
                ),
            )
            try:
                max_movement = max(max_movement, int(movement_no.lstrip("M")))
            except ValueError:
                pass

        setting_map: dict[str, str] = {}
        for item in settings:
            key = _text(item.get("key"))
            if key:
                value = _text(item.get("value"))
                setting_map[key] = value
                conn.execute(
                    "INSERT INTO settings (key, value) VALUES (?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (key, value),
                )
        if AUTHORITY_FORMS_SETTING not in setting_map:
            conn.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                (AUTHORITY_FORMS_SETTING, "0"),
            )

        max_order = 0
        for (order_no,) in conn.execute("SELECT order_no FROM orders").fetchall():
            try:
                max_order = max(max_order, int(str(order_no).split("-")[-1]))
            except ValueError:
                pass

        movement_seq = max_movement
        order_seq = max_order
        try:
            movement_seq = max(
                movement_seq, int(setting_map.get("last_movement_seq", "0"))
            )
        except ValueError:
            pass
        try:
            order_seq = max(order_seq, int(setting_map.get("last_order_seq", "0")))
        except ValueError:
            pass
        conn.execute(
            "INSERT INTO counters (key, value) VALUES ('movement', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = MAX(value, excluded.value)",
            (movement_seq,),
        )
        conn.execute(
            "INSERT INTO counters (key, value) VALUES ('order', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = MAX(value, excluded.value)",
            (order_seq,),
        )
        meta_set(conn, "offline_migrated", now_str())
        meta_set(conn, "offline_source", str(source_path))
        LOGGER.info(
            "offline migration complete: products=%s movements=%s users=%s",
            len(products),
            len(movements),
            len(users),
        )

    source.close()


def _bootstrap_admin(conn: sqlite3.Connection) -> None:
    count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    if count:
        return
    with conn:
        conn.execute(
            "INSERT INTO users (username, password_hash, role, created_at) VALUES (?, ?, 'admin', ?)",
            (
                config.ADMIN_USERNAME,
                hash_password(config.ADMIN_PASSWORD),
                now_str(),
            ),
        )
    LOGGER.warning(
        "created bootstrap admin %r; change ADMIN_PASSWORD in production",
        config.ADMIN_USERNAME,
    )


def init_db() -> None:
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = connect()
    try:
        conn.executescript(SCHEMA)
        conn.commit()
        _migrate_offline(conn)
        _bootstrap_admin(conn)
    finally:
        conn.close()
