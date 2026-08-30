from pathlib import Path
import io
import os
import re
import uuid
from .config import settings

# Cloudinary SDK (optional — បើអត់មាន SDK នឹងប្រើ Local Disk វិញ)
try:
    import cloudinary
    import cloudinary.uploader

    _HAS_CLOUDINARY = True
except ImportError:
    cloudinary = None
    _HAS_CLOUDINARY = False

# ថតរក្សាទុករូបភាពដែល Upload ពីកុំព្យូទ័រ (backend/uploads/) — ប្រើតែពេលអត់ Cloudinary
# អាចប្តូរទីតាំងតាម Environment Variable `UPLOAD_DIR`
DEFAULT_UPLOAD_DIR = Path(__file__).resolve().parent.parent / "uploads"
UPLOAD_DIR = Path(os.environ.get("UPLOAD_DIR", str(DEFAULT_UPLOAD_DIR)))

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif"}

# វីដេអូដែលអាច Upload បាន (Slider)
ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".webm", ".mov", ".ogg", ".m4v"}

# រួមគ្នា (រូប + វីដេអូ)
ALLOWED_MEDIA_EXTENSIONS = ALLOWED_EXTENSIONS | ALLOWED_VIDEO_EXTENSIONS


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
    - បើកំណត់ Cloudinary -> ផ្ទុកទៅ Cloudinary (URL អចិន្ត្រៃយ៍ មិនបាត់ពេល Redeploy)
    - បើអត់ -> រក្សាទុកលើ Local Disk (backend/uploads/) ដូចពីមុន
    Returns: {"url", "filename", "media_type"} — media_type = 'image' | 'video'
    """
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

    ext = Path(filename).suffix.lower()
    unique_name = f"{uuid.uuid4().hex}{ext}"
    media_type = "video" if ext in ALLOWED_VIDEO_EXTENSIONS else "image"
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
    """លុបឯកសារ (Delete) តាម URL៖ Cloudinary ឬ Local Disk។
    URL ខាងក្រៅ (picsum, pinimg...) មិនត្រូវបានលុបទេ។"""
    if not url:
        return False

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
        try:
            d.mkdir(parents=True, exist_ok=True)
            return d
        except Exception:
            continue
    return UPLOAD_DIR


