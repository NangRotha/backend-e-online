from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks
from sqlalchemy.orm import Session
from pathlib import Path
from typing import List
from .. import models, schemas
from ..database import get_db
from ..deps import get_current_admin
from ..storage import ALLOWED_MEDIA_EXTENSIONS, save_upload
from ..ws_manager import manager

router = APIRouter(prefix="/api", tags=["Slides"])

VALID_MEDIA_TYPES = {"image", "video", "youtube"}

def _validate(payload: schemas.SlideCreate):
    """ពិនិត្យប្រភេទ Media និង URL ដែលត្រូវការ"""
    if payload.media_type not in VALID_MEDIA_TYPES:
        raise HTTPException(
            status_code=400,
            detail="media_type must be 'image', 'video' or 'youtube'",
        )
    if payload.media_type == "youtube":
        if not payload.youtube_url.strip():
            raise HTTPException(
                status_code=400,
                detail="YouTube URL is required for media_type 'youtube'",
            )
    else:
        if not payload.media_url.strip():
            raise HTTPException(
                status_code=400,
                detail="Media URL (image or video) is required",
            )

def _broadcast_slides_changed(background_tasks: BackgroundTasks):
    """ជូនដំណឹង Storefront ឲ្យផ្ទុក Slide ថ្មីដោយស្វ័យប្រវត្តិ"""
    background_tasks.add_task(
        manager.broadcast,
        {"type": "slides_changed", "message": "Slides have been updated"},
    )

# ==========================================
# User: បង្ហាញ Slide សកម្មទាំងអស់ (Slider លើ Storefront)
# ==========================================
@router.get("/slides", response_model=List[schemas.SlideOut])
def get_slides(db: Session = Depends(get_db)):
    return (
        db.query(models.Slide)
        .filter(models.Slide.is_active == True)
        .order_by(models.Slide.sort_order.asc(), models.Slide.id.asc())
        .all()
    )

# ==========================================
# Admin: បង្ហាញ Slide ទាំងអស់ (រួមទាំង Slide ដែលបិទ)
# ==========================================
@router.get("/admin/slides", response_model=List[schemas.SlideOut])
def get_admin_slides(
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    return (
        db.query(models.Slide)
        .order_by(models.Slide.sort_order.asc(), models.Slide.id.asc())
        .all()
    )

# ==========================================
# Admin: Upload រូបភាព ឬ វីដេអូសម្រាប់ Slide
# ==========================================
@router.post("/admin/slides/upload")
async def upload_slide_media(
    file: UploadFile = File(...),
    admin: models.User = Depends(get_current_admin),
):
    filename = file.filename or ""
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_MEDIA_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported file type '{ext or 'none'}'. "
                f"Allowed: {', '.join(sorted(ALLOWED_MEDIA_EXTENSIONS))}"
            ),
        )

    content = await file.read()
    # Cloudinary (បើកំណត់) — resource_type auto ស្គាល់រូប / វីដេអូ ហើយ media_type ត្រឡប់ 'image' | 'video'
    return save_upload(content, filename, folder="slides")

# ==========================================
# Admin: បង្កើត Slide ថ្មី
# ==========================================
@router.post("/admin/slides", response_model=schemas.SlideOut)
def create_slide(
    payload: schemas.SlideCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    _validate(payload)
    slide = models.Slide(**payload.dict())
    db.add(slide)
    db.commit()
    db.refresh(slide)
    _broadcast_slides_changed(background_tasks)
    return slide

# ==========================================
# Admin: កែប្រែ Slide
# ==========================================
@router.put("/admin/slides/{slide_id}", response_model=schemas.SlideOut)
def update_slide(
    slide_id: int,
    payload: schemas.SlideUpdate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    slide = db.query(models.Slide).filter(models.Slide.id == slide_id).first()
    if not slide:
        raise HTTPException(status_code=404, detail="Slide not found")
    _validate(payload)
    for key, value in payload.dict().items():
        setattr(slide, key, value)
    db.commit()
    db.refresh(slide)
    _broadcast_slides_changed(background_tasks)
    return slide

# ==========================================
# Admin: លុប Slide
# ==========================================
@router.delete("/admin/slides/{slide_id}")
def delete_slide(
    slide_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    slide = db.query(models.Slide).filter(models.Slide.id == slide_id).first()
    if not slide:
        raise HTTPException(status_code=404, detail="Slide not found")
    db.delete(slide)
    db.commit()
    _broadcast_slides_changed(background_tasks)
    return {"message": "Slide deleted", "id": slide_id}
