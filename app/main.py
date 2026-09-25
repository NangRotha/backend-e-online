import hashlib
import mimetypes
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse, HTMLResponse
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

    email = app_settings.effective_admin_email.lower()
    password = app_settings.effective_admin_password
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


def _bootstrap_site_settings():
    """កំណត់ Site Settings ដំបូងសម្រាប់ ABA Pay / Bakong Wallet ប្រសិនបើមិនទាន់មាន"""
    db = SessionLocal()
    try:
        defaults = {
            "payment_company_name": "Udom Shop",
            "payment_bakong_id": "Udom",
            "payment_display_name": "Udom",
            "payment_currency": "USD",
            "payment_khr_rate": "4100",
            "khqrcc_profile_id": "MOgrEmjgLkEmYzovmfTH0HQUPLgJ6DFq",
            "khqrcc_secret_key": "EIiW0sBH4vWjzeovF5bRC6WwDHJYzvfK",
            "telegram_bot_token": "8975197808:AAEbgpMagnJ2vGDSU_RDCMyTQ2dJHBDzxQQ",
            "telegram_bot_username": "DomLumiereOrdersBot",
            "telegram_chat_id": "8636603530",
            "telegram_notifications_enabled": "true",
        }
        legacy_defaults = {
            "payment_company_name": {"", "My Shop", "KHMER UDOM ET CO.,LTD", "ShopeKh"},
            "payment_bakong_id": {"", "udom@acleda", "yourname@acleda", "nang_rotha@bkrt"},
            "payment_display_name": {"", "Udom ET", "Real Name"},
            "khqrcc_profile_id": {"", "64BHRPOl0tGc3IMdw3V1ysjwhFKVC8EH"},
            "khqrcc_secret_key": {"", "cr6NRkWA2q3sq3rbR4VZshMRZQIj56L6"},
            "telegram_bot_token": {"", "123456:ABC-your-token", "PUT_REAL_BOT_TOKEN_OR_SKIP_THIS_LINE"},
            "telegram_bot_username": {"", "YourShopBot", "MyShopBot"},
            "telegram_chat_id": {"", "0"},
        }
        existing = {s.key: s for s in db.query(models.SiteSetting).all()}
        updated = 0
        for key, val in defaults.items():
            if key not in existing:
                db.add(models.SiteSetting(key=key, value=val))
                updated += 1
            else:
                curr_val = (existing[key].value or "").strip()
                curr_lower = curr_val.lower()
                legacy_lowers = {v.lower() for v in legacy_defaults.get(key, set())}
                if not curr_val or curr_val in legacy_defaults.get(key, set()) or curr_lower in legacy_lowers:
                    existing[key].value = val
                    updated += 1
        if updated:
            db.commit()
            print(f"✅ Site Settings bootstrap: បានកំណត់ {updated} settings (ABA Pay & Telegram Bot: @DomLumiereOrdersBot)", flush=True)
    except Exception as exc:  # noqa: BLE001
        print(f"⚠️  Site Settings bootstrap បរាជ័យ: {type(exc).__name__}: {exc}", flush=True)
    finally:
        db.close()


# បង្កើតតារាងទាំងអស់ក្នុង Database ប្រសិនបើមិនទាន់មាន (រួមទាំង Migration)
init_db()

# 👤 Bootstrap Admin ដំបូង (ដំណើរការតែពេលកំណត់ ADMIN_EMAIL + ADMIN_PASSWORD)
_bootstrap_admin()

# 💳 Bootstrap Site Settings សម្រាប់ ABA Pay / Bakong Wallet
_bootstrap_site_settings()


def _optimize_existing_videos() -> None:
    """ពិនិត្យ និង Optimize វីដេអូ MP4 ទាំងអស់ក្នុង uploads/ ឱ្យទៅជា Faststart ដោយស្វ័យប្រវត្តិ
    ដើម្បីឱ្យ Browser អាច Play ភ្លាមៗ (moov atom នៅខាងដើម)។"""
    from .storage import DEFAULT_UPLOAD_DIR, UPLOAD_DIR, faststart_mp4

    count = 0
    seen = set()
    for d in (UPLOAD_DIR, DEFAULT_UPLOAD_DIR):
        if not d.exists() or not d.is_dir():
            continue
        try:
            for mp4_file in d.glob("*.mp4"):
                canonical = str(mp4_file.resolve())
                if canonical in seen:
                    continue
                seen.add(canonical)
                try:
                    size = mp4_file.stat().st_size
                    if size < 32:
                        continue
                    raw = mp4_file.read_bytes()
                    optimized = faststart_mp4(raw)
                    if len(optimized) != len(raw) or optimized[:32] != raw[:32]:
                        mp4_file.write_bytes(optimized)
                        count += 1
                        print(f"🎬 Faststart optimized: {mp4_file.name} ({size} bytes)", flush=True)
                except Exception as exc:
                    print(f"⚠️ Faststart error on {mp4_file.name}: {exc}", flush=True)
        except Exception:
            pass
    if count:
        print(f"✅ Video optimization: បានកែសម្រួល {count} MP4 ទៅជា Faststart រួចរាល់", flush=True)


