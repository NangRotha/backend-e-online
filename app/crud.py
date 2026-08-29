from sqlalchemy.orm import Session
from . import models, schemas
from .auth import hash_password
from datetime import datetime
from typing import List, Optional

# ==========================================
# 1. USER CRUD
# ==========================================

def get_user_by_email(db: Session, email: str):
    return db.query(models.User).filter(models.User.email == email).first()

def get_user_by_id(db: Session, user_id: int):
    return db.query(models.User).filter(models.User.id == user_id).first()

def create_user(db: Session, user: schemas.UserCreate):
    hashed_pw = hash_password(user.password)
    db_user = models.User(
        name=user.name,
        email=user.email,
        hashed_password=hashed_pw,
        role="user"  # តាមលំនាំដើមជា User ធម្មតា
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

def update_user_role(db: Session, user_id: int, new_role: str):
    db_user = get_user_by_id(db, user_id)
    if db_user:
        db_user.role = new_role
        db.commit()
        db.refresh(db_user)
    return db_user


# ==========================================
# 2. PRODUCT CRUD
# ==========================================

def get_products(db: Session, skip: int = 0, limit: int = 100) -> List[models.Product]:
    return db.query(models.Product).offset(skip).limit(limit).all()

def get_product_by_id(db: Session, product_id: int) -> Optional[models.Product]:
    return db.query(models.Product).filter(models.Product.id == product_id).first()

def create_product(db: Session, product: schemas.ProductCreate):
    db_product = models.Product(**product.dict())
    db.add(db_product)
    db.commit()
    db.refresh(db_product)
    return db_product

def update_product(db: Session, product_id: int, product: schemas.ProductCreate):
    db_product = get_product_by_id(db, product_id)
    if db_product:
        for key, value in product.dict().items():
            setattr(db_product, key, value)
        db.commit()
        db.refresh(db_product)
    return db_product

def delete_product(db: Session, product_id: int):
    db_product = get_product_by_id(db, product_id)
    if db_product:
        db.delete(db_product)
        db.commit()
        return True
    return False

def decrease_stock(db: Session, product_id: int, quantity: int):
    db_product = get_product_by_id(db, product_id)
    if db_product and db_product.stock >= quantity:
        db_product.stock -= quantity
        db.commit()
        db.refresh(db_product)
        return True
    return False


# ==========================================
# 3. ORDER CRUD
# ==========================================

def create_order(db: Session, user_id: int, total_amount: float, promo_code: Optional[str] = None):
    db_order = models.Order(
        user_id=user_id,
        total_amount=total_amount,
        status="pending",
        promo_code=promo_code
    )
    db.add(db_order)
    db.commit()
    db.refresh(db_order)
    return db_order

def get_order_by_id(db: Session, order_id: int) -> Optional[models.Order]:
    return db.query(models.Order).filter(models.Order.id == order_id).first()

def update_order_status(db: Session, order_id: int, status: str, payment_ref: Optional[str] = None):
    db_order = get_order_by_id(db, order_id)
    if db_order:
        db_order.status = status
        if payment_ref:
            db_order.payment_ref = payment_ref
        db.commit()
        db.refresh(db_order)
    return db_order


# ==========================================
# 4. ORDER ITEM CRUD
# ==========================================

def create_order_item(db: Session, order_id: int, product_id: int, quantity: int, price: float):
    db_item = models.OrderItem(
        order_id=order_id,
        product_id=product_id,
        quantity=quantity,
        price=price
    )
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    return db_item


# ==========================================
# 5. DISCOUNT / PROMO CRUD
# ==========================================

def get_discount_by_code(db: Session, code: str) -> Optional[models.Discount]:
    return db.query(models.Discount).filter(models.Discount.code == code).first()

def create_discount(db: Session, discount: schemas.DiscountCreate):
    expiry_date = None
    if discount.expiry_date:
        expiry_date = datetime.fromisoformat(discount.expiry_date)
        
    db_discount = models.Discount(
        code=discount.code,
        percent=discount.percent,
        max_uses=discount.max_uses,
        expiry_date=expiry_date,
        is_active=True,
        used_count=0
    )
    db.add(db_discount)
    db.commit()
    db.refresh(db_discount)
    return db_discount

def increment_discount_usage(db: Session, code: str):
    db_discount = get_discount_by_code(db, code)
    if db_discount:
        db_discount.used_count += 1
        db.commit()
        db.refresh(db_discount)
    return db_discount


# ==========================================
# 6. SETTINGS CRUD
# ==========================================

def get_setting_by_key(db: Session, key: str) -> Optional[models.SiteSetting]:
    return db.query(models.SiteSetting).filter(models.SiteSetting.key == key).first()

def get_all_settings(db: Session) -> dict:
    settings = db.query(models.SiteSetting).all()
    return {s.key: s.value for s in settings}

def update_or_create_setting(db: Session, key: str, value: str):
    db_setting = get_setting_by_key(db, key)
    if db_setting:
        db_setting.value = value
    else:
        db_setting = models.SiteSetting(key=key, value=value)
        db.add(db_setting)
    db.commit()
    db.refresh(db_setting)
    return db_setting