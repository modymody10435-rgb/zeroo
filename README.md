# نظام إدارة مخزن المعمل

تطبيق ويب عربي كامل بواجهة **RTL** مبنية بـ HTML5 وCSS3 وJavaScript، وخادم **Python/FastAPI**، وقاعدة بيانات **SQLite** محلية. التطبيق لا يعتمد على Streamlit ولا على Google Sheets لتشغيله اليومي.

## المزايا

- تسجيل دخول بجلسات آمنة وصلاحيات مدير/مستخدم.
- لوحة معلومات وإحصاءات المخزون والحركات.
- إدارة الأصناف: PCR، الكيماويات، المكتبية، مستلزمات الكمبيوتر، وعام.
- إضافة وتعديل وحذف الأصناف مع حد أدنى للمخزون.
- سحب الأصناف مع إدخال **اسم الصنف وكوده** والتحقق من تطابقهما.
- الطلبيات والأصناف المطلوبة والسحب المرتبط بالطلبية.
- استمارات الهيئة: وارد، صرف، سجل الحركات، وحذف الأصناف.
- إهلاك الأجهزة وسجل الإهلاك.
- التقارير وتصدير CSV.
- إدارة المستخدمين وكلمات المرور والأدوار.
- واجهة متجاوبة مع الهاتف وسطح المكتب.

## البنية

```text
.
├── frontend/
│   ├── index.html
│   └── assets/
│       ├── css/styles.css
│       └── js/app.js
├── server/
│   ├── __main__.py      # تشغيل الخادم من متغيرات البيئة
│   ├── main.py          # تطبيق FastAPI والمسارات
│   ├── database.py      # SQLite والترحيل والتهيئة
│   ├── services.py      # منطق المخزن والطلبيات والتقارير
│   ├── security.py      # كلمات المرور والجلسات
│   ├── constants.py     # التصنيفات والحالات
│   └── config.py        # إعدادات البيئة
├── deploy/
│   ├── nginx.conf
│   └── warehouse.service
├── data/                # قاعدة البيانات (غير مرفوعة إلى Git)
├── Dockerfile
├── docker-compose.yml
├── requirements-web.txt
├── .env.example
└── README.md
```

## التشغيل المحلي

المتطلب: Python 3.10 أو أحدث.

### Windows

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-web.txt
Copy-Item .env.example .env
```

عدّل `.env` وغيّر `ADMIN_PASSWORD`، ثم شغّل:

```powershell
python -m server
```

### Linux / macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-web.txt
cp .env.example .env
python -m server
```

افتح `http://localhost:8000`.

بيانات الدخول الأولية تكون من `ADMIN_USERNAME` و`ADMIN_PASSWORD` في `.env`. القيمة الافتراضية في `.env.example` هي `admin` مع كلمة مرور يجب تغييرها.

## الإعدادات

| المتغير | الافتراضي | الوصف |
|---|---|---|
| `APP_TITLE` | نظام إدارة مخزن المعمل | اسم التطبيق |
| `WAREHOUSE_HOST` | `0.0.0.0` | عنوان الاستماع |
| `WAREHOUSE_PORT` | `8000` | منفذ التطبيق |
| `FORWARDED_ALLOW_IPS` | `127.0.0.1` | الوكلاء الموثوقون لترويسات `X-Forwarded-*` |
| `WAREHOUSE_DB_PATH` | `data/warehouse.sqlite3` | مسار قاعدة SQLite |
| `OFFLINE_DB_PATH` | `data/offline.db` | مصدر الترحيل القديم |
| `MIGRATE_OFFLINE_DB` | `1` | تفعيل الترحيل عند أول تشغيل |
| `ADMIN_USERNAME` | `admin` | اسم المدير الأولي |
| `ADMIN_PASSWORD` | `admin123` | كلمة مرور المدير الأولية، وغيّرها في `.env` |
| `SESSION_DAYS` | `14` | مدة الجلسة بالأيام |
| `COOKIE_NAME` | `warehouse_session` | اسم ملف الجلسة |
| `COOKIE_SECURE` | `0` | اجعله `1` عند استخدام HTTPS |
| `COOKIE_SAMESITE` | `lax` | سياسة SameSite |
| `TRUSTED_ORIGINS` | فارغ | نطاقات مسموحة عند فصل الواجهة |

