from __future__ import annotations

from pathlib import Path
import base64
import hashlib
import hmac
import io
import json
import mimetypes
import os
import re
import time
import uuid
import urllib.parse

import httpx

from .config import settings

# Cloudinary SDK (optional — បើអត់មាន SDK នឹងប្រើ Local Disk វិញ)
try:
    import cloudinary
    import cloudinary.uploader

    _HAS_CLOUDINARY = True
except ImportError:
    cloudinary = None
    _HAS_CLOUDINARY = False

# sqids — ត្រូវការដើម្បីបង្កើត File Key របស់ UploadThing (ដូច SDK JavaScript)
try:
    from sqids import Sqids as _Sqids

    _HAS_SQIDS = True
except ImportError:
    _Sqids = None
    _HAS_SQIDS = False

# ថតរក្សាទុករូបភាពដែល Upload ពីកុំព្យូទ័រ (backend/uploads/) — ប្រើតែពេលអត់ Cloudinary
# អាចប្តូរទីតាំងតាម Environment Variable `UPLOAD_DIR`
DEFAULT_UPLOAD_DIR = Path(__file__).resolve().parent.parent / "uploads"


def _resolve_upload_dir() -> Path:
    raw = os.environ.get("UPLOAD_DIR", "").strip()
    if raw and raw not in (".", "/"):
        return Path(raw)

    render_flag = os.environ.get("RENDER", "").strip().lower() in ("true", "1", "yes")
    var_data = Path("/var/data")
    if (render_flag or var_data.exists()) and var_data.is_dir():
        return Path("/var/data/uploads")

    return DEFAULT_UPLOAD_DIR


UPLOAD_DIR = _resolve_upload_dir()

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif"}

# វីដេអូដែលអាច Upload បាន (Slider)
ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".webm", ".mov", ".ogg", ".m4v"}

# រួមគ្នា (រូប + វីដេអូ)
ALLOWED_MEDIA_EXTENSIONS = ALLOWED_EXTENSIONS | ALLOWED_VIDEO_EXTENSIONS


# ============================================================
# UploadThing — ផ្ទុករូបភាព/វីដេអូលើ CDN របស់ UploadThing
# យក Token ពី https://uploadthing.com/dashboard -> API Keys
# ============================================================
# ត្រូវគ្នានឹង SDK JS (uploadthing 7.7.4) — key យកពី sqids + effect/Hash
_UPLOADTHING_ALPHABET = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
_UPLOADTHING_VERSION = "7.7.4"
_UT_URL_RE = re.compile(
    r"https?://(?:utfs\.io|[\w-]+\.ufs\.sh)/(?:f/|a/[^/]+/)([A-Za-z0-9]+)"
)
_UT_CLIENT = httpx.Client(timeout=60)


def _uploadthing_creds() -> dict | None:
    """ញែក Token យក apiKey + appId + region (ដើម្បីបង្កើត ingest URL)"""
    token = (settings.UPLOADTHING_TOKEN or "").strip()
    if not token or token in ("your-uploadthing-token", "PUT_REAL_TOKEN_OR_SKIP_THIS_LINE"):
        return None
    try:
        data = json.loads(base64.b64decode(token))
        api_key = data.get("apiKey")
        app_id = data.get("appId")
        regions = data.get("regions") or ["sea1"]
        if not api_key or not app_id:
            return None
        ingest_host = data.get("ingestHost") or "ingest.uploadthing.com"
        return {
            "api_key": api_key,
            "app_id": app_id,
            "ingest": f"https://{regions[0]}.{ingest_host}",
        }
    except Exception:
        return None


def uploadthing_configured() -> bool:
    return bool(_uploadthing_creds()) and _HAS_SQIDS


def _ut_i32(x: int) -> int:
    x &= 0xFFFFFFFF
    return x if x < 0x80000000 else x - 0x100000000


def _ut_hash_string(s: str) -> int:
    """effect/Hash.string — djb2 variant (h=5381, h*33^char, ពីចុងមកដើម)"""
    h = 5381
    for i in range(len(s) - 1, -1, -1):
        h = _ut_i32(_ut_i32(h * 33) ^ ord(s[i]))
    n = h & 0xFFFFFFFF
    return _ut_i32((h & 0xBFFFFFFF) | ((n >> 1) & 0x40000000))


def _ut_js_rem(a: int, b: int) -> int:
    """JS % (remainder រក្សាសញ្ញាដូច dividend)"""
    t = abs(a) % abs(b)
    return -t if a < 0 else t


def _ut_shuffle(s: str, seed: str) -> str:
    chars = list(s)
    sn = _ut_hash_string(seed)
    n = len(chars)
    for i in range(n):
        j = (_ut_js_rem(sn, i + 1) + i) % n
        chars[i], chars[j] = chars[j], chars[i]
    return "".join(chars)


