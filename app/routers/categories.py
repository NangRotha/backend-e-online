from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List
from .. import models, schemas
from ..database import get_db
from ..deps import get_current_admin
from ..ws_manager import broadcast_products_changed

router = APIRouter(prefix="/api", tags=["Categories"])

def _category_out(db: Session, cat: models.Category) -> dict:
    """បង្កើត response រួមជាមួយចំនួនផលិតផលដែលប្រើ Category នេះ"""
    product_count = db.query(func.count(models.Product.id)).filter(
        models.Product.category == cat.name
    ).scalar()
    return {
        "id": cat.id,
        "name": cat.name,
        "name_kh": getattr(cat, "name_kh", "") or "",
        "description": cat.description or "",
        "description_kh": getattr(cat, "description_kh", "") or "",
        "product_count": product_count,
        "created_at": cat.created_at,
    }

# ==========================================
# User: បង្ហាញ Category ទាំងអស់ (សម្រាប់ Filter ក្នុង Storefront)
# ==========================================
@router.get("/categories", response_model=List[schemas.CategoryOut])
def list_categories(db: Session = Depends(get_db)):
    cats = db.query(models.Category).order_by(models.Category.name.asc()).all()
    return [_category_out(db, c) for c in cats]

# ==========================================
# Admin: បង្កើត Category ថ្មី
# ==========================================
@router.post("/admin/categories", response_model=schemas.CategoryOut)
def create_category(
    category: schemas.CategoryCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    name = category.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Category name is required")

    duplicate = db.query(models.Category).filter(
        func.lower(models.Category.name) == name.lower()
    ).first()
    if duplicate:
        raise HTTPException(
            status_code=400,
            detail=f"Category '{name}' already exists",
        )

    new_cat = models.Category(
        name=name,
        name_kh=(category.name_kh or "").strip(),
        description=category.description.strip(),
        description_kh=(category.description_kh or "").strip(),
    )
    db.add(new_cat)
    db.commit()
    db.refresh(new_cat)
    # ជូនដំណឹង Storefront ឲ្យបញ្ចូល Category ថ្មីដោយស្វ័យប្រវត្តិ
    background_tasks.add_task(broadcast_products_changed)
    return _category_out(db, new_cat)

# ==========================================
# Admin: កែប្រែ Category (ពេលប្តូរឈ្មោះ -> កែផលិតផលដែលប្រើឈ្មោះចាស់ផង)
# ==========================================
@router.put("/admin/categories/{category_id}", response_model=schemas.CategoryOut)
def update_category(
    category_id: int,
    category: schemas.CategoryUpdate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    db_cat = db.query(models.Category).filter(models.Category.id == category_id).first()
    if not db_cat:
        raise HTTPException(status_code=404, detail="Category not found")

    name = category.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Category name is required")

    duplicate = db.query(models.Category).filter(
        func.lower(models.Category.name) == name.lower(),
        models.Category.id != category_id,
    ).first()
    if duplicate:
        raise HTTPException(
            status_code=400,
            detail=f"Category '{name}' already exists",
        )

    old_name = db_cat.name
    db_cat.name = name
    db_cat.name_kh = (category.name_kh or "").strip()
    db_cat.description = category.description.strip()
    db_cat.description_kh = (category.description_kh or "").strip()

    # បើប្តូរឈ្មោះ Category -> ធ្វើបច្ចុប្បន្នភាពផលិតផលដែលប្រើឈ្មោះចាស់
    if old_name != name:
        products = db.query(models.Product).filter(models.Product.category == old_name).all()
        for p in products:
            p.category = name
        background_tasks.add_task(broadcast_products_changed)

    db.commit()
    db.refresh(db_cat)
    return _category_out(db, db_cat)

# ==========================================
# Admin: លុប Category (ហាមលុបបើនៅមានផលិតផលប្រើនៅឡើយ)
# ==========================================
@router.delete("/admin/categories/{category_id}")
def delete_category(
    category_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    db_cat = db.query(models.Category).filter(models.Category.id == category_id).first()
    if not db_cat:
        raise HTTPException(status_code=404, detail="Category not found")

    product_count = db.query(func.count(models.Product.id)).filter(
        models.Product.category == db_cat.name
    ).scalar()
    if product_count:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Cannot delete '{db_cat.name}' — {product_count} product(s) still use "
                "this category. Reassign or delete those products first."
            ),
        )

    db.delete(db_cat)
    db.commit()
    # ជូនដំណឹង Storefront ឲ្យដក Category ដែលលុបចេញដោយស្វ័យប្រវត្តិ
    background_tasks.add_task(broadcast_products_changed)
    return {"message": "Category deleted", "id": db_cat.id}