ملاحظات:

- في الإنتاج استخدم مساراً مطلقاً لقاعدة البيانات، مثل `/var/lib/warehouse/warehouse.sqlite3`.
- لا ترفع `.env` أو قاعدة البيانات إلى Git.
- عند تشغيل الواجهة والخادم على نطاقين مختلفين، أضف نطاق الواجهة إلى `TRUSTED_ORIGINS` واستخدم `COOKIE_SECURE=1` و`COOKIE_SAMESITE=none`.
- شغّل نسخة خادم واحدة مع SQLite. لا تستخدم عدة replicas على نفس ملف قاعدة البيانات.

## الترحيل من التطبيق القديم

1. ضع نسخة قاعدة التطبيق القديم في `data/offline.db`.
2. تأكد أن `MIGRATE_OFFLINE_DB=1`.
3. احذف `data/warehouse.sqlite3` إن كان موجوداً من محاولة سابقة قبل الترحيل.
4. شغّل الخادم مرة واحدة. يتم إنشاء الجداول ونقل المستخدمين والأصناف والطلبيات والحركات والإعدادات.
5. يتم ضبط كلمة مرور المدير على قيمة `ADMIN_PASSWORD` أثناء الترحيل.
6. تحقق من الأرصدة والحركات قبل إيقاف التطبيق القديم.

بعد نجاح الترحيل يمكن ضبط `MIGRATE_OFFLINE_DB=0`، مع الاحتفاظ بنسخة من `offline.db` للرجوع إليها.

## النشر باستخدام Docker

```bash
cp .env.example .env
# عدّل .env وغيّر ADMIN_PASSWORD
docker compose up -d --build
docker compose logs -f warehouse
```

- المنفذ الافتراضي: `8000`.
- قاعدة البيانات محفوظة في volume باسم `warehouse_data`.
- للترحيل الأولي، فعّل السطر الخاص بـ `./data/offline.db` في `docker-compose.yml`.
- فحص الصحة: `http://SERVER_IP:8000/api/health`.
- أوقف الخدمة باستخدام `docker compose down` مع إبقاء الـ volume.

لتغيير المنفذ الخارجي:

```bash
WAREHOUSE_PORT=8080 docker compose up -d
```

## النشر على خادم Linux مع systemd وNginx

### 1. تجهيز التطبيق

```bash
sudo useradd --system --create-home --shell /usr/sbin/nologin warehouse
sudo mkdir -p /opt/zeroo
sudo chown warehouse:warehouse /opt/zeroo
```

انسخ ملفات المشروع إلى `/opt/zeroo`، ثم:

```bash
cd /opt/zeroo
sudo -u warehouse python3 -m venv .venv
sudo -u warehouse .venv/bin/pip install -r requirements-web.txt
sudo -u warehouse cp .env.example .env
sudo -u warehouse mkdir -p data
sudo chmod 750 data
sudo -u warehouse nano .env
```

غيّر `ADMIN_PASSWORD`، واضبط `WAREHOUSE_DB_PATH=/opt/zeroo/data/warehouse.sqlite3` و`WAREHOUSE_HOST=127.0.0.1`، واجعل `COOKIE_SECURE=1` بعد تفعيل HTTPS.

### 2. خدمة systemd

```bash
sudo cp deploy/warehouse.service /etc/systemd/system/warehouse.service
sudo systemctl daemon-reload
sudo systemctl enable --now warehouse
sudo systemctl status warehouse
sudo journalctl -u warehouse -f
```

الخدمة تستمع على `127.0.0.1:8000` فقط، ويتولى Nginx الوصول الخارجي. إذا غيّرت `WAREHOUSE_PORT` فحدّث `proxy_pass` في `deploy/nginx.conf` بنفس المنفذ.

### 3. Nginx

```bash
sudo cp deploy/nginx.conf /etc/nginx/sites-available/warehouse
sudo ln -s /etc/nginx/sites-available/warehouse /etc/nginx/sites-enabled/warehouse
sudo nginx -t
sudo systemctl reload nginx
```

