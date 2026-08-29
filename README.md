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
| `UPLOAD_DIR`          | ទុកទទេ ឬ `/var/data/uploads` (បើមាន Disk)  |

> **RENDER** ត្រូវបាន Render កំណត់ដោយស្វ័យប្រវត្តិ (`RENDER=true`) —
> code នឹងប្រើ `DATABASE_URL_INTERNAL` ដោយស្វ័យប្រវត្តិ។

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

---

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

