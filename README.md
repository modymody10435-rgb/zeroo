# نظام إدارة مخزن المعمل — Streamlit + SQLite

هذه نسخة تعمل بواجهة Streamlit الحالية وقاعدة SQLite محلية، دون اعتماد وقت التشغيل على Google Sheets (كمصدر بيانات أولي) أو PostgreSQL أو Streamlit Cloud.

## الملفات المهمة
- `app.py`: واجهة Streamlit.
- `core/` و`views/`: منطق التطبيق والصفحات.
- `requirements.txt`: مكتبات التشغيل.
- `Dockerfile.streamlit` و`docker-compose.streamlit.yml`: تشغيل على السيرفر باستخدام Docker.
- `data/مخزن المعمل.xlsx`: نسخة البيانات المصدّرة من Google Sheets (كمصدر بيانات أولي).
- `data/warehouse.sqlite3`: قاعدة البيانات المحلية، تُنشأ عند التشغيل.

## تشغيل السيرفر
من داخل مجلد المشروع:
```bash
docker compose -f docker-compose.streamlit.yml up -d --build
```
افتح `http://SERVER_IP:8501` أو اربط الدومين/HTTPS من إعدادات السيرفر.

## الاستيراد الأولي
عند أول تشغيل تُقرأ أوراق Excel وتُستورد البيانات إلى SQLite فقط إذا كان جدول التخزين فارغًا. لا يعاد الاستيراد فوق بيانات موجودة. للاختبار دون تغيير قاعدة البيانات:
```bash
python scripts/import_workbook_sqlite.py --dry-run
```

قاعدة البيانات محفوظة في `data/warehouse.sqlite3` ومجلد `data` مربوط كمسار دائم في Docker Compose. احتفظ بنسخة احتياطية منه. ملف Excel هو تصدير وقت رفعه، وليس اتصالًا مباشرًا بالشيت الأصلي؛ صدّر من Google Sheets (كمصدر بيانات أولي) مجددًا إذا كانت هناك بيانات أحدث.
