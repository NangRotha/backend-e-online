from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from .database import init_db
from .config import settings as app_settings
from .routers import auth, products, orders, discounts, settings, admin, ws, categories, slides, users, chat, alerts, payments
from .storage import ensure_upload_dir
from .email_sender import email_status

# បង្កើតតារាងទាំងអស់ក្នុង PostgreSQL ប្រសិនបើមិនទាន់មាន (រួមទាំង Migration)
init_db()

# ព្រមានបើ Email (OTP) មិនទាន់កំណត់ — ពេលនោះ OTP នឹងបង្ហាញក្នុង Dev Mode តែប៉ុណ្ណោះ
_email_cfg = email_status()
if not _email_cfg["configured"]:
    print(
        "⚠️  Email (OTP) NOT configured — SMTP_USER/SMTP_PASSWORD missing.\n"
        "    OTP emails will NOT be sent; codes show in dev mode instead.\n"
        "    Add SMTP_* env vars (Gmail/Brevo/SendGrid) to fix."
    )

app = FastAPI(title="E-commerce API")

# CORS សម្រាប់អនុញ្ញាតឱ្យ Frontend (React Vite) ភ្ជាប់មក
# - Dev localhost តែងតែអនុញ្ញាតដោយស្វ័យប្រវត្តិ
# - Production frontends (Vercel) ត្រូវបានបញ្ចូលដោយផ្ទាល់នៅទីនេះ
# - អាចបន្ថែម Origin បន្ថែមទៀតតាមរយៈ CORS_ORIGINS ក្នុង Environment (ញែកដោយសញ្ញាក្បៀស)
_DEV_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:5174",
    "http://localhost:5175",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:5174",
    "http://127.0.0.1:5175",
]
_PRODUCTION_ORIGINS = [
    "https://frontend-user-e-online.vercel.app",
    "https://frontend-admin-e-online.vercel.app",
]
# បញ្ជី Origin ទាំងអស់ដែលអនុញ្ញាត (Dev + Production + CORS_ORIGINS ពី Environment)
_CORS_ORIGINS = [
    *_DEV_ORIGINS,
    *_PRODUCTION_ORIGINS,
    *app_settings.cors_origins_list,
]
_cors_regex = (app_settings.CORS_ORIGIN_REGEX or "").strip()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    # Regex ជាជម្រើស — សម្រាប់ Vercel Preview URL ដែលផ្លាស់ប្តូររាល់ពេល Deploy
    **({"allow_origin_regex": _cors_regex} if _cors_regex else {}),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# បម្រើរូបភាពដែល Upload ពីកុំព្យូទ័រ (/uploads/...)
# ប្រើ directory ដែលអាចសរសេរបាន (UPLOAD_DIR បើអាច បើអត់ -> backend/uploads/)
# check_dir=False -> កុំ crash បើ directory នៅមិនទាន់មាន
_EFFECTIVE_UPLOAD_DIR = ensure_upload_dir()
app.mount(
    "/uploads",
    StaticFiles(directory=_EFFECTIVE_UPLOAD_DIR, check_dir=False),
    name="uploads",
)

# ចុះឈ្មោះ Routers
app.include_router(auth.router)
app.include_router(products.router)
app.include_router(orders.router)
app.include_router(discounts.router)
app.include_router(settings.router)
app.include_router(admin.router)
app.include_router(ws.router)
app.include_router(categories.router)
app.include_router(slides.router)
app.include_router(users.router)
app.include_router(chat.router)
app.include_router(alerts.router)
app.include_router(payments.router)

@app.get("/")
def read_root():
    return {"message": "E-commerce Backend is running!"}

@app.get("/health")
def health_check():
    """សម្រាប់ Render Health Check (Render ហៅ endpoint នេះរៀងរាល់ពេល)"""
    return {"status": "ok"}


