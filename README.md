# Backend — E-commerce API (FastAPI)

Backend API សម្រាប់ E-commerce app (Storefront + Admin Panel) ដែលអាច Deploy
លើ **Render** (Web Service + PostgreSQL)។

## បច្ចេកវិទ្យា

- **FastAPI** + **Uvicorn** (WebSocket real-time ផងដែរ)
- **SQLAlchemy** + **SQLite** (Local) ឬ **PostgreSQL** (Render Postgres)
- JWT Auth (Admin), KHQR / ABA Pay, DeepSeek AI Chat, UploadThing/Cloudinary
- **SQLite + PostgreSQL ទាំងពីរ** — Migration រត់ស្វ័យប្រវត្តិ ដំណើរការលើទាំងពីរ

---

## Database — SQLite ឬ PostgreSQL?

Backend ជ្រើសរើស Database ដោយស្វ័យប្រវត្តិ (មិនចាំបាច់កែកូដ)៖

| លក្ខខណ្ឌ | Database ដែលប្រើ |
| --- | --- |
| `DB_ENGINE=sqlite` | **SQLite** (`SQLITE_PATH` ឬ `backend/ecommerce.db`) — បង្ខំ |
| `DB_ENGINE=postgres` | PostgreSQL (`DATABASE_URL_INTERNAL` នៅលើ Render បើមាន បើអត់ → `DATABASE_URL`) |
| `DB_ENGINE=auto` (Default) + `RENDER=true` + `DATABASE_URL_INTERNAL` | PostgreSQL (Internal URL) |
| `DB_ENGINE=auto` + មាន `DATABASE_URL` | តាម URL នោះ (Postgres ឬ SQLite) |
| `DB_ENGINE=auto` + គ្មាន URL | **SQLite** → `backend/ecommerce.db` (បង្កើតស្វ័យប្រវត្តិ) |

### ប្រើ SQLite (សាមញ្ញបំផុត — សម្រាប់ Local)

```bash
cd backend-e-online
# ទុក DATABASE_URL ទទេ ក្នុង .env (ឬគ្មាន .env ក៏បាន)
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

> ⚠️ **លើ Render** ឯកសារ SQLite នឹងបាត់ពេល Redeploy/Restart ព្រោះ Disk ជា
> Ephemeral។ បើចង់ប្រើ SQLite លើ Render ត្រូវបន្ថែម **Persistent Disk**
> រួចកំណត់ `SQLITE_PATH=/var/data/ecommerce.db` និង `UPLOAD_DIR=/var/data/uploads`។
> បើមិនចង់បាត់ទិន្នន័យ សូមប្រើ PostgreSQL (`DATABASE_URL`) ដូចពីមុន។

### 🔄 ផ្លាស់ Production ពី PostgreSQL → SQLite (ដោយមិនបាត់ទិន្នន័យ)

> ⚠️ **សំខាន់បំផុត:** Render មិនរក្សាឯកសារ SQLite ទេ បើគ្មាន **Persistent Disk**។
> Free plan មិនគាំទ្រ Disk → ត្រូវប្រើ Plan ដែលមាន Disk (ឧ. Starter)។
> បើគ្មាន Disk នោះ **ទិន្នន័យនឹងបាត់រាល់ពេល Redeploy/Restart**។

១) **Export ទិន្នន័យពី Production (Postgres) ជាមុន** — ត្រូវការគណនី Admin៖

```bash
cd backend-e-online
.venv/bin/python scripts/backup_restore.py export \
    --url https://backend-e-online.onrender.com \
    --email <admin-email> --password '<admin-password>' \
    --out backup.json
