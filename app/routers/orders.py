from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from datetime import datetime
from typing import List, Optional
from .. import models, schemas
from ..database import get_db
from ..deps import get_current_user_optional
from ..ws_manager import broadcast_orders_changed
from .payments import create_order_payment
import uuid

router = APIRouter(prefix="/api/orders", tags=["Orders"])

def _effective_price(product: models.Product) -> float:
    """គណនាតម្លៃពិតប្រាកដបន្ទាប់ពីដក Sale Discount"""
    if product.is_on_sale and product.sale_percent and product.sale_percent > 0:
        return round(product.price * (1 - product.sale_percent / 100), 2)
    return product.price


def payment_branding(db: Session) -> dict:
    """អានព័ត៌មាន Bakong Wallet / Payment ពី Site Settings
    (Admin កំណត់ក្នុង Admin Panel -> Settings -> Bakong Wallet)

    - payment_company_name → ចំណងជើងលើផ្ទាំង Checkout (Default: Udom Shop)
    - payment_display_name → ឈ្មោះអ្នកទទួលប្រាក់ (បង្ហាញលើ Bakong Wallet — Default: Udom)
    - payment_bakong_id    → Bakong Wallet ID (លេខគណនីផ្លូវការ — Default: Udom)
    - payment_currency     → USD | KHR  និង payment_khr_rate (អត្រាប្តូរប្រាក់)
    """
    rows = {s.key: s.value for s in db.query(models.SiteSetting).all()}
    site_name = rows.get("site_name") or ""
    try:
        khr_rate = float(rows.get("payment_khr_rate") or 4100)
    except (TypeError, ValueError):
        khr_rate = 4100.0
    if khr_rate <= 0:
        khr_rate = 4100.0
    return {
        "company_name": rows.get("payment_company_name") or site_name or "Udom Shop",
        "display_name": rows.get("payment_display_name") or site_name or "Udom",
        "bakong_id": rows.get("payment_bakong_id") or "Udom",
        "currency": (rows.get("payment_currency") or "USD").upper(),
        "khr_rate": khr_rate,
    }

