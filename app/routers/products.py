from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List
from pathlib import Path
from .. import models, schemas
from ..database import get_db
from ..deps import get_current_admin
from ..storage import (
    ALLOWED_EXTENSIONS,
    ALLOWED_VIDEO_EXTENSIONS,
    save_upload,
    delete_upload_by_url,
    delete_uploads_by_urls,
)
from ..ws_manager import broadcast_products_changed

router = APIRouter(prefix="/api", tags=["Products"])

def _normalize_images(data: dict) -> dict:
    """បញ្ជាក់រូបភាព៖ images ជាបញ្ជី URL (រូបទី១ = Main) ហើយ image_url = រូបទី១
    ប្រសិនបើ client មិនបានផ្ញើ images/image_url (ឧ. កែតម្លៃតែប៉ុណ្ណោះ) ទុករូបភាពដដែល។"""
    if "images" not in data and "image_url" not in data:
        return data
    images = data.get("images") or []
    if not images and data.get("image_url"):
        images = [data["image_url"]]
    data["images"] = images
    data["image_url"] = images[0] if images else (data.get("image_url") or "")
    return data

# Admin: Upload រូបភាព ឬ **វីដេអូ** ពីកុំព្យូទ័រ (Product images / Product video)
# kind=image -> jpg/png/webp... | kind=video -> mp4/webm/mov...
@router.post("/admin/upload")
async def upload_image(
    file: UploadFile = File(...),
    kind: str = "image",
    admin: models.User = Depends(get_current_admin),
):
    if kind not in ("image", "video"):
        raise HTTPException(status_code=400, detail="kind must be 'image' or 'video'")

    filename = file.filename or ""
    ext = Path(filename).suffix.lower()
    allowed = ALLOWED_VIDEO_EXTENSIONS if kind == "video" else ALLOWED_EXTENSIONS
    if ext not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported {kind} file type '{ext or 'none'}'. Allowed: {', '.join(sorted(allowed))}",
        )

    content = await file.read()
    return save_upload(content, filename, folder="products")

# បង្ហាញផលិតផលទាំងអស់ (សម្រាប់ User)
@router.get("/products", response_model=List[schemas.ProductOut])
def get_products(db: Session = Depends(get_db)):
    return db.query(models.Product).all()

# បង្ហាញផលិតផលមួយ (សម្រាប់ Share)
@router.get("/products/{product_id}", response_model=schemas.ProductOut)
def get_product(product_id: int, db: Session = Depends(get_db)):
    product = db.query(models.Product).filter(models.Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product

# Admin: បង្កើតផលិតផលថ្មី
@router.post("/admin/products", response_model=schemas.ProductOut)
def create_product(
    product: schemas.ProductCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    data = _normalize_images(product.dict())
    new_product = models.Product(**data)
    db.add(new_product)
    db.commit()
    db.refresh(new_product)
    # ជូនដំណឹង frontend-user ដើម្បីធ្វើបច្ចុប្បន្នភាពដោយស្វ័យប្រវត្តិ
    background_tasks.add_task(broadcast_products_changed)
    return new_product

# Admin: កែប្រែផលិតផល (partial update — អាចផ្ញើតែ price ឬតែ stock ក៏បាន)
@router.put("/admin/products/{product_id}", response_model=schemas.ProductOut)
def update_product(
    product_id: int,
    product: schemas.ProductUpdate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    db_product = db.query(models.Product).filter(models.Product.id == product_id).first()
    if not db_product:
        raise HTTPException(status_code=404, detail="Product not found")
    data = _normalize_images(product.dict(exclude_unset=True))

    # លុបរូបភាពដែលលែងប្រើ (តែពេលមានការផ្ញើ images/image_url មកប៉ុណ្ណោះ —
    # បើអត់ នោះជាការកែតម្រូវផ្នែកផ្សេង ហើយរូបភាពត្រូវរក្សាទុកដដែល)
    if "images" in data or "image_url" in data:
        old_urls = set(filter(None, [db_product.image_url or ""] + list(db_product.images or [])))
        new_urls = set(filter(None, data.get("images") or []))
        delete_uploads_by_urls(old_urls - new_urls)

    # លុបវីដេអូចាស់ បើមានការប្តូរវីដេអូថ្មី
    if "video_url" in data:
        old_video = (db_product.video_url or "").strip()
        new_video = (data.get("video_url") or "").strip()
        if old_video and old_video != new_video:
            delete_upload_by_url(old_video)

    for key, value in data.items():
        setattr(db_product, key, value)
    db.commit()
    db.refresh(db_product)
    # ជូនដំណឹង frontend-user ដើម្បីធ្វើបច្ចុប្បន្នភាពដោយស្វ័យប្រវត្តិ
    background_tasks.add_task(broadcast_products_changed)
    return db_product

# Admin: លុបផលិតផល
@router.delete("/admin/products/{product_id}")
def delete_product(
    product_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    db_product = db.query(models.Product).filter(models.Product.id == product_id).first()
    if not db_product:
        raise HTTPException(status_code=404, detail="Product not found")
    # លុបរូបភាព + វីដេអូ ទាំងអស់ពី UploadThing / Cloudinary / Local Disk ផង (Delete)
    urls = [db_product.image_url or "", db_product.video_url or ""] + list(db_product.images or [])
    delete_uploads_by_urls(urls)
    db.delete(db_product)
    db.commit()
    # ជូនដំណឹង frontend-user ដើម្បីធ្វើបច្ចុប្បន្នភាពដោយស្វ័យប្រវត្តិ
    background_tasks.add_task(broadcast_products_changed)
    return {"message": "Deleted successfully"}