import re
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

# ផ្លូវដាច់ខាតទៅកាន់ backend/.env
# (config.py នេះនៅក្នុង backend/app/ -> parent.parent = backend/)
# ធ្វើបែបនេះ Backend អាចដំណើរការបានពី Directory ណាក៏បានដែរ
BACKEND_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BACKEND_DIR / ".env"

# ============================================================
# ពិនិត្យតម្លៃ Database URL ដែលមិនត្រឹមត្រូវ (Placeholder ពី .env.example)
# ------------------------------------------------------------
# បញ្ហាដែលធ្លាប់កើត៖ មានគេ Copy តម្លៃគំរូ `postgresql://USER:PASS@dpg-xxxx-a/DBNAME`
# ដាក់ក្នុង Render Environment -> App Retry 10 ដងរួច Crash ("could not translate
# host name dpg-xxxx-a")។ ដូច្នេះយើងច្រោះតម្លៃទាំងនោះចេញ ហើយប្រើ SQLite ឬ URL ផ្សេងជំនួស។
#
# ចំណាំ៖ Render Internal Hostname ជាទម្រង់ `dpg-abc123-a` (គ្មាន . ទេ) ដូច្នេះ
# យើងពិនិត្យតែ Host/User/Pass/DB ដែលជាតម្លៃគំរូប៉ុណ្ណោះ។
# ============================================================
_VALID_PG_SCHEMES = ("postgres://", "postgresql://")
_URL_PARTS_RE = re.compile(
    r"^(?P<user>[^:@/]*)(?::(?P<pw>[^@]*))?@(?P<host>[^/?]+)(?:/(?P<db>[^?]*))?"
)
_USER_PLACEHOLDERS = {"user", "username", "your-user", "your_user", "youruser"}
_PASS_PLACEHOLDERS = {"pass", "password", "your-password", "your_password", "yourpass"}
_HOST_PLACEHOLDERS = {"host", "hostname", "your-host", "yourhost", "example.com"}
_DB_PLACEHOLDERS = {"dbname", "your-db", "your_db", "yourdb", "database"}


def is_usable_database_url(url: str) -> bool:
    """URL ត្រឹមត្រូវសម្រាប់ប្រើឬអត់?

    - ត្រូវមាន scheme ត្រឹមត្រូវ (postgres/postgresql/sqlite)
    - មិនត្រូវមាន User/Pass/Host/DB ជាតម្លៃគំរូ
      (ឧ. `dpg-xxxx-a`, `USER:PASS`, `DBNAME`, `HOST`)
    - Render Internal Hostname ដូចជា `dpg-abc123-a` ត្រូវបានទទួលយក ✓
    """
    value = (url or "").strip()
    if not value:
        return False
    if value.startswith("sqlite"):
        return True
    if not value.startswith(_VALID_PG_SCHEMES):
        return False

    match = _URL_PARTS_RE.match(value.split("://", 1)[1])
    if not match:
        return False

    user = (match.group("user") or "").lower()
    password = (match.group("pw") or "").lower()
    host = (match.group("host") or "").lower()
    dbname = (match.group("db") or "").lower()

    if not user or not host:
        return False
    if user in _USER_PLACEHOLDERS or password in _PASS_PLACEHOLDERS:
        return False
    if host in _HOST_PLACEHOLDERS or re.match(r"^dpg-x+(-a)?$", host):
        return False
    if dbname in _DB_PLACEHOLDERS:
        return False
    return True



