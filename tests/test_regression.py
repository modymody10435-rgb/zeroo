# -*- coding: utf-8 -*-
"""اختبارات تراجعية شاملة (بدون شبكة حقيقية).

تغطي: تهيئة القاعدة تلقائيًا، العمل دون اتصال، دفع المزامنة، السحب الأولي،
ذاكرة الدخول، رسائل أخطاء تسجيل الدخول، ومسارات الكتابة المتصلة.
"""
import os
import shutil
import sqlite3
import sys
import tempfile

import pandas as pd

os.environ["POLIO_FORCE_OFFLINE"] = "1"
os.environ["GSHEETS_KEY"] = "k-regression"
sys.path.insert(0, r"D:\polio stock")
os.chdir(r"D:\polio stock")

from gspread.exceptions import WorksheetNotFound  # noqa: E402

from core import offline, services, users  # noqa: E402
from core import auth as auth_mod  # noqa: E402
from core import gsheets as gsheets_mod  # noqa: E402
from core.config import SHEETS, load_config  # noqa: E402
from core.gsheets import SCHEMA  # noqa: E402

TEST_DATA = os.path.join(tempfile.gettempdir(), "polio_reg_test")
shutil.rmtree(TEST_DATA, ignore_errors=True)
os.makedirs(TEST_DATA, exist_ok=True)


def cfg_stub(key="k-regression"):
    return type(
        "Cfg",
        (),
        {
            "spreadsheet_key": key,
            "service_account_info": None,
            "service_account_file": "",
            "database_path": os.path.join(TEST_DATA, "warehouse.db"),
        },
    )()


class FakeCell:
    def __init__(self, row):
        self.row = row


class FakeWS:
    def __init__(self, title, headers, data_rows=None):
        self.title = title
        self.rows = [list(headers)] + [list(r) for r in (data_rows or [])]
        self.fail_next = False

    def _maybe_fail(self):
        if self.fail_next:
            self.fail_next = False
            raise Exception("network timeout: connection refused")

    def row_values(self, i):
        return self.rows[i - 1][:] if 0 < i <= len(self.rows) else []

    def get_all_values(self):
        self._maybe_fail()
        return [r[:] for r in self.rows]

    def get_all_records(self, default_blank="", numericise_ignore=None):
        self._maybe_fail()
        head = self.rows[0]
        out = []
        for r in self.rows[1:]:
            out.append({h: (r[i] if i < len(r) else default_blank) for i, h in enumerate(head)})
        return out

    def append_row(self, values, value_input_option=None):
        self._maybe_fail()
        self.rows.append([str(v) for v in values])

    def update_cell(self, r, c, v):
        self._maybe_fail()
        while len(self.rows) < r:
            self.rows.append([])
        row = self.rows[r - 1]
        while len(row) < c:
            row.append("")
        row[c - 1] = str(v)

    def find(self, value, in_column=None):
        self._maybe_fail()
        ci = (in_column or 1) - 1
        for i, r in enumerate(self.rows[1:], start=2):
            if ci < len(r) and str(r[ci]).strip() == str(value).strip():
                return FakeCell(i)
        return None

    def delete_rows(self, start, count=None):
        self._maybe_fail()
        count = 1 if count is None else count
        del self.rows[start - 1 : start - 1 + count]

    def batch_clear(self, ranges):
        pass


class FakeSS:
    def __init__(self, worksheets):
        self._ws = {w.title: w for w in worksheets}

    def worksheets(self):
        return list(self._ws.values())

    def worksheet(self, title):
        if title not in self._ws:
            raise WorksheetNotFound(title)
        return self._ws[title]

    def add_worksheet(self, title, rows=1000, cols=10):
        ws = FakeWS(title, [f"c{i}" for i in range(cols)])
        self._ws[title] = ws
        return ws


class FakeClient:
    def __init__(self, ss):
        self._ss = ss

    def open_by_key(self, key):
        return self._ss


def row_for(sheet, mapping):
    headers = SCHEMA[SHEETS[sheet]]
    return [str(mapping.get(h, "")) for h in headers]