# ============================================================
# Deployment Diagnostics — បង្ហាញស្ថានភាព Environment ពេល Startup
# មើលបន្ទាត់ទាំងនេះក្នុង Render -> Service -> Logs
# ============================================================
def _deploy_diagnostics():
    from .database import IS_SQLITE, safe_database_url
    from .email_sender import email_status
    from .routers.payments import payment_configured
    from .storage import UPLOAD_DIR, cloudinary_configured, uploadthing_configured

    on_render = app_settings.RENDER.lower() == "true"
    warnings = []

    print("─" * 64, flush=True)
    print(
        f"🚀 Environment : {'Render (production)' if on_render else 'Local / other'}",
        flush=True,
    )
    print(
        f"   Database   : {'SQLite' if IS_SQLITE else 'PostgreSQL'} "
        f"(DB_ENGINE={app_settings.db_engine}) → {safe_database_url()}",
        flush=True,
    )
    if IS_SQLITE:
        print(f"   SQLite Path: {app_settings.sqlite_file_path}", flush=True)

    # ⚠️ DB_ENGINE=postgres តែគ្មាន DATABASE_URL → បាន Fallback ទៅ SQLite
    if app_settings.db_engine == "postgres" and not (
        app_settings.clean_database_url or app_settings.clean_database_url_internal
    ):
        warnings.append(
            "DB_ENGINE=postgres ប៉ុន្តែគ្មាន DATABASE_URL ត្រឹមត្រូវ — ប្រព័ន្ធបានប្តូរទៅ SQLite វិញ"
        )

    # ⚠️ Env Var Database ដែលមានតម្លៃគំរូ (ឧ. dpg-xxxx-a) -> មិនគិត
    warnings.extend(app_settings.database_warnings)

    # ⚠️ SQLite លើ Render ត្រូវការ Persistent Disk មិនដូច្នេះទិន្នន័យនឹងបាត់
    if on_render and IS_SQLITE:
        path = app_settings.sqlite_file_path
        if path.startswith("/var/data"):
            print(
                "   Storage DB : ✅ SQLITE_PATH ស្ថិតលើ Persistent Disk (/var/data)",
                flush=True,
            )
        else:
            warnings.append(
                "SQLite លើ Render គ្មាន Persistent Disk → ទិន្នន័យនឹងបាត់ពេល Redeploy! "
                "សូមកំណត់ SQLITE_PATH=/var/data/ecommerce.db រួចបន្ថែម Persistent Disk "
                "(ឬប្រើ DB_ENGINE=postgres + DATABASE_URL)"
            )

    if uploadthing_configured():
        print("   Storage    : ✅ UploadThing (CDN អចិន្ត្រៃយ៍)", flush=True)
    elif cloudinary_configured():
        print("   Storage    : ✅ Cloudinary (CDN អចិន្ត្រៃយ៍)", flush=True)
    else:
        print(f"   Storage    : ⚠️  Local Disk → {UPLOAD_DIR}", flush=True)
        if on_render:
            warnings.append(
                "គ្មាន UploadThing/Cloudinary → រូបភាព/វីដេអូ Upload នឹងបាត់ពេល Redeploy "
                "(កំណត់ UPLOADTHING_TOKEN ឬ UPLOAD_DIR=/var/data/uploads + Disk)"
            )

    email = email_status()
    if email["configured"]:
        print(
            f"   Email      : ✅ {email['method']} → {email['sender']}",
            flush=True,
        )
    else:
        print(
            "   Email      : ⚠️  not configured (receipt email នឹងមិនផ្ញើ)",
            flush=True,
        )

    print(
        f"   KHQR/ABA   : {'✅ enabled' if payment_configured() else '⚠️  not configured (ខ្វះ KHQRCC keys)'}",
        flush=True,
    )
    print(
        f"   CORS       : {len(_CORS_ORIGINS)} origin(s)"
        f"{' + regex' if _cors_regex else ''}",
        flush=True,
    )

    # ⚠️ SECRET_KEY Default = JWT អាចក្លែងបាន
    if app_settings.SECRET_KEY == "your-secret-key-change-this":
        if on_render:
            warnings.append(
                "SECRET_KEY កំពុងប្រើតម្លៃ Default — សូមកំណត់ SECRET_KEY ថ្មីក្នុង "
                "Render → Environment (មិនដូច្នេះ JWT អាចក្លែងបាន)"
            )
        else:
            print("   SECRET_KEY : ⚠️  default value (ok for local dev)", flush=True)

    for w in warnings:
        print(f"⚠️  WARNING: {w}", flush=True)
    print("─" * 64, flush=True)


_deploy_diagnostics()