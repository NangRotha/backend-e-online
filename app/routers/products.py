from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List
from pathlib import Path
from .. import models, schemas
from ..database import get_db
from ..deps import get_current_admin
from ..storage import ALLOWED_EXTENSIONS, save_upload
from ..ws_manager import broadcast_products_changed

router = APIRouter(prefix="/api", tags=["Products"])

def _normalize_images(data: dict) -> dict:
    """បញ្ជាក់រូបភាព៖ images ជាបញ្ជី URL (រូបទី១ = Main) ហើយ image_url = រូបទី១"""
    images = data.get("images") or []
    if not images and data.get("image_url"):
        images = [data["image_url"]]
    data["images"] = images
    data["image_url"] = images[0] if images else (data.get("image_url") or "")
    return data

# Admin: Upload រូបភាពពីកុំព្យូទ័រ (Main / Supporting images) — Cloudinary (បើកំណត់)
@router.post("/admin/upload")
async def upload_image(
    file: UploadFile = File(...),
    admin: models.User = Depends(get_current_admin),
):
    filename = file.filename or ""
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext or 'none'}'. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
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

# Admin: កែប្រែផលិតផល
@router.put("/admin/products/{product_id}", response_model=schemas.ProductOut)
def update_product(
    product_id: int,
    product: schemas.ProductCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    db_product = db.query(models.Product).filter(models.Product.id == product_id).first()
    if not db_product:
        raise HTTPException(status_code=404, detail="Product not found")
    data = _normalize_images(product.dict())
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
    db.delete(db_product)
    db.commit()
    # ជូនដំណឹង frontend-user ដើម្បីធ្វើបច្ចុប្បន្នភាពដោយស្វ័យប្រវត្តិ
    background_tasks.add_task(broadcast_products_changed)
    return {"message": "Deleted successfully"}