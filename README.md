# Backend — E-commerce API (FastAPI)

Backend API សម្រាប់ E-commerce app (Storefront + Admin Panel) ដែលអាច Deploy
លើ **Render** (Web Service + **SQLite**)។

## បច្ចេកវិទ្យា

- **FastAPI** + **Uvicorn** (WebSocket real-time ផងដែរ)
- **SQLAlchemy** + **SQLite** (Database តែមួយ — គ្មាន Driver បន្ថែម)
- **🐳 Docker** (`Dockerfile` + `docker-compose.yml`) — Python 3.12-slim
- JWT Auth (Admin), KHQR / ABA Pay, DeepSeek AI Chat, UploadThing/Cloudinary
- **SQLite តែមួយប៉ុណ្ណោះ** — Migration រត់ស្វ័យប្រវត្តិ (Column/Index ថ្មី)

---

## Database — 🟢 SQLite តែមួយប៉ុណ្ណោះ

Backend នេះប្រើ **SQLite** ជា Database តែមួយ (គ្មាន PostgreSQL ទៀតទេ)។

| Env Var | លទ្ធផល |
| --- | --- |
| `SQLITE_PATH` ទទេ **(Default)** | ឯកសារ `backend-e-online/ecommerce.db` (បង្កើតស្វ័យប្រវត្តិ) |
| `SQLITE_PATH=/var/data/ecommerce.db` | ប្រើឯកសារនៅទីតាំងកំណត់ (ឧ. Render + Persistent Disk) |

> ⚠️ បើថតក្នុង `SQLITE_PATH` សរសេរមិនបាន (ឧ. Free plan គ្មាន Disk → `/var/data` មិនមាន)
> នោះ Backend នឹង **Fallback ទៅ `backend-e-online/ecommerce.db`** ដោយស្វ័យប្រវត្តិ (App មិន Crash)។
> គ្មាន Env Var `DATABASE_URL` / `DATABASE_URL_INTERNAL` / `DB_ENGINE` ទៀតទេ។

### ប្រើ SQLite ក្នុងម៉ាស៊ីន (Local — គ្មាន Config)

```bash
cd backend-e-online
# ទុក SQLITE_PATH ទទេ (ឬគ្មាន .env ក៏បាន) -> ប្រើ backend-e-online/ecommerce.db ស្វ័យប្រវត្តិ
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --reload
```

បង្កើតគណនី Admin (Storefront គ្មាន Sign Up ទៀតទេ)៖

```bash
.venv/bin/python create_admin.py admin@example.com --password 'admin12345' --name 'Store Admin'
```

- ឯកសារ Database: `backend-e-online/ecommerce.db` (gitignored)
- ចង់ប្តូរទីតាំង → `SQLITE_PATH=/var/data/ecommerce.db`
- ចង់ Reset Database → លុបឯកសារ `.db` ចោល រួច Restart (តារាងនឹងបង្កើតឡើងវិញ)

### 🐳 Docker — រត់ក្នុងម៉ាស៊ីន (ឬ Deploy លើ Render)

Repo នេះមាន **`Dockerfile`** (Python 3.12-slim) និង **`docker-compose.yml`**
ដែលកំណត់ SQLite + Uploads នៅ **`/var/data`** ខាងក្នុង Container។

**ជម្រើស A — Docker Compose (ណែនាំសម្រាប់ Local)**

```bash
cd backend-e-online
cp .env.example .env            # (ជាជម្រើស) បំពេញ SECRET_KEY / ADMIN_* / KHQRCC_* ...
docker compose up --build -d    # -> http://localhost:8000
docker compose logs -f backend  # មើល Log
docker compose down             # បិទ
```

- ទិន្នន័យ (SQLite + uploads) ស្ថិតក្នុងថត **`data/`** ខាងក្រៅ Container
  → `docker compose down`/Build ឡើងវិញ ក៏ទិន្នន័យមិនបាត់ ✓
- ពិនិត្យ៖ `curl http://localhost:8000/health`
- ពាក្យបញ្ជាក្នុង Container (Admin / Backup)៖
  ```bash
  docker compose exec backend python create_admin.py admin@example.com --password 'admin12345'
  docker compose exec backend python scripts/backup_restore.py --help
  ```

**ជម្រើស B — Docker ធម្មតា**

```bash
docker build -t backend-e-online .
docker run -d --name backend -p 8000:8000 -v backend_data:/var/data \
    -e ADMIN_EMAIL=admin@example.com -e ADMIN_PASSWORD='admin12345' \
    backend-e-online
```

**Env Var ក្នុង Container** (កំណត់រួចក្នុង `Dockerfile`)

| Env Var | Default | ចំណាំ |
| --- | --- | --- |
| `SQLITE_PATH` | `/var/data/ecommerce.db` | Volume ត្រូវ mount នៅ `/var/data` |
| `UPLOAD_DIR` | `/var/data/uploads` | ដូចខាងលើ (ឬប្រើ `UPLOADTHING_TOKEN`) |
| `PORT` | `8000` | Render កំណត់ដោយស្វ័យប្រវត្តិ |

> ⚠️ `.env` មិនចូលក្នុង Image ទេ (មើល `.dockerignore`) — បើចង់ផ្ញើ Env ចូល Container
> ត្រូវប្រើ `--env-file .env`, `-e KEY=value`, ឬ `env_file:` ក្នុង `docker-compose.yml`។
>
> 💡 Image មិនរាប់បញ្ចូល `*.db` / `uploads/` / `.venv` / `.env` → តូចលឿន (≈ 88 MB)
> និងគ្មាន Secret នៅក្នុង Image។

### 🖥️ ប្រើ SQLite លើ Render (Production)