class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE) if ENV_FILE.exists() else None,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ============================================================
    # Database Engine — ជ្រើសរើសដោយច្បាស់លាស់
    #   "auto"     = ស្វ័យប្រវត្តិ (RENDER + DATABASE_URL_INTERNAL -> Postgres,
    #                បើមាន DATABASE_URL -> តាមវា, បើអត់ -> SQLite)  [Default]
    #   "sqlite"   = បង្ខំឱ្យប្រើ SQLite (SQLITE_PATH ឬ backend/ecommerce.db)
    #   "postgres" = បង្ខំឱ្យប្រើ PostgreSQL (ត្រូវមាន DATABASE_URL)
    # ============================================================
    DB_ENGINE: str = "auto"

    # PostgreSQL (Render) — External Database URL
    # ប្រើសម្រាប់ Local Development និង Deploy លើ Vercel
    DATABASE_URL: str = ""

    # PostgreSQL (Render) — Internal Database URL (Internal Hostname)
    # ប្រើតែពេល Deploy លើ Render ដែល hostname ខាងក្នុងអាចភ្ជាប់បាន
    DATABASE_URL_INTERNAL: str = ""

    # SQLite — ប្រើពេលគ្មាន PostgreSQL (Local Development / Deploy តូច)
    # បើទុកទទេ -> បង្កើតឯកសារ `backend/ecommerce.db` ដោយស្វ័យប្រវត្តិ
    # ឧ. /var/data/ecommerce.db (បើប្រើ Render Persistent Disk)
    SQLITE_PATH: str = ""

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

    # SMTP — សម្រាប់ផ្ញើ OTP Email ទៅកាន់អ្នកប្រើប្រាស់លើសកលលោក
    # (អាចប្រើបានជាមួយ Gmail, Yahoo, Outlook, Zoho, Brevo, SendGrid, Mailgun...)
    # បើប្រើ Gmail ត្រូវប្រើ App Password (មិនមែន password ធម្មតាទេ):
    # https://myaccount.google.com/apppasswords
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = ""
    SMTP_FROM_NAME: str = "E-Commerce Store"  # ឈ្មោះអ្នកផ្ញើដែលបង្ហាញដល់អ្នកទទួល
    SMTP_USE_SSL: bool = False  # True = SSL (port 465), False = STARTTLS (port 587)
    OTP_EXPIRE_MINUTES: int = 10

    # Brevo HTTP API — ផ្ញើ OTP/Receipt តាម HTTPS (port 443) ជំនួស SMTP
    # (សំខាន់លើ Render free tier ព្រោះ port 587/465 អាចគ្មាន network)
    # យក API Key ពី https://app.brevo.com/settings/keys/api (xkeysib-...)
    BREVO_API_KEY: str = ""

    # Telegram Login Widget — សម្រាប់ឱ្យអ្នកប្រើប្រាស់ Register/Login ជាមួយ Telegram
    # បង្កើត Bot តាម @BotFather ហើយកំណត់ Domain តាម /setdomain
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_BOT_USERNAME: str = ""  # ឧ. MyShopBot (ដោយគ្មាន @)

    # DeepSeek AI — សម្រាប់ AI Chatbot លើ Storefront
    # យក API Key ពី https://platform.deepseek.com
    DEEPSEEK_API_KEY: str = ""

    # Cloudinary — រក្សាទុករូបភាព/វីដេអូ Upload ឱ្យមានស្ថេរភាព
    # (Render free/standard disk មិន persistent — រូបនឹងបាត់ពេល Redeploy បើអត់ប្រើ Cloudinary)
    # យកពី Cloudinary Dashboard -> Settings -> API Keys
    CLOUDINARY_CLOUD_NAME: str = ""
    CLOUDINARY_API_KEY: str = ""
    CLOUDINARY_API_SECRET: str = ""

    # UploadThing — ផ្ទុករូបភាព/វីដេអូ Upload លើ CDN អចិន្ត្រៃយ៍
    # (ពេញចិត្តបំផុត — យក Token ពី https://uploadthing.com/dashboard -> API Keys)
    UPLOADTHING_TOKEN: str = ""

    # ABA Pay / KHQRcc — សម្រាប់ឲ្យអតិថិជនបង់ប្រាក់តាម QR Code (Scan & Pay)
    # យកពី https://khqr.cc Dashboard -> ABA Pay Gateway -> API Keys
    KHQRCC_PROFILE_ID: str = ""
    KHQRCC_SECRET_KEY: str = ""
    # URL របស់ Storefront (សម្រាប់ success_url ពេលអតិថិជនបង់ប្រាក់ចប់)
    FRONTEND_URL: str = "https://frontend-user-e-online.vercel.app"

    @property
    def clean_database_url(self) -> str:
        """DATABASE_URL ដែលប្រើបាន (បើជាតម្លៃគំរូ/ខុស -> ទទេ)"""
        value = (self.DATABASE_URL or "").strip()
        return value if is_usable_database_url(value) else ""

    @property
    def clean_database_url_internal(self) -> str:
        """DATABASE_URL_INTERNAL ដែលប្រើបាន (បើជាតម្លៃគំរូ/ខុស -> ទទេ)"""
        value = (self.DATABASE_URL_INTERNAL or "").strip()
        return value if is_usable_database_url(value) else ""

    @property
    def database_warnings(self) -> list:
        """សារព្រមានអំពី Env Var Database ដែលខុស (បង្ហាញក្នុង Diagnostics)"""
        warnings = []
        for name, raw in (
            ("DATABASE_URL", self.DATABASE_URL),
            ("DATABASE_URL_INTERNAL", self.DATABASE_URL_INTERNAL),
        ):
            value = (raw or "").strip()
            if value and not is_usable_database_url(value):
                shown = value.split("@")[-1] if "@" in value else value
                warnings.append(
                    f"{name} មិនត្រឹមត្រូវ (មើលទៅជាតម្លៃគំរូ): …@{shown} — ត្រូវបានមិនគិត! "
                    "សូមដាក់ URL ពិតពី Render → Postgres → Connect"
                )
        return warnings

    @property
    def db_engine(self) -> str:
        """'sqlite' | 'postgres' | 'auto' (ធ្វើឱ្យ DB_ENGINE ត្រឹមត្រូវ)"""
        value = (self.DB_ENGINE or "auto").strip().lower()
        if value in ("sqlite", "sqlite3", "file"):
            return "sqlite"
        if value in ("postgres", "postgresql", "pg", "psql"):
            return "postgres"
        return "auto"

    @property
    def active_database_url(self) -> str:
        """ជ្រើសរើស Database តាមលំដាប់អាទិភាព (ច្រោះ URL ដែលមិនត្រឹមត្រូវចេញ)៖

        1. `DB_ENGINE=sqlite`   → **SQLite** (SQLITE_PATH ឬ `backend/ecommerce.db`) — បង្ខំ
        2. `DB_ENGINE=postgres` → PostgreSQL (`DATABASE_URL_INTERNAL` ត្រឹមត្រូវ បើមាន → `DATABASE_URL`)
        3. `DB_ENGINE=auto` (Default)៖
           - នៅលើ Render + `DATABASE_URL_INTERNAL` ត្រឹមត្រូវ → PostgreSQL (Internal)
           - បើ `DATABASE_URL` ត្រឹមត្រូវ → តាម URL នោះ
           - បើគ្មាន URL ត្រឹមត្រូវ → **SQLite** (App មិន Crash ទេ តែបង្ហាញ WARNING)
        """
        engine = self.db_engine
        on_render = self.RENDER.lower() == "true"

        if engine == "sqlite":
            return f"sqlite:///{self.sqlite_file_path}"

        if engine == "postgres":
            if on_render and self.clean_database_url_internal:
                return self.clean_database_url_internal
            if self.clean_database_url:
                return self.clean_database_url
            # បើគ្មាន URL ត្រឹមត្រូវ -> SQLite (ព្រមានក្នុង Startup Diagnostics)
            return f"sqlite:///{self.sqlite_file_path}"

        # auto
        if on_render and self.clean_database_url_internal:
            return self.clean_database_url_internal
        if self.clean_database_url:
            return self.clean_database_url
        return f"sqlite:///{self.sqlite_file_path}"

    @property
    def sqlite_file_path(self) -> str:
        """ផ្លូវឯកសារ SQLite (បើកំណត់ SQLITE_PATH -> ប្រើវា បើអត់ -> backend/ecommerce.db)"""
        custom = (self.SQLITE_PATH or "").strip()
        return custom or str(BACKEND_DIR / "ecommerce.db")

    @property
    def cors_origins_list(self) -> list:
        """ញែក CORS_ORIGINS (comma-separated) ទៅជាបញ្ជី Origin"""
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

# ផ្ទុក .env ពី backend/ (ផ្លូវដាច់ខាត — ដំណើរការពី Directory ណាក៏បានដែរ)
settings = Settings()
