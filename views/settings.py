"""صفحة الإعدادات: حالة الاتصال، إعداد الأسرار، أدوات."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from core.config import SHEETS, load_config
from core.gsheets import DataError, clear_cache, ensure_schema, get_spreadsheet, read_sheet
from core.services import get_orders, get_products, today_str
from core.styles import header


def render() -> None:
    header("⚙️ الإعدادات", "إعدادات قاعدة البيانات PostgreSQL وأدوات النظام")

    cfg = load_config()

    st.markdown("### 🔌 حالة الاتصال")
    if not cfg.spreadsheet_key:
        st.error(
            "لم يتم إعداد اتصال PostgreSQL. اضبط DATABASE_URL في ملف .env أو "
            "[database].url في .streamlit/secrets.toml ثم أعد تشغيل التطبيق."
        )
        _render_help()
        return

    col1, col2 = st.columns(2)
    with col1:
        st.write("**قاعدة البيانات:**")
        masked = "PostgreSQL (عنوان الاتصال مخفي)" if cfg.database_url else "PostgreSQL (تحقق من الإعدادات)"
        st.code(masked)
    with col2:
        method = "DATABASE_URL / Streamlit Secrets"
        st.write("**طريقة الاعتماد:**")
        st.code(method)

    if st.button("🔍 اختبار الاتصال", type="primary"):
        try:
            ensure_schema(cfg.spreadsheet_key)
            ss = get_spreadsheet(cfg.spreadsheet_key)
            st.success(f"تم الاتصال بنجاح بالملف: {ss.title}")
        except DataError as exc:
            st.error(str(exc))
        except Exception as exc:  # noqa: BLE001
            st.error(f"فشل الاتصال: {exc}")

    if st.button("🧱 إنشاء/فحص جداول قاعدة البيانات"):
        try:
            ensure_schema(cfg.spreadsheet_key)
            st.success("تم التأكد من جاهزية جداول قاعدة البيانات: " + ", ".join(SHEETS.values()))
        except Exception as exc:  # noqa: BLE001
            st.error(f"تعذر إنشاء الأوراق: {exc}")

    st.write("")
    st.markdown("### 📊 ملخص البيانات الحالية")
    try:
        counts = {
            "Products (الأصناف)": len(get_products()),
            "Orders (الطلبات)": len(get_orders()),
            "Order_Items (أصناف الطلبات)": len(read_sheet(cfg.spreadsheet_key, SHEETS["order_items"])),
            "Withdrawals (السحوبات)": len(read_sheet(cfg.spreadsheet_key, SHEETS["withdrawals"])),
            "Stock_Movements (الحركات)": len(read_sheet(cfg.spreadsheet_key, SHEETS["stock_movements"])),
        }
        st.dataframe(
            pd.DataFrame({"الورقة": list(counts.keys()), "عدد الصفوف": list(counts.values())}),
            use_container_width=True,
            hide_index=True,
        )
    except Exception as exc:  # noqa: BLE001
        st.warning(f"تعذر قراءة الملخص: {exc}")

    st.write("")
    st.markdown("### 🛠️ أدوات")
    if st.button("♻️ تحديث الاتصال (مسح الكاش)"):
        clear_cache()
        st.success("تم مسح الكاش. أعد تحميل الصفحة.")

    st.caption(f"تاريخ النظام: {today_str()}")

    _render_help()


def _render_help() -> None:
    with st.expander("📘 طريقة إعداد PostgreSQL"):
        st.markdown(
            """
1. انسخ `.env.example` إلى `.env` واضبط كلمة مرور قوية لـ `POSTGRES_PASSWORD`.
2. شغّل `docker compose -f docker-compose.streamlit.yml up -d --build`.
3. تُحفظ بيانات PostgreSQL داخل مجلد المشروع `data/postgres-data/` وتستمر بعد إعادة تشغيل الحاويات.
4. لا تحذف هذا المجلد أثناء تشغيل النظام، وخذ نسخة احتياطية قبل أي ترقية أو نقل.
5. لا تشارك ملف `.env` أو ترفع كلمات المرور إلى GitHub.
            """
        )
        st.code(
            '[database]\nurl = "postgresql://warehouse_user:YOUR_PASSWORD@localhost:5432/warehouse_db"\n\n'
            '[auth]\nusername = "admin"\npassword = "CHANGE_ME_TO_A_LONG_RANDOM_PASSWORD"\napp_title = "نظام إدارة مخزن المعمل"',
            language="toml",
        )
