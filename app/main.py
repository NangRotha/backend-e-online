from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from .database import SessionLocal, init_db
from .config import settings as app_settings
from . import models
from .routers import auth, products, orders, discounts, settings, admin, ws, categories, slides, users, chat, alerts, payments
from .storage import ensure_upload_dir
from .email_sender import email_status


def _bootstrap_admin() -> None:
    """បង្កើត/ដំឡើង Admin ដំបូងដោយស្វ័យប្រវត្តិ ពី Env Var (`ADMIN_EMAIL`/`ADMIN_PASSWORD`)

    ចាំបាច់សម្រាប់ Host ដែល **គ្មាន Shell/SSH** (ឧ. Render Free Plan — រត់
    `create_admin.py` មិនបានទេ) ព្រោះបើគ្មាន Admin នោះចូល Admin Panel មិនបាន។

    ដំណើរការ **Idempotent** (សុវត្ថិភាព រត់រាល់ Startup)៖
      1. គ្មានគណនី -> បង្កើតថ្មី (role=admin, email_verified=True)
      2. មានគណនីតែ role=user -> ដំឡើងជា admin
      3. Password ក្នុង DB ខុសពី `ADMIN_PASSWORD` -> កំណត់តាម Env វិញ
    ⚠️ បើ `ADMIN_EMAIL` ឬ `ADMIN_PASSWORD` ទទេ -> រំលងទាំងស្រុង (មិនបង្កើត User)
    """
    from .auth import hash_password, verify_password

    email = (app_settings.ADMIN_EMAIL or "").strip().lower()
    password = app_settings.ADMIN_PASSWORD or ""
    if not email or not password:
        return

    # ពិនិត្យអ៊ីមែល — Login ប្រើ Pydantic `EmailStr` ដូច្នេះ Domain បម្រុង (.local/.test...)
    # នឹងត្រូវបដិសេធ (422) -> គ្មានប្រយោជន៍បង្កើត
    try:
        from email_validator import EmailNotValidError, validate_email as _validate

        _validate(email, check_deliverability=False)
    except EmailNotValidError as exc:
        print(
            f"⚠️  Admin bootstrap: ADMIN_EMAIL '{email}' មិនត្រឹមត្រូវ ({exc}) — រំលង",
            flush=True,
        )
        return
    except ImportError:
        pass

    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.email == email).first()

        if user is None:
            db.add(
                models.User(
                    name=(app_settings.ADMIN_NAME or "").strip() or "Admin",
                    email=email,
                    hashed_password=hash_password(password),
                    role="admin",
                    email_verified=True,  # Admin មិនត្រូវការ OTP
                )
            )
            db.commit()
            print(
                f"✅ Admin bootstrap: បង្កើត Admin '{email}' ដោយស្វ័យប្រវត្តិ",
                flush=True,
            )
            return

        changes = []
        if user.role != "admin":
            user.role = "admin"
            changes.append("role=admin")
        if not user.email_verified:
            user.email_verified = True
            changes.append("email_verified=True")

        # ពិនិត្យ Password — បើ Hash ខូច/មិនស្គាល់ (UnknownHashError) ក៏ត្រូវកំណត់ឡើងវិញ
        # ដែរ ព្រោះបើអត់ នោះ Admin នឹងចូលមិនបាន (ប៉ុន្តែមិនត្រូវឱ្យវា Crash ទេ)
        try:
            password_ok = verify_password(password, user.hashed_password or "")
        except Exception:  # noqa: BLE001
            password_ok = False
        if not password_ok:
            user.hashed_password = hash_password(password)
            changes.append("password=ADMIN_PASSWORD")

        if changes:
            db.commit()
            print(
                f"✅ Admin bootstrap: ធ្វើបច្ចុប្បន្នភាព '{email}' ({', '.join(changes)})",
                flush=True,
            )
        else:
            print(f"ℹ️  Admin bootstrap: '{email}' ជា Admin រួចហើយ", flush=True)
    except Exception as exc:  # noqa: BLE001
        print(f"⚠️  Admin bootstrap បរាជ័យ: {type(exc).__name__}: {exc}", flush=True)
    finally:
        db.close()


# បង្កើតតារាងទាំងអស់ក្នុង Database ប្រសិនបើមិនទាន់មាន (រួមទាំង Migration)
init_db()

# 👤 Bootstrap Admin ដំបូង (ដំណើរការតែពេលកំណត់ ADMIN_EMAIL + ADMIN_PASSWORD)
_bootstrap_admin()

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
    """Render Health Check + បង្ហាញទីតាំងទិន្នន័យ (SQLite file នៅឯណា?)

    មិនមាន Secret ទេ — គ្រាន់តែបង្ហាញថា Database engine អ្វី ឯកសារនៅឯណា
    និងចំនួនទិន្នន័យ ដើម្បីឱ្យអ្នកអាចពិនិត្យបានដោយ `curl /health`។
    """
    from .database import EFFECTIVE_DATABASE_URL

    path = EFFECTIVE_DATABASE_URL.replace("sqlite:///", "", 1)
    on_disk = path.startswith("/var/data")
    info = {
        "status": "ok",
        "engine": "sqlite",
        "url": EFFECTIVE_DATABASE_URL,
        "file": path,
        "on_persistent_disk": on_disk,
        "note": (
            "ឯកសារនេះស្ថិតលើ Persistent Disk (/var/data) ✓ ទិន្នន័យមិនបាត់ពេល Redeploy"
            if on_disk
            else "⚠️ ឯកសារនេះមិននៅលើ /var/data ទេ → បាត់ពេល Redeploy "
            "(ត្រូវការ Persistent Disk + SQLITE_PATH=/var/data/ecommerce.db)"
        ),
    }

    # ចំនួនទិន្នន័យ (ស្រាលបំផុត) — ដើម្បីដឹងថា Database ទទេ ឬមានទិន្នន័យ
    try:
        db = SessionLocal()
        try:
            info["counts"] = {
                "products": db.query(models.Product).count(),
                "categories": db.query(models.Category).count(),
                "orders": db.query(models.Order).count(),
                "users": db.query(models.User).count(),
                "site_settings": db.query(models.SiteSetting).count(),
            }
        finally:
            db.close()
    except Exception as exc:  # noqa: BLE001
        info["counts_error"] = f"{type(exc).__name__}"

    from .storage import cloudinary_configured, uploadthing_configured

    info["storage"] = (
        "uploadthing"
        if uploadthing_configured()
        else "cloudinary"
        if cloudinary_configured()
        else "local-disk"
    )
    return info


# ============================================================
# Deployment Diagnostics — បង្ហាញស្ថានភាព Environment ពេល Startup
# មើលបន្ទាត់ទាំងនេះក្នុង Render -> Service -> Logs
# ============================================================
def _deploy_diagnostics():
    from .database import EFFECTIVE_DATABASE_URL
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
    print(f"   Database   : SQLite → {EFFECTIVE_DATABASE_URL}", flush=True)
    print(f"   SQLite Path: {app_settings.sqlite_file_path}", flush=True)

    # ⚠️ SQLite លើ Render ត្រូវការ Persistent Disk មិនដូច្នេះទិន្នន័យនឹងបាត់
    if on_render:
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
                "(Plan `starter` ឡើងទៅ — មើល OPTION B ក្នុង render.yaml)"
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