@router.post("/checkout", response_model=schemas.CheckoutResponse)
async def checkout(
    order: schemas.CheckoutRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    # Guest Checkout — អតិថិជនអត់ចាំបាច់ Login (Token ជាជម្រើស)
    current_user: Optional[models.User] = Depends(get_current_user_optional),
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
        purchased.append((product, item.quantity, unit_price, getattr(item, "variant", None)))
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
    # (Guest: user_id = None — Order ភ្ជាប់តាមលេខទូរសព្ទ/អ៊ីមែលជំនួសវិញ)
    customer_email = (order.customer_email or "").strip()
    profile_name = ""
    user_id = None
    if isinstance(current_user, models.User):
        user_id = current_user.id
        profile_name = current_user.name or ""
        if not customer_email:
            customer_email = current_user.email or ""

    shipping_addr = order.shipping_address or ""
    # ពិនិត្យថាអតិថិជនកុម្ម៉ង់នៅភ្នំពេញ (Cash on Delivery) ឬតាមបណ្តាខេត្ត (ABA Pay KHQR)
    is_phnom_penh = (
        "ភ្នំពេញ" in shipping_addr
        or "phnom penh" in shipping_addr.lower()
        or (order.payment_method or "").lower() == "cod"
    )
    payment_method = "cod" if is_phnom_penh else "aba_pay"

    new_order = models.Order(
        user_id=user_id,
        total_amount=total,
        status="pending",
        promo_code=order.promo_code if discount_applied else None,
        # ព័ត៌មានអ្នកទទួល / ដឹកជញ្ជូន — បើអត់បញ្ចូល យកឈ្មោះពី Profile ដោយស្វ័យប្រវត្តិ
        customer_name=(order.customer_name or "").strip() or profile_name or "Customer",
        customer_phone=(order.customer_phone or "").strip(),
        customer_email=customer_email,
        shipping_address=shipping_addr,
        payment_method=payment_method,
        note=order.note or "",
    )
    db.add(new_order)
    db.commit()
    db.refresh(new_order)

    # បង្កើត Order Items និងបន្ថយ Stock
    for product, qty, unit_price, variant in purchased:
        db.add(models.OrderItem(
            order_id=new_order.id,
            product_id=product.id,
            quantity=qty,
            price=unit_price,
            variant=variant or None
        ))
        product.stock -= qty
    db.commit()

    payment = None
    # បង្កើត ABA Pay / KHQRcc Payment សម្រាប់តែការកុម្ម៉ង់តាមបណ្តាខេត្តប៉ុណ្ណោះ (ត្រូវគិតលុយមុន)
    # នៅភ្នំពេញ មិនបង្ហាញ QR ទេ ព្រោះអីវ៉ាន់ដល់ដៃបានគិតលុយ (COD)
    if payment_method != "cod":
        payment = await create_order_payment(
            order_id=new_order.id,
            amount=total,
            remark=f"Order #{new_order.id}",
            items=[
                {"name": product.name, "quantity": qty, "price": unit_price}
                for product, qty, unit_price, *rest in purchased
            ],
            db=db,
        )
        if payment:
            new_order.payment_ref = payment["transaction_id"]
            # រក្សាទុក QR / Redirect URL ក្នុង Database
            # -> អតិថិជន Refresh ឬបើកទំព័រឡើងវិញក៏ឃើញ QR ដដែល (មិនបាត់)
            new_order.payment_qr_url = payment.get("qr_url") or ""
            new_order.payment_url = payment.get("url") or ""
            new_order.payment_checkout_url = payment.get("checkout_url") or ""
            db.commit()

    # Redirect Checkout URL (ABA Pay Managed Checkout) — ប្រើជាជម្រើស
    payment_url = payment["url"] if payment else ""

    branding = payment_branding(db)

    # Real-time: ជូនដំណឹងទៅ Admin (Orders ថ្មីឡើងភ្លាម) និង Storefront
    background_tasks.add_task(broadcast_orders_changed)

    return {
        "order_id": new_order.id,
        "total_amount": total,
        "status": "pending",
        "payment_method": payment_method,
        "payment_url": payment_url,
        "payment_checkout_url": payment["checkout_url"] if payment else "",
        "payment_enabled": payment is not None,
        "payment_transaction_id": payment["transaction_id"] if payment else None,
        "payment_qr_url": payment["qr_url"] if payment else None,
        "payment_qr": payment["qr"] if payment else None,
        "payment_company_name": branding["company_name"],
        "payment_display_name": branding["display_name"],
        "payment_bakong_id": branding["bakong_id"],
        "currency": branding["currency"],
        "khr_rate": branding["khr_rate"],
    }

@router.get("/{order_id}/status")
def order_status(order_id: int, db: Session = Depends(get_db)):
    """ពិនិត្យស្ថានភាព Order តាមលេខសម្គាល់ (សម្រាប់ទំព័រ Order Success)

    ត្រឡប់ QR + ព័ត៌មាន Bakong ផងដែរ ដើម្បីឱ្យអតិថិជន Refresh ទំព័រហើយ
    នៅតែឃើញ QR សម្រាប់បង់ប្រាក់ (មិនបាត់ពេល Refresh)"""
    order = db.query(models.Order).filter(models.Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    branding = payment_branding(db)
    return {
        "order_id": order.id,
        "status": order.status,
        "total_amount": order.total_amount,
        "payment_method": getattr(order, "payment_method", "aba_pay") or "aba_pay",
        "payment_enabled": bool(order.payment_ref),
        "payment_transaction_id": order.payment_ref,
        "payment_qr_url": order.payment_qr_url or None,
        "payment_url": order.payment_url or None,
        "payment_checkout_url": order.payment_checkout_url or None,
        "payment_company_name": branding["company_name"],
        "payment_display_name": branding["display_name"],
        "payment_bakong_id": branding["bakong_id"],
        "currency": branding["currency"],
        "khr_rate": branding["khr_rate"],
        "customer_name": order.customer_name or "",
        "customer_phone": order.customer_phone or "",
        "customer_email": order.customer_email or "",
        "shipping_address": order.shipping_address or "",
    }