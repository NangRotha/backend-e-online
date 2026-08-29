from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from .. import models, schemas
from ..database import get_db
from ..deps import get_current_admin
from datetime import datetime

router = APIRouter(prefix="/api/discounts", tags=["Discounts"])

# Admin: បង្កើត Promo Code
@router.post("/admin/create")
def create_discount(
    discount: schemas.DiscountCreate,
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    expiry = datetime.fromisoformat(discount.expiry_date) if discount.expiry_date else None
    new_discount = models.Discount(
        code=discount.code,
        percent=discount.percent,
        max_uses=discount.max_uses,
        expiry_date=expiry
    )
    db.add(new_discount)
    db.commit()
    db.refresh(new_discount)
    return {"message": "Discount created successfully", "code": new_discount.code}

# User: ពិនិត្យថា Promo Code ត្រឹមត្រូវឬអត់
@router.get("/validate/{code}")
def validate_discount(code: str, db: Session = Depends(get_db)):
    promo = db.query(models.Discount).filter(models.Discount.code == code).first()
    if not promo or not promo.is_active:
        raise HTTPException(status_code=400, detail="Invalid promo code")
    if promo.expiry_date and promo.expiry_date < datetime.now():
        raise HTTPException(status_code=400, detail="Promo code expired")
    return {"valid": True, "percent": promo.percent}