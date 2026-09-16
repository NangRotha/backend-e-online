from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, declarative_base
from .config import settings
import time

# យក Database URL ពី Environment Variables
# - បើកំណត់ DATABASE_URL / DATABASE_URL_INTERNAL -> PostgreSQL (Render)
# - បើអត់កំណត់ -> SQLite ក្នុងម៉ាស៊ីន (backend/ecommerce.db) ដោយស្វ័យប្រវត្តិ
DATABASE_URL = settings.active_database_url
IS_SQLITE = DATABASE_URL.startswith("sqlite")


def _create_engine():
    """បង្កើត Engine តាមប្រភេទ Database (SQLite ឬ PostgreSQL)"""
    if IS_SQLITE:
        # SQLite — ត្រូវការ check_same_thread=False ព្រោះ FastAPI ប្រើច្រើន Thread
        return create_engine(
            DATABASE_URL,
            connect_args={"check_same_thread": False},
            pool_pre_ping=True,
        )
    # PostgreSQL — connect_timeout: កុំឱ្យជាប់រង់ចាំយូរពេល DNS / បណ្តាញធ្លាក់
    return create_engine(
        DATABASE_URL,
        connect_args={"sslmode": "require", "connect_timeout": 10},
        pool_pre_ping=True,
    )


engine = _create_engine()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# ព្យាយាមភ្ជាប់ឡើងវិញពេល DNS / បណ្តាញធ្លាក់មួយភ្លែត (តែ PostgreSQL ប៉ុណ្ណោះ)
DB_MAX_ATTEMPTS = 10
DB_RETRY_DELAY_SECONDS = 3


def safe_database_url(url: str = None) -> str:
    """បង្ហាញ Database URL ដោយលាក់ Username/Password (កុំឱ្យលេចក្នុង Log)"""
    value = url or DATABASE_URL
    if "@" in value:
        scheme = value.split("://", 1)[0] if "://" in value else ""
        return f"{scheme}://***@{value.split('@', 1)[1]}"
    return value


def _column_default_sql(col) -> str:
    """បង្កើត DEFAULT សម្រាប់ ALTER TABLE ADD COLUMN (បើ Column មាន default ធម្មតា)"""
    default = getattr(col, "default", None)
    if default is None or not getattr(default, "is_scalar", False):
        return ""
    value = default.arg
    if isinstance(value, bool):
        return f" DEFAULT {'TRUE' if value else 'FALSE'}"
    if isinstance(value, (int, float)):
        return f" DEFAULT {value}"
    if isinstance(value, str):
        return " DEFAULT '%s'" % value.replace("'", "''")
    return ""


def _migrate(conn) -> list:
    """Migration ស្វ័យប្រវត្តិ — បន្ថែម Column/Index ដែលមានក្នុង Model
    តែគ្មានក្នុង Database ដែលមានស្រាប់។

    ដំណើរការទាំង **PostgreSQL** និង **SQLite** (មិនប្រើ
    `ALTER TABLE ... IF NOT EXISTS` ព្រោះ SQLite មិនគាំទ្រ)។
    """
    inspector = inspect(conn)
    existing_tables = set(inspector.get_table_names())
    changes = []

    for table in Base.metadata.sorted_tables:
        if table.name not in existing_tables:
            continue  # តារាងថ្មី -> create_all បង្កើតរួចហើយ

        # 1) Columns ដែលខ្វះ
        have = {c["name"] for c in inspector.get_columns(table.name)}
        for col in table.columns:
            if col.name in have:
                continue
            col_type = col.type.compile(dialect=conn.dialect)
            conn.execute(
                text(
                    f'ALTER TABLE "{table.name}" '
                    f'ADD COLUMN "{col.name}" {col_type}{_column_default_sql(col)}'
                )
            )
            changes.append(f"{table.name}.{col.name}")

        # 2) Index ដែលខ្វះ (ឧ. index លើ telegram_id)
        try:
            have_indexes = {ix["name"] for ix in inspector.get_indexes(table.name)}
        except Exception:
            have_indexes = set()
        for ix in table.indexes:
            if not ix.name or ix.name in have_indexes:
                continue
            cols = ", ".join(f'"{c.name}"' for c in ix.columns)
            unique = "UNIQUE " if ix.unique else ""
            conn.execute(
                text(
                    f'CREATE {unique}INDEX IF NOT EXISTS "{ix.name}" '
                    f'ON "{table.name}" ({cols})'
                )
            )
            changes.append(f"index {ix.name}")

    return changes


def _init_db_once() -> list:
    """បង្កើតតារាងទាំងអស់ និងធ្វើ Migration ស្វ័យប្រវត្តិ (idempotent)

    - តារាងថ្មី -> `Base.metadata.create_all()` បង្កើតឱ្យ
    - Column/Index ថ្មី (ក្នុង Model តែគ្មានក្នុង DB ចាស់) -> `_migrate()` បន្ថែមឱ្យ
    ដំណើរការទាំង **SQLite** និង **PostgreSQL**
    """
    # ធានាថា Model ទាំងអស់ត្រូវបានចុះឈ្មោះក្នុង `Base.metadata` មុនពេល create_all
    # (import ក្នុង Function ដើម្បីកុំឱ្យមាន Circular Import)
    from . import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    with engine.connect() as conn:
        changes = _migrate(conn)
        conn.commit()
    return changes

def init_db():
    """បង្កើតតារាង + Migration ព្រមទាំងព្យាយាមភ្ជាប់ឡើងវិញ (តែ PostgreSQL)

    - **SQLite** (Local / File)៖ អត់មានបញ្ហា Network -> ព្យាយាមតែម្តង
    - **PostgreSQL** (Render)៖ ព្យាយាម 10 ដង ព្រោះ DNS/Network អាចធ្លាក់មួយភ្លែត
    """
    label = "SQLite" if IS_SQLITE else "PostgreSQL"
    print(f"🗄️  Database ({label}): {safe_database_url()}", flush=True)

    attempts = 1 if IS_SQLITE else DB_MAX_ATTEMPTS
    last_exc = None

    for attempt in range(1, attempts + 1):
        try:
            changes = _init_db_once()
            if changes:
                print(f"✅ Migration: បន្ថែម {', '.join(changes)}", flush=True)
            return
        except Exception as e:
            last_exc = e
            print(
                f"⚠️  Database connection failed (attempt {attempt}/{attempts}): "
                f"{type(e).__name__}: {e}",
                flush=True,
            )
            if attempt < attempts:
                print(
                    f"    Retrying in {DB_RETRY_DELAY_SECONDS}s... "
                    f"(កំពុងព្យាយាមភ្ជាប់ Database ឡើងវិញ)",
                    flush=True,
                )
                time.sleep(DB_RETRY_DELAY_SECONDS)

    hint = (
        "  1. ផ្លូវឯកសារ SQLite ខុស ឬថតគ្មានសិទ្ធិសរសេរ (SQLITE_PATH)\n"
        if IS_SQLITE
        else "  1. No internet / DNS is down — check your connection.\n"
        "  2. The database host is unreachable / Postgres ផុតកំណត់\n"
    )
    raise RuntimeError(
        f"Could not connect to the database ({label}: {safe_database_url()}) "
        f"after {attempts} attempt(s).\n"
        "Possible causes:\n"
        f"{hint}"
        "  3. Wrong DATABASE_URL in backend/.env — បើចង់ប្រើ SQLite សូមទុក DATABASE_URL ទទេ\n"
        f"Last error: {last_exc}"
    ) from last_exc


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()