> ⚠️ **ត្រូវការ Persistent Disk** មិនដូច្នេះ **ទិន្នន័យនឹងបាត់រាល់ពេល Redeploy/Restart**។
> Free plan មិនគាំទ្រ Disk → ត្រូវប្រើ Plan ដែលមាន Disk (Starter+) ឬ Seed ទិន្នន័យឡើងវិញ។
>
> 🆓 **លើ Free plan (គ្មាន Disk)**៖ ទុក `SQLITE_PATH` ទទេ ដើម្បីឱ្យ Backend បង្កើត DB
> ក្នុង Service Folder (`/opt/render/project/src/ecommerce.db`) — App ដំណើរការធម្មតា
> ប៉ុន្តែ **ទិន្នន័យបាត់ពេល Redeploy/Restart** (ល្មមសម្រាប់សាកល្បងប៉ុណ្ណោះ)។
> បើចង់ទិន្នន័យមិនបាត់ → ប្រើ **OPTION B** (Starter + Persistent Disk + `SQLITE_PATH`)។

**១) បន្ថែម Disk** — Render → Service → **Disks** → *Add Disk*៖
`Name: data` · `Mount Path: /var/data` · `Size: 1 GB`

**២) Environment** (កំណត់រួចក្នុង `render.yaml`)៖

```
SQLITE_PATH=/var/data/ecommerce.db
UPLOAD_DIR=/var/data/uploads
```

**៣) បើមានឯកសារ SQLite ចាស់** (ឧ. ពីកុំព្យូទ័ររបស់អ្នក) — មើលផ្នែក
*Backup / Restore* ខាងក្រោម។ បើគ្មានទេ SQLite នឹងទទេ (ត្រូវបង្កើតផលិតផល/ការកំណត់ថ្មី)។

**៤) ពិនិត្យ** — Logs ត្រូវបង្ហាញ៖

```
🗄️  Database (SQLite): sqlite:////var/data/ecommerce.db
   Database   : SQLite → sqlite:////var/data/ecommerce.db
   SQLite Path: /var/data/ecommerce.db
   Storage DB : ✅ SQLITE_PATH ស្ថិតលើ Persistent Disk (/var/data)
```

> បើឃើញ `⚠️ WARNING: SQLite លើ Render គ្មាន Persistent Disk` មានន័យថាមិនទាន់បានបន្ថែម Disk។

### 📍 តើ SQLite file (ទិន្នន័យ) នៅឯណា?

| បរិស្ថាន | ទីតាំងឯកសារ | ចំណាំ |
| --- | --- | --- |
| **Local (កុំព្យូទ័ររបស់អ្នក)** | `backend-e-online/ecommerce.db` | ស្ថិតក្នុង Folder `backend-e-online/` ដូច `README.md` |
| **Render + Persistent Disk** | `/var/data/ecommerce.db` | ✅ ទិន្នន័យមិនបាត់ពេល Redeploy |
| **Render គ្មាន Disk (free plan)** | `/opt/render/project/src/ecommerce.db` | ⚠️ Ephemeral — បាត់ពេល Redeploy/Restart |
| រូបភាព/វីដេអូ Upload | `backend-e-online/uploads/` ឬ `/var/data/uploads` | ឬលើ UploadThing/Cloudinary (បើកំណត់) |

> ❗ **មូលហេតុដែលអ្នកមិនឃើញឯកសារ `ecommerce.db` ក្នុង GitHub/Render Dashboard:**
> វាត្រូវបាន **`.gitignore`** ចោលដោយចេតនា (`*.db`) ព្រោះជាទិន្នន័យ Production —
> មិនត្រូវ Push ទៅ Git ទេ។ ដូច្នេះវានៅតែមាន **ក្នុងម៉ាស៊ីន/Server** ប៉ុណ្ណោះ។
> Render ក៏គ្មាន File Browser ដែរ → ត្រូវមើលតាម **Shell** ឬតាម `curl /health`។

**ពិនិត្យពីចម្ងាយ (ងាយបំផុត) — ដោយមិនបាច់ចូល Shell៖**

```bash
curl https://backend-e-online.onrender.com/health
```

```json
{
  "status": "ok",
  "engine": "sqlite",
  "file": "/var/data/ecommerce.db",
  "on_persistent_disk": true,
  "counts": { "products": 12, "orders": 5, "users": 3, "site_settings": 6 },
  "storage": "uploadthing"
}
```

- `file` = ទីតាំងឯកសារ Database ជាក់ស្តែង
- `on_persistent_disk: true` = ស្ថិតលើ Disk (ទិន្នន័យមិនបាត់)
- `counts` = បើគ្រប់ចំនួន `0` មានន័យថា **Database ទទេ** (ត្រូវ Migration ឬបង្កើតទិន្នន័យថ្មី)

**មើលក្នុង Render Shell** (Service → Shell)៖

```bash
ls -la /var/data                  # បើមាន Disk -> ឃើញ ecommerce.db
du -h /var/data/ecommerce.db      # ទំហំឯកសារ
python -c "import sqlite3;c=sqlite3.connect('/var/data/ecommerce.db');\
print([r[0] for r in c.execute(\"select name from sqlite_master where type='table'\")]);\
print('products =', c.execute('select count(*) from products').fetchone()[0])"
```

**មើលក្នុងម៉ាស៊ីនរបស់អ្នក**៖

```bash
ls -la backend-e-online/ecommerce.db
sqlite3 backend-e-online/ecommerce.db ".tables"        # បើមាន sqlite3
# ឬ (គ្មាន sqlite3 ក៏បាន):
python -c "import sqlite3;c=sqlite3.connect('backend-e-online/ecommerce.db');print(c.execute('select count(*) from products').fetchone())"
```

> 💡 បើអ្នកចង់ "ឃើញ" ឯកសារនេះក្នុង Finder សូមបើក Folder `backend-e-online/`
> (ឯកសារ `ecommerce.db` មិនមែនជា Hidden file ទេ — វានឹងបង្ហាញធម្មតា)។

### 🔄 Backup / ផ្លាស់ទិន្នន័យ (SQLite → SQLite ដោយមិនបាត់ទិន្នន័យ)

