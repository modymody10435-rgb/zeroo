"""نظام إدارة مخزن المعمل - واجهة مبسطة (Streamlit).

الصفحات (حسب ترتيب القائمة الجانبية):
    1. 🏠 الصفحة الرئيسية (Dashboard)     — الافتراضية بعد الدخول
    2. 📤 تسجيل سحب (Withdrawal Page)
    3. ➕ إدارة الأصناف (Item Management)
    4. 🧬 قسم PCR (PCR Section)
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
    - عمل دون اتصال (Offline-First): الحفظ في قاعدة بيانات محلية SQLite عند
      انقطاع الإنترنت ودَفع تلقائي إلى Google Sheets فور عودة الاتصال، مع
      شارة حالة (Online / Offline / Syncing) أعلى الواجهة وفي القائمة الجانبية.

قاعدة البيانات: SQLite محلية (نسخة الديسك توب) — ملف data/warehouse.db.
"""
from __future__ import annotations

import html
import os
import subprocess
from datetime import date, datetime

import pandas as pd
import streamlit as st

from core import offline
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
    receive_authority_forms,
    record_movement,
    sell_draw_item,
    update_product,
    withdraw_authority_forms,
    withdraw_chemical,
    withdraw_computer_item,
    withdraw_office_item,
)
from core.styles import header, inject_styles, metric_card
from core.users import (
    ROLE_ADMIN,
    ROLES,
    add_user,
    delete_user,
    get_users,
    reset_password,
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
    "🗑️ تكهين الأجهزة (Device Decommissioning)",
    "📊 التقارير والسجلات (Reports & Logs)",
]
ADMIN_PAGES = ["👤 إدارة المستخدمين (User Management - Admin only)"]


# --------------------------------------------------------------------------- #
#                       التهيئة والاتصال بقاعدة البيانات
# --------------------------------------------------------------------------- #
def _bootstrap() -> None:
    if st.session_state.get("_db_ready"):
        return
    cfg = load_config()
    try:
        offline.configure(cfg)  # بيانات المزامنة الخلفية (بلا أي واجهة Streamlit)
        configure(cfg.database_path)
        ensure_schema(cfg.spreadsheet_key)  # يُؤجَّل تلقائيًا عند غياب الاتصال
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
    st.markdown(offline.pill_html(), unsafe_allow_html=True)


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
        items = PAGES + (ADMIN_PAGES if is_admin() else [])

        # طلب تنقّل من أزرار الوصول السريع (يُستهلك قبل تركيب القائمة)
        pending = st.session_state.pop("pending_page", None)
        if pending in items:
            st.session_state["nav_page"] = pending
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
            st.caption(f"💾 قاعدة البيانات المحلية: `{info['title']}`")
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

    products = get_products()
    withdrawals = get_withdrawals()

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

    products = get_products()
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
    w = get_withdrawals()
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
        pcr_products = products[is_pcr]
        chemical_products = products[is_chemical]
        office_products = products[is_office]
        computer_products = products[is_computer]
        general_products = products[~is_pcr & ~is_chemical & ~is_office & ~is_computer]
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
        st.caption(f"🧬 أصناف PCR تُخزَّن تلقائيًا في «{PCR_STORAGE_SECTION}» عند ترك مكان التخزين فارغًا.")
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
    st.success(f"{msg} 🔄 التعديلات محفوظة في Google Sheets.")
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
            "سيُحذف الصنف نهائيًا من ورقة Products في Google Sheets ومن النسخة المحلية. "
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
    st.dataframe(_pcr_device_view(df), use_container_width=True, hide_index=True)


