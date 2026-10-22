# -*- coding: utf-8 -*-
"""اختبار تشغيل التطبيق كاملًا (AppTest) في وضع دون اتصال."""
import os
import sys

os.environ["POLIO_FORCE_OFFLINE"] = "1"
os.environ["GSHEETS_KEY"] = "test-key-123"
sys.path.insert(0, r"D:\polio stock")
os.chdir(r"D:\polio stock")

from streamlit.testing.v1 import AppTest  # noqa: E402

at = AppTest.from_file(r"D:\polio stock\app.py", default_timeout=90)
at.run()
assert not at.exception, at.exception
print("[PASS] صفحة تسجيل الدخول تعمل دون اتصال")

# تسجيل الدخول بالحساب الافتراضي من secrets (مسار احتياطي عند غياب ورقة المستخدمين)
at.text_input[0].set_value("admin")
at.text_input[1].set_value("admin123")
for btn in at.button:
    if "تسجيل الدخول" in (btn.label or ""):
        btn.click()
        break
at.run()
assert not at.exception, at.exception
logged_in = bool("logged_in" in at.session_state and at.session_state["logged_in"])
print(f"[PASS] تسجيل الدخول دون اتصال (logged_in={logged_in})")
assert logged_in

# الصفحة الرئيسية تُعرض من النسخة المحلية
markdown = "\n".join(str(m.value) for m in at.markdown)
assert "Offline" in markdown or "online" in markdown.lower(), markdown[:500]
print("[PASS] شارة حالة المزامنة ظاهرة في الواجهة")

# التنقل إلى صفحة الأصناف وإضافة صنف دون اتصال
nav = at.radio[0]
options = list(nav.options)
nav.set_value(options[2])  # إدارة الأصناف
at.run()
assert not at.exception, at.exception
print("[PASS] صفحة إدارة الأصناف تعمل دون اتصال")

# إضافة صنف والتحقق من تسجيل اسم المستخدم في عمود added_by
at.text_input(key="add_code").set_value("T001")
at.text_input(key="add_name").set_value("صنف اختبار")
at.number_input(key="add_qty").set_value(5.0)
for btn in at.button:
    if "إضافة الصنف" in (btn.label or ""):
        btn.click()
        break
at.run()
assert not at.exception, at.exception
from core import offline  # noqa: E402

df = offline.read_snapshot("Products")
t001 = df[df["product_code"].astype(str).str.strip() == "T001"]
assert not t001.empty, "T001 غير موجود بعد الإضافة"
added = str(t001.iloc[0].get("added_by", "") or "").strip()
assert added == "admin", f"added_by غير صحيح: {added!r}"
print(f"[PASS] الصنف أُضيف باسم المستخدم (added_by={added})")
print(f"[INFO] حالة المزامنة: {offline.status_info()}")
print(f"[INFO] قاعدة البيانات المحلية: {offline.db_path()}")
print("SMOKE TEST PASSED")
