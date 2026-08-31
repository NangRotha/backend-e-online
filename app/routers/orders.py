from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
from typing import List, Optional
from .. import models, schemas
from ..database import get_db
from ..deps import get_current_user
from .payments import create_order_payment
import uuid

router = APIRouter(prefix="/api/orders", tags=["Orders"])

def _effective_price(product: models.Product) -> float:
    """គណនាតម្លៃពិតប្រាកដបន្ទាប់ពីដក Sale Discount"""
    if product.is_on_sale and product.sale_percent and product.sale_percent > 0:
        return round(product.price * (1 - product.sale_percent / 100), 2)
    return product.price

@router.post("/checkout", response_model=schemas.CheckoutResponse)
async def checkout(
    order: schemas.CheckoutRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),  # យក User ID ពី JWT
):
    # ប្រើ `items` (Cart) ឬ Single product (`product_id` + `quantity`) សម្រាប់ Backward Compatibility
    if order.items:
        items: List[schemas.CheckoutItem] = order.items
    elif order.product_id is not None:
        if order.quantity is None:
            raise HTTPException(status_code=400, detail="quantity is required")
        items = [schemas.CheckoutItem(product_id=order.product_id, quantity=order.quantity)]
    else:
        raise HTTPException(status_code=400, detail="Provide either 'items' or 'product_id' and 'quantity'")

    # ពិនិត្យ Stock និងគណនា Total (រាប់បញ្ចូល Sale Discount)
    total = 0.0
    purchased = []  # (product, quantity, effective_unit_price)
    for item in items:
        if item.quantity <= 0:
            raise HTTPException(status_code=400, detail="Quantity must be greater than zero")
        product = db.query(models.Product).filter(models.Product.id == item.product_id).first()
        if not product:
            raise HTTPException(status_code=400, detail=f"Product {item.product_id} not found")
        if product.stock < item.quantity:
            raise HTTPException(status_code=400, detail=f"Product '{product.name}' out of stock")
        unit_price = _effective_price(product)
        purchased.append((product, item.quantity, unit_price))
        total += unit_price * item.quantity

    discount_applied = False
    if order.promo_code:
        promo = db.query(models.Discount).filter(models.Discount.code == order.promo_code).first()
        if promo and promo.is_active and promo.used_count < promo.max_uses:
            if promo.expiry_date and promo.expiry_date < datetime.now():
                raise HTTPException(status_code=400, detail="Promo code expired")
            total -= (promo.percent / 100) * total
            promo.used_count += 1
            discount_applied = True
        else:
            raise HTTPException(status_code=400, detail="Invalid or expired promo code")

    total = round(total, 2)

    # បង្កើត Order ក្នុង Database
    new_order = models.Order(
        user_id=current_user.id,
        total_amount=total,
        status="pending",
        promo_code=order.promo_code if discount_applied else None,
        # ព័ត៌មានអ្នកទទួល / ដឹកជញ្ជូន — បើអត់បញ្ចូល យកឈ្មោះពី Profile ដោយស្វ័យប្រវត្តិ
        customer_name=(order.customer_name or "").strip() or current_user.name,
        customer_phone=(order.customer_phone or "").strip(),
        shipping_address=order.shipping_address or "",
        note=order.note or "",
    )
    db.add(new_order)
    db.commit()
    db.refresh(new_order)

    # បង្កើត Order Items និងបន្ថយ Stock
    for product, qty, unit_price in purchased:
        db.add(models.OrderItem(
            order_id=new_order.id,
            product_id=product.id,
            quantity=qty,
            price=unit_price
        ))
        product.stock -= qty
    db.commit()

    # បង្កើត ABA Pay / KHQRcc Payment (QR Code) ដោយស្វ័យប្រវត្តិ
    payment = await create_order_payment(
        order_id=new_order.id,
        amount=total,
        remark=f"Order #{new_order.id}",
    )
    if payment:
        new_order.payment_ref = payment["transaction_id"]
        db.commit()

    # Redirect Checkout URL (ABA Pay Managed Checkout) — ប្រើជាជម្រើស
    payment_url = payment["url"] if payment else f"https://pay.example.com/checkout/{uuid.uuid4()}"

    return {
        "order_id": new_order.id,
        "total_amount": total,
        "status": "pending",
        "payment_url": payment_url,
        "payment_enabled": payment is not None,
        "payment_transaction_id": payment["transaction_id"] if payment else None,
        "payment_qr_url": payment["qr_url"] if payment else None,
        "payment_qr": payment["qr"] if payment else None,
    }

@router.get("/{order_id}/status")
def order_status(order_id: int, db: Session = Depends(get_db)):
    """ពិនិត្យស្ថានភាព Order តាមលេខសម្គាល់ (សម្រាប់ទំព័រ Order Success)"""
    order = db.query(models.Order).filter(models.Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return {
        "order_id": order.id,
        "status": order.status,
        "total_amount": order.total_amount,
    }