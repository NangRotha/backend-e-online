# ============================================================
# Backend — E-commerce API (FastAPI + SQLite)
# ប្រើសម្រាប់ Deploy លើ Render (Docker runtime) ឬរត់ក្នុងម៉ាស៊ីនតាម Docker Compose
# ============================================================
# Python 3.12 (ដូច `.python-version` + README)
# 💡 Docker កំណត់ Python Version ដោយខ្លួនឯង -> មិនត្រូវការ Env Var PYTHON_VERSION ទេ
# 💡 គ្មាន PostgreSQL -> មិនត្រូវការ libpq / psycopg2 (Image តូច និង Build លឿន)
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8000 \
    SQLITE_PATH=/var/data/ecommerce.db \
    UPLOAD_DIR=/var/data/uploads

WORKDIR /app

# ca-certificates ចាំបាច់សម្រាប់ HTTPS (khqr.cc · Brevo · UploadThing)
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# 1) Requirements មុនគេ (Docker Cache — Build លឿនពេលកូដផ្លាស់ប្តូរ)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 2) កូដទាំងអស់ (មើល `.dockerignore` — គ្មាន .venv / .env / *.db)
COPY . .

# ថតសម្រាប់ SQLite + Uploads
# Docker: ដាក់ Volume នៅទីនេះដើម្បីកុំបាត់ទិន្នន័យ  ->  -v backend_data:/var/data
# Render: បន្ថែម Persistent Disk ដោយ mount នៅ /var/data
RUN mkdir -p /var/data/uploads

EXPOSE 8000

# Health Check ដូច Render (ប្រើ Python ព្រោះ Image គ្មាន curl)
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('PORT', '8000') + '/health', timeout=4)"

# --workers 1        : WebSocket manager ស្ថិតក្នុង Memory -> ត្រូវការ Single Instance
# --proxy-headers    : Render ជា Reverse Proxy (ត្រូវអាន X-Forwarded-*)
# --forwarded-allow-ips='*' : ទុកឱ្យ Proxy កំណត់ IP/Scheme ពិត
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --proxy-headers --forwarded-allow-ips='*'"]
