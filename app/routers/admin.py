from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List
from .. import models, schemas
from ..database import get_db
from ..deps import get_current_admin

router = APIRouter(prefix="/api/admin", tags=["Admin"])

def _admin(db: Session = Depends(get_db), admin: models.User = Depends(get_current_admin)):
    return db

# ==========================================
# Dashboard Stats
# ==========================================
@router.get("/stats")
def get_stats(db: Session = Depends(_admin)):
    total_products = db.query(models.Product).count()
    total_users = db.query(models.User).count()
    total_orders = db.query(models.Order).count()
    total_revenue = db.query(
        func.coalesce(func.sum(models.Order.total_amount), 0)
    ).filter(models.Order.status.in_(["paid", "shipped"])).scalar()

    orders_by_status = dict(
        db.query(models.Order.status, func.count(models.Order.id))
        .group_by(models.Order.status)
        .all()
    )

    low_stock = (
        db.query(models.Product)
        .filter(models.Product.stock <= 5)
        .order_by(models.Product.stock.asc())
        .limit(10)
        .all()
    )

    recent_orders = (
        db.query(models.Order)
        .order_by(models.Order.created_at.desc())
        .limit(5)
        .all()
    )

    recent = []
    for o in recent_orders:
        user = db.query(models.User).filter(models.User.id == o.user_id).first()
        recent.append({
            "id": o.id,
            "user_email": user.email if user else None,
            "total_amount": o.total_amount,
            "status": o.status,
            "created_at": o.created_at,
        })

    return {
        "total_products": total_products,
        "total_users": total_users,
        "total_orders": total_orders,
        "total_revenue": float(total_revenue),
        "orders_by_status": orders_by_status,
        "low_stock": [
            {
                "id": p.id,
                "name": p.name,
                "stock": p.stock,
                "price": p.price,
            }
            for p in low_stock
        ],
        "recent_orders": recent,
    }

# ==========================================
# Users Management
# ==========================================
@router.get("/users")
def list_users(db: Session = Depends(_admin)):
    users = db.query(models.User).order_by(models.User.created_at.desc()).all()
    return [
        {
            "id": u.id,
            "name": u.name,
            "email": u.email,
            "role": u.role,
            "email_verified": u.email_verified,
            "profile_image": u.profile_image or "",
            "created_at": u.created_at,
        }
        for u in users
    ]

@router.put("/users/{user_id}/role")
def update_user_role(
    user_id: int,
    payload: schemas.RoleUpdate,
    db: Session = Depends(_admin),
    admin: models.User = Depends(get_current_admin),
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if payload.role not in ("admin", "user"):
        raise HTTPException(status_code=400, detail="Role must be 'admin' or 'user'")
    # ការពារកុំឲ្យ Admin ប្តូរ Role របស់ខ្លួនឯង (អាចធ្វើឲ្យបាត់សិទ្ធិ Admin)
    if user.id == admin.id:
        raise HTTPException(status_code=400, detail="You cannot change your own role")
    user.role = payload.role
    db.commit()
    return {"message": "Role updated", "user_id": user.id, "role": user.role}

# ==========================================
# Orders Management
# ==========================================
@router.get("/orders")
def list_orders(db: Session = Depends(_admin)):
    orders = db.query(models.Order).order_by(models.Order.created_at.desc()).all()
    result = []
    for o in orders:
        user = db.query(models.User).filter(models.User.id == o.user_id).first()
        items = (
            db.query(models.OrderItem)
            .filter(models.OrderItem.order_id == o.id)
            .all()
        )
        result.append({
            "id": o.id,
            "user_email": user.email if user else None,
            "total_amount": o.total_amount,
            "status": o.status,
            "promo_code": o.promo_code,
            "payment_ref": o.payment_ref,
            "created_at": o.created_at,
            "items": [
                {
                    "product_id": i.product_id,
                    "quantity": i.quantity,
                    "price": i.price,
                }
                for i in items
            ],
        })
    return result

@router.put("/orders/{order_id}/status")
def update_order_status(
    order_id: int,
    payload: schemas.OrderStatusUpdate,
    db: Session = Depends(_admin),
):
    order = db.query(models.Order).filter(models.Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if payload.status not in ("pending", "paid", "shipped", "cancelled"):
        raise HTTPException(status_code=400, detail="Invalid status")
    order.status = payload.status
    db.commit()
    return {"message": "Order status updated", "order_id": order.id, "status": order.status}

# ==========================================
# Discounts Management
# ==========================================
@router.get("/discounts")
def list_discounts(db: Session = Depends(_admin)):
    discounts = db.query(models.Discount).order_by(models.Discount.id.desc()).all()
    return [
        {
            "id": d.id,
            "code": d.code,
            "percent": d.percent,
            "max_uses": d.max_uses,
            "used_count": d.used_count,
            "is_active": d.is_active,
            "expiry_date": d.expiry_date,
        }
        for d in discounts
    ]

@router.put("/discounts/{discount_id}/toggle")
def toggle_discount(
    discount_id: int,
    db: Session = Depends(_admin),
):
    discount = db.query(models.Discount).filter(models.Discount.id == discount_id).first()
    if not discount:
        raise HTTPException(status_code=404, detail="Discount not found")
    discount.is_active = not discount.is_active
    db.commit()
    return {
        "message": "Discount updated",
        "id": discount.id,
        "is_active": discount.is_active,
    }