```

២) **Import ចូល SQLite ក្នុងម៉ាស៊ីនរបស់អ្នក** (ដើម្បីពិនិត្យជាមុន)៖

```bash
DB_ENGINE=sqlite .venv/bin/python scripts/backup_restore.py import --file backup.json --truncate
.venv/bin/python create_admin.py <admin-email> --password '<new-password>' --reset
```

៣) **លើ Render** — Service → Settings បន្ថែម **Disk**៖
`Name: data` · `Mount Path: /var/data` · `Size: 1 GB`

៤) **លើ Render** — Environment កំណត់៖

```
DB_ENGINE=sqlite
SQLITE_PATH=/var/data/ecommerce.db
UPLOAD_DIR=/var/data/uploads
DATABASE_URL=            ← ទុកទទេ (ឬលុបចោល)
DATABASE_URL_INTERNAL=   ← ទុកទទេ (ឬលុបចោល)
```

> បើទុក `DATABASE_URL` នៅ ត្រូវដាក់ `DB_ENGINE=sqlite` ដើម្បីបង្ខំឱ្យប្រើ SQLite។

៥) **Seed ទិន្នន័យចូល SQLite លើ Render** — មាន ២ វិធី៖
- **វិធី A (ងាយ):** upload `ecommerce.db` ដែល Import ក្នុងម៉ាស៊ីនទៅ Disk តាម Render Shell៖
  ```bash
  # ក្នុង Render Shell
  mkdir -p /var/data && cat > /var/data/ecommerce.db   # paste SQLite file ជា base64
  ```
- **វិធី B (ណែនាំ):** បន្ថែម `backup.json` ទៅ Disk រួច Import តាម Render Shell៖
  ```bash
  DB_ENGINE=sqlite SQLITE_PATH=/var/data/ecommerce.db \
      python scripts/backup_restore.py import --file backup.json --truncate
  python create_admin.py <admin-email> --password '<new>' --reset
  ```

៦) **ពិនិត្យ** — Logs ត្រូវបង្ហាញ៖
```
   Database   : SQLite (DB_ENGINE=sqlite) → sqlite:////var/data/ecommerce.db
   Storage DB : ✅ SQLITE_PATH ស្ថិតលើ Persistent Disk (/var/data)
```

> 💡 បើចង់ត្រឡប់ទៅ PostgreSQL វិញ៖ `DB_ENGINE=postgres` រួច
> `.venv/bin/python scripts/backup_restore.py import --file backup.json` (ឬប្រើ `from-postgres`)

### 🧰 Backup / Restore / Migration Script

`scripts/backup_restore.py` — ឧបករណ៍ផ្លាស់ទិន្នន័យរវាង Database ដោយមិនបាត់ទិន្នន័យ៖

| Command | ការងារ |
| --- | --- |
| `export --url … --email … --password … --out backup.json` | ទាញទិន្នន័យទាំងអស់ចេញពី API (ត្រូវការ Admin) |
| `import --file backup.json --truncate` | បញ្ចូលទិន្នន័យចូល DB បច្ចុប្បន្ន (តាម `DB_ENGINE`) |
| `from-postgres` (ប្រើ `SOURCE_DATABASE_URL`) | ចម្លងផ្ទាល់ Postgres → DB បច្ចុប្បន្ន (រួមទាំង Password) |

API endpoint សម្រាប់ Export: `GET /api/admin/export` (Admin only, លាក់ Password)။

### Migration ស្វ័យប្រវត្តិ

ពេល Backend ចាប់ផ្តើម `init_db()` នឹង៖
1. បង្កើតតារាងដែលខ្វះ (`create_all`)
2. បន្ថែម Column/Index ថ្មីៗដែលមានក្នុង Model តែគ្មានក្នុង Database ចាស់
   (ដំណើរការទាំង SQLite និង PostgreSQL — មិនប្រើ `IF NOT EXISTS` ព្រោះ SQLite មិនគាំទ្រ)

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

## Deploy លើ Render

### ✅ Checklist មុន Deploy (សំខាន់)

| ចំណុច | ហេតុអ្វី |
| --- | --- |
| **Build Command** = `pip install -r requirements.txt` | `uvicorn[standard]` ត្រូវបានដំឡើង → មាន `websockets` សម្រាប់ Real-time |
| **Start Command** = `uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 1 --proxy-headers --forwarded-allow-ips='*'` | `--workers 1` ព្រោះ WebSocket manager ស្ថិតក្នុង Memory · `--proxy-headers` ព្រោះ Render ជា Reverse Proxy |
| **Health Check Path** = `/health` | Render ដឹងថា Service ដំណើរការ |
| **Python Version** = `3.12.10` (Manual Service) ឬ `pythonVersion: 3.12.8` (Blueprint) | Render default ថ្មីជាងនេះ → បណ្ណាល័យខ្លះគ្មាន wheel |
| **Environment** = Production | បើក `DATABASE_URL`, `SECRET_KEY`, `CORS_ORIGINS`, `KHQRCC_*`, `FRONTEND_URL`, `BREVO_API_KEY`, `UPLOADTHING_TOKEN` |
| **មិន Scale ច្រើន Instance** | WebSocket real-time ត្រូវការ Single Instance (បើចង់ Scale ត្រូវប្រើ Redis Pub/Sub) |

### 🔍 ពិនិត្យក្រោយ Deploy (Service → Logs)

ពេល Backend ចាប់ផ្តើម វានឹងបោះពុម្ព **Deployment Diagnostics** ដូចនេះ៖

```
🗄️  Database (PostgreSQL): postgresql://***@dpg-xxxx-a/DBNAME
────────────────────────────────────────────────────────────────
🚀 Environment : Render (production)
   Database   : PostgreSQL → postgresql://***@dpg-xxxx-a/DBNAME
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