# 🎬 Optimize វីដេអូដែលធ្លាប់ Upload ពីមុនឱ្យទៅជា Faststart
_optimize_existing_videos()

# ព្រមានបើ Email (OTP) មិនទាន់កំណត់ — ពេលនោះ OTP នឹងបង្ហាញក្នុង Dev Mode តែប៉ុណ្ណោះ
_email_cfg = email_status()
if not _email_cfg["configured"]:
    print(
        "⚠️  Email (OTP) NOT configured — SMTP_USER/SMTP_PASSWORD missing.\n"
        "    OTP emails will NOT be sent; codes show in dev mode instead.\n"
        "    Add SMTP_* env vars (Gmail/Brevo/SendGrid) to fix."
    )

app = FastAPI(
    title="E-commerce API",
    docs_url="/docs" if app_settings.show_docs else None,
    redoc_url="/redoc" if app_settings.show_docs else None,
    openapi_url="/openapi.json" if app_settings.show_docs else None,
)

# CORS សម្រាប់អនុញ្ញាតឱ្យ Frontend (React Vite) ភ្ជាប់មក
# - Dev localhost តែងតែអនុញ្ញាតដោយស្វ័យប្រវត្តិ
# - Production frontends (Vercel) ត្រូវបានបញ្ចូលដោយផ្ទាល់នៅទីនេះ
# - អាចបន្ថែម Origin បន្ថែមទៀតតាមរយៈ CORS_ORIGINS ក្នុង Environment (ញែកដោយសញ្ញាក្បៀស)
_DEV_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:5174",
    "https://www.udomkh.online",
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

# Security Headers Middleware — ការពារ Clickjacking, MIME-sniffing, XSS & Information Disclosure
@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    # Enforce request payload size safety (max 100MB)
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > 100 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Payload too large")

    response = await call_next(request)

    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if "server" in response.headers:
        del response.headers["server"]
    return response

# បម្រើរូបភាព និងវីដេអូដែល Upload ពីកុំព្យូទ័រ (/uploads/...)
# គាំទ្រ HTTP Range Requests (206 Partial Content) ពេញលេញសម្រាប់ Video Streaming
_EFFECTIVE_UPLOAD_DIR = ensure_upload_dir()


