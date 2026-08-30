from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from pathlib import Path
from .. import models, schemas, auth
from ..database import get_db
from ..deps import get_current_user
from ..storage import ALLOWED_EXTENSIONS, save_upload

router = APIRouter(prefix="/api/users", tags=["Users"])

# ==========================================
# User: មើល Profile របស់ខ្លួនឯង
# ==========================================
@router.get("/me", response_model=schemas.UserOut)
def get_me(current_user: models.User = Depends(get_current_user)):
    return current_user

# ==========================================
# User: កែប្រែ Profile (ឈ្មោះ + រូប Profile)
# ==========================================
@router.put("/me", response_model=schemas.UserOut)
def update_profile(
    payload: schemas.ProfileUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name is required")
    current_user.name = name
    current_user.profile_image = payload.profile_image.strip()
    db.commit()
    db.refresh(current_user)
    return current_user

# ==========================================
# User: ប្តូរពាក្យសម្ងាត់ (តម្រូវឲ្យបញ្ចូលពាក្យសម្ងាត់បច្ចុប្បន្ន)
# ==========================================
@router.put("/me/password")
def change_password(
    payload: schemas.PasswordChange,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    if len(payload.new_password) < 6:
        raise HTTPException(
            status_code=400,
            detail="New password must be at least 6 characters",
        )
    if not auth.verify_password(payload.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    current_user.hashed_password = auth.hash_password(payload.new_password)
    db.commit()
    return {"message": "Password updated successfully"}

# ==========================================
# User: Upload រូប Profile ពីកុំព្យូទ័រ
# ==========================================
@router.post("/me/upload-image")
async def upload_profile_image(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    filename = file.filename or ""
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext or 'none'}'. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    content = await file.read()
    # Cloudinary (បើកំណត់) — បើអត់ រក្សាទុកលើ Local Disk ដូចពីមុន
    result = save_upload(content, filename, folder="profile")

    # រក្សាទុក URL និងបញ្ជូន Profile ថ្មីមកវិញ
    current_user.profile_image = result["url"]
    db.commit()
    db.refresh(current_user)
    return {
        "url": result["url"],
        "user": schemas.UserOut.model_validate(current_user).model_dump(),
    }
