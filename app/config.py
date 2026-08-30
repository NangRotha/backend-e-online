from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

# ផ្លូវដាច់ខាតទៅកាន់ backend/.env
# (config.py នេះនៅក្នុង backend/app/ -> parent.parent = backend/)
# ធ្វើបែបនេះ Backend អាចដំណើរការបានពី Directory ណាក៏បានដែរ
BACKEND_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BACKEND_DIR / ".env"

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE) if ENV_FILE.exists() else None,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # PostgreSQL (Render) — External Database URL
    # ប្រើសម្រាប់ Local Development និង Deploy លើ Vercel
    DATABASE_URL: str = ""

    # PostgreSQL (Render) — Internal Database URL (Internal Hostname)
    # ប្រើតែពេល Deploy លើ Render ដែល hostname ខាងក្នុងអាចភ្ជាប់បាន
    DATABASE_URL_INTERNAL: str = ""

    # Render កំណត់ RENDER=true ដោយស្វ័យប្រវត្តិ នៅពេលដំណើរការលើ Render
    RENDER: str = ""

    # CORS — បញ្ជី Origin ដែលអនុញ្ញាតឱ្យភ្ជាប់មក API
    # (ញែកដោយសញ្ញាក្បៀស) ឧ. https://shop.example.com,https://admin.example.com
    # Dev localhost តែងតែត្រូវបានអនុញ្ញាតដោយស្វ័យប្រវត្តិ
    CORS_ORIGINS: str = ""

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

    # ABA Pay / KHQRcc — សម្រាប់ឲ្យអតិថិជនបង់ប្រាក់តាម QR Code (Scan & Pay)
    # យកពី https://khqr.cc Dashboard -> ABA Pay Gateway -> API Keys
    KHQRCC_PROFILE_ID: str = ""
    KHQRCC_SECRET_KEY: str = ""
    # URL របស់ Storefront (សម្រាប់ success_url ពេលអតិថិជនបង់ប្រាក់ចប់)
    FRONTEND_URL: str = "https://frontend-user-e-online.vercel.app"

    @property
    def active_database_url(self) -> str:
        """ជ្រើសរើស Database URL ត្រឹមត្រូវតាមបរិស្ថានដំណើរការ។
        - នៅលើ Render: ប្រើ Internal Hostname (លឿន និងសុវត្ថិភាពជាង)
        - នៅ Local / Vercel: ប្រើ External Hostname
        """
        if self.RENDER.lower() == "true" and self.DATABASE_URL_INTERNAL:
            return self.DATABASE_URL_INTERNAL
        return self.DATABASE_URL

    @property
    def cors_origins_list(self) -> list:
        """ញែក CORS_ORIGINS (comma-separated) ទៅជាបញ្ជី Origin"""
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

# ផ្ទុក .env ពី backend/ (ផ្លូវដាច់ខាត — ដំណើរការពី Directory ណាក៏បានដែរ)
settings = Settings()
