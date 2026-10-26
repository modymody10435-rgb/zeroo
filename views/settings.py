"""صفحة الإعدادات: حالة قاعدة SQLite وأدوات النظام."""
from __future__ import annotations
import os
from pathlib import Path
import pandas as pd
import streamlit as st
from core.config import SHEETS, load_config
from core.gsheets import DataError, clear_cache, ensure_schema, get_spreadsheet, read_sheet
from core.services import get_orders, get_products, today_str
from core.styles import header

def render() -> None:
    header("⚙️ الإعدادات", "قاعدة بيانات SQLite المحلية")
    cfg = load_config()
    st.markdown("### 🗄️ التخزين المحلي")
    st.code(cfg.database_path)
    st.caption("تُحفظ البيانات داخل مجلد data في المشروع، ولا يحتاج التطبيق إلى Google Sheets أثناء التشغيل.")
    if st.button("🔍 فحص قاعدة البيانات", type="primary"):
        try:
            ensure_schema("sqlite")
            st.success(f"قاعدة البيانات جاهزة: {get_spreadsheet('sqlite').title}")
        except DataError as exc: st.error(str(exc))
        except Exception as exc: st.error(f"فشل الفحص: {exc}")
    st.markdown("### 📊 ملخص البيانات الحالية")
    try:
        counts = {"Products (الأصناف)": len(get_products()), "Orders (الطلبات)": len(get_orders()), "Order_Items (أصناف الطلبات)": len(read_sheet("sqlite", SHEETS["order_items"])), "Withdrawals (السحوبات)": len(read_sheet("sqlite", SHEETS["withdrawals"])), "Stock_Movements (الحركات)": len(read_sheet("sqlite", SHEETS["stock_movements"]))}
        st.dataframe(pd.DataFrame({"الورقة": list(counts.keys()), "عدد الصفوف": list(counts.values())}), use_container_width=True, hide_index=True)
    except Exception as exc: st.warning(f"تعذر قراءة الملخص: {exc}")
    if st.button("♻️ تحديث البيانات المعروضة"):
        clear_cache(); st.success("تم مسح الكاش. أعد تحميل الصفحة.")
    st.caption(f"تاريخ النظام: {today_str()}")
    with st.expander("📘 تشغيل المشروع على السيرفر"):
        st.markdown("""1. فك ضغط المشروع على السيرفر.
2. شغّل `docker compose -f docker-compose.streamlit.yml up -d --build`.
3. ملف قاعدة البيانات هو `data/warehouse.sqlite3` ويظل محفوظًا في مجلد المشروع.
4. احتفظ بنسخة احتياطية من مجلد `data` قبل التحديثات.
5. استيراد Excel يتم تلقائيًا مرة واحدة فقط إذا كانت قاعدة البيانات فارغة.""")
