from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List
from .. import models, schemas, auth
from ..database import get_db
from ..deps import get_current_admin
from ..storage import delete_upload_by_url
from ..ws_manager import broadcast_orders_changed
from ..telegram import send_order_status_telegram, test_telegram_connection
from typing import Optional

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

@router.post("/users", response_model=schemas.UserOut)
def create_user(
    payload: schemas.AdminUserCreate,
    db: Session = Depends(_admin),
):
    name = payload.name.strip()
    email = payload.email.strip().lower()
    if not name:
        raise HTTPException(status_code=400, detail="Name is required")
    if not email:
        raise HTTPException(status_code=400, detail="Email is required")
    if len(payload.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
    if payload.role not in ("admin", "user"):
        raise HTTPException(status_code=400, detail="Role must be 'admin' or 'user'")

    existing = db.query(models.User).filter(func.lower(models.User.email) == email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    new_user = models.User(
        name=name,
        email=email,
        hashed_password=auth.hash_password(payload.password),
        role=payload.role,
        email_verified=payload.email_verified,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user

@router.put("/users/{user_id}", response_model=schemas.UserOut)
def update_user(
    user_id: int,
    payload: schemas.AdminUserUpdate,
    db: Session = Depends(_admin),
    admin: models.User = Depends(get_current_admin),
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if payload.name is not None:
        name = payload.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="Name cannot be empty")
        user.name = name

    if payload.email is not None:
        email = payload.email.strip().lower()
        if not email:
            raise HTTPException(status_code=400, detail="Email cannot be empty")
        existing = db.query(models.User).filter(
            func.lower(models.User.email) == email,
            models.User.id != user_id,
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail="Email already registered by another account")
        user.email = email

    if payload.role is not None:
        if payload.role not in ("admin", "user"):
            raise HTTPException(status_code=400, detail="Role must be 'admin' or 'user'")
        if user.id == admin.id and payload.role != "admin":
            raise HTTPException(status_code=400, detail="You cannot change your own role")
        user.role = payload.role

    if payload.email_verified is not None:
        user.email_verified = payload.email_verified

    if payload.password and payload.password.strip():
        if len(payload.password.strip()) < 6:
            raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
        user.hashed_password = auth.hash_password(payload.password.strip())

    db.commit()
    db.refresh(user)
    return user

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

@router.delete("/users/{user_id}")
def delete_user(
    user_id: int,
    db: Session = Depends(_admin),
    admin: models.User = Depends(get_current_admin),
):
    """Admin: លុបអ្នកប្រើប្រាស់ (Delete User) — រួមទាំង Orders + រូប Profile ផង"""
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    # ការពារកុំឲ្យ Admin លុបខ្លួនឯង (អាចធ្វើឲ្យបាត់សិទ្ធិ Admin)
    if user.id == admin.id:
        raise HTTPException(status_code=400, detail="You cannot delete your own account")

    # លុប Orders + Order Items របស់អ្នកប្រើជាមុន (ទាក់ទង Foreign Key)
    for order in (
        db.query(models.Order).filter(models.Order.user_id == user.id).all()
    ):
        db.query(models.OrderItem).filter(
            models.OrderItem.order_id == order.id
        ).delete()
    db.query(models.Order).filter(models.Order.user_id == user.id).delete()

    # លុប OTP Codes ចាស់ៗរបស់អ្នកប្រើ
    db.query(models.OtpCode).filter(models.OtpCode.email == user.email).delete()

    # លុបរូប Profile ពី UploadThing / Cloudinary / Local Disk
    if user.profile_image:
        delete_upload_by_url(user.profile_image)

    db.delete(user)
    db.commit()
    return {"message": "User deleted", "user_id": user.id, "email": user.email}

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
        serialized_items = []
        for i in items:
            p = db.query(models.Product).filter(models.Product.id == i.product_id).first()
            serialized_items.append({
                "product_id": i.product_id,
                "product_name": p.name if p else f"Product #{i.product_id}",
                "product_image": p.image_url if p else "",
                "variant": getattr(i, "variant", "") or "",
                "quantity": i.quantity,
                "price": i.price,
            })
        result.append({
            "id": o.id,
            "user_email": user.email if user else None,
            "customer_email": o.customer_email or "",
            "total_amount": o.total_amount,
            "status": o.status,
            "promo_code": o.promo_code,
            "payment_ref": o.payment_ref,
            "customer_name": o.customer_name,
            "customer_phone": o.customer_phone,
            "shipping_address": o.shipping_address,
            "latitude": getattr(o, "latitude", None),
            "longitude": getattr(o, "longitude", None),
            "map_url": getattr(o, "map_url", "") or "",
            "payment_method": getattr(o, "payment_method", "aba_pay") or "aba_pay",
            "note": o.note,
            "created_at": o.created_at,
            "items": serialized_items,
        })
    return result

@router.put("/orders/{order_id}/status")
def update_order_status(
    order_id: int,
    payload: schemas.OrderStatusUpdate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(_admin),
):
    order = db.query(models.Order).filter(models.Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if payload.status not in ("pending", "paid", "shipped", "cancelled"):
        raise HTTPException(status_code=400, detail="Invalid status")
    order.status = payload.status
    db.commit()
    # Real-time: ជូនដំណឹងទៅ Admin Panel ផ្សេងទៀត និង Storefront (Order Success)
    background_tasks.add_task(broadcast_orders_changed)
    # Telegram Bot: ជូនដំណឹងពេលផ្លាស់ប្តូរស្ថានភាព Order ទៅកាន់ Admin
    background_tasks.add_task(send_order_status_telegram, order.id, payload.status)
    return {"message": "Order status updated", "order_id": order.id, "status": order.status}

@router.post("/telegram/test")
def test_telegram(
    payload: Optional[schemas.TelegramTestRequest] = None,
    db: Session = Depends(_admin),
):
    """Admin: ធ្វើតេស្តការតភ្ជាប់ Telegram Bot និងផ្ញើសារសាកល្បងទៅកាន់ Admin Telegram ID"""
    token = payload.bot_token if payload else None
    chat_id = payload.chat_id if payload else None
    return test_telegram_connection(bot_token=token, chat_id=chat_id, db=db)

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

# ==========================================
# Backup — Export ទិន្នន័យទាំងអស់ជា JSON
# ==========================================
@router.get("/export")
def export_data(db: Session = Depends(_admin)):
    """Admin: Export ទិន្នន័យទាំងអស់ជា JSON (សម្រាប់ Backup ឬ ផ្លាស់ Database)

    ប្រើជាមួយ `scripts/backup_restore.py import` ដើម្បីផ្លាស់ទិន្នន័យពី
    SQLite មួយ → SQLite មួយផ្សេងទៀត (ឧ. Local → Render) ដោយមិនបាត់ទិន្នន័យ។

    ចំណាំ: Users ត្រូវបាន Export ដោយគ្មាន `hashed_password` (ការពារសុវត្ថិភាព)
    """
    data = {}
    for table in models.Base.metadata.sorted_tables:
        rows = db.execute(table.select()).mappings().all()
        data[table.name] = [
            {k: v for k, v in dict(row).items()
             if not (table.name == "users" and k == "hashed_password")}
            for row in rows
        ]
    data["_meta"] = {
        "exported_tables": {name: len(rows) for name, rows in data.items() if isinstance(rows, list)},
        "note": "users.hashed_password ត្រូវបានលាក់ — ត្រូវកំណត់ពាក្យសម្ងាត់ឡើងវិញក្រោយ Import",
    }
    return data