@app.head("/uploads/{file_path:path}")
@app.get("/uploads/{file_path:path}")
async def serve_upload_file(file_path: str, request: Request):
    """បម្រើ File ក្នុង uploads ជាមួយ Range Requests (206 Partial Content)
    ចាំបាច់សម្រាប់ HTML5 Video streaming (MP4/WebM) ដើម្បីឱ្យ Browser ចាក់ភ្លាមៗ។"""
    from .storage import DEFAULT_UPLOAD_DIR

    clean_name = os.path.normpath(file_path).lstrip("/\\")
    full_path = (_EFFECTIVE_UPLOAD_DIR / clean_name).resolve()
    effective_dir = _EFFECTIVE_UPLOAD_DIR.resolve()

    # សុវត្ថិភាព Directory Traversal
    if not str(full_path).startswith(str(effective_dir)) or not full_path.is_file():
        fallback_dir = DEFAULT_UPLOAD_DIR.resolve()
        fallback_path = (DEFAULT_UPLOAD_DIR / clean_name).resolve()
        if str(fallback_path).startswith(str(fallback_dir)) and fallback_path.is_file():
            full_path = fallback_path
        else:
            raise HTTPException(status_code=404, detail="File not found")

    file_size = full_path.stat().st_size
    mtime = full_path.stat().st_mtime
    etag = f'"{hashlib.md5(f"{file_size}-{mtime}".encode()).hexdigest()}"'

    media_type, _ = mimetypes.guess_type(str(full_path))
    if not media_type:
        ext = full_path.suffix.lower()
        if ext in (".mp4", ".m4v"):
            media_type = "video/mp4"
        elif ext == ".webm":
            media_type = "video/webm"
        elif ext in (".jpg", ".jpeg"):
            media_type = "image/jpeg"
        elif ext == ".png":
            media_type = "image/png"
        elif ext == ".webp":
            media_type = "image/webp"
        else:
            media_type = "application/octet-stream"

    # HEAD Request -> ត្រឡប់ headers រួមទាំង Accept-Ranges
    if request.method == "HEAD":
        return Response(
            status_code=200,
            headers={
                "Accept-Ranges": "bytes",
                "Content-Length": str(file_size),
                "Content-Type": media_type,
                "ETag": etag,
                "Cache-Control": "public, max-age=86400",
            },
        )

    range_header = request.headers.get("range") or request.headers.get("Range")
    if not range_header or not range_header.strip().startswith("bytes="):
        return FileResponse(
            full_path,
            media_type=media_type,
            headers={
                "Accept-Ranges": "bytes",
                "ETag": etag,
                "Cache-Control": "public, max-age=86400",
            },
        )

    # Parse Range: bytes=start-end
    range_val = range_header.replace("bytes=", "").strip()
    if range_val.startswith("-"):
        suffix_len = int(range_val[1:])
        start = max(0, file_size - suffix_len)
        end = file_size - 1
    else:
        parts = range_val.split("-", 1)
        start = int(parts[0]) if parts[0] else 0
        end = int(parts[1]) if len(parts) > 1 and parts[1] else file_size - 1

    if start >= file_size or start > end:
        return Response(
            status_code=416,
            headers={
                "Content-Range": f"bytes */{file_size}",
                "Accept-Ranges": "bytes",
            },
        )

    end = min(end, file_size - 1)
    content_length = (end - start) + 1

    def iterfile(path, offset, total_bytes, chunk_size=256 * 1024):
        with open(path, "rb") as f:
            f.seek(offset)
            remaining = total_bytes
            while remaining > 0:
                chunk = f.read(min(chunk_size, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk

    headers = {
        "Content-Range": f"bytes {start}-{end}/{file_size}",
        "Accept-Ranges": "bytes",
        "Content-Length": str(content_length),
        "Content-Type": media_type,
        "ETag": etag,
        "Cache-Control": "public, max-age=86400",
    }
    return StreamingResponse(
        iterfile(full_path, start, content_length),
        status_code=206,
        headers=headers,
        media_type=media_type,
    )


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
    """Render Health Check — Returns clean, secure status without leaking internal filesystem paths."""
    from .storage import cloudinary_configured, uploadthing_configured

    db_status = "connected"
    counts = {}
    try:
        db = SessionLocal()
        try:
            counts = {
                "products": db.query(models.Product).count(),
                "categories": db.query(models.Category).count(),
                "orders": db.query(models.Order).count(),
                "users": db.query(models.User).count(),
                "site_settings": db.query(models.SiteSetting).count(),
            }
        finally:
            db.close()
    except Exception as exc:  # noqa: BLE001
        db_status = f"unhealthy: {type(exc).__name__}"

    storage_type = (
        "uploadthing"
        if uploadthing_configured()
        else "cloudinary"
        if cloudinary_configured()
        else "local-disk"
    )

    info = {
        "status": "ok" if db_status == "connected" else "degraded",
        "database": db_status,
        "storage": storage_type,
        "counts": counts,
    }

    # Only include internal diagnostic path if docs are explicitly enabled in development
    if app_settings.show_docs:
        from .database import EFFECTIVE_DATABASE_URL
        info["debug_db_url"] = EFFECTIVE_DATABASE_URL

    return info


@app.get("/p/{product_id}", response_class=HTMLResponse)
def share_product_redirect(product_id: int):
    """
    OpenGraph / Social Media Link Preview & redirect for products.
    Returns rich metadata with real product image for Telegram, Facebook, WhatsApp, etc.
    """
    import html

    db = SessionLocal()
    try:
        product = db.query(models.Product).filter(models.Product.id == product_id).first()
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")

        product_name = product.name_kh or product.name or "ទំនិញ"
        price_str = f"${float(product.price or 0):.2f}"
        title = f"{product_name} — {price_str} | Udom Shop"
        desc = product.description or f"សូមមើលផលិតផល «{product_name}» គុណភាពខ្ពស់ តម្លៃត្រឹមតែ {price_str} នៅ Udom Shop"

        img = ""
        if product.images and isinstance(product.images, list) and len(product.images) > 0:
            img = product.images[0]
        elif product.image_url:
            img = product.image_url

        if img and img.startswith("/"):
            img = f"https://backend-e-online.onrender.com{img}"

        canonical_url = f"https://www.udomkh.online/product/{product_id}"

        safe_title = html.escape(title)
        safe_desc = html.escape(desc)
        safe_img = html.escape(img or "https://www.udomkh.online/vite.svg")
        safe_url = html.escape(canonical_url)

        return HTMLResponse(content=f"""<!DOCTYPE html>
<html lang="km">
<head>
  <meta charset="UTF-8" />
  <title>{safe_title}</title>
  <meta name="description" content="{safe_desc}" />
  <meta property="og:type" content="product" />
  <meta property="og:site_name" content="Udom Shop" />
  <meta property="og:url" content="{safe_url}" />
  <meta property="og:title" content="{safe_title}" />
  <meta property="og:description" content="{safe_desc}" />
  <meta property="og:image" content="{safe_img}" />
  <meta property="og:image:secure_url" content="{safe_img}" />
  <meta property="og:image:alt" content="{html.escape(product_name)}" />
  <meta property="og:image:width" content="800" />
  <meta property="og:image:height" content="800" />
  <meta name="twitter:card" content="summary_large_image" />
  <meta name="twitter:url" content="{safe_url}" />
  <meta name="twitter:title" content="{safe_title}" />
  <meta name="twitter:description" content="{safe_desc}" />
  <meta name="twitter:image" content="{safe_img}" />
  <meta http-equiv="refresh" content="0;url={safe_url}" />
  <link rel="canonical" href="{safe_url}" />
</head>
<body style="font-family: sans-serif; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; background: #f8fafc; color: #0f172a;">
  <div style="text-align: center; padding: 20px;">
    <h2>{safe_title}</h2>
    <p>{safe_desc}</p>
    <a href="{safe_url}" style="display: inline-block; padding: 10px 20px; background: #059669; color: white; border-radius: 8px; text-decoration: none; font-weight: bold;">ចូលមើលទំនិញ</a>
  </div>
  <script>window.location.replace("{safe_url}");</script>
</body>
</html>""")
    finally:
        db.close()


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
    print(
        f"   Docs UI    : {'✅ Enabled (/docs)' if app_settings.show_docs else '🔒 Hidden in production (docs_url=None)'}",
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
    if app_settings.SECRET_KEY in ("your-secret-key-change-this", "replace-with-a-long-random-secret"):
        if on_render:
            warnings.append(
                "SECRET_KEY កំពុងប្រើតម្លៃ Default/Placeholder — សូមកំណត់ SECRET_KEY ថ្មី (random 32+ chars) ក្នុង "
                "Render → Environment (មិនដូច្នេះ JWT អាចក្លែងបាន)"
            )
        else:
            print("   SECRET_KEY : ⚠️  default value (ok for local dev)", flush=True)

    if app_settings.has_legacy_postgres_url:
        warnings.append(
            "រកឃើញ DATABASE_URL/DATABASE_URL_INTERNAL បែប PostgreSQL ក្នុង Render Environment — "
            "Backend ដំណើរការលើ SQLite ដោយស្វ័យប្រវត្តិ។ សូមចូល Render → Environment Variables ហើយលុប "
            "DATABASE_URL, DATABASE_URL_INTERNAL, និង DB_ENGINE ចេញ។"
        )

    if on_render and (not app_settings.effective_admin_email or not app_settings.effective_admin_password):
        warnings.append(
            "ខ្វះ ADMIN_EMAIL ឬ ADMIN_PASSWORD ក្នុង Render Environment Variables — គ្មាន Admin ត្រូវបានបង្កើតទេ! "
            "សូមបន្ថែម ADMIN_EMAIL=... និង ADMIN_PASSWORD=... (ឬ Email=... និង Password=...) ក្នុង Render ដើម្បីចូល Admin Panel បាន។"
        )

    for w in warnings:
        print(f"⚠️  WARNING: {w}", flush=True)
    print("─" * 64, flush=True)


_deploy_diagnostics()