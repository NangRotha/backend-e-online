"""
បង្កើត / ដំឡើងគណនី Admin
========================
Storefront លែងមាន Sign Up ទៀតហើយ ដូច្នេះ script នេះបង្កើតគណនី Admin ផ្ទាល់។

Usage:
    # បង្កើតថ្មី បើមិនទាន់មាន (កំណត់ពាក្យសម្ងាត់ខ្លួនឯង)
    .venv/bin/python create_admin.py admin@example.com --password 'admin12345' --name 'Store Admin'

    # បង្កើតដោយពាក្យសម្ងាត់ស្វ័យប្រវត្តិ
    .venv/bin/python create_admin.py admin@example.com

    # ដំឡើងគណនីដែលមានរួចជា Admin
    .venv/bin/python create_admin.py user@mystore.com

⚠️  សូមប្រើអ៊ីមែលធម្មតា (ឧ. admin@example.com ឬ admin@mystore.com)។
    Domain បម្រុង (reserved) ដូចជា `.local`, `.test`, `.invalid`, `.localhost`
    នឹងត្រូវ API បដិសេធពេល Login (Pydantic EmailStr)។
"""
import argparse
import secrets
import sys

sys.path.insert(0, ".")

from app import auth, models  # noqa: E402
from app.database import SessionLocal, init_db  # noqa: E402

# Domain បម្រុងដែល API មិនអនុញ្ញាត (Pydantic EmailStr / email-validator)
RESERVED_SUFFIXES = (".local", ".localhost", ".test", ".invalid", ".example")


def validate_email(email: str) -> str | None:
    """ត្រឡប់សារកំហុស បើអ៊ីមែលមិនអាចប្រើ Login បាន"""
    try:
        from email_validator import EmailNotValidError, validate_email as _validate

        _validate(email, check_deliverability=False)
        return None
    except EmailNotValidError as exc:
        return str(exc)
    except Exception:
        # បើ email-validator គ្មាន -> ពិនិត្យយ៉ាងសាមញ្ញ
        if "@" not in email or "." not in email.split("@")[-1]:
            return "invalid email address"
        if email.lower().endswith(RESERVED_SUFFIXES):
            return "reserved email domain (use a real domain, e.g. admin@example.com)"
        return None


def main():
    parser = argparse.ArgumentParser(description="Create or promote an admin account")
    parser.add_argument("email", help="Admin email address (e.g. admin@example.com)")
    parser.add_argument(
        "--password",
        default=None,
        help="Password (បើមិនផ្តល់ -> បង្កើតឱ្យស្វ័យប្រវត្តិ)",
    )
    parser.add_argument("--name", default=None, help="Display name (default: Admin)")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="កំណត់ពាក្យសម្ងាត់ថ្មី ទោះគណនីមានរួច (ត្រូវភ្ជាប់ជាមួយ --password)",
    )
    args = parser.parse_args()

    email = args.email.strip().lower()

    # ពិនិត្យអ៊ីមែលជាមុន — បើ domain បម្រុង នោះ Login នឹងបរាជ័យ (422)
    problem = validate_email(email)
    if problem:
        print(f"❌ Email '{email}' ប្រើមិនបានទេ: {problem}")
        print("   សូមប្រើអ៊ីមែលធម្មតា ឧ. admin@example.com")
        sys.exit(1)

    # បង្កើតតារាងឱ្យបានមុន (បើ Database ថ្មី)
    init_db()

    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.email == email).first()

        if user:
            if args.reset and args.password:
                # កំណត់ពាក្យសម្ងាត់ថ្មី (ប្រើក្រោយ Import/ផ្លាស់ Database)
                user.hashed_password = auth.hash_password(args.password)
                user.role = "admin"
                user.email_verified = True
                if args.name:
                    user.name = args.name.strip() or user.name
                db.commit()
                print(f"✅ Password reset for '{email}' (role: admin)")
                return

            if user.role == "admin":
                print(f"ℹ️  '{email}' is already an ADMIN.")
                print("   (បើចង់ប្តូរពាក្យសម្ងាត់ -> បន្ថែម --password '<new>' --reset)")
                return
            user.role = "admin"
            db.commit()
            print(f"✅ '{email}' is now an ADMIN. You can log in to the admin panel.")
            return

        # បង្កើតគណនីថ្មី
        password = args.password or secrets.token_urlsafe(9)
        name = (args.name or "Admin").strip() or "Admin"
        user = models.User(
            name=name,
            email=email,
            hashed_password=auth.hash_password(password),
            role="admin",
            email_verified=True,  # Admin មិនត្រូវការ OTP
        )
        db.add(user)
        db.commit()
        print("✅ Admin account created")
        print(f"   Email    : {email}")
        print(f"   Password : {password}")
        print("   (សូមប្តូរពាក្យសម្ងាត់ក្រោយពេលចូលដំបូង)")
    finally:
        db.close()


if __name__ == "__main__":
    main()
