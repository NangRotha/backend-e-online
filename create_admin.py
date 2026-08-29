"""
បង្កើតគណនី Admin ដំបូង
================================
Usage:
    .venv/bin/python create_admin.py user@example.com

ចំណាំ: ត្រូវចុះឈ្មោះ (register) គណនីនោះសិន មុនពេលប្រើ script នេះ។
"""
import sys

sys.path.insert(0, ".")

from app.database import SessionLocal
from app import models

def main():
    if len(sys.argv) < 2:
        print("Usage: .venv/bin/python create_admin.py user@example.com")
        sys.exit(1)

    email = sys.argv[1].strip().lower()
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.email == email).first()
        if not user:
            print(f"❌ User '{email}' not found. Register the account first.")
            sys.exit(1)
        user.role = "admin"
        db.commit()
        print(f"✅ '{email}' is now an ADMIN. You can log in to the admin panel.")
    finally:
        db.close()

if __name__ == "__main__":
    main()
