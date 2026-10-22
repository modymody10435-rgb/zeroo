# -*- coding: utf-8 -*-
"""ينزّل بيانات الشيت الحقيقي إلى قاعدة بيانات مجلد معيّن (يُستخدم لتجهيز dist)."""
import os
import sys

DIST = sys.argv[1] if len(sys.argv) > 1 else r"D:\polio stock\dist\PolioStock"
sys.path.insert(0, r"D:\polio stock")  # الكود من المصدر، والمسارات/الأسرار من مجلد النشر
os.chdir(DIST)

from core import offline  # noqa: E402
from core.config import load_config  # noqa: E402

cfg = load_config()
offline.configure(cfg)
offline.init_db()
res = offline.initial_pull(force=True)
print("initial_pull:", res)
users = offline.read_snapshot("Users")
print("  Users:", 0 if users is None else len(users))
if users is not None and not users.empty:
    print("USERS (%d): %s" % (len(users), ", ".join(users["username"].astype(str))))
prods = offline.read_snapshot("Products")
if prods is not None and "added_by" in prods.columns:
    print("added_by column present ✓")
print("PREWARM DONE ->", offline.db_path())
