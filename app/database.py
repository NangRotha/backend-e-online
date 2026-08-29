from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base
from .config import settings

# យក Database URL ពី Environment Variables (បង្កើតក្នុង .env ឬ Render Dashboard)
DATABASE_URL = settings.active_database_url

# បង្កើត engine សម្រាប់ភ្ជាប់ទៅ PostgreSQL (Render)
engine = create_engine(
    DATABASE_URL,
    connect_args={"sslmode": "require"},  # Render PostgreSQL តម្រូវឱ្យប្រើ SSL
    pool_pre_ping=True
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def init_db():
    """បង្កើតតារាងទាំងអស់ និងធ្វើ Migration បើចាំបាច់ (idempotent)"""
    Base.metadata.create_all(bind=engine)
    with engine.connect() as conn:
        # Migration: បន្ថែម column email_verified ទៅតារាង users បើនៅមិនទាន់មាន
        conn.execute(text(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verified BOOLEAN DEFAULT FALSE"
        ))
        # Migration: បន្ថែម column images ទៅតារាង products បើនៅមិនទាន់មាន
        conn.execute(text(
            "ALTER TABLE products ADD COLUMN IF NOT EXISTS images JSON DEFAULT '[]'::json"
        ))
        # Migration: បន្ថែម column telegram_id ទៅតារាង users បើនៅមិនទាន់មាន
        conn.execute(text(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS telegram_id INTEGER"
        ))
        conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_telegram_id ON users (telegram_id)"
        ))
        # Migration: បន្ថែម column profile_image ទៅតារាង users (រូប Profile របស់អ្នកប្រើ)
        conn.execute(text(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS profile_image VARCHAR DEFAULT ''"
        ))
        # Migration: បង្កើតតារាង categories (សម្រាប់ Admin គ្រប់គ្រង Category)
        conn.execute(text(
            "CREATE TABLE IF NOT EXISTS categories ("
            " id SERIAL PRIMARY KEY,"
            " name VARCHAR NOT NULL UNIQUE,"
            " description VARCHAR DEFAULT '',"
            " created_at TIMESTAMPTZ DEFAULT now()"
            ")"
        ))
        # Migration: បង្កើតតារាង slides (Slider លើ Storefront: រូប / វីដេអូ / YouTube)
        conn.execute(text(
            "CREATE TABLE IF NOT EXISTS slides ("
            " id SERIAL PRIMARY KEY,"
            " title VARCHAR DEFAULT '',"
            " subtitle VARCHAR DEFAULT '',"
            " media_type VARCHAR DEFAULT 'image',"
            " media_url VARCHAR DEFAULT '',"
            " youtube_url VARCHAR DEFAULT '',"
            " link_url VARCHAR DEFAULT '',"
            " sort_order INTEGER DEFAULT 0,"
            " is_active BOOLEAN DEFAULT TRUE,"
            " created_at TIMESTAMPTZ DEFAULT now()"
            ")"
        ))
        # Migration: បង្កើតតារាង alerts (ការជូនដំណឹង / Popup បង្ហាញលើ Storefront)
        conn.execute(text(
            "CREATE TABLE IF NOT EXISTS alerts ("
            " id SERIAL PRIMARY KEY,"
            " title VARCHAR DEFAULT '',"
            " message VARCHAR DEFAULT '',"
            " alert_type VARCHAR DEFAULT 'info',"
            " style VARCHAR DEFAULT 'both',"
            " link_url VARCHAR DEFAULT '',"
            " is_active BOOLEAN DEFAULT TRUE,"
            " starts_at TIMESTAMPTZ,"
            " expires_at TIMESTAMPTZ,"
            " created_at TIMESTAMPTZ DEFAULT now(),"
            " updated_at TIMESTAMPTZ DEFAULT now()"
            ")"
        ))
        # Migration: បន្ថែម column image_url ទៅតារាង alerts (រូបភាព Alert / Popup)
        conn.execute(text(
            "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS image_url VARCHAR DEFAULT ''"
        ))
        conn.commit()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()