"""نظام إدارة مخزن المعمل - واجهة مبسطة (Streamlit).

الصفحات (حسب ترتيب القائمة الجانبية):
    1. 🏠 الصفحة الرئيسية (Dashboard)     — الافتراضية بعد الدخول
    2. 📤 تسجيل سحب (Withdrawal Page)
    3. ➕ إدارة الأصناف (Item Management)
    4. 🧬 قسم PCR المستقل (PCR Section)
    5. 🧪 قسم الكيماويات (Chemicals Section)
    6. 🗂️ قسم المكتبية (Office Supplies Section)
    7. 💻 قسم مستلزمات الكمبيوتر (Computer Supplies Section)
    8. 📄 استمارات الهيئة — الوارد والصرف (Authority Forms)
    9. 🗑️ تكهين الأجهزة (Device Decommissioning)
    10. 📊 التقارير والسجلات (Reports & Logs)
    11. 👤 إدارة المستخدمين (User Management) — للمدير فقط

المميزات:
    - نظام مستخدمين متعدد (ورقة Users) مع إضافة/حذف/تغيير كلمات المرور.
    - حقول إدخال فارغة بلا أرقام افتراضية أو نصوص إرشادية داخل الحقول.
    - طوابع زمنية مفصّلة بصيغة YYYY-MM-DD HH:MM:SS لكل عملية سحب.
    - كود الصنف وتاريخ الإضافة عند إضافة صنف جديد.
    - تمييز «اسم المسؤول» عن «اسم الساحب» في سجل السحوبات.
    - شارة المستخدم النشط أعلى الواجهة + زر تسجيل الخروج.
    - لوحة رئيسية بمؤشرات وآخر التحديثات وأزرار وصول سريع.
    - تخطيط متجاوب مع الهواتف المحمولة (عمود واحد + أهداف لمس أكبر).
    - تخزين البيانات في SQLite داخل مجلد المشروع.

قاعدة البيانات: SQLite محلية داخل data/warehouse.sqlite3.
"""
from __future__ import annotations

import html
import io
import os
import re
import subprocess
import unicodedata
from datetime import date, datetime

import pandas as pd
import streamlit as st
st.markdown(
    """
    <style>
    [data-testid="stSidebar"] div[role="radiogroup"] label div p {
        font-size: 18px !important;
        font-weight: bold !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)
from core.auth import current_username, is_admin, is_logged_in, login_form, logout
from core.config import load_config
from core.db import DataError, configure, ensure_schema, spreadsheet_info, to_number
from core.services import (
    CHEMICALS_STORAGE_SECTION,
    COMPUTER_STORAGE_SECTION,
    DEVICE_CONDITIONS,
    DEVICE_CONDITION_DEFAULT,
    DEVICE_STATUSES,
    DEVICE_STATUS_DEFAULT,
    DEVICE_STATUS_DECOMMISSIONED,
    OFFICE_STORAGE_SECTION,
    PCR_STORAGE_SECTION,
    PRODUCT_CATEGORIES,
    PRODUCT_CATEGORY_CHEMICALS,
    PRODUCT_CATEGORY_COMPUTER,
    PRODUCT_CATEGORY_GENERAL,
    PRODUCT_CATEGORY_OFFICE,
    PRODUCT_CATEGORY_PCR,
    add_reagent_item,
    add_stock_item,
    clear_test_data,
    decommission_device,
    delete_authority_form_item,
    delete_product,
    get_authority_form_items,
    get_authority_form_receipts,
    get_authority_form_withdrawals,
    get_authority_forms_count,
    get_chemical_products,
    get_computer_products,
    get_movements,
    get_office_products,
    get_pcr_products,
    get_products,
    get_withdrawals,
    normalize_category,
    products_by_category,
    receive_authority_forms,
    record_movement,
    sell_draw_item,
    update_product,
    withdraw_authority_forms,
    withdraw_chemical,
    withdraw_computer_item,
    withdraw_office_item,
    withdraw_reagent_item,
)
from core.styles import header, inject_styles, metric_card
from core.users import (
    LAB_ALL,
    LAB_CELL_CULTURE,
    LAB_PCR,
    LAB_SEQUENCING,
    LABS,
    ROLE_ADMIN,
    ROLES,
    add_user,
    delete_user,
    get_user_lab_access,
    get_users,
    has_lab_access,
    list_users,
    reset_password,
    set_lab_access,
    set_role,
)

# --------------------------------------------------------------------------- #
#                              إعداد الصفحة
# --------------------------------------------------------------------------- #
st.set_page_config(
    page_title="مخزن المعمل",
    page_icon="🏭",
    layout="wide",
    initial_sidebar_state="collapsed",  # مهيأ للهاتف: القائمة مطويوة
)
inject_styles()

# --------------------------------------------------------------------------- #
#     إصلاح تخطيط عام: حدود الشريط الجانبي + توافق RTL/LTR (يُحقن بعد الثيم)
# --------------------------------------------------------------------------- #
LAYOUT_FIX_CSS = """
<style>
/* ============ 1) تنظيف حدود الشريط الجانبي وإزالة الخطوط ============ */
[data-testid="stSidebar"],
[data-testid="stSidebarCollapsed"],
[data-testid="stSidebarContent"],
[data-testid="stSidebarHeader"],
[data-testid="stSidebarLogo"] {
    border-right: none !important;
    border-left: none !important;
    border-top: none !important;
    border-bottom: none !important;
    box-shadow: none !important;
    outline: none !important;
}

/* إزالة خطوط/حدود قائمة التنقل داخل الشريط الجانبي */
[data-testid="stSidebarNav"],
[data-testid="stSidebarNavItems"],
[data-testid="stSidebarNavSeparator"],
[data-testid="stSidebarNavLinkContainer"] {
    border: none !important;
    border-top: none !important;
    border-bottom: none !important;
    box-shadow: none !important;
    outline: none !important;
}

/* الفواصل الداخلية تبقى ناعمة بلا ظلال */
[data-testid="stSidebar"] hr {
    border: none !important;
    border-top: 1px solid rgba(255, 255, 255, 0.16) !important;
    box-shadow: none !important;
    opacity: 1 !important;
    margin: 0.6rem 0 !important;
}

/* ============ 1ب) انتقال سلس لزر الطي/الفتح ============ */
[data-testid="stSidebarCollapseButton"] {
    outline: none !important;
    border: none !important;
    box-shadow: none !important;
    transition: all 0.25s ease !important;
}
[data-testid="stSidebarCollapseButton"] button,
[data-testid="stSidebarCollapseButton"] > div {
    transition: background 0.25s ease, transform 0.25s ease,
        border-radius 0.25s ease, box-shadow 0.25s ease !important;
    border: none !important;
    outline: none !important;
    box-shadow: none !important;
}
[data-testid="stSidebarCollapseButton"] button:hover {
    transform: scale(1.06);
}
section[data-testid="stSidebar"] {
    transition: transform 0.3s ease-in-out, width 0.3s ease-in-out !important;
}

/* ============ 2) توافق RTL/LTR: flexbox للحاوية الرئيسية ============ */
.stApp,
.block-container {
    box-sizing: border-box;
    width: 100%;
}
.block-container {
    display: flex;
    flex-direction: column;
    align-items: stretch;
    gap: 0.25rem;
}
.block-container > * {
    box-sizing: border-box;
    min-width: 0;
    max-width: 100%;
}
[data-testid="stVerticalBlock"],
[data-testid="stHorizontalBlock"],
[data-testid="stForm"],
[data-testid="stForm"] [data-testid="stHorizontalBlock"] {
    box-sizing: border-box;
    width: 100%;
    min-width: 0;
}
[data-testid="stMetric"] { box-sizing: border-box; }

/* ============ 3) عرض كامل للعناصر ============ */
.stButton > button,
[data-testid="stButton"] > button,
.stDownloadButton > button,
[data-testid="stDownloadButton"] > button {
    width: 100%;
}

/* الجداول والنماذج بعرض كامل دائمًا لتفادي كسر التخطيط */
[data-testid="stDataFrame"],
[data-testid="stTable"] {
    width: 100% !important;
    max-width: 100% !important;
}
[data-testid="stForm"] {
    width: 100%;
}

/* ============ 4) إطارات واضحة لحقول الإدخال في كل التطبيق ============ */
div[data-baseweb="input"],
div[data-baseweb="textarea"],
div[data-baseweb="select"],
input,
textarea {
    border: 1.5px solid #4A5568 !important;
    border-radius: 6px !important;
    padding: 6px 10px !important;
    box-sizing: border-box !important;
}

/* منع تكرار الإطار: غلاف الحقل يحمل الإطار المرئي، والعنصر الداخلي شفاف */
div[data-baseweb] input,
div[data-baseweb] textarea {
    border: none !important;
    border-radius: 0 !important;
    padding: 0 !important;
    box-shadow: none !important;
}

/* توهج قوي باللون الأساسي عند التركيز */
div[data-baseweb="input"]:focus-within,
div[data-baseweb="textarea"]:focus-within,
div[data-baseweb="select"]:focus-within {
    border-color: #2563eb !important;
    box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.30) !important;
}
input:focus,
textarea:focus {
    border-color: #2563eb !important;
    box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.30) !important;
    outline: none !important;
}

/* ============ 5) خانة الإجمالي (معطّلة للقراءة) بنفس مظهر الحقول العادية ============ */
div[data-baseweb="input"]:has(input:disabled),
div[data-baseweb="textarea"]:has(textarea:disabled) {
    background: #ffffff !important;
    border-color: #4A5568 !important;
    opacity: 1 !important;
}
div[data-baseweb="input"] input:disabled,
div[data-baseweb="textarea"] textarea:disabled {
    background: transparent !important;
    color: inherit !important;
    opacity: 1 !important;
    -webkit-text-fill-color: currentColor !important;
    cursor: default !important;
}
</style>
"""

st.markdown(LAYOUT_FIX_CSS, unsafe_allow_html=True)

PAGES = [
    "🏠 الصفحة الرئيسية (Dashboard)",
    "📤 تسجيل سحب (Withdrawal Page)",
    "➕ إدارة الأصناف (Item Management)",
    "🧬 قسم PCR (PCR Section)",
    "🧪 قسم الكيماويات (Chemicals Section)",
    "🗂️ قسم المكتبية (Office Supplies Section)",
    "💻 قسم مستلزمات الكمبيوتر (Computer Supplies Section)",
    "📄 استمارات الهيئة — الوارد والصرف (Authority Forms)",
    "🌐 طلبيات منظمة الصحة العالمية (WHO Orders)",
    "🗑️ تكهين الأجهزة (Device Decommissioning)",
    "📊 التقارير والسجلات (Reports & Logs)",
]
ADMIN_PAGES = ["👤 إدارة المستخدمين (User Management - Admin only)"]

REAGENTS_PARENT_PAGE = "🧊 Reagents Refrigerators"
REAGENTS_CATEGORY_PCR = "PCR Reagents"
REAGENTS_CATEGORY_SEQUENCING = "Sequencing"
REAGENTS_CATEGORY_CELL_CULTURE = "Cell Culture"
REAGENTS_CATEGORIES = {
    REAGENTS_CATEGORY_PCR,
    REAGENTS_CATEGORY_SEQUENCING,
    REAGENTS_CATEGORY_CELL_CULTURE,
}
REAGENTS_STORAGE_SEQUENCING = "قسم Sequencing"
REAGENTS_STORAGE_CELL_CULTURE = "قسم Cell Culture"
REAGENTS_PCR_PAGE = "reagents_pcr"
REAGENTS_SEQUENCING_PAGE = "reagents_sequencing"
REAGENTS_CELL_CULTURE_PAGE = "reagents_cell_culture"
REAGENTS_SUB_PAGES = {
    "PCR": REAGENTS_PCR_PAGE,
    "Sequencing": REAGENTS_SEQUENCING_PAGE,
    "Cell Culture": REAGENTS_CELL_CULTURE_PAGE,
}
REAGENTS_SECTION_CONFIG = {
    "PCR": {
        "icon": "🧬",
        "title": "قسم PCR",
        "subtitle": (
            "إدارة كواشف PCR داخل قسم Reagents Refrigerators: "
            "الكود، الاسم، الشركة، التواريخ، الحالة، الكميات وتتبع المستخدمين"
        ),
        "category": REAGENTS_CATEGORY_PCR,
        "storage_section": PCR_STORAGE_SECTION,
        "key_prefix": "reagents_pcr",
        "item_singular": "كاشف PCR",
        "item_plural": "كواشف PCR",
        "fields": {
            "code": "كود كاشف PCR *",
            "name": "اسم كاشف PCR *",
            "company": "شركة كاشف PCR",
            "date_added": "تاريخ إضافة كاشف PCR",
            "expiry_date": "تاريخ انتهاء كاشف PCR",
            "condition": "حالة كاشف PCR",
            "initial": "الكمية الأولية لكاشف PCR",
            "withdrawn": "الكمية المسحوبة من كاشف PCR",
            "remaining": "الكمية المتبقية لكاشف PCR",
            "notes": "ملاحظات كاشف PCR",
        },
        "columns": {
            "product_code": "كود كاشف PCR",
            "product_name": "اسم كاشف PCR",
            "manufacturer": "الشركة المصنعة",
            "date_added": "تاريخ الإضافة",
            "expiry_date": "تاريخ الانتهاء",
            "_condition": "الحالة",
            "_initial": "الكمية الأولية",
            "_withdrawn": "الكمية المسحوبة",
            "_remaining": "الكمية المتبقية",
            "_added_by": "أضافه",
            "_last_withdrawn_by": "آخر سحب بواسطة",
        },
        "tabs": {
            "list": "📋 كواشف PCR",
            "add": "➕ إضافة كاشف PCR",
            "withdraw": "📤 سحب من كاشف PCR",
            "delete": "🗑️ حذف كاشف PCR",
        },
    },
    "Sequencing": {
        "icon": "🧬",
        "title": "قسم Sequencing",
        "subtitle": (
            "إدارة كواشف Sequencing داخل قسم Reagents Refrigerators: "
            "الكود، الاسم، الشركة، التواريخ، الحالة، الكميات وتتبع المستخدمين"
        ),
        "category": REAGENTS_CATEGORY_SEQUENCING,
        "storage_section": REAGENTS_STORAGE_SEQUENCING,
        "key_prefix": "reagents_sequencing",
        "item_singular": "كاشف Sequencing",
        "item_plural": "كواشف Sequencing",
        "fields": {
            "code": "كود كاشف Sequencing *",
            "name": "اسم كاشف Sequencing *",
            "company": "شركة كاشف Sequencing",
            "date_added": "تاريخ إضافة كاشف Sequencing",
            "expiry_date": "تاريخ انتهاء كاشف Sequencing",
            "condition": "حالة كاشف Sequencing",
            "initial": "الكمية الأولية لكاشف Sequencing",
            "withdrawn": "الكمية المسحوبة من كاشف Sequencing",
            "remaining": "الكمية المتبقية لكاشف Sequencing",
            "notes": "ملاحظات كاشف Sequencing",
        },
        "columns": {
            "product_code": "كود كاشف Sequencing",
            "product_name": "اسم كاشف Sequencing",
            "manufacturer": "الشركة المصنعة",
            "date_added": "تاريخ الإضافة",
            "expiry_date": "تاريخ الانتهاء",
            "_condition": "الحالة",
            "_initial": "الكمية الأولية",
            "_withdrawn": "الكمية المسحوبة",
            "_remaining": "الكمية المتبقية",
            "_added_by": "أضافه",
            "_last_withdrawn_by": "آخر سحب بواسطة",
        },
        "tabs": {
            "list": "📋 كواشف Sequencing",
            "add": "➕ إضافة كاشف Sequencing",
            "withdraw": "📤 سحب من كاشف Sequencing",
            "delete": "🗑️ حذف كاشف Sequencing",
        },
    },
    "Cell Culture": {
        "icon": "🧫",
        "title": "قسم Cell Culture",
        "subtitle": (
            "إدارة كواشف Cell Culture داخل قسم Reagents Refrigerators: "
            "الكود، الاسم، الشركة، التواريخ، الحالة، الكميات وتتبع المستخدمين"
        ),
        "category": REAGENTS_CATEGORY_CELL_CULTURE,
        "storage_section": REAGENTS_STORAGE_CELL_CULTURE,
        "key_prefix": "reagents_cell_culture",
        "item_singular": "كاشف Cell Culture",
        "item_plural": "كواشف Cell Culture",
        "fields": {
            "code": "كود كاشف Cell Culture *",
            "name": "اسم كاشف Cell Culture *",
            "company": "شركة كاشف Cell Culture",
            "date_added": "تاريخ إضافة كاشف Cell Culture",
            "expiry_date": "تاريخ انتهاء كاشف Cell Culture",
            "condition": "حالة كاشف Cell Culture",
            "initial": "الكمية الأولية لكاشف Cell Culture",
            "withdrawn": "الكمية المسحوبة من كاشف Cell Culture",
            "remaining": "الكمية المتبقية لكاشف Cell Culture",
            "notes": "ملاحظات كاشف Cell Culture",
        },
        "columns": {
            "product_code": "كود كاشف Cell Culture",
            "product_name": "اسم كاشف Cell Culture",
            "manufacturer": "الشركة المصنعة",
            "date_added": "تاريخ الإضافة",
            "expiry_date": "تاريخ الانتهاء",
            "_condition": "الحالة",
            "_initial": "الكمية الأولية",
            "_withdrawn": "الكمية المسحوبة",
            "_remaining": "الكمية المتبقية",
            "_added_by": "أضافه",
            "_last_withdrawn_by": "آخر سحب بواسطة",
        },
        "tabs": {
            "list": "📋 كواشف Cell Culture",
            "add": "➕ إضافة كاشف Cell Culture",
            "withdraw": "📤 سحب من كاشف Cell Culture",
            "delete": "🗑️ حذف كاشف Cell Culture",
        },
    },
}


# --------------------------------------------------------------------------- #
#                       التهيئة والاتصال بقاعدة البيانات
# --------------------------------------------------------------------------- #
def _bootstrap() -> None:
    if st.session_state.get("_db_ready"):
        return
    cfg = load_config()
    try:
        configure(cfg.database_path)
        ensure_schema("sqlite")
        st.session_state["_db_ready"] = True
        st.session_state.pop("_db_error", None)
    except DataError as exc:
        st.session_state["_db_error"] = str(exc)
    except Exception as exc:  # noqa: BLE001
        st.session_state["_db_error"] = f"تعذر تهيئة قاعدة البيانات المحلية: {exc}"


# --------------------------------------------------------------------------- #
#                  شارة حالة الاتصال والمزامنة (تتحدث تلقائيًا)
# --------------------------------------------------------------------------- #
def _render_sync_pill() -> None:
    st.markdown(
        "<div style='display:inline-block;padding:5px 10px;border-radius:999px;"
        "background:#e7f7ee;color:#166534;font-size:12px;font-weight:600;'>"
        "🗄️ التخزين المحلي: SQLite</div>",
        unsafe_allow_html=True,
    )


@st.fragment(run_every=2)
def _sidebar_sync_status() -> None:
    """حالة المزامنة في القائمة الجانبية (تتحدث كل ثانيتين دون تدخل المستخدم)."""
    _render_sync_pill()


@st.fragment(run_every=2)
def _topbar_sync_status() -> None:
    """حالة المزامنة في الشريط العلوي (تتحدث كل ثانيتين دون تدخل المستخدم)."""
    _render_sync_pill()


@st.cache_resource(show_spinner=False)
def _app_version() -> str:
    """رقم نسخة التطبيق (commit git) للتحقق من أن النسخة المنشورة هي الأحدث."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=os.path.dirname(os.path.abspath(__file__)),
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        return "—"
    return "—"


