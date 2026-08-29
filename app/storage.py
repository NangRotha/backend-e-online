from pathlib import Path
import os

# ថតរក្សាទុករូបភាពដែល Upload ពីកុំព្យូទ័រ (backend/uploads/)
# អាចប្តូរទីតាំងតាម Environment Variable `UPLOAD_DIR`
# (ឧ. នៅលើ Render អាច mount Persistent Disk ហើយដាក់ UPLOAD_DIR=/var/data/uploads)
DEFAULT_UPLOAD_DIR = Path(__file__).resolve().parent.parent / "uploads"
UPLOAD_DIR = Path(os.environ.get("UPLOAD_DIR", str(DEFAULT_UPLOAD_DIR)))

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif"}

# វីដេអូដែលអាច Upload បាន (Slider)
ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".webm", ".mov", ".ogg", ".m4v"}

# រួមគ្នា (រូប + វីដេអូ)
ALLOWED_MEDIA_EXTENSIONS = ALLOWED_EXTENSIONS | ALLOWED_VIDEO_EXTENSIONS

def ensure_upload_dir() -> Path:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    return UPLOAD_DIR
