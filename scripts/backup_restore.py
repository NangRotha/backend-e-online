"""
Backup / Restore — Database Migration (SQLite → SQLite)
======================================================
ឧបករណ៍ Backup / Restore / ផ្លាស់ទិន្នន័យ (SQLite តែមួយប៉ុណ្ណោះ) ដោយមិនបាត់ទិន្នន័យ។

Usage:
    # 1) Export ចេញពី Backend ដែលកំពុងដំណើរការ (តាម API — ត្រូវការគណនី Admin)
    .venv/bin/python scripts/backup_restore.py export --url https://backend-e-online.onrender.com --email admin@example.com --password 'admin12345' --out backup.json

    # 2) Import ចូល Database SQLite បច្ចុប្បន្ន (តាម SQLITE_PATH ឬ backend/ecommerce.db)
    .venv/bin/python scripts/backup_restore.py import --file backup.json --truncate

    # 3) ចម្លងផ្ទាល់ពីឯកសារ SQLite ដើម → Database បច្ចុប្បន្ន (មិនតាម API, passwords គ្រប់)
    SOURCE_SQLITE_PATH=/path/to/old-ecommerce.db .venv/bin/python scripts/backup_restore.py copy-source --truncate

ចំណាំ: ក្រោយ `import` គណនី Users នឹងគ្មានពាក្យសម្ងាត់ដើម (Export លាក់វា)
      ដូច្នេះត្រូវកំណត់ពាក្យសម្ងាត់ Admin ឡើងវិញ៖
      .venv/bin/python create_admin.py admin@example.com --password 'newpass' --reset
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine, select  # noqa: E402

from app import models  # noqa: E402
from app.config import settings  # noqa: E402
from app.database import (  # noqa: E402
    DATABASE_URL,
    Base,
    engine,
)

CHUNK = 500


def _json_default(value):
    """ប្តូរតម្លៃដែល JSON មិនស្គាល់ (datetime) ទៅជាអក្សរ"""
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


# ============================================================
# 1) EXPORT តាម API
# ============================================================
def cmd_export(args):
    import httpx

    base = args.url.rstrip("/")
    with httpx.Client(timeout=120) as client:
        resp = client.post(
            f"{base}/api/auth/login",
            json={"email": args.email, "password": args.password},
        )
        if resp.status_code != 200:
            print(f"❌ Login failed ({resp.status_code}): {resp.text[:200]}")
            sys.exit(1)
        token = resp.json()["access_token"]

        resp = client.get(
            f"{base}/api/admin/export",
            headers={"Authorization": f"Bearer {token}"},
        )
        if resp.status_code != 200:
            print(f"❌ Export failed ({resp.status_code}): {resp.text[:200]}")
            sys.exit(1)
        data = resp.json()

    out = Path(args.out)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=_json_default))
    print(f"✅ Exported → {out}")
    for name, rows in data.items():
        if isinstance(rows, list):
            print(f"   {name:<15} {len(rows)} rows")


# ============================================================
# 2) IMPORT ចូល Database បច្ចុប្បន្ន (SQLite — SQLITE_PATH)
# ============================================================
def _coerce_value(column, value):
    """បំលែងតម្លៃពី JSON (string) ទៅជាប្រភេទដែល Database ត្រូវការ

    ឧ. `"2026-09-16T14:32:47"` → `datetime` ព្រោះ SQLite DateTime column
    ទទួលតែ Python datetime/date ប៉ុណ្ណោះ (បើអត់បំលែងទេ នឹង TypeError)
    """
    if value is None:
        return None

    try:
        python_type = column.type.python_type
    except Exception:
        python_type = None

    if isinstance(value, str):
        if python_type is datetime:
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return value
        if python_type is date:
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
            except ValueError:
                return value
        if python_type is bool:
            return value.strip().lower() in ("1", "true", "yes", "t", "on")
        if python_type is int:
            try:
                return int(float(value))
            except (TypeError, ValueError):
                return value
        if python_type is float:
            try:
                return float(value)
            except (TypeError, ValueError):
                return value
        return value

    # SQLite៖ bool/number ធម្មតាមកជា Python object ស្រាប់
    if python_type is bool and not isinstance(value, bool):
        return bool(value)
    return value


def _insert_rows(conn, table, rows, truncate: bool) -> int:
    if not rows:
        return 0
    if truncate:
        conn.execute(table.delete())

    # យកតែ Column ដែលមានក្នុងតារាង + បំលែងប្រភេទតម្លៃឱ្យត្រូវ
    columns = {c.name: c for c in table.columns}
    payload = [
        {
            name: _coerce_value(columns[name], value)
            for name, value in row.items()
            if name in columns
        }
        for row in rows
    ]
    for i in range(0, len(payload), CHUNK):
        conn.execute(table.insert(), payload[i : i + CHUNK])
    return len(payload)


def _import_data(data: dict, truncate: bool, source_label: str):
    from app import auth as app_auth

    Base.metadata.create_all(bind=engine)
    counts = {}

    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:  # តាមលំដាប់ FK
            rows = data.get(table.name) or []
            if rows and table.name == "users":
                # Export លាក់ hashed_password → ដាក់ពាក្យសម្ងាត់ចៃដន្យជំនួស (Login មិនបាន)
                for row in rows:
                    if not row.get("hashed_password"):
                        row["hashed_password"] = app_auth.hash_password(uuid.uuid4().hex)
            counts[table.name] = _insert_rows(conn, table, rows, truncate)

    print(f"✅ Imported → SQLite: {DATABASE_URL}")
    print(f"   (source: {source_label})")
    for name, count in counts.items():
        if count:
            print(f"   {name:<15} {count} rows")


def cmd_import(args):
    path = Path(args.file)
    if not path.exists():
        print(f"❌ File not found: {path}")
        sys.exit(1)
    data = json.loads(path.read_text())
    _import_data(data, args.truncate, f"backup file {path.name}")
    if data.get("users"):
        print(
            "\n⚠️  គណនី Users គ្មានពាក្យសម្ងាត់ដើមទេ — សូមកំណត់ពាក្យសម្ងាត់ Admin ឡើងវិញ៖\n"
            "   .venv/bin/python create_admin.py <admin-email> --password '<new>' --reset"
        )


# ============================================================
# 3) ចម្លងផ្ទាល់ពីឯកសារ SQLite ដើម → Database បច្ចុប្បន្ន (Passwords គ្រប់)
# ============================================================
def cmd_copy_source(args):
    # ទទួលផ្លូវឯកសារ SQLite ពី --source ឬ Env Var SOURCE_SQLITE_PATH
    raw = (args.source or os.environ.get("SOURCE_SQLITE_PATH", "")).strip()
    if not raw:
        print("❌ សូមផ្តល់ SOURCE_SQLITE_PATH ឬ --source /path/to/ecommerce.db")
        sys.exit(1)

    source_path = Path(raw.replace("sqlite:///", "", 1))
    if not source_path.exists():
        print(f"❌ រកមិនឃើញឯកសារ SQLite: {source_path}")
        sys.exit(1)

    source_url = f"sqlite:///{source_path}"
    if source_url == DATABASE_URL:
        print("⚠️  Source និង Target ជា Database តែមួយ — ឈប់ដើម្បីសុវត្ថិភាព")
        sys.exit(1)

    source = create_engine(source_url, connect_args={"check_same_thread": False})
    print(f"📤 Source: {source_url}")
    print(f"📥 Target: SQLite — {DATABASE_URL}")

    Base.metadata.create_all(bind=engine)
    counts = {}

    with source.connect() as src, engine.begin() as dst:
        for table in Base.metadata.sorted_tables:
            cols = [c.name for c in table.columns]
            try:
                rows = src.execute(select(*[table.c[c] for c in cols])).mappings().all()
            except Exception as exc:
                print(f"   ⏭  {table.name}: skipped ({type(exc).__name__})")
                continue
            counts[table.name] = _insert_rows(
                dst, table, [dict(r) for r in rows], args.truncate
            )

    print("✅ Migration complete")
    for name, count in counts.items():
        print(f"   {name:<15} {count} rows")


def main():
    parser = argparse.ArgumentParser(description="Backup / Restore / Migrate database")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_export = sub.add_parser("export", help="Export ចេញពី API ជា JSON")
    p_export.add_argument("--url", required=True, help="Backend URL")
    p_export.add_argument("--email", required=True, help="Admin email")
    p_export.add_argument("--password", required=True, help="Admin password")
    p_export.add_argument("--out", default="backup.json", help="Output file")
    p_export.set_defaults(func=cmd_export)

    p_import = sub.add_parser("import", help="Import JSON ចូល Database បច្ចុប្បន្ន")
    p_import.add_argument("--file", required=True)
    p_import.add_argument("--truncate", action="store_true", help="លុបទិន្នន័យចាស់មុន Import")
    p_import.set_defaults(func=cmd_import)

    p_copy = sub.add_parser(
        "copy-source",
        help="ចម្លងពីឯកសារ SQLite ដើម ចូល DB បច្ចុប្បន្ន (Passwords គ្រប់)",
    )
    p_copy.add_argument(
        "--source", default="", help="ផ្លូវឯកសារ SQLite (ឬប្រើ Env Var SOURCE_SQLITE_PATH)"
    )
    p_copy.add_argument("--truncate", action="store_true")
    p_copy.set_defaults(func=cmd_copy_source)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