def _sidebar() -> str:
    cfg = load_config()
    username = current_username()
    role = str(st.session_state.get("role", "")).strip()
    role_label = {"admin": "👑 مدير", "user": "👤 مستخدم"}.get(role.lower(), role)
    with st.sidebar:
        st.markdown(
            f"<div style='padding:14px 6px 6px;text-align:center;'>"
            f"<div style='font-size:34px;'>🏭</div>"
            f"<div style='font-weight:700;font-size:17px;color:#fff;'>{cfg.app_title}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )
        if username:
            st.markdown(
                f'<div class="sidebar-user">'
                f'<div class="name">👤 المستخدم الحالي: {html.escape(username)}</div>'
                f'<div class="role">{html.escape(role_label)}</div>'
                f"</div>",
                unsafe_allow_html=True,
            )
        # شارة حالة الاتصال/المزامنة (تتحدث تلقائيًا كل ثانيتين)
        _sidebar_sync_status()
        st.markdown("---")
        if is_admin():
            sidebar_pages = PAGES[:4] + [REAGENTS_PARENT_PAGE] + PAGES[4:]
            items = sidebar_pages + ADMIN_PAGES
        else:
            # المستخدم غير الإداري يرى الرئيسية والسحب وأقسام الكواشف المصرح بها فقط.
            items = [PAGES[0], PAGES[1]]
            for lab in _accessible_reagent_types():
                target = REAGENTS_SUB_PAGES.get(lab)
                if target:
                    items.append(target)

        # طلب تنقّل من أزرار الوصول السريع (يُستهلك قبل تركيب القائمة)
        pending = st.session_state.pop("pending_page", None)
        if pending in items:
            st.session_state["nav_page"] = pending
        elif pending in REAGENTS_SUB_PAGES.values():
            st.session_state["nav_page"] = REAGENTS_PARENT_PAGE
            for label, target in REAGENTS_SUB_PAGES.items():
                if target == pending:
                    st.session_state["reagents_sub_page"] = label
                    break
        # إسقاط أي صفحة غير صالحة (مثل صفحة المدير عند دخول مستخدم عادي)
        if st.session_state.get("nav_page") not in items:
            st.session_state.pop("nav_page", None)

        page = st.radio(
            "القائمة",
            items,
            index=0,
            label_visibility="collapsed",
            width="stretch",
            key="nav_page",
        )
        if page == REAGENTS_PARENT_PAGE:
            section = st.selectbox(
                "اختر القسم الفرعي",
                options=list(REAGENTS_SUB_PAGES.keys()),
                width="stretch",
                key="reagents_sub_page",
            )
            page = REAGENTS_SUB_PAGES[section]
        st.markdown("---")
        if st.button("🚪 تسجيل الخروج", use_container_width=True):
            logout()
        # زر إغلاق البرنامج (يظهر فقط في نسخة exe المكتبي)
        if os.environ.get("WAREHOUSE_DESKTOP") == "1":
            if st.button("⏻ إغلاق التطبيق", key="desktop_quit", use_container_width=True):
                os._exit(0)
        st.markdown("---")
        info = spreadsheet_info(cfg.spreadsheet_key)
        if info.get("url"):
            st.caption(f"🔗 مصدر البيانات: [{info['title']}]({info['url']})")
        elif info.get("title"):
            st.caption(f"🗄️ قاعدة البيانات المركزية: `{info['title']}`")
        st.caption(f"🔧 إصدار التطبيق: `{_app_version()}`")
    return page


def _topbar() -> None:
    """شريط علوي يعرض المستخدم النشط في أعلى كل صفحة (مع زر خروج وحالة المزامنة)."""
    username = current_username()
    if not username:
        return
    role = str(st.session_state.get("role", "")).strip()
    role_label = {"admin": "👑 مدير", "user": "👤 مستخدم"}.get(role.lower(), role)
    c_main, c_status, c_action = st.columns([3, 2, 1])
    with c_action:
        if st.button("🚪 تسجيل الخروج", key="topbar_logout", use_container_width=True):
            logout()
    with c_status:
        _topbar_sync_status()
    with c_main:
        st.markdown(
            f'<div class="user-bar" style="margin-bottom:0;">'
            f'<span class="who">👤 المستخدم الحالي: {html.escape(username)}'
            f'<span class="role-chip {"admin" if role.lower() == "admin" else ""}">'
            f"{html.escape(role_label)}</span></span>"
            f"</div>",
            unsafe_allow_html=True,
        )


def _guard() -> bool:
    """يعرض رسالة الخطأ ويمنع تنفيذ الصفحات عند فشل الاتصال."""
    err = st.session_state.get("_db_error")
    if not err:
        return True
    st.error(f"⚠️ {err}\n\nتعذّر تجهيز قاعدة البيانات المحلية في مجلد data بجانب التطبيق.")
    return False


def _go_to(page_label: str) -> None:
    """ينتقل إلى صفحة محددة عبر أزرار الوصول السريع."""
    st.session_state["pending_page"] = page_label
    st.rerun()


# --------------------------------------------------------------------------- #
#                    1) الصفحة الرئيسية (لوحة المعلومات)
def _remaining_quantity(wrow, movements, fallback=None):
    """الرصيد المتبقي بعد عملية سحب: balance_after من حركة «سحب» المطابقة أو الرصيد الحالي."""

    def _txt(value):
        s = str(value).strip()
        return "" if s.lower() in ("nan", "none", "nat") else s

    if movements is not None and not movements.empty:
        stamp = _txt(wrow.get("withdraw_date"))
        code = _txt(wrow.get("product_code"))
        matched = movements[
            (movements["product_code"].apply(_txt) == code)
            & (movements["movement_date"].apply(_txt) == stamp)
            & (movements["movement_type"].apply(_txt) == "سحب")
        ]
        if not matched.empty:
            return to_number(matched.iloc[-1]["balance_after"])
    if fallback is not None:
        return to_number(fallback)
    return None


def _product_note(value) -> str:
    s = str(value if value is not None else "").strip()
    return "" if s.lower() in ("nan", "none", "nat") else s


def _unit_value(unit_raw):
    """قيمة الوحدة كرقم (لحساب الإجمالي بعد السحب) أو None إن لم تكن رقمية."""
    text = _product_note(unit_raw)
    if not text:
        return None
    value = to_number(text, -1.0)
    return value if value >= 0 else None


def _notes_by_code(products) -> dict:
    if products is None or getattr(products, "empty", True):
        return {}
    return {
        str(p.get("product_code", "") or "").strip(): _product_note(p.get("notes"))
        for p in products.to_dict("records")
    }


# --------------------------------------------------------------------------- #
def page_home() -> None:
    username = current_username()
    header(f"👤 مرحبا بك، {username}", "نظرة سريعة على حالة المخزن وآخر العمليات")

    products = _filter_products_to_user_labs(get_products())
    withdrawals = _filter_withdrawals_to_user_labs(get_withdrawals(), products)

    total_items = len(products)
    total_ops = len(withdrawals)
    today = datetime.now().strftime("%Y-%m-%d")
    today_ops = (
        int(withdrawals["withdraw_date"].astype(str).str[:10].eq(today).sum())
        if not withdrawals.empty
        else 0
    )

    m1, m2, m3 = st.columns(3)
    with m1:
        st.metric("إجمالي الأصناف في المخزن", total_items, width="stretch")
    with m2:
        st.metric("إجمالي عمليات السحب", total_ops, width="stretch")
    with m3:
        st.metric("عمليات السحب اليوم", today_ops, width="stretch")

    st.write("")
    st.markdown("#### 🔎 بحث عن صنف")
    items = [] if products.empty else products.to_dict("records")
    options = {}
    seen_codes = set()
    for p in items:
        code_p = str(p.get("product_code", "") or "").strip()
        nm = str(p.get("product_name", "") or "").strip()
        code_key = code_p.lower()
        if not code_p and not nm:
            continue
        if code_p and code_key in seen_codes:
            continue
        if code_p:
            seen_codes.add(code_key)
        unit_p = str(p.get("unit", "") or "").strip()
        stock_p = to_number(p.get("current_stock"))
        label = f"{nm} [{code_p}] — رصيد {stock_p:g}"
        if unit_p:
            label += f" {unit_p}"
        while label in options:
            label += " "
        options[label] = code_p
    if not options:
        st.info("لا توجد أصناف مسجّلة في المخزن.")
    else:
        choice = st.selectbox(
            "اسم الصنف",
            options=list(options.keys()),
            index=None,
            placeholder="اختر صنفًا لعرض رصيده وعمليات السحب",
            key="home_product_select",
            width="stretch",
        )
        if choice is None:
            st.caption(
                "اختر صنفًا من القائمة لعرض رصيده الحالي وآخر عمليات السحب الخاصة به."
            )
        else:
            selected_code = options[choice]
            product = next(
                (
                    p
                    for p in items
                    if str(p.get("product_code", "") or "").strip().lower()
                    == selected_code.lower()
                ),
                {},
            )
            code_q = str(product.get("product_code", "") or "").strip()
            stock = to_number(product.get("current_stock"))
            min_stock = to_number(product.get("min_stock"))
            unit = str(product.get("unit", "") or "").strip()
            name = str(product.get("product_name", "") or "").strip()
            st.caption(f"{name} — [{code_q}]")
            q1, q2, q3, q4 = st.columns(4)
            with q1:
                st.metric(
                    f"الرصيد الحالي{f' ({unit})' if unit else ''}",
                    f"{stock:g}",
                    width="stretch",
                )
            with q2:
                st.metric("الحد الأدنى", f"{min_stock:g}", width="stretch")
            with q3:
                st.metric(
                    "الحالة",
                    "⚠️ منخفض" if stock <= min_stock else "✅ جيد",
                    width="stretch",
                )
            unit_val = _unit_value(unit)
            with q4:
                st.metric(
                    "الإجمالي بعد السحب",
                    f"{stock * unit_val:g}" if unit_val is not None else "—",
                    width="stretch",
                )
            st.caption(
                "💡 الإجمالي بعد السحب = الرصيد الحالي × قيمة الوحدة"
                + ("" if unit_val is not None else " — (أدخل قيمة رقمية في خانة «الوحدة» ليظهر الحساب).")
            )

            p_notes = _product_note(product.get("notes"))
            if p_notes:
                st.info(f"📝 ملاحظات الصنف: {p_notes}")
            else:
                st.caption("📝 لا توجد ملاحظات مسجلة لهذا الصنف.")

            mine = (
                withdrawals[
                    withdrawals["product_code"]
                    .astype(str)
                    .str.strip()
                    .str.lower()
                    == code_q.lower()
                ]
                if not withdrawals.empty
                else withdrawals
            )
            if mine.empty:
                st.info("لا توجد عمليات سحب مسجّلة لهذا الصنف.")
            else:
                total_qty = sum(to_number(v) for v in mine["qty"])
                st.markdown(
                    f"**📋 آخر عمليات السحب لهذا الصنف** — إجمالي المسحوب: {total_qty:g} "
                    f"({len(mine)} عملية)"
                )
                recent_mine = mine.iloc[::-1].head(10).copy()
                movements = get_movements()
                remainings = []
                for _, row in recent_mine.iterrows():
                    rem = _remaining_quantity(row, movements, product.get("current_stock"))
                    remainings.append("" if rem is None else f"{rem:g}")
                recent_mine["remaining_quantity"] = remainings
                recent_mine["total_after_withdrawal"] = [
                    "" if rem_str == "" or unit_val is None else f"{to_number(rem_str) * unit_val:g}"
                    for rem_str in remainings
                ]
                recent_mine["product_notes"] = p_notes
                st.dataframe(
                    recent_mine[
                        [
                            "withdraw_date",
                            "qty",
                            "remaining_quantity",
                            "total_after_withdrawal",
                            "product_notes",
                            "withdrawn_by",
                            "supervisor_name",
                        ]
                    ].rename(
                        columns={
                            "withdraw_date": "التاريخ والوقت",
                            "qty": "الكمية المسحوبة",
                            "remaining_quantity": "الرصيد المتبقي",
                            "total_after_withdrawal": "الإجمالي بعد السحب",
                            "product_notes": "ملاحظات الصنف",
                            "withdrawn_by": "اسم الساحب",
                            "supervisor_name": "اسم المسؤول",
                        }
                    ),
                    use_container_width=True,
                    hide_index=True,
                )
                st.caption(
                    "💡 عمود «الإجمالي بعد السحب» = الرصيد المتبقي بعد العملية × قيمة الوحدة."
                    if unit_val is not None
                    else "⚠️ عمود «الإجمالي بعد السحب» يتطلب قيمة رقمية في خانة «الوحدة»."
                )

    st.write("")
    st.markdown("#### ⚠️ أصناف منخفضة المخزون (الرصيد 3 أو أقل)")
    if products.empty:
        st.info("لا توجد أصناف مسجّلة في المخزن.")
    else:
        low = products.copy()
        low["_stock_num"] = low["current_stock"].map(to_number)
        low = low[low["_stock_num"] <= 3].sort_values("_stock_num", kind="stable")
        if low.empty:
            st.success("✅ لا توجد أصناف منخفضة المخزون — جميع الأصناف ضمن الحدود الآمنة.")
        else:
            if "added_by" not in low.columns:
                low["added_by"] = ""
            view = low.rename(
                columns={
                    "product_name": "اسم الصنف",
                    "product_code": "الكود",
                    "current_stock": "الرصيد الحالي",
                    "unit": "الوحدة",
                    "notes": "ملاحظات الصنف",
                    "added_by": "أضافه",
                }
            )[
                ["اسم الصنف", "الكود", "الرصيد الحالي", "الوحدة", "ملاحظات الصنف", "أضافه"]
            ]
            st.dataframe(view, use_container_width=True, hide_index=True)
            st.caption(f"عدد الأصناف التي رصيدها 3 أو أقل: {len(low)}")

    st.write("")
    st.markdown("#### 🕒 آخر التحديثات في المخزن")
    if withdrawals.empty:
        st.info("لا توجد عمليات سحب بعد.")
    else:
        recent = withdrawals.tail(8).iloc[::-1]
        notes_map = _notes_by_code(products)
        for _, r in recent.iterrows():
            stamp = str(r.get("withdraw_date", "") or "").strip()
            item = str(r.get("product_name", "") or "").strip()
            code = str(r.get("product_code", "") or "").strip()
            recipient = str(r.get("withdrawn_by", "") or "").strip()
            supervisor = str(r.get("supervisor_name", "") or "").strip()
            p_notes = _product_note(notes_map.get(code))
            notes_line = (
                f'<div class="act-meta">📝 ملاحظات الصنف: {html.escape(p_notes)}</div>' if p_notes else ""
            )
            st.markdown(
                f'<div class="activity-card">'
                f'<div class="act-time">🕒 {html.escape(stamp)}</div>'
                f'<div class="act-title">{html.escape(item) or "—"} '
                f'<span class="act-code">[{html.escape(code)}]</span></div>'
                f'<div class="act-meta">👤 الساحب: {html.escape(recipient) or "—"}'
                f' &nbsp;•&nbsp; 🛡️ المسؤول: {html.escape(supervisor) or "—"}</div>'
                f"{notes_line}"
                f"</div>",
                unsafe_allow_html=True,
            )

    st.write("")
    st.markdown("#### ⚡ أزرار الوصول السريع")
    b1, b2 = st.columns(2)
    with b1:
        if st.button(
            "📤 تسجيل سحب جديد", type="primary", use_container_width=True, key="qa_withdraw"
        ):
            _go_to(PAGES[1])
    with b2:
        if st.button(
            "➕ إضافة صنف جديد", type="primary", use_container_width=True, key="qa_add_item"
        ):
            _go_to(PAGES[2])


# --------------------------------------------------------------------------- #
#                        2) صفحة تسجيل السحب
# --------------------------------------------------------------------------- #
def page_withdraw() -> None:
    header("📤 تسجيل سحب", "صرف صنف من المخزن — يُسجَّل الطابع الزمني تلقائيًا")

    products = _filter_products_to_user_labs(get_products())
    available = products[products["current_stock"].apply(to_number) > 0] if not products.empty else products
    if available.empty:
        st.info("لا توجد أصناف متاحة في المخزون. أضف أصنافًا من صفحة «➕ إدارة الأصناف».")
        return

    c0, _ = st.columns([1, 3])
    with c0:
        code_filter = st.text_input("🔍 بحث بكود الصنف", placeholder="", width="stretch")
    if code_filter.strip():
        available = available[
            available["product_code"].astype(str).str.contains(code_filter.strip(), case=False, na=False)
        ]
        if available.empty:
            st.warning("لا يوجد صنف بهذا الكود.")
            return

    options = {
        f'[{r["product_code"]}] {r["product_name"]} — رصيد {to_number(r["current_stock"]):g} {str(r.get("unit", "") or "").strip()}'.strip(): str(
            r["product_code"]
        )
        for _, r in available.iterrows()
    }

    st.markdown("#### 📦 الصنف المراد سحبه")
    choice = st.selectbox(
        "اختر الصنف",
        options=list(options.keys()),
        width="stretch",
        placeholder="",
        key="withdraw_product_select",
    )
    code = options[choice]
    selected = next((r for _, r in available.iterrows() if str(r["product_code"]).strip() == code), None)
    p_notes = _product_note(None if selected is None else selected.get("notes"))
    if p_notes:
        st.info(f"📝 ملاحظات الصنف: {p_notes}")
    else:
        st.caption("📝 لا توجد ملاحظات مسجلة لهذا الصنف.")

    with st.form("withdraw_form", clear_on_submit=True):
        st.markdown("#### بيانات السحب")
        c1, c2 = st.columns(2)
        with c1:
            supervisor = st.text_input("اسم المسؤول / أمين المخزن *", placeholder="", width="stretch")
        with c2:
            person = st.text_input("اسم الساحب / المستلم *", placeholder="", width="stretch")
        q1, q2 = st.columns(2)
        with q1:
            qty = st.number_input(
                "الكمية المسحوبة", min_value=0.0, step=1.0, value=None, placeholder="", width="stretch"
            )

        stamp_now = datetime.now()
        d1, h1, m1, a1 = st.columns(4)
        with d1:
            wdate = st.date_input("تاريخ السحب", value=stamp_now.date(), width="stretch")
        with h1:
            hour12 = st.selectbox(
                "الساعة",
                options=list(range(1, 13)),
                index=(stamp_now.hour % 12 or 12) - 1,
                width="stretch",
            )
        with m1:
            minute = st.selectbox(
                "الدقيقة",
                options=list(range(0, 60)),
                index=stamp_now.minute,
                format_func=lambda m: f"{m:02d}",
                width="stretch",
            )
        with a1:
            ampm = st.selectbox(
                "ص / م",
                options=["ص", "م"],
                index=0 if stamp_now.hour < 12 else 1,
                width="stretch",
            )
        st.caption(
            "اختر الوقت بنظام 12 ساعة (ص/م) — يُسجَّل الطابع الزمني بصيغة (YYYY-MM-DD HH:MM:SS)."
        )

        submitted = st.form_submit_button("📤 تسجيل السحب", type="primary", use_container_width=True)

    if submitted:
        code = options[choice]
        hour24 = (int(hour12) % 12) + (12 if ampm == "م" else 0)
        stamp = (
            f"{wdate.strftime('%Y-%m-%d')} {hour24:02d}:{int(minute):02d}:00"
            if wdate
            else ""
        )
        ok, msg = sell_draw_item(code, qty, person, stamp, supervisor)
        if ok:
            st.success(msg)
            st.rerun()
        else:
            st.error(msg)

    _render_recent_withdrawals(limit=5)


def _render_recent_withdrawals(limit: int = 5) -> None:
    st.write("")
    st.markdown("#### 🕒 آخر عمليات السحب")
    products_for_scope = _filter_products_to_user_labs(get_products())
    w = _filter_withdrawals_to_user_labs(get_withdrawals(), products_for_scope)
    if w.empty:
        st.info("لا توجد عمليات سحب بعد.")
        return
    recent = w.tail(limit).iloc[::-1].copy()

    def _txt(value) -> str:
        s = str(value).strip()
        return "" if s.lower() in ("nan", "none", "nat") else s

    products = get_products()
    prod_map = {_txt(r["product_code"]): r for _, r in products.iterrows()} if not products.empty else {}
    movements = get_movements()

    manufacturers, suppliers, expiries, remainings, product_notes = [], [], [], [], []
    for _, row in recent.iterrows():
        code = _txt(row.get("product_code"))
        p = prod_map.get(code)
        manufacturers.append(_txt(p.get("manufacturer")) if p is not None else "")
        suppliers.append(_txt(p.get("supplier")) if p is not None else "")
        expiries.append(_txt(p.get("expiry_date")) if p is not None else "")
        product_notes.append(_txt(p.get("notes")) if p is not None else "")

        remaining = _remaining_quantity(
            row, movements, p["current_stock"] if p is not None else None
        )
        remainings.append("" if remaining is None else f"{remaining:g}")

    recent["manufacturer"] = manufacturers
    recent["supplier"] = suppliers
    recent["expiry_date"] = expiries
    recent["remaining_quantity"] = remainings
    recent["product_notes"] = product_notes

    st.dataframe(
        recent[
            [
                "withdraw_date",
                "product_code",
                "product_name",
                "qty",
                "remaining_quantity",
                "manufacturer",
                "supplier",
                "expiry_date",
                "product_notes",
                "supervisor_name",
                "withdrawn_by",
            ]
        ].rename(
            columns={
                "withdraw_date": "التاريخ والوقت",
                "product_code": "الكود",
                "product_name": "الصنف",
                "qty": "الكمية",
                "remaining_quantity": "الرصيد المتبقي",
                "manufacturer": "شركة الصنع",
                "supplier": "شركة التوريد",
                "expiry_date": "تاريخ الانتهاء",
                "product_notes": "ملاحظات الصنف",
                "supervisor_name": "اسم المسؤول",
                "withdrawn_by": "اسم الساحب",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )


# --------------------------------------------------------------------------- #
#                        3) صفحة إدارة الأصناف
# --------------------------------------------------------------------------- #
ITEMS_INPUT_LTR_CSS = """
<style>
/* حقول الإدخال في إدارة الأصناف: محاذاة النصوص لليسار لعرض الإنجليزي والمختلط بشكل صحيح */
div[data-baseweb="input"] input,
div[data-baseweb="input"] textarea,
div[data-baseweb="textarea"] textarea,
div[data-baseweb="textarea"] input {
    text-align: left !important;
    direction: ltr !important;
}
</style>
"""


def _item_added_by(row) -> str:
    return str(row.get("added_by", "") or "").strip()


def _item_label(row) -> str:
    """عنصر القائمة المنسدلة: الاسم (الكود) — الرصيد — أضافه: المستخدم."""
    base = (
        f'{row["product_name"]} ({row["product_code"]}) '
        f"— رصيد {to_number(row['current_stock']):g}"
    )
    added = _item_added_by(row)
    return f"{base} — أضافه: {added}" if added else base


def _category_options(current: str = "") -> list:
    value = normalize_category(current)
    options = list(PRODUCT_CATEGORIES)
    if value and value not in options:
        options.append(value)
    return options


def _render_inventory_table(df, empty_message: str) -> None:
    if df.empty:
        st.info(empty_message)
        return
    view = df.copy()
    if "added_by" not in view.columns:
        view["added_by"] = ""
    if "category" not in view.columns:
        view["category"] = PRODUCT_CATEGORY_GENERAL
    view["category"] = view["category"].apply(normalize_category)
    st.dataframe(
        view[
            ["product_code", "product_name", "category", "unit", "current_stock", "storage_location", "added_by"]
        ].rename(
            columns={
                "product_code": "الكود",
                "product_name": "اسم الصنف",
                "category": "التصنيف",
                "unit": "الوحدة",
                "current_stock": "الرصيد الحالي",
                "storage_location": "مكان التخزين",
                "added_by": "أضافه",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )


def page_items() -> None:
    header("➕ إدارة الأصناف", "إضافة صنف جديد أو تعديل بياناته أو حذفه من المخزون")
    st.markdown(ITEMS_INPUT_LTR_CSS, unsafe_allow_html=True)

    products = get_products()
    if products.empty:
        st.info("لا توجد أصناف بعد — أضف أول صنف من تبويب «إضافة صنف».")
    else:
        if "category" not in products.columns:
            products = products.copy()
            products["category"] = PRODUCT_CATEGORY_GENERAL
        categories = products["category"].apply(normalize_category)
        is_pcr = categories == PRODUCT_CATEGORY_PCR
        is_chemical = categories == PRODUCT_CATEGORY_CHEMICALS
        is_office = categories == PRODUCT_CATEGORY_OFFICE
        is_computer = categories == PRODUCT_CATEGORY_COMPUTER
        is_reagents = categories.str.upper().isin(
            {category.upper() for category in REAGENTS_CATEGORIES}
        )
        pcr_products = products[is_pcr]
        chemical_products = products[is_chemical]
        office_products = products[is_office]
        computer_products = products[is_computer]
        general_products = products[
            ~is_pcr & ~is_chemical & ~is_office & ~is_computer & ~is_reagents
        ]
        st.markdown("#### 🧬 قسم PCR")
        st.caption("أصناف PCR مخزّنة ومُدارة بشكل منفصل عن باقي المخزن.")
        _render_inventory_table(
            pcr_products,
            "لا توجد أصناف PCR بعد — أضف صنفًا واختر التصنيف «PCR».",
        )
        st.markdown("#### 🧪 قسم الكيماويات")
        st.caption("المواد الكيميائية مخزّنة ومُدارة في قسم مستقل مع بيانات التصنيع والصلاحية.")
        _render_inventory_table(
            chemical_products,
            "لا توجد مواد كيميائية بعد — أضف مادة واختر التصنيف «كيماويات».",
        )
        st.markdown("#### 🗂️ قسم المكتبية")
        st.caption("الأصناف المكتبية مخزّنة ومُدارة في قسم مستقل مع الكميات والتواريخ.")
        _render_inventory_table(
            office_products,
            "لا توجد أصناف مكتبية بعد — أضف صنفًا واختر التصنيف «المكتبية».",
        )
        st.markdown("#### 💻 قسم مستلزمات الكمبيوتر")
        st.caption("مستلزمات الكمبيوتر مخزّنة ومُدارة في قسم مستقل مع المواصفات والتصنيف.")
        _render_inventory_table(
            computer_products,
            "لا توجد مستلزمات كمبيوتر بعد — أضف صنفًا واختر التصنيف «مستلزمات الكمبيوتر».",
        )
        st.markdown("#### 📦 المخزن العام")
        _render_inventory_table(general_products, "لا توجد أصناف في المخزن العام.")

    tab_add, tab_edit, tab_delete = st.tabs(
        ["➕ إضافة صنف", "✏️ تعديل صنف", "🗑️ حذف صنف"]
    )

    with tab_add:
        _render_add_item()
    with tab_edit:
        _render_edit_item()
    with tab_delete:
        _render_delete_item()


def _total_text(qty, unit_raw) -> tuple:
    """(قيمة الإجمالي كنص، هل خانة الوحدة رقمية). الإجمالي = الكمية × الوحدة."""
    unit_text = str(unit_raw or "").strip()
    unit_num = to_number(unit_text, -1.0)
    if not unit_text or unit_num < 0:
        return "", False
    return f"{to_number(qty, 0.0) * unit_num:g}", True


def _render_total_field(total_key: str, qty, unit_raw) -> None:
    """خانة الإجمالي (معطّلة للقراءة فقط) تُحدَّث لحظيًا مع تغيّر الكمية أو الوحدة."""
    total_text, unit_is_number = _total_text(qty, unit_raw)
    st.session_state[total_key] = total_text
    st.text_input(
        "الإجمالي",
        key=total_key,
        disabled=True,
        placeholder="",
        width="stretch",
    )
    if not unit_is_number:
        st.caption("⚠️ أدخل رقمًا في خانة «الوحدة» ليُحسب الإجمالي = الكمية × الوحدة.")


def _render_add_item() -> None:
    if st.session_state.pop("_clear_add_form", False):
        for key in (
            "add_code",
            "add_name",
            "add_date",
            "add_qty",
            "add_unit",
            "add_total",
            "add_mfr",
            "add_sup",
            "add_expiry",
            "add_notes",
            "add_category",
            "add_location",
            "add_serial",
            "add_device_status",
        ):
            st.session_state.pop(key, None)

    st.markdown("#### إضافة صنف جديد")
    c1, c2, c3 = st.columns(3)
    with c1:
        code = st.text_input("كود الصنف *", placeholder="", width="stretch", key="add_code")
    with c2:
        name = st.text_input("اسم الصنف *", placeholder="", width="stretch", key="add_name")
    with c3:
        date_added = st.date_input(
            "تاريخ الإضافة", value=date.today(), width="stretch", key="add_date"
        )
    c4, c5, c6 = st.columns(3)
    with c4:
        start_qty = st.number_input(
            "الكمية", min_value=0.0, step=1.0, value=None, placeholder="", width="stretch",
            key="add_qty",
        )
    with c5:
        unit = st.text_input(
            "الوحدة (قطعة، كرتونة، لتر...)", placeholder="", width="stretch", key="add_unit"
        )
    with c6:
        _render_total_field("add_total", start_qty, unit)
    c7, c8, c9 = st.columns(3)
    with c7:
        manufacturer = st.text_input(
            "شركة الصنع", placeholder="", width="stretch", key="add_mfr"
        )
    with c8:
        supplier = st.text_input(
            "شركة التوريد / المرسل", placeholder="", width="stretch", key="add_sup"
        )
    with c9:
        expiry_date = st.date_input(
            "تاريخ الانتهاء", value=None, width="stretch", key="add_expiry"
        )
    c10, c11 = st.columns(2)
    with c10:
        category = st.selectbox(
            "التصنيف / قسم المخزن",
            options=PRODUCT_CATEGORIES,
            index=0,
            width="stretch",
            key="add_category",
        )
    with c11:
        storage_location = st.text_input(
            "مكان التخزين",
            placeholder=f"مثال: {PCR_STORAGE_SECTION}",
            width="stretch",
            key="add_location",
        )
    serial_number = ""
    device_status = ""
    if category == PRODUCT_CATEGORY_PCR:
        st.caption(f"🧬 أصناف PCR تُخزَّن تلقائيًا في «{PCR_STORAGE_SECTION}» عند ترك مكان التخزين فارغًا.")
        c12, c13 = st.columns(2)
        with c12:
            serial_number = st.text_input(
                "الرقم التسلسلي للجهاز",
                placeholder="",
                width="stretch",
                key="add_serial",
            )
        with c13:
            device_status = st.selectbox(
                "حالة الجهاز",
                options=DEVICE_STATUSES,
                index=0,
                width="stretch",
                key="add_device_status",
            )
    elif category == PRODUCT_CATEGORY_CHEMICALS:
        st.caption(
            f"🧪 المواد الكيميائية تُخزَّن تلقائيًا في «{CHEMICALS_STORAGE_SECTION}» "
            "عند ترك مكان التخزين فارغًا."
        )
    elif category == PRODUCT_CATEGORY_OFFICE:
        st.caption(
            f"🗂️ الأصناف المكتبية تُخزَّن تلقائيًا في «{OFFICE_STORAGE_SECTION}». "
            "لإدخال الكراتين والوحدات داخل الكرتونة استخدم صفحة «قسم المكتبية»."
        )
    elif category == PRODUCT_CATEGORY_COMPUTER:
        st.caption(
            f"💻 مستلزمات الكمبيوتر تُخزَّن تلقائيًا في «{COMPUTER_STORAGE_SECTION}». "
            "لإدخال المواصفات والأرقام التسلسلية والتصنيف استخدم صفحة «قسم مستلزمات الكمبيوتر»."
        )
    notes = st.text_area("ملاحظات", placeholder="", height=90, width="stretch", key="add_notes")
    submitted = st.button(
        "➕ إضافة الصنف", type="primary", use_container_width=True, key="add_submit"
    )

    if submitted:
        ok, msg = add_stock_item(
            name,
            start_qty,
            unit,
            code=code,
            date_added=date_added.strftime("%Y-%m-%d") if date_added else "",
            notes=notes,
            manufacturer=manufacturer,
            supplier=supplier,
            expiry_date=expiry_date.strftime("%Y-%m-%d") if expiry_date else "",
            category=category,
            storage_location=storage_location,
            serial_number=serial_number,
            device_status=device_status,
        )
        if ok:
            st.success(msg)
            added_by = current_username()
            if added_by:
                st.caption(f"👤 الصنف أُضيف بواسطة: {added_by} — سيظهر بجنبه في كل الجداول.")
            saved_notes = str(notes or "").strip()
            if saved_notes:
                st.caption(f"📝 ملاحظات الصنف المحفوظة في قاعدة البيانات: {saved_notes}")
            st.session_state["_clear_add_form"] = True
            st.rerun()
        else:
            st.error(msg)


def _render_edit_item() -> None:
    products = get_products()
    if products.empty:
        st.info("لا توجد أصناف لتعديلها.")
        return

    labels = {
        _item_label(r): str(r["product_code"])
        for _, r in products.iterrows()
    }
    choice = st.selectbox(
        "اختر الصنف المراد تعديله",
        options=list(labels.keys()),
        index=None,
        placeholder="",
        width="stretch",
        key="edit_item_select",
    )
    if choice is None:
        st.caption("اختر صنفًا لعرض بياناته وتعديلها.")
        return

    code = labels[choice]
    product = next(
        (r for _, r in products.iterrows() if str(r["product_code"]).strip() == code),
        None,
    )
    if product is None:
        st.warning("لم يتم العثور على الصنف المحدد.")
        return

    cur_name = _product_note(product.get("product_name"))
    cur_unit = _product_note(product.get("unit"))
    cur_mfr = _product_note(product.get("manufacturer"))
    cur_sup = _product_note(product.get("supplier"))
    cur_notes = _product_note(product.get("notes"))
    cur_location = _product_note(product.get("storage_location"))
    cur_category = normalize_category(product.get("category"))
    cur_serial = _product_note(product.get("serial_number"))
    cur_status_raw = _product_note(product.get("device_status"))
    cur_status = cur_status_raw or DEVICE_STATUS_DEFAULT
    cur_stock = to_number(product.get("current_stock"))
    cur_min = to_number(product.get("min_stock"))
    cur_added = _product_note(product.get("date_added"))

    expiry_raw = _product_note(product.get("expiry_date"))
    cur_expiry = None
    if expiry_raw:
        try:
            cur_expiry = datetime.strptime(expiry_raw[:10], "%Y-%m-%d").date()
        except ValueError:
            cur_expiry = None

    st.markdown("#### تعديل بيانات الصنف")
    code_line = f"كود الصنف: `{code}` (ثابت للحفاظ على ربط السحوبات السابقة)"
    if cur_added:
        code_line += f" — تاريخ الإضافة: {cur_added}"
    st.caption(code_line)
    c1, c2, c3 = st.columns(3)
    with c1:
        name_v = st.text_input(
            "اسم الصنف *", value=cur_name, placeholder="", width="stretch",
            key=f"edit_name_{code}",
        )
    with c2:
        unit_v = st.text_input(
            "الوحدة (قطعة، كرتونة، لتر...)", value=cur_unit, placeholder="", width="stretch",
            key=f"edit_unit_{code}",
        )
    with c3:
        location_v = st.text_input(
            "مكان التخزين", value=cur_location, placeholder="", width="stretch",
            key=f"edit_location_{code}",
        )
    category_options = _category_options(cur_category)
    category_v = st.selectbox(
        "التصنيف / قسم المخزن",
        options=category_options,
        index=category_options.index(cur_category),
        width="stretch",
        key=f"edit_category_{code}",
    )
    serial_v = cur_serial
    status_v = cur_status_raw
    if category_v == PRODUCT_CATEGORY_PCR:
        st.caption(
            f"🧬 أصناف PCR تُخزَّن تلقائيًا في «{PCR_STORAGE_SECTION}» عند ترك مكان التخزين فارغًا."
        )
        status_current = status_v or DEVICE_STATUS_DEFAULT
        status_options = list(DEVICE_STATUSES)
        if status_current not in status_options:
            status_options.append(status_current)
        c12, c13 = st.columns(2)
        with c12:
            serial_v = st.text_input(
                "الرقم التسلسلي للجهاز",
                value=cur_serial,
                placeholder="",
                width="stretch",
                key=f"edit_serial_{code}",
            )
        with c13:
            status_v = st.selectbox(
                "حالة الجهاز",
                options=status_options,
                index=status_options.index(status_current),
                width="stretch",
                key=f"edit_status_{code}",
            )
    q1, q2, q3 = st.columns(3)
    with q1:
        stock_v = st.number_input(
            "الرصيد الحالي",
            min_value=0.0,
            step=1.0,
            value=cur_stock,
            placeholder="",
            width="stretch",
            key=f"edit_stock_{code}",
        )
    with q2:
        min_v = st.number_input(
            "الحد الأدنى",
            min_value=0.0,
            step=1.0,
            value=cur_min,
            placeholder="",
            width="stretch",
            key=f"edit_min_{code}",
        )
    with q3:
        _render_total_field(f"edit_total_{code}", stock_v, unit_v)
    c4, c5, c6 = st.columns(3)
    with c4:
        mfr_v = st.text_input(
            "شركة الصنع", value=cur_mfr, placeholder="", width="stretch",
            key=f"edit_mfr_{code}",
        )
    with c5:
        sup_v = st.text_input(
            "شركة التوريد / المرسل", value=cur_sup, placeholder="", width="stretch",
            key=f"edit_sup_{code}",
        )
    with c6:
        expiry_v = st.date_input(
            "تاريخ الانتهاء",
            value=cur_expiry,
            width="stretch",
            key=f"edit_expiry_{code}",
        )
    notes_v = st.text_area(
        "ملاحظات", value=cur_notes, placeholder="", height=90, width="stretch",
        key=f"edit_notes_{code}",
    )
    submitted = st.button(
        "💾 حفظ التعديلات", type="primary", use_container_width=True,
        key=f"edit_submit_{code}",
    )

    if not submitted:
        return

    name_v = str(name_v or "").strip()
    if not name_v:
        st.error("اسم الصنف مطلوب.")
        return

    new_stock = to_number(stock_v, -1)
    if new_stock < 0:
        st.error("الرصيد الحالي يجب أن يكون صفرًا أو أكثر.")
        return

    updates = {
        "product_name": name_v,
        "unit": str(unit_v or "").strip(),
        "storage_location": str(location_v or "").strip(),
        "current_stock": new_stock,
        "min_stock": to_number(min_v, 0.0),
        "manufacturer": str(mfr_v or "").strip(),
        "supplier": str(sup_v or "").strip(),
        "expiry_date": expiry_v.strftime("%Y-%m-%d") if expiry_v else "",
        "notes": str(notes_v or "").strip(),
        "category": category_v,
        "serial_number": str(serial_v or "").strip(),
        "device_status": str(status_v or "").strip(),
    }
    ok, msg = update_product(code, updates)
    if not ok:
        st.error(msg)
        return

    delta = new_stock - cur_stock
    if abs(delta) > 1e-9:
        record_movement(
            order_no="",
            product_code=code,
            product_name=name_v,
            qty=delta,
            balance_after=new_stock,
            person=current_username() or "تعديل صنف",
            movement_type="تعديل رصيد",
            notes=f"تعديل يدوي للرصيد من {cur_stock:g} إلى {new_stock:g}",
        )
    st.success(f"{msg} 🔄 التعديلات محفوظة في SQLite.")
    st.rerun()


def _render_delete_item() -> None:
    products = get_products()
    if products.empty:
        st.info("لا توجد أصناف للحذف.")
        return

    labels = {
        _item_label(r): str(r["product_code"])
        for _, r in products.iterrows()
    }
    with st.form("delete_item_form"):
        st.markdown("#### حذف صنف نهائيًا")
        st.caption("سيُحذف الصنف من ورقة المخزون. سجل السحوبات السابقة يبقى محفوظًا.")
        choice = st.selectbox("اختر الصنف", options=list(labels.keys()), width="stretch", placeholder="")
        confirmed = st.checkbox("أؤكد رغبتي في حذف هذا الصنف نهائيًا", width="stretch")
        submitted = st.form_submit_button("🗑️ حذف الصنف", type="primary", use_container_width=True)

    if submitted:
        code = labels[choice]
        if not confirmed:
            st.warning("⚠️ يرجى تحديد مربع التأكيد قبل الحذف.")
            return
        ok, msg = delete_product(code, force=True)
        if ok:
            st.success(msg)
            st.rerun()
        else:
            st.error(msg)


def _render_product_delete_form(
    df,
    form_key: str,
    empty_message: str,
    heading: str = "🗑️ حذف صنف نهائيًا",
) -> None:
    if df.empty:
        st.info(empty_message)
        return

    labels = {
        _item_label(row): str(row["product_code"])
        for _, row in df.iterrows()
    }
    with st.form(f"delete_{form_key}_form"):
        st.markdown(f"#### {heading}")
        st.caption(
            "سيُحذف الصنف نهائيًا من قاعدة بيانات SQLite. "
            "تبقى سجلات السحوبات والحركات السابقة محفوظة."
        )
        choice = st.selectbox(
            "اختر الصنف",
            options=list(labels.keys()),
            index=None,
            placeholder="",
            width="stretch",
        )
        confirmed = st.checkbox(
            "أؤكد رغبتي في حذف هذا الصنف نهائيًا", width="stretch"
        )
        submitted = st.form_submit_button(
            "🗑️ حذف الصنف", type="primary", use_container_width=True
        )

    if not submitted:
        return
    if choice is None:
        st.warning("⚠️ يرجى اختيار الصنف المراد حذفه.")
        return
    if not confirmed:
        st.warning("⚠️ يرجى تحديد مربع التأكيد قبل الحذف.")
        return

    ok, msg = delete_product(labels[choice], force=True)
    if ok:
        st.success(msg)
        st.rerun()
    else:
        st.error(msg)


# --------------------------------------------------------------------------- #
#                        4) صفحة قسم PCR المستقل
# --------------------------------------------------------------------------- #
def _pcr_device_view(df) -> pd.DataFrame:
    view = df.copy()
    for column, default in (
        ("serial_number", ""),
        ("manufacturer", ""),
        ("storage_location", ""),
        ("device_status", ""),
    ):
        if column not in view.columns:
            view[column] = default
    view["_quantity"] = view["current_stock"].apply(to_number)
    view["serial_number"] = view["serial_number"].apply(
        lambda value: _product_note(value) or "—"
    )
    view["manufacturer"] = view["manufacturer"].apply(
        lambda value: _product_note(value) or "—"
    )
    view["storage_location"] = view["storage_location"].apply(
        lambda value: _product_note(value) or PCR_STORAGE_SECTION
    )
    view["device_status"] = view["device_status"].apply(
        lambda value: _product_note(value) or "غير محدد"
    )
    return view[
        [
            "product_name",
            "serial_number",
            "manufacturer",
            "storage_location",
            "_quantity",
            "device_status",
        ]
    ].rename(
        columns={
            "product_name": "اسم الجهاز",
            "serial_number": "الرقم التسلسلي",
            "manufacturer": "اسم الشركة المصنعة",
            "storage_location": "مكان التخزين",
            "_quantity": "الكمية",
            "device_status": "حالة الجهاز",
        }
    )


def _render_pcr_devices_table(df, empty_message: str) -> None:
    if df.empty:
        st.info(empty_message)
        return
    st.dataframe(
        _pcr_device_view(df),
        use_container_width=True,
        hide_index=True,
    )


def _render_pcr_add_device(devices) -> None:
    existing_serials = {
        _product_note(value).lower()
        for value in devices.get("serial_number", [])
        if _product_note(value)
    }
    existing_codes = {
        str(value).strip().lower()
        for value in devices.get("product_code", [])
        if str(value).strip()
    }

    with st.form("pcr_add_device_form", clear_on_submit=True):
        st.markdown("#### ➕ إضافة جهاز PCR")
        c1, c2, c3 = st.columns(3)
        with c1:
            device_name = st.text_input("اسم الجهاز *", placeholder="", width="stretch")
        with c2:
            serial_number = st.text_input("الرقم التسلسلي *", placeholder="", width="stretch")
        with c3:
            manufacturer = st.text_input("اسم الشركة المصنعة", placeholder="", width="stretch")
        c4, c5, c6 = st.columns(3)
        with c4:
            storage_location = st.text_input(
                "مكان التخزين", value=PCR_STORAGE_SECTION, width="stretch"
            )
        with c5:
            quantity = st.number_input(
                "الكمية", min_value=0.0, step=1.0, value=None, placeholder="", width="stretch"
            )
        with c6:
            device_status = st.selectbox(
                "حالة الجهاز", options=DEVICE_STATUSES, index=0, width="stretch"
            )
        notes = st.text_area("ملاحظات", placeholder="", height=80, width="stretch")
        submitted = st.form_submit_button(
            "➕ إضافة الجهاز", type="primary", use_container_width=True
        )

    if not submitted:
        return

    device_name = str(device_name or "").strip()
    serial_number = str(serial_number or "").strip()
    if not device_name:
        st.error("اسم الجهاز مطلوب.")
        return
    if not serial_number:
        st.error("الرقم التسلسلي مطلوب.")
        return
    if serial_number.lower() in existing_serials:
        st.error(f"الرقم التسلسلي «{serial_number}» مسجّل مسبقًا لجهاز آخر.")
        return

    code = f"PCR-{serial_number}"
    base_code = code
    suffix = 2
    while code.lower() in existing_codes:
        code = f"{base_code}-{suffix}"
        suffix += 1

    ok, msg = add_stock_item(
        device_name,
        quantity,
        "جهاز",
        code=code,
        notes=notes,
        manufacturer=manufacturer,
        category=PRODUCT_CATEGORY_PCR,
        storage_location=storage_location,
        serial_number=serial_number,
        device_status=device_status,
    )
    if ok:
        st.success(msg)
        st.rerun()
    else:
        st.error(msg)


def _render_pcr_edit_device(devices) -> None:
    if devices.empty:
        st.info("لا توجد أجهزة PCR لتعديلها.")
        return

    labels = {}
    for _, row in devices.iterrows():
        serial = _product_note(row.get("serial_number")) or "بدون رقم تسلسلي"
        labels[
            f'{_product_note(row.get("product_name")) or "جهاز"} — {serial} '
            f'[{row["product_code"]}]'
        ] = str(row["product_code"])
    choice = st.selectbox(
        "اختر جهاز PCR المراد تعديله",
        options=list(labels.keys()),
        index=None,
        placeholder="",
        width="stretch",
        key="pcr_edit_device_select",
    )
    if choice is None:
        st.caption("اختر جهازًا لعرض بياناته وتعديلها.")
        return

    code = labels[choice]
    product = next(
        (r for _, r in devices.iterrows() if str(r["product_code"]).strip() == code),
        None,
    )
    if product is None:
        st.warning("لم يتم العثور على الجهاز المحدد.")
        return

    cur_name = _product_note(product.get("product_name"))
    cur_serial = _product_note(product.get("serial_number"))
    cur_manufacturer = _product_note(product.get("manufacturer"))
    cur_location = _product_note(product.get("storage_location")) or PCR_STORAGE_SECTION
    cur_quantity = to_number(product.get("current_stock"))
    cur_status = _product_note(product.get("device_status")) or DEVICE_STATUS_DEFAULT
    cur_notes = _product_note(product.get("notes"))
    cur_unit = _product_note(product.get("unit")) or "جهاز"

    status_options = list(DEVICE_STATUSES)
    if cur_status not in status_options:
        status_options.append(cur_status)

    with st.form(f"pcr_edit_device_form_{code}"):
        st.markdown(f"#### ✏️ تعديل الجهاز `{code}`")
        c1, c2, c3 = st.columns(3)
        with c1:
            name_v = st.text_input("اسم الجهاز *", value=cur_name, width="stretch")
        with c2:
            serial_v = st.text_input("الرقم التسلسلي *", value=cur_serial, width="stretch")
        with c3:
            manufacturer_v = st.text_input(
                "اسم الشركة المصنعة", value=cur_manufacturer, width="stretch"
            )
        c4, c5, c6 = st.columns(3)
        with c4:
            location_v = st.text_input(
                "مكان التخزين", value=cur_location, width="stretch"
            )
        with c5:
            quantity_v = st.number_input(
                "الكمية", min_value=0.0, step=1.0, value=cur_quantity, width="stretch"
            )
        with c6:
            status_v = st.selectbox(
                "حالة الجهاز",
                options=status_options,
                index=status_options.index(cur_status),
                width="stretch",
            )
        notes_v = st.text_area("ملاحظات", value=cur_notes, height=80, width="stretch")
        submitted = st.form_submit_button(
            "💾 حفظ تعديلات الجهاز", type="primary", use_container_width=True
        )

    if not submitted:
        return

    name_v = str(name_v or "").strip()
    serial_v = str(serial_v or "").strip()
    if not name_v:
        st.error("اسم الجهاز مطلوب.")
        return
    if not serial_v:
        st.error("الرقم التسلسلي مطلوب.")
        return

    other_serials = {
        _product_note(row.get("serial_number")).lower()
        for _, row in devices.iterrows()
        if str(row["product_code"]).strip() != code and _product_note(row.get("serial_number"))
    }
    if serial_v.lower() in other_serials:
        st.error(f"الرقم التسلسلي «{serial_v}» مسجّل مسبقًا لجهاز آخر.")
        return

    new_quantity = to_number(quantity_v, -1)
    if new_quantity < 0:
        st.error("الكمية يجب أن تكون صفرًا أو أكثر.")
        return

    ok, msg = update_product(
        code,
        {
            "product_name": name_v,
            "unit": cur_unit,
            "manufacturer": str(manufacturer_v or "").strip(),
            "storage_location": str(location_v or "").strip(),
            "current_stock": new_quantity,
            "notes": str(notes_v or "").strip(),
            "category": PRODUCT_CATEGORY_PCR,
            "serial_number": serial_v,
            "device_status": status_v,
        },
    )
    if not ok:
        st.error(msg)
        return

    delta = new_quantity - cur_quantity
    if abs(delta) > 1e-9:
        record_movement(
            order_no="",
            product_code=code,
            product_name=name_v,
            qty=delta,
            balance_after=new_quantity,
            person=current_username() or "تعديل جهاز PCR",
            movement_type="تعديل رصيد",
            notes=f"تعديل كمية جهاز PCR من {cur_quantity:g} إلى {new_quantity:g}",
        )
    st.success(msg)
    st.rerun()


def page_pcr() -> None:
    header(
        "🧬 قسم PCR",
        "تتبع أجهزة PCR: الاسم، الرقم التسلسلي، الشركة المصنعة، الموقع، الكمية والحالة",
    )
    st.caption(
        f"يعرض هذا القسم أجهزة تصنيف «PCR» فقط. "
        f"تُخزَّن الأجهزة تلقائيًا في «{PCR_STORAGE_SECTION}» عند ترك مكان التخزين فارغًا."
    )

    pcr = get_pcr_products().copy()
    if not pcr.empty:
        for column in ("serial_number", "manufacturer", "storage_location", "device_status"):
            if column not in pcr.columns:
                pcr[column] = ""
        pcr["_stock"] = pcr["current_stock"].apply(to_number)
        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("عدد أجهزة PCR", len(pcr), width="stretch")
        with c2:
            st.metric("إجمالي الكميات", f"{pcr['_stock'].sum():g}", width="stretch")
        with c3:
            st.metric(
                "أجهزة تحت الصيانة",
                int((pcr["device_status"].apply(_product_note) == "تحت الصيانة").sum()),
                width="stretch",
            )

    tab_list, tab_add, tab_edit, tab_delete = st.tabs(
        ["📋 أجهزة PCR", "➕ إضافة جهاز", "✏️ تعديل جهاز", "🗑️ حذف صنف"]
    )
    with tab_add:
        _render_pcr_add_device(pcr)
    with tab_edit:
        _render_pcr_edit_device(pcr)
    with tab_delete:
        _render_product_delete_form(pcr, "pcr", "لا توجد أجهزة PCR للحذف.")
    with tab_list:
        if pcr.empty:
            st.info("لا توجد أجهزة PCR بعد — أضف أول جهاز من تبويب «إضافة جهاز».")
            return

        search = st.text_input(
            "🔍 ابحث بالاسم أو الرقم التسلسلي أو الشركة المصنعة أو مكان التخزين",
            placeholder="",
            key="pcr_search",
            width="stretch",
        )
        status_filter = st.selectbox(
            "🎛️ تصفية حسب حالة الجهاز",
            options=["الكل"] + DEVICE_STATUSES,
            key="pcr_status_filter",
            width="stretch",
        )
        view = pcr
        if search.strip():
            term = search.strip()
            mask = (
                view["product_code"].astype(str).str.contains(term, case=False, na=False)
                | view["product_name"].astype(str).str.contains(term, case=False, na=False)
                | view["serial_number"].astype(str).str.contains(term, case=False, na=False)
                | view["manufacturer"].astype(str).str.contains(term, case=False, na=False)
                | view["storage_location"].astype(str).str.contains(term, case=False, na=False)
            )
            view = view[mask]
        if status_filter != "الكل":
            view = view[view["device_status"].apply(_product_note) == status_filter]

        st.write("")
        st.markdown(f"#### 📦 أجهزة PCR ({len(view)})")
        _render_pcr_devices_table(view, "لا توجد أجهزة PCR مطابقة للبحث.")

        st.write("")
        st.markdown(f"#### 🗂️ التخزين المنظم داخل {PCR_STORAGE_SECTION}")
        grouped = view.copy()
        if "storage_location" not in grouped.columns:
            grouped["storage_location"] = ""
        grouped["storage_location"] = grouped["storage_location"].apply(
            lambda value: str(value or "").strip() or PCR_STORAGE_SECTION
        )
        for location, group in grouped.groupby("storage_location", sort=True):
            st.markdown(f"##### 📍 {location} — {len(group)} جهاز")
            _render_pcr_devices_table(group, "لا توجد أجهزة في هذا الموقع.")


def _reagent_initial_value(row) -> float:
    starting = to_number(row.get("starting_stock"))
    if starting > 0:
        return starting
    return to_number(row.get("current_stock")) + to_number(row.get("total_withdrawn"))


def _reagent_last_withdrawals() -> dict:
    withdrawals = get_withdrawals()
    if withdrawals.empty:
        return {}
    if "withdraw_date" in withdrawals.columns:
        withdrawals = withdrawals.sort_values("withdraw_date")
    result = {}
    for _, row in withdrawals.iterrows():
        code = str(row.get("product_code", "")).strip()
        if code:
            result[code] = _product_note(row.get("withdrawn_by")) or "—"
    return result


def _reagents_view(df, last_withdrawals: dict, columns: dict) -> pd.DataFrame:
    view = df.copy()
    for column, default in (
        ("manufacturer", ""),
        ("date_added", ""),
        ("expiry_date", ""),
        ("device_condition", ""),
        ("added_by", ""),
        ("starting_stock", 0),
        ("total_withdrawn", 0),
    ):
        if column not in view.columns:
            view[column] = default
    view["_initial"] = view.apply(_reagent_initial_value, axis=1)
    view["_withdrawn"] = view["total_withdrawn"].apply(to_number)
    view["_remaining"] = view["current_stock"].apply(to_number)
    view["manufacturer"] = view["manufacturer"].apply(
        lambda value: _product_note(value) or "—"
    )
    view["date_added"] = view["date_added"].apply(
        lambda value: _product_note(value)[:10] or "—"
    )
    view["expiry_date"] = view["expiry_date"].apply(
        lambda value: _product_note(value)[:10] or "—"
    )
    view["_condition"] = view["device_condition"].apply(
        lambda value: _product_note(value) or "—"
    )
    view["_added_by"] = view["added_by"].apply(
        lambda value: _product_note(value) or "—"
    )
    view["_last_withdrawn_by"] = view["product_code"].apply(
        lambda value: last_withdrawals.get(str(value).strip(), "—")
    )
    return view[
        [
            "product_code",
            "product_name",
            "manufacturer",
            "date_added",
            "expiry_date",
            "_condition",
            "_initial",
            "_withdrawn",
            "_remaining",
            "_added_by",
            "_last_withdrawn_by",
        ]
    ].rename(columns=columns)


def _render_reagents_table(
    df, empty_message: str, last_withdrawals: dict, columns: dict
) -> None:
    if df.empty:
        st.info(empty_message)
        return
    st.dataframe(
        _reagents_view(df, last_withdrawals, columns),
        use_container_width=True,
        hide_index=True,
    )


def _render_reagents_unified_add_form() -> None:
    key_prefix = "reagents_unified"
    if st.session_state.pop(f"{key_prefix}_clear_add", False):
        for suffix in (
            "section_type",
            "code",
            "name",
            "company",
            "date_added",
            "expiry_date",
            "condition",
            "initial",
            "withdrawn",
            "notes",
        ):
            st.session_state.pop(f"{key_prefix}_add_{suffix}", None)

    st.markdown("#### ➕ إضافة كاشف")
    st.caption(f"👤 سيُسجَّل المستخدم الحالي: {current_username() or '—'}")

    section_type = st.selectbox(
        "نوع الكاشف / القسم *",
        options=["PCR", "Sequencing", "Cell Culture"],
        index=0,
        width="stretch",
        key=f"{key_prefix}_add_section_type",
    )
    config = REAGENTS_SECTION_CONFIG[section_type]
    category = config["category"]
    storage_section = config["storage_section"]
    fields = config["fields"]

    st.caption(f"📦 سيُحفظ في: {storage_section} — التصنيف: {category}")

    c1, c2, c3 = st.columns(3)
    with c1:
        code = st.text_input(
            "كود الكاشف *",
            placeholder="",
            width="stretch",
            key=f"{key_prefix}_add_code",
        )
    with c2:
        name = st.text_input(
            "اسم الكاشف *",
            placeholder="",
            width="stretch",
            key=f"{key_prefix}_add_name",
        )
    with c3:
        company = st.text_input(
            "الشركة المصنعة",
            placeholder="",
            width="stretch",
            key=f"{key_prefix}_add_company",
        )
    c4, c5, c6 = st.columns(3)
    with c4:
        date_added = st.date_input(
            "تاريخ الإضافة",
            value=date.today(),
            width="stretch",
            key=f"{key_prefix}_add_date_added",
        )
    with c5:
        expiry_date = st.date_input(
            "تاريخ الانتهاء",
            value=None,
            width="stretch",
            key=f"{key_prefix}_add_expiry_date",
        )
    with c6:
        condition = st.selectbox(
            "الحالة",
            options=DEVICE_CONDITIONS,
            index=0,
            width="stretch",
            key=f"{key_prefix}_add_condition",
        )
    c7, c8, c9 = st.columns(3)
    with c7:
        initial_qty = st.number_input(
            "الكمية الأولية",
            min_value=0.0,
            step=1.0,
            value=None,
            placeholder="",
            width="stretch",
            key=f"{key_prefix}_add_initial",
        )
    with c8:
        withdrawn_qty = st.number_input(
            "الكمية المسحوبة",
            min_value=0.0,
            step=1.0,
            value=0.0,
            width="stretch",
            key=f"{key_prefix}_add_withdrawn",
        )
    with c9:
        remaining = max(to_number(initial_qty) - to_number(withdrawn_qty), 0.0)
        st.metric("الكمية المتبقية", f"{remaining:g}", width="stretch")
    notes = st.text_area(
        "ملاحظات",
        placeholder="",
        height=90,
        width="stretch",
        key=f"{key_prefix}_add_notes",
    )
    submitted = st.button(
        "➕ حفظ الكاشف",
        type="primary",
        use_container_width=True,
        key=f"{key_prefix}_add_submit",
    )
    if not submitted:
        return

    ok, msg = add_reagent_item(
        product_code=code,
        product_name=name,
        company=company,
        date_added=date_added.strftime("%Y-%m-%d") if date_added else "",
        expiry_date=expiry_date.strftime("%Y-%m-%d") if expiry_date else "",
        condition=condition,
        initial_qty=initial_qty,
        withdrawn_qty=withdrawn_qty,
        category=category,
        storage_location=storage_section,
        notes=notes,
    )
    if ok:
        st.success(msg)
        st.session_state[f"{key_prefix}_clear_add"] = True
        st.rerun()
    else:
        st.error(msg)


def _render_reagents_unified_withdraw_form() -> None:
    key_prefix = "reagents_unified"
    all_reagents = []
    allowed_labs = set(_accessible_reagent_types())
    for section_name, config in REAGENTS_SECTION_CONFIG.items():
        if section_name not in allowed_labs:
            continue
        section_data = products_by_category(config["category"]).copy()
        if not section_data.empty:
            section_data["_section"] = section_name
            all_reagents.append(section_data)

    if not all_reagents:
        st.info("لا توجد كواشف متاحة للسحب.")
        return

    devices = pd.concat(all_reagents, ignore_index=True)
    active = devices[devices["current_stock"].apply(to_number) > 0].copy()
    if active.empty:
        st.info("لا توجد كواشف بها كمية متبقية للسحب.")
        return

    labels = {}
    for _, row in active.iterrows():
        remaining = to_number(row.get("current_stock"))
        section = row["_section"]
        labels[
            f'[{section}] {_product_note(row.get("product_name")) or "كاشف"} — '
            f'{_product_note(row.get("product_code"))} — المتبقي {remaining:g}'
        ] = str(row["product_code"])

    choice = st.selectbox(
        "اختر الكاشف",
        options=list(labels.keys()),
        index=None,
        placeholder="اختر كاشفاً من القائمة",
        width="stretch",
        key=f"{key_prefix}_withdraw_select",
    )
    if choice is None:
        st.caption("اختر كاشفاً لتسجيل كمية مسحوبة.")
        return

    code = labels[choice]
    product = active[active["product_code"].astype(str).str.strip() == code].iloc[0]
    remaining = to_number(product.get("current_stock"))
    section = product["_section"]

    with st.form(f"{key_prefix}_withdraw_form"):
        st.markdown(f"#### 📤 تسجيل سحب من `{code}` — القسم: **{section}**")
        st.caption(
            f"اسم الكاشف: {_product_note(product.get('product_name')) or '—'} — "
            f"المتبقي الحالي: {remaining:g}"
        )
        c1, c2 = st.columns(2)
        with c1:
            qty = st.number_input(
                "الكمية المسحوبة *",
                min_value=0.0,
                step=1.0,
                value=None,
                placeholder="",
                width="stretch",
            )
        with c2:
            person = st.text_input(
                "اسم المستخدم الذي قام بالسحب *",
                value=current_username() or "",
                width="stretch",
            )
        c3, c4 = st.columns(2)
        with c3:
            withdraw_date = st.date_input(
                "تاريخ السحب", value=date.today(), width="stretch"
            )
        with c4:
            notes = st.text_input("ملاحظات السحب", placeholder="", width="stretch")
        submitted = st.form_submit_button(
            "📤 تسجيل السحب", type="primary", use_container_width=True
        )

    if not submitted:
        return

    ok, msg = withdraw_reagent_item(
        code,
        qty,
        person,
        withdraw_date.strftime("%Y-%m-%d") if withdraw_date else "",
        notes,
    )
    if ok:
        st.success(msg)
        st.rerun()
    else:
        st.error(msg)


# =========================================================================== #
#                   صفحة ثلاجات الكواشف الموحدة (Reagents Refrigerators)
# =========================================================================== #

REAGENT_TYPE_MAP = {
    "PCR": {
        "category": REAGENTS_CATEGORY_PCR,
        "storage": PCR_STORAGE_SECTION,
        "label": "كاشف PCR"
    },
    "Sequencing": {
        "category": REAGENTS_CATEGORY_SEQUENCING,
        "storage": REAGENTS_STORAGE_SEQUENCING,
        "label": "كاشف Sequencing"
    },
    "Cell Culture": {
        "category": REAGENTS_CATEGORY_CELL_CULTURE,
        "storage": REAGENTS_STORAGE_CELL_CULTURE,
        "label": "كاشف Cell Culture"
    }
}


def _accessible_reagent_types() -> list[str]:
    """أنواع الكواشف المسموح بها للمستخدم الحالي وفق صلاحيات المعامل."""
    if is_admin() or get_user_lab_access() == LAB_ALL:
        return list(REAGENT_TYPE_MAP)
    return [lab for lab in REAGENT_TYPE_MAP if has_lab_access(lab)]


def _filter_products_to_user_labs(products: pd.DataFrame) -> pd.DataFrame:
    """قصر أصناف المستخدم العادي على أقسام الكواشف المصرح بها."""
    if products is None or products.empty or is_admin():
        return products
    allowed = _accessible_reagent_types()
    categories = {
        normalize_category(REAGENT_TYPE_MAP[lab]["category"])
        for lab in allowed
    }
    if "category" not in products.columns:
        return products.iloc[0:0].copy()
    mask = products["category"].apply(normalize_category).isin(categories)
    return products.loc[mask].copy()


def _filter_withdrawals_to_user_labs(
    withdrawals: pd.DataFrame, products: pd.DataFrame | None = None
) -> pd.DataFrame:
    """يعرض سجلات السحب المرتبطة فقط بكواشف المعامل المصرح بها."""
    if withdrawals is None or withdrawals.empty or is_admin():
        return withdrawals
    if products is None:
        products = get_products()
    scoped_products = _filter_products_to_user_labs(products)
    if scoped_products is None or scoped_products.empty or "product_code" not in scoped_products.columns:
        return withdrawals.iloc[0:0].copy()
    allowed_codes = set(scoped_products["product_code"].astype(str).str.strip())
    if "product_code" not in withdrawals.columns:
        return withdrawals.iloc[0:0].copy()
    return withdrawals.loc[
        withdrawals["product_code"].astype(str).str.strip().isin(allowed_codes)
    ].copy()

def page_reagents_unified() -> None:
    header("❄️ ثلاجات الكواشف (Refrigerators)", "إدارة ومتابعة كواشف PCR و Sequencing و Cell Culture")
    
    # الحصول على صلاحية المعمل للمستخدم الحالي
    user_lab = get_user_lab_access()
    username = current_username()
    
    # عرض معلومات الصلاحية
    if user_lab == LAB_ALL:
        st.caption(f"👤 المستخدم: **{username}** | الصلاحية: **جميع المعامل** (PCR, Sequencing, Cell Culture)")
    else:
        st.caption(f"👤 المستخدم: **{username}** | الصلاحية: **معمل {user_lab}** فقط")
    
    # جلب البيانات بناءً على صلاحية المستخدم
    all_reagents = []
    accessible_labs = []
    
    for r_type, conf in REAGENT_TYPE_MAP.items():
        # التحقق من صلاحية الوصول
        has_access = r_type in _accessible_reagent_types()
        if has_access:
            accessible_labs.append(r_type)
            df_cat = products_by_category(conf["category"]).copy()
            if not df_cat.empty:
                df_cat["_reagent_section"] = r_type
                all_reagents.append(df_cat)
    
    if not accessible_labs:
        st.error("⚠️ ليس لديك صلاحية للوصول إلى أي معمل.")
        return

    if all_reagents:
        full_df = pd.concat(all_reagents, ignore_index=True)
    else:
        full_df = pd.DataFrame()

    # تجهيز الأعمدة والحسابات
    if not full_df.empty:
        for col, default in (
            ("manufacturer", ""),
            ("device_condition", ""),
            ("starting_stock", 0),
            ("total_withdrawn", 0),
            ("current_stock", 0),
            ("date_added", ""),
            ("expiry_date", ""),
            ("added_by", ""),
        ):
            if col not in full_df.columns:
                full_df[col] = default

        full_df["_initial"] = full_df.apply(_reagent_initial_value, axis=1)
        full_df["_withdrawn"] = full_df["total_withdrawn"].apply(to_number)
        full_df["_remaining"] = full_df["current_stock"].apply(to_number)
        
        # إضافة تحذير للكواشف القريبة من النفاذ (أقل من 20% من الكمية الأولية)
        full_df["_low_stock"] = full_df.apply(
            lambda row: row["_remaining"] < (row["_initial"] * 0.2) if row["_initial"] > 0 else False,
            axis=1
        )
        low_stock_count = int(full_df["_low_stock"].sum())

        # بطاقات إحصائيات سريعة
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.metric("إجمالي الكواشف", len(full_df), width="stretch")
        with c2:
            st.metric("الكمية الأولية الكلية", f"{full_df['_initial'].sum():g}", width="stretch")
        with c3:
            st.metric("المتبقي في الثلاجات", f"{full_df['_remaining'].sum():g}", width="stretch")
        with c4:
            st.metric("⚠️ كواشف قاربت على النفاذ", low_stock_count, delta=None, delta_color="inverse", width="stretch")

    last_withdrawals = _reagent_last_withdrawals()

    # التابات العامة الموحدة
    tab_list, tab_add, tab_withdraw, tab_delete = st.tabs([
        "📋 سجل ومخزون الكواشف",
        "➕ إضافة كاشف جديد",
        "📤 تسجيل سحب كاشف",
        "🗑️ حذف كاشف"
    ])

    # ---------------- 1) إضافة كاشف ---------------- #
    with tab_add:
        st.markdown("#### ➕ إضافة كاشف إلى الثلاجة")
        
        # تصفية الخيارات بناءً على صلاحية المستخدم
        with st.form("add_unified_reagent_form", clear_on_submit=True):
            r_type_selected = st.selectbox(
                "📂 اختر القسم التابع له الكاشف *",
                options=accessible_labs,
                width="stretch",
                key="unified_reagent_type_select"
            )

            target_conf = REAGENT_TYPE_MAP[r_type_selected]
            st.caption(f"سيتم حفظ الكاشف ضمن تصنيف «{target_conf['category']}» في موقع التخزين: «{target_conf['storage']}».")

            c1, c2, c3 = st.columns(3)
            with c1:
                code = st.text_input(f"كود كاشف {r_type_selected} *", width="stretch")
            with c2:
                name = st.text_input(f"اسم كاشف {r_type_selected} *", width="stretch")
            with c3:
                company = st.text_input("الشركة المصنعة", width="stretch")

            c4, c5, c6 = st.columns(3)
            with c4:
                date_added = st.date_input("تاريخ الإضافة", value=date.today(), width="stretch")
            with c5:
                expiry_date = st.date_input("تاريخ الانتهاء", value=None, width="stretch")
            with c6:
                condition = st.selectbox("حالة الكاشف", options=DEVICE_CONDITIONS, index=0, width="stretch")

            c7, c8 = st.columns(2)
            with c7:
                initial_qty = st.number_input("الكمية الأولية *", min_value=0.0, step=1.0, value=None, width="stretch")
            with c8:
                withdrawn_qty = st.number_input("الكمية المسحوبة المبدئية", min_value=0.0, step=1.0, value=0.0, width="stretch")

            notes = st.text_area("ملاحظات", height=80, width="stretch")
            submitted = st.form_submit_button("➕ حفظ الكاشف في الثلاجة", type="primary", use_container_width=True)

            if submitted:
                if not code.strip() or not name.strip():
                    st.error("الكود واسم الكاشف حقول إلزامية.")
                elif to_number(initial_qty, -1) < 0:
                    st.error("يرجى إدخال كمية أولية صحيحة.")
                else:
                    ok, msg = add_reagent_item(
                        product_code=code.strip(),
                        product_name=name.strip(),
                        company=company.strip(),
                        date_added=date_added.strftime("%Y-%m-%d") if date_added else "",
                        expiry_date=expiry_date.strftime("%Y-%m-%d") if expiry_date else "",
                        condition=condition,
                        initial_qty=initial_qty,
                        withdrawn_qty=withdrawn_qty,
                        category=target_conf["category"],
                        storage_location=target_conf["storage"],
                        notes=notes.strip(),
                    )
                    if ok:
                        st.success(f"✅ تمت إضافة ({name}) بنجاح إلى قسم {r_type_selected}!")
                        st.rerun()
                    else:
                        st.error(msg)

    # ---------------- 2) تسجيل سحب كاشف (أولوية لمعمل المستخدم) ---------------- #
    with tab_withdraw:
        st.markdown("#### 📤 تسجيل سحب كاشف من الثلاجة")
        
        if user_lab != LAB_ALL:
            st.info(f"🎯 **أولوية السحب**: سيتم عرض كواشف معمل **{user_lab}** أولاً")
        
        if full_df.empty:
            st.info("لا توجد كواشف مسجلة في الثلاجات لسحبها.")
        else:
            active_reagents = full_df[full_df["current_stock"].apply(to_number) > 0].copy()
            if active_reagents.empty:
                st.info("جميع الكواشف رصيدها المتبقي 0 حالياً.")
            else:
                # ترتيب الكواشف: معمل المستخدم أولاً
                if user_lab != LAB_ALL:
                    user_lab_reagents = active_reagents[active_reagents["_reagent_section"] == user_lab]
                    other_reagents = active_reagents[active_reagents["_reagent_section"] != user_lab]
                    active_reagents = pd.concat([user_lab_reagents, other_reagents], ignore_index=True)
                
                reagent_options = {}
                for _, row in active_reagents.iterrows():
                    sec = row.get("_reagent_section", "")
                    cd = _product_note(row.get("product_code"))
                    nm = _product_note(row.get("product_name"))
                    rem = to_number(row.get("current_stock"))
                    
                    # إضافة علامة تحذير للكواشف القريبة من النفاذ
                    warning = " ⚠️ قارب على النفاذ" if row.get("_low_stock", False) else ""
                    label = f"[{sec}] {nm} (كود: {cd}) — المتبقي: {rem:g}{warning}"
                    reagent_options[label] = cd

                chosen_label = st.selectbox(
                    "اختر الكاشف المراد السحب منه *",
                    options=list(reagent_options.keys()),
                    index=None,
                    placeholder="ابحث واختر الكاشف...",
                    width="stretch"
                )

                if chosen_label:
                    selected_code = reagent_options[chosen_label]
                    selected_row = active_reagents[active_reagents["product_code"].astype(str).str.strip() == selected_code].iloc[0]
                    cur_rem = to_number(selected_row.get("current_stock"))
                    selected_section = selected_row.get("_reagent_section")

                    with st.form("unified_withdraw_form"):
                        st.caption(f"القسم: **{selected_section}** | الكود: **{selected_code}** | الرصيد المتبقي: **{cur_rem:g}**")
                        w_c1, w_c2 = st.columns(2)
                        with w_c1:
                            w_qty = st.number_input("الكمية المسحوبة *", min_value=0.0, max_value=float(cur_rem), step=1.0, value=None, width="stretch")
                        with w_c2:
                            w_person = st.text_input("اسم المستخدم القائم بالسحب *", value=username, width="stretch")

                        w_c3, w_c4 = st.columns(2)
                        with w_c3:
                            w_date = st.date_input("تاريخ السحب", value=date.today(), width="stretch")
                        with w_c4:
                            w_notes = st.text_input("ملاحظات السحب", placeholder="", width="stretch")

                        w_sub = st.form_submit_button("📤 تأكيد سحب الكمية", type="primary", use_container_width=True)

                    if w_sub:
                        if to_number(w_qty, 0) <= 0:
                            st.error("أدخل كمية مسحوبة أكبر من صفر.")
                        elif not w_person.strip():
                            st.error("اسم المستخدم القائم بالسحب مطلوب.")
                        else:
                            ok, msg = withdraw_reagent_item(
                                selected_code,
                                w_qty,
                                w_person.strip(),
                                w_date.strftime("%Y-%m-%d") if w_date else "",
                                w_notes.strip()
                            )
                            if ok:
                                st.success(f"✅ تم سحب {w_qty:g} من كاشف ({selected_row.get('product_name')}) بنجاح!")
                                st.rerun()
                            else:
                                st.error(msg)

    # ---------------- 3) حذف كاشف ---------------- #
    with tab_delete:
        st.markdown("#### 🗑️ حذف كاشف من الثلاجة")
        if full_df.empty:
            st.info("لا توجد كواشف للحذف.")
        else:
            del_options = {
                f"[{r.get('_reagent_section')}] {_product_note(r.get('product_name'))} (كود: {_product_note(r.get('product_code'))})": str(r.get("product_code"))
                for _, r in full_df.iterrows()
            }
            with st.form("unified_delete_reagent_form"):
                del_choice = st.selectbox("اختر الكاشف المراد حذفه نهائياً", options=list(del_options.keys()), index=None, width="stretch")
                confirmed = st.checkbox("أؤكد رغبتي في حذف هذا الكاشف نهائياً", width="stretch")
                del_sub = st.form_submit_button("🗑️ حذف الكاشف", type="primary", use_container_width=True)

            if del_sub:
                if not del_choice:
                    st.warning("يرجى اختيار كاشف أولاً.")
                elif not confirmed:
                    st.warning("يرجى تأكيد الحذف عبر المربع.")
                else:
                    ok, msg = delete_product(del_options[del_choice], force=True)
                    if ok:
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)

    # ---------------- 4) جدول العرض والفلترة ---------------- #
    with tab_list:
        if full_df.empty:
            st.info(f"لا توجد كواشف مسجلة في {'معمل ' + user_lab if user_lab != LAB_ALL else 'المعامل المتاحة'} بعد. استخدم تبويب «➕ إضافة كاشف جديد».")
            return

        # الفلاتر
        f_col1, f_col2, f_col3 = st.columns([1, 1, 2])
        with f_col1:
            filter_options = ["الكل"] + accessible_labs
            cat_filter = st.selectbox("🗂️ عرض قسم محدد:", filter_options, key="reagent_view_filter")
        with f_col2:
            stock_filter = st.selectbox("⚠️ حالة المخزون:", ["الكل", "قارب على النفاذ", "متوفر"], key="stock_status_filter")
        with f_col3:
            search_txt = st.text_input("🔍 ابحث بالاسم أو الكود أو الشركة", placeholder="", key="reagent_search_txt")

        display_df = full_df.copy()
        
        # تطبيق الفلاتر
        if cat_filter != "الكل":
            display_df = display_df[display_df["_reagent_section"] == cat_filter]
        
        if stock_filter == "قارب على النفاذ":
            display_df = display_df[display_df["_low_stock"] == True]
        elif stock_filter == "متوفر":
            display_df = display_df[display_df["_low_stock"] == False]

        if search_txt.strip():
            term = search_txt.strip()
            display_df = display_df[
                display_df["product_code"].astype(str).str.contains(term, case=False, na=False)
                | display_df["product_name"].astype(str).str.contains(term, case=False, na=False)
                | display_df["manufacturer"].astype(str).str.contains(term, case=False, na=False)
            ]

        if display_df.empty:
            st.info("لا توجد نتائج مطابقة لمعايير البحث.")
            return

        # تنسيق الجدول للعرض
        display_df["_last_withdrawn_by"] = display_df["product_code"].apply(
            lambda val: last_withdrawals.get(str(val).strip(), "—")
        )
        display_df["_status"] = display_df["_low_stock"].apply(lambda x: "⚠️ قارب على النفاذ" if x else "✓ متوفر")

        st.markdown(f"#### 📊 عرض {len(display_df)} كاشف")
        
        table_cols = {
            "_reagent_section": "القسم",
            "product_code": "الكود",
            "product_name": "اسم الكاشف",
            "manufacturer": "الشركة المصنعة",
            "_initial": "الكمية الأولية",
            "_withdrawn": "المسحوب",
            "_remaining": "المتبقي",
            "_status": "الحالة",
            "date_added": "تاريخ الإضافة",
            "expiry_date": "تاريخ الانتهاء",
            "device_condition": "الحالة",
            "_last_withdrawn_by": "آخر سحب بواسطة",
        }

        st.dataframe(
            display_df[list(table_cols.keys())].rename(columns=table_cols),
            use_container_width=True,
            hide_index=True
        )

    if all_reagents:
        full_df = pd.concat(all_reagents, ignore_index=True)
    else:
        full_df = pd.DataFrame()

    # تجهيز الأعمدة والحسابات
    if not full_df.empty:
        for col, default in (
            ("manufacturer", ""),
            ("device_condition", ""),
            ("starting_stock", 0),
            ("total_withdrawn", 0),
            ("current_stock", 0),
            ("date_added", ""),
            ("expiry_date", ""),
            ("added_by", ""),
        ):
            if col not in full_df.columns:
                full_df[col] = default

        full_df["_initial"] = full_df.apply(_reagent_initial_value, axis=1)
        full_df["_withdrawn"] = full_df["total_withdrawn"].apply(to_number)
        full_df["_remaining"] = full_df["current_stock"].apply(to_number)

        # بطاقات إحصائيات سريعة
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.metric("إجمالي الكواشف", len(full_df), width="stretch")
        with c2:
            st.metric("الكمية الأولية الكلية", f"{full_df['_initial'].sum():g}", width="stretch")
        with c3:
            st.metric("إجمالي المسحوب", f"{full_df['_withdrawn'].sum():g}", width="stretch")
        with c4:
            st.metric("المتبقي في الثلاجات", f"{full_df['_remaining'].sum():g}", width="stretch")

    last_withdrawals = _reagent_last_withdrawals()

    # التابات العامة الموحدة
    tab_list, tab_add, tab_withdraw, tab_delete = st.tabs([
        "📋 سجل ومخزون الكواشف",
        "➕ إضافة كاشف جديد",
        "📤 تسجيل سحب كاشف",
        "🗑️ حذف كاشف"
    ])

    # ---------------- 1) إضافة كاشف ---------------- #
    with tab_add:
        st.markdown("#### ➕ إضافة كاشف إلى الثلاجة")
        with st.form("add_unified_reagent_form", clear_on_submit=True):
            r_type_selected = st.selectbox(
                "📂 اختر القسم التابع له الكاشف *",
                options=["PCR", "Sequencing", "Cell Culture"],
                width="stretch",
                key="unified_reagent_type_select"
            )

            target_conf = REAGENT_TYPE_MAP[r_type_selected]
            st.caption(f"سيتم حفظ الكاشف ضمن تصنيف «{target_conf['category']}» في موقع التخزين: «{target_conf['storage']}».")

            c1, c2, c3 = st.columns(3)
            with c1:
                code = st.text_input(f"كود كاشف {r_type_selected} *", width="stretch")
            with c2:
                name = st.text_input(f"اسم كاشف {r_type_selected} *", width="stretch")
            with c3:
                company = st.text_input("الشركة المصنعة", width="stretch")

            c4, c5, c6 = st.columns(3)
            with c4:
                date_added = st.date_input("تاريخ الإضافة", value=date.today(), width="stretch")
            with c5:
                expiry_date = st.date_input("تاريخ الانتهاء", value=None, width="stretch")
            with c6:
                condition = st.selectbox("حالة الكاشف", options=DEVICE_CONDITIONS, index=0, width="stretch")

            c7, c8 = st.columns(2)
            with c7:
                initial_qty = st.number_input("الكمية الأولية *", min_value=0.0, step=1.0, value=None, width="stretch")
            with c8:
                withdrawn_qty = st.number_input("الكمية المسحوبة المبدئية", min_value=0.0, step=1.0, value=0.0, width="stretch")

            notes = st.text_area("ملاحظات", height=80, width="stretch")
            submitted = st.form_submit_button("➕ حفظ الكاشف في الثلاجة", type="primary", use_container_width=True)

            if submitted:
                if not code.strip() or not name.strip():
                    st.error("الكود واسم الكاشف حقول إلزامية.")
                elif to_number(initial_qty, -1) < 0:
                    st.error("يرجى إدخال كمية أولية صحيحة.")
                else:
                    ok, msg = add_reagent_item(
                        product_code=code.strip(),
                        product_name=name.strip(),
                        company=company.strip(),
                        date_added=date_added.strftime("%Y-%m-%d") if date_added else "",
                        expiry_date=expiry_date.strftime("%Y-%m-%d") if expiry_date else "",
                        condition=condition,
                        initial_qty=initial_qty,
                        withdrawn_qty=withdrawn_qty,
                        category=target_conf["category"],
                        storage_location=target_conf["storage"],
                        notes=notes.strip(),
                    )
                    if ok:
                        st.success(f"✅ تمت إضافة ({name}) بنجاح إلى قسم {r_type_selected}!")
                        st.rerun()
                    else:
                        st.error(msg)

    # ---------------- 2) تسجيل سحب كاشف ---------------- #
    with tab_withdraw:
        st.markdown("#### 📤 تسجيل سحب كاشف من الثلاجة")
        if full_df.empty:
            st.info("لا توجد كواشف مسجلة في الثلاجات لسحبها.")
        else:
            active_reagents = full_df[full_df["current_stock"].apply(to_number) > 0].copy()
            if active_reagents.empty:
                st.info("جميع الكواشف رصيدها المتبقي 0 حالياً.")
            else:
                reagent_options = {}
                for _, row in active_reagents.iterrows():
                    sec = row.get("_reagent_section", "")
                    cd = _product_note(row.get("product_code"))
                    nm = _product_note(row.get("product_name"))
                    rem = to_number(row.get("current_stock"))
                    label = f"[{sec}] {nm} (كود: {cd}) — المتبقي: {rem:g}"
                    reagent_options[label] = cd

                chosen_label = st.selectbox(
                    "اختر الكاشف المراد السحب منه *",
                    options=list(reagent_options.keys()),
                    index=None,
                    placeholder="ابحث واختر الكاشف...",
                    width="stretch"
                )

                if chosen_label:
                    selected_code = reagent_options[chosen_label]
                    selected_row = active_reagents[active_reagents["product_code"].astype(str).str.strip() == selected_code].iloc[0]
                    cur_rem = to_number(selected_row.get("current_stock"))

                    with st.form("unified_withdraw_form"):
                        st.caption(f"القسم: **{selected_row.get('_reagent_section')}** | الكود: **{selected_code}** | الرصيد المتبقي: **{cur_rem:g}**")
                        w_c1, w_c2 = st.columns(2)
                        with w_c1:
                            w_qty = st.number_input("الكمية المسحوبة *", min_value=0.0, max_value=float(cur_rem), step=1.0, value=None, width="stretch")
                        with w_c2:
                            w_person = st.text_input("اسم المستخدم القائم بالسحب *", value=current_username() or "", width="stretch")

                        w_c3, w_c4 = st.columns(2)
                        with w_c3:
                            w_date = st.date_input("تاريخ السحب", value=date.today(), width="stretch")
                        with w_c4:
                            w_notes = st.text_input("ملاحظات السحب", placeholder="", width="stretch")

                        w_sub = st.form_submit_button("📤 تأكيد سحب الكمية", type="primary", use_container_width=True)

                    if w_sub:
                        if to_number(w_qty, 0) <= 0:
                            st.error("أدخل كمية مسحوبة أكبر من صفر.")
                        elif not w_person.strip():
                            st.error("اسم المستخدم القائم بالسحب مطلوب.")
                        else:
                            ok, msg = withdraw_reagent_item(
                                selected_code,
                                w_qty,
                                w_person.strip(),
                                w_date.strftime("%Y-%m-%d") if w_date else "",
                                w_notes.strip()
                            )
                            if ok:
                                st.success(f"✅ تم سحب {w_qty:g} من كاشف ({selected_row.get('product_name')}) بنجاح!")
                                st.rerun()
                            else:
                                st.error(msg)

    # ---------------- 3) حذف كاشف ---------------- #
    with tab_delete:
        st.markdown("#### 🗑️ حذف كاشف من الثلاجة")
        if full_df.empty:
            st.info("لا توجد كواشف للحذف.")
        else:
            del_options = {
                f"[{r.get('_reagent_section')}] {_product_note(r.get('product_name'))} (كود: {_product_note(r.get('product_code'))})": str(r.get("product_code"))
                for _, r in full_df.iterrows()
            }
            with st.form("unified_delete_reagent_form"):
                del_choice = st.selectbox("اختر الكاشف المراد حذفه نهائياً", options=list(del_options.keys()), index=None, width="stretch")
                confirmed = st.checkbox("أؤكد رغبتي في حذف هذا الكاشف نهائياً", width="stretch")
                del_sub = st.form_submit_button("🗑️ حذف الكاشف", type="primary", use_container_width=True)

            if del_sub:
                if not del_choice:
                    st.warning("يرجى اختيار كاشف أولاً.")
                elif not confirmed:
                    st.warning("يرجى تأكيد الحذف عبر المربع.")
                else:
                    ok, msg = delete_product(del_options[del_choice], force=True)
                    if ok:
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)

    # ---------------- 4) جدول العرض والفلترة ---------------- #
    with tab_list:
        if full_df.empty:
            st.info("لا توجد كواشف مسجلة في الثلاجة بعد. استخدم تبويب «➕ إضافة كاشف جديد».")
            return

        f_col1, f_col2 = st.columns([1, 2])
        with f_col1:
            cat_filter = st.selectbox("🗂️ عرض قسم محدد:", ["الكل", "PCR", "Sequencing", "Cell Culture"], key="reagent_view_filter")
        with f_col2:
            search_txt = st.text_input("🔍 ابحث بالاسم أو الكود أو الشركة", placeholder="", key="reagent_search_txt")

        display_df = full_df.copy()
        if cat_filter != "الكل":
            display_df = display_df[display_df["_reagent_section"] == cat_filter]

        if search_txt.strip():
            term = search_txt.strip()
            display_df = display_df[
                display_df["product_code"].astype(str).str.contains(term, case=False, na=False)
                | display_df["product_name"].astype(str).str.contains(term, case=False, na=False)
                | display_df["manufacturer"].astype(str).str.contains(term, case=False, na=False)
            ]

        # تنسيق الجدول للعرض
        display_df["_last_withdrawn_by"] = display_df["product_code"].apply(
            lambda val: last_withdrawals.get(str(val).strip(), "—")
        )

        table_cols = {
            "_reagent_section": "القسم",
            "product_code": "الكود",
            "product_name": "اسم الكاشف",
            "manufacturer": "الشركة المصنعة",
            "device_condition": "الحالة",
            "_initial": "الكمية الأولية",
            "_withdrawn": "الكمية المسحوبة",
            "_remaining": "الكمية المتبقية",
            "added_by": "المسؤول عن الإضافة",
            "_last_withdrawn_by": "آخر سحب بواسطة",
            "date_added": "تاريخ الإضافة",
            "expiry_date": "تاريخ الانتهاء",
        }

        st.dataframe(
            display_df[list(table_cols.keys())].rename(columns=table_cols),
            use_container_width=True,
            hide_index=True
        )


def page_reagents_pcr() -> None:
    page_reagents_unified()


def page_reagents_sequencing() -> None:
    page_reagents_unified()


def page_reagents_cell_culture() -> None:
    page_reagents_unified()


# --------------------------------------------------------------------------- #
#                        5) صفحة قسم الكيماويات المستقل
# --------------------------------------------------------------------------- #
def _date_value(value):
    text = _product_note(value)
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(text[:10], fmt).date()
        except ValueError:
            continue
    return None


def _chemicals_view(df) -> pd.DataFrame:
    view = df.copy()
    for column in ("manufacturer", "storage_location", "date_added", "expiry_date"):
        if column not in view.columns:
            view[column] = ""
    view["_count"] = view["current_stock"].apply(to_number)
    view["manufacturer"] = view["manufacturer"].apply(
        lambda value: _product_note(value) or "—"
    )
    view["storage_location"] = view["storage_location"].apply(
        lambda value: _product_note(value) or CHEMICALS_STORAGE_SECTION
    )
    view["date_added"] = view["date_added"].apply(
        lambda value: _product_note(value) or "—"
    )
    view["expiry_date"] = view["expiry_date"].apply(
        lambda value: _product_note(value) or "—"
    )
    return view[
        [
            "product_code",
            "product_name",
            "manufacturer",
            "_count",
            "storage_location",
            "date_added",
            "expiry_date",
        ]
    ].rename(
        columns={
            "product_code": "الكود",
            "product_name": "اسم المادة الكيميائية",
            "manufacturer": "اسم الشركة المصنعة",
            "_count": "العدد",
            "storage_location": "مكان التخزين",
            "date_added": "تاريخ الإضافة",
            "expiry_date": "تاريخ الانتهاء",
        }
    )


def _render_chemicals_table(df, empty_message: str) -> None:
    if df.empty:
        st.info(empty_message)
        return
    st.dataframe(_chemicals_view(df), use_container_width=True, hide_index=True)


def _render_chemical_withdraw_form(chemicals) -> None:
    if chemicals.empty:
        st.info("لا توجد مواد كيميائية لسحبها — أضف مادة أولًا.")
        return

    labels = {}
    for _, row in chemicals.iterrows():
        name = _product_note(row.get("product_name")) or "مادة كيميائية"
        stock = to_number(row.get("current_stock"))
        unit = _product_note(row.get("unit"))
        suffix = f" {unit}" if unit else ""
        labels[f'{name} [{row["product_code"]}] — الرصيد {stock:g}{suffix}'] = str(
            row["product_code"]
        )

    choice = st.selectbox(
        "اختر المادة الكيميائية المراد سحبها",
        options=list(labels.keys()),
        width="stretch",
        key="chemical_withdraw_select",
    )
    code = labels[choice]
    product = next(
        (r for _, r in chemicals.iterrows() if str(r["product_code"]).strip() == code),
        None,
    )
    if product is None:
        st.warning("لم يتم العثور على المادة المحددة.")
        return

    stock = to_number(product.get("current_stock"))
    manufacturer = _product_note(product.get("manufacturer")) or "—"
    location = _product_note(product.get("storage_location")) or CHEMICALS_STORAGE_SECTION
    expiry = _product_note(product.get("expiry_date")) or "—"
    st.caption(
        f"الرصيد الحالي: **{stock:g}** • الشركة المصنعة: **{manufacturer}** • "
        f"مكان التخزين: **{location}** • تاريخ الانتهاء: **{expiry}**"
    )
    if stock <= 0:
        st.warning("لا يوجد رصيد متاح من هذه المادة حاليًا.")
        return

    with st.form("chemical_withdraw_form", clear_on_submit=True):
        st.markdown("#### بيانات سحب المادة الكيميائية")
        q1, _q2 = st.columns(2)
        with q1:
            qty = st.number_input(
                "الكمية المسحوبة *",
                min_value=0.0,
                step=1.0,
                value=None,
                placeholder="",
                width="stretch",
            )
        c1, c2 = st.columns(2)
        with c1:
            person = st.text_input(
                "اسم الساحب / المستلم *", placeholder="", width="stretch"
            )
        with c2:
            supervisor = st.text_input(
                "اسم المسؤول / أمين المخزن *", placeholder="", width="stretch"
            )

        stamp_now = datetime.now()
        d1, h1, m1, a1 = st.columns(4)
        with d1:
            wdate = st.date_input("تاريخ السحب", value=stamp_now.date(), width="stretch")
        with h1:
            hour12 = st.selectbox(
                "الساعة",
                options=list(range(1, 13)),
                index=(stamp_now.hour % 12 or 12) - 1,
                width="stretch",
            )
        with m1:
            minute = st.selectbox(
                "الدقيقة",
                options=list(range(0, 60)),
                index=stamp_now.minute,
                format_func=lambda m: f"{m:02d}",
                width="stretch",
            )
        with a1:
            ampm = st.selectbox(
                "ص / م",
                options=["ص", "م"],
                index=0 if stamp_now.hour < 12 else 1,
                width="stretch",
            )
        notes = st.text_area(
            "ملاحظات السحب", placeholder="", height=80, width="stretch"
        )
        submitted = st.form_submit_button(
            "📤 تسجيل سحب المادة", type="primary", use_container_width=True
        )

    if not submitted:
        return

    hour24 = (int(hour12) % 12) + (12 if ampm == "م" else 0)
    stamp = (
        f"{wdate.strftime('%Y-%m-%d')} {hour24:02d}:{int(minute):02d}:00"
        if wdate
        else ""
    )
    ok, msg = withdraw_chemical(
        code, qty, person, stamp, supervisor, notes=notes
    )
    if ok:
        st.success(msg)
        st.rerun()
    else:
        st.error(msg)


def _render_chemical_withdrawals(chemicals) -> None:
    withdrawals = get_withdrawals()
    if withdrawals.empty:
        st.info("لا توجد عمليات سحب كيميائية مسجلة بعد.")
        return

    chemical_codes = {
        _product_note(row.get("product_code")) for _, row in chemicals.iterrows()
    }
    chemical_codes.discard("")
    if not chemical_codes:
        st.info("لا توجد عمليات سحب كيميائية مسجلة بعد.")
        return

    history = withdrawals[
        withdrawals["product_code"].apply(_product_note).isin(chemical_codes)
    ].copy()
    if history.empty:
        st.info("لا توجد عمليات سحب كيميائية مسجلة بعد.")
        return

    search = st.text_input(
        "🔍 ابحث بالكود أو الاسم أو اسم الساحب أو المسؤول",
        placeholder="",
        key="chemical_withdraw_search",
        width="stretch",
    )
    if search.strip():
        term = search.strip()
        mask = (
            history["product_code"].astype(str).str.contains(term, case=False, na=False)
            | history["product_name"].astype(str).str.contains(term, case=False, na=False)
            | history["withdrawn_by"].astype(str).str.contains(term, case=False, na=False)
            | history["supervisor_name"].astype(str).str.contains(term, case=False, na=False)
        )
        history = history[mask]
        if history.empty:
            st.info("لا توجد عمليات سحب مطابقة للبحث.")
            return

    movements = get_movements()
    fallback_map = {
        _product_note(row.get("product_code")): to_number(row.get("current_stock"))
        for _, row in chemicals.iterrows()
    }

    rows = []
    for _, row in history.iloc[::-1].iterrows():
        code = _product_note(row.get("product_code"))
        remaining = _remaining_quantity(row, movements, fallback_map.get(code))
        rows.append(
            {
                "التاريخ والوقت": _product_note(row.get("withdraw_date")),
                "الكود": code,
                "المادة الكيميائية": _product_note(row.get("product_name")),
                "الكمية المسحوبة": to_number(row.get("qty")),
                "الرصيد المتبقي": "" if remaining is None else f"{remaining:g}",
                "اسم الساحب / المستلم": _product_note(row.get("withdrawn_by")),
                "اسم المسؤول / أمين المخزن": _product_note(row.get("supervisor_name")),
                "ملاحظات": _product_note(row.get("notes")),
                "وقت التسجيل": _product_note(row.get("created_at")),
            }
        )

    total_qty = sum(to_number(row.get("qty")) for _, row in history.iterrows())
    c1, c2 = st.columns(2)
    with c1:
        st.metric("عدد عمليات السحب", len(history), width="stretch")
    with c2:
        st.metric("إجمالي الكمية المسحوبة", f"{total_qty:g}", width="stretch")
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def _render_chemical_add_form() -> None:
    with st.form("chemical_add_form", clear_on_submit=True):
        st.markdown("#### ➕ إضافة مادة كيميائية")
        c1, c2, c3 = st.columns(3)
        with c1:
            code = st.text_input("الكود *", placeholder="", width="stretch")
        with c2:
            name = st.text_input(
                "اسم المادة الكيميائية (اختياري)", placeholder="", width="stretch"
            )
        with c3:
            manufacturer = st.text_input(
                "اسم الشركة المصنعة", placeholder="", width="stretch"
            )
        c4, c5, c6 = st.columns(3)
        with c4:
            count = st.number_input(
                "العدد", min_value=0.0, step=1.0, value=None, placeholder="", width="stretch"
            )
        with c5:
            storage_location = st.text_input(
                "مكان التخزين", value=CHEMICALS_STORAGE_SECTION, width="stretch"
            )
        with c6:
            date_added = st.date_input("تاريخ الإضافة", value=date.today(), width="stretch")
        expiry_date = st.date_input("تاريخ الانتهاء", value=None, width="stretch")
        notes = st.text_area("ملاحظات", placeholder="", height=80, width="stretch")
        submitted = st.form_submit_button(
            "➕ إضافة المادة الكيميائية", type="primary", use_container_width=True
        )

    if not submitted:
        return

    code = str(code or "").strip()
    if not code:
        st.error("الكود مطلوب.")
        return
    name = str(name or "").strip() or code

    ok, msg = add_stock_item(
        name,
        count,
        "",
        code=code,
        date_added=date_added.strftime("%Y-%m-%d") if date_added else "",
        notes=notes,
        manufacturer=manufacturer,
        expiry_date=expiry_date.strftime("%Y-%m-%d") if expiry_date else "",
        category=PRODUCT_CATEGORY_CHEMICALS,
        storage_location=storage_location,
    )
    if ok:
        st.success(msg)
        st.rerun()
    else:
        st.error(msg)


def _render_chemical_edit_form(chemicals) -> None:
    if chemicals.empty:
        st.info("لا توجد مواد كيميائية لتعديلها.")
        return

    labels = {
        f'{_product_note(row.get("product_name")) or "مادة كيميائية"} '
        f'[{row["product_code"]}]': str(row["product_code"])
        for _, row in chemicals.iterrows()
    }
    choice = st.selectbox(
        "اختر المادة الكيميائية المراد تعديلها",
        options=list(labels.keys()),
        index=None,
        placeholder="",
        width="stretch",
        key="chemical_edit_select",
    )
    if choice is None:
        st.caption("اختر مادة لعرض بياناتها وتعديلها.")
        return

    code = labels[choice]
    product = next(
        (r for _, r in chemicals.iterrows() if str(r["product_code"]).strip() == code),
        None,
    )
    if product is None:
        st.warning("لم يتم العثور على المادة المحددة.")
        return

    cur_name = _product_note(product.get("product_name"))
    cur_manufacturer = _product_note(product.get("manufacturer"))
    cur_count = to_number(product.get("current_stock"))
    cur_location = _product_note(product.get("storage_location")) or CHEMICALS_STORAGE_SECTION
    cur_date_added = _date_value(product.get("date_added"))
    cur_expiry = _date_value(product.get("expiry_date"))
    cur_notes = _product_note(product.get("notes"))
    cur_unit = _product_note(product.get("unit"))

    with st.form(f"chemical_edit_form_{code}"):
        st.markdown(f"#### ✏️ تعديل المادة الكيميائية `{code}`")
        c1, c2, c3 = st.columns(3)
        with c1:
            name_v = st.text_input(
                "اسم المادة الكيميائية", value=cur_name, width="stretch"
            )
        with c2:
            manufacturer_v = st.text_input(
                "اسم الشركة المصنعة", value=cur_manufacturer, width="stretch"
            )
        with c3:
            count_v = st.number_input(
                "العدد", min_value=0.0, step=1.0, value=cur_count, width="stretch"
            )
        c4, c5, c6 = st.columns(3)
        with c4:
            location_v = st.text_input(
                "مكان التخزين", value=cur_location, width="stretch"
            )
        with c5:
            date_added_v = st.date_input(
                "تاريخ الإضافة", value=cur_date_added, width="stretch"
            )
        with c6:
            expiry_v = st.date_input(
                "تاريخ الانتهاء", value=cur_expiry, width="stretch"
            )
        notes_v = st.text_area("ملاحظات", value=cur_notes, height=80, width="stretch")
        submitted = st.form_submit_button(
            "💾 حفظ تعديلات المادة", type="primary", use_container_width=True
        )

    if not submitted:
        return

    new_count = to_number(count_v, -1)
    if new_count < 0:
        st.error("العدد يجب أن يكون صفرًا أو أكثر.")
        return

    name_v = str(name_v or "").strip() or code
    ok, msg = update_product(
        code,
        {
            "product_name": name_v,
            "unit": cur_unit,
            "manufacturer": str(manufacturer_v or "").strip(),
            "current_stock": new_count,
            "storage_location": str(location_v or "").strip(),
            "date_added": date_added_v.strftime("%Y-%m-%d") if date_added_v else "",
            "expiry_date": expiry_v.strftime("%Y-%m-%d") if expiry_v else "",
            "notes": str(notes_v or "").strip(),
            "category": PRODUCT_CATEGORY_CHEMICALS,
        },
    )
    if not ok:
        st.error(msg)
        return

    delta = new_count - cur_count
    if abs(delta) > 1e-9:
        record_movement(
            order_no="",
            product_code=code,
            product_name=name_v,
            qty=delta,
            balance_after=new_count,
            person=current_username() or "تعديل مادة كيميائية",
            movement_type="تعديل رصيد",
            notes=f"تعديل عدد مادة كيميائية من {cur_count:g} إلى {new_count:g}",
        )
    st.success(msg)
    st.rerun()


def page_chemicals() -> None:
    header("🧪 قسم الكيماويات", "قسم مستقل لتتبع المواد الكيميائية وبياناتها")
    st.caption(
        f"يعرض هذا القسم المواد الكيميائية فقط. "
        f"تُخزَّن تلقائيًا في «{CHEMICALS_STORAGE_SECTION}» عند ترك مكان التخزين فارغًا."
    )

    products = get_chemical_products()
    chemicals = products.copy()
    if not chemicals.empty:
        for column in ("manufacturer", "storage_location", "date_added", "expiry_date"):
            if column not in chemicals.columns:
                chemicals[column] = ""
        chemicals["_count"] = chemicals["current_stock"].apply(to_number)
        today = date.today()
        expired = 0
        for value in chemicals["expiry_date"]:
            expiry = _date_value(value)
            if expiry and expiry < today:
                expired += 1
        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("عدد المواد الكيميائية", len(chemicals), width="stretch")
        with c2:
            st.metric("إجمالي العدد", f"{chemicals['_count'].sum():g}", width="stretch")
        with c3:
            st.metric("مواد منتهية الصلاحية", expired, width="stretch")

    tab_list, tab_withdraw, tab_history, tab_add, tab_edit, tab_delete = st.tabs(
        [
            "📋 المواد الكيميائية",
            "📤 سحب مادة",
            "📜 سجل السحب",
            "➕ إضافة مادة",
            "✏️ تعديل مادة",
            "🗑️ حذف صنف",
        ]
    )
    with tab_add:
        _render_chemical_add_form()
    with tab_edit:
        _render_chemical_edit_form(chemicals)
    with tab_withdraw:
        _render_chemical_withdraw_form(chemicals)
    with tab_history:
        _render_chemical_withdrawals(chemicals)
    with tab_delete:
        _render_product_delete_form(
            chemicals, "chemicals", "لا توجد مواد كيميائية للحذف."
        )
    with tab_list:
        if chemicals.empty:
            st.info("لا توجد مواد كيميائية بعد — أضف أول مادة من تبويب «إضافة مادة».")
            return

        search = st.text_input(
            "🔍 ابحث بالكود أو الاسم أو الشركة المصنعة أو مكان التخزين",
            placeholder="",
            key="chemical_search",
            width="stretch",
        )
        view = chemicals
        if search.strip():
            term = search.strip()
            mask = (
                view["product_code"].astype(str).str.contains(term, case=False, na=False)
                | view["product_name"].astype(str).str.contains(term, case=False, na=False)
                | view["manufacturer"].astype(str).str.contains(term, case=False, na=False)
                | view["storage_location"].astype(str).str.contains(term, case=False, na=False)
            )
            view = view[mask]

        st.write("")
        st.markdown(f"#### 🧪 المواد الكيميائية ({len(view)})")
        _render_chemicals_table(view, "لا توجد مواد كيميائية مطابقة للبحث.")


# --------------------------------------------------------------------------- #
#                        6) صفحة قسم المكتبية المستقل
# --------------------------------------------------------------------------- #
def _office_split(stock, units_per_carton):
    stock = to_number(stock)
    per = to_number(units_per_carton)
    if per > 0:
        cartons = int(stock // per)
        return cartons, stock - cartons * per
    return 0, stock


def _office_view(df) -> pd.DataFrame:
    view = df.copy()
    for column in (
        "units_per_carton",
        "purchase_date",
        "last_withdraw_date",
        "storage_location",
    ):
        if column not in view.columns:
            view[column] = ""
    view["_count"] = view["current_stock"].apply(to_number)
    view["_per_carton"] = view["units_per_carton"].apply(to_number)
    split = [
        _office_split(stock, per)
        for stock, per in zip(view["_count"], view["_per_carton"])
    ]
    view["_cartons"] = [part[0] for part in split]
    view["_loose"] = [part[1] for part in split]
    view["units_per_carton"] = view["_per_carton"].apply(
        lambda value: f"{value:g}" if value > 0 else "—"
    )
    view["purchase_date"] = view["purchase_date"].apply(
        lambda value: _product_note(value) or "—"
    )
    view["last_withdraw_date"] = view["last_withdraw_date"].apply(
        lambda value: _product_note(value) or "—"
    )
    view["storage_location"] = view["storage_location"].apply(
        lambda value: _product_note(value) or OFFICE_STORAGE_SECTION
    )
    return view[
        [
            "product_code",
            "product_name",
            "_count",
            "_cartons",
            "_loose",
            "units_per_carton",
            "purchase_date",
            "last_withdraw_date",
            "storage_location",
        ]
    ].rename(
        columns={
            "product_code": "الكود",
            "product_name": "اسم الصنف",
            "_count": "العدد الإجمالي",
            "_cartons": "عدد الكراتين",
            "_loose": "وحدات مفردة",
            "units_per_carton": "الوحدات داخل الكرتونة",
            "purchase_date": "تاريخ الشراء",
            "last_withdraw_date": "تاريخ السحب",
            "storage_location": "مكان التخزين",
        }
    )


def _render_office_table(df, empty_message: str) -> None:
    if df.empty:
        st.info(empty_message)
        return
    st.dataframe(_office_view(df), use_container_width=True, hide_index=True)


def _render_office_add_form() -> None:
    with st.form("office_add_form", clear_on_submit=True):
        st.markdown("#### ➕ إضافة صنف مكتبي")
        c1, c2, c3 = st.columns(3)
        with c1:
            code = st.text_input("الكود *", placeholder="", width="stretch")
        with c2:
            name = st.text_input("اسم الصنف *", placeholder="", width="stretch")
        with c3:
            units_per_carton = st.number_input(
                "الوحدات داخل الكرتونة",
                min_value=0.0,
                step=1.0,
                value=None,
                placeholder="",
                width="stretch",
            )
        c4, c5, c6 = st.columns(3)
        with c4:
            cartons = st.number_input(
                "عدد الكراتين",
                min_value=0.0,
                step=1.0,
                value=None,
                placeholder="",
                width="stretch",
            )
        with c5:
            loose_units = st.number_input(
                "وحدات مفردة (اختياري)",
                min_value=0.0,
                step=1.0,
                value=None,
                placeholder="",
                width="stretch",
            )
        with c6:
            purchase_date = st.date_input("تاريخ الشراء", value=None, width="stretch")
        location = st.text_input(
            "مكان التخزين", value=OFFICE_STORAGE_SECTION, width="stretch"
        )
        notes = st.text_area("ملاحظات", placeholder="", height=80, width="stretch")
        submitted = st.form_submit_button(
            "➕ إضافة الصنف المكتبي", type="primary", use_container_width=True
        )

    if not submitted:
        return

    code = str(code or "").strip()
    name = str(name or "").strip()
    if not code:
        st.error("الكود مطلوب.")
        return
    if not name:
        st.error("اسم الصنف مطلوب.")
        return

    per_carton = to_number(units_per_carton, 0)
    cartons_count = to_number(cartons, 0)
    loose = to_number(loose_units, 0)
    if per_carton < 0 or cartons_count < 0 or loose < 0:
        st.error("الكميات يجب أن تكون صفرًا أو أكثر.")
        return
    if cartons_count > 0 and per_carton <= 0:
        st.error("أدخل عدد الوحدات داخل الكرتونة عند إضافة كراتين.")
        return
    qty = cartons_count * per_carton + loose

    ok, msg = add_stock_item(
        name,
        qty,
        "",
        code=code,
        date_added=date.today().strftime("%Y-%m-%d"),
        notes=notes,
        category=PRODUCT_CATEGORY_OFFICE,
        storage_location=location,
        units_per_carton=per_carton,
        purchase_date=purchase_date.strftime("%Y-%m-%d") if purchase_date else "",
    )
    if ok:
        st.success(msg)
        st.rerun()
    else:
        st.error(msg)


def _render_office_edit_form(office) -> None:
    if office.empty:
        st.info("لا توجد أصناف مكتبية لتعديلها.")
        return

    labels = {
        f'{_product_note(row.get("product_name")) or "صنف مكتبي"} '
        f'[{row["product_code"]}]': str(row["product_code"])
        for _, row in office.iterrows()
    }
    choice = st.selectbox(
        "اختر الصنف المكتبي المراد تعديله",
        options=list(labels.keys()),
        index=None,
        placeholder="",
        width="stretch",
        key="office_edit_select",
    )
    if choice is None:
        st.caption("اختر صنفًا لعرض بياناته وتعديلها.")
        return

    code = labels[choice]
    product = next(
        (r for _, r in office.iterrows() if str(r["product_code"]).strip() == code),
        None,
    )
    if product is None:
        st.warning("لم يتم العثور على الصنف المحدد.")
        return

    cur_name = _product_note(product.get("product_name"))
    cur_count = to_number(product.get("current_stock"))
    cur_per_carton = to_number(product.get("units_per_carton"))
    cur_purchase = _date_value(product.get("purchase_date"))
    cur_withdraw = _date_value(product.get("last_withdraw_date"))
    cur_location = _product_note(product.get("storage_location")) or OFFICE_STORAGE_SECTION
    cur_notes = _product_note(product.get("notes"))
    cur_unit = _product_note(product.get("unit"))

    with st.form(f"office_edit_form_{code}"):
        st.markdown(f"#### ✏️ تعديل الصنف المكتبي `{code}`")
        c1, c2, c3 = st.columns(3)
        with c1:
            name_v = st.text_input("اسم الصنف", value=cur_name, width="stretch")
        with c2:
            count_v = st.number_input(
                "العدد الإجمالي", min_value=0.0, step=1.0, value=cur_count, width="stretch"
            )
        with c3:
            per_carton_v = st.number_input(
                "الوحدات داخل الكرتونة",
                min_value=0.0,
                step=1.0,
                value=cur_per_carton,
                width="stretch",
            )
        c4, c5, c6 = st.columns(3)
        with c4:
            purchase_v = st.date_input(
                "تاريخ الشراء", value=cur_purchase, width="stretch"
            )
        with c5:
            withdraw_v = st.date_input(
                "تاريخ السحب", value=cur_withdraw, width="stretch"
            )
        with c6:
            location_v = st.text_input(
                "مكان التخزين", value=cur_location, width="stretch"
            )
        notes_v = st.text_area("ملاحظات", value=cur_notes, height=80, width="stretch")
        submitted = st.form_submit_button(
            "💾 حفظ تعديلات الصنف", type="primary", use_container_width=True
        )

    if not submitted:
        return

    new_count = to_number(count_v, -1)
    new_per_carton = to_number(per_carton_v, -1)
    if new_count < 0 or new_per_carton < 0:
        st.error("العدد والوحدات داخل الكرتونة يجب أن تكون صفرًا أو أكثر.")
        return

    name_v = str(name_v or "").strip() or code
    ok, msg = update_product(
        code,
        {
            "product_name": name_v,
            "unit": cur_unit,
            "current_stock": new_count,
            "units_per_carton": new_per_carton,
            "purchase_date": purchase_v.strftime("%Y-%m-%d") if purchase_v else "",
            "last_withdraw_date": withdraw_v.strftime("%Y-%m-%d") if withdraw_v else "",
            "storage_location": str(location_v or "").strip(),
            "notes": str(notes_v or "").strip(),
            "category": PRODUCT_CATEGORY_OFFICE,
        },
    )
    if not ok:
        st.error(msg)
        return

    delta = new_count - cur_count
    if abs(delta) > 1e-9:
        record_movement(
            order_no="",
            product_code=code,
            product_name=name_v,
            qty=delta,
            balance_after=new_count,
            person=current_username() or "تعديل صنف مكتبي",
            movement_type="تعديل رصيد",
            notes=f"تعديل عدد صنف مكتبي من {cur_count:g} إلى {new_count:g}",
        )
    st.success(msg)
    st.rerun()


def _render_office_withdraw_form(office) -> None:
    if office.empty:
        st.info("لا توجد أصناف مكتبية لسحبها — أضف صنفًا أولًا.")
        return

    labels = {}
    for _, row in office.iterrows():
        name = _product_note(row.get("product_name")) or "صنف مكتبي"
        stock = to_number(row.get("current_stock"))
        per_carton = to_number(row.get("units_per_carton"))
        cartons, loose = _office_split(stock, per_carton)
        cartons_text = f" — {cartons} كرتونة + {loose:g} وحدة" if per_carton > 0 else ""
        labels[f'{name} [{row["product_code"]}] — العدد {stock:g}{cartons_text}'] = str(
            row["product_code"]
        )

    choice = st.selectbox(
        "اختر الصنف المكتبي المراد سحبه",
        options=list(labels.keys()),
        width="stretch",
        key="office_withdraw_select",
    )
    code = labels[choice]
    product = next(
        (r for _, r in office.iterrows() if str(r["product_code"]).strip() == code),
        None,
    )
    if product is None:
        st.warning("لم يتم العثور على الصنف المحدد.")
        return

    stock = to_number(product.get("current_stock"))
    per_carton = to_number(product.get("units_per_carton"))
    cartons, loose = _office_split(stock, per_carton)
    location = _product_note(product.get("storage_location")) or OFFICE_STORAGE_SECTION
    purchase = _product_note(product.get("purchase_date")) or "—"
    st.caption(
        f"العدد الحالي: **{stock:g}** • الكراتين: **{cartons}** • وحدات مفردة: **{loose:g}** • "
        f"داخل الكرتونة: **{per_carton:g}** • مكان التخزين: **{location}** • "
        f"تاريخ الشراء: **{purchase}**"
    )
    if stock <= 0:
        st.warning("لا يوجد رصيد متاح من هذا الصنف حاليًا.")
        return

    with st.form("office_withdraw_form", clear_on_submit=True):
        st.markdown("#### بيانات سحب الصنف المكتبي")
        qty = st.number_input(
            "الكمية المسحوبة (بالعدد) *",
            min_value=0.0,
            step=1.0,
            value=None,
            placeholder="",
            width="stretch",
        )
        c1, c2 = st.columns(2)
        with c1:
            person = st.text_input(
                "اسم الساحب / المستلم *", placeholder="", width="stretch"
            )
        with c2:
            supervisor = st.text_input(
                "اسم المسؤول / أمين المخزن *", placeholder="", width="stretch"
            )

        stamp_now = datetime.now()
        d1, h1, m1, a1 = st.columns(4)
        with d1:
            wdate = st.date_input("تاريخ السحب", value=stamp_now.date(), width="stretch")
        with h1:
            hour12 = st.selectbox(
                "الساعة",
                options=list(range(1, 13)),
                index=(stamp_now.hour % 12 or 12) - 1,
                width="stretch",
            )
        with m1:
            minute = st.selectbox(
                "الدقيقة",
                options=list(range(0, 60)),
                index=stamp_now.minute,
                format_func=lambda m: f"{m:02d}",
                width="stretch",
            )
        with a1:
            ampm = st.selectbox(
                "ص / م",
                options=["ص", "م"],
                index=0 if stamp_now.hour < 12 else 1,
                width="stretch",
            )
        notes = st.text_area(
            "ملاحظات السحب", placeholder="", height=80, width="stretch"
        )
        submitted = st.form_submit_button(
            "📤 تسجيل سحب الصنف", type="primary", use_container_width=True
        )

    if not submitted:
        return

    hour24 = (int(hour12) % 12) + (12 if ampm == "م" else 0)
    stamp = (
        f"{wdate.strftime('%Y-%m-%d')} {hour24:02d}:{int(minute):02d}:00"
        if wdate
        else ""
    )
    ok, msg = withdraw_office_item(
        code, qty, person, stamp, supervisor, notes=notes
    )
    if ok:
        st.success(msg)
        st.rerun()
    else:
        st.error(msg)


def _render_office_withdrawals(office) -> None:
    withdrawals = get_withdrawals()
    if withdrawals.empty:
        st.info("لا توجد عمليات سحب مكتبية مسجلة بعد.")
        return

    office_codes = {
        _product_note(row.get("product_code")) for _, row in office.iterrows()
    }
    office_codes.discard("")
    if not office_codes:
        st.info("لا توجد عمليات سحب مكتبية مسجلة بعد.")
        return

    history = withdrawals[
        withdrawals["product_code"].apply(_product_note).isin(office_codes)
    ].copy()
    if history.empty:
        st.info("لا توجد عمليات سحب مكتبية مسجلة بعد.")
        return

    search = st.text_input(
        "🔍 ابحث بالكود أو الاسم أو اسم الساحب أو المسؤول",
        placeholder="",
        key="office_withdraw_search",
        width="stretch",
    )
    if search.strip():
        term = search.strip()
        mask = (
            history["product_code"].astype(str).str.contains(term, case=False, na=False)
            | history["product_name"].astype(str).str.contains(term, case=False, na=False)
            | history["withdrawn_by"].astype(str).str.contains(term, case=False, na=False)
            | history["supervisor_name"].astype(str).str.contains(term, case=False, na=False)
        )
        history = history[mask]
        if history.empty:
            st.info("لا توجد عمليات سحب مطابقة للبحث.")
            return

    movements = get_movements()
    per_carton_map = {
        _product_note(row.get("product_code")): to_number(row.get("units_per_carton"))
        for _, row in office.iterrows()
    }
    fallback_map = {
        _product_note(row.get("product_code")): to_number(row.get("current_stock"))
        for _, row in office.iterrows()
    }

    rows = []
    for _, row in history.iloc[::-1].iterrows():
        code = _product_note(row.get("product_code"))
        qty = to_number(row.get("qty"))
        per_carton = per_carton_map.get(code, 0)
        cartons, loose = _office_split(qty, per_carton)
        remaining = _remaining_quantity(row, movements, fallback_map.get(code))
        rows.append(
            {
                "التاريخ والوقت": _product_note(row.get("withdraw_date")),
                "الكود": code,
                "اسم الصنف": _product_note(row.get("product_name")),
                "الكمية المسحوبة": qty,
                "الكراتين": cartons if per_carton > 0 else "—",
                "وحدات مفردة": loose if per_carton > 0 else "—",
                "الرصيد المتبقي": "" if remaining is None else f"{remaining:g}",
                "اسم الساحب / المستلم": _product_note(row.get("withdrawn_by")),
                "اسم المسؤول / أمين المخزن": _product_note(row.get("supervisor_name")),
                "ملاحظات": _product_note(row.get("notes")),
                "وقت التسجيل": _product_note(row.get("created_at")),
            }
        )

    total_qty = sum(to_number(row.get("qty")) for _, row in history.iterrows())
    c1, c2 = st.columns(2)
    with c1:
        st.metric("عدد عمليات السحب", len(history), width="stretch")
    with c2:
        st.metric("إجمالي الكمية المسحوبة", f"{total_qty:g}", width="stretch")
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def page_office() -> None:
    header("🗂️ قسم المكتبية", "قسم مستقل لتتبع الأصناف المكتبية وكمياتها وتواريخها")
    st.caption(
        f"يعرض هذا القسم الأصناف المكتبية فقط. "
        f"تُخزَّن تلقائيًا في «{OFFICE_STORAGE_SECTION}» عند ترك مكان التخزين فارغًا."
    )

    office = get_office_products().copy()
    if not office.empty:
        for column in (
            "units_per_carton",
            "purchase_date",
            "last_withdraw_date",
            "storage_location",
        ):
            if column not in office.columns:
                office[column] = ""
        office["_count"] = office["current_stock"].apply(to_number)
        office["_per_carton"] = office["units_per_carton"].apply(to_number)
        cartons_total = sum(
            _office_split(stock, per)[0]
            for stock, per in zip(office["_count"], office["_per_carton"])
        )
        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("عدد الأصناف المكتبية", len(office), width="stretch")
        with c2:
            st.metric("إجمالي العدد", f"{office['_count'].sum():g}", width="stretch")
        with c3:
            st.metric("إجمالي الكراتين", cartons_total, width="stretch")

    tab_list, tab_withdraw, tab_history, tab_add, tab_edit, tab_delete = st.tabs(
        [
            "📋 الأصناف المكتبية",
            "📤 سحب صنف",
            "📜 سجل السحب",
            "➕ إضافة صنف",
            "✏️ تعديل صنف",
            "🗑️ حذف صنف",
        ]
    )
    with tab_add:
        _render_office_add_form()
    with tab_edit:
        _render_office_edit_form(office)
    with tab_withdraw:
        _render_office_withdraw_form(office)
    with tab_history:
        _render_office_withdrawals(office)
    with tab_delete:
        _render_product_delete_form(
            office, "office", "لا توجد أصناف مكتبية للحذف."
        )
    with tab_list:
        if office.empty:
            st.info("لا توجد أصناف مكتبية بعد — أضف أول صنف من تبويب «إضافة صنف».")
            return

        search = st.text_input(
            "🔍 ابحث بالكود أو الاسم أو مكان التخزين",
            placeholder="",
            key="office_search",
            width="stretch",
        )
        view = office
        if search.strip():
            term = search.strip()
            mask = (
                view["product_code"].astype(str).str.contains(term, case=False, na=False)
                | view["product_name"].astype(str).str.contains(term, case=False, na=False)
                | view["storage_location"].astype(str).str.contains(term, case=False, na=False)
            )
            view = view[mask]

        st.write("")
        st.markdown(f"#### 🗂️ الأصناف المكتبية ({len(view)})")
        _render_office_table(view, "لا توجد أصناف مكتبية مطابقة للبحث.")


# --------------------------------------------------------------------------- #
#                    7) صفحة قسم مستلزمات الكمبيوتر المستقل
# --------------------------------------------------------------------------- #
def _computer_view(df) -> pd.DataFrame:
    view = df.copy()
    for column in (
        "storage_location",
        "purchase_date",
        "serial_number",
        "device_condition",
        "device_status",
    ):
        if column not in view.columns:
            view[column] = ""
    view["current_stock"] = view["current_stock"].apply(to_number)
    view["storage_location"] = view["storage_location"].apply(
        lambda value: _product_note(value) or COMPUTER_STORAGE_SECTION
    )
    view["purchase_date"] = view["purchase_date"].apply(
        lambda value: _product_note(value) or "—"
    )
    view["device_condition"] = view["device_condition"].apply(
        lambda value: _product_note(value) or "—"
    )
    view["serial_number"] = view["serial_number"].apply(
        lambda value: _product_note(value) or "—"
    )
    view["device_status"] = view["device_status"].apply(
        lambda value: _product_note(value) or "—"
    )
    return view[
        [
            "product_code",
            "product_name",
            "current_stock",
            "storage_location",
            "purchase_date",
            "device_condition",
            "device_status",
            "serial_number",
        ]
    ].rename(
        columns={
            "product_code": "الكود",
            "product_name": "اسم الصنف",
            "current_stock": "الكمية",
            "storage_location": "مكان التخزين",
            "purchase_date": "تاريخ الشراء",
            "device_condition": "تصنيف الجهاز",
            "device_status": "حالة الجهاز",
            "serial_number": "المواصفات / الأرقام التسلسلية",
        }
    )


def _render_computer_table(df, empty_message: str) -> None:
    if df.empty:
        st.info(empty_message)
        return
    st.dataframe(_computer_view(df), use_container_width=True, hide_index=True)


def _render_computer_add_form() -> None:
    with st.form("computer_add_form", clear_on_submit=True):
        st.markdown("#### ➕ إضافة صنف كمبيوتر")
        c1, c2, c3 = st.columns(3)
        with c1:
            code = st.text_input("الكود *", placeholder="", width="stretch")
        with c2:
            name = st.text_input("اسم الصنف *", placeholder="", width="stretch")
        with c3:
            qty = st.number_input(
                "الكمية",
                min_value=0.0,
                step=1.0,
                value=None,
                placeholder="",
                width="stretch",
            )
        c4, c5, c6 = st.columns(3)
        with c4:
            location = st.text_input(
                "مكان التخزين", value=COMPUTER_STORAGE_SECTION, width="stretch"
            )
        with c5:
            purchase_date = st.date_input("تاريخ الشراء", value=None, width="stretch")
        with c6:
            condition = st.selectbox(
                "تصنيف الجهاز",
                options=DEVICE_CONDITIONS,
                index=0,
                width="stretch",
            )
        specs = st.text_area(
            "مواصفات الأجهزة أو الأرقام التسلسلية",
            placeholder="",
            height=90,
            width="stretch",
        )
        notes = st.text_area("ملاحظات", placeholder="", height=80, width="stretch")
        submitted = st.form_submit_button(
            "➕ إضافة الصنف", type="primary", use_container_width=True
        )

    if not submitted:
        return

    code = str(code or "").strip()
    name = str(name or "").strip()
    if not code:
        st.error("الكود مطلوب.")
        return
    if not name:
        st.error("اسم الصنف مطلوب.")
        return
    if to_number(qty, -1) < 0:
        st.error("الكمية يجب أن تكون صفرًا أو أكثر.")
        return

    ok, msg = add_stock_item(
        name,
        qty,
        "",
        code=code,
        date_added=date.today().strftime("%Y-%m-%d"),
        notes=notes,
        category=PRODUCT_CATEGORY_COMPUTER,
        storage_location=location,
        purchase_date=purchase_date.strftime("%Y-%m-%d") if purchase_date else "",
        serial_number=specs,
        device_condition=condition,
    )
    if ok:
        st.success(msg)
        st.rerun()
    else:
        st.error(msg)


def _render_computer_edit_form(computer) -> None:
    if computer.empty:
        st.info("لا توجد مستلزمات كمبيوتر لتعديلها.")
        return

    labels = {
        f'{_product_note(row.get("product_name")) or "صنف كمبيوتر"} '
        f'[{row["product_code"]}]': str(row["product_code"])
        for _, row in computer.iterrows()
    }
    choice = st.selectbox(
        "اختر الصنف المراد تعديله",
        options=list(labels.keys()),
        index=None,
        placeholder="",
        width="stretch",
        key="computer_edit_select",
    )
    if choice is None:
        st.caption("اختر صنفًا لعرض بياناته وتعديلها.")
        return

    code = labels[choice]
    product = next(
        (r for _, r in computer.iterrows() if str(r["product_code"]).strip() == code),
        None,
    )
    if product is None:
        st.warning("لم يتم العثور على الصنف المحدد.")
        return

    cur_name = _product_note(product.get("product_name"))
    cur_qty = to_number(product.get("current_stock"))
    cur_location = _product_note(product.get("storage_location")) or COMPUTER_STORAGE_SECTION
    cur_purchase = _date_value(product.get("purchase_date"))
    cur_specs = _product_note(product.get("serial_number"))
    cur_notes = _product_note(product.get("notes"))
    cur_condition = _product_note(product.get("device_condition"))
    cur_unit = _product_note(product.get("unit"))
    condition_index = (
        DEVICE_CONDITIONS.index(cur_condition)
        if cur_condition in DEVICE_CONDITIONS
        else 0
    )

    with st.form(f"computer_edit_form_{code}"):
        st.markdown(f"#### ✏️ تعديل الصنف `{code}`")
        c1, c2, c3 = st.columns(3)
        with c1:
            name_v = st.text_input("اسم الصنف", value=cur_name, width="stretch")
        with c2:
            qty_v = st.number_input(
                "الكمية", min_value=0.0, step=1.0, value=cur_qty, width="stretch"
            )
        with c3:
            location_v = st.text_input(
                "مكان التخزين", value=cur_location, width="stretch"
            )
        c4, c5 = st.columns(2)
        with c4:
            purchase_v = st.date_input(
                "تاريخ الشراء", value=cur_purchase, width="stretch"
            )
        with c5:
            condition_v = st.selectbox(
                "تصنيف الجهاز",
                options=DEVICE_CONDITIONS,
                index=condition_index,
                width="stretch",
            )
        specs_v = st.text_area(
            "مواصفات الأجهزة أو الأرقام التسلسلية",
            value=cur_specs,
            height=90,
            width="stretch",
        )
        notes_v = st.text_area("ملاحظات", value=cur_notes, height=80, width="stretch")
        submitted = st.form_submit_button(
            "💾 حفظ تعديلات الصنف", type="primary", use_container_width=True
        )

    if not submitted:
        return

    new_qty = to_number(qty_v, -1)
    if new_qty < 0:
        st.error("الكمية يجب أن تكون صفرًا أو أكثر.")
        return

    name_v = str(name_v or "").strip() or code
    ok, msg = update_product(
        code,
        {
            "product_name": name_v,
            "unit": cur_unit,
            "current_stock": new_qty,
            "storage_location": str(location_v or "").strip(),
            "purchase_date": purchase_v.strftime("%Y-%m-%d") if purchase_v else "",
            "serial_number": str(specs_v or "").strip(),
            "device_condition": condition_v,
            "notes": str(notes_v or "").strip(),
            "category": PRODUCT_CATEGORY_COMPUTER,
        },
    )
    if not ok:
        st.error(msg)
        return

    delta = new_qty - cur_qty
    if abs(delta) > 1e-9:
        record_movement(
            order_no="",
            product_code=code,
            product_name=name_v,
            qty=delta,
            balance_after=new_qty,
            person=current_username() or "تعديل صنف كمبيوتر",
            movement_type="تعديل رصيد",
            notes=f"تعديل كمية صنف كمبيوتر من {cur_qty:g} إلى {new_qty:g}",
        )
    st.success(msg)
    st.rerun()


def _render_computer_withdraw_form(computer) -> None:
    if computer.empty:
        st.info("لا توجد مستلزمات كمبيوتر لسحبها — أضف صنفًا أولًا.")
        return

    labels = {}
    for _, row in computer.iterrows():
        name = _product_note(row.get("product_name")) or "صنف كمبيوتر"
        qty = to_number(row.get("current_stock"))
        condition = _product_note(row.get("device_condition"))
        condition_text = f" — {condition}" if condition else ""
        labels[f'{name} [{row["product_code"]}] — الكمية {qty:g}{condition_text}'] = str(
            row["product_code"]
        )

    choice = st.selectbox(
        "اختر الصنف المراد سحبه",
        options=list(labels.keys()),
        width="stretch",
        key="computer_withdraw_select",
    )
    code = labels[choice]
    product = next(
        (r for _, r in computer.iterrows() if str(r["product_code"]).strip() == code),
        None,
    )
    if product is None:
        st.warning("لم يتم العثور على الصنف المحدد.")
        return

    stock = to_number(product.get("current_stock"))
    location = _product_note(product.get("storage_location")) or COMPUTER_STORAGE_SECTION
    condition = _product_note(product.get("device_condition")) or "—"
    specs = _product_note(product.get("serial_number")) or "—"
    st.caption(
        f"الكمية الحالية: **{stock:g}** • مكان التخزين: **{location}** • "
        f"التصنيف: **{condition}** • المواصفات: **{specs}**"
    )
    if stock <= 0:
        st.warning("لا يوجد رصيد متاح من هذا الصنف حاليًا.")
        return

    with st.form("computer_withdraw_form", clear_on_submit=True):
        st.markdown("#### بيانات سحب صنف الكمبيوتر")
        qty = st.number_input(
            "الكمية المسحوبة *",
            min_value=0.0,
            step=1.0,
            value=None,
            placeholder="",
            width="stretch",
        )
        c1, c2 = st.columns(2)
        with c1:
            person = st.text_input(
                "اسم الساحب / المستلم *", placeholder="", width="stretch"
            )
        with c2:
            supervisor = st.text_input(
                "اسم المسؤول / أمين المخزن *", placeholder="", width="stretch"
            )

        stamp_now = datetime.now()
        d1, h1, m1, a1 = st.columns(4)
        with d1:
            wdate = st.date_input("تاريخ السحب", value=stamp_now.date(), width="stretch")
        with h1:
            hour12 = st.selectbox(
                "الساعة",
                options=list(range(1, 13)),
                index=(stamp_now.hour % 12 or 12) - 1,
                width="stretch",
            )
        with m1:
            minute = st.selectbox(
                "الدقيقة",
                options=list(range(0, 60)),
                index=stamp_now.minute,
                format_func=lambda m: f"{m:02d}",
                width="stretch",
            )
        with a1:
            ampm = st.selectbox(
                "ص / م",
                options=["ص", "م"],
                index=0 if stamp_now.hour < 12 else 1,
                width="stretch",
            )
        notes = st.text_area(
            "ملاحظات السحب", placeholder="", height=80, width="stretch"
        )
        submitted = st.form_submit_button(
            "📤 تسجيل سحب الصنف", type="primary", use_container_width=True
        )

    if not submitted:
        return

    hour24 = (int(hour12) % 12) + (12 if ampm == "م" else 0)
    stamp = (
        f"{wdate.strftime('%Y-%m-%d')} {hour24:02d}:{int(minute):02d}:00"
        if wdate
        else ""
    )
    ok, msg = withdraw_computer_item(
        code, qty, person, stamp, supervisor, notes=notes
    )
    if ok:
        st.success(msg)
        st.rerun()
    else:
        st.error(msg)


def _render_computer_withdrawals(computer) -> None:
    withdrawals = get_withdrawals()
    if withdrawals.empty:
        st.info("لا توجد عمليات سحب لمستلزمات الكمبيوتر بعد.")
        return

    computer_codes = {
        _product_note(row.get("product_code")) for _, row in computer.iterrows()
    }
    computer_codes.discard("")
    if not computer_codes:
        st.info("لا توجد عمليات سحب لمستلزمات الكمبيوتر بعد.")
        return

    history = withdrawals[
        withdrawals["product_code"].apply(_product_note).isin(computer_codes)
    ].copy()
    if history.empty:
        st.info("لا توجد عمليات سحب لمستلزمات الكمبيوتر بعد.")
        return

    search = st.text_input(
        "🔍 ابحث بالكود أو الاسم أو اسم الساحب أو المسؤول",
        placeholder="",
        key="computer_withdraw_search",
        width="stretch",
    )
    if search.strip():
        term = search.strip()
        mask = (
            history["product_code"].astype(str).str.contains(term, case=False, na=False)
            | history["product_name"].astype(str).str.contains(term, case=False, na=False)
            | history["withdrawn_by"].astype(str).str.contains(term, case=False, na=False)
            | history["supervisor_name"].astype(str).str.contains(term, case=False, na=False)
        )
        history = history[mask]
        if history.empty:
            st.info("لا توجد عمليات سحب مطابقة للبحث.")
            return

    movements = get_movements()
    fallback_map = {
        _product_note(row.get("product_code")): to_number(row.get("current_stock"))
        for _, row in computer.iterrows()
    }
    condition_map = {
        _product_note(row.get("product_code")): _product_note(row.get("device_condition"))
        for _, row in computer.iterrows()
    }
    specs_map = {
        _product_note(row.get("product_code")): _product_note(row.get("serial_number"))
        for _, row in computer.iterrows()
    }

    rows = []
    for _, row in history.iloc[::-1].iterrows():
        code = _product_note(row.get("product_code"))
        remaining = _remaining_quantity(row, movements, fallback_map.get(code))
        rows.append(
            {
                "التاريخ والوقت": _product_note(row.get("withdraw_date")),
                "الكود": code,
                "اسم الصنف": _product_note(row.get("product_name")),
                "الكمية المسحوبة": to_number(row.get("qty")),
                "الرصيد المتبقي": "" if remaining is None else f"{remaining:g}",
                "التصنيف": condition_map.get(code) or "—",
                "المواصفات / الأرقام التسلسلية": specs_map.get(code) or "—",
                "اسم الساحب / المستلم": _product_note(row.get("withdrawn_by")),
                "اسم المسؤول / أمين المخزن": _product_note(row.get("supervisor_name")),
                "ملاحظات": _product_note(row.get("notes")),
                "وقت التسجيل": _product_note(row.get("created_at")),
            }
        )

    total_qty = sum(to_number(row.get("qty")) for _, row in history.iterrows())
    c1, c2 = st.columns(2)
    with c1:
        st.metric("عدد عمليات السحب", len(history), width="stretch")
    with c2:
        st.metric("إجمالي الكمية المسحوبة", f"{total_qty:g}", width="stretch")
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def page_computer() -> None:
    header("💻 قسم مستلزمات الكمبيوتر", "إدارة مستلزمات الكمبيوتر ومواصفاتها وتصنيفها")
    st.caption(
        f"يعرض هذا القسم مستلزمات الكمبيوتر فقط. "
        f"تُخزَّن تلقائيًا في «{COMPUTER_STORAGE_SECTION}» عند ترك مكان التخزين فارغًا."
    )

    computer = get_computer_products().copy()
    if not computer.empty:
        for column in (
            "storage_location",
            "purchase_date",
            "serial_number",
            "device_condition",
        ):
            if column not in computer.columns:
                computer[column] = ""
        computer["_qty"] = computer["current_stock"].apply(to_number)
        computer["_condition"] = computer["device_condition"].apply(_product_note)
        new_qty = computer.loc[computer["_condition"] == DEVICE_CONDITIONS[0], "_qty"].sum()
        old_qty = computer.loc[computer["_condition"] == DEVICE_CONDITIONS[1], "_qty"].sum()
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.metric("عدد الأصناف", len(computer), width="stretch")
        with c2:
            st.metric("إجمالي الكمية", f"{computer['_qty'].sum():g}", width="stretch")
        with c3:
            st.metric("كمية جديدة", f"{new_qty:g}", width="stretch")
        with c4:
            st.metric("كمية قديمة", f"{old_qty:g}", width="stretch")

    tab_list, tab_withdraw, tab_history, tab_add, tab_edit, tab_delete = st.tabs(
        [
            "📋 المستلزمات",
            "📤 سحب صنف",
            "📜 سجل السحب",
            "➕ إضافة صنف",
            "✏️ تعديل صنف",
            "🗑️ حذف صنف",
        ]
    )
    with tab_add:
        _render_computer_add_form()
    with tab_edit:
        _render_computer_edit_form(computer)
    with tab_withdraw:
        _render_computer_withdraw_form(computer)
    with tab_history:
        _render_computer_withdrawals(computer)
    with tab_delete:
        _render_product_delete_form(
            computer, "computer", "لا توجد مستلزمات كمبيوتر للحذف."
        )
    with tab_list:
        if computer.empty:
            st.info("لا توجد مستلزمات كمبيوتر بعد — أضف أول صنف من تبويب «إضافة صنف».")
            return

        f1, f2 = st.columns([2, 1])
        with f1:
            search = st.text_input(
                "🔍 ابحث بالكود أو الاسم أو المواصفات أو مكان التخزين",
                placeholder="",
                key="computer_search",
                width="stretch",
            )
        with f2:
            condition_filter = st.selectbox(
                "تصنيف الجهاز",
                options=["كل التصنيفات"] + DEVICE_CONDITIONS,
                width="stretch",
                key="computer_condition_filter",
            )

        view = computer
        if search.strip():
            term = search.strip()
            mask = (
                view["product_code"].astype(str).str.contains(term, case=False, na=False)
                | view["product_name"].astype(str).str.contains(term, case=False, na=False)
                | view["serial_number"].astype(str).str.contains(term, case=False, na=False)
                | view["storage_location"].astype(str).str.contains(term, case=False, na=False)
            )
            view = view[mask]
        if condition_filter != "كل التصنيفات":
            view = view[view["device_condition"].apply(_product_note) == condition_filter]

        st.write("")
        st.markdown(f"#### 💻 مستلزمات الكمبيوتر ({len(view)})")
        _render_computer_table(view, "لا توجد أصناف مطابقة للبحث.")


# --------------------------------------------------------------------------- #
#                    8) صفحة استمارات الهيئة (الوارد والصرف)
# --------------------------------------------------------------------------- #
def _render_authority_forms_receive_form() -> None:
    current = get_authority_forms_count()
    st.caption(f"العدد المتاح حاليًا: **{current:g}** — سيُضاف إليه الوارد الجديد تلقائيًا.")
    with st.form("authority_forms_receive_form", clear_on_submit=True):
        st.markdown("#### 📥 تسجيل كمية واردة من الهيئة")
        c1, c2 = st.columns(2)
        with c1:
            item_name = st.text_input("اسم الصنف *", placeholder="", width="stretch")
        with c2:
            item_code = st.text_input(
                "كود الصنف", placeholder="اختياري", width="stretch"
            )
        c3, c4 = st.columns(2)
        with c3:
            qty = st.number_input(
                "الكمية المستلمة *",
                min_value=0.0,
                step=1.0,
                value=None,
                placeholder="",
                width="stretch",
            )
        with c4:
            receipt_date = st.date_input(
                "تاريخ الاستلام", value=date.today(), width="stretch"
            )
        receiver = st.text_input(
            "اسم المستلم *",
            value=current_username() or "",
            width="stretch",
        )
        notes = st.text_area(
            "ملاحظات الاستلام", placeholder="", height=80, width="stretch"
        )
        submitted = st.form_submit_button(
            "📥 تسجيل الوارد", type="primary", use_container_width=True
        )

    if not submitted:
        return

    ok, msg = receive_authority_forms(
        item_name,
        qty,
        receipt_date.strftime("%Y-%m-%d") if receipt_date else "",
        receiver,
        item_code=item_code,
        notes=notes,
    )
    if ok:
        st.success(msg)
        st.rerun()
    else:
        st.error(msg)


def _render_authority_forms_withdrawal_form() -> None:
    current = get_authority_forms_count()
    st.caption(
        f"العدد المتاح حاليًا: **{current:g}** — ستُخصم الكمية المصروفة تلقائيًا."
    )

    if current <= 0:
        st.info("لا يوجد رصيد متاح للصرف حاليًا. سجّل كمية واردة أولًا.")
        return

    items = get_authority_form_items()
    items = items[items["available_qty"] > 0].copy()
    items["withdrawable"] = items["available_qty"].clip(upper=current)
    items = items[items["withdrawable"] > 0].reset_index(drop=True)
    if items.empty:
        st.info("لا توجد أصناف متاحة للصرف حاليًا. سجّل كمية واردة أولًا.")
        return

    labels = [
        f"{row['item_name']} — {row['item_code']} (متاح: {row['withdrawable']:g})"
        for _, row in items.iterrows()
    ]
    selected_index = st.selectbox(
        "اسم الصنف *",
        options=list(range(len(items))),
        format_func=lambda index: labels[index],
        key="authority_forms_withdraw_item",
    )
    selected = items.iloc[selected_index]
    item_name = str(selected["item_name"])
    item_code = str(selected["item_code"])
    available = to_number(selected["withdrawable"])
    st.text_input("كود الصنف", value=item_code, disabled=True, width="stretch")

    with st.form("authority_forms_withdrawal_form", clear_on_submit=True):
        st.markdown("#### 📤 تسجيل كمية مصروفة من استمارات الهيئة")
        c1, c2 = st.columns(2)
        with c1:
            qty = st.number_input(
                "الكمية المصروفة *",
                min_value=0.0,
                max_value=float(available),
                step=1.0,
                value=None,
                placeholder="",
                width="stretch",
            )
        with c2:
            withdrawal_date = st.date_input(
                "تاريخ السحب", value=date.today(), width="stretch"
            )
        username = st.text_input(
            "اسم المستخدم القائم بالصرف *",
            value=current_username() or "",
            width="stretch",
        )
        notes = st.text_area(
            "ملاحظات الصرف", placeholder="", height=80, width="stretch"
        )
        submitted = st.form_submit_button(
            "📤 تسجيل الصرف", type="primary", use_container_width=True
        )

    if not submitted:
        return

    ok, msg = withdraw_authority_forms(
        item_name,
        item_code,
        qty,
        username,
        withdrawal_date.strftime("%Y-%m-%d") if withdrawal_date else "",
        notes=notes,
    )
    if ok:
        st.success(msg)
        st.rerun()
    else:
        st.error(msg)


def _render_authority_forms_receipts_log() -> None:
    receipts = get_authority_form_receipts()
    if receipts.empty:
        st.info("لا توجد كميات واردة مسجلة بعد.")
        return

    search = st.text_input(
        "🔍 ابحث باسم الصنف أو المستلم أو التاريخ",
        placeholder="",
        key="authority_forms_receipt_search",
        width="stretch",
    )
    history = receipts
    if search.strip():
        term = search.strip()
        mask = (
            history["product_name"].astype(str).str.contains(term, case=False, na=False)
            | history["person"].astype(str).str.contains(term, case=False, na=False)
            | history["movement_date"].astype(str).str.contains(term, case=False, na=False)
        )
        history = history[mask]
        if history.empty:
            st.info("لا توجد كميات واردة مطابقة للبحث.")
            return

    rows = []
    for _, row in history.iloc[::-1].iterrows():
        rows.append(
            {
                "اسم الصنف": _product_note(row.get("product_name")),
                "كود الصنف": _product_note(row.get("product_code")),
                "الكمية المستلمة": to_number(row.get("qty")),
                "تاريخ الاستلام": _product_note(row.get("movement_date")),
                "اسم المستلم": _product_note(row.get("person")),
                "العدد المتاح بعد الاستلام": to_number(row.get("balance_after")),
                "ملاحظات": _product_note(row.get("notes")),
                "وقت التسجيل": _product_note(row.get("created_at")),
            }
        )

    total_qty = sum(to_number(row.get("qty")) for _, row in history.iterrows())
    c1, c2 = st.columns(2)
    with c1:
        st.metric("عدد عمليات الاستلام", len(history), width="stretch")
    with c2:
        st.metric("إجمالي الكمية الواردة", f"{total_qty:g}", width="stretch")
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def _render_authority_forms_delete_form() -> None:
    receipts = get_authority_form_receipts()
    if receipts.empty:
        st.info("لا توجد أصناف استمارات مسجلة للحذف.")
        return
    items = get_authority_form_items()
    if items.empty:
        st.info("لا توجد أصناف استمارات مسجلة للحذف.")
        return

    pair_set = {
        (
            _product_note(row.get("product_name")),
            _product_note(row.get("product_code")) or "AUTHORITY_FORMS",
        )
        for _, row in receipts.iterrows()
    }
    labels = {}
    for _, row in items.iterrows():
        pair = (
            _product_note(row.get("item_name")),
            _product_note(row.get("item_code")) or "AUTHORITY_FORMS",
        )
        if pair not in pair_set:
            continue
        labels[
            f"{pair[0]} — {pair[1]} (متاح: {to_number(row.get('available_qty')):g})"
        ] = pair

    if not labels:
        st.info("لا توجد أصناف استمارات مسجلة للحذف.")
        return

    with st.form("delete_authority_form_item_form"):
        st.markdown("#### 🗑️ حذف صنف استمارات الهيئة")
        st.caption(
            "سيُحذف الصنف مع كل سجلات الوارد والصرف المرتبطة به من SQLite، "
            "ويُخصم المتاح منه من رصيد استمارات الهيئة."
        )
        choice = st.selectbox(
            "اختر الصنف",
            options=list(labels.keys()),
            index=None,
            placeholder="",
            width="stretch",
        )
        confirmed = st.checkbox(
            "أؤكد حذف الصنف وسجلاته نهائيًا", width="stretch"
        )
        submitted = st.form_submit_button(
            "🗑️ حذف الصنف", type="primary", use_container_width=True
        )

    if not submitted:
        return
    if choice is None:
        st.warning("⚠️ يرجى اختيار الصنف المراد حذفه.")
        return
    if not confirmed:
        st.warning("⚠️ يرجى تحديد مربع التأكيد قبل الحذف.")
        return

    name, code = labels[choice]
    ok, msg = delete_authority_form_item(name, code)
    if ok:
        st.success(msg)
        st.rerun()
    else:
        st.error(msg)


def page_authority_forms() -> None:
    header(
        "📄 استمارات الهيئة",
        "تسجيل الكميات الواردة والمصروفة ومتابعة العدد المتاح",
    )
    st.caption(
        "يسجّل هذا القسم الكميات الواردة من الهيئة باسم الصنف وكوده وتاريخ الاستلام "
        "واسم المستلم، والكميات المصروفة بتحديد الصنف وتاريخ السحب واسم المستخدم، "
        "مع تحديث العدد تلقائيًا."
    )

    current = get_authority_forms_count()
    receipts = get_authority_form_receipts()
    withdrawals = get_authority_form_withdrawals()
    total_received = sum(to_number(row.get("qty")) for _, row in receipts.iterrows())
    total_withdrawn = sum(to_number(row.get("qty")) for _, row in withdrawals.iterrows())
    last_withdrawal = (
        _product_note(withdrawals.iloc[-1].get("movement_date"))
        if not withdrawals.empty
        else "—"
    )
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("العدد الحالي", f"{current:g}", width="stretch")
    with c2:
        st.metric("إجمالي الوارد", f"{total_received:g}", width="stretch")
    with c3:
        st.metric("إجمالي المصروف", f"{total_withdrawn:g}", width="stretch")
    with c4:
        st.metric("آخر تاريخ سحب", last_withdrawal or "—", width="stretch")

    tab_receive, tab_withdraw, tab_receipts, tab_delete = st.tabs(
        ["📥 تسجيل وارد", "📤 تسجيل صرف", "📜 سجل الوارد", "🗑️ حذف صنف"]
    )
    with tab_receive:
        _render_authority_forms_receive_form()
    with tab_withdraw:
        _render_authority_forms_withdrawal_form()
    with tab_receipts:
        _render_authority_forms_receipts_log()
    with tab_delete:
        _render_authority_forms_delete_form()

# --------------------------------------------------------------------------- #
#              8-ب) صفحة طلبيات منظمة الصحة العالمية (WHO Orders)
# --------------------------------------------------------------------------- #
WHO_DATA_PATH = os.path.join("data", "who_orders.csv")
WHO_COLUMNS = [
    "order_year",
    "serial_no",
    "item_description",
    "specification",
    "product_code",
    "uom",
    "qty_ordered",
    "qty_in_po",
    "po",
    "qty_confirmed",
    "qty_received",
    "date_rec",
    "remarks",
]

_WHO_NUMERIC_COLUMNS = ("qty_ordered", "qty_in_po", "qty_confirmed", "qty_received")

_WHO_RENAME = {
    "order_year": "السنة",
    "serial_no": "S.#.",
    "item_description": "Item Description",
    "specification": "Specification",
    "product_code": "Product Code/PN/Cat#",
    "uom": "UOM",
    "qty_ordered": "Quantity Ordered",
    "qty_in_po": "Quantity in PO",
    "po": "PO",
    "qty_confirmed": "الكمية المعتمدة",
    "qty_received": "Quantity Received",
    "date_rec": "Date Rec",
    "remarks": "Remarks",
}


def _cell_text(value) -> str:
    text = str(value).strip()
    return "" if text.lower() in ("nan", "none", "nat", "<na>") else text


def _cell_date(value) -> str:
    text = _cell_text(value)
    if not text:
        return ""
    if re.fullmatch(r"\d+(?:\.\d+)?", text):
        serial = float(text)
        if 20000 <= serial <= 80000:
            return (
                pd.Timestamp("1899-12-30") + pd.to_timedelta(serial, unit="D")
            ).strftime("%Y-%m-%d")
    parsed = pd.to_datetime(text, errors="coerce", dayfirst=True)
    return parsed.strftime("%Y-%m-%d") if not pd.isna(parsed) else text


def _who_year_columns(df: pd.DataFrame) -> list:
    return [c for c in df.columns if str(c).startswith("year_")]


def _who_rename_map(df: pd.DataFrame) -> dict:
    mapping = dict(_WHO_RENAME)
    for col in _who_year_columns(df):
        label = str(col)[len("year_"):]
        if label == "current":
            label = "السنة الحالية"
        elif label == "previous":
            label = "السنة السابقة"
        mapping[col] = label
    return mapping


def _who_year_options(df: pd.DataFrame) -> list:
    current = date.today().year
    years = {str(current - 5 + i) for i in range(8)}
    if "order_year" in df.columns:
        for value in df["order_year"]:
            text = str(value).strip()
            if re.fullmatch(r"\d{4}(?:\.0+)?", text):
                years.add(text[:4])
    for col in _who_year_columns(df):
        label = str(col)[len("year_"):]
        if re.fullmatch(r"\d{4}", label):
            years.add(label)
    return sorted(years, reverse=True)


def _load_who_df() -> pd.DataFrame:
    os.makedirs("data", exist_ok=True)
    if os.path.isfile(WHO_DATA_PATH):
        try:
            df = pd.read_csv(WHO_DATA_PATH, dtype=str).fillna("")
            df = df.loc[:, [c for c in df.columns if not str(c).startswith("Unnamed:")]]
            for col in WHO_COLUMNS:
                if col not in df.columns:
                    df[col] = ""
            for col in _WHO_NUMERIC_COLUMNS:
                df[col] = df[col].apply(lambda v: to_number(v, 0.0))
            ordered = WHO_COLUMNS + [c for c in df.columns if c not in WHO_COLUMNS]
            return df[ordered]
        except Exception:
            pass
    return pd.DataFrame(columns=WHO_COLUMNS)


def _save_who_df(df: pd.DataFrame) -> None:
    os.makedirs("data", exist_ok=True)
    for col in WHO_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    extra = [c for c in df.columns if c not in WHO_COLUMNS]
    df[WHO_COLUMNS + extra].fillna("").to_csv(
        WHO_DATA_PATH, index=False, encoding="utf-8-sig"
    )


def _pdf_cell(value) -> str:
    return re.sub(r"\s+", " ", _cell_text(value)).strip()


def _pdf_header_target(value: str):
    if not value:
        return None
    return _normalize_col_map([value]).get(value)


def _pdf_header_score(value: str) -> int:
    c = _clean_col_name(value)
    if not c:
        return 0
    if c in _SERIAL_HEADERS:
        return 1
    if c in _CURRENT_YEAR_HEADERS or c in _PREVIOUS_YEAR_HEADERS:
        return 3
    if _YEAR_RE.fullmatch(c):
        return 3
    if _pdf_header_target(value):
        return 3
    if c in _GENERIC_QTY_HEADERS:
        return 2
    return 0


def _pdf_is_item_header(value: str) -> bool:
    return _pdf_header_target(value) == "item_description"


def _pdf_find_header_end(rows) -> int | None:
    end = None
    for ri, row in enumerate(rows[:6]):
        first = _clean_col_name(row[0]) if row else ""
        numeric_first = bool(re.fullmatch(r"\d+(?:\.\d+)?", first))
        score = sum(1 for cell in row if _pdf_header_score(cell) >= 3)
        if score >= 2 and not numeric_first:
            end = ri
            continue
        if end is not None:
            break
    if end is not None:
        return end
    for ri, row in enumerate(rows[:5]):
        if any(_pdf_is_item_header(cell) for cell in row):
            return ri
    return None


def _pdf_build_header(rows, start: int, end: int) -> list:
    width = max(len(r) for r in rows)
    header = []
    for ci in range(width):
        candidates = [
            row[ci]
            for row in rows[start:end + 1]
            if ci < len(row) and _cell_text(row[ci])
        ]
        if not candidates:
            header.append("")
            continue
        best = candidates[-1]
        best_score = 0
        for cand in candidates:
            score = _pdf_header_score(cand)
            if score >= best_score:
                best = cand
                best_score = score
        header.append(best)
    return header


def _pdf_records_from_tables(tables) -> list:
    records = []
    last_header = None
    for table in tables:
        if not table:
            continue
        rows = [[_pdf_cell(cell) for cell in row] for row in table]
        header_end = _pdf_find_header_end(rows)
        if header_end is None:
            if last_header is None:
                continue
            header = last_header
            start = 0
        else:
            header = _pdf_build_header(rows, 0, header_end)
            start = header_end + 1
            last_header = header

        targets = [_pdf_header_target(cell) for cell in header]
        for row in rows[start:]:
            if not any(row):
                continue
            if any(_pdf_is_item_header(cell) for cell in row):
                continue
            first = _clean_col_name(row[0]) if row else ""
            if first in _SERIAL_HEADERS:
                continue
            record = {}
            for ci, cell in enumerate(row):
                if not cell or ci >= len(header):
                    continue
                target = targets[ci]
                if target:
                    if not _cell_text(record.get(target, "")):
                        record[target] = cell
                else:
                    key = _clean_col_name(header[ci]) or f"extra_{ci + 1}"
                    if not record.get(key):
                        record[key] = cell
            if not any(
                _cell_text(record.get(key))
                for key in ("item_description", "product_code", "specification")
            ):
                continue
            records.append(record)
    return records


def _read_pdf_tables(uploaded_file) -> pd.DataFrame:
    pdfplumber = None
    try:
        import pdfplumber
    except ImportError:
        pass

    pymupdf = None
    try:
        import pymupdf
    except ImportError:
        try:
            import fitz as pymupdf
        except ImportError:
            pass

    if pdfplumber is None and pymupdf is None:
        raise RuntimeError(
            "قراءة ملفات PDF غير متاحة حاليًا. ثبّت الحزمة pdfplumber "
            "أو pymupdf أو ارفع الملف بصيغة Excel."
        )

    try:
        uploaded_file.seek(0)
    except Exception:
        pass
    data = uploaded_file.read()
    if isinstance(data, str):
        data = data.encode("utf-8")

    tables = []
    if pdfplumber is not None:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            for page in pdf.pages:
                tables.extend(page.extract_tables() or [])

    records = _pdf_records_from_tables(tables)

    if not records and pymupdf is not None:
        doc = pymupdf.open(stream=data, filetype="pdf")
        try:
            fallback_tables = []
            for page in doc:
                found = page.find_tables()
                fallback_tables.extend(table.extract() for table in found.tables)
            records = _pdf_records_from_tables(fallback_tables)
        finally:
            doc.close()

    return pd.DataFrame(records).fillna("")


def _read_uploaded_sheet(uploaded_file) -> pd.DataFrame:
    name = str(getattr(uploaded_file, "name", "")).lower().strip()
    if name.endswith(".csv"):
        return pd.read_csv(uploaded_file).fillna("")
    if name.endswith(".pdf"):
        return _read_pdf_tables(uploaded_file)

    head = b""
    try:
        position = uploaded_file.tell()
        head = uploaded_file.read(5)
        uploaded_file.seek(position)
    except Exception:
        head = b""
    if head == b"%PDF-":
        return _read_pdf_tables(uploaded_file)

    return pd.read_excel(uploaded_file).fillna("")


_ARABIC_MARKS_RE = re.compile(r"[\u0610-\u061a\u064b-\u065f\u0670\u06d6-\u06ed\u0640]")
_COL_CLEAN_RE = re.compile(r"[^\w\u0600-\u06ff]+", re.UNICODE)
_PANDAS_DUP_RE = re.compile(r"\.\d+\s*$")

_SERIAL_HEADERS = {
    "s", "s n", "sn", "#", "no", "n", "m", "t", "id", "seq", "sequence",
    "serial", "serial no", "serial number", "s no", "s number",
    "رقم", "الرقم", "م", "ت", "مسلسل", "الرقم المسلسل", "رقم البند",
    "البند",
}

_COL_RULES = (
    (
        "date_rec",
        (
            "date rec", "rec date", "date received", "received date",
            "receipt date", "date of receipt", "تاريخ الاستلام",
            "تاريخ الاستلام",
        ),
    ),
    (
        "qty_confirmed",
        (
            "confirmed", "confirmation", "approved", "approval", "accepted",
            "authorized", "who confirmed", "qty confirmed", "confirmed qty",
            "الكميه المعتمده", "المعتمده", "الكميه المؤكده", "المؤكده",
            "تم التاكيد", "التاكيد", "تم التأكيد", "الموافق عليها",
        ),
    ),
    (
        "qty_received",
        (
            "received", "receipt", "delivered", "delivery", "supplied",
            "supply", "shipped", "shipment", "arrived", "actual received",
            "qty received", "received qty", "quantity rec", "qty rec",
            "rec qty", "quantity recieved", "qty recieved",
            "الكميه المستلمه", "المستلمه", "تم الاستلام", "الاستلام",
            "الوارد", "وارد",
        ),
    ),
    (
        "qty_in_po",
        (
            "quantity in po", "qty in po", "quantity on po", "qty on po",
            "po quantity", "po qty", "quantity in purchase order",
            "qty in purchase order", "quantity required", "required quantity",
            "qty required", "الكميه في امر الشراء", "الكميه في po",
            "كميه امر الشراء",
        ),
    ),
    (
        "qty_ordered",
        (
            "ordered", "order quantity", "order qty", "qty ordered",
            "ordered quantity", "requested", "requested qty", "required",
            "required qty", "needed", "الكميه المطلوبه", "المطلوبه",
            "الطلب", "طلب",
        ),
    ),
    (
        "specification",
        (
            "specification", "specifications", "spacification",
            "spacifications", "spec", "specs", "technical description",
            "technical specification", "المواصفات", "المواصفه",
            "المواصفات الفنيه", "الوصف الفني",
        ),
    ),
    (
        "po",
        (
            "po", "p o", "po number", "po no", "purchase order",
            "purchase order number", "purchase order no", "أمر شراء",
            "امر شراء", "رقم امر الشراء",
        ),
    ),
    (
        "product_code",
        (
            "product code", "item code", "material code", "material number",
            "material no", "part number", "part no", "product number",
            "product no", "item number", "item no", "catalog number",
            "catalog no", "cat number", "cat no", "cat", "pn", "p n", "sku",
            "code", "ref", "reference",
            "كود الصنف", "كود", "الكود", "رمز الصنف", "الرمز", "رقم الصنف",
            "رقم القطعه", "بارت",
        ),
    ),
    (
        "item_description",
        (
            "item description", "description", "item name", "product name",
            "product description", "material description", "goods description",
            "اسم الصنف", "وصف الصنف", "وصف", "الوصف", "البيان", "بيان الصنف",
            "الصنف", "الاصناف",
        ),
    ),
    (
        "uom",
        (
            "uom", "unit of measure", "unit of issue", "unit", "units",
            "measure", "pack", "package", "packing", "presentation",
            "الوحده", "وحده القياس", "وحده", "العبوه",
        ),
    ),
    (
        "remarks",
        (
            "remarks", "remark", "notes", "note", "comments", "comment",
            "observation", "ملاحظات", "ملاحظه", "الملاحظات", "تعليق",
            "تعليقات",
        ),
    ),
)

_GENERIC_QTY_HEADERS = {"qty", "quantity", "الكميه", "كميه"}
_NON_COLUMN_PREFIXES = ("unnamed", "nan", "none", "empty")
_CURRENT_YEAR_HEADERS = {
    "current year", "this year", "year to date", "ytd", "السنه الحاليه",
    "العام الحالي", "بيانات السنه الحاليه",
}
_PREVIOUS_YEAR_HEADERS = {
    "previous year", "last year", "prior year", "السنه السابقه",
    "العام السابق", "بيانات السنه السابقه",
}
_YEAR_RE = re.compile(
    r"(?:(?:year|yr|qty|quantity|data|total|الكميه|كميه|بيانات|سنه)\s+)?"
    r"((?:19|20)\d{2})"
    r"(?:\s+(?:year|yr|qty|quantity|data|total|remaining|balance|"
    r"الكميه|كميه|بيانات|يقابلا|يلامجلاا|المتبقي|الباقي))?"
)


def _clean_col_name(col) -> str:
    text = unicodedata.normalize("NFKC", str(col))
    text = (
        text.replace("\ufeff", "")
        .replace("\u200b", "")
        .replace("\u200c", "")
        .replace("\u200d", "")
        .replace("\xa0", " ")
        .replace("_", " ")
    )
    text = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", text)
    text = _ARABIC_MARKS_RE.sub("", text)
    text = text.translate(
        str.maketrans(
            {
                "أ": "ا", "إ": "ا", "آ": "ا", "ى": "ي", "ة": "ه", "ؤ": "و",
                "ئ": "ي", "٠": "0", "١": "1", "٢": "2", "٣": "3", "٤": "4",
                "٥": "5", "٦": "6", "٧": "7", "٨": "8", "٩": "9", "۰": "0",
                "۱": "1", "۲": "2", "۳": "3", "۴": "4", "۵": "5", "۶": "6",
                "۷": "7", "۸": "8", "۹": "9",
            }
        )
    )
    text = text.lower()
    text = _PANDAS_DUP_RE.sub("", text)
    text = _COL_CLEAN_RE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def _col_contains(text: str, phrases) -> bool:
    return any(re.search(rf"(?<!\w){re.escape(p)}(?!\w)", text) for p in phrases)


def _normalize_col_map(columns) -> dict:
    mapping = {}
    for col in columns:
        c = _clean_col_name(col)
        if not c or c.startswith(_NON_COLUMN_PREFIXES):
            continue
        if c in _SERIAL_HEADERS:
            mapping[col] = "serial_no"
            continue
        if c in _CURRENT_YEAR_HEADERS:
            mapping[col] = "year_current"
            continue
        if c in _PREVIOUS_YEAR_HEADERS:
            mapping[col] = "year_previous"
            continue
        year_match = _YEAR_RE.fullmatch(c)
        if year_match:
            mapping[col] = f"year_{year_match.group(1)}"
            continue
        for target, phrases in _COL_RULES:
            if target == "uom" and any(k in c for k in ("price", "cost", "سعر", "تكلفه")):
                continue
            if _col_contains(c, phrases):
                mapping[col] = target
                break
        else:
            if c in _GENERIC_QTY_HEADERS:
                mapping[col] = "qty_ordered"
    return mapping


def _mapped_values(row, col_map) -> dict:
    mapped = {}
    for col in row.index:
        target = col_map.get(col)
        if not target:
            continue
        if not _cell_text(mapped.get(target, "")):
            mapped[target] = row[col]
    return mapped


def page_who_orders() -> None:
    header(
        "🌐 طلبيات منظمة الصحة العالمية (WHO Orders)",
        "إدارة الطلبيات المرسلة، ردود المنظمة، تفريغ شيتات التوريد، ومطابقة النواقص آليًا",
    )

    df = _load_who_df()

    tab1, tab2, tab3, tab4 = st.tabs(
        [
            "1️⃣ الطلبية المرسلة (Sent Order)",
            "2️⃣ رد وتأكيد المنظمة (WHO Confirmation)",
            "3️⃣ استلام الشحنة برفع Excel",
            "4️⃣ مطابقة المستلم والنواقص",
        ]
    )

    # ---------------- المرحلة 1: الطلبية المرسلة ---------------- #
    with tab1:
        st.markdown("#### 📤 تسجيل أو استيراد طلبية مرسلة إلى WHO")
        selected_order_year = st.selectbox(
            "📅 سنة الطلبية *",
            options=_who_year_options(df),
            index=None,
            placeholder="اختر السنة أولاً...",
            key="who_order_year",
        )
        st.caption("اختيار السنة إجباري؛ تُربط كل بنود الطلبية والاستيراد بالسنة المختارة.")
        missing_year = int((df["order_year"].astype(str).str.strip() == "").sum())
        if missing_year:
            st.warning(
                f"يوجد {missing_year} بندًا قديمًا بدون سنة. اربطها بسنة من الخيار أدناه "
                "حتى تظهر في شاشة الاستلام والمطابقة."
            )
            with st.expander("🔗 ربط البنود القديمة بسنة", expanded=False):
                legacy_year = st.selectbox(
                    "اختر السنة لربط البنود غير المرتبطة",
                    options=_who_year_options(df),
                    index=None,
                    placeholder="اختر السنة...",
                    key="who_legacy_year",
                )
                if st.button(
                    "🔗 ربط البنود القديمة بالسنة",
                    use_container_width=True,
                    disabled=legacy_year is None,
                ):
                    legacy_mask = df["order_year"].astype(str).str.strip() == ""
                    df.loc[legacy_mask, "order_year"] = legacy_year
                    _save_who_df(df)
                    st.success(f"تم ربط {int(legacy_mask.sum())} بندًا بسنة {legacy_year}.")
                    st.rerun()
        with st.expander("📥 استيراد الطلبية المرسلة من ملف Excel / CSV / PDF", expanded=False):
            up_order = st.file_uploader(
                "ارفع ملف الطلبية (Item Description, Specification, Quantity Ordered, Remarks, PO, Quantity in PO, Quantity Received, Date Rec، وأعمدة السنوات)",
                type=["xlsx", "xls", "csv", "pdf"],
                key="who_upload_order",
            )
            if up_order is not None and st.button(
                "📥 تحميل بنود الطلبية من الملف",
                type="primary",
                use_container_width=True,
                disabled=selected_order_year is None,
            ):
                try:
                    raw = _read_uploaded_sheet(up_order)
                    col_map = _normalize_col_map(raw.columns)
                    imported_rows = []
                    for idx, r in raw.iterrows():
                        mapped = _mapped_values(r, col_map)
                        desc = _cell_text(mapped.get("item_description"))
                        code = _cell_text(mapped.get("product_code"))
                        spec = _cell_text(mapped.get("specification"))
                        if not desc and not code and not spec:
                            continue
                        qty_ord = to_number(mapped.get("qty_ordered", 0), 0.0)
                        qty_po = to_number(mapped.get("qty_in_po", 0), 0.0)
                        if qty_ord <= 0 and qty_po > 0:
                            qty_ord = qty_po
                        new_row = {
                            "order_year": selected_order_year,
                            "serial_no": _cell_text(mapped.get("serial_no")) or str(idx + 1),
                            "item_description": desc,
                            "specification": spec,
                            "product_code": code,
                            "uom": _cell_text(mapped.get("uom")),
                            "qty_ordered": qty_ord,
                            "qty_in_po": qty_po,
                            "po": _cell_text(mapped.get("po")),
                            "qty_confirmed": qty_po if qty_po > 0 else qty_ord,
                            "qty_received": to_number(mapped.get("qty_received", 0), 0.0),
                            "date_rec": _cell_date(mapped.get("date_rec")),
                            "remarks": _cell_text(mapped.get("remarks")),
                        }
                        for key, value in mapped.items():
                            if key not in new_row and key != "serial_no":
                                new_row[key] = _cell_text(value)
                        imported_rows.append(new_row)
                    if imported_rows:
                        df = pd.concat([df, pd.DataFrame(imported_rows)], ignore_index=True)
                        _save_who_df(df)
                        st.success(f"تم استيراد {len(imported_rows)} بندًا بنجاح.")
                        st.rerun()
                    else:
                        detected = "، ".join(str(c) for c in raw.columns[:12])
                        if raw.empty:
                            st.warning(
                                "الملف لا يحتوي على صفوف قابلة للقراءة. إذا كان ملف PDF "
                                "مصورًا (Scanned) فلن يمكن استخراج الجدول منه؛ ارفع نسخة "
                                "Excel أو PDF تحتوي على نص قابل للنسخ. ولو الملف نصي، "
                                "تأكد من تثبيت `pdfplumber` و`pymupdf` ثم أعد تشغيل الموقع."
                            )
                        else:
                            st.warning(
                                "لم يتم العثور على أعمدة مطابقة في الملف المرفوع. "
                                f"الأعمدة المكتشفة: {detected or 'لا توجد أعمدة'}"
                            )
                except Exception as exc:
                    st.error(f"تعذر قراءة الملف: {exc}")

        with st.form("who_add_item_form", clear_on_submit=True):
            st.markdown("##### ➕ إضافة بند يدويًا للطلبية")
            c1, c2, c3 = st.columns([3, 2, 1])
            with c1:
                desc_v = st.text_input("وصف الصنف (Item Description) *")
            with c2:
                code_v = st.text_input("كود الصنف (Product Code/PN/Cat#)")
            with c3:
                uom_v = st.text_input("الوحدة (UOM)", placeholder="Pack / Case / Each")
            c4, c5 = st.columns([1, 3])
            with c4:
                qty_v = st.number_input("الكمية المطلوبة (Quantity Ordered) *", min_value=0.0, step=1.0, value=None)
            with c5:
                rem_v = st.text_input("ملاحظات واشتراطات الصلاحية (Remarks)")
            c6, c7, c8, c9 = st.columns([3, 2, 1, 1])
            with c6:
                spec_v = st.text_input("المواصفات (Specification)")
            with c7:
                po_v = st.text_input("أمر الشراء (PO)")
            with c8:
                qty_po_v = st.number_input("الكمية في PO", min_value=0.0, step=1.0, value=None)
            with c9:
                date_rec_v = st.text_input("تاريخ الاستلام (Date Rec)", placeholder="YYYY-MM-DD")
            sub_add = st.form_submit_button(
                "➕ إضافة البند للطلبية",
                type="primary",
                use_container_width=True,
                disabled=selected_order_year is None,
            )

        if sub_add:
            if selected_order_year is None:
                st.error("اختر سنة الطلبية أولاً.")
            elif not str(desc_v).strip():
                st.error("وصف الصنف مطلوب.")
            elif to_number(qty_v, 0.0) <= 0:
                st.error("أدخل كمية مطلوبة أكبر من صفر.")
            else:
                q_num = to_number(qty_v, 0.0)
                qty_po = to_number(qty_po_v, 0.0)
                new_row = {
                    "order_year": selected_order_year,
                    "serial_no": str(len(df) + 1),
                    "item_description": str(desc_v).strip(),
                    "specification": _cell_text(spec_v),
                    "product_code": str(code_v).strip(),
                    "uom": str(uom_v).strip(),
                    "qty_ordered": q_num,
                    "qty_in_po": qty_po,
                    "po": _cell_text(po_v),
                    "qty_confirmed": qty_po if qty_po > 0 else q_num,
                    "qty_received": 0.0,
                    "date_rec": _cell_date(date_rec_v),
                    "remarks": str(rem_v).strip(),
                }
                df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
                _save_who_df(df)
                st.success("تمت إضافة البند إلى الطلبية المرسلة.")
                st.rerun()

        st.markdown("##### 📋 جدول الطلبية المرسلة")
        if df.empty:
            st.info("لا توجد بنود مسجلة في الطلبية بعد.")
        else:
            if "who_order_search_query" not in st.session_state:
                st.session_state["who_order_search_query"] = ""
            st.markdown("##### 🔍 البحث عن طلبية")
            sc1, sc2 = st.columns([4, 1])
            with sc1:
                search_value = st.text_input(
                    "ابحث بالكود أو الوصف أو رقم PO أو المواصفات أو السنة",
                    key="who_order_search_input",
                    placeholder="مثال: 203677541 أو TUBE CULTURE أو 2025",
                )
            with sc2:
                apply_search = st.button("🔍 بحث", use_container_width=True)
            if apply_search:
                st.session_state["who_order_search_query"] = search_value.strip()
            active_query = str(st.session_state.get("who_order_search_query", "")).strip()
            view_df = df
            if active_query:
                query = active_query.lower()
                search_mask = pd.Series(False, index=df.index)
                for col in (
                    "order_year",
                    "serial_no",
                    "item_description",
                    "specification",
                    "product_code",
                    "uom",
                    "po",
                    "remarks",
                ):
                    if col in df.columns:
                        search_mask |= df[col].astype(str).str.lower().str.contains(
                            query, regex=False, na=False
                        )
                view_df = df[search_mask]
                if view_df.empty:
                    st.warning(f"لا توجد نتائج مطابقة لـ «{active_query}».")
                else:
                    st.info(f"عدد النتائج لـ «{active_query}»: {len(view_df)} بند.")
                if st.button("✖️ إلغاء البحث", use_container_width=True):
                    st.session_state["who_order_search_query"] = ""
                    st.rerun()

            display_cols = [c for c in WHO_COLUMNS if c in df.columns] + _who_year_columns(df)
            st.dataframe(
                view_df[display_cols].rename(columns=_who_rename_map(view_df)),
                use_container_width=True,
                hide_index=True,
            )
            if st.button("🗑️ مسح جميع بنود الطلبية الحالية", use_container_width=True):
                _save_who_df(pd.DataFrame(columns=WHO_COLUMNS))
                st.rerun()

    # ---------------- المرحلة 2: رد وتأكيد WHO ---------------- #
    with tab2:
        st.markdown("#### ✅ رد منظمة الصحة العالمية وتحديث الكميات المعتمدة")
        if df.empty:
            st.info("أضف أو ارفع طلبية في المرحلة الأولى أولاً.")
        else:
            st.caption("يمكنك تعديل عمود «الكمية المعتمدة من WHO» وملاحظات المنظمة مباشرة ثم الضغط على حفظ:")
            conf_cols = [c for c in WHO_COLUMNS if c in df.columns] + _who_year_columns(df)
            conf_rename = _who_rename_map(df)
            conf_rename["qty_ordered"] = "الكمية المطلوبة"
            conf_rename["qty_confirmed"] = "الكمية المعتمدة من WHO"
            conf_editor_df = df[conf_cols].rename(columns=conf_rename)
            conf_disabled = [
                c for c in conf_editor_df.columns
                if c not in ("الكمية المعتمدة من WHO", "Remarks")
            ]
            edited_conf = st.data_editor(
                conf_editor_df,
                disabled=conf_disabled,
                use_container_width=True,
                hide_index=True,
                key="who_confirm_editor",
            )
            if st.button("💾 حفظ تأكيد المنظمة", type="primary", use_container_width=True):
                df["qty_confirmed"] = edited_conf["الكمية المعتمدة من WHO"].apply(lambda v: to_number(v, 0.0))
                df["remarks"] = edited_conf["Remarks"].astype(str)
                _save_who_df(df)
                st.success("تم حفظ الكميات المعتمدة من WHO.")
                st.rerun()

    # ---------------- المرحلة 3: استلام الشحنة برفع Excel ---------------- #
    with tab3:
        st.markdown("#### 📦 استلام الشحنة وتفريغ شيت الوارد آليًا (Excel / CSV)")
        if df.empty:
            st.info("لا توجد طلبية مسجلة لمطابقتها. سجّل الطلبية في المرحلة الأولى أولاً.")
        else:
            st.caption(
                "ارفع شيت التوريد الوارد مع الشحنة (`.xlsx` أو `.csv` أو `.pdf`) ليقوم النظام تلقائيًا "
                "بمطابقة الكود أو اسم الصنف وتحديث الكميات المستلمة وتاريخ الاستلام والمواصفات "
                "وأمر الشراء وبيانات السنوات الحالية والسابقة."
            )
            selected_ship_year = st.selectbox(
                "📅 سنة الشحنة *",
                options=_who_year_options(df),
                index=None,
                placeholder="اختر السنة أولاً...",
                key="who_ship_year",
            )
            st.caption("اختيار السنة إجباري؛ تُطابق الشحنة مع بنود هذه السنة فقط.")
            up_ship = st.file_uploader(
                "📂 اختر ملف شيت الاستلام (Excel / CSV / PDF)",
                type=["xlsx", "xls", "csv", "pdf"],
                key="who_upload_shipment",
            )
            mode = st.radio(
                "طريقة تحديث الكميات المستلمة:",
                ["إضافة على المستلم السابق (توريد على دفعات)", "استبدال الكمية المستلمة بالقيمة الجديدة"],
                horizontal=True,
            )
            if up_ship is not None and st.button(
                "⚡ تحليل الشيت ومطابقة الشحنة تلقائيًا",
                type="primary",
                use_container_width=True,
                disabled=selected_ship_year is None,
            ):
                try:
                    ship_df = _read_uploaded_sheet(up_ship)
                    col_map = _normalize_col_map(ship_df.columns)
                    matched_count = 0
                    year_mask = (
                        df["order_year"].astype(str).str.strip() == selected_ship_year
                    )
                    for _, srow in ship_df.iterrows():
                        mapped = _mapped_values(srow, col_map)
                        scode = _cell_text(mapped.get("product_code")).lower()
                        sdesc = _cell_text(mapped.get("item_description")).lower()
                        if "qty_received" in mapped:
                            sqty = to_number(mapped.get("qty_received"), 0.0)
                        else:
                            sqty = to_number(
                                mapped.get("qty_in_po", mapped.get("qty_ordered", 0)), 0.0
                            )
                        if sqty <= 0 and not scode and not sdesc:
                            continue

                        mask = pd.Series(False, index=df.index)
                        if scode:
                            mask = year_mask & (
                                df["product_code"].astype(str).str.strip().str.lower() == scode
                            )
                        if not mask.any() and sdesc:
                            mask = year_mask & (
                                df["item_description"].astype(str).str.strip().str.lower() == sdesc
                            )

                        if mask.any():
                            matched_count += int(mask.sum())
                            if mode.startswith("إضافة"):
                                df.loc[mask, "qty_received"] = df.loc[mask, "qty_received"].apply(to_number) + sqty
                            else:
                                df.loc[mask, "qty_received"] = sqty
                            if "date_rec" in mapped and _cell_date(mapped.get("date_rec")):
                                df.loc[mask, "date_rec"] = _cell_date(mapped.get("date_rec"))
                            for extra_col in ("specification", "po"):
                                value = _cell_text(mapped.get(extra_col))
                                if value:
                                    df.loc[mask, extra_col] = value
                            if "qty_in_po" in mapped:
                                qty_po = to_number(mapped.get("qty_in_po"), 0.0)
                                df.loc[mask, "qty_in_po"] = qty_po
                                if qty_po > 0:
                                    df.loc[mask, "qty_confirmed"] = qty_po
                            for key, value in mapped.items():
                                if not key.startswith("year_"):
                                    continue
                                year_value = _cell_text(value)
                                if not year_value:
                                    continue
                                if key not in df.columns:
                                    df[key] = ""
                                df.loc[mask, key] = year_value
                    if matched_count:
                        _save_who_df(df)
                        st.success(f"تمت مطابقة وتحديث {matched_count} بندًا من ملف الشحنة بنجاح!")
                        st.rerun()
                    else:
                        st.warning(
                            f"لم يتم العثور على بنود مطابقة ضمن سنة {selected_ship_year}. "
                            "تأكد من اختيار السنة الصحيحة أو من تسجيل الطلبية بهذه السنة."
                        )
                except Exception as exc:
                    st.error(f"حدث خطأ أثناء معالجة ملف الإكسل: {exc}")

            st.markdown("##### ✏️ أو تعديل الكميات المستلمة يدويًا")
            if selected_ship_year is None:
                st.info("اختر السنة أولاً لعرض بنودها وتعديل الكميات المستلمة.")
            else:
                rec_source = df[
                    df["order_year"].astype(str).str.strip() == selected_ship_year
                ]
                if rec_source.empty:
                    st.info(f"لا توجد بنود مسجلة لسنة {selected_ship_year}.")
                else:
                    rec_cols = [c for c in WHO_COLUMNS if c in df.columns] + _who_year_columns(df)
                    rec_rename = _who_rename_map(df)
                    rec_rename["qty_received"] = "الكمية المستلمة فعليًا"
                    rec_rename["date_rec"] = "تاريخ الاستلام (Date Rec)"
                    rec_editor_df = rec_source[rec_cols].rename(columns=rec_rename)
                    rec_disabled = [
                        c for c in rec_editor_df.columns
                        if c not in ("الكمية المستلمة فعليًا", "تاريخ الاستلام (Date Rec)")
                    ]
                    edited_rec = st.data_editor(
                        rec_editor_df,
                        disabled=rec_disabled,
                        use_container_width=True,
                        hide_index=True,
                        key=f"who_receive_editor_{selected_ship_year}",
                    )
                    if st.button("💾 حفظ الكميات المستلمة", use_container_width=True):
                        df.loc[rec_source.index, "qty_received"] = edited_rec[
                            "الكمية المستلمة فعليًا"
                        ].apply(lambda v: to_number(v, 0.0))
                        df.loc[rec_source.index, "date_rec"] = edited_rec[
                            "تاريخ الاستلام (Date Rec)"
                        ].apply(_cell_date)
                        _save_who_df(df)
                        st.success(f"تم تحديث الكميات المستلمة لسنة {selected_ship_year}.")
                        st.rerun()

    # ---------------- المرحلة 4: مطابقة المستلم والنواقص ---------------- #
    with tab4:
        st.markdown("#### 📊 لوحة مطابقة الشحنة وتتبع النواقص (Reconciliation Dashboard)")
        if df.empty:
            st.info("لا توجد بيانات لعرض المطابقة.")
        else:
            rec_df = df.copy()
            rec_df["target_qty"] = rec_df.apply(
                lambda r: to_number(r["qty_confirmed"]) if to_number(r["qty_confirmed"]) > 0 else to_number(r["qty_ordered"]),
                axis=1,
            )
            rec_df["shortage"] = (rec_df["target_qty"] - rec_df["qty_received"]).clip(lower=0.0)

            def _status_label(row) -> str:
                rec = to_number(row["qty_received"])
                tgt = to_number(row["target_qty"])
                if tgt <= 0:
                    return "—"
                if rec >= tgt:
                    return "✅ مكتمل (Fully Received)"
                if rec > 0:
                    return "🟠 استلام جزئي / عجز (Partial)"
                return "🔴 لم يصل (Pending / Missing)"

            rec_df["status"] = rec_df.apply(_status_label, axis=1)

            total_items = len(rec_df)
            full_count = int((rec_df["status"].str.startswith("✅")).sum())
            partial_count = int((rec_df["status"].str.startswith("🟠")).sum())
            missing_count = int((rec_df["status"].str.startswith("🔴")).sum())

            m1, m2, m3, m4 = st.columns(4)
            with m1:
                st.metric("إجمالي البنود", total_items, width="stretch")
            with m2:
                st.metric("✅ مكتمل بالكامل", full_count, width="stretch")
            with m3:
                st.metric("🟠 عجز جزئي", partial_count, width="stretch")
            with m4:
                st.metric("🔴 لم يصل", missing_count, width="stretch")

            filter_status = st.radio(
                "تصفية العرض:",
                ["الكل", "النواقص فقط (عجز جزئي + لم يصل)", "المكتمل فقط"],
                horizontal=True,
            )
            view_df = rec_df
            if filter_status == "النواقص فقط (عجز جزئي + لم يصل)":
                view_df = rec_df[rec_df["shortage"] > 0]
            elif filter_status == "المكتمل فقط":
                view_df = rec_df[rec_df["shortage"] <= 0]

            rec_display_cols = [
                c for c in WHO_COLUMNS if c in view_df.columns
            ] + ["shortage", "status"] + _who_year_columns(view_df)
            rec_display_rename = _who_rename_map(view_df)
            rec_display_rename.update(
                {
                    "qty_ordered": "المطلوب",
                    "qty_in_po": "الكمية في PO",
                    "qty_confirmed": "المعتمد",
                    "qty_received": "المستلم",
                    "shortage": "العجز / المتبقي",
                    "status": "حالة التوريد",
                }
            )
            display_df = view_df[rec_display_cols].rename(columns=rec_display_rename)

            st.dataframe(display_df, use_container_width=True, hide_index=True)

            shortage_only = display_df[display_df["العجز / المتبقي"] > 0]
            c_dl1, c_dl2 = st.columns(2)
            with c_dl1:
                st.download_button(
                    "⬇️ تصدير تقرير النواقص فقط (CSV)",
                    data=shortage_only.to_csv(index=False).encode("utf-8-sig"),
                    file_name="who_shortage_report.csv",
                    mime="text/csv",
                    use_container_width=True,
                )
            with c_dl2:
                st.download_button(
                    "⬇️ تصدير جدول المطابقة الكامل (CSV)",
                    data=display_df.to_csv(index=False).encode("utf-8-sig"),
                    file_name="who_full_reconciliation.csv",
                    mime="text/csv",
                    use_container_width=True,
                )
# --------------------------------------------------------------------------- #
#                    9) صفحة تكهين الأجهزة
# --------------------------------------------------------------------------- #
def page_decommission() -> None:
    header(
        "🗑️ تكهين الأجهزة",
        "تسجيل تكهين أجهزة PCR ومستلزمات الكمبيوتر وتحديث حالتها",
    )
    st.caption(
        "اختر مصدر الجهاز ثم الجهاز المطلوب، وأدخل تاريخ التكهين وسببه واسم القائم "
        f"بالتكهين. تُحدَّث حالة الجهاز تلقائيًا إلى «{DEVICE_STATUS_DECOMMISSIONED}»."
    )

    device_frames = {
        PRODUCT_CATEGORY_PCR: get_pcr_products().copy(),
        PRODUCT_CATEGORY_COMPUTER: get_computer_products().copy(),
    }
    for frame in device_frames.values():
        for column in (
            "serial_number",
            "device_status",
            "decommission_date",
            "decommission_reason",
            "decommissioned_by",
        ):
            if column not in frame.columns:
                frame[column] = ""

    done_map = {
        category: (
            frame[
                frame["device_status"].apply(_product_note)
                == DEVICE_STATUS_DECOMMISSIONED
            ]
            if not frame.empty
            else frame
        )
        for category, frame in device_frames.items()
    }
    done_total = sum(len(frame) for frame in done_map.values())
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("إجمالي الأجهزة المكهنة", done_total, width="stretch")
    with c2:
        st.metric("أجهزة PCR المكهنة", len(done_map[PRODUCT_CATEGORY_PCR]), width="stretch")
    with c3:
        st.metric(
            "مستلزمات الكمبيوتر المكهنة",
            len(done_map[PRODUCT_CATEGORY_COMPUTER]),
            width="stretch",
        )
    st.write("")
    st.markdown("#### ➕ تسجيل تكهين جهاز")
    source_options = {
        "🧬 أجهزة PCR": PRODUCT_CATEGORY_PCR,
        "💻 مستلزمات الكمبيوتر": PRODUCT_CATEGORY_COMPUTER,
    }
    source_label = st.selectbox(
        "مصدر الجهاز *",
        options=list(source_options.keys()),
        key="decommission_source",
        width="stretch",
    )
    source_category = source_options[source_label]
    devices = device_frames[source_category]

    if devices.empty:
        st.info("لا توجد أجهزة مسجلة في المصدر المحدد.")
        choice = None
    else:
        active = devices[
            devices["device_status"].apply(_product_note) != DEVICE_STATUS_DECOMMISSIONED
        ].copy()
        if active.empty:
            st.info("جميع أجهزة هذا المصدر مكهنة بالفعل.")
            choice = None
        else:
            labels = {}
            for _, row in active.iterrows():
                serial = _product_note(row.get("serial_number")) or "بدون رقم تسلسلي"
                labels[
                    f"{_product_note(row.get('product_name')) or 'جهاز'} — "
                    f"{_product_note(row.get('product_code'))} — {serial}"
                ] = str(row.get("product_code"))
            choice = st.selectbox(
                "اختيار الجهاز *",
                options=list(labels.keys()),
                index=None,
                placeholder="",
                key="decommission_device_select",
                width="stretch",
            )

    if devices.empty or choice is None:
        st.caption("اختر جهازًا لعرض بياناته وتسجيل تكهينه.")
    else:
        code = labels[choice]
        selected = active[
            active["product_code"].astype(str).str.strip() == code
        ].iloc[0]
        st.caption(
            f"**{_product_note(selected.get('product_name'))}** — "
            f"الكود: `{code}` — الرقم التسلسلي: "
            f"{_product_note(selected.get('serial_number')) or '—'} — "
            f"الحالة الحالية: {_product_note(selected.get('device_status')) or '—'}"
        )
        with st.form("decommission_device_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1:
                decommission_date = st.date_input(
                    "تاريخ التكهين", value=date.today(), width="stretch"
                )
            with c2:
                person = st.text_input(
                    "اسم القائم بالتكهين *",
                    value=current_username() or "",
                    width="stretch",
                )
            reason = st.text_area(
                "سبب التكهين *", placeholder="", height=90, width="stretch"
            )
            submitted = st.form_submit_button(
                "🗑️ تأكيد التكهين", type="primary", use_container_width=True
            )

        if submitted:
            ok, msg = decommission_device(
                source_category,
                code,
                decommission_date.strftime("%Y-%m-%d") if decommission_date else "",
                reason,
                person,
            )
            if ok:
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)

    st.write("")
    st.markdown("#### 📜 سجل الأجهزة المكهنة")
    rows = []
    for source_name, frame in (
        ("أجهزة PCR", done_map[PRODUCT_CATEGORY_PCR]),
        ("مستلزمات الكمبيوتر", done_map[PRODUCT_CATEGORY_COMPUTER]),
    ):
        if frame.empty:
            continue
        for _, row in frame.iterrows():
            rows.append(
                {
                    "المصدر": source_name,
                    "كود الجهاز": _product_note(row.get("product_code")),
                    "اسم الجهاز": _product_note(row.get("product_name")),
                    "الرقم التسلسلي": _product_note(row.get("serial_number")) or "—",
                    "الكمية": to_number(row.get("current_stock")),
                    "تاريخ التكهين": _product_note(row.get("decommission_date")) or "—",
                    "سبب التكهين": _product_note(row.get("decommission_reason")) or "—",
                    "القائم بالتكهين": _product_note(row.get("decommissioned_by")) or "—",
                }
            )

    if not rows:
        st.info("لا توجد أجهزة مكهنة مسجلة بعد.")
    else:
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    st.write("")
    done_frames = [
        done_map[PRODUCT_CATEGORY_PCR],
        done_map[PRODUCT_CATEGORY_COMPUTER],
    ]
    done = (
        pd.concat(done_frames, ignore_index=True)
        if done_frames
        else pd.DataFrame()
    )
    _render_product_delete_form(
        done,
        "decommissioned",
        "لا توجد أجهزة مكهنة قابلة للحذف.",
        "🗑️ حذف جهاز مكهّن نهائيًا",
    )


# --------------------------------------------------------------------------- #
#                        10) صفحة التقارير والسجلات
# --------------------------------------------------------------------------- #
def page_reports() -> None:
    header("📊 التقارير والسجلات", "حالة المخزون وسجل السحوبات الكامل")

    products = get_products()
    withdrawals = get_withdrawals()

    total_items = len(products)
    total_withdrawals = len(withdrawals)
    total_stock = sum(to_number(v) for v in products["current_stock"]) if not products.empty else 0.0

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(metric_card("إجمالي الأصناف", total_items), unsafe_allow_html=True)
    with c2:
        st.markdown(metric_card("إجمالي عمليات السحب", total_withdrawals, "purple"), unsafe_allow_html=True)
    with c3:
        st.markdown(metric_card("إجمالي رصيد المخزن", f"{total_stock:,.2f}", "good"), unsafe_allow_html=True)

    st.write("")
    st.markdown("#### 📦 حالة المخزون الحالية")
    if products.empty:
        st.info("لا توجد أصناف.")
    else:
        stock_view = products.copy()
        if "added_by" not in stock_view.columns:
            stock_view["added_by"] = ""
        stock_view["current_stock"] = stock_view["current_stock"].apply(to_number)
        stock_view["min_stock"] = stock_view["min_stock"].apply(to_number)
        stock_view["starting_stock"] = stock_view["starting_stock"].apply(to_number)
        stock_view["total_withdrawn"] = stock_view["total_withdrawn"].apply(to_number)
        if "category" not in stock_view.columns:
            stock_view["category"] = PRODUCT_CATEGORY_GENERAL
        stock_view["category"] = stock_view["category"].apply(normalize_category)
        stock_view["الحالة"] = stock_view.apply(
            lambda r: "⚠️ منخفض" if r["current_stock"] <= r["min_stock"] else "✅ جيد", axis=1
        )
        code_filter = st.text_input(
            "🔍 بحث بكود الصنف", key="stock_code_filter", placeholder="", width="stretch"
        )
        if code_filter.strip():
            stock_view = stock_view[
                stock_view["product_code"].astype(str).str.contains(
                    code_filter.strip(), case=False, na=False
                )
            ]
        # قيم التصفية الجديدة تُقرأ من الحالة قبل بناء الجدول، لأن حقولها تُنشأ أسفله
        cat_filter = str(st.session_state.get("stock_category_filter", "الكل")).strip()
        mfr_filter = str(st.session_state.get("stock_mfr_filter", "")).strip()
        sup_filter = str(st.session_state.get("stock_sup_filter", "")).strip()
        exp_filter = str(st.session_state.get("stock_exp_filter", "")).strip()
        if cat_filter and cat_filter != "الكل":
            stock_view = stock_view[
                stock_view["category"].astype(str).str.upper() == cat_filter.upper()
            ]
        if mfr_filter:
            stock_view = stock_view[
                stock_view["manufacturer"].astype(str).str.contains(mfr_filter, case=False, na=False)
            ]
        if sup_filter:
            stock_view = stock_view[
                stock_view["supplier"].astype(str).str.contains(sup_filter, case=False, na=False)
            ]
        if exp_filter:
            stock_view = stock_view[
                stock_view["expiry_date"].astype(str).str.contains(exp_filter, case=False, na=False)
            ]
        st.dataframe(
            stock_view[
                [
                    "product_code",
                    "product_name",
                    "category",
                    "unit",
                    "starting_stock",
                    "total_withdrawn",
                    "current_stock",
                    "date_added",
                    "added_by",
                    "manufacturer",
                    "supplier",
                    "expiry_date",
                    "notes",
                    "الحالة",
                ]
            ].rename(
                columns={
                    "product_code": "الكود",
                    "product_name": "اسم الصنف",
                    "category": "التصنيف",
                    "unit": "الوحدة",
                    "starting_stock": "الكمية الابتدائية",
                    "total_withdrawn": "إجمالي المسحوب",
                    "current_stock": "الرصيد الحالي",
                    "date_added": "تاريخ الإضافة",
                    "added_by": "أضافه",
                    "manufacturer": "شركة الصنع",
                    "supplier": "شركة التوريد",
                    "expiry_date": "تاريخ الانتهاء",
                    "notes": "ملاحظات الصنف",
                }
            ),
            use_container_width=True,
            hide_index=True,
        )
        st.write("")
        st.caption("🔍 تصفية الجدول حسب التصنيف وبيانات الشركة والتاريخ (بحث جزئي مسموح):")
        f0, f1, f2, f3 = st.columns(4)
        with f0:
            st.selectbox(
                "🗂️ التصنيف",
                options=["الكل"] + PRODUCT_CATEGORIES,
                key="stock_category_filter",
                width="stretch",
            )
        with f1:
            st.text_input(
                "🔍 بحث بشركة الصنع", key="stock_mfr_filter", placeholder="", width="stretch"
            )
        with f2:
            st.text_input(
                "🔍 بحث بشركة التوريد", key="stock_sup_filter", placeholder="", width="stretch"
            )
        with f3:
            st.text_input(
                "🔍 بحث بتاريخ الانتهاء", key="stock_exp_filter", placeholder="", width="stretch"
            )

    st.write("")
    st.markdown("#### 📜 سجل السحوبات الكامل")
    if withdrawals.empty:
        st.info("لا توجد عمليات سحب بعد.")
        return

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        supervisor_search = st.text_input("🔍 بحث باسم المسؤول", placeholder="", width="stretch")
    with c2:
        person = st.text_input("🔍 بحث باسم الساحب", placeholder="", width="stretch")
    with c3:
        item = st.text_input("🔍 بحث باسم الصنف", placeholder="", width="stretch")
    with c4:
        code_search = st.text_input("🔍 بحث بكود الصنف", placeholder="", width="stretch")
    with c5:
        start = st.date_input("من تاريخ", value=None, width="stretch")

    df = withdrawals.copy()
    if supervisor_search.strip():
        df = df[
            df["supervisor_name"].astype(str).str.contains(supervisor_search.strip(), case=False, na=False)
        ]
    if person.strip():
        df = df[df["withdrawn_by"].astype(str).str.contains(person.strip(), case=False, na=False)]
    if item.strip():
        df = df[df["product_name"].astype(str).str.contains(item.strip(), case=False, na=False)]
    if code_search.strip():
        df = df[
            df["product_code"].astype(str).str.contains(code_search.strip(), case=False, na=False)
        ]
    if start:
        df = df[df["withdraw_date"].astype(str).str[:10] >= start.strftime("%Y-%m-%d")]

    notes_map = _notes_by_code(products)
    log_view = df.iloc[::-1].copy()
    log_view["product_notes"] = [
        _product_note(notes_map.get(str(c).strip())) for c in log_view["product_code"]
    ]
    view = log_view[
        [
            "withdraw_date",
            "product_code",
            "product_name",
            "qty",
            "product_notes",
            "supervisor_name",
            "withdrawn_by",
        ]
    ].rename(
        columns={
            "withdraw_date": "التاريخ والوقت",
            "product_code": "الكود",
            "product_name": "الصنف",
            "qty": "الكمية",
            "product_notes": "ملاحظات الصنف",
            "supervisor_name": "اسم المسؤول",
            "withdrawn_by": "اسم الساحب",
        }
    )
    total_qty = sum(to_number(v) for v in df["qty"])
    st.caption(f"عدد العمليات: {len(df)} — إجمالي الكميات المسحوبة: {total_qty:g}")
    st.dataframe(view, use_container_width=True, hide_index=True)

    st.download_button(
        "⬇️ تصدير السجل CSV",
        data=view.to_csv(index=False).encode("utf-8-sig"),
        file_name="withdrawals_log.csv",
        mime="text/csv",
        use_container_width=True,
    )


# --------------------------------------------------------------------------- #
#                       5) صفحة إدارة المستخدمين (للأدمن)
# --------------------------------------------------------------------------- #
def _users_dataframe():
    users = get_users()
    if users.empty:
        return users
    view = users.copy()
    view["الصلاحية"] = view["role"].apply(lambda r: "👑 مدير" if str(r).strip().lower() == ROLE_ADMIN else "👤 مستخدم")
    if "lab_access" in view.columns:
        view["صلاحية المعمل"] = view["lab_access"].apply(
            lambda lab: {
                LAB_ALL: "🌐 جميع المعامل",
                LAB_PCR: "🧬 PCR فقط",
                LAB_SEQUENCING: "🧬 Sequencing فقط",
                LAB_CELL_CULTURE: "🫫 Cell Culture فقط"
            }.get(str(lab).strip(), str(lab))
        )
    else:
        view["صلاحية المعمل"] = LAB_ALL
    cols = ["username"]
    if "created_at" in view.columns:
        cols.append("created_at")
    cols.extend(["الصلاحية", "صلاحية المعمل"])
    return view[cols].rename(
        columns={"username": "اسم المستخدم", "created_at": "تاريخ الإنشاء"}
    )


def page_users() -> None:
    header("👥 إدارة المستخدمين", "إضافة وحذف المستخدمين وعرضهم وتغيير كلمات المرور")
    if not is_admin():
        st.error("هذه الصفحة متاحة لحساب المدير فقط.")
        return

    users = get_users()
    usernames = [str(u).strip() for u in users["username"]] if not users.empty else []

    tab_add, tab_del, tab_list, tab_reset = st.tabs(
        ["➕ إضافة مستخدم جديد", "🗑️ حذف مستخدم", "📋 عرض المستخدمين", "🔑 تغيير كلمة المرور"]
    )

    with tab_add:
        with st.form("add_user_form", clear_on_submit=True):
            st.markdown("#### إضافة مستخدم جديد")
            c1, c2, c3 = st.columns(3)
            with c1:
                new_username = st.text_input("اسم المستخدم *", placeholder="", width="stretch")
            with c2:
                new_password = st.text_input("كلمة المرور *", type="password", placeholder="", width="stretch")
            with c3:
                new_role = st.selectbox(
                    "الصلاحية",
                    options=ROLES,
                    format_func=lambda r: "👑 مدير" if r == ROLE_ADMIN else "👤 مستخدم",
                    width="stretch",
                    placeholder="",
                )
            
            st.markdown("##### 🔬 صلاحية الوصول للمعامل")
            new_lab_access = st.selectbox(
                "المعمل المسموح بالوصول إليه",
                options=LABS,
                index=0,
                format_func=lambda lab: {
                    LAB_ALL: "🌐 جميع المعامل (PCR, Sequencing, Cell Culture)",
                    LAB_PCR: "🧬 معمل PCR فقط",
                    LAB_SEQUENCING: "🧬 معمل Sequencing فقط",
                    LAB_CELL_CULTURE: "🧫 معمل Cell Culture فقط"
                }.get(lab, lab),
                width="stretch"
            )
            
            submitted = st.form_submit_button("➕ إضافة المستخدم", type="primary", use_container_width=True)
        if submitted:
            ok, msg = add_user(new_username, new_password, new_role, new_lab_access)
            st.success(msg) if ok else st.error(msg)
            if ok:
                st.rerun()

    with tab_del:
        if not usernames:
            st.info("لا يوجد مستخدمون للحذف.")
        else:
            with st.form("delete_user_form"):
                st.markdown("#### حذف مستخدم")
                st.caption("لا يمكن حذف آخر حساب مدير في النظام.")
                target = st.selectbox(
                    "اختر المستخدم", options=usernames, index=None, placeholder="", width="stretch"
                )
                confirmed = st.checkbox("أؤكد حذف هذا المستخدم نهائيًا", width="stretch")
                submitted = st.form_submit_button("🗑️ حذف المستخدم", type="primary", use_container_width=True)
            if submitted:
                if not target:
                    st.warning("⚠️ يرجى اختيار مستخدم أولاً.")
                elif not confirmed:
                    st.warning("⚠️ يرجى تحديد مربع التأكيد قبل الحذف.")
                else:
                    ok, msg = delete_user(target)
                    st.success(msg) if ok else st.error(msg)
                    if ok:
                        st.rerun()

    with tab_list:
        st.markdown("#### قائمة المستخدمين الحاليين")
        view = _users_dataframe()
        if view is None or view.empty:
            st.info("لا يوجد مستخدمون.")
        else:
            st.dataframe(view, use_container_width=True, hide_index=True)
            st.caption(f"عدد المستخدمين: {len(view)}")

    with tab_reset:
        if not usernames:
            st.info("لا يوجد مستخدمون.")
        else:
            with st.form("reset_password_form"):
                st.markdown("#### تغيير كلمة مرور مستخدم")
                target = st.selectbox(
                    "اختر المستخدم", options=usernames, index=None, placeholder="", width="stretch"
                )
                c1, c2 = st.columns(2)
                with c1:
                    new_password = st.text_input(
                        "كلمة المرور الجديدة *", type="password", placeholder="", width="stretch"
                    )
                with c2:
                    confirm_password = st.text_input(
                        "تأكيد كلمة المرور *", type="password", placeholder="", width="stretch"
                    )
                submitted = st.form_submit_button("🔑 تغيير كلمة المرور", type="primary", use_container_width=True)
            if submitted:
                if not target:
                    st.warning("⚠️ يرجى اختيار مستخدم أولاً.")
                elif new_password != confirm_password:
                    st.error("كلمتا المرور غير متطابقتين.")
                else:
                    ok, msg = reset_password(target, new_password)
                    st.success(msg) if ok else st.error(msg)

    st.write("")
    st.markdown("#### ⚙️ تحديث صلاحيات المستخدم")
    if usernames:
        c_tabs1, c_tabs2 = st.columns(2)
        
        with c_tabs1:
            st.markdown("##### 🔐 صلاحية النظام")
            with st.form("set_role_form"):
                c1, c2 = st.columns(2)
                with c1:
                    target_role = st.selectbox(
                        "اختر المستخدم", 
                        options=usernames, 
                        index=None, 
                        placeholder="", 
                        width="stretch",
                        key="role_user_select"
                    )
                with c2:
                    role = st.selectbox(
                        "الصلاحية",
                        options=ROLES,
                        format_func=lambda r: "👑 مدير" if r == ROLE_ADMIN else "👤 مستخدم",
                        width="stretch",
                        placeholder="",
                    )
                submitted_role = st.form_submit_button("💾 حفظ صلاحية النظام", use_container_width=True)
            if submitted_role:
                if not target_role:
                    st.warning("⚠️ يرجى اختيار مستخدم أولاً.")
                else:
                    ok, msg = set_role(target_role, role)
                    st.success(msg) if ok else st.error(msg)
        
        with c_tabs2:
            st.markdown("##### 🔬 صلاحية المعمل")
            with st.form("set_lab_form"):
                c3, c4 = st.columns(2)
                with c3:
                    target_lab = st.selectbox(
                        "اختر المستخدم",
                        options=usernames,
                        index=None,
                        placeholder="",
                        width="stretch",
                        key="lab_user_select"
                    )
                with c4:
                    lab_access = st.selectbox(
                        "المعمل المسموح",
                        options=LABS,
                        format_func=lambda lab: {
                            LAB_ALL: "🌐 جميع المعامل",
                            LAB_PCR: "🧬 PCR",
                            LAB_SEQUENCING: "🧬 Sequencing",
                            LAB_CELL_CULTURE: "🧫 Cell Culture"
                        }.get(lab, lab),
                        width="stretch"
                    )
                submitted_lab = st.form_submit_button("💾 حفظ صلاحية المعمل", use_container_width=True)
            if submitted_lab:
                if not target_lab:
                    st.warning("⚠️ يرجى اختيار مستخدم أولاً.")
                else:
                    ok, msg = set_lab_access(target_lab, lab_access)
                    st.success(msg) if ok else st.error(msg)
                    if ok:
                        st.rerun()

    # ------------------------------------------------------------------ #
    #               تصفير البيانات التجريبية (إجراء خطر — للمدير فقط)
    # ------------------------------------------------------------------ #
    st.write("")
    st.markdown("#### 🧹 تصفير البيانات التجريبية")
    st.caption(
        "يحذف كل صفوف الأصناف وسجل السحوبات من قاعدة البيانات المحلية نهائيًا."
    )
    confirmed = st.checkbox(
        "تأكيد مسح كافة البيانات التجريبية",
        key="confirm_clear_test_data",
        width="stretch",
    )
    if st.button(
        "🧹 تصفير البيانات التجريبية",
        type="primary",
        use_container_width=True,
        disabled=not confirmed,
        key="clear_test_data_btn",
    ):
        ok, msg = clear_test_data()
        if ok:
            st.success("تم مسح جميع البيانات التجريبية بنجاح والمخزن جاهز للعمل")
        else:
            st.error(msg)
    if not confirmed:
        st.caption("⚠️ حدّد مربع التأكيد أعلاه لتفعيل زر التصفير.")


# --------------------------------------------------------------------------- #
#                                  التشغيل
# --------------------------------------------------------------------------- #
def main() -> None:
    cfg = load_config()
    try:
        configure(cfg.database_path)
        ensure_schema("sqlite")
    except Exception as exc:  # noqa: BLE001
        st.session_state["_db_error"] = f"تعذر إعداد قاعدة SQLite: {exc}"

    if not is_logged_in():
        login_form()
        return

    _bootstrap()
    page = _sidebar()
    if not _guard():
        return
    _topbar()

    if page == PAGES[0]:
        page_home()
    elif page == PAGES[1]:
        page_withdraw()
    elif page == PAGES[2]:
        page_items()
    elif page == PAGES[3]:
        page_pcr()
    elif page == REAGENTS_PCR_PAGE:
        page_reagents_pcr()
    elif page == REAGENTS_SEQUENCING_PAGE:
        page_reagents_sequencing()
    elif page == REAGENTS_CELL_CULTURE_PAGE:
        page_reagents_cell_culture()
    elif page == PAGES[4]:
        page_chemicals()
    elif page == PAGES[5]:
        page_office()
    elif page == PAGES[6]:
        page_computer()
    elif page == PAGES[7]:
        page_authority_forms()
    elif page == PAGES[8]:
        page_who_orders()
    elif page == PAGES[9]:
        page_decommission()
    elif page == ADMIN_PAGES[0]:
        page_users()
    else:
        page_reports()


if __name__ == "__main__":
    main()