1. Push code ទៅ GitHub (ត្រូវមាន `render.yaml` និង `requirements.txt` នៅក្នុង folder នេះ)
2. Render Dashboard → **New → Blueprint**
3. ជ្រើស repo នេះ → Render បង្កើត Web Service ដោយស្វ័យប្រវត្តិ
4. ចូល **Service → Environment** ហើយបំពេញអថេរទាំងនេះ (ដែលមាន `sync: false` ក្នុង `render.yaml`)៖

| Env Var | តម្រូវ? | ឧទាហរណ៍ / កន្លែងយក |
| --- | --- | --- |
| `DATABASE_URL` | ✅ ត្រូវ | `postgresql://USER:PASS@dpg-xxxx-a.singapore-postgres.render.com/DBNAME` (Postgres → Connect → **External**) |
| `DATABASE_URL_INTERNAL` | ⭐ ណែនាំ | `postgresql://USER:PASS@dpg-xxxx-a/DBNAME` (Postgres → Connect → **Internal**) — ប្រើជាមុនពេល `RENDER=true` |
| `SECRET_KEY` | ✅ ត្រូវ | Render បង្កើតស្វ័យប្រវត្តិ (Blueprint) ឬ string វែងសុវត្ថិភាព |
| `CORS_ORIGINS` | ✅ ត្រូវ | `https://frontend-user-e-online.vercel.app,https://frontend-admin-e-online.vercel.app` |
| `CORS_ORIGIN_REGEX` | ជម្រើស | Regex សម្រាប់ Vercel Preview URL ឧ. `^https://frontend-(user\|admin)-e-online.*\.vercel\.app$` |
| `KHQRCC_PROFILE_ID` | ✅ សម្រាប់ KHQR | https://khqr.cc → ABA Pay Gateway → API Keys |
| `KHQRCC_SECRET_KEY` | ✅ សម្រាប់ KHQR | ដូចខាងលើ |
| `FRONTEND_URL` | ✅ សម្រាប់ KHQR | `https://frontend-user-e-online.vercel.app` (success_url ពេលបង់ប្រាក់ចប់) |
| `BREVO_API_KEY` | ⭐ ណែនាំ (Receipt) | `xkeysib-...` ពី Brevo → SMTP & API → **API Keys** (ដំណើរការលើ Render free tier) |
| `SMTP_HOST` | បើមិនប្រើ Brevo API | `smtp-relay.brevo.com` (ឬ `smtp.gmail.com`) |
| `SMTP_PORT` | | `587` |
| `SMTP_USER` | | `xxxx@smtp-brevo.com` |
| `SMTP_PASSWORD` | | SMTP key (`xsmtpsib-...`) — **ទុក IP restriction ទទេ** |
| `SMTP_FROM` | | អ៊ីមែលដែលបាន **Verify** ក្នុង Brevo |
| `SMTP_FROM_NAME` | | `E-Online` |
| `SMTP_USE_SSL` | | `False` (587) ឬ `True` (465) |
| `UPLOADTHING_TOKEN` | ⭐ ណែនាំ (រូបភាព) | https://uploadthing.com/dashboard → API Keys |
| `CLOUDINARY_CLOUD_NAME` / `CLOUDINARY_API_KEY` / `CLOUDINARY_API_SECRET` | ជម្រើស | Cloudinary Dashboard → API Keys (ជំនួស UploadThing) |
| `DEEPSEEK_API_KEY` | ជម្រើស (AI Chat) | https://platform.deepseek.com |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_BOT_USERNAME` | ជម្រើស | @BotFather (Storefront លែងប្រើ Telegram login ទៀតទេ) |
| `UPLOAD_DIR` | ជម្រើស | ទុកទទេ (backend/uploads) ឬ `/var/data/uploads` បើមាន Persistent Disk |
| `PYTHON_VERSION` | ✅ បើបង្កើត Manual | `3.12.10` (Blueprint កំណត់រួចក្នុង `render.yaml`) |
| `CORS_ORIGIN_REGEX` | ជម្រើស | Regex សម្រាប់ Vercel Preview (ឧ. `^https://frontend-.*\.vercel\.app$`) |
| `SQLITE_PATH` | ជម្រើស | ប្រើតែពេលជ្រើស SQLite លើ Render (ត្រូវការ Persistent Disk) |
| `OTP_EXPIRE_MINUTES` | ជម្រើស | `10` |

