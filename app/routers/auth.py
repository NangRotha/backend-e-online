from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
import uuid
from .. import models, schemas, auth, otp
from ..database import get_db
from ..deps import get_current_admin
from ..email_sender import send_otp_email, email_status
from ..config import settings
from ..telegram import verify_telegram_auth, telegram_configured

router = APIRouter(prefix="/api/auth", tags=["Auth"])

@router.get("/email-config")
def email_config():
    """ពិនិត្យថា Email (OTP) បានបើកដំណើរការលើ Server ឬអត់
    (សម្រាប់ Admin ពិនិត្យលើ Production: curl https://<backend>/api/auth/email-config)"""
    return email_status()

@router.post("/test-email")
def send_test_email(
    payload: schemas.TestEmailRequest,
    admin: models.User = Depends(get_current_admin),
):
    """Admin: ផ្ញើ OTP សាកល្បងទៅអាសយដ្ឋានណាមួយ — ពិនិត្យ SMTP លើ Production ភ្លាមៗ
    (ផ្ញើ code 123456 ហើយបង្ហាញ last_error បើបរាជ័យ)"""
    result = send_otp_email(payload.email, "123456")
    return {
        "sent": result["sent"],
        "reason": result["reason"],
        "email": payload.email,
        "status": email_status(),
    }

@router.post("/register", response_model=schemas.RegisterResponse)
def register(user: schemas.UserCreate, db: Session = Depends(get_db)):
    existing = db.query(models.User).filter(models.User.email == user.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    hashed_pw = auth.hash_password(user.password)
    new_user = models.User(
        name=user.name,
        email=user.email,
        hashed_password=hashed_pw,
        email_verified=False,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # បង្កើត OTP និងផ្ញើទៅអ៊ីមែល (ឬបង្ហាញក្នុង Console បើ SMTP មិនទាន់កំណត់)
    code = otp.create_otp(db, user.email)
    result = send_otp_email(user.email, code)

    return {
        "message": "Registration successful. Check your email for the verification code.",
        "email": user.email,
        "dev_otp": result.get("dev_otp"),
        "otp_reason": result.get("reason"),
    }

@router.post("/verify-otp", response_model=schemas.Token)
def verify_otp(payload: schemas.VerifyOtpRequest, db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter(models.User.email == payload.email).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")
    if db_user.email_verified:
        raise HTTPException(status_code=400, detail="Email already verified")

    if not otp.verify_otp(db, payload.email, payload.code.strip()):
        raise HTTPException(status_code=400, detail="Invalid or expired verification code")

    db_user.email_verified = True
    db.commit()
    db.refresh(db_user)

    token = auth.create_access_token({"sub": db_user.email, "role": db_user.role})
    return {"access_token": token, "token_type": "bearer"}

@router.post("/resend-otp")
def resend_otp(payload: schemas.ResendOtpRequest, db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter(models.User.email == payload.email).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")
    if db_user.email_verified:
        raise HTTPException(status_code=400, detail="Email already verified")

    code = otp.create_otp(db, payload.email)
    result = send_otp_email(payload.email, code)

    return {
        "message": "A new verification code has been sent.",
        "email": payload.email,
        "dev_otp": result.get("dev_otp"),
        "otp_reason": result.get("reason"),
    }

@router.post("/login", response_model=schemas.Token)
def login(user: schemas.UserLogin, db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter(models.User.email == user.email).first()
    if not db_user or not auth.verify_password(user.password, db_user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not db_user.email_verified:
        raise HTTPException(
            status_code=403,
            detail="Email not verified. Please verify your email with the OTP code first.",
        )

    token = auth.create_access_token({"sub": db_user.email, "role": db_user.role})
    return {"access_token": token, "token_type": "bearer"}

@router.get("/telegram/config")
def telegram_config():
    """ផ្ញើ bot username ទៅ Frontend ដើម្បីបង្ហាញប៊ូតុង Login with Telegram"""
    return {
        "enabled": telegram_configured(),
        "bot_username": settings.TELEGRAM_BOT_USERNAME,
    }

@router.post("/telegram", response_model=schemas.Token)
def telegram_login(payload: schemas.TelegramAuthData, db: Session = Depends(get_db)):
    """
    Register/Login ជាមួយ Telegram៖
    - បើ telegram_id នៅមិនទាន់មានក្នុង DB -> បង្កើតគណនីថ្មីដោយស្វ័យប្រវត្តិ (Register)
    - បើមានរួចហើយ -> Login
    """
    if not telegram_configured():
        raise HTTPException(status_code=400, detail="Telegram login is not configured")

    data = payload.dict()
    if not verify_telegram_auth(data):
        raise HTTPException(status_code=400, detail="Telegram authentication failed. Please try again.")

    telegram_id = payload.id
    db_user = db.query(models.User).filter(models.User.telegram_id == telegram_id).first()

    if not db_user:
        # ===== Register ថ្មីតាម Telegram =====
        username = payload.username or f"tg_{telegram_id}"
        name = (payload.first_name or username)
        if payload.last_name:
            name = f"{name} {payload.last_name}"

        email = f"telegram_{telegram_id}@telegram.local"
        # បើ email placeholder ពិតជាប៉ះទង្គិច (ករណីកម្រ) -> បន្ថែមលេខ
        if db.query(models.User).filter(models.User.email == email).first():
            email = f"telegram_{telegram_id}_{uuid.uuid4().hex[:8]}@telegram.local"

        db_user = models.User(
            name=name.strip(),
            email=email,
            hashed_password=auth.hash_password(str(uuid.uuid4())),  # គ្មាន password សម្រាប់ Telegram login
            role="user",
            email_verified=True,  # Telegram បានបញ្ជាក់អត្តសញ្ញាណរួចហើយ
            telegram_id=telegram_id,
        )
        db.add(db_user)
        db.commit()
        db.refresh(db_user)

    token = auth.create_access_token({"sub": db_user.email, "role": db_user.role})
    return {"access_token": token, "token_type": "bearer"}