def _ut_generate_key(creds: dict, name: str, size: int, file_type: str, now_ms: int) -> str:
    hash_parts = json.dumps(
        [name, size, file_type, now_ms, now_ms],
        separators=(",", ":"),
        ensure_ascii=False,
    )
    alpha = _ut_shuffle(_UPLOADTHING_ALPHABET, creds["app_id"])
    file_seed = _Sqids(alphabet=alpha, min_length=36, blocklist=[]).encode(
        [abs(_ut_hash_string(hash_parts))]
    )
    app_part = _Sqids(alphabet=alpha, min_length=12, blocklist=[]).encode(
        [abs(_ut_hash_string(creds["app_id"]))]
    )
    return app_part + file_seed


def _ut_signed_url(
    creds: dict,
    key: str,
    name: str,
    size: int,
    file_type: str,
    content_disposition: str = "inline",
) -> str:
    """បង្កើត Presigned PUT URL (ផ្ញើឯកសារដោយផ្ទាល់ទៅ UploadThing CDN)"""
    expires = int(time.time() * 1000) + 3600 * 1000
    js_enc = lambda v: urllib.parse.quote(str(v), safe="!~*'()")
    form_enc = lambda s: urllib.parse.quote(s, safe="*-._")
    params = [
        ("expires", str(expires)),
        ("x-ut-identifier", creds["app_id"]),
        ("x-ut-file-name", form_enc(js_enc(name))),
        ("x-ut-file-size", str(size)),
        ("x-ut-file-type", form_enc(js_enc(file_type))),
        ("x-ut-content-disposition", content_disposition),
    ]
    qs = "&".join(f"{k}={v}" for k, v in params)
    base = f"{creds['ingest']}/{key}?{qs}"
    sig = "hmac-sha256=" + hmac.new(
        creds["api_key"].encode(), base.encode(), hashlib.sha256
    ).hexdigest()
    return base + "&signature=" + form_enc(sig)


def _ut_upload(content: bytes, filename: str, media_type: str) -> dict:
    """Upload ទៅ UploadThing៖ Presign + PUT + យក URL អចិន្ត្រៃយ៍"""
    creds = _uploadthing_creds()
    if not creds or not _HAS_SQIDS:
        raise RuntimeError("UploadThing not configured")
    mime = mimetypes.guess_type(filename)[0] or (
        "video/mp4" if media_type == "video" else "image/png"
    )
    now_ms = int(time.time() * 1000)
    key = _ut_generate_key(creds, filename, len(content), mime, now_ms)
    put_url = _ut_signed_url(creds, key, filename, len(content), mime)
    resp = _UT_CLIENT.put(
        put_url,
        files={"file": (filename, content, mime)},
        headers={"Range": "bytes=0-", "x-uploadthing-version": _UPLOADTHING_VERSION},
    )
    resp.raise_for_status()
    data = resp.json()
    return {
        "url": data.get("ufsUrl") or data.get("url") or data.get("appUrl") or "",
        "filename": key,
        "media_type": media_type,
    }


def _ut_key_from_url(url: str) -> str | None:
    m = _UT_URL_RE.match((url or "").strip())
    return m.group(1) if m else None


def _ut_delete(key: str) -> bool:
    creds = _uploadthing_creds()
    if not creds:
        return False
    resp = _UT_CLIENT.post(
        "https://api.uploadthing.com/v6/deleteFiles",
        json={"fileKeys": [key]},
        headers={
            "x-uploadthing-version": _UPLOADTHING_VERSION,
            "x-uploadthing-be-adapter": "server-sdk",
            "x-uploadthing-api-key": creds["api_key"],
            "Content-Type": "application/json",
        },
    )
    if resp.status_code >= 400:
        return False
    return bool((resp.json() or {}).get("success"))


def cloudinary_configured() -> bool:
    """ពិនិត្យថាបានកំណត់ Cloudinary credentials ពេញលេញឬអត់"""
    return bool(
        _HAS_CLOUDINARY
        and settings.CLOUDINARY_CLOUD_NAME
        and settings.CLOUDINARY_API_KEY
        and settings.CLOUDINARY_API_SECRET
    )


def _get_cloudinary():
    cloudinary.config(
        cloud_name=settings.CLOUDINARY_CLOUD_NAME,
        api_key=settings.CLOUDINARY_API_KEY,
        api_secret=settings.CLOUDINARY_API_SECRET,
        secure=True,
    )
    return cloudinary


