from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List
from .. import models, schemas
from ..database import get_db
from ..deps import get_current_admin
from ..ws_manager import broadcast_orders_changed

router = APIRouter(prefix="/api", tags=["Shipping"])

DEFAULT_SHIPPING_COMPANIES = [
    {
        "name": "VET Express",
        "name_kh": "វីរៈ ប៊ុនថាំ",
        "fee": 1.50,
        "estimated_delivery": "1-2 ថ្ងៃ",
        "sort_order": 1,
        "is_active": True,
    },
    {
        "name": "J&T Express",
        "name_kh": "ជេ & ធី",
        "fee": 1.50,
        "estimated_delivery": "1-2 ថ្ងៃ",
        "sort_order": 2,
        "is_active": True,
    },
    {
        "name": "CE Express",
        "name_kh": "ស៊ីអ៊ី",
        "fee": 1.50,
        "estimated_delivery": "1-2 ថ្ងៃ",
        "sort_order": 3,
        "is_active": True,
    },
    {
        "name": "Cambodia Post / EMS",
        "name_kh": "ប្រៃសណីយ៍កម្ពុជា",
        "fee": 1.50,
        "estimated_delivery": "2-3 ថ្ងៃ",
        "sort_order": 4,
        "is_active": True,
    },
    {
        "name": "Capitol Express",
        "name_kh": "កាពីតូល",
        "fee": 1.50,
        "estimated_delivery": "1-2 ថ្ងៃ",
        "sort_order": 5,
        "is_active": True,
    },
    {
        "name": "ZTO Express",
        "name_kh": "ZTO",
        "fee": 1.50,
        "estimated_delivery": "1-2 ថ្ងៃ",
        "sort_order": 6,
        "is_active": True,
    },
]

def seed_default_shipping_companies(db: Session):
    """បង្កើតក្រុមហ៊ុនដឹកជញ្ជូនលំនាំដើមទាំង ៦ បើក្នុង Database មិនទាន់មាន"""
    count = db.query(models.ShippingCompany).count()
    if count == 0:
        for item in DEFAULT_SHIPPING_COMPANIES:
            db.add(models.ShippingCompany(**item))
        db.commit()


# ============================================================
# Storefront / Public: បញ្ជីក្រុមហ៊ុនដឹកជញ្ជូនដែលបើកដំណើរការ
# ============================================================
@router.get("/shipping-companies", response_model=List[schemas.ShippingCompanyOut])
def get_public_shipping_companies(db: Session = Depends(get_db)):
    """ទាញយកបញ្ជីក្រុមហ៊ុនដឹកជញ្ជូនសម្រាប់ទំព័រ Checkout (បង្ហាញតែ active)"""
    seed_default_shipping_companies(db)
    return (
        db.query(models.ShippingCompany)
        .filter(models.ShippingCompany.is_active == True)
        .order_by(models.ShippingCompany.sort_order.asc(), models.ShippingCompany.id.asc())
        .all()
    )


# ============================================================
# Admin: បញ្ជីក្រុមហ៊ុនដឹកជញ្ជូនទាំងអស់ (រួមទាំង inactive)
# ============================================================
@router.get("/admin/shipping-companies", response_model=List[schemas.ShippingCompanyOut])
def list_shipping_companies_admin(
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    """Admin: ទាញយកបញ្ជីក្រុមហ៊ុនដឹកជញ្ជូនទាំងអស់"""
    seed_default_shipping_companies(db)
    return (
        db.query(models.ShippingCompany)
        .order_by(models.ShippingCompany.sort_order.asc(), models.ShippingCompany.id.asc())
        .all()
    )


# ============================================================
# Admin: បង្កើតក្រុមហ៊ុនដឹកជញ្ជូនថ្មី
# ============================================================
@router.post("/admin/shipping-companies", response_model=schemas.ShippingCompanyOut)
def create_shipping_company(
    data: schemas.ShippingCompanyCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    name = (data.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Shipping company name is required")

    fee = max(0.0, round(float(data.fee or 0.0), 2))
    new_company = models.ShippingCompany(
        name=name,
        name_kh=(data.name_kh or "").strip(),
        fee=fee,
        estimated_delivery=(data.estimated_delivery or "1-2 ថ្ងៃ").strip(),
        sort_order=int(data.sort_order or 0),
        is_active=bool(data.is_active if data.is_active is not None else True),
    )
    db.add(new_company)
    db.commit()
    db.refresh(new_company)

    background_tasks.add_task(broadcast_orders_changed)
    return new_company


# ============================================================
# Admin: កែប្រែព័ត៌មានក្រុមហ៊ុនដឹកជញ្ជូន
# ============================================================
@router.put("/admin/shipping-companies/{company_id}", response_model=schemas.ShippingCompanyOut)
def update_shipping_company(
    company_id: int,
    data: schemas.ShippingCompanyUpdate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    company = db.query(models.ShippingCompany).filter(models.ShippingCompany.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Shipping company not found")

    if data.name is not None:
        name = data.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="Shipping company name cannot be empty")
        company.name = name

    if data.name_kh is not None:
        company.name_kh = data.name_kh.strip()

    if data.fee is not None:
        company.fee = max(0.0, round(float(data.fee), 2))

    if data.estimated_delivery is not None:
        company.estimated_delivery = data.estimated_delivery.strip()

    if data.sort_order is not None:
        company.sort_order = int(data.sort_order)

    if data.is_active is not None:
        company.is_active = bool(data.is_active)

    db.commit()
    db.refresh(company)

    background_tasks.add_task(broadcast_orders_changed)
    return company


# ============================================================
# Admin: បិទ/បើកដំណើរការ (Toggle Active)
# ============================================================
@router.put("/admin/shipping-companies/{company_id}/toggle", response_model=schemas.ShippingCompanyOut)
def toggle_shipping_company(
    company_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    company = db.query(models.ShippingCompany).filter(models.ShippingCompany.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Shipping company not found")

    company.is_active = not company.is_active
    db.commit()
    db.refresh(company)

    background_tasks.add_task(broadcast_orders_changed)
    return company


# ============================================================
# Admin: លុបក្រុមហ៊ុនដឹកជញ្ជូន
# ============================================================
@router.delete("/admin/shipping-companies/{company_id}")
def delete_shipping_company(
    company_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    company = db.query(models.ShippingCompany).filter(models.ShippingCompany.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Shipping company not found")

    db.delete(company)
    db.commit()

    background_tasks.add_task(broadcast_orders_changed)
    return {"message": "Shipping company deleted successfully", "id": company_id}


# ============================================================
# Admin: កំណត់ក្រុមហ៊ុនដឹកជញ្ជូនទៅលំនាំដើម (Reset Defaults)
# ============================================================
@router.post("/admin/shipping-companies/reset-defaults", response_model=List[schemas.ShippingCompanyOut])
def reset_default_shipping_companies(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    # បន្ថែមក្រុមហ៊ុនណាដែលខ្វះក្នុង Default list
    existing_names = {c.name.lower() for c in db.query(models.ShippingCompany).all()}
    for item in DEFAULT_SHIPPING_COMPANIES:
        if item["name"].lower() not in existing_names:
            db.add(models.ShippingCompany(**item))
    db.commit()

    background_tasks.add_task(broadcast_orders_changed)
    return (
        db.query(models.ShippingCompany)
        .order_by(models.ShippingCompany.sort_order.asc(), models.ShippingCompany.id.asc())
        .all()
    )
