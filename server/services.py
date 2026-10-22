from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime
from typing import Any

from server.constants import (
    AUTHORITY_FORMS_CODE,
    AUTHORITY_FORMS_NAME,
    AUTHORITY_FORMS_SETTING,
    AUTHORITY_RECEIPT_TYPE,
    AUTHORITY_WITHDRAWAL_LEGACY,
    AUTHORITY_WITHDRAWAL_TYPE,
    CATEGORY_CHEMICALS,
    CATEGORY_COMPUTER,
    CATEGORY_GENERAL,
    CATEGORY_OFFICE,
    CATEGORY_PCR,
    CATEGORY_STORAGE,
    DEVICE_CONDITION_DEFAULT,
    DEVICE_CONDITIONS,
    DEVICE_STATUS_DECOMMISSIONED,
    DEVICE_STATUS_DEFAULT,
    DEVICE_STATUSES,
    MOVEMENT_ADD,
    MOVEMENT_ADJUST,
    MOVEMENT_ORDER_DELETE,
    MOVEMENT_RESTORE,
    MOVEMENT_WITHDRAW,
    ORDER_STATUS_COMPLETED,
    ORDER_STATUS_OPEN,
)
from server.database import now_str, today_str
from server.security import hash_password

PRODUCT_FIELDS = [
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
]

EDITABLE_FIELDS = {
    "product_name",
    "unit",
    "min_stock",
    "storage_location",
    "notes",
    "current_stock",
    "manufacturer",
    "supplier",
    "expiry_date",
    "date_added",
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
}

NUMERIC_FIELDS = {"min_stock", "current_stock", "units_per_carton"}


def text(value: Any) -> str:
    if value is None:
        return ""
    result = str(value).strip()
    return "" if result.lower() in {"nan", "none", "null"} else result


def number(value: Any, default: float = 0.0) -> float:
    try:
        raw = text(value).replace(",", "")
        return float(raw) if raw else default
    except (TypeError, ValueError):
        return default


def normalize_category(value: Any) -> str:
    raw = text(value)
    if not raw:
        return CATEGORY_GENERAL
    if raw.upper() == "PCR":
        return CATEGORY_PCR
    aliases = {
        "chemicals": CATEGORY_CHEMICALS,
        "chemical": CATEGORY_CHEMICALS,
        "كيماويات": CATEGORY_CHEMICALS,
        "office": CATEGORY_OFFICE,
        "stationery": CATEGORY_OFFICE,
        "المكتبية": CATEGORY_OFFICE,
        "computer": CATEGORY_COMPUTER,
        "computers": CATEGORY_COMPUTER,
        "it": CATEGORY_COMPUTER,
        "مستلزمات الكمبيوتر": CATEGORY_COMPUTER,
    }
    return aliases.get(raw.lower(), raw)


def normalize_condition(value: Any, category: str) -> str:
    raw = text(value)
    if raw:
        return raw
    return DEVICE_CONDITION_DEFAULT if category == CATEGORY_COMPUTER else ""


def normalize_status(value: Any, category: str) -> str:
    raw = text(value)
    if raw:
        return raw
    return DEVICE_STATUS_DEFAULT if category == CATEGORY_PCR else ""


def normalize_timestamp(value: Any = "") -> str:
    raw = text(value)
    if not raw:
        return now_str()
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", ""))
        return parsed.strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(raw[:19], fmt).strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
    return now_str()


def normalize_date(value: Any = "") -> str:
    return normalize_timestamp(value)[:10]