def save_upload(content: bytes, filename: str, folder: str = "ecommerce") -> dict:
    """រក្សាទុកឯកសារដែល Upload ពីកុំព្យូទ័រ៖
    - បើកំណត់ UploadThing -> ផ្ទុកទៅ UploadThing CDN (URL អចិន្ត្រៃយ៍ មិនបាត់ពេល Redeploy)
    - បើកំណត់ Cloudinary -> ផ្ទុកទៅ Cloudinary (URL អចិន្ត្រៃយ៍ មិនបាត់ពេល Redeploy)
    - បើអត់ -> រក្សាទុកលើ Local Disk (backend/uploads/) ដូចពីមុន
    Returns: {"url", "filename", "media_type"} — media_type = 'image' | 'video'
    """
    ext = Path(filename).suffix.lower()
    media_type = "video" if ext in ALLOWED_VIDEO_EXTENSIONS else "image"

    # 1) UploadThing (ពេញចិត្តបំផុត)
    if uploadthing_configured():
        try:
            return _ut_upload(content, filename, media_type)
        except Exception:
            # បើ UploadThing បរាជ័យ (គ្មាន internet / token ខុស) -> ត្រឡប់ទៅ Cloudinary/Local វិញ
            pass

    # 2) Cloudinary
    if cloudinary_configured():
        try:
            result = _get_cloudinary().uploader.upload(
                io.BytesIO(content),
                folder=folder,
                public_id=uuid.uuid4().hex,
                resource_type="auto",  # ស្គាល់រូប / វីដេអូ ដោយស្វ័យប្រវត្តិ
                overwrite=True,
            )
            return {
                "url": result.get("secure_url") or result.get("url", ""),
                "filename": result.get("public_id", ""),
                "media_type": result.get("resource_type", "image"),
            }
        except Exception:
            # បើ Cloudinary បរាជ័យ (គ្មាន internet / key ខុស) -> ត្រឡប់ទៅ Local Disk វិញ
            pass

    # 3) Local Disk (បម្រុងទុក)
    unique_name = f"{uuid.uuid4().hex}{ext}"
    # ព្យាយាមរក directory ដែលអាចសរសេរបាន
    # (បើ UPLOAD_DIR កំណត់ខុស / គ្មាន Persistent Disk -> ត្រឡប់ទៅ backend/uploads/)
    for d in (UPLOAD_DIR, DEFAULT_UPLOAD_DIR):
        try:
            d.mkdir(parents=True, exist_ok=True)
            dest = d / unique_name
            with open(dest, "wb") as fh:
                fh.write(content)
            return {
                "url": f"/uploads/{unique_name}",
                "filename": unique_name,
                "media_type": media_type,
            }
        except Exception:
            continue
    # គ្មាន directory ណាមួយអាចសរសេរបាន -> បញ្ជូន URL ទទេ (មិន crash)
    return {"url": "", "filename": "", "media_type": media_type}


def _cloudinary_url_parts(url: str):
    """ញែក Cloudinary URL យក public_id + resource_type (សម្រាប់លុប)"""
    # ឧទាហរណ៍៖ https://res.cloudinary.com/<cloud>/image/upload/v123456/folder/pub.png
    m = re.match(
        r"https?://res\.cloudinary\.com/[^/]+/([^/]+)/upload/(?:v\d+/)?(.+)",
        url,
    )
    if not m:
        return None, None
    resource_type, tail = m.group(1), m.group(2)
    public_id = tail.rsplit(".", 1)[0]  # កាត់ extension
    return resource_type, public_id


def delete_upload_by_url(url: str) -> bool:
    """លុបឯកសារ (Delete) តាម URL៖ UploadThing / Cloudinary / Local Disk។
    URL ខាងក្រៅ (picsum, pinimg...) មិនត្រូវបានលុបទេ។"""
    if not url:
        return False

    # UploadThing (utfs.io / *.ufs.sh)
    ut_key = _ut_key_from_url(url)
    if ut_key:
        return _ut_delete(ut_key)

    # Cloudinary
    if "res.cloudinary.com" in url:
        if not cloudinary_configured():
            return False
        resource_type, public_id = _cloudinary_url_parts(url)
        if not public_id:
            return False
        try:
            _get_cloudinary().uploader.destroy(
                public_id, resource_type=resource_type or "image"
            )
            return True
        except Exception:
            return False

    # Local disk (/uploads/...)
    if url.startswith("/uploads/"):
        for d in (UPLOAD_DIR, DEFAULT_UPLOAD_DIR):
            try:
                (d / Path(url).name).unlink(missing_ok=True)
            except Exception:
                continue
        return True

    # URL ខាងក្រៅ -> កុំលុប
    return False


def delete_uploads_by_urls(urls) -> None:
    """លុបឯកសារច្រើន (យក URL ដដែលៗចេញដើម្បីកុំលុបពីរដង)"""
    seen = set()
    for u in urls or []:
        if not u or u in seen:
            continue
        seen.add(u)
        delete_upload_by_url(u)


def ensure_upload_dir() -> Path:
    """រក directory ដែលអាចបង្កើត/សរសេរបាន៖
    ប្រើ UPLOAD_DIR បើអាច បើអត់ -> ត្រឡប់ទៅ DEFAULT_UPLOAD_DIR (backend/uploads/)។
    (កុំឱ្យ App crash ពេល UPLOAD_DIR កំណត់ខុស / គ្មាន Persistent Disk)"""
    for d in (UPLOAD_DIR, DEFAULT_UPLOAD_DIR):
        if str(d) in ("", "."):
            continue
        try:
            d.mkdir(parents=True, exist_ok=True)
            return d
        except Exception:
            continue
    DEFAULT_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    return DEFAULT_UPLOAD_DIR