> ⚠️ **សំខាន់បំផុត:** Render មិនរក្សាឯកសារ SQLite ទេ បើគ្មាន **Persistent Disk**។
> Free plan មិនគាំទ្រ Disk → ត្រូវប្រើ Plan ដែលមាន Disk (ឧ. Starter)។
> បើគ្មាន Disk នោះ **ទិន្នន័យនឹងបាត់រាល់ពេល Redeploy/Restart**។

១) **Export ទិន្នន័យពី Backend ដែលកំពុងដំណើរការ** — ត្រូវការគណនី Admin៖

```bash
cd backend-e-online
.venv/bin/python scripts/backup_restore.py export \
    --url https://backend-e-online.onrender.com \
    --email <admin-email> --password '<admin-password>' \
    --out backup.json
```

២) **Import ចូល SQLite ក្នុងម៉ាស៊ីនរបស់អ្នក** (ដើម្បីពិនិត្យជាមុន)៖

```bash
.venv/bin/python scripts/backup_restore.py import --file backup.json --truncate
.venv/bin/python create_admin.py <admin-email> --password '<new-password>' --reset
```

៣) **លើ Render** — Service → Settings បន្ថែម **Disk**៖
`Name: data` · `Mount Path: /var/data` · `Size: 1 GB`

៤) **លើ Render** — Environment កំណត់៖

```
SQLITE_PATH=/var/data/ecommerce.db
UPLOAD_DIR=/var/data/uploads
```

៥) **Seed ទិន្នន័យចូល SQLite លើ Render** — មាន ២ វិធី៖
- **វិធី A (ងាយ):** upload `ecommerce.db` ដែល Import ក្នុងម៉ាស៊ីនទៅ Disk តាម Render Shell៖
  ```bash
  # ក្នុង Render Shell
  mkdir -p /var/data && cat > /var/data/ecommerce.db   # paste SQLite file ជា base64
  ```
- **វិធី B (ណែនាំ):** បន្ថែម `backup.json` ទៅ Disk រួច Import តាម Render Shell៖
  ```bash
  SQLITE_PATH=/var/data/ecommerce.db \
      python scripts/backup_restore.py import --file backup.json --truncate
  python create_admin.py <admin-email> --password '<new>' --reset
  ```

៦) **ពិនិត្យ** — Logs ត្រូវបង្ហាញ៖
```
   Database   : SQLite → sqlite:////var/data/ecommerce.db
   Storage DB : ✅ SQLITE_PATH ស្ថិតលើ Persistent Disk (/var/data)
```

> 💡 ចង់ចម្លងឯកសារ SQLite ទាំងមូល (រួមទាំង Password) ចូល DB បច្ចុប្បន្ន៖
> `SOURCE_SQLITE_PATH=/path/to/old.db .venv/bin/python scripts/backup_restore.py copy-source --truncate`

### 🧰 Backup / Restore / Migration Script

`scripts/backup_restore.py` — ឧបករណ៍ Backup / Restore ទិន្នន័យ (SQLite) ដោយមិនបាត់ទិន្នន័យ៖

| Command | ការងារ |
| --- | --- |
| `export --url … --email … --password … --out backup.json` | ទាញទិន្នន័យទាំងអស់ចេញពី API (ត្រូវការ Admin) |
| `import --file backup.json --truncate` | បញ្ចូលទិន្នន័យចូល DB បច្ចុប្បន្ន (តាម `SQLITE_PATH`) |
| `copy-source --source /path/old.db` (ឬ `SOURCE_SQLITE_PATH`) | ចម្លងផ្ទាល់ SQLite → SQLite (រួមទាំង Password) |

API endpoint សម្រាប់ Export: `GET /api/admin/export` (Admin only, លាក់ Password)။

### Migration ស្វ័យប្រវត្តិ

ពេល Backend ចាប់ផ្តើម `init_db()` នឹង៖
1. បង្កើតតារាងដែលខ្វះ (`create_all`)
2. បន្ថែម Column/Index ថ្មីៗដែលមានក្នុង Model តែគ្មានក្នុង Database ចាស់
   (ដំណើរការលើ SQLite — មិនប្រើ `IF NOT EXISTS` ព្រោះ SQLite មិនគាំទ្រ)

ក្នុង Log នឹងឃើញ៖ `🗄️ Database (SQLite): sqlite:///...` និង
`✅ Migration: បន្ថែម products.video_url` (បើមានការបន្ថែម)។

---

## Product Video (Admin Upload)

Admin អាច Upload **វីដេអូ** ទៅឱ្យផលិតផលបាន (ក្រៅពីរូបភាព)៖

- **Admin Panel → Products → Add/Edit Product → "Product video"**
- ទ្រទ្រង់៖ `.mp4`, `.webm`, `.mov`, `.ogg`, `.m4v` (កំណត់ក្នុង
  `ALLOWED_VIDEO_EXTENSIONS` → `app/storage.py`)
- API: `POST /api/admin/upload?kind=video` (រូបភាពប្រើ `kind=image` ជា Default)
- រក្សាទុកក្នុង Column `products.video_url`
- **Storefront** បង្ហាញវីដេអូក្នុង Gallery នៃទំព័រផលិតផល (មាន Play button +
  Video badge លើ Product Card)

ឯកសារត្រូវបានផ្ទុកទៅ **UploadThing** (ឬ Cloudinary) បើបានកំណត់ បើអត់ →
Local Disk `backend/uploads/`។ ពេលលុប/ប្តូរវីដេអូ ឯកសារចាស់ត្រូវបានលុបផង។


---

## 💳 ABA Pay / KHQRcc — QR + Managed Checkout (v2)

Env vars ដែលត្រូវការ៖

