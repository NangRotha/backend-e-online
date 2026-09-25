from sqlalchemy import create_engine, inspect, text, event
from sqlalchemy.orm import sessionmaker, declarative_base
import os

from .config import DEFAULT_SQLITE_FILE, settings

# ============================================================
# 🗄️ Database = **SQLite តែមួយប៉ុណ្ណោះ**
# ------------------------------------------------------------
# - ឯកសារ DB ស្ថិតតាម `SQLITE_PATH`, `DATABASE_URL` (sqlite://) ឬ `backend/ecommerce.db`
# - បើរកឃើញ DATABASE_URL បែប PostgreSQL សល់ពីមុន វានឹងរំលងដោយសុវត្ថិភាព និងបន្តប្រើ SQLite
# ============================================================
DATABASE_URL = f"sqlite:///{settings.sqlite_file_path}"

# URL ដែលកំពុងប្រើពិតប្រាកដ (ខុសពី DATABASE_URL បើមាន Fallback)
EFFECTIVE_DATABASE_URL = DATABASE_URL


def _configure_sqlite_pragmas(engine_obj):
    """កំណត់ SQLite PRAGMA សម្រាប់បង្កើនល្បឿន សុវត្ថិភាព និងការពារ database lock ពេលមាន request ច្រើន"""
    @event.listens_for(engine_obj, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA temp_store=MEMORY")
        except Exception:
            pass
        finally:
            cursor.close()
    return engine_obj


def _create_engine():
    """បង្កើត SQLite Engine (បង្កើតថតមេរបស់ឯកសារ DB បើចាំបាច់)"""
    global EFFECTIVE_DATABASE_URL

    if settings.has_legacy_postgres_url:
        print(
            "ℹ️  Environment: រកឃើញ DATABASE_URL (PostgreSQL) — Backend នេះដំណើរការលើ SQLite "
            "ហើយកំពុងប្រើប្រាស់ SQLite ដោយស្វ័យប្រវត្តិ (PostgreSQL ត្រូវបានរំលង)។\n"
            "   👉 Tip: អ្នកអាចលុប DATABASE_URL, DATABASE_URL_INTERNAL, និង DB_ENGINE ចេញពី Render Environment Variables បាន។",
            flush=True,
        )

    target = settings.sqlite_file_path
    directory = os.path.dirname(target)
    if directory:
        try:
            os.makedirs(directory, exist_ok=True)
            try:
                os.chmod(directory, 0o700)  # Directory accessible only by owner
            except Exception:
                pass
            # បើជាថត /var/data លើ Persistent Disk -> បង្កើត uploads directory ផងដែរ
            if directory == "/var/data" or directory.startswith("/var/data"):
                os.makedirs("/var/data/uploads", exist_ok=True)
        except Exception as exc:  # noqa: BLE001
            # ⚠️ ឧ. Render Free Plan: /var/data មិនមាន (គ្មាន Persistent Disk)
            fallback = f"sqlite:///{DEFAULT_SQLITE_FILE}"
            print(
                f"⚠️  SQLite: មិនអាចបង្កើតថត '{directory}' ({type(exc).__name__}) "
                f"→ ប្រើ '{DEFAULT_SQLITE_FILE}' ជំនួស។ "
                "(លើ Render សូមបន្ថែម Persistent Disk សម្រាប់ /var/data)",
                flush=True,
            )
            EFFECTIVE_DATABASE_URL = fallback
            eng = create_engine(
                fallback,
                connect_args={"check_same_thread": False},
                pool_pre_ping=True,
            )
            return _configure_sqlite_pragmas(eng)

    # បើនៅលើ Disk (/var/data) ហើយ DB មិនទាន់មាន (Disk ទើបតែបង្កើតថ្មី) តែមាន default DB
    # -> ចម្លងពី template មក ដើម្បីកុំឱ្យបាត់ Categories, Products, Site Settings ដំបូង
    if not os.path.exists(target) and DEFAULT_SQLITE_FILE.exists() and str(DEFAULT_SQLITE_FILE) != target:
        import shutil
        try:
            shutil.copy2(DEFAULT_SQLITE_FILE, target)
            print(f"📦 Persistent Disk: បានចម្លងទិន្នន័យដំបូងពី {DEFAULT_SQLITE_FILE.name} ទៅកាន់ {target}", flush=True)
        except Exception as e:
            print(f"ℹ️ Persistent Disk: បង្កើតទិន្នន័យថ្មីនៅ {target} ({e})", flush=True)

    # កំណត់សិទ្ធិឯកសារ Database (0600 = Read/Write តែម្ចាស់ Process ប៉ុណ្ណោះ ការពារការលួចអានពី user ផ្សេង)
    if os.path.exists(target):
        try:
            os.chmod(target, 0o600)
        except Exception:
            pass

    EFFECTIVE_DATABASE_URL = f"sqlite:///{target}"
    # SQLite ត្រូវការ `check_same_thread=False` ព្រោះ FastAPI ប្រើច្រើន Thread
    eng = create_engine(
        EFFECTIVE_DATABASE_URL,
        connect_args={"check_same_thread": False},
        pool_pre_ping=True,
    )
    return _configure_sqlite_pragmas(eng)


engine = _create_engine()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

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

    ធ្វើការជាមួយ SQLite (មិនប្រើ `ALTER TABLE ... IF NOT EXISTS`
    ព្រោះ SQLite មិនគាំទ្រ)។
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
    """បង្កើតតារាង + Migration (SQLite — គ្មាន Network ដូច្នេះព្យាយាមតែម្តង)"""
    print(f"🗄️  Database (SQLite): {EFFECTIVE_DATABASE_URL}", flush=True)

    try:
        changes = _init_db_once()
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            f"Could not initialise the SQLite database ({EFFECTIVE_DATABASE_URL}).\n"
            "Possible causes:\n"
            "  1. ផ្លូវឯកសារ SQLite ខុស ឬថតគ្មានសិទ្ធិសរសេរ (SQLITE_PATH)\n"
            "  2. ឯកសារ DB ខូច ឬ Lock ដោយ Process ផ្សេង (សូមបិទ Server ចាស់)\n"
            f"Last error: {type(exc).__name__}: {exc}"
        ) from exc

    if changes:
        print(f"✅ Migration: បន្ថែម {', '.join(changes)}", flush=True)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