def make_remote(with_data=False):
    worksheets = []
    for name, headers in SCHEMA.items():
        worksheets.append(FakeWS(name, headers))
    ss = FakeSS(worksheets)
    if with_data:
        ss.worksheet(SHEETS["products"]).rows.append(
            row_for(
                "products",
                {
                    "product_code": "P100",
                    "product_name": "محلول بعيد",
                    "unit": "10",
                    "current_stock": 50,
                    "starting_stock": 50,
                },
            )
        )
        for uname, role, pwd in (("admin", "admin", "admin123"), ("Nada", "user", "nada123")):
            ss.worksheet(SHEETS["users"]).rows.append(
                row_for(
                    "users",
                    {
                        "username": uname,
                        "password_hash": users.hash_password(pwd),
                        "role": role,
                        "created_at": "2026-01-01 10:00:00",
                    },
                )
            )
    return ss


def install_fake(ss, online=True):
    offline._client_cache = FakeClient(ss)
    offline._worksheet_cache.clear()
    offline.is_online = lambda timeout=2.0: online


def tables(path):
    con = sqlite3.connect(path)
    try:
        return {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        con.close()


# --------------------------------------------------------------------------- #
# أ) تهيئة القاعدة تلقائيًا (إصلاح خطأ no such table: outbox)
# --------------------------------------------------------------------------- #
offline.configure(cfg_stub())
path = offline.init_db()
got = tables(path)
for t in ("outbox", "snapshot", "meta", "auth_cache"):
    assert t in got, f"الجدول {t} غير موجود بعد init_db — الجداول: {got}"
assert offline.pending_count() == 0
print("[PASS] init_db ينشئ كل الجداول (outbox/snapshot/meta/auth_cache)")

os.remove(path)
assert offline.pending_count() == 0
assert {"outbox", "snapshot", "meta", "auth_cache"} <= tables(path)
print("[PASS] حذف ملف القاعدة أثناء التشغيل: تُعاد الجداول تلقائيًا بلا خطأ")

# --------------------------------------------------------------------------- #
# ب) سير العمل دون اتصال
# --------------------------------------------------------------------------- #
install_fake(make_remote(), online=False)
ok, msg = services.add_stock_item("محلول تجريبي", 100, unit="10", code="001")
assert ok, msg
df = offline.read_snapshot(SHEETS["products"])
assert not df.empty and "001" in set(df["product_code"].astype(str)), "الصنف غير محفوظ محليًا"
print(f"[PASS] إضافة صنف دون اتصال ({msg[:40]}...)")

ok, msg = services.sell_draw_item("001", 7, person="ساحب", supervisor="مسؤول")
assert ok, msg
df = offline.read_snapshot(SHEETS["products"])
stock = float(df[df["product_code"].astype(str) == "001"]["current_stock"].iloc[0])
assert stock == 93.0, f"الرصيد بعد السحب {stock}"
print(f"[PASS] سحب دون اتصال (الرصيد المتبقي {stock:g})")

ok, msg = services.update_product("001", {"min_stock": 5, "notes": "ملاحظة محدثة"})
assert ok, msg
df = offline.read_snapshot(SHEETS["products"])
r0 = df[df["product_code"].astype(str) == "001"].iloc[0]
assert float(r0["min_stock"]) == 5 and str(r0["notes"]) == "ملاحظة محدثة"
print("[PASS] تعديل صنف دون اتصال")

ok, msg = services.add_stock_item("لقاح شلل الأطفال", 10, code="002")
assert ok, msg
print("[PASS] إضافة صنف ثانٍ دون اتصال")

ops = offline.pending_ops()
assert ops, "الطابور فارغ بعد العمليات دون اتصال"
sheets_in_queue = {o["sheet"] for o in ops}
assert SHEETS["products"] in sheets_in_queue and SHEETS["withdrawals"] in sheets_in_queue
assert offline.status_info()["state"] == "offline"
print(f"[PASS] الطابور فيه عمليات معلّقة (عدد={len(ops)}) والحالة offline")

ok, msg = services.delete_product("001", force=True)
assert ok, msg
df = offline.read_snapshot(SHEETS["products"])
assert "001" not in set(df["product_code"].astype(str)), "الصنف لم يُحذف محليًا"
print("[PASS] حذف صنف دون اتصال")

# --------------------------------------------------------------------------- #
# ج) دفع المزامنة إلى شيت وهمي + مقاومة أخطاء الشبكة
# --------------------------------------------------------------------------- #
remote = make_remote()
install_fake(remote, online=True)
res = offline.flush()
assert res.get("synced", 0) > 0, res
assert offline.pending_count() == 0
prod_ws = remote.worksheet(SHEETS["products"])
codes = {str(r[0]) for r in prod_ws.rows[1:]}
assert "002" in codes, f"لم يصل الصنف الثاني للشيت: {codes}"
wd_ws = remote.worksheet(SHEETS["withdrawals"])
assert len(wd_ws.rows) > 1, "عملية السحب لم تصل للشيت"
assert offline.status_info()["state"] in ("online", "syncing")
print(f"[PASS] المزامنة دفعت الطابور ({res})")

offline.enqueue(SHEETS["products"], "append", {"row": {"product_code": "NET1", "product_name": "فشل شبكي"}})
prod_ws.fail_next = True
res = offline.flush()
assert offline.pending_count() >= 1, "عمليات فشلت نظريًا وضاعت من الطابور"
assert offline.status_info()["state"] in ("offline", "error", "syncing")
print(f"[PASS] خطأ شبكة أثناء الدفع يُبقي العمليات في الطابور ({res})")

res = offline.flush()
assert offline.pending_count() == 0, f"لم تُدفع العمليات بعد التعافي: {res}"
print(f"[PASS] المزامنة تستأنف بعد الشفاء ({res})")

# --------------------------------------------------------------------------- #
# د) السحب الأولي + ذاكرة الدخول + الدخول دون اتصال
# --------------------------------------------------------------------------- #
os.remove(offline.db_path())
offline.configure(cfg_stub(key="k-pull"))
remote = make_remote(with_data=True)
install_fake(remote, online=True)
res = offline.initial_pull(force=True)
assert res.get("pulled") == 7 and not res.get("failed"), res
assert offline.has_snapshot(SHEETS["products"])
assert offline.auth_cache_count() == 2
print(f"[PASS] السحب الأولي سحب كل الأوراق ({res})")

cached = offline.get_cached_user("admin")
assert cached and users.verify_password("admin123", cached["password_hash"])
print("[PASS] ذاكرة الدخول تولدت من السحب (تجزئة صحيحة)")

install_fake(remote, online=False)
user, err = auth_mod._check("admin", "admin123")
assert user and not err, err
user, err = auth_mod._check("admin", "خطأ")
assert not user and err == "اسم المستخدم أو كلمة المرور غير صحيحة."
print("[PASS] الدخول دون اتصال بالذاكرة المحلية + رفض كلمة خاطئة")

ok, msg = users.reset_password("admin", "newpass99")
assert ok, msg
cached = offline.get_cached_user("admin")
assert users.verify_password("newpass99", cached["password_hash"])
assert not users.verify_password("admin123", cached["password_hash"])
print(f"[PASS] تغيير كلمة مرور دون اتصال ({msg})")

ok, msg = users.add_user("worker1", "wpass123")
assert ok, msg
assert offline.get_cached_user("worker1")
user, err = auth_mod._check("worker1", "wpass123")
assert user and not err, f"_check worker1: err={err!r}"
print(f"[PASS] إضافة مستخدم دون اتصال ({msg})")

# --------------------------------------------------------------------------- #
# هـ) رسائل أخطاء تسجيل الدخول التوضيحية
# --------------------------------------------------------------------------- #
orig_load_config = auth_mod.load_config
auth_mod.load_config = lambda: cfg_stub(key="")
user, err = auth_mod._check("x", "y")
assert user is None and "لم يتم إعداد مفتاح الجدول" in err, err
auth_mod.load_config = orig_load_config
print("[PASS] لا مفتاح: رفض + رسالة توضيحية")

os.remove(offline.db_path())
offline.configure(cfg_stub(key="k-fresh"))
install_fake(make_remote(), online=False)
user, err = auth_mod._check("ghost", "ghost")
assert user is None and "لا توجد حسابات محفوظة" in err, err
print("[PASS] أول تشغيل دون اتصال: رسالة «لا توجد حسابات»")

real_client_from_config = gsheets_mod._client_from_config


def _raise_403(cfg):
    raise Exception("403: Permission denied")


gsheets_mod._client_from_config = _raise_403
install_fake(make_remote(), online=True)
user, err = auth_mod._check("anyone", "any")
assert user is None and "403: Permission denied" in err, err
gsheets_mod._client_from_config = real_client_from_config
print("[PASS] خطأ API: رسالة تفسيرية تحتوي تفاصيل403")

# --------------------------------------------------------------------------- #
# و) مسارات الكتابة المتصلة (شيت وهمي على مستوى الخدمات)
# --------------------------------------------------------------------------- #
remote = make_remote()


def _col_index(sheet, match_col):
    return SCHEMA[sheet].index(match_col)


def fake_read_sheet(key, sheet):
    ws = remote.worksheet(sheet)
    return pd.DataFrame(ws.get_all_records(), columns=SCHEMA[sheet])


def fake_append_row(key, sheet, row):
    remote.worksheet(sheet).append_row([str(row.get(h, "")) for h in SCHEMA[sheet]])


def fake_update_row(key, sheet, match_col, match_value, updates):
    ws = remote.worksheet(sheet)
    ci = _col_index(sheet, match_col)
    for i, r in enumerate(ws.rows[1:], start=2):
        if ci < len(r) and str(r[ci]).strip() == str(match_value).strip():
            for col, v in updates.items():
                if col in SCHEMA[sheet]:
                    ws.update_cell(i, SCHEMA[sheet].index(col) + 1, v)
            return True
    return False


def fake_delete_row(key, sheet, match_col, match_value):
    ws = remote.worksheet(sheet)
    ci = _col_index(sheet, match_col)
    for i in range(len(ws.rows) - 1, 0, -1):
        if ci < len(ws.rows[i]) and str(ws.rows[i][ci]).strip() == str(match_value).strip():
            del ws.rows[i]
            return True
    return False


def fake_delete_rows_where(key, sheet, match_col, match_value):
    n = 0
    while fake_delete_row(key, sheet, match_col, match_value):
        n += 1
    return n


def fake_count_rows_where(key, sheet, match_col, match_value):
    ws = remote.worksheet(sheet)
    ci = _col_index(sheet, match_col)
    return sum(
        1 for r in ws.rows[1:] if ci < len(r) and str(r[ci]).strip() == str(match_value).strip()
    )


fakes = {
    "read_sheet": fake_read_sheet,
    "append_row": fake_append_row,
    "update_row": fake_update_row,
    "delete_row": fake_delete_row,
    "delete_rows_where": fake_delete_rows_where,
    "count_rows_where": fake_count_rows_where,
    "clear_rows_where": lambda key, sheet, match_col, match_value: 0,
    "sync_row": lambda *a, **k: 1,
    "invalidate_cache": lambda: None,
}
orig = {n: getattr(services, n) for n in fakes}
for n, fn in fakes.items():
    setattr(services, n, fn)
install_fake(remote, online=True)
ok, msg = services.add_stock_item("متصل مباشر", 5, code="900")
assert ok, msg
assert offline.pending_count() == 0, "الكتابة المتصلة لا تُqueue"
assert "900" in {str(r[0]) for r in remote.worksheet(SHEETS["products"]).rows[1:]}
print("[PASS] مسار الكتابة المتصل: يصل الشيت بلا طابور")

ok, msg = services.update_product("900", {"min_stock": 2})
assert ok, msg
ok, msg = services.delete_product("900", force=True)
assert ok, msg
assert "900" not in {str(r[0]) for r in remote.worksheet(SHEETS["products"]).rows[1:]}
print("[PASS] مسار التعديل والحذف المتصل على الشيت")
for n, fn in orig.items():
    setattr(services, n, fn)

# --------------------------------------------------------------------------- #
# ز) تغيير المفتاح يمسح البيانات المحلية (عدم خلط الشيتات)
# --------------------------------------------------------------------------- #
remote = make_remote(with_data=True)
install_fake(remote, online=True)
offline.enqueue(SHEETS["products"], "append", {"row": {"product_code": "OLD1"}})
offline.configure(cfg_stub(key="k-OTHER-KEY"))
assert offline.pending_count() == 0, "الطابور القديم لم يُمسح بعد تغيير المفتاح"
assert offline.auth_cache_count() == 0
print("[PASS] تغيير المفتاح يمسح الطابور/الذاكرة/النسخة المحلية")

print("ALL PASS")