| Env Var | កន្លែងយក |
| --- | --- |
| `KHQRCC_PROFILE_ID` | khqr.cc → Gateway → **API Security Essentials → Profile ID** |
| `KHQRCC_SECRET_KEY` | khqr.cc → **Secret Key** (ចុច RE-GENERATE បើសង្ស័យថាលេចធ្លាយ) |
| `FRONTEND_URL` | `https://frontend-user-e-online.vercel.app` (សម្រាប់ `success_url` / `cancel_url`) |

### ដំណើរការ (ពេលអតិថិជន Checkout)

1. Backend ហៅ **QR API** (`/{profile}/payment-gateway/v1/payments/qr-api-khqrcc`)
   ដើម្បីទាញ **EMV KHQR string** (+ រូបភាព បើ Gateway ផ្តល់មក)
   - hash = `sha1(secret + transaction_id + amount + success_url + remark)`
2. បើ Gateway **មិនផ្តល់រូបភាព** → Backend **បង្កើតរូប QR ខ្លួនឯង** ពី EMV string
   (`app/qr.py` ប្រើ `qrcode[pil]`) រួចរក្សាទុកក្នុង UploadThing/Cloudinary/Local
3. Backend បង្កើត **Managed Checkout v2 URL** ខ្លួនឯង៖
   `https://checkout.khqr.cc/payment/khqrcc/{profile_id}?transaction_id=…&amount=…&success_url=…&remark=…&hash=…&cancel_url=…&items=<base64>`
   → បើ Gateway ជាប់/Timeout ក៏ Link នេះនៅតែប្រើបាន ✓
4. Storefront (Order Success)៖
   - បើមានរូប QR → បង្ហាញរូប + ឈ្មោះអ្នកទទួល + Bakong ID
   - បើអត់មានរូប → បង្ហាញប៊ូតុង **“Pay with ABA Pay / KHQRcc”**
     (បើកតាម **KHQRcc Checkout Plugin** `KhqrPayway.openCheckout`, បើ Plugin ផ្ទុកមិនបាន → បើក Tab ថ្មី)
     ព្រមទាំង “Open checkout” និង “Copy payment link”
5. **Auto-detect**៖ ទំព័រ Poll `/api/payments/status` រៀងរាល់ 3 វិនាទី →
   ពេល `success` → `/api/payments/confirm` → Order = `paid` + ផ្ញើ Receipt
   (Webhook `POST /api/payments/callback` ក៏មានដែរ សម្រាប់ Server-to-Server)

### 🔧 Setup ក្នុង khqr.cc Dashboard (ធ្វើម្តង)

| កន្លែងក្នុង Dashboard | តម្លៃដែលត្រូវដាក់ |
| --- | --- |
| **API Security Essentials → Profile ID** | ដាក់ក្នុង Render Env: `KHQRCC_PROFILE_ID` |
| **API Security Essentials → Secret Key** | ដាក់ក្នុង Render Env: `KHQRCC_SECRET_KEY` (ចុច RE-GENERATE បើលេចធ្លាយ) |
| **Global Webhook Endpoint** | `https://backend-e-online.onrender.com/api/payments/callback` |
| **Custom Callback Payload** | ទុកទទេ (Default) ឬប្រើ placeholders៖ `{{transaction_id}}, {{amount}}, {{status}}, {{req_time}}, {{hash}}` |
| **Bakong Wallet → Company Name / Display Name / Currency** | កំណត់ក្នុង **Admin Panel → Settings → Bakong Wallet** (រក្សាទុកក្នុង DB) |
| **Bakong Wallet → Bakong Wallet ID** | លេខគណនី Bakong ផ្ទាល់ខ្លួន (ឧ. `yourname@acleda`) — បង្ហាញលើផ្ទៃបង់ប្រាក់ |

> ✅ **Webhook = សំខាន់បំផុត** — បើទុកទទេ ការបង់ប្រាក់នឹងបញ្ជាក់បានតែពេលអតិថិជន
> នៅលើទំព័រ Order Success (Poll 3 វិនាទី)។ បើដាក់ Webhook នោះ Order នឹងប្តូរទៅ
> `paid` ទោះអតិថិជនបិទ Browser ក៏ដោយ។

### ✅ ការបញ្ជាក់ការបង់ប្រាក់ (៣ ស្រទាប់)

1. **Redirect Params** — Gateway Redirect ទៅ `success_url` ជាមួយ `success_hash`,
   `success_time`, `success_amount` → Storefront ហៅ `/api/payments/confirm` ភ្លាម
   (Server ផ្ទៀងផ្ទាត់ម្តងទៀតជាមួយ Gateway — មិនជឿតែ Query String)
2. **Polling** — រៀងរាល់ 3 វិនាទី រហូត 3 នាទី (តាមឯកសារ) បន្ទាប់មកឈប់ និងបង្ហាញ
   “QR ផុតកំណត់” + ប៊ូតុង **Check payment now** (ចុចរួចចាប់ផ្តើម Poll ឡើងវិញ)
3. **Webhook** — `POST /api/payments/callback` ពិនិត្យ hash
   `sha256(secret + req_time + transaction_id + amount + "SUCCESS")` → `paid` + ផ្ញើ Receipt

### Checkout URLs (មាន ២ ប្រភេទ)

| Field | តម្លៃ | ប្រើសម្រាប់ |
| --- | --- | --- |
| `payment_url` | `https://khqr.cc/api/payment/requestv2/{profile}?…` | **KHQRcc Checkout Plugin** (`KhqrPayway.openCheckout`) + Redirect |
| `payment_checkout_url` | `https://checkout.khqr.cc/payment/khqrcc/{profile}?…` | បើកក្នុង Tab ថ្មី / ចម្លងជា Link |

ទាំងពីរមាន `hash = sha1(secret + transaction_id + amount + success_url + remark)`
ព្រមទាំង `cancel_url` / `items` (base64) / `custom_fields` (base64)។