ثم فعّل HTTPS باستخدام Certbot أو شهادة الخادم، وبعدها غيّر `COOKIE_SECURE=1` وأعد تشغيل الخدمة:

```bash
sudo systemctl restart warehouse
```

### 4. الجدار الناري

اسمح فقط بالمنافذ المطلوبة، مثل:

```bash
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
```

لا تفتح المنفذ `8000` للإنترنت عند استخدام Nginx. وإن كان الخادم خلف موازن أحمال، اجعل `--forwarded-allow-ips` مطابقاً لعنوان الموازن بدلاً من `*`.

## النسخ الاحتياطي والتحديث

### نسخة احتياطية من SQLite

يفضل استخدام أمر SQLite بدلاً من نسخ الملف أثناء الكتابة:

```bash
sqlite3 data/warehouse.sqlite3 ".backup 'backups/warehouse-$(date +%F).sqlite3'"
```

أو أوقف الخدمة ثم انسخ الملف:

```bash
sudo systemctl stop warehouse
sudo cp /opt/zeroo/data/warehouse.sqlite3 /var/backups/warehouse-$(date +%F).sqlite3
sudo systemctl start warehouse
```

### تحديث التطبيق

```bash
cd /opt/zeroo
sudo -u warehouse .venv/bin/pip install -r requirements-web.txt
sudo systemctl restart warehouse
```

اختبر `/api/health` بعد كل تحديث.

## واجهات API

كل المسارات تحت `/api`:

- `GET /api/health` فحص الصحة.
- `GET /api/meta` التصنيفات والحالات.
- `POST /api/auth/login`، `POST /api/auth/logout`، `GET /api/auth/me`.
- `GET/POST /api/products`، `GET/PUT/DELETE /api/products/{code}`.
- `POST /api/products/{code}/decommission` و`GET /api/decommissioned`.
- `POST/GET /api/withdrawals` و`DELETE /api/withdrawals/{id}`.
- `GET/POST /api/orders` وإدارة عناصر الطلبية وحالتها.
- `GET /api/authority` مع مسارات الوارد والصرف والحذف.
- `GET /api/reports/summary` و`movements` و`withdrawals` و`low-stock` و`export.csv`.
- `/api/users` لإدارة المستخدمين، للمدير فقط.

الطلبات المعدلة `POST/PUT/PATCH/DELETE` يجب أن تحمل الترويسة:

```text
X-Requested-With: XMLHttpRequest
```

مثال فحص سريع:

```bash
curl http://localhost:8000/api/health
```

## الاختبار

```bash
python -m compileall -q server
node --check frontend/assets/js/app.js
```

فحص يدوي مختصر:

1. سجّل الدخول.
2. أضف صنفاً وعدّله.
3. اسحب كمية بإدخال الاسم والكود معاً.
4. أنشئ طلبية وأضف صنفاً واسحب منه.
5. استلم واستخدم استمارة هيئة.
6. أهلك جهازاً وراجع السجل.
7. صدّر تقرير CSV.
8. أضف مستخدماً وغيّر كلمة مروره.

## التطبيق القديم

الملفات القديمة `app.py` و`core/` و`views/` و`.streamlit/` بقيت في المشروع كمرجع، لكن التطبيق الجديد لا يحتاجها. لتشغيل النسخة القديمة:

```bash
pip install -r requirements.txt
streamlit run app.py
```

النسخة القديمة تعمل على `http://localhost:8501` وتستخدم Google Sheets. لا تشارك `.streamlit/secrets.toml` أو مفاتيح Google، ولا تستخدمها في التطبيق الجديد.

## ملاحظات أمنية

- غيّر `ADMIN_PASSWORD` قبل أول تشغيل في الإنتاج.
- استخدم HTTPS وفعّل `COOKIE_SECURE=1`.
- اجعل صلاحيات مجلد `data` محدودة لمستخدم الخدمة فقط.
- لا تشغّل عدة نسخ من الخادم على نفس قاعدة SQLite.
- احتفظ بنسخ احتياطية دورية من قاعدة البيانات.
- راجع المستخدمين والأدوار بانتظام.