def _serialize_product(row: sqlite3.Row | dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    item = dict(row)
    item["current_stock"] = number(item.get("current_stock"))
    item["min_stock"] = number(item.get("min_stock"))
    item["starting_stock"] = number(item.get("starting_stock"))
    item["total_withdrawn"] = number(item.get("total_withdrawn"))
    item["units_per_carton"] = number(item.get("units_per_carton"))
    item["is_low"] = item["current_stock"] <= item["min_stock"]
    item["available"] = item["current_stock"] > 0
    return item


def get_product(conn: sqlite3.Connection, code: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM products WHERE product_code = ? COLLATE NOCASE",
        (text(code),),
    ).fetchone()
    return _serialize_product(row)


def list_products(
    conn: sqlite3.Connection,
    category: str = "",
    search: str = "",
    low_only: bool = False,
    decommissioned: bool | None = None,
) -> list[dict[str, Any]]:
    sql = "SELECT * FROM products WHERE 1=1"
    params: list[Any] = []
    if category:
        sql += " AND category = ?"
        params.append(normalize_category(category))
    if search:
        term = f"%{text(search)}%"
        sql += (
            " AND (product_code LIKE ? OR product_name LIKE ? "
            "OR serial_number LIKE ? OR notes LIKE ? OR storage_location LIKE ?)"
        )
        params.extend([term, term, term, term, term])
    if low_only:
        sql += " AND current_stock <= min_stock"
    if decommissioned is True:
        sql += " AND device_status = ?"
        params.append(DEVICE_STATUS_DECOMMISSIONED)
    elif decommissioned is False:
        sql += " AND device_status <> ?"
        params.append(DEVICE_STATUS_DECOMMISSIONED)
    sql += " ORDER BY category, product_name COLLATE NOCASE, product_code"
    rows = conn.execute(sql, params).fetchall()
    return [_serialize_product(row) for row in rows]


def _product_values(data: dict[str, Any], creating: bool, actor: str) -> dict[str, Any]:
    code = text(data.get("product_code"))
    name = text(data.get("product_name"))
    category = normalize_category(data.get("category"))
    location = text(data.get("storage_location")) or CATEGORY_STORAGE.get(category, "")
    current_stock = number(data.get("current_stock"))
    values = {
        "product_code": code,
        "product_name": name,
        "unit": text(data.get("unit")),
        "current_stock": current_stock,
        "min_stock": number(data.get("min_stock")),
        "storage_location": location,
        "notes": text(data.get("notes")),
        "created_at": now_str() if creating else text(data.get("created_at")) or now_str(),
        "starting_stock": current_stock if creating else number(data.get("starting_stock")),
        "total_withdrawn": 0.0 if creating else number(data.get("total_withdrawn")),
        "date_added": text(data.get("date_added")) or today_str(),
        "manufacturer": text(data.get("manufacturer")),
        "supplier": text(data.get("supplier")),
        "expiry_date": text(data.get("expiry_date")),
        "added_by": text(data.get("added_by")) or (actor if creating else ""),
        "category": category,
        "serial_number": text(data.get("serial_number")),
        "device_status": normalize_status(data.get("device_status"), category),
        "units_per_carton": number(data.get("units_per_carton")),
        "purchase_date": text(data.get("purchase_date")),
        "last_withdraw_date": text(data.get("last_withdraw_date")),
        "device_condition": normalize_condition(data.get("device_condition"), category),
        "decommission_date": text(data.get("decommission_date")),
        "decommission_reason": text(data.get("decommission_reason")),
        "decommissioned_by": text(data.get("decommissioned_by")),
    }
    return values


def create_product(
    conn: sqlite3.Connection, data: dict[str, Any], actor: str
) -> dict[str, Any]:
    values = _product_values(data, True, actor)
    if not values["product_code"]:
        raise ValueError("كود الصنف مطلوب.")
    if not values["product_name"]:
        raise ValueError("اسم الصنف مطلوب.")
    if values["current_stock"] < 0 or values["min_stock"] < 0:
        raise ValueError("الكمية لا يمكن أن تكون سالبة.")
    exists = conn.execute(
        "SELECT 1 FROM products WHERE product_code = ? COLLATE NOCASE",
        (values["product_code"],),
    ).fetchone()
    if exists:
        raise ValueError(f"كود الصنف {values['product_code']} موجود مسبقاً.")
    with conn:
        columns = ", ".join(values.keys())
        placeholders = ", ".join("?" for _ in values)
        conn.execute(
            f"INSERT INTO products ({columns}) VALUES ({placeholders})",
            tuple(values.values()),
        )
        if values["current_stock"] > 0:
            _record_movement(
                conn,
                order_no="",
                product_code=values["product_code"],
                product_name=values["product_name"],
                category=values["category"],
                qty=values["current_stock"],
                balance_after=values["current_stock"],
                person=values["added_by"] or "إضافة صنف ابتدائي",
                movement_type=MOVEMENT_ADD,
                notes="رصيد افتتاحي عند إنشاء الصنف",
            )
    return get_product(conn, values["product_code"])  # type: ignore[return-value]


def update_product(
    conn: sqlite3.Connection,
    code: str,
    data: dict[str, Any],
    actor: str,
) -> dict[str, Any]:
    existing = get_product(conn, code)
    if not existing:
        raise ValueError("الصنف غير موجود.")
    updates = {key: value for key, value in data.items() if key in EDITABLE_FIELDS}
    if not updates and "product_name" not in data:
        return existing
    merged = dict(existing)
    merged.update(updates)
    category = normalize_category(merged.get("category"))
    if not text(merged.get("product_name")):
        raise ValueError("اسم الصنف مطلوب.")
    new_stock = number(merged.get("current_stock"))
    min_stock = number(merged.get("min_stock"))
    if new_stock < 0 or min_stock < 0:
        raise ValueError("الكمية لا يمكن أن تكون سالبة.")
    if not text(merged.get("storage_location")):
        merged["storage_location"] = CATEGORY_STORAGE.get(category, "")
    merged["category"] = category
    merged["device_status"] = normalize_status(merged.get("device_status"), category)
    merged["device_condition"] = normalize_condition(
        merged.get("device_condition"), category
    )

    fields = [
        "product_name",
        "unit",
        "current_stock",
        "min_stock",
        "storage_location",
        "notes",
        "date_added",
        "manufacturer",
        "supplier",
        "expiry_date",
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
    ]
    assignments = ", ".join(f"{field} = ?" for field in fields)
    params = [merged.get(field) for field in fields]
    for index, field in enumerate(fields):
        if field in NUMERIC_FIELDS:
            params[index] = number(params[index])

    stock_delta = new_stock - number(existing.get("current_stock"))
    with conn:
        conn.execute(
            f"UPDATE products SET {assignments} WHERE product_code = ? COLLATE NOCASE",
            (*params, existing["product_code"]),
        )
        if abs(stock_delta) > 1e-9:
            _record_movement(
                conn,
                order_no="",
                product_code=existing["product_code"],
                product_name=text(merged.get("product_name")),
                category=category,
                qty=stock_delta,
                balance_after=new_stock,
                person=actor,
                movement_type=MOVEMENT_ADJUST,
                notes="تعديل رصيد يدوي من شاشة الأصناف",
            )
    return get_product(conn, existing["product_code"])  # type: ignore[return-value]


def delete_product(
    conn: sqlite3.Connection, code: str, force: bool = False
) -> dict[str, Any]:
    product = get_product(conn, code)
    if not product:
        raise ValueError("الصنف غير موجود.")
    related = conn.execute(
        "SELECT COUNT(*) FROM order_items WHERE product_code = ? COLLATE NOCASE",
        (product["product_code"],),
    ).fetchone()[0]
    if related and not force:
        raise ValueError(
            "الصنف مرتبط بطلبات سابقة. استخدم الحذف النهائي مع تأكيد صريح."
        )
    with conn:
        conn.execute(
            "DELETE FROM products WHERE product_code = ? COLLATE NOCASE",
            (product["product_code"],),
        )
    return {"deleted": True, "product_code": product["product_code"]}


def decommission_device(
    conn: sqlite3.Connection,
    source: str,
    product_code: str,
    decommission_date: str = "",
    reason: str = "",
    person: str = "",
) -> dict[str, Any]:
    category = normalize_category(source)
    if category not in {CATEGORY_PCR, CATEGORY_COMPUTER}:
        raise ValueError("مصدر التكهين يجب أن يكون PCR أو مستلزمات الكمبيوتر.")
    product = get_product(conn, product_code)
    if not product:
        raise ValueError("الجهاز غير موجود.")
    if product["category"] != category:
        raise ValueError("الجهاز لا يتبع القسم المحدد.")
    if product.get("device_status") == DEVICE_STATUS_DECOMMISSIONED:
        raise ValueError("الجهاز مكهّن مسبقاً.")
    reason = text(reason)
    person = text(person)
    if not reason:
        raise ValueError("سبب التكهين مطلوب.")
    if not person:
        raise ValueError("اسم القائم بالتكهين مطلوب.")
    with conn:
        conn.execute(
            """
            UPDATE products SET device_status = ?, decommission_date = ?,
                decommission_reason = ?, decommissioned_by = ?
            WHERE product_code = ? COLLATE NOCASE
            """,
            (
                DEVICE_STATUS_DECOMMISSIONED,
                normalize_date(decommission_date),
                reason,
                person,
                product["product_code"],
            ),
        )
    return get_product(conn, product["product_code"])  # type: ignore[return-value]


def list_decommissioned(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM products WHERE device_status = ? ORDER BY decommission_date DESC",
        (DEVICE_STATUS_DECOMMISSIONED,),
    ).fetchall()
    return [_serialize_product(row) for row in rows]


def _next_counter(conn: sqlite3.Connection, key: str, prefix: str, width: int) -> str:
    row = conn.execute("SELECT value FROM counters WHERE key = ?", (key,)).fetchone()
    value = int(row[0]) + 1 if row else 1
    conn.execute(
        "INSERT INTO counters (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
    return f"{prefix}{value:0{width}d}"


def _record_movement(
    conn: sqlite3.Connection,
    *,
    order_no: str,
    product_code: str,
    product_name: str,
    category: str,
    qty: float,
    balance_after: float,
    person: str,
    movement_type: str,
    notes: str = "",
    movement_date: str = "",
    withdrawal_id: str = "",
) -> str:
    movement_no = _next_counter(conn, "movement", "M", 4)
    conn.execute(
        """
        INSERT INTO stock_movements (
            movement_no, movement_date, movement_type, order_no, product_code,
            product_name, category, qty, balance_after, person, notes,
            withdrawal_id, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            movement_no,
            normalize_timestamp(movement_date),
            movement_type,
            order_no,
            product_code,
            product_name,
            category,
            number(qty),
            number(balance_after),
            person,
            notes,
            withdrawal_id,
            now_str(),
        ),
    )
    return movement_no


def _withdrawal_record(
    conn: sqlite3.Connection,
    *,
    product: dict[str, Any],
    qty: float,
    person: str,
    supervisor: str,
    notes: str,
    withdraw_date: str,
    order_no: str = "",
    item_id: str = "",
) -> dict[str, Any]:
    current_stock = number(product.get("current_stock"))
    if qty <= 0:
        raise ValueError("الكمية المسحوبة يجب أن تكون أكبر من صفر.")
    if qty > current_stock + 1e-9:
        raise ValueError(f"الكمية المطلوبة أكبر من الرصيد المتاح ({current_stock:g}).")
    person = text(person)
    if not person:
        raise ValueError("اسم الساحب / المستخدم مطلوب.")
    stamp = normalize_timestamp(withdraw_date)
    new_stock = current_stock - qty
    new_total = number(product.get("total_withdrawn")) + qty
    withdrawal_id = f"W-{product['product_code']}-{uuid.uuid4().hex[:10]}"

    conn.execute(
        """
        UPDATE products SET current_stock = ?, total_withdrawn = ?, last_withdraw_date = ?
        WHERE product_code = ? COLLATE NOCASE
        """,
        (new_stock, new_total, stamp, product["product_code"]),
    )
    conn.execute(
        """
        INSERT INTO withdrawals (
            withdrawal_id, order_no, item_id, product_code, product_name, category,
            qty, withdraw_date, withdrawn_by, supervisor_name, notes, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            withdrawal_id,
            order_no,
            item_id,
            product["product_code"],
            product["product_name"],
            product.get("category", ""),
            qty,
            stamp,
            person,
            text(supervisor),
            text(notes),
            now_str(),
        ),
    )
    _record_movement(
        conn,
        order_no=order_no,
        product_code=product["product_code"],
        product_name=product["product_name"],
        category=product.get("category", ""),
        qty=qty,
        balance_after=new_stock,
        person=person,
        movement_type=MOVEMENT_WITHDRAW,
        movement_date=stamp,
        notes=text(notes) or f"عملية سحب {withdrawal_id}",
        withdrawal_id=withdrawal_id,
    )
    return {
        "withdrawal_id": withdrawal_id,
        "product_code": product["product_code"],
        "product_name": product["product_name"],
        "qty": qty,
        "balance_after": new_stock,
        "withdraw_date": stamp,
    }


def withdraw_product(
    conn: sqlite3.Connection,
    *,
    product_code: str,
    product_name: str,
    qty: float,
    person: str,
    withdraw_date: str = "",
    supervisor: str = "",
    notes: str = "",
    order_no: str = "",
    item_id: str = "",
) -> dict[str, Any]:
    name = text(product_name)
    if not text(product_code):
        raise ValueError("كود الصنف مطلوب.")
    if not name:
        raise ValueError("اسم الصنف مطلوب.")
    product = get_product(conn, product_code)
    if not product:
        raise ValueError("الصنف غير موجود.")
    if text(product["product_name"]).casefold() != name.casefold():
        raise ValueError("اسم الصنف لا يطابق الكود المحدد.")
    if qty <= 0:
        raise ValueError("الكمية المسحوبة يجب أن تكون أكبر من صفر.")

    with conn:
        if order_no and item_id:
            order = conn.execute(
                "SELECT * FROM orders WHERE order_no = ?", (order_no,)
            ).fetchone()
            if order is None:
                raise ValueError("الطلبية غير موجودة.")
            if order["status"] == ORDER_STATUS_COMPLETED:
                raise ValueError("لا يمكن السحب من طلبية مكتملة.")
            item = conn.execute(
                "SELECT * FROM order_items WHERE item_id = ? AND order_no = ?",
                (item_id, order_no),
            ).fetchone()
            if item is None:
                raise ValueError("بند الطلبية غير موجود.")
            remaining = number(item["required_qty"]) - number(item["withdrawn_qty"])
            if qty > remaining + 1e-9:
                raise ValueError(f"الكمية أكبر من المتبقي في الطلبية ({remaining:g}).")
            conn.execute(
                """
                UPDATE order_items SET withdrawn_qty = ?, last_withdraw_date = ?,
                    last_withdrawn_by = ?
                WHERE item_id = ?
                """,
                (
                    number(item["withdrawn_qty"]) + qty,
                    normalize_timestamp(withdraw_date),
                    text(person),
                    item_id,
                ),
            )
        result = _withdrawal_record(
            conn,
            product=product,
            qty=qty,
            person=person,
            supervisor=supervisor,
            notes=notes,
            withdraw_date=withdraw_date,
            order_no=order_no,
            item_id=item_id,
        )
        result["is_low"] = result["balance_after"] <= number(product.get("min_stock"))
    return result


def withdraw_chemical(
    conn: sqlite3.Connection, product_code: str, **kwargs: Any
) -> dict[str, Any]:
    product = get_product(conn, product_code)
    if not product or product["category"] != CATEGORY_CHEMICALS:
        raise ValueError("الصنف ليس مادة كيميائية.")
    kwargs.pop("product_name", None)
    return withdraw_product(conn, product_code=product_code, product_name=product["product_name"], **kwargs)


def withdraw_office(
    conn: sqlite3.Connection, product_code: str, **kwargs: Any
) -> dict[str, Any]:
    product = get_product(conn, product_code)
    if not product or product["category"] != CATEGORY_OFFICE:
        raise ValueError("الصنف ليس من المكتبية.")
    kwargs.pop("product_name", None)
    return withdraw_product(conn, product_code=product_code, product_name=product["product_name"], **kwargs)


def withdraw_computer(
    conn: sqlite3.Connection, product_code: str, **kwargs: Any
) -> dict[str, Any]:
    product = get_product(conn, product_code)
    if not product or product["category"] != CATEGORY_COMPUTER:
        raise ValueError("الصنف ليس من مستلزمات الكمبيوتر.")
    kwargs.pop("product_name", None)
    return withdraw_product(conn, product_code=product_code, product_name=product["product_name"], **kwargs)


def list_withdrawals(
    conn: sqlite3.Connection,
    *,
    category: str = "",
    search: str = "",
    date_from: str = "",
    date_to: str = "",
    limit: int = 500,
) -> list[dict[str, Any]]:
    sql = """
        SELECT w.*, COALESCE(NULLIF(w.category, ''), p.category, '') AS resolved_category
        FROM withdrawals w
        LEFT JOIN products p ON p.product_code = w.product_code COLLATE NOCASE
        WHERE 1=1
    """
    params: list[Any] = []
    if category:
        sql += " AND COALESCE(NULLIF(w.category, ''), p.category, '') = ?"
        params.append(normalize_category(category))
    if search:
        term = f"%{text(search)}%"
        sql += " AND (w.product_name LIKE ? OR w.product_code LIKE ? OR w.withdrawn_by LIKE ?)"
        params.extend([term, term, term])
    if date_from:
        sql += " AND substr(w.withdraw_date, 1, 10) >= ?"
        params.append(date_from[:10])
    if date_to:
        sql += " AND substr(w.withdraw_date, 1, 10) <= ?"
        params.append(date_to[:10])
    sql += " ORDER BY w.withdraw_date DESC, w.id DESC LIMIT ?"
    params.append(max(1, min(limit, 5000)))
    rows = conn.execute(sql, params).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["qty"] = number(item.get("qty"))
        item["category"] = item.get("resolved_category") or item.get("category") or ""
        result.append(item)
    return result


def delete_withdrawal(conn: sqlite3.Connection, withdrawal_id: str) -> dict[str, Any]:
    row = conn.execute(
        "SELECT * FROM withdrawals WHERE withdrawal_id = ?", (text(withdrawal_id),)
    ).fetchone()
    if row is None:
        raise ValueError("عملية السحب غير موجودة.")
    record = dict(row)
    qty = number(record["qty"])
    product = get_product(conn, record["product_code"])
    with conn:
        if product:
            new_stock = number(product["current_stock"]) + qty
            conn.execute(
                """
                UPDATE products SET current_stock = ?,
                    total_withdrawn = MAX(0, total_withdrawn - ?)
                WHERE product_code = ? COLLATE NOCASE
                """,
                (new_stock, qty, product["product_code"]),
            )
            _record_movement(
                conn,
                order_no=text(record.get("order_no")),
                product_code=product["product_code"],
                product_name=product["product_name"],
                category=product.get("category", ""),
                qty=-qty,
                balance_after=new_stock,
                person=text(record.get("withdrawn_by")),
                movement_type=MOVEMENT_RESTORE,
                notes=f"إلغاء السحب {withdrawal_id}",
            )
        if record.get("item_id"):
            item = conn.execute(
                "SELECT * FROM order_items WHERE item_id = ?", (record["item_id"],)
            ).fetchone()
            if item:
                conn.execute(
                    "UPDATE order_items SET withdrawn_qty = MAX(0, withdrawn_qty - ?) WHERE item_id = ?",
                    (qty, record["item_id"]),
                )
        conn.execute("DELETE FROM withdrawals WHERE withdrawal_id = ?", (withdrawal_id,))
    return {"deleted": True, "withdrawal_id": withdrawal_id, "restored_qty": qty}


def list_movements(
    conn: sqlite3.Connection,
    *,
    category: str = "",
    search: str = "",
    date_from: str = "",
    date_to: str = "",
    movement_type: str = "",
    limit: int = 500,
) -> list[dict[str, Any]]:
    sql = """
        SELECT m.*, COALESCE(NULLIF(m.category, ''), p.category, '') AS resolved_category
        FROM stock_movements m
        LEFT JOIN products p ON p.product_code = m.product_code COLLATE NOCASE
        WHERE 1=1
    """
    params: list[Any] = []
    if category:
        sql += " AND COALESCE(NULLIF(m.category, ''), p.category, '') = ?"
        params.append(normalize_category(category))
    if search:
        term = f"%{text(search)}%"
        sql += " AND (m.product_name LIKE ? OR m.product_code LIKE ? OR m.person LIKE ? OR m.notes LIKE ?)"
        params.extend([term, term, term, term])
    if date_from:
        sql += " AND substr(m.movement_date, 1, 10) >= ?"
        params.append(date_from[:10])
    if date_to:
        sql += " AND substr(m.movement_date, 1, 10) <= ?"
        params.append(date_to[:10])
    if movement_type:
        sql += " AND m.movement_type = ?"
        params.append(movement_type)
    sql += " ORDER BY m.movement_date DESC, m.id DESC LIMIT ?"
    params.append(max(1, min(limit, 5000)))
    rows = conn.execute(sql, params).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["qty"] = number(item.get("qty"))
        item["balance_after"] = number(item.get("balance_after"))
        item["category"] = item.get("resolved_category") or item.get("category") or ""
        result.append(item)
    return result


def create_order(
    conn: sqlite3.Connection,
    order_date: str,
    factory_name: str,
    responsible_person: str,
    notes: str = "",
) -> dict[str, Any]:
    factory_name = text(factory_name)
    responsible_person = text(responsible_person)
    if not factory_name:
        raise ValueError("اسم المصنع / الجهة مطلوب.")
    if not responsible_person:
        raise ValueError("اسم المسؤول مطلوب.")
    with conn:
        order_no = _next_counter(conn, "order", "ORD-", 4)
        conn.execute(
            """
            INSERT INTO orders (order_no, order_date, factory_name, responsible_person,
                status, notes, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                order_no,
                text(order_date) or today_str(),
                factory_name,
                responsible_person,
                ORDER_STATUS_OPEN,
                text(notes),
                now_str(),
            ),
        )
    return get_order(conn, order_no)  # type: ignore[return-value]


def list_orders(conn: sqlite3.Connection, status: str = "") -> list[dict[str, Any]]:
    sql = """
        SELECT o.*,
            COUNT(i.id) AS items_count,
            COALESCE(SUM(MAX(i.required_qty - i.withdrawn_qty, 0)), 0) AS remaining_qty,
            COALESCE(SUM(i.required_qty), 0) AS required_total
        FROM orders o
        LEFT JOIN order_items i ON i.order_no = o.order_no
        WHERE 1=1
    """
    params: list[Any] = []
    if status:
        sql += " AND o.status = ?"
        params.append(status)
    sql += " GROUP BY o.id ORDER BY o.created_at DESC, o.id DESC"
    rows = conn.execute(sql, params).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["items_count"] = int(item.get("items_count") or 0)
        item["remaining_qty"] = number(item.get("remaining_qty"))
        item["required_total"] = number(item.get("required_total"))
        result.append(item)
    return result


def get_order(conn: sqlite3.Connection, order_no: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM orders WHERE order_no = ?", (text(order_no),)
    ).fetchone()
    if row is None:
        return None
    order = dict(row)
    items = conn.execute(
        "SELECT * FROM order_items WHERE order_no = ? ORDER BY id", (order["order_no"],)
    ).fetchall()
    order["items"] = []
    for item in items:
        entry = dict(item)
        entry["required_qty"] = number(entry["required_qty"])
        entry["withdrawn_qty"] = number(entry["withdrawn_qty"])
        entry["remaining_qty"] = max(
            0.0, entry["required_qty"] - entry["withdrawn_qty"]
        )
        order["items"].append(entry)
    order["withdrawals"] = [
        dict(item)
        for item in conn.execute(
            "SELECT * FROM withdrawals WHERE order_no = ? ORDER BY withdraw_date DESC",
            (order["order_no"],),
        ).fetchall()
    ]
    return order


def add_order_item(
    conn: sqlite3.Connection,
    order_no: str,
    product_code: str,
    product_name: str,
    required_qty: float,
    unit: str = "",
) -> dict[str, Any]:
    order = get_order(conn, order_no)
    if not order:
        raise ValueError("الطلبية غير موجودة.")
    if order["status"] == ORDER_STATUS_COMPLETED:
        raise ValueError("لا يمكن تعديل طلبية مكتملة.")
    code = text(product_code)
    if not code:
        raise ValueError("كود الصنف مطلوب.")
    qty = number(required_qty)
    if qty <= 0:
        raise ValueError("الكمية المطلوبة يجب أن تكون أكبر من صفر.")
    product = get_product(conn, code)
    name = text(product_name) or (product["product_name"] if product else code)
    unit = text(unit) or (product["unit"] if product else "")
    existing = conn.execute(
        "SELECT 1 FROM order_items WHERE order_no = ? AND product_code = ? COLLATE NOCASE",
        (order["order_no"], code),
    ).fetchone()
    if existing:
        raise ValueError("الصنف مضاف مسبقاً لهذه الطلبية.")
    item_id = f"{order['order_no']}-{code}-{uuid.uuid4().hex[:8]}"
    with conn:
        conn.execute(
            """
            INSERT INTO order_items (item_id, order_no, product_code, product_name, unit,
                required_qty, withdrawn_qty, last_withdraw_date, last_withdrawn_by, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 0, '', '', ?)
            """,
            (item_id, order["order_no"], code, name, unit, qty, now_str()),
        )
    return get_order(conn, order["order_no"])  # type: ignore[return-value]


def remove_order_item(
    conn: sqlite3.Connection, order_no: str, item_id: str
) -> dict[str, Any]:
    item = conn.execute(
        "SELECT * FROM order_items WHERE order_no = ? AND item_id = ?",
        (text(order_no), text(item_id)),
    ).fetchone()
    if item is None:
        raise ValueError("بند الطلبية غير موجود.")
    if number(item["withdrawn_qty"]) > 0:
        raise ValueError("لا يمكن حذف بند تم السحب منه. ألغِ عمليات السحب أولاً.")
    with conn:
        conn.execute("DELETE FROM order_items WHERE item_id = ?", (item_id,))
    return {"deleted": True, "item_id": item_id}


def set_order_status(
    conn: sqlite3.Connection, order_no: str, status: str
) -> dict[str, Any]:
    if status not in {ORDER_STATUS_OPEN, ORDER_STATUS_COMPLETED}:
        raise ValueError("حالة الطلبية غير صحيحة.")
    order = get_order(conn, order_no)
    if not order:
        raise ValueError("الطلبية غير موجودة.")
    with conn:
        conn.execute(
            "UPDATE orders SET status = ? WHERE order_no = ?", (status, order_no)
        )
    return get_order(conn, order_no)  # type: ignore[return-value]


def delete_order(conn: sqlite3.Connection, order_no: str) -> dict[str, Any]:
    order = get_order(conn, order_no)
    if not order:
        raise ValueError("الطلبية غير موجودة.")
    withdrawals = conn.execute(
        "SELECT * FROM withdrawals WHERE order_no = ?", (order_no,)
    ).fetchall()
    restored = 0.0
    with conn:
        for row in withdrawals:
            record = dict(row)
            qty = number(record["qty"])
            product = get_product(conn, record["product_code"])
            if product and qty > 0:
                new_stock = number(product["current_stock"]) + qty
                conn.execute(
                    """
                    UPDATE products SET current_stock = ?,
                        total_withdrawn = MAX(0, total_withdrawn - ?)
                    WHERE product_code = ? COLLATE NOCASE
                    """,
                    (new_stock, qty, product["product_code"]),
                )
                _record_movement(
                    conn,
                    order_no=order_no,
                    product_code=product["product_code"],
                    product_name=product["product_name"],
                    category=product.get("category", ""),
                    qty=-qty,
                    balance_after=new_stock,
                    person=text(record.get("withdrawn_by")),
                    movement_type=MOVEMENT_ORDER_DELETE,
                    notes=f"إرجاع كمية عند حذف الطلبية {order_no}",
                )
                restored += qty
        conn.execute("DELETE FROM withdrawals WHERE order_no = ?", (order_no,))
        conn.execute("DELETE FROM order_items WHERE order_no = ?", (order_no,))
        conn.execute("DELETE FROM orders WHERE order_no = ?", (order_no,))
    return {"deleted": True, "order_no": order_no, "restored_qty": restored}


def pending_for_product(
    conn: sqlite3.Connection, product_code: str, current_order_no: str = ""
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT i.order_no, o.order_date, o.factory_name, i.required_qty, i.withdrawn_qty
        FROM order_items i
        JOIN orders o ON o.order_no = i.order_no
        WHERE i.product_code = ? COLLATE NOCASE
          AND i.required_qty > i.withdrawn_qty
          AND o.status = ?
          AND (? = '' OR i.order_no <> ?)
        ORDER BY o.order_date
        """,
        (text(product_code), ORDER_STATUS_OPEN, text(current_order_no), text(current_order_no)),
    ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["required_qty"] = number(item["required_qty"])
        item["withdrawn_qty"] = number(item["withdrawn_qty"])
        item["remaining_qty"] = max(
            0.0, item["required_qty"] - item["withdrawn_qty"]
        )
        result.append(item)
    return result


def get_settings(conn: sqlite3.Connection) -> dict[str, str]:
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    return {str(row["key"]): str(row["value"]) for row in rows}


def set_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, str(value)),
    )


def get_authority_forms_count(conn: sqlite3.Connection) -> float:
    row = conn.execute(
        "SELECT value FROM settings WHERE key = ?", (AUTHORITY_FORMS_SETTING,)
    ).fetchone()
    return number(row["value"]) if row else 0.0


def get_authority_items(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT
            CASE WHEN TRIM(product_name) = '' THEN '' ELSE product_name END AS item_name,
            CASE WHEN TRIM(product_code) = '' THEN ? ELSE product_code END AS item_code,
            SUM(CASE WHEN movement_type = ? THEN qty ELSE 0 END) AS received_qty,
            SUM(CASE WHEN movement_type IN (?, ?) THEN qty ELSE 0 END) AS withdrawn_qty
        FROM stock_movements
        WHERE movement_type IN (?, ?, ?)
        GROUP BY item_name, item_code
        ORDER BY item_name
        """,
        (
            AUTHORITY_FORMS_CODE,
            AUTHORITY_RECEIPT_TYPE,
            AUTHORITY_WITHDRAWAL_TYPE,
            AUTHORITY_WITHDRAWAL_LEGACY,
            AUTHORITY_RECEIPT_TYPE,
            AUTHORITY_WITHDRAWAL_TYPE,
            AUTHORITY_WITHDRAWAL_LEGACY,
        ),
    ).fetchall()
    items = []
    for row in rows:
        item = dict(row)
        if not text(item["item_name"]):
            continue
        item["received_qty"] = number(item["received_qty"])
        item["withdrawn_qty"] = number(item["withdrawn_qty"])
        item["available_qty"] = max(
            0.0, item["received_qty"] - item["withdrawn_qty"]
        )
        items.append(item)
    if not items:
        current = get_authority_forms_count(conn)
        if current > 0:
            items.append(
                {
                    "item_name": AUTHORITY_FORMS_NAME,
                    "item_code": AUTHORITY_FORMS_CODE,
                    "received_qty": current,
                    "withdrawn_qty": 0.0,
                    "available_qty": current,
                }
            )
    return items


def receive_authority(
    conn: sqlite3.Connection,
    *,
    item_name: str,
    item_code: str,
    qty: float,
    receipt_date: str,
    receiver: str,
    notes: str = "",
) -> dict[str, Any]:
    name = text(item_name)
    code = text(item_code) or AUTHORITY_FORMS_CODE
    receiver = text(receiver)
    if not name:
        raise ValueError("اسم الصنف مطلوب.")
    if qty <= 0:
        raise ValueError("الكمية المستلمة يجب أن تكون أكبر من صفر.")
    if not receiver:
        raise ValueError("اسم المستلم مطلوب.")
    with conn:
        current = get_authority_forms_count(conn)
        new_count = current + qty
        set_setting(conn, AUTHORITY_FORMS_SETTING, f"{new_count:g}")
        _record_movement(
            conn,
            order_no="",
            product_code=code,
            product_name=name,
            category="",
            qty=qty,
            balance_after=new_count,
            person=receiver,
            movement_type=AUTHORITY_RECEIPT_TYPE,
            movement_date=receipt_date,
            notes=text(notes),
        )
    return {"count": new_count, "items": get_authority_items(conn)}


def withdraw_authority(
    conn: sqlite3.Connection,
    *,
    item_name: str,
    item_code: str,
    qty: float,
    username: str,
    withdrawal_date: str,
    notes: str = "",
) -> dict[str, Any]:
    name = text(item_name)
    code = text(item_code)
    username = text(username)
    if not name:
        raise ValueError("اسم الصنف مطلوب.")
    if not code:
        raise ValueError("كود الصنف مطلوب.")
    if qty <= 0:
        raise ValueError("الكمية المصروفة يجب أن تكون أكبر من صفر.")
    if not username:
        raise ValueError("اسم المستخدم مطلوب.")
    items = get_authority_items(conn)
    match = next(
        (
            item
            for item in items
            if item["item_name"] == name and item["item_code"] == code
        ),
        None,
    )
    if match is None:
        raise ValueError("الصنف غير موجود في سجل استمارات الهيئة.")
    available = number(match["available_qty"])
    if qty > available + 1e-9:
        raise ValueError(f"الكمية أكبر من المتاح لهذا الصنف ({available:g}).")
    with conn:
        current = get_authority_forms_count(conn)
        if qty > current + 1e-9:
            raise ValueError(f"الكمية أكبر من إجمالي الرصيد ({current:g}).")
        new_count = current - qty
        set_setting(conn, AUTHORITY_FORMS_SETTING, f"{new_count:g}")
        _record_movement(
            conn,
            order_no="",
            product_code=code,
            product_name=name,
            category="",
            qty=qty,
            balance_after=new_count,
            person=username,
            movement_type=AUTHORITY_WITHDRAWAL_TYPE,
            movement_date=withdrawal_date,
            notes=text(notes),
        )
    return {"count": new_count, "items": get_authority_items(conn)}


def delete_authority_item(
    conn: sqlite3.Connection, item_name: str, item_code: str
) -> dict[str, Any]:
    name = text(item_name)
    code = text(item_code) or AUTHORITY_FORMS_CODE
    if not name:
        raise ValueError("اسم الصنف مطلوب.")
    receipts = conn.execute(
        """
        SELECT * FROM stock_movements
        WHERE movement_type = ?
          AND TRIM(product_name) = ?
          AND (CASE WHEN TRIM(product_code) = '' THEN ? ELSE product_code END) = ?
        """,
        (AUTHORITY_RECEIPT_TYPE, name, AUTHORITY_FORMS_CODE, code),
    ).fetchall()
    if not receipts:
        raise ValueError("لا توجد سجلات وارد لهذا الصنف.")
    withdrawals = conn.execute(
        """
        SELECT * FROM stock_movements
        WHERE movement_type IN (?, ?)
          AND TRIM(product_name) = ?
          AND (CASE WHEN TRIM(product_code) = '' THEN ? ELSE product_code END) = ?
        """,
        (AUTHORITY_WITHDRAWAL_TYPE, AUTHORITY_WITHDRAWAL_LEGACY, name, AUTHORITY_FORMS_CODE, code),
    ).fetchall()
    received_qty = sum(number(row["qty"]) for row in receipts)
    withdrawn_qty = sum(number(row["qty"]) for row in withdrawals)
    net_qty = max(0.0, received_qty - withdrawn_qty)
    movement_ids = [row["id"] for row in receipts] + [row["id"] for row in withdrawals]
    with conn:
        placeholders = ", ".join("?" for _ in movement_ids)
        conn.execute(
            f"DELETE FROM stock_movements WHERE id IN ({placeholders})", movement_ids
        )
        current = get_authority_forms_count(conn)
        deduction = min(net_qty, max(current, 0.0))
        set_setting(conn, AUTHORITY_FORMS_SETTING, f"{current - deduction:g}")
    return {
        "deleted": True,
        "item_name": name,
        "item_code": code,
        "removed_movements": len(movement_ids),
        "deducted_qty": deduction,
        "count": get_authority_forms_count(conn),
    }


def authority_snapshot(conn: sqlite3.Connection) -> dict[str, Any]:
    receipts = list_movements(
        conn, movement_type=AUTHORITY_RECEIPT_TYPE, limit=5000
    )
    withdrawals = [
        item
        for item in list_movements(conn, limit=5000)
        if item["movement_type"] in {AUTHORITY_WITHDRAWAL_TYPE, AUTHORITY_WITHDRAWAL_LEGACY}
    ]
    return {
        "count": get_authority_forms_count(conn),
        "items": get_authority_items(conn),
        "receipts": receipts,
        "withdrawals": withdrawals,
    }


def dashboard_metrics(conn: sqlite3.Connection) -> dict[str, Any]:
    products = list_products(conn)
    orders = list_orders(conn)
    low = [item for item in products if item["is_low"]]
    open_orders = [item for item in orders if item["status"] == ORDER_STATUS_OPEN]
    pending_items = sum(
        1
        for order in open_orders
        for item in (get_order(conn, order["order_no"]) or {}).get("items", [])
        if item["remaining_qty"] > 0
    )
    category_counts: dict[str, int] = {}
    category_stock: dict[str, float] = {}
    for item in products:
        category = item["category"] or CATEGORY_GENERAL
        category_counts[category] = category_counts.get(category, 0) + 1
        category_stock[category] = category_stock.get(category, 0.0) + item["current_stock"]
    recent_movements = list_movements(conn, limit=8)
    return {
        "total_products": len(products),
        "total_stock": sum(item["current_stock"] for item in products),
        "total_orders": len(orders),
        "open_orders": len(open_orders),
        "pending_items": pending_items,
        "low_stock_count": len(low),
        "authority_forms_count": get_authority_forms_count(conn),
        "category_counts": category_counts,
        "category_stock": category_stock,
        "low_stock": low[:8],
        "recent_movements": recent_movements,
    }


def report_summary(
    conn: sqlite3.Connection, date_from: str = "", date_to: str = ""
) -> dict[str, Any]:
    products = list_products(conn)
    withdrawals = list_withdrawals(
        conn, date_from=date_from, date_to=date_to, limit=5000
    )
    movements = list_movements(
        conn, date_from=date_from, date_to=date_to, limit=5000
    )
    receipts = [
        item for item in movements if item["movement_type"] == AUTHORITY_RECEIPT_TYPE
    ]
    return {
        "products_count": len(products),
        "total_stock": sum(item["current_stock"] for item in products),
        "low_stock_count": sum(1 for item in products if item["is_low"]),
        "withdrawals_count": len(withdrawals),
        "withdrawals_qty": sum(item["qty"] for item in withdrawals),
        "authority_receipts_qty": sum(item["qty"] for item in receipts),
        "movements_count": len(movements),
        "authority_forms_count": get_authority_forms_count(conn),
    }


def report_movements(
    conn: sqlite3.Connection,
    *,
    date_from: str = "",
    date_to: str = "",
    category: str = "",
    search: str = "",
    movement_type: str = "",
) -> list[dict[str, Any]]:
    return list_movements(
        conn,
        date_from=date_from,
        date_to=date_to,
        category=category,
        search=search,
        movement_type=movement_type,
        limit=5000,
    )


def report_withdrawals(
    conn: sqlite3.Connection,
    *,
    date_from: str = "",
    date_to: str = "",
    category: str = "",
    search: str = "",
) -> list[dict[str, Any]]:
    return list_withdrawals(
        conn,
        date_from=date_from,
        date_to=date_to,
        category=category,
        search=search,
        limit=5000,
    )


def list_users(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT id, username, role, created_at FROM users ORDER BY username"
    ).fetchall()
    return [dict(row) for row in rows]


def add_user(
    conn: sqlite3.Connection, username: str, password: str, role: str = "user"
) -> dict[str, Any]:
    username = text(username)
    password = str(password or "")
    role = text(role) or "user"
    if not username:
        raise ValueError("اسم المستخدم مطلوب.")
    if len(password) < 4:
        raise ValueError("كلمة المرور يجب أن تكون 4 أحرف على الأقل.")
    if role not in {"admin", "user"}:
        raise ValueError("الدور غير صالح.")
    exists = conn.execute(
        "SELECT 1 FROM users WHERE username = ? COLLATE NOCASE", (username,)
    ).fetchone()
    if exists:
        raise ValueError(f"اسم المستخدم {username} موجود مسبقاً.")
    with conn:
        conn.execute(
            "INSERT INTO users (username, password_hash, role, created_at) VALUES (?, ?, ?, ?)",
            (username, hash_password(password), role, now_str()),
        )
    return {
        "username": username,
        "role": role,
        "created_at": now_str(),
    }


def delete_user(conn: sqlite3.Connection, username: str, actor: str) -> dict[str, Any]:
    user = conn.execute(
        "SELECT * FROM users WHERE username = ? COLLATE NOCASE", (text(username),)
    ).fetchone()
    if user is None:
        raise ValueError("المستخدم غير موجود.")
    if text(user["username"]).casefold() == text(actor).casefold():
        raise ValueError("لا يمكن حذف المستخدم الحالي.")
    admins = conn.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'").fetchone()[0]
    if user["role"] == "admin" and admins <= 1:
        raise ValueError("لا يمكن حذف آخر مدير للنظام.")
    with conn:
        conn.execute("DELETE FROM users WHERE id = ?", (user["id"],))
    return {"deleted": True, "username": user["username"]}


def reset_password(
    conn: sqlite3.Connection, username: str, new_password: str
) -> dict[str, Any]:
    if len(str(new_password or "")) < 4:
        raise ValueError("كلمة المرور يجب أن تكون 4 أحرف على الأقل.")
    user = conn.execute(
        "SELECT * FROM users WHERE username = ? COLLATE NOCASE", (text(username),)
    ).fetchone()
    if user is None:
        raise ValueError("المستخدم غير موجود.")
    with conn:
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (hash_password(new_password), user["id"]),
        )
    return {"reset": True, "username": user["username"]}


def set_user_role(
    conn: sqlite3.Connection, username: str, role: str
) -> dict[str, Any]:
    role = text(role)
    if role not in {"admin", "user"}:
        raise ValueError("الدور غير صالح.")
    user = conn.execute(
        "SELECT * FROM users WHERE username = ? COLLATE NOCASE", (text(username),)
    ).fetchone()
    if user is None:
        raise ValueError("المستخدم غير موجود.")
    admins = conn.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'").fetchone()[0]
    if user["role"] == "admin" and role != "admin" and admins <= 1:
        raise ValueError("لا يمكن تغيير دور آخر مدير للنظام.")
    with conn:
        conn.execute("UPDATE users SET role = ? WHERE id = ?", (role, user["id"]))
    return {"username": user["username"], "role": role}


def meta_payload() -> dict[str, Any]:
    return {
        "categories": [
            CATEGORY_GENERAL,
            CATEGORY_PCR,
            CATEGORY_CHEMICALS,
            CATEGORY_OFFICE,
            CATEGORY_COMPUTER,
        ],
        "category_storage": CATEGORY_STORAGE,
        "device_statuses": DEVICE_STATUSES,
        "device_conditions": DEVICE_CONDITIONS,
        "authority": {
            "code": AUTHORITY_FORMS_CODE,
            "name": AUTHORITY_FORMS_NAME,
            "receipt_type": AUTHORITY_RECEIPT_TYPE,
            "withdrawal_type": AUTHORITY_WITHDRAWAL_TYPE,
        },
        "order_statuses": {
            "open": ORDER_STATUS_OPEN,
            "completed": ORDER_STATUS_COMPLETED,
        },
        "movement_types": [
            MOVEMENT_ADD,
            MOVEMENT_WITHDRAW,
            MOVEMENT_ADJUST,
            MOVEMENT_RESTORE,
            MOVEMENT_ORDER_DELETE,
            AUTHORITY_RECEIPT_TYPE,
            AUTHORITY_WITHDRAWAL_TYPE,
        ],
    }
