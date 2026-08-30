from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from .database import init_db
from .config import settings as app_settings
from .routers import auth, products, orders, discounts, settings, admin, ws, categories, slides, users, chat, alerts
from .storage import ensure_upload_dir

# បង្កើតតារាងទាំងអស់ក្នុង PostgreSQL ប្រសិនបើមិនទាន់មាន (រួមទាំង Migration)
init_db()

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
app.add_middleware(
    CORSMiddleware,
    allow_origins=[*_DEV_ORIGINS, *_PRODUCTION_ORIGINS, *app_settings.cors_origins_list],
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

@app.get("/")
def read_root():
    return {"message": "E-commerce Backend is running!"}

@app.get("/health")
def health_check():
    """សម្រាប់ Render Health Check (Render ហៅ endpoint នេះរៀងរាល់ពេល)"""
    return {"status": "ok"}