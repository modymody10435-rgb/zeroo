"""منطق الأعمال: الأصناف، الطلبات، السحب، وحركة المخزن."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from core.config import SHEETS, load_config
from core.gsheets import (
    DataError,
    append_row,
    clear_rows_where,
    clear_sheet_rows,
    count_rows_where,
    delete_row,
    delete_rows_where,
    invalidate_cache,
    read_sheet,
    sync_row,
    to_number,
    update_row,
)


PRODUCT_CATEGORY_GENERAL = "عام"
PRODUCT_CATEGORY_PCR = "PCR"
PRODUCT_CATEGORY_CHEMICALS = "كيماويات"
PRODUCT_CATEGORY_OFFICE = "المكتبية"
PRODUCT_CATEGORY_COMPUTER = "مستلزمات الكمبيوتر"
PRODUCT_CATEGORIES = [
    PRODUCT_CATEGORY_GENERAL,
    PRODUCT_CATEGORY_PCR,
    PRODUCT_CATEGORY_CHEMICALS,
    PRODUCT_CATEGORY_OFFICE,
    PRODUCT_CATEGORY_COMPUTER,
]
PCR_STORAGE_SECTION = "قسم PCR"
CHEMICALS_STORAGE_SECTION = "قسم الكيماويات"
OFFICE_STORAGE_SECTION = "قسم المكتبية"
COMPUTER_STORAGE_SECTION = "قسم مستلزمات الكمبيوتر"
DEVICE_CONDITIONS = ["جديد", "قديم"]
DEVICE_CONDITION_DEFAULT = DEVICE_CONDITIONS[0]
AUTHORITY_FORMS_SETTING = "authority_forms_stock"
AUTHORITY_FORMS_CODE = "AUTHORITY_FORMS"
AUTHORITY_FORMS_NAME = "استمارات الهيئة"
AUTHORITY_FORMS_RECEIPT_TYPE = "وارد استمارات الهيئة"
AUTHORITY_FORMS_WITHDRAWAL_TYPE = "صرف استمارات الهيئة"
AUTHORITY_FORMS_WITHDRAWAL_TYPE_LEGACY = "سحب استمارات الهيئة"
DEVICE_STATUSES = [
    "جاهز",
    "قيد الاستخدام",
    "تحت الصيانة",
    "معطل",
    "تالف",
    "خارج الخدمة",
    "مكهن",
]
DEVICE_STATUS_DEFAULT = DEVICE_STATUSES[0]
DEVICE_STATUS_DECOMMISSIONED = "مكهن"


def normalize_category(value: Any) -> str:
    """يوحّد تصنيف الصنف: فارغ = عام، وقيمة PCR بأي حالة أحرف = PCR."""
    text = str(value or "").strip()
    if not text:
        return PRODUCT_CATEGORY_GENERAL
    if text.upper() == PRODUCT_CATEGORY_PCR:
        return PRODUCT_CATEGORY_PCR
    if text.lower() in ("chemicals", "chemical", PRODUCT_CATEGORY_CHEMICALS):
        return PRODUCT_CATEGORY_CHEMICALS
    if text.lower() in (
        "office",
        "stationery",
        "office supplies",
        PRODUCT_CATEGORY_OFFICE,
        "مكتبية",
        "المكتبات",
    ):
        return PRODUCT_CATEGORY_OFFICE
    if text.lower() in (
        "computer",
        "computers",
        "it",
        "computer supplies",
        PRODUCT_CATEGORY_COMPUTER,
        "كمبيوتر",
        "حاسوب",
    ):
        return PRODUCT_CATEGORY_COMPUTER
    return text


def is_pcr_category(value: Any) -> bool:
    return normalize_category(value).upper() == PRODUCT_CATEGORY_PCR


def normalize_device_status(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


def normalize_device_condition(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def current_user_safe() -> str:
    """اسم المستخدم الحالي دون تعطيل العملية إن لم توجد جلسة."""
    try:
        from core.auth import current_username

        return str(current_username() or "").strip()
    except Exception:
        return ""


def normalize_timestamp(value: str = "") -> str:
    """يُرجع طابعًا زمنيًا كاملًا بالصيغة YYYY-MM-DD HH:MM:SS."""
    raw = str(value or "").strip()
    if not raw:
        return now_str()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(raw[:19], fmt).strftime("%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError):
            continue
    return now_str()


def _key() -> str:
    cfg = load_config()
    if not cfg.spreadsheet_key:
        raise DataError("لم يتم إعداد مفتاح Google Sheet في الإعدادات (secrets.toml).")
    return cfg.spreadsheet_key


# --------------------------------------------------------------------------- #
#                          الإعدادات العامة (عدادات الأرقام)
# --------------------------------------------------------------------------- #
def get_settings() -> Dict[str, str]:
    df = read_sheet(_key(), SHEETS["settings"])
    return dict(zip(df["key"].astype(str), df["value"].astype(str)))


def set_setting(key: str, value: str) -> None:
    df = read_sheet(_key(), SHEETS["settings"])
    exists = df[df["key"].astype(str) == key]
    if not exists.empty:
        update_row(_key(), SHEETS["settings"], "key", key, {"value": value})
    else:
        append_row(_key(), SHEETS["settings"], {"key": key, "value": value})


def get_authority_forms_count() -> float:
    """العدد الحالي المتاح من استمارات الهيئة."""
    return to_number(get_settings().get(AUTHORITY_FORMS_SETTING, "0"))


def receive_authority_forms(
    item_name: str,
    qty: float,
    receipt_date: str = "",
    receiver: str = "",
    item_code: str = "",
    notes: str = "",
) -> Tuple[bool, str]:
    """تسجيل كمية واردة من استمارات الهيئة وزيادة العدد المتاح تلقائيًا."""
    item_name = str(item_name or "").strip()
    if not item_name:
        return False, "اسم الصنف مطلوب."
    qty = to_number(qty, -1)
    if qty <= 0:
        return False, "الكمية المستلمة يجب أن تكون أكبر من صفر."
    receiver = str(receiver or "").strip()
    if not receiver:
        return False, "اسم المستلم مطلوب."

    current = get_authority_forms_count()
    new_qty = current + qty
    set_setting(AUTHORITY_FORMS_SETTING, f"{new_qty:g}")
    stamp = normalize_timestamp(receipt_date)
    record_movement(
        order_no="",
        product_code=str(item_code or "").strip() or AUTHORITY_FORMS_CODE,
        product_name=item_name,
        qty=qty,
        balance_after=new_qty,
        person=receiver,
        movement_type=AUTHORITY_FORMS_RECEIPT_TYPE,
        movement_date=stamp,
        notes=str(notes or "").strip(),
    )
    return (
        True,
        f"تم تسجيل استلام {qty:g} من «{item_name}». العدد المتاح: {new_qty:g}.",
    )


def withdraw_authority_forms(
    item_name: str,
    item_code: str,
    qty: float,
    username: str,
    withdrawal_date: str = "",
    notes: str = "",
) -> Tuple[bool, str]:
    """تسجيل كمية مصروفة من صنف استمارات الهيئة وخصمها من المخزون."""
    item_name = str(item_name or "").strip()
    if not item_name:
        return False, "اسم الصنف مطلوب."
    item_code = str(item_code or "").strip()
    if not item_code:
        return False, "كود الصنف مطلوب."
    qty = to_number(qty, -1)
    if qty <= 0:
        return False, "الكمية المصروفة يجب أن تكون أكبر من صفر."
    username = str(username or "").strip()
    if not username:
        return False, "اسم المستخدم القائم بالصرف مطلوب."

    items = get_authority_form_items()
    matched = items[
        (items["item_name"].astype(str) == item_name)
        & (items["item_code"].astype(str) == item_code)
    ]
    if matched.empty:
        return False, "الصنف المحدد أو كوده غير متاح في المخزون."
    available = to_number(matched.iloc[0].get("available_qty"))
    if qty > available + 1e-9:
        return False, f"الكمية المصروفة أكبر من المتاح من الصنف ({available:g})."

    current = get_authority_forms_count()
    if qty > current + 1e-9:
        return False, f"الكمية المصروفة أكبر من العدد المتاح ({current:g})."
    new_qty = current - qty
    set_setting(AUTHORITY_FORMS_SETTING, f"{new_qty:g}")
    stamp = normalize_timestamp(withdrawal_date)
    record_movement(
        order_no="",
        product_code=item_code,
        product_name=item_name,
        qty=qty,
        balance_after=new_qty,
        person=username,
        movement_type=AUTHORITY_FORMS_WITHDRAWAL_TYPE,
        movement_date=stamp,
        notes=str(notes or "").strip(),
    )
    return (
        True,
        f"تم صرف {qty:g} من «{item_name}». العدد المتبقي: {new_qty:g}.",
    )


def get_authority_form_receipts() -> pd.DataFrame:
    """سجل الكميات الواردة من الهيئة."""
    movements = get_movements()
    if movements.empty:
        return movements
    mask = movements["movement_type"].apply(
        lambda value: str(value or "").strip() == AUTHORITY_FORMS_RECEIPT_TYPE
    )
    return movements[mask].copy()


def get_authority_form_withdrawals() -> pd.DataFrame:
    """سجل الكميات المصروفة من استمارات الهيئة، بما يشمل السجلات القديمة."""
    movements = get_movements()
    if movements.empty:
        return movements
    allowed = {
        AUTHORITY_FORMS_WITHDRAWAL_TYPE,
        AUTHORITY_FORMS_WITHDRAWAL_TYPE_LEGACY,
    }
    mask = movements["movement_type"].apply(
        lambda value: str(value or "").strip() in allowed
    )
    return movements[mask].copy()


def get_authority_form_items() -> pd.DataFrame:
    """أصناف استمارات الهيئة المتاحة مع أكوادها وأرصدة الوارد والصرف."""
    columns = [
        "item_name",
        "item_code",
        "received_qty",
        "withdrawn_qty",
        "available_qty",
    ]
    receipts = get_authority_form_receipts()
    if receipts.empty:
        current = get_authority_forms_count()
        if current <= 0:
            return pd.DataFrame(columns=columns)
        return pd.DataFrame(
            [
                {
                    "item_name": AUTHORITY_FORMS_NAME,
                    "item_code": AUTHORITY_FORMS_CODE,
                    "received_qty": current,
                    "withdrawn_qty": 0.0,
                    "available_qty": current,
                }
            ],
            columns=columns,
        )

    received = receipts.copy()
    received["item_name"] = received["product_name"].fillna("").astype(str).str.strip()
    received["item_code"] = (
        received["product_code"]
        .fillna("")
        .astype(str)
        .str.strip()
        .replace("", AUTHORITY_FORMS_CODE)
    )
    received["qty"] = received["qty"].apply(to_number)
    received = received[received["item_name"] != ""]
    grouped = (
        received.groupby(["item_name", "item_code"], as_index=False)["qty"]
        .sum()
        .rename(columns={"qty": "received_qty"})
    )

    withdrawals = get_authority_form_withdrawals()
    if withdrawals.empty:
        grouped["withdrawn_qty"] = 0.0
    else:
        issued = withdrawals.copy()
        issued["item_name"] = issued["product_name"].fillna("").astype(str).str.strip()
        issued["item_code"] = (
            issued["product_code"]
            .fillna("")
            .astype(str)
            .str.strip()
            .replace("", AUTHORITY_FORMS_CODE)
        )
        issued["qty"] = issued["qty"].apply(to_number)
        issued = issued[issued["item_name"] != ""]
        issued = (
            issued.groupby(["item_name", "item_code"], as_index=False)["qty"]
            .sum()
            .rename(columns={"qty": "withdrawn_qty"})
        )
        grouped = grouped.merge(
            issued, on=["item_name", "item_code"], how="left"
        )
        grouped["withdrawn_qty"] = grouped["withdrawn_qty"].fillna(0.0)

    grouped["available_qty"] = (
        grouped["received_qty"] - grouped["withdrawn_qty"]
    ).clip(lower=0.0)
    return grouped[columns]


def delete_authority_form_item(
    item_name: str, item_code: str
) -> Tuple[bool, str]:
    """حذف صنف استمارات الهيئة وسجلات وارداته وصرفه من Google Sheets."""
    item_name = str(item_name or "").strip()
    item_code = str(item_code or "").strip() or AUTHORITY_FORMS_CODE
    if not item_name:
        return False, "اسم الصنف مطلوب."

    def matches(frame: pd.DataFrame) -> pd.DataFrame:
        if frame.empty:
            return frame
        names = frame["product_name"].fillna("").astype(str).str.strip()
        codes = (
            frame["product_code"]
            .fillna("")
            .astype(str)
            .str.strip()
            .replace("", AUTHORITY_FORMS_CODE)
        )
        return frame[(names == item_name) & (codes == item_code)].copy()

    receipts = matches(get_authority_form_receipts())
    if receipts.empty:
        return False, "لم يتم العثور على واردات مسجلة لهذا الصنف."
    withdrawals = matches(get_authority_form_withdrawals())
    received_qty = sum(receipts["qty"].apply(to_number))
    withdrawn_qty = (
        sum(withdrawals["qty"].apply(to_number)) if not withdrawals.empty else 0.0
    )
    net_qty = max(received_qty - withdrawn_qty, 0.0)

    records = pd.concat([receipts, withdrawals], ignore_index=True)
    movement_nos = [
        str(value).strip()
        for value in records.get("movement_no", pd.Series(dtype=str)).tolist()
        if str(value).strip().lower() not in ("", "nan", "none")
    ]
    if not movement_nos:
        return False, "تعذر تحديد سجلات الحركة المرتبطة بالصنف."

    failed = 0
    for movement_no in dict.fromkeys(movement_nos):
        try:
            if not delete_row(
                _key(), SHEETS["stock_movements"], "movement_no", movement_no
            ):
                failed += 1
        except Exception:  # noqa: BLE001
            failed += 1
    invalidate_cache()

    if failed:
        return (
            False,
            f"تعذر حذف {failed} سجل حركة من Google Sheets. لم يتم تعديل رصيد الاستمارات؛ أعد المحاولة.",
        )

    current = get_authority_forms_count()
    deduction = min(net_qty, max(current, 0.0))
    set_setting(AUTHORITY_FORMS_SETTING, f"{current - deduction:g}")
    return (
        True,
        f"تم حذف صنف «{item_name}» ({item_code}) وسجلاته من Google Sheets، "
        f"وخُصم {deduction:g} من رصيد استمارات الهيئة.",
    )


def _next_sequence(prefix_key: str, sheet: str) -> int:
    settings = get_settings()
    seq = int(to_number(settings.get(prefix_key, "0")))
    df = read_sheet(_key(), sheet)
    return max(seq, len(df)) + 1


def next_order_no() -> str:
    settings = get_settings()
    seq = int(to_number(settings.get("last_order_seq", "0")))
    df = read_sheet(_key(), SHEETS["orders"])
    seq = max(seq, len(df)) + 1
    set_setting("last_order_seq", str(seq))
    return f"ORD-{seq:04d}"


def next_movement_no() -> str:
    settings = get_settings()
    seq = int(to_number(settings.get("last_movement_seq", "0")))
    df = read_sheet(_key(), SHEETS["stock_movements"])
    seq = max(seq, len(df)) + 1
    set_setting("last_movement_seq", str(seq))
    return f"M{seq:04d}"


# --------------------------------------------------------------------------- #
#                                  الأصناف
# --------------------------------------------------------------------------- #
def get_products() -> pd.DataFrame:
    return read_sheet(_key(), SHEETS["products"])


def products_by_category(category: str) -> pd.DataFrame:
    """أصناف تصنيف معيّن (قسم المخزن) — فارغ إذا لم توجد."""
    products = get_products()
    if products.empty:
        return products
    target = normalize_category(category).upper()
    mask = products["category"].apply(lambda value: normalize_category(value).upper() == target)
    return products[mask].copy()


def get_pcr_products() -> pd.DataFrame:
    return products_by_category(PRODUCT_CATEGORY_PCR)


def get_chemical_products() -> pd.DataFrame:
    return products_by_category(PRODUCT_CATEGORY_CHEMICALS)


def get_office_products() -> pd.DataFrame:
    return products_by_category(PRODUCT_CATEGORY_OFFICE)


def get_computer_products() -> pd.DataFrame:
    return products_by_category(PRODUCT_CATEGORY_COMPUTER)


def find_product(product_code: str) -> Optional[Dict[str, Any]]:
    df = get_products()
    if df.empty:
        return None
    rows = df[
        df["product_code"].astype(str).str.strip().str.lower()
        == str(product_code).strip().lower()
    ]
    if rows.empty:
        return None
    return rows.iloc[0].to_dict()


def add_product(data: Dict[str, Any]) -> Tuple[bool, str]:
    code = str(data.get("product_code", "")).strip()
    name = str(data.get("product_name", "")).strip()
    if not code:
        return False, "كود الصنف مطلوب."
    if not name:
        return False, "اسم الصنف مطلوب."
    if find_product(code):
        return False, f"كود الصنف {code} موجود مسبقًا."
    start_qty = to_number(data.get("current_stock", 0))
    date_added = str(data.get("date_added", "")).strip() or now_str()
    category = normalize_category(data.get("category"))
    location = str(data.get("storage_location", "")).strip()
    if not location:
        if category == PRODUCT_CATEGORY_PCR:
            location = PCR_STORAGE_SECTION
        elif category == PRODUCT_CATEGORY_CHEMICALS:
            location = CHEMICALS_STORAGE_SECTION
        elif category == PRODUCT_CATEGORY_OFFICE:
            location = OFFICE_STORAGE_SECTION
        elif category == PRODUCT_CATEGORY_COMPUTER:
            location = COMPUTER_STORAGE_SECTION
    device_status = normalize_device_status(
        data.get("device_status"),
        DEVICE_STATUS_DEFAULT if category == PRODUCT_CATEGORY_PCR else "",
    )
    row = {
        "product_code": code,
        "product_name": name,
        "unit": str(data.get("unit", "")).strip(),
        "current_stock": start_qty,
        "min_stock": to_number(data.get("min_stock", 0)),
        "storage_location": location,
        "notes": str(data.get("notes", "")).strip(),
        "created_at": now_str(),
        "starting_stock": start_qty,
        "total_withdrawn": 0,
        "date_added": date_added,
        "manufacturer": str(data.get("manufacturer", "")).strip(),
        "supplier": str(data.get("supplier", "")).strip(),
        "expiry_date": str(data.get("expiry_date", "")).strip(),
        "added_by": current_user_safe(),
        "category": category,
        "serial_number": str(data.get("serial_number", "")).strip(),
        "device_status": device_status,
        "units_per_carton": to_number(data.get("units_per_carton", 0)),
        "purchase_date": str(data.get("purchase_date", "")).strip(),
        "last_withdraw_date": str(data.get("last_withdraw_date", "")).strip(),
        "device_condition": normalize_device_condition(
            data.get("device_condition"),
            DEVICE_CONDITION_DEFAULT if category == PRODUCT_CATEGORY_COMPUTER else "",
        ),
        "decommission_date": "",
        "decommission_reason": "",
        "decommissioned_by": "",
    }
    append_row(_key(), SHEETS["products"], row)
    if count_rows_where(_key(), SHEETS["products"], "product_code", code) == 0:
        return False, f"تعذر حفظ الصنف {name} في Google Sheets — لم يتم العثور على الصف بعد الإضافة."
    sync_row(_key(), SHEETS["products"], "product_code", code, row)
    if row["current_stock"] > 0:
        record_movement(
            order_no="",
            product_code=code,
            product_name=name,
            qty=row["current_stock"],
            balance_after=row["current_stock"],
            person="إضافة صنف ابتدائي",
            movement_type="إضافة رصيد",
            notes="رصيد افتتاحي عند إنشاء الصنف",
        )
    msg = f"تم إضافة الصنف {name} بنجاح."
    if row["added_by"]:
        msg += f" 👤 أضافه: {row['added_by']}."
    if row["notes"]:
        msg += " 📝 تم حفظ ملاحظات الصنف في Google Sheets."
    return True, msg


def update_product(code: str, updates: Dict[str, Any]) -> Tuple[bool, str]:
    allowed = {
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
    clean = {k: v for k, v in updates.items() if k in allowed}
    for k in ("min_stock", "current_stock", "units_per_carton"):
        if k in clean:
            clean[k] = to_number(clean[k])
    for k in ("purchase_date", "last_withdraw_date", "decommission_date"):
        if k in clean:
            clean[k] = str(clean[k] or "").strip()
    for k in ("decommission_reason", "decommissioned_by"):
        if k in clean:
            clean[k] = str(clean[k] or "").strip()
    if "serial_number" in clean:
        clean["serial_number"] = str(clean["serial_number"] or "").strip()
    if "category" in clean:
        clean["category"] = normalize_category(clean["category"])
    if "device_status" in clean:
        default_status = (
            DEVICE_STATUS_DEFAULT
            if clean.get("category") == PRODUCT_CATEGORY_PCR
            else ""
        )
        clean["device_status"] = normalize_device_status(clean["device_status"], default_status)
    if "device_condition" in clean:
        condition_default = (
            DEVICE_CONDITION_DEFAULT
            if clean.get("category") == PRODUCT_CATEGORY_COMPUTER
            else ""
        )
        clean["device_condition"] = normalize_device_condition(
            clean["device_condition"], condition_default
        )
    default_location = ""
    if clean.get("category") == PRODUCT_CATEGORY_PCR:
        default_location = PCR_STORAGE_SECTION
    elif clean.get("category") == PRODUCT_CATEGORY_CHEMICALS:
        default_location = CHEMICALS_STORAGE_SECTION
    elif clean.get("category") == PRODUCT_CATEGORY_OFFICE:
        default_location = OFFICE_STORAGE_SECTION
    elif clean.get("category") == PRODUCT_CATEGORY_COMPUTER:
        default_location = COMPUTER_STORAGE_SECTION
    if default_location:
        if "storage_location" in clean:
            if not str(clean["storage_location"] or "").strip():
                clean["storage_location"] = default_location
        else:
            current = find_product(code)
            if current and not str(current.get("storage_location", "") or "").strip():
                clean["storage_location"] = default_location
    ok = update_row(_key(), SHEETS["products"], "product_code", code, clean)
    return (ok, "تم تحديث الصنف." if ok else "لم يتم العثور على الصنف.")


def decommission_device(
    source: str,
    product_code: str,
    decommission_date: str = "",
    reason: str = "",
    person: str = "",
) -> Tuple[bool, str]:
    """تسجيل تكهين جهاز من PCR أو مستلزمات الكمبيوتر وتحديث حالته إلى مكهن."""
    category = normalize_category(source)
    if category not in (PRODUCT_CATEGORY_PCR, PRODUCT_CATEGORY_COMPUTER):
        return False, "مصدر الجهاز يجب أن يكون PCR أو مستلزمات الكمبيوتر."
    code = str(product_code or "").strip()
    if not code:
        return False, "اختيار الجهاز مطلوب."
    reason = str(reason or "").strip()
    if not reason:
        return False, "سبب التكهين مطلوب."
    person = str(person or "").strip()
    if not person:
        return False, "اسم القائم بالتكهين مطلوب."

    product = find_product(code)
    if not product:
        return False, "لم يتم العثور على الجهاز المحدد."
    if normalize_category(product.get("category")) != category:
        return False, "الجهاز المحدد لا ينتمي إلى المصدر المختار."
    if normalize_device_status(product.get("device_status")) == DEVICE_STATUS_DECOMMISSIONED:
        return False, "هذا الجهاز مكهن مسبقًا."

    date_value = normalize_timestamp(decommission_date)[:10]
    ok, msg = update_product(
        code,
        {
            "device_status": DEVICE_STATUS_DECOMMISSIONED,
            "decommission_date": date_value,
            "decommission_reason": reason,
            "decommissioned_by": person,
        },
    )
    if not ok:
        return False, msg
    name = str(product.get("product_name") or "").strip()
    return True, f"تم تكهين «{name or code}» وتحديث حالته إلى {DEVICE_STATUS_DECOMMISSIONED}."


def delete_product(code: str, force: bool = False) -> Tuple[bool, str]:
    """حذف صنف من المخزن: يحذف صفوفه من Google Sheets نفسها، لا من الواجهة فقط.

    إن كان مرتبطًا بطلبات نطلب التأكيد (force=True).
    """
    code = str(code).strip()
    product = find_product(code)
    if not product:
        return False, "لم يتم العثور على الصنف."
    items = get_order_items()
    related = (
        items[items["product_code"].astype(str).str.strip() == code]
        if not items.empty
        else items
    )
    if not related.empty and not force:
        orders = sorted(set(related["order_no"].astype(str).tolist()))
        return (
            False,
            f"الصنف مرتبط بـ {len(related)} بند في الطلبيات: {', '.join(orders)}. "
            "أكّد الحذف لإزالة الصنف من قائمة المخزن (سجل الطلبات يبقى محفوظًا).",
        )

    sheet = SHEETS["products"]
    try:
        deleted = delete_rows_where(_key(), sheet, "product_code", code)
    except Exception:
        deleted = 0
    if deleted == 0:
        try:
            deleted = 1 if delete_row(_key(), sheet, "product_code", code) else 0
        except Exception:
            deleted = 0

    remaining = count_rows_where(_key(), sheet, "product_code", code)
    cleared = 0
    if remaining:
        try:
            cleared = clear_rows_where(_key(), sheet, "product_code", code)
        except Exception:
            cleared = 0
        remaining = count_rows_where(_key(), sheet, "product_code", code)

    invalidate_cache()
    if remaining:
        return (
            False,
            f"تعذر حذف الصنف {code} من Google Sheets: ما زال {remaining} صف مطابق في الشيت.",
        )
    if find_product(code) is not None:
        return False, f"تعذر مزامنة Google Sheets: الصنف {code} ما زال ظاهرًا في التطبيق بعد الحذف."

    parts = []
    if deleted:
        parts.append(f"حُذف {deleted} صف")
    if cleared:
        parts.append(f"أُفرغ {cleared} صف")
    detail = f" ({'، '.join(parts)})" if parts else ""
    return True, (
        f"تم حذف الصنف {product['product_name']} نهائيًا من Google Sheets{detail}. "
        "✅ تحقّق مباشر بقراءة حديثة من الشيت: 0 صف متبقٍ لهذا الكود."
    )


def clear_test_data() -> Tuple[bool, str]:
    """مسح كل البيانات التجريبية: الأصناف وسجل السحوبات (يبقى صف العناوين فقط)."""
    try:
        cleared = 0
        for sheet in (SHEETS["products"], SHEETS["withdrawals"]):
            cleared += clear_sheet_rows(_key(), sheet)
        return True, f"تم مسح {cleared} صف من البيانات التجريبية."
    except DataError as exc:
        return False, str(exc)
    except Exception as exc:  # noqa: BLE001
        return False, f"تعذر مسح البيانات التجريبية: {exc}"


def product_notes_map() -> Dict[str, str]:
    df = get_products()
    mapping: Dict[str, str] = {}
    if df.empty or "product_code" not in df.columns:
        return mapping
    notes_col = df["notes"] if "notes" in df.columns else pd.Series([""] * len(df))
    for code, note in zip(df["product_code"], notes_col):
        key = str(code).strip()
        if not key:
            continue
        mapping[key] = "" if pd.isna(note) else str(note).strip()
    return mapping


def low_stock_products() -> pd.DataFrame:
    df = get_products()
    if df.empty:
        return df
    df = df.copy()
    df["_stock"] = df["current_stock"].apply(to_number)
    df["_min"] = df["min_stock"].apply(to_number)
    return df[df["_stock"] <= df["_min"]]


# --------------------------------------------------------------------------- #
#                                  الطلبات
# --------------------------------------------------------------------------- #
def get_orders() -> pd.DataFrame:
    return read_sheet(_key(), SHEETS["orders"])


def get_order_items() -> pd.DataFrame:
    df = read_sheet(_key(), SHEETS["order_items"])
    if not df.empty:
        df["_required"] = df["required_qty"].apply(to_number)
        df["_withdrawn"] = df["withdrawn_qty"].apply(to_number)
        df["_remaining"] = (df["_required"] - df["_withdrawn"]).clip(lower=0)
    return df


def create_order(date: str, factory: str, responsible: str, notes: str = "") -> Tuple[bool, str, str]:
    if not str(factory).strip():
        return False, "اسم المعمل أو القسم مطلوب.", ""
    if not str(responsible).strip():
        return False, "اسم المسؤول مطلوب.", ""
    order_no = next_order_no()
    row = {
        "order_no": order_no,
        "order_date": date or today_str(),
        "factory_name": str(factory).strip(),
        "responsible_person": str(responsible).strip(),
        "status": "مفتوحة",
        "notes": str(notes).strip(),
        "created_at": now_str(),
    }
    append_row(_key(), SHEETS["orders"], row)
    return True, f"تم إنشاء الطلبية {order_no}.", order_no


def get_order(order_no: str) -> Optional[Dict[str, Any]]:
    df = get_orders()
    if df.empty:
        return None
    rows = df[df["order_no"].astype(str) == str(order_no)]
    if rows.empty:
        return None
    return rows.iloc[0].to_dict()


def order_items(order_no: str) -> pd.DataFrame:
    df = get_order_items()
    if df.empty:
        return df
    return df[df["order_no"].astype(str) == str(order_no)]


def add_order_item(order_no: str, code: str, name: str, required: float, unit: str = "") -> Tuple[bool, str]:
    code = str(code).strip()
    name = str(name).strip()
    if not code:
        return False, "كود الصنف مطلوب."
    if required is None or to_number(required, -1) <= 0:
        return False, "الكمية المطلوبة يجب أن تكون أكبر من صفر."
    if not name:
        product = find_product(code)
        name = product["product_name"] if product else code
    items = order_items(order_no)
    if not items.empty:
        same = items[items["product_code"].astype(str).str.strip() == code]
        if not same.empty:
            return False, f"هذا الصنف مضاف مسبقًا لنفس الطلبية (كود {code})."
    item_id = f"{order_no}-{code}-{datetime.now().strftime('%H%M%S%f')[:9]}"
    row = {
        "item_id": item_id,
        "order_no": order_no,
        "product_code": code,
        "product_name": name,
        "unit": unit,
        "required_qty": to_number(required),
        "withdrawn_qty": 0,
        "last_withdraw_date": "",
        "last_withdrawn_by": "",
        "created_at": now_str(),
    }
    append_row(_key(), SHEETS["order_items"], row)
    return True, f"تم إضافة الصنف {name} إلى الطلبية."


def previous_pending_for_product(code: str, current_order_no: str) -> List[Dict[str, Any]]:
    """الطلبات الأقدم غير المكتملة لنفس الصنف."""
    items = get_order_items()
    orders = get_orders()
    if items.empty:
        return []
    remaining = items[
        (items["product_code"].astype(str).str.strip() == str(code).strip())
        & (items["_remaining"] > 0)
        & (items["order_no"].astype(str) != str(current_order_no))
    ]
    if remaining.empty:
        return []
    result: List[Dict[str, Any]] = []
    for _, item in remaining.iterrows():
        order_no = str(item["order_no"])
        order = orders[orders["order_no"].astype(str) == order_no]
        if order.empty:
            continue
        o = order.iloc[0]
        if str(o.get("status", "")) == "مكتملة":
            continue
        result.append(
            {
                "order_no": order_no,
                "order_date": o.get("order_date", ""),
                "factory_name": o.get("factory_name", ""),
                "required_qty": item["_required"],
                "withdrawn_qty": item["_withdrawn"],
                "remaining_qty": item["_remaining"],
            }
        )
    result.sort(key=lambda x: str(x["order_date"]))
    return result


def complete_order(order_no: str) -> Tuple[bool, str]:
    ok = update_row(_key(), SHEETS["orders"], "order_no", order_no, {"status": "مكتملة"})
    return (ok, "تم إتمام الطلبية." if ok else "لم يتم العثور على الطلبية.")


def reopen_order(order_no: str) -> Tuple[bool, str]:
    ok = update_row(_key(), SHEETS["orders"], "order_no", order_no, {"status": "مفتوحة"})
    return (ok, "تم إعادة فتح الطلبية." if ok else "لم يتم العثور على الطلبية.")


def delete_order(order_no: str) -> Tuple[bool, str]:
    """حذف طلبية كاملة: يُرجع الكميات المسحوبة للمخزن ثم يحذف أصنافها وسحوباتها."""
    order = get_order(order_no)
    if not order:
        return False, "لم يتم العثور على الطلبية."

    withdrawals = get_withdrawals()
    order_withdrawals = (
        withdrawals[withdrawals["order_no"].astype(str) == str(order_no)]
        if not withdrawals.empty
        else withdrawals
    )
    restored = 0.0
    for _, w in order_withdrawals.iterrows():
        qty = to_number(w.get("qty"))
        code = str(w.get("product_code", ""))
        product = find_product(code)
        if product and qty > 0:
            new_stock = to_number(product["current_stock"]) + qty
            update_row(_key(), SHEETS["products"], "product_code", code, {"current_stock": new_stock})
            record_movement(
                order_no=order_no,
                product_code=code,
                product_name=product["product_name"],
                qty=-qty,
                balance_after=new_stock,
                person=str(w.get("withdrawn_by", "")),
                movement_type="حذف طلبية",
                notes=f"إرجاع كمية عند حذف الطلبية {order_no}",
            )
            restored += qty

    n_items = delete_rows_where(_key(), SHEETS["order_items"], "order_no", order_no)
    n_withdrawals = delete_rows_where(_key(), SHEETS["withdrawals"], "order_no", order_no)
    ok = delete_row(_key(), SHEETS["orders"], "order_no", order_no)
    if not ok:
        return False, "تعذر حذف الطلبية."
    return (
        True,
        f"تم حذف الطلبية {order_no} ({n_items} صنف، {n_withdrawals} سحب) وإرجاع {restored:g} للمخزن.",
    )


# --------------------------------------------------------------------------- #
#                                  السحب
# --------------------------------------------------------------------------- #
def record_movement(
    order_no: str,
    product_code: str,
    product_name: str,
    qty: float,
    balance_after: float,
    person: str,
    movement_type: str = "سحب",
    withdrawal_id: str = "",
    movement_date: str = "",
    notes: str = "",
) -> str:
    movement_no = next_movement_no()
    row = {
        "movement_no": movement_no,
        "movement_date": movement_date or now_str(),
        "movement_type": movement_type,
        "order_no": order_no,
        "product_code": product_code,
        "product_name": product_name,
        "qty": to_number(qty),
        "balance_after": to_number(balance_after),
        "person": person,
        "notes": notes or (f"مرتبط بالسحب {withdrawal_id}" if withdrawal_id else ""),
        "created_at": now_str(),
    }
    append_row(_key(), SHEETS["stock_movements"], row)
    return movement_no


def withdraw(
    order_no: str,
    item_id: str,
    qty: float,
    person: str,
    withdraw_date: str = "",
    notes: str = "",
    supervisor: str = "",
) -> Tuple[bool, str]:
    qty = to_number(qty, -1)
    if qty <= 0:
        return False, "الكمية المسحوبة يجب أن تكون أكبر من صفر."
    if not str(person).strip():
        return False, "اسم الشخص الذي قام بالسحب مطلوب."

    items = order_items(order_no)
    if items.empty:
        return False, "لا توجد أصناف في هذه الطلبية."
    match = items[items["item_id"].astype(str) == str(item_id)]
    if match.empty:
        return False, "لم يتم العثور على الصنف داخل الطلبية."
    item = match.iloc[0]
    remaining = to_number(item["required_qty"]) - to_number(item["withdrawn_qty"])
    if qty > remaining + 1e-9:
        return False, f"الكمية أكبر من المتبقي في الطلبية ({remaining:g})."

    product = find_product(item["product_code"])
    if product is None:
        return False, "الصنف غير موجود في قائمة الأصناف."
    stock = to_number(product["current_stock"])
    if qty > stock + 1e-9:
        return False, f"الكمية أكبر من الرصيد المتاح في المخزن ({stock:g})."

    withdraw_date = normalize_timestamp(withdraw_date)
    withdrawal_id = f"W-{order_no}-{datetime.now().strftime('%H%M%S%f')[:10]}"

    new_withdrawn = to_number(item["withdrawn_qty"]) + qty
    update_row(
        _key(),
        SHEETS["order_items"],
        "item_id",
        item_id,
        {
            "withdrawn_qty": new_withdrawn,
            "last_withdraw_date": withdraw_date,
            "last_withdrawn_by": str(person).strip(),
        },
    )

    new_stock = stock - qty
    update_row(_key(), SHEETS["products"], "product_code", item["product_code"], {"current_stock": new_stock})

    append_row(
        _key(),
        SHEETS["withdrawals"],
        {
            "withdrawal_id": withdrawal_id,
            "order_no": order_no,
            "item_id": item_id,
            "product_code": item["product_code"],
            "product_name": item["product_name"],
            "qty": qty,
            "withdraw_date": withdraw_date,
            "withdrawn_by": str(person).strip(),
            "supervisor_name": str(supervisor).strip(),
            "notes": notes,
            "created_at": now_str(),
        },
    )

    record_movement(
        order_no=order_no,
        product_code=item["product_code"],
        product_name=item["product_name"],
        qty=qty,
        balance_after=new_stock,
        person=str(person).strip(),
        movement_type="سحب",
        withdrawal_id=withdrawal_id,
        movement_date=withdraw_date,
        notes=notes,
    )

    msg = f"تم سحب {qty:g} من {item['product_name']}."
    if new_stock <= to_number(product["min_stock"]):
        msg += " ⚠️ المخزون منخفض."
    return True, msg


def delete_withdrawal(withdrawal_id: str) -> Tuple[bool, str]:
    """التراجع عن سحب: يعيد الكمية للمخزن ويخصمها من الطلبية.

    (تُقرأ البيانات عبر الطبقة الموحدة لتعمل العملية أيضًا دون اتصال.)
    """
    withdrawals = read_sheet(_key(), SHEETS["withdrawals"])
    if withdrawals.empty:
        return False, "لم يتم العثور على عملية السحب."
    match = withdrawals[
        withdrawals["withdrawal_id"].astype(str).str.strip() == str(withdrawal_id).strip()
    ]
    if match.empty:
        return False, "لم يتم العثور على عملية السحب."
    record = match.iloc[0].to_dict()
    qty = to_number(record.get("qty"))
    item_id = record.get("item_id", "")
    product_code = record.get("product_code", "")

    items = order_items(record.get("order_no", ""))
    match_items = items[items["item_id"].astype(str) == str(item_id)]
    if not match_items.empty:
        item = match_items.iloc[0]
        new_withdrawn = max(0.0, to_number(item["withdrawn_qty"]) - qty)
        update_row(_key(), SHEETS["order_items"], "item_id", item_id, {"withdrawn_qty": new_withdrawn})
    product = find_product(product_code)
    if product:
        new_stock = to_number(product["current_stock"]) + qty
        update_row(_key(), SHEETS["products"], "product_code", product_code, {"current_stock": new_stock})
        record_movement(
            order_no=record.get("order_no", ""),
            product_code=product_code,
            product_name=product["product_name"],
            qty=-qty,
            balance_after=new_stock,
            person=record.get("withdrawn_by", ""),
            movement_type="إلغاء سحب",
            notes=f"إلغاء السحب {withdrawal_id}",
        )
    delete_row(_key(), SHEETS["withdrawals"], "withdrawal_id", withdrawal_id)
    return True, "تم إلغاء عملية السحب وإرجاع الكمية للمخزن."


def get_withdrawals() -> pd.DataFrame:
    return read_sheet(_key(), SHEETS["withdrawals"])


def get_movements() -> pd.DataFrame:
    return read_sheet(_key(), SHEETS["stock_movements"])


# --------------------------------------------------------------------------- #
#                       عمليات مبسطة (بدون طلبات)
# --------------------------------------------------------------------------- #
def add_stock_item(
    name: str,
    start_qty: float,
    unit: str = "",
    code: str = "",
    date_added: str = "",
    notes: str = "",
    manufacturer: str = "",
    supplier: str = "",
    expiry_date: str = "",
    category: str = PRODUCT_CATEGORY_GENERAL,
    storage_location: str = "",
    serial_number: str = "",
    device_status: str = "",
    units_per_carton: float = 0,
    purchase_date: str = "",
    last_withdraw_date: str = "",
    device_condition: str = "",
) -> Tuple[bool, str]:
    """إضافة صنف جديد للمخزن برصيد افتتاحي (كود يُولَّد تلقائيًا إن لم يُحدَّد)."""
    name = str(name or "").strip()
    if not name:
        return False, "اسم الصنف مطلوب."
    qty = 0.0 if start_qty is None else to_number(start_qty, -1)
    if qty < 0:
        return False, "الكمية يجب أن تكون صفرًا أو أكثر."
    code = str(code or "").strip()
    if not code:
        products = get_products()
        existing = {str(c).strip() for c in products["product_code"].tolist()}
        seq = 1
        while f"{seq:03d}" in existing:
            seq += 1
        code = f"{seq:03d}"
    return add_product(
        {
            "product_code": code,
            "product_name": name,
            "unit": str(unit or "").strip(),
            "current_stock": qty,
            "min_stock": 0,
            "date_added": str(date_added or "").strip(),
            "notes": str(notes or "").strip(),
            "manufacturer": str(manufacturer or "").strip(),
            "supplier": str(supplier or "").strip(),
            "expiry_date": str(expiry_date or "").strip(),
            "category": normalize_category(category),
            "storage_location": str(storage_location or "").strip(),
            "serial_number": str(serial_number or "").strip(),
            "device_status": normalize_device_status(device_status),
            "units_per_carton": to_number(units_per_carton, 0),
            "purchase_date": str(purchase_date or "").strip(),
            "last_withdraw_date": str(last_withdraw_date or "").strip(),
            "device_condition": str(device_condition or "").strip(),
        }
    )


def sell_draw_item(
    product_code: str,
    qty: float,
    person: str,
    timestamp: str = "",
    supervisor: str = "",
    notes: str = "",
) -> Tuple[bool, str]:
    """صرف كمية من صنف مباشرة (بدون طلبية): يخصم من المخزن ويسجّل عملية مستقلة بطابع زمني."""
    qty = to_number(qty, -1)
    if qty <= 0:
        return False, "الكمية يجب أن تكون أكبر من صفر."
    person = str(person or "").strip()
    if not person:
        return False, "اسم الساحب / المستلم مطلوب."
    supervisor = str(supervisor or "").strip()
    if not supervisor:
        return False, "اسم المسؤول / أمين المخزن مطلوب."

    product = find_product(product_code)
    if not product:
        return False, "الصنف غير موجود في المخزون."
    stock = to_number(product["current_stock"])
    if qty > stock + 1e-9:
        return False, f"الكمية أكبر من الرصيد المتاح ({stock:g})."

    stamp = normalize_timestamp(timestamp)
    withdrawal_id = f"W-{product_code}-{datetime.now().strftime('%H%M%S%f')[:10]}"
    new_stock = stock - qty
    new_total_withdrawn = to_number(product.get("total_withdrawn")) + qty
    update_row(
        _key(),
        SHEETS["products"],
        "product_code",
        product_code,
        {
            "current_stock": new_stock,
            "total_withdrawn": new_total_withdrawn,
            "last_withdraw_date": stamp,
        },
    )

    append_row(
        _key(),
        SHEETS["withdrawals"],
        {
            "withdrawal_id": withdrawal_id,
            "order_no": "",
            "item_id": "",
            "product_code": product_code,
            "product_name": product["product_name"],
            "qty": qty,
            "withdraw_date": stamp,
            "withdrawn_by": person,
            "supervisor_name": supervisor,
            "notes": str(notes or "").strip(),
            "created_at": now_str(),
        },
    )
    record_movement(
        order_no="",
        product_code=product_code,
        product_name=product["product_name"],
        qty=qty,
        balance_after=new_stock,
        person=person,
        movement_type="سحب",
        movement_date=stamp,
        notes=str(notes or "").strip(),
    )
    msg = f"تم سحب {qty:g} من «{product['product_name']}» بنجاح. الرصيد المتبقي: {new_stock:g}."
    if new_stock <= to_number(product["min_stock"]):
        msg += " ⚠️ المخزون منخفض."
    return True, msg


def withdraw_chemical(
    product_code: str,
    qty: float,
    person: str,
    timestamp: str = "",
    supervisor: str = "",
    notes: str = "",
) -> Tuple[bool, str]:
    """سحب مادة كيميائية فقط، مع خصم الرصيد وتسجيل بيانات السحب والمستخدم."""
    product = find_product(product_code)
    if not product:
        return False, "المادة الكيميائية غير موجودة في المخزون."
    if normalize_category(product.get("category")) != PRODUCT_CATEGORY_CHEMICALS:
        return False, "الصنف المحدد ليس مادة كيميائية."
    return sell_draw_item(
        product_code=product_code,
        qty=qty,
        person=person,
        timestamp=timestamp,
        supervisor=supervisor,
        notes=notes,
    )


def withdraw_office_item(
    product_code: str,
    qty: float,
    person: str,
    timestamp: str = "",
    supervisor: str = "",
    notes: str = "",
) -> Tuple[bool, str]:
    """سحب صنف مكتبي فقط، مع تحديث الرصيد وتاريخ آخر سحب تلقائيًا."""
    product = find_product(product_code)
    if not product:
        return False, "الصنف المكتبي غير موجود في المخزون."
    if normalize_category(product.get("category")) != PRODUCT_CATEGORY_OFFICE:
        return False, "الصنف المحدد ليس من أصناف المكتبية."
    return sell_draw_item(
        product_code=product_code,
        qty=qty,
        person=person,
        timestamp=timestamp,
        supervisor=supervisor,
        notes=notes,
    )


def withdraw_computer_item(
    product_code: str,
    qty: float,
    person: str,
    timestamp: str = "",
    supervisor: str = "",
    notes: str = "",
) -> Tuple[bool, str]:
    """سحب صنف كمبيوتر فقط، مع خصم الكمية وتسجيل السحب في السجل العام."""
    product = find_product(product_code)
    if not product:
        return False, "صنف مستلزمات الكمبيوتر غير موجود في المخزون."
    if normalize_category(product.get("category")) != PRODUCT_CATEGORY_COMPUTER:
        return False, "الصنف المحدد ليس من مستلزمات الكمبيوتر."
    return sell_draw_item(
        product_code=product_code,
        qty=qty,
        person=person,
        timestamp=timestamp,
        supervisor=supervisor,
        notes=notes,
    )


# --------------------------------------------------------------------------- #
#                                  ملخصات
# --------------------------------------------------------------------------- #
def dashboard_metrics() -> Dict[str, Any]:
    products = get_products()
    orders = get_orders()
    items = get_order_items()
    total_products = len(products)
    total_stock = sum(to_number(v) for v in products["current_stock"]) if not products.empty else 0.0
    total_orders = len(orders)
    low = low_stock_products()
    open_orders = 0
    if not orders.empty:
        open_orders = int((orders["status"].astype(str) != "مكتملة").sum())
    pending_items = int((items["_remaining"] > 0).sum()) if not items.empty else 0
    return {
        "total_products": total_products,
        "total_stock": total_stock,
        "total_orders": total_orders,
        "low_stock_count": len(low),
        "open_orders": open_orders,
        "pending_items": pending_items,
    }