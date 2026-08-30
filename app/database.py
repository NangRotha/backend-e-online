from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base
from .config import settings
import time

# យក Database URL ពី Environment Variables (បង្កើតក្នុង .env ឬ Render Dashboard)
DATABASE_URL = settings.active_database_url

# បង្កើត engine សម្រាប់ភ្ជាប់ទៅ PostgreSQL (Render)
# connect_timeout: កុំឱ្យជាប់រង់ចាំយូរពេល DNS / បណ្តាញធ្លាក់
engine = create_engine(
    DATABASE_URL,
    connect_args={"sslmode": "require", "connect_timeout": 10},
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# ព្យាយាមភ្ជាប់ឡើងវិញពេល DNS / បណ្តាញធ្លាក់មួយភ្លែត
DB_MAX_ATTEMPTS = 10
DB_RETRY_DELAY_SECONDS = 3


def _init_db_once():
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


def init_db():
    """បង្កើតតារាង + Migration ជាមួយការព្យាយាមភ្ជាប់ឡើងវិញ
    (ដោះស្រាយបញ្ហា DNS / បណ្តាញធ្លាក់មួយភ្លែត ដែលបណ្តាលឱ្យ
    'could not translate host name')"""
    last_exc = None
    for attempt in range(1, DB_MAX_ATTEMPTS + 1):
        try:
            _init_db_once()
            return
        except Exception as e:
            last_exc = e
            print(
                f"⚠️  Database connection failed (attempt {attempt}/{DB_MAX_ATTEMPTS}): "
                f"{type(e).__name__}: {e}"
            )
            if attempt < DB_MAX_ATTEMPTS:
                print(
                    f"    Retrying in {DB_RETRY_DELAY_SECONDS}s... "
                    f"(កំពុងព្យាយាមភ្ជាប់ Database ឡើងវិញ)"
                )
                time.sleep(DB_RETRY_DELAY_SECONDS)

    raise RuntimeError(
        "Could not connect to the database after "
        f"{DB_MAX_ATTEMPTS} attempts.\n"
        "Possible causes:\n"
        "  1. No internet / DNS is down — check your connection.\n"
        "  2. The database host is unreachable — run:\n"
        "     nc -vz dpg-da8q4obtqb8s73evcl20-a.singapore-postgres.render.com 5432\n"
        "  3. Wrong DATABASE_URL in backend/.env\n"
        f"Last error: {last_exc}"
    ) from last_exc


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()