| Endpoint | ការងារ |
| --- | --- |
| `GET /api/payments/config` | បើក/បិទ + ព័ត៌មាន Bakong Wallet (Company/Display/Bakong ID/Currency) |
| `POST /api/payments/create` | បង្កើត QR (Admin/Test) |
| `POST /api/payments/status` | ពិនិត្យស្ថានភាព (Verify V2) |
| `POST /api/payments/confirm` | ផ្ទៀងផ្ទាត់ + ប្តូរ Order → paid |
| `POST /api/payments/callback` | Webhook ពី Gateway (hash sha256) |

### ⚠️ ដោះស្រាយបញ្ហា QR

| រោគសញ្ញា | មូលហេតុ / ដំណោះស្រាយ |
| --- | --- |
| ទំព័រ Order Success មិនបង្ហាញ QR | ធ្លាប់កើតព្រោះ Gateway ត្រឡប់តែ EMV string → **បានជួសជុល** ដោយបង្កើតរូប QR ខ្លួនឯង |
| គ្មាន QR ទាល់តែសោះ (Gateway Timeout) | ឥឡូវបង្ហាញប៊ូតុង ABA Pay Checkout — អតិថិជននៅតែបង់បាត់បាន |
| `khqr.cc` មិនអាចភ្ជាប់ (Timeout) | បណ្តាញ/ISP បិទ — សាកល្បងបើក `https://khqr.cc` ក្នុង Browser; លើ Render ធម្មតាភ្ជាប់បាន |
| ការបង់ប្រាក់មិន Auto-confirm | ពិនិត្យ `KHQRCC_SECRET_KEY` (ត្រូវតែត្រូវនឹង Profile) និង Webhook URL ក្នុង khqr.cc Dashboard |



### ✅ Checklist មុន Deploy (សំខាន់)

| ចំណុច | ហេតុអ្វី |
| --- | --- |
| **Runtime** = `docker` 🐳 | Render Build តាម `Dockerfile` — **មិនត្រូវការ** Build Command / Start Command ក្នុង Dashboard |
| **Dockerfile Path** = `./Dockerfile` | កំណត់រួចក្នុង `render.yaml` (`dockerfilePath`) |
| **Health Check Path** = `/health` | Render ដឹងថា Service ដំណើរការ (`render.yaml` + `HEALTHCHECK` ក្នុង Dockerfile) |
| **Python Version** = `3.12` (ក្នុង `Dockerfile`) | 🐳 Docker ជ្រើស Python ខ្លួនឯង → **មិនត្រូវការ `PYTHON_VERSION`** ទេ (បើប្រើ Runtime ធម្មតា ត្រូវពឹងលើ `.python-version`) |
| **Environment** = Production | បើក `SECRET_KEY`, `CORS_ORIGINS`, `KHQRCC_*`, `FRONTEND_URL`, `BREVO_API_KEY`, `UPLOADTHING_TOKEN` — 🚫 **មិនត្រូវការ `DATABASE_URL` ទៀតទេ** |
| **មិន Scale ច្រើន Instance** | WebSocket real-time ត្រូវការ Single Instance (បើចង់ Scale ត្រូវប្រើ Redis Pub/Sub) |
| **Admin ដំបូង** | ដាក់ `ADMIN_EMAIL` + `ADMIN_PASSWORD` — បង្កើតឱ្យស្វ័យប្រវត្តិពេល Startup (ចាំបាច់ព្រោះ Free គ្មាន Shell) |

### 🆓 Free Plan — អ្វីដែលខុសពី Plan បង់ (អានមុន Deploy)

| ចំណុច | លើ Free Plan | ដំណោះស្រាយក្នុង Repo នេះ |
| --- | --- | --- |
| **Persistent Disk** | ❌ គ្មាន → data នៅក្នុង Container (Ephemeral) | 🐳 Docker ប្រើ `/var/data` ក្នុង Container — បាត់ពេល Redeploy · រូបភាពប្រើ `UPLOADTHING_TOKEN` · ចង់ទិន្នន័យមិនបាត់ → **OPTION B** (Disk mount នៅ `/var/data`) |
| **Shell / SSH** | ❌ គ្មាន → រត់ `create_admin.py` មិនបាន | **Bootstrap Admin**: `ADMIN_EMAIL` + `ADMIN_PASSWORD` (បង្កើតពេល Startup) |
| **One-off Job** | ❌ មិនគាំទ្រ | បំពេញទិន្នន័យតាម Admin Panel (ឬប្តូរទៅ Plan បង់) |
| **SMTP port 587/465** | ❌ បិទ (Outbound Blocked) | ប្រើ `BREVO_API_KEY` (HTTP API លើ port 443) — កូដជ្រើស Brevo ជាមុនស្វ័យប្រវត្តិ |
| **Spin down ពេលទំនេរ** | ⚠️ បន្ទាប់ពី ~15 នាទី → Request ដំបូងយឺត (Cold Start) | ធម្មតាទេ — Upgrade បើចង់ឱ្យលឿនជាប់ |
| **Region** | ✅ គ្រប់ Region | `region: singapore` (ជិតកម្ពុជាជាងគេ — `render.yaml` កំណត់រួច) |

> 💡 ចង់បានទិន្នន័យ **មិនបាត់** លើ Render៖ ត្រូវប្រើ Plan ដែលមាន **Persistent Disk**
> (Starter ឡើងទៅ) រួចកំណត់ `SQLITE_PATH=/var/data/ecommerce.db` (OPTION B)។
> រូបភាព/វីដេអូ៖ ប្រើ `UPLOADTHING_TOKEN` (CDN) ដើម្បីកុំបាត់ពេល Redeploy។

### 🔍 ពិនិត្យក្រោយ Deploy (Service → Logs)

ពេល Backend ចាប់ផ្តើម វានឹងបោះពុម្ព **Deployment Diagnostics** ដូចនេះ៖

```
🗄️  Database (SQLite): sqlite:////var/data/ecommerce.db
────────────────────────────────────────────────────────────────
🚀 Environment : Render (production)
   Database   : SQLite → sqlite:////var/data/ecommerce.db
   SQLite Path: /var/data/ecommerce.db
   Storage    : ✅ UploadThing (CDN អចិន្ត្រៃយ៍)
   Email      : ✅ brevo_api → you@email.com
   KHQR/ABA   : ✅ enabled
   CORS       : 8 origin(s)
────────────────────────────────────────────────────────────────
```

បើមានបញ្ហា វានឹងបង្ហាញ `⚠️ WARNING:` ឧទាហរណ៍៖
- SQLite លើ Render គ្មាន Persistent Disk → ទិន្នន័យនឹងបាត់
- គ្មាន UploadThing/Cloudinary → រូបភាពនឹងបាត់
- `SECRET_KEY` នៅតែជា Default → JWT អាចក្លែងបាន

បន្ទាប់មកពិនិត្យ៖

```bash
curl https://<your-service>.onrender.com/health          # {"status":"ok"}
curl https://<your-service>.onrender.com/api/payments/config   # enabled: true
curl -X POST https://<your-service>.onrender.com/api/orders/checkout \
  -H 'Content-Type: application/json' -d '{}'            # 400 (មិនមែន 401) = Guest checkout ដំណើរការ
```

### វិធីទី 1 — Blueprint (render.yaml) ស្វ័យប្រវត្តិ

1. Push code ទៅ GitHub (ត្រូវមាន `Dockerfile` · `render.yaml` · `requirements.txt` នៅ root)
2. Render Dashboard → **New → Blueprint**
3. ជ្រើស repo នេះ → Render បង្កើត Web Service (**Runtime: Docker** 🐳) ដោយស្វ័យប្រវត្តិ
4. ចូល **Service → Environment** ហើយបំពេញអថេរទាំងនេះ (ដែលមាន `sync: false` ក្នុង `render.yaml`)៖

| Env Var | តម្រូវ? | ឧទាហរណ៍ / កន្លែងយក |
| --- | --- | --- |
| 🚫 `DATABASE_URL` / `DATABASE_URL_INTERNAL` | មិនប្រើទៀតទេ | Backend ប្រើ **SQLite** ជានិច្ច — សូមលុប Env Var ទាំងនេះចេញពី Render (បើមាន) |
| `SECRET_KEY` | ✅ ត្រូវ | Render បង្កើតស្វ័យប្រវត្តិ (Blueprint) ឬ string វែងសុវត្ថិភាព |
| `CORS_ORIGINS` | ✅ ត្រូវ | `https://frontend-user-e-online.vercel.app,https://frontend-admin-e-online.vercel.app` (ដាក់រួចក្នុង `render.yaml`) |
| `CORS_ORIGIN_REGEX` | ជម្រើស | Regex សម្រាប់ Vercel Preview URL ឧ. `^https://frontend-(user\|admin)-e-online.*\.vercel\.app$` (ដាក់រួចក្នុង `render.yaml`) |
| `ADMIN_EMAIL` | ⭐ ណែនាំ (Free plan) | អ៊ីមែល Admin ដំបូង — បង្កើតដោយស្វ័យប្រវត្តិពេល Startup ឧ. `admin@mystore.com` |
| `ADMIN_PASSWORD` | ⭐ ណែនាំ (Free plan) | ពាក្យសម្ងាត់ Admin (Source of Truth — កំណត់ឡើងវិញរាល់ Startup បើខុស) |
| `ADMIN_NAME` | ជម្រើស | ឈ្មោះបង្ហាញរបស់ Admin (Default: `Admin`) |
| `KHQRCC_PROFILE_ID` | ✅ សម្រាប់ KHQR | https://khqr.cc → ABA Pay Gateway → API Keys |
| `KHQRCC_SECRET_KEY` | ✅ សម្រាប់ KHQR | ដូចខាងលើ |
| `FRONTEND_URL` | ✅ សម្រាប់ KHQR | `https://frontend-user-e-online.vercel.app` (success_url ពេលបង់ប្រាក់ចប់) |
| `BREVO_API_KEY` | ⭐ ណែនាំ (Receipt) | `xkeysib-...` ពី Brevo → SMTP & API → **API Keys** (ដំណើរការលើ Render free tier) |
| `SMTP_FROM` | ⭐ ត្រូវការ (ទាំង Brevo) | អ៊ីមែលដែលបាន **Verify** ក្នុង Brevo — កូដប្រើវាជា "អ្នកផ្ញើ" |
| `SMTP_FROM_NAME` | ជម្រើស | `E-Online` |
| 🚫 `SMTP_HOST` / `SMTP_PORT` / `SMTP_USER` / `SMTP_PASSWORD` / `SMTP_USE_SSL` | **កុំដាក់លើ Free plan** | Render Free បិទ port 25/465/587 → ប្រើ `BREVO_API_KEY` ជំនួស (បើចង់ប្រើ SMTP ពិត ត្រូវការ Plan បង់) · ⚠️ កុំទុកតម្លៃទទេ — `SMTP_PORT`/`SMTP_USE_SSL` ទទេ = App Crash |
| `UPLOADTHING_TOKEN` | ⭐ ណែនាំ (រូបភាព) | https://uploadthing.com/dashboard → API Keys |
| `CLOUDINARY_CLOUD_NAME` / `CLOUDINARY_API_KEY` / `CLOUDINARY_API_SECRET` | ជម្រើស | Cloudinary Dashboard → API Keys (ជំនួស UploadThing) |
| `DEEPSEEK_API_KEY` | ជម្រើស (AI Chat) | https://platform.deepseek.com |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_BOT_USERNAME` | ជម្រើស | @BotFather (Storefront លែងប្រើ Telegram login ទៀតទេ) |
| `UPLOAD_DIR` | ជម្រើស | 🐳 Docker Default: `/var/data/uploads` (កំណត់ក្នុង Dockerfile) · Local ធម្មតា: `backend/uploads` |
| `PYTHON_VERSION` | 🚫 មិនត្រូវការ (Docker) | 🐳 Python កំណត់ក្នុង `Dockerfile` (`python:3.12-slim`) — ប្រើតែពេល Runtime = Python ធម្មតា (`3.12.10`) |
| `CORS_ORIGIN_REGEX` | ជម្រើស | Regex សម្រាប់ Vercel Preview (ឧ. `^https://frontend-.*\.vercel\.app$`) |
| `SQLITE_PATH` | ជម្រើស | 🐳 Docker Default: `/var/data/ecommerce.db` (កំណត់ក្នុង Dockerfile) · Local ធម្មតា: ទុកទទេ → `backend-e-online/ecommerce.db` |
| `OTP_EXPIRE_MINUTES` | ជម្រើស | `10` |