> **Render កំណត់ដោយស្វ័យប្រវត្តិ (មិនត្រូវបំពេញដោយដៃ)៖**
> `RENDER=true`, `PORT`, និង `DATABASE_URL*` បើភ្ជាប់ Postgres តាម Blueprint។
>
> ⚠️ **ព័ត៌មាន Bakong Wallet** (Company Name · Bakong Wallet ID · Display Name ·
> Currency · KHR rate) **មិនមែន Env Var ទេ** — វារក្សាទុកក្នុង Database
> (`site_settings`) ហើយកំណត់តាម **Admin Panel → Settings → Bakong Wallet / KHQR payment**។

> **RENDER** ត្រូវបាន Render កំណត់ដោយស្វ័យប្រវត្តិ (`RENDER=true`) —
> code នឹងប្រើ `DATABASE_URL_INTERNAL` ដោយស្វ័យប្រវត្តិ។

> **Python Version:** Render default ថ្មីគឺ **3.14** (មិនទាន់មាន wheel សម្រាប់
> បណ្ណាល័យខ្លះទេ) — ដូច្នេះ repo នេះប្រើ **Python 3.12**។
> - Manual Web Service៖ ដាក់ Env Var `PYTHON_VERSION=3.12.10` (ឬ Render អាន
>   `backend/.python-version` ដែលផ្ទុក `3.12`)
> - Blueprint៖ ប្រើ `pythonVersion: 3.12.8` ក្នុង `render.yaml` (បានកំណត់រួចហើយ)

### វិធីទី 2 — Web Service (Manual)

1. Render Dashboard → **New → Web Service** → ជ្រើស repo
2. **Build Command:** `pip install -r requirements.txt`
3. **Start Command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   (ឬ Render អាន `Procfile` ដោយស្វ័យប្រវត្តិ)
4. **Health Check Path:** `/health`
5. បំពេញ Env Vars ដូចតារាងខាងលើ

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

