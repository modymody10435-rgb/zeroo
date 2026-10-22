from __future__ import annotations

CATEGORY_GENERAL = "عام"
CATEGORY_PCR = "PCR"
CATEGORY_CHEMICALS = "كيماويات"
CATEGORY_OFFICE = "المكتبية"
CATEGORY_COMPUTER = "مستلزمات الكمبيوتر"

CATEGORIES = [
    CATEGORY_GENERAL,
    CATEGORY_PCR,
    CATEGORY_CHEMICALS,
    CATEGORY_OFFICE,
    CATEGORY_COMPUTER,
]

CATEGORY_STORAGE = {
    CATEGORY_GENERAL: "",
    CATEGORY_PCR: "قسم PCR",
    CATEGORY_CHEMICALS: "قسم الكيماويات",
    CATEGORY_OFFICE: "قسم المكتبية",
    CATEGORY_COMPUTER: "قسم مستلزمات الكمبيوتر",
}

DEVICE_STATUSES = [
    "جاهز",
    "قيد الاستخدام",
    "تحت الصيانة",
    "معطل",
    "تالف",
    "خارج الخدمة",
    "مكهن",
]
DEVICE_STATUS_DEFAULT = "جاهز"
DEVICE_STATUS_DECOMMISSIONED = "مكهن"

DEVICE_CONDITIONS = ["جديد", "قديم"]
DEVICE_CONDITION_DEFAULT = "جديد"

AUTHORITY_FORMS_SETTING = "authority_forms_stock"
AUTHORITY_FORMS_CODE = "AUTHORITY_FORMS"
AUTHORITY_FORMS_NAME = "استمارات الهيئة"
AUTHORITY_RECEIPT_TYPE = "وارد استمارات الهيئة"
AUTHORITY_WITHDRAWAL_TYPE = "صرف استمارات الهيئة"
AUTHORITY_WITHDRAWAL_LEGACY = "سحب استمارات الهيئة"

ORDER_STATUS_OPEN = "مفتوحة"
ORDER_STATUS_COMPLETED = "مكتملة"

MOVEMENT_ADD = "إضافة رصيد"
MOVEMENT_WITHDRAW = "سحب"
MOVEMENT_ADJUST = "تعديل رصيد"
MOVEMENT_RESTORE = "إرجاع رصيد"
MOVEMENT_ORDER_DELETE = "حذف طلبية"