> **Render កំណត់ដោយស្វ័យប្រវត្តិ (មិនត្រូវបំពេញដោយដៃ)៖**
> `RENDER=true` និង `PORT` (គ្មាន `DATABASE_URL` ទៀតទេ)។
>
> ⚠️ **ព័ត៌មាន Bakong Wallet** (Company Name · Bakong Wallet ID · Display Name ·
> Currency · KHR rate) **មិនមែន Env Var ទេ** — វារក្សាទុកក្នុង Database
> (`site_settings`) ហើយកំណត់តាម **Admin Panel → Settings → Bakong Wallet / KHQR payment**។

> **RENDER** ត្រូវបាន Render កំណត់ដោយស្វ័យប្រវត្តិ (`RENDER=true`) —
> code ប្រើវាសម្រាប់ Startup Diagnostics និងការព្រមានអំពី Persistent Disk។

> **Python Version (🐳 Docker):** កំណត់ក្នុង `Dockerfile` = **`python:3.12-slim`**
> → **មិនត្រូវការ Env Var `PYTHON_VERSION`** ទេ (Blueprint ក៏មិនត្រូវការដែរ)
> ⚠️ **កុំដាក់ `pythonVersion:`** ក្នុង `render.yaml` — មិនមែន Key ត្រឹមត្រូវទេ
> (Schema កំណត់ `additionalProperties: false`) → Blueprint នឹង Error ពេល Deploy
> 💡 បើប្រើ Runtime `python` ធម្មតា (មិនមែន Docker)៖ ដាក់ `.python-version` = `3.12`
> ឬ Env Var `PYTHON_VERSION=3.12.10` (ត្រូវជា version ពេញលេញ) — Render default ថ្មីជាងនេះមាន 3.14

### វិធីទី 2 — Web Service (Manual) 🐳 Docker

1. Render Dashboard → **New → Web Service** → ជ្រើស repo
2. **Language / Runtime:** **Docker** (ជ្រើស "Docker" មិនមែន Python)
3. **Dockerfile Path:** `./Dockerfile`
4. **Build / Start Command:** ទុកទទេ — Render ប្រើ `Dockerfile` (`CMD` + `HEALTHCHECK`)
5. **Health Check Path:** `/health`
6. **Docker Command:** ទុកទទេ (បើចង់ override សូមប្រើ
   `uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 1 --proxy-headers`)
7. បំពេញ Env Vars ដូចតារាងខាងលើ (មិនត្រូវការ `PYTHON_VERSION` / `DATABASE_URL`)
8. (ស្រេចចិត្ត) បន្ថែម **Persistent Disk** → Mount Path = `/var/data` (Plan Starter ឡើងទៅ)
   → SQLite + Uploads នឹងនៅក្នុង Disk ដោយស្វ័យប្រវត្តិ ✓

### ក្រោយ Deploy

- ពិនិត្យ API: `https://<your-service>.onrender.com/health` → `{"status": "ok"}`
- WebSocket real-time: `wss://<your-service>.onrender.com/ws/products`
- កុំ Scale ទៅច្រើន Instance (WebSocket manager ស្ថិតក្នុង Memory) —
  បើចង់ Scale ត្រូវប្រើ Redis Pub/Sub ជំនួស

### រូបភាព Upload (uploads/)

- Free/Starter plan: filesystem របស់ Render មិន Persistent — រូបនឹងបាត់ពេល Redeploy
- បើចង់រក្សារូបភាព៖
  1. Upgrade plan ដែលគាំទ្រ **Persistent Disk**
  2. Service → **Disks** → បង្កើត Disk (mount នៅ `/var/data/uploads`)
  3. ដាក់ Env Var `UPLOAD_DIR=/var/data/uploads`

### UploadThing (ណែនាំបំផុត) — ផ្ទុករូបភាព/វីដេអូ លើ CDN អចិន្ត្រៃយ៍

កូដនេះប្រើ **UploadThing** ដោយស្វ័យប្រវត្តិ បើបានកំណត់ Token៖

```bash
UPLOADTHING_TOKEN=eyJhcGlLZXkiOiJza19saXZlX2...
```

- **Create**: Upload → UploadThing CDN (URL អចិន្ត្រៃយ៍ `*.ufs.sh/f/...` / `utfs.io/f/...`)
- **Read**: Frontend បង្ហាញ URL ផ្ទាល់ពី CDN
- **Update**: លុបរូបចាស់ចេញពី UploadThing ពេលប្តូរទៅរូបថ្មី
- **Delete**: លុបរូបចេញពី UploadThing ពេលលុប Product / Slide / Alert / Profile
- បើអត់កំណត់ UploadThing -> បន្តប្រើ Cloudinary (បើកំណត់) -> Local Disk

យក Token ពី UploadThing Dashboard → **API Keys** (ប៊ូតុង Copy)។
ចំណាំ៖ UploadThing Free plan កំណត់ឯកសារ **4MB / សន្លឹក**។

