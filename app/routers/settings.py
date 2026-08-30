from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from .. import models, schemas
from ..database import get_db
from ..deps import get_current_admin
from ..storage import delete_upload_by_url
from ..ws_manager import manager

router = APIRouter(prefix="/api/settings", tags=["Settings"])

# Admin: ប្តូរ Logo ឬ Site Name
@router.put("/admin/update")
def update_setting(
    setting: schemas.SiteSettingUpdate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    db_setting = db.query(models.SiteSetting).filter(models.SiteSetting.key == setting.key).first()
    if db_setting:
        old_value = db_setting.value
        # លុប Logo ចាស់ពី Cloudinary / Local Disk ពេលប្តូរទៅ Logo ថ្មី
        if setting.key == "site_logo" and old_value and old_value != setting.value:
            delete_upload_by_url(old_value)
        db_setting.value = setting.value
    else:
        new_setting = models.SiteSetting(key=setting.key, value=setting.value)
        db.add(new_setting)
    db.commit()
    # ជូនដំណឹង Storefront ឲ្យបញ្ចូល Logo / Site Name ថ្មីដោយស្វ័យប្រវត្តិ
    background_tasks.add_task(
        manager.broadcast,
        {"type": "settings_changed", "message": "Site settings have been updated"},
    )
    return {"message": "Setting updated successfully"}

# ទាញយក Setting ទាំងអស់មកបង្ហាញក្នុង Frontend
@router.get("/all")
def get_settings(db: Session = Depends(get_db)):
    settings = db.query(models.SiteSetting).all()
    return {s.key: s.value for s in settings}