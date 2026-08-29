import random
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from . import models
from .config import settings

def generate_otp() -> str:
    """បង្កើតលេខ OTP 6 ខ្ទង់"""
    return f"{random.randint(0, 999999):06d}"

def create_otp(db: Session, email: str) -> str:
    """បង្កើត OTP ថ្មី និងបិទ (used) លេខកូដចាស់ដែលមិនទាន់បានប្រើ"""
    db.query(models.OtpCode).filter(
        models.OtpCode.email == email,
        models.OtpCode.used == False,
    ).update({models.OtpCode.used: True}, synchronize_session=False)

    code = generate_otp()
    expires_at = datetime.utcnow() + timedelta(minutes=settings.OTP_EXPIRE_MINUTES)
    db.add(models.OtpCode(email=email, code=code, expires_at=expires_at, used=False))
    db.commit()
    return code

def verify_otp(db: Session, email: str, code: str) -> bool:
    """ពិនិត្យ OTP ត្រឹមត្រូវ និងមិនទាន់ផុតកំណត់"""
    record = db.query(models.OtpCode).filter(
        models.OtpCode.email == email,
        models.OtpCode.code == code,
        models.OtpCode.used == False,
    ).order_by(models.OtpCode.id.desc()).first()

    if not record:
        return False
    if record.expires_at and record.expires_at.replace(tzinfo=None) < datetime.utcnow():
        return False

    record.used = True
    db.commit()
    return True