### Cloudinary — ជម្រើសទី 2 សម្រាប់រក្សាទុករូបភាព/វីដេអូ អចិន្ត្រៃយ៍

កូដនេះប្រើ **Cloudinary** ដោយស្វ័យប្រវត្តិ បើមិនបានកំណត់ UploadThing តែបានកំណត់ credentials នេះ៖

```bash
CLOUDINARY_CLOUD_NAME=your-cloud-name
CLOUDINARY_API_KEY=your-api-key
CLOUDINARY_API_SECRET=your-api-secret
```

- **Create**: Upload → Cloudinary (URL អចិន្ត្រៃយ៍ `res.cloudinary.com/...`)
- **Read**: Frontend បង្ហាញ URL ផ្ទាល់ពី Cloudinary
- **Update**: លុបរូបចាស់ចេញពី Cloudinary ពេលប្តូរទៅរូបថ្មី
- **Delete**: លុបរូបចេញពី Cloudinary ពេលលុប Product / Slide / Alert / Profile

### OTP Email — ផ្ញើទៅអ៊ីមែលណាក៏បានក្នុងលោក (Global)

SMTP គ្រាន់តែជា **អ្នកផ្ញើ** (sender) — អ្នកទទួលអាចជា Gmail / Yahoo / Outlook /
Hotmail / Zoho / domain ផ្ទាល់ខ្លួន ក្នុងប្រទេសណាក៏បាន។ ប្តូរ provider ត្រឹមតែ
ប្តូរ env vars ខាងក្រោម (មិនបាច់កែកូដ)៖

| Provider   | `SMTP_HOST`            | Port | `SMTP_USE_SSL` | Free tier       | សម្គាល់ |
| ---------- | ---------------------- | ---- | -------------- | --------------- | ------- |
| Gmail      | `smtp.gmail.com`       | 587  | `False`        | 500 emails/day  | ត្រូវប្រើ App Password |
| **Brevo** (ណែនាំ) | `smtp-relay.brevo.com` | 587  | `False`        | 300 emails/day  | `SMTP_USER`=login, `SMTP_PASSWORD`=master password |
| SendGrid   | `smtp.sendgrid.net`    | 587  | `False`        | 100 emails/day  | API Key |
| Mailgun    | `smtp.mailgun.org`     | 587  | `False`        | 100 emails/day  | domain SMTP login |
| Zoho       | `smtp.zoho.com`        | 465  | `True`         | 5 users / 250/day | — |

ពិនិត្យលើ Production ថា Email បានបើក៖
```bash
curl https://<your-backend>.onrender.com/api/auth/email-config
# → {"configured":true,"provider":"smtp-relay.brevo.com","sender":"...","from_name":"E-Online","last_error":null}
```
បើ `configured:false` -> ដាក់ `SMTP_*` env vars លើ Render Dashboard ហើយ Redeploy។

### Troubleshooting Brevo
- `last_error` = `525 5.7.1 Unauthorized IP address` **ឬ** `401 ... unrecognised IP address ... authorised_ips`
  -> **Brevo កំពុងតែបើក IP authorization**។ ចូល
  **https://app.brevo.com/security/authorised_ips** ហើយ **បិទ (Disable)** IP authorization
  (ឬបន្ថែម IP របស់ Server/Local ទៅក្នុងបញ្ជី) — ព្រោះ Render ប្រើ IP ប្រែប្រួល។
- `last_error` = sender rejected / `554` -> **SMTP_FROM មិនទាន់ Verify ក្នុង Brevo**។
  Brevo Dashboard -> **Settings -> Senders & IPs -> Add a sender** -> បញ្ចូលអ៊ីមែល
  (ឧ. rothanang21@gmail.com) -> ចុចតំណក្នុងអ៊ីមែលដែល Brevo ផ្ញើមកបញ្ជាក់។
- Admin អាចផ្ញើ OTP សាកល្បង និងមើល error បានភ្លាមៗ៖
  ```bash
  curl -X POST https://<backend>/api/auth/test-email \
    -H "Authorization: Bearer <admin_token>" \
    -H "Content-Type: application/json" \
    -d '{"email":"you@gmail.com"}'
  ```
- បើអត់កំណត់ Cloudinary -> នឹងប្រើ Local Disk (`backend/uploads/`) ដូចពីមុន

យក Cloud Name / API Key / API Secret ពី Cloudinary Dashboard → **Settings → API Keys**

---

### ABA Pay / KHQRcc — Scan & Pay QR

អតិថិជនបង់ប្រាក់តាម **QR Code** (ABA Mobile / Bakong) ហើយ Order
ប្តូរទៅ **paid** ដោយស្វ័យប្រវត្តិ (auto-detection)។

```bash
KHQRCC_PROFILE_ID=your-profile-id
KHQRCC_SECRET_KEY=your-secret-key
FRONTEND_URL=https://your-shop.vercel.app
```

- **Checkout** → ហៅ `khqr.cc` QR API ដោយស្វ័យប្រវត្តិ យក QR Code បង្ហាញលើទំព័រ Order Success
- **Auto-payment** → Frontend poll `/api/payments/status` រៀងរាល់ 3 វិនាទី;
  ពេលឃើញ `success` -> ហៅ `/api/payments/confirm` -> Order = **paid**
- **Webhook** → `POST /api/payments/callback` (ស្វ័យប្រវត្តិ ពី khqr.cc) ពិនិត្យ hash ហើយ mark paid
- បើអត់កំណត់ Secret Key -> Checkout នៅតែដំណើរការ (mock URL) ដូចពីមុន

យក Profile ID / Secret Key ពី https://khqr.cc Dashboard → **ABA Pay Gateway → API Keys**

## អភិវឌ្ឍន៍លើ Local

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # បំពេញតម្លៃ
uvicorn app.main:app --reload
```

## អ្នកគ្រប់គ្រងដំបូង (Admin)

```bash
python create_admin.py your@email.com password
```

