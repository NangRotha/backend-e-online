from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from typing import Optional
from . import models, auth
from .database import get_db

# FastAPI នឹងអាន `Authorization: Bearer <token>` ពី Request Header
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
):
    """ទាញយក User បច្ចុប្បន្នពី JWT Token (ផ្ញើមកជាមួយ `Authorization: Bearer ...`)"""
    payload = auth.decode_token(token)
    if not payload or "sub" not in payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = db.query(models.User).filter(models.User.email == payload["sub"]).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user

def get_current_admin(current_user: models.User = Depends(get_current_user)):
    """ទាញយក User បច្ចុប្បន្ន ហើយពិនិត្យថាជា Admin ឬអត់"""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user


# ============================================================
# Guest Checkout — Token ជាជម្រើស (Optional)
# ============================================================
# ⚠️ Frontend User លែងមាន Login/Sign Up -> អតិថិជនអាចបញ្ជាទិញបានដោយគ្មានគណនី
# បើអ្នកប្រើផ្ញើ Token មក (ឧ. Admin កំពុងសាកល្បង) យើងនឹងភ្ជាប់ Order ជាមួយ User នោះ
oauth2_scheme_optional = OAuth2PasswordBearer(
    tokenUrl="/api/auth/login", auto_error=False
)

def get_current_user_optional(
    token: Optional[str] = Depends(oauth2_scheme_optional),
    db: Session = Depends(get_db),
):
    """ទាញយក User បច្ចុប្បន្នបើមាន Token ត្រឹមត្រូវ — បើគ្មាន -> None (Guest)"""
    if not token:
        return None
    payload = auth.decode_token(token)
    if not payload or "sub" not in payload:
        return None
    return db.query(models.User).filter(models.User.email == payload["sub"]).first()
