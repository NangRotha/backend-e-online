from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# ផ្លូវដាច់ខាតទៅកាន់ backend/.env
# (config.py នេះនៅក្នុង backend/app/ -> parent.parent = backend/)
# ធ្វើបែបនេះ Backend អាចដំណើរការបានពី Directory ណាក៏បានដែរ
BACKEND_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BACKEND_DIR / ".env"

# ឯកសារ SQLite ដើម — បង្កើតដោយស្វ័យប្រវត្តិ (backend/ecommerce.db)
DEFAULT_SQLITE_FILE = BACKEND_DIR / "ecommerce.db"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE) if ENV_FILE.exists() else None,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ============================================================
    # 🗄️ Database = **SQLite តែមួយប៉ុណ្ណោះ** (គ្មាន PostgreSQL ទៀតទេ)
    # ------------------------------------------------------------
    # • ទុក `SQLITE_PATH` ទទេ -> បង្កើត `backend/ecommerce.db` ដោយស្វ័យប្រវត្តិ
    # • ចង់ប្តូរទីតាំង -> `SQLITE_PATH=/var/data/ecommerce.db` (Render + Persistent Disk)
    # ⚠️ បើថតនោះសរសេរមិនបាន (ឧ. Free plan គ្មាន Disk) -> Fallback ទៅ
    #    `backend/ecommerce.db` វិញ ដើម្បីកុំឱ្យ App Crash
    # ============================================================
    SQLITE_PATH: str = ""
    DATABASE_URL: str = ""
    DATABASE_URL_INTERNAL: str = ""
    DB_ENGINE: str = ""

    # Render កំណត់ RENDER=true ដោយស្វ័យប្រវត្តិ នៅពេលដំណើរការលើ Render
    RENDER: str = ""

    # CORS — បញ្ជី Origin ដែលអនុញ្ញាតឱ្យភ្ជាប់មក API
    # (ញែកដោយសញ្ញាក្បៀស) ឧ. https://shop.example.com,https://admin.example.com
    # Dev localhost តែងតែត្រូវបានអនុញ្ញាតដោយស្វ័យប្រវត្តិ
    CORS_ORIGINS: str = ""

    # CORS Regex (ជាជម្រើស) — សម្រាប់ Vercel Preview Deployment ដែល URL ផ្លាស់ប្តូររាល់ដង
    # ឧ. ^https://frontend-(user|admin)-e-online.*\.vercel\.app$
    CORS_ORIGIN_REGEX: str = ""

    SECRET_KEY: str = "your-secret-key-change-this"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24

    # ============================================================
    # SMTP — សម្រាប់ផ្ញើ OTP Email (Gmail, Yahoo, Outlook, Zoho, Brevo...)
    # ⚠️ Gmail ត្រូវប្រើ App Password (មិនមែន password ធម្មតា)៖
    #    https://myaccount.google.com/apppasswords
    # ⚠️ លើ Render Free plan port 587/465 ត្រូវបានបិទ -> ប្រើ BREVO_API_KEY ជំនួស
    # ============================================================
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = ""
    SMTP_FROM_NAME: str = "E-Commerce Store"  # ឈ្មោះអ្នកផ្ញើដែលបង្ហាញដល់អ្នកទទួល
    SMTP_USE_SSL: bool = False  # True = SSL (port 465), False = STARTTLS (port 587)
    OTP_EXPIRE_MINUTES: int = 10

    # Brevo HTTP API — ផ្ញើ OTP/Receipt តាម HTTPS (port 443) ជំនួស SMTP
    # (សំខាន់លើ Render free tier ព្រោះ port 587/465 ត្រូវបានបិទ)
    # យក API Key ពី https://app.brevo.com/settings/keys/api (xkeysib-...)
    BREVO_API_KEY: str = ""

    # Telegram Bot & Order Notifications — ជូនដំណឹងពេលមានការកុម្ម៉ង់ថ្មី (New Orders)
    TELEGRAM_BOT_TOKEN: str = "8975197808:AAEbgpMagnJ2vGDSU_RDCMyTQ2dJHBDzxQQ"
    TELEGRAM_BOT_USERNAME: str = "DomLumiereOrdersBot"  # Bot username (ដោយគ្មាន @)
    TELEGRAM_CHAT_ID: str = "8636603530"  # Admin Telegram ID សម្រាប់ទទួលសារ
    TELEGRAM_NOTIFICATIONS_ENABLED: bool = True
    ADMIN_FRONTEND_URL: str = "https://frontend-admin-e-online.vercel.app"

    # DeepSeek AI — សម្រាប់ AI Chatbot លើ Storefront
    # យក API Key ពី https://platform.deepseek.com
    DEEPSEEK_API_KEY: str = ""

    # Cloudinary — រក្សាទុករូបភាព/វីដេអូ Upload ឱ្យមានស្ថេរភាព
    # យកពី Cloudinary Dashboard -> Settings -> API Keys
    CLOUDINARY_CLOUD_NAME: str = ""
    CLOUDINARY_API_KEY: str = ""
    CLOUDINARY_API_SECRET: str = ""

    # UploadThing — ផ្ទុករូបភាព/វីដេអូ Upload លើ CDN អចិន្ត្រៃយ៍
    # (យក Token ពី https://uploadthing.com/dashboard -> API Keys)
    UPLOADTHING_TOKEN: str = ""

    # ABA Pay / KHQRcc — សម្រាប់ឲ្យអតិថិជនបង់ប្រាក់តាម QR (Scan & Pay)
    # យកពី https://anajakpay.com Dashboard -> ABA Pay Gateway -> API Keys
    KHQRCC_PROFILE_ID: str = "MOgrEmjgLkEmYzovmfTH0HQUPLgJ6DFq"
    KHQRCC_SECRET_KEY: str = "EIiW0sBH4vWjzeovF5bRC6WwDHJYzvfK"
    # URL របស់ Storefront (សម្រាប់ success_url ពេលអតិថិជនបង់ប្រាក់ចប់)
    FRONTEND_URL: str = "https://frontend-user-e-online.vercel.app"

    # ============================================================
    # 👤 Bootstrap Admin — បង្កើត Admin ដំបូងដោយស្វ័យប្រវត្តិ ពេល App Startup
    # ------------------------------------------------------------
    # ចាំបាច់សម្រាប់ Host ដែល **គ្មាន Shell/SSH** (ឧ. Render Free Plan —
    # មិនអាចរត់ `create_admin.py` បានទេ ព្រោះ Free គ្មាន Shell/One-off Job)
    #
    # បើកំណត់ `ADMIN_EMAIL` + `ADMIN_PASSWORD` -> បង្កើត/ដំឡើងជា Admin (Idempotent)
    # បើទុកទទេ -> គ្មានអ្វីកើតឡើង (មិនបង្កើត User ណាមួយទេ — សុវត្ថិភាព)
    #
    # ⚠️ `ADMIN_PASSWORD` ជា Source of Truth៖ បើ Password ក្នុង DB ខុសពី Env
    #    នោះវានឹងកំណត់តាម Env វិញរាល់ពេល Startup (ដើម្បីកុំឱ្យចូលមិនបាន)
    # ============================================================
    ADMIN_EMAIL: str = ""
    ADMIN_PASSWORD: str = ""
    Email: str = ""
    Password: str = ""
    EMAIL: str = ""
    PASSWORD: str = ""
    ADMIN_NAME: str = "Admin"  # ឈ្មោះបង្ហាញ (Display Name) របស់ Admin

    @property
    def effective_admin_email(self) -> str:
        """អ៊ីមែល Admin — គាំទ្រទាំង ADMIN_EMAIL និង Email"""
        return (self.ADMIN_EMAIL or self.Email or self.EMAIL or "").strip()

    @property
    def effective_admin_password(self) -> str:
        """ពាក្យសម្ងាត់ Admin — គាំទ្រទាំង ADMIN_PASSWORD និង Password"""
        return self.ADMIN_PASSWORD or self.Password or self.PASSWORD or ""

    @property
    def has_legacy_postgres_url(self) -> bool:
        """ពិនិត្យថាតើមាន DATABASE_URL បែប PostgreSQL សល់ពីមុនឬអត់"""
        for raw in (self.DATABASE_URL, self.DATABASE_URL_INTERNAL):
            url = (raw or "").strip().lower()
            if url.startswith("postgres://") or url.startswith("postgresql://"):
                return True
        return False

    @property
    def sqlite_file_path(self) -> str:
        """ផ្លូវឯកសារ SQLite — គាំទ្រ SQLITE_PATH, DATABASE_URL (sqlite:///...),
        និង auto-detection សម្រាប់ Render (/var/data) ឬ local fallback"""
        custom = (self.SQLITE_PATH or "").strip()
        if custom:
            return custom

        # គាំទ្រ DATABASE_URL បើជា sqlite://
        for raw in (self.DATABASE_URL, self.DATABASE_URL_INTERNAL):
            db_url = (raw or "").strip()
            if db_url.startswith("sqlite:///"):
                return db_url.replace("sqlite:///", "", 1)
            if db_url.startswith("sqlite://"):
                return db_url.replace("sqlite://", "", 1)

        # បើនៅលើ Render / Docker ហើយមានថត /var/data -> ប្រើ /var/data/ecommerce.db
        render_flag = (self.RENDER or "").strip().lower() in ("true", "1", "yes")
        var_data = Path("/var/data")
        if (render_flag or var_data.exists()) and var_data.is_dir():
            return "/var/data/ecommerce.db"

        return str(DEFAULT_SQLITE_FILE)

    @property
    def cors_origins_list(self) -> list:
        """ញែក CORS_ORIGINS (comma-separated) ទៅជាបញ្ជី Origin"""
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


# ផ្ទុក .env ពី backend/ (ផ្លូវដាច់ខាត — ដំណើរការពី Directory ណាក៏បានដែរ)
settings = Settings()
