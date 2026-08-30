from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, UploadFile, File
from sqlalchemy.orm import Session
from pathlib import Path
from typing import List
from datetime import datetime, timezone
from .. import models, schemas
from ..database import get_db
from ..deps import get_current_admin
from ..ws_manager import broadcast_alerts_changed
from ..storage import ALLOWED_EXTENSIONS, save_upload

router = APIRouter(prefix="/api", tags=["Alerts"])

VALID_TYPES = {"info", "success", "warning", "danger"}
VALID_STYLES = {"banner", "popup", "both"}

def _validate(payload: schemas.AlertCreate):
    """ពិនិត្យប្រភេទ Alert និង Style ដែលអនុញ្ញាត"""
    if payload.alert_type not in VALID_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"alert_type must be one of: {', '.join(sorted(VALID_TYPES))}",
        )
    if payload.style not in VALID_STYLES:
        raise HTTPException(
            status_code=400,
            detail=f"style must be one of: {', '.join(sorted(VALID_STYLES))}",
        )
    if payload.starts_at and payload.expires_at and payload.starts_at > payload.expires_at:
        raise HTTPException(
            status_code=400,
            detail="starts_at must be earlier than expires_at",
        )

def _broadcast(background_tasks: BackgroundTasks):
    """ជូនដំណឹង Storefront ឲ្យផ្ទុក Alert / Popup ថ្មីដោយស្វ័យប្រវត្តិ"""
    background_tasks.add_task(broadcast_alerts_changed)

# ==========================================
# User: បង្ហាញ Alert សកម្ម (ស្ថិតក្នុងរយៈពេលដែលកំណត់) — សម្រាប់ Storefront
# ==========================================
@router.get("/alerts", response_model=List[schemas.AlertOut])
def get_active_alerts(db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    return (
        db.query(models.Alert)
        .filter(models.Alert.is_active == True)
        .filter(
            (models.Alert.starts_at.is_(None)) | (models.Alert.starts_at <= now),
            (models.Alert.expires_at.is_(None)) | (models.Alert.expires_at >= now),
        )
        .order_by(models.Alert.created_at.desc(), models.Alert.id.desc())
        .all()
    )

# ==========================================
# Admin: បង្ហាញ Alert ទាំងអស់ (រួមទាំង Alert ដែលបិទ / ផុតកំណត់)
# ==========================================
@router.get("/admin/alerts", response_model=List[schemas.AlertOut])
def get_admin_alerts(
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    return (
        db.query(models.Alert)
        .order_by(models.Alert.created_at.desc(), models.Alert.id.desc())
        .all()
    )

# ==========================================
# Admin: Upload រូបភាពពីកុំព្យូទ័រ សម្រាប់ Alert / Popup
# ==========================================
@router.post("/admin/alerts/upload")
async def upload_alert_image(
    file: UploadFile = File(...),
    admin: models.User = Depends(get_current_admin),
):
    filename = file.filename or ""
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported file type '{ext or 'none'}'. "
                f"Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
            ),
        )

    content = await file.read()
    return save_upload(content, filename, folder="alerts")

# ==========================================
# Admin: បង្កើត Alert ថ្មី
# ==========================================
@router.post("/admin/alerts", response_model=schemas.AlertOut)
def create_alert(
    payload: schemas.AlertCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    _validate(payload)
    alert = models.Alert(**payload.dict())
    db.add(alert)
    db.commit()
    db.refresh(alert)
    _broadcast(background_tasks)
    return alert

# ==========================================
# Admin: កែប្រែ Alert
# ==========================================
@router.put("/admin/alerts/{alert_id}", response_model=schemas.AlertOut)
def update_alert(
    alert_id: int,
    payload: schemas.AlertUpdate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    alert = db.query(models.Alert).filter(models.Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    _validate(payload)
    for key, value in payload.dict().items():
        setattr(alert, key, value)
    db.commit()
    db.refresh(alert)
    _broadcast(background_tasks)
    return alert

# ==========================================
# Admin: លុប Alert
# ==========================================
@router.delete("/admin/alerts/{alert_id}")
def delete_alert(
    alert_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    alert = db.query(models.Alert).filter(models.Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    db.delete(alert)
    db.commit()
    _broadcast(background_tasks)
    return {"message": "Alert deleted", "id": alert_id}
