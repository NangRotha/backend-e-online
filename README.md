# Backend — E-commerce API (FastAPI)

Backend API សម្រាប់ E-commerce app (Storefront + Admin Panel) ដែលអាច Deploy
លើ **Render** (Web Service + PostgreSQL)។

## បច្ចេកវិទ្យា

- **FastAPI** + **Uvicorn** (WebSocket real-time ផងដែរ)
- **SQLAlchemy** + **PostgreSQL** (Render Postgres)
- JWT Auth, OTP Email (SMTP), Telegram Login, DeepSeek AI Chat

---

## Deploy លើ Render

### វិធីទី 1 — Blueprint (render.yaml) ស្វ័យប្រវត្តិ

1. Push code ទៅ GitHub (ត្រូវមាន `render.yaml` និង `requirements.txt` នៅក្នុង folder នេះ)
2. Render Dashboard → **New → Blueprint**
3. ជ្រើស repo នេះ → Render បង្កើត Web Service ដោយស្វ័យប្រវត្តិ
4. ចូល **Service → Environment** ហើយបំពេញអថេរទាំងនេះ (ដែលមាន `sync: false`)៖

| Env Var               | ឧទាហរណ៍                                    |
| --------------------- | --------------------------------------------- |
| `DATABASE_URL`        | `postgresql://USER:PASS@HOST...singapore-postgres.render.com/DB` |
| `DATABASE_URL_INTERNAL` | `postgresql://USER:PASS@dpg-xxx-a/DB` (ពី DB → Connect → Internal) |
| `SECRET_KEY`          | បង្កើតដោយ Render ដោយស្វ័យប្រវត្តិ        |
| `CORS_ORIGINS`        | `https://your-shop.vercel.app,https://your-admin.vercel.app` |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USER` / `SMTP_PASSWORD` | Gmail/Provider SMTP |
| `SMTP_FROM` / `SMTP_FROM_NAME` | `you@gmail.com` / `E-Commerce Store` |
| `SMTP_USE_SSL`        | `False` (587) ឬ `True` (465)                  |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_BOT_USERNAME` | ពី @BotFather              |
| `DEEPSEEK_API_KEY`    | ពី https://platform.deepseek.com              |
| `UPLOADTHING_TOKEN`   | ពី https://uploadthing.com/dashboard → API Keys |
| `UPLOAD_DIR`          | ទុកទទេ ឬ `/var/data/uploads` (បើមាន Disk)  |

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