def _render_pcr_add_device(pcr) -> None:
    existing_serials = {
        _product_note(value).lower()
        for value in pcr.get("serial_number", [])
        if _product_note(value)
    }
    existing_codes = {
        str(value).strip().lower() for value in pcr.get("product_code", []) if str(value).strip()
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


def _render_pcr_edit_device(pcr) -> None:
    if pcr.empty:
        st.info("لا توجد أجهزة PCR لتعديلها.")
        return

    labels = {}
    for _, row in pcr.iterrows():
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
        (r for _, r in pcr.iterrows() if str(r["product_code"]).strip() == code),
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
        for _, row in pcr.iterrows()
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
    header("🧬 قسم PCR", "تتبع أجهزة PCR: الاسم، الرقم التسلسلي، الشركة المصنعة، الموقع، الكمية والحالة")
    st.caption(
        f"يعرض هذا القسم أجهزة تصنيف «{PRODUCT_CATEGORY_PCR}» فقط. "
        f"تُخزَّن الأجهزة تلقائيًا في «{PCR_STORAGE_SECTION}» عند ترك مكان التخزين فارغًا."
    )

    products = get_pcr_products()
    pcr = products.copy()
    if not pcr.empty:
        for column in (
            "serial_number",
            "manufacturer",
            "storage_location",
            "device_status",
        ):
            if column not in pcr.columns:
                pcr[column] = ""
        pcr["_stock"] = pcr["current_stock"].apply(to_number)
        status_column = (
            pcr["device_status"].apply(_product_note)
            if "device_status" in pcr.columns
            else pd.Series([""] * len(pcr), index=pcr.index)
        )
        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("عدد أجهزة PCR", len(pcr), width="stretch")
        with c2:
            st.metric("إجمالي الكميات", f"{pcr['_stock'].sum():g}", width="stretch")
        with c3:
            st.metric(
                "أجهزة تحت الصيانة",
                int((status_column == "تحت الصيانة").sum()),
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
        _render_product_delete_form(
            pcr, "pcr", "لا توجد أجهزة PCR للحذف."
        )
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
            view = view[
                view["device_status"].apply(_product_note) == status_filter
            ]

        st.write("")
        st.markdown(f"#### 📦 أجهزة PCR ({len(view)})")
        _render_pcr_devices_table(view, "لا توجد أجهزة PCR مطابقة للبحث.")

        st.write("")
        st.markdown("#### 🗂️ التخزين المنظم داخل قسم PCR")
        grouped = view.copy()
        if "storage_location" not in grouped.columns:
            grouped["storage_location"] = ""
        grouped["storage_location"] = grouped["storage_location"].apply(
            lambda value: str(value or "").strip() or PCR_STORAGE_SECTION
        )
        for location, group in grouped.groupby("storage_location", sort=True):
            st.markdown(f"##### 📍 {location} — {len(group)} جهاز")
            _render_pcr_devices_table(group, "لا توجد أجهزة في هذا الموقع.")


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
            "سيُحذف الصنف مع كل سجلات الوارد والصرف الخاصة به من Google Sheets، "
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

    pcr = get_pcr_products().copy()
    computer = get_computer_products().copy()
    for frame in (pcr, computer):
        for column in (
            "serial_number",
            "device_status",
            "decommission_date",
            "decommission_reason",
            "decommissioned_by",
        ):
            if column not in frame.columns:
                frame[column] = ""

    pcr_done = pcr[
        pcr["device_status"].apply(_product_note) == DEVICE_STATUS_DECOMMISSIONED
    ] if not pcr.empty else pcr
    computer_done = computer[
        computer["device_status"].apply(_product_note) == DEVICE_STATUS_DECOMMISSIONED
    ] if not computer.empty else computer
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("إجمالي الأجهزة المكهنة", len(pcr_done) + len(computer_done), width="stretch")
    with c2:
        st.metric("أجهزة PCR المكهنة", len(pcr_done), width="stretch")
    with c3:
        st.metric("مستلزمات الكمبيوتر المكهنة", len(computer_done), width="stretch")

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
    devices = pcr if source_category == PRODUCT_CATEGORY_PCR else computer

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
        ("أجهزة PCR", pcr_done),
        ("مستلزمات الكمبيوتر", computer_done),
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
    done_frames = [frame for frame in (pcr_done, computer_done) if not frame.empty]
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
    view["الحالة"] = view["role"].apply(lambda r: "👑 مدير" if str(r).strip().lower() == ROLE_ADMIN else "👤 مستخدم")
    cols = ["username"]
    if "created_at" in view.columns:
        cols.append("created_at")
    cols.append("الحالة")
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
            submitted = st.form_submit_button("➕ إضافة المستخدم", type="primary", use_container_width=True)
        if submitted:
            ok, msg = add_user(new_username, new_password, new_role)
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
    st.markdown("#### ⚙️ صلاحية المستخدم")
    if usernames:
        with st.form("set_role_form"):
            c1, c2 = st.columns(2)
            with c1:
                target = st.selectbox(
                    "اختر المستخدم", options=usernames, index=None, placeholder="", width="stretch"
                )
            with c2:
                role = st.selectbox(
                    "الصلاحية",
                    options=ROLES,
                    format_func=lambda r: "👑 مدير" if r == ROLE_ADMIN else "👤 مستخدم",
                    width="stretch",
                    placeholder="",
                )
            submitted = st.form_submit_button("💾 حفظ الصلاحية", use_container_width=True)
        if submitted:
            if not target:
                st.warning("⚠️ يرجى اختيار مستخدم أولاً.")
            else:
                ok, msg = set_role(target, role)
                st.success(msg) if ok else st.error(msg)

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
        offline.init_db()          # تهيئة القاعدة المحلية (إنشاء الجداول) فورًا
    except Exception as exc:  # noqa: BLE001
        st.session_state["_db_error"] = f"تعذر تهيئة قاعدة البيانات المحلية: {exc}"
    try:
        offline.configure(cfg)      # يلتقط بيانات المزامنة للخيط الخلفي
        offline.ensure_worker()     # خيط مزامنة تلقائي: يدفع الطابور ويسحب البيانات في الخلفية
        offline.flush_if_pending()  # دفعة فورية عند فتح التطبيق (سريعة)
    except Exception as exc:  # noqa: BLE001
        st.session_state["_db_error"] = f"تعذر تجهيز نظام المزامنة المحلية: {exc}"
    try:
        configure(cfg.database_path)
    except Exception as exc:  # noqa: BLE001
        st.session_state["_db_error"] = f"تعذر تجهيز مسار قاعدة البيانات: {exc}"

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
    elif page == PAGES[4]:
        page_chemicals()
    elif page == PAGES[5]:
        page_office()
    elif page == PAGES[6]:
        page_computer()
    elif page == PAGES[7]:
        page_authority_forms()
    elif page == PAGES[8]:
        page_decommission()
    elif page == ADMIN_PAGES[0]:
        page_users()
    else:
        page_reports()


if __name__ == "__main__":
    main()
