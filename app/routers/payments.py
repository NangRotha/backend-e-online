import hashlib
import hmac
import logging
import uuid
import httpx
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import Optional, Dict
from .. import models, schemas
from ..database import get_db
from ..config import settings
from ..email_sender import smtp_configured, send_order_receipt_email

router = APIRouter(prefix="/api/payments", tags=["ABA Pay (KHQRcc)"])

logger = logging.getLogger("uvicorn.error")

KHQRCC_BASE = "https://khqr.cc"


def payment_configured() -> bool:
    """ពិនិត្យថាបានកំណត់ KHQRcc (Profile ID + Secret Key) ឬអត់"""
    return bool(settings.KHQRCC_PROFILE_ID and settings.KHQRCC_SECRET_KEY)


def _fmt_amount(amount: float) -> str:
    """បម្លែងចំនួនទឹកប្រាក់ទៅជាខ្សែអក្សរ PHP-style (12.50 -> '12.5', 12.00 -> '12')"""
    return f"{amount:.2f}".rstrip("0").rstrip(".")


def _sha1(*parts) -> str:
    return hashlib.sha1("".join(str(p) for p in parts).encode()).hexdigest()


def _sha256(*parts) -> str:
    return hashlib.sha256("".join(str(p) for p in parts).encode()).hexdigest()


def _qr_api_url() -> str:
    return (
        f"{KHQRCC_BASE}/api/{settings.KHQRCC_PROFILE_ID}"
        "/payment-gateway/v1/payments/qr-api-khqrcc"
    )


def _verify_api_url() -> str:
    return (
        f"{KHQRCC_BASE}/api/{settings.KHQRCC_PROFILE_ID}"
        "/payment-gateway/v1/payments/check-transv2-khqrcc"
    )


# ============================================================
# Public: ពិនិត្យថាបានបើក ABA Pay / KHQRcc ឬអត់
# ============================================================
@router.get("/config")
def payment_config():
    return {
        "enabled": payment_configured(),
        "provider": "aba_khqrcc",
    }


# ============================================================
# Public: បង្កើត QR Code សម្រាប់បង់ប្រាក់ (Scan & Pay)
# ============================================================
@router.post("/create", response_model=schemas.PaymentCreateResponse)
async def create_payment(payload: schemas.PaymentCreateRequest):
    if not payment_configured():
        raise HTTPException(status_code=400, detail="ABA Pay (KHQRcc) is not configured")

    amount = _fmt_amount(payload.amount)
    data = {
        "transaction_id": payload.transaction_id,
        "amount": amount,
        "success_url": payload.success_url,
        "remark": payload.remark,
        "hash": _sha1(
            settings.KHQRCC_SECRET_KEY,
            payload.transaction_id,
            amount,
            payload.success_url,
            payload.remark,
        ),
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(_qr_api_url(), data=data)
        try:
            result = resp.json()
        except Exception:
            raise HTTPException(status_code=502, detail="ABA Pay gateway error")

    if result.get("responseCode") != 0:
        raise HTTPException(
            status_code=502,
            detail=result.get("responseMessage", "ABA Pay gateway error"),
        )

    d = result.get("data") or {}
    return {
        "transaction_id": d.get("transaction_id", payload.transaction_id),
        "amount": d.get("amount", amount),
        "qr": d.get("qr", ""),
        "qr_url": d.get("qr_url", ""),
    }


# ============================================================
# Public: ពិនិត្យស្ថានភាពការបង់ប្រាក់ (Polling — auto-payment detection)
# ============================================================
@router.post("/status", response_model=schemas.PaymentStatusResponse)
async def check_status(payload: schemas.PaymentStatusRequest):
    if not payment_configured():
        raise HTTPException(status_code=400, detail="ABA Pay (KHQRcc) is not configured")

    data = {
        "transaction_id": payload.transaction_id,
        "hash": _sha1(settings.KHQRCC_SECRET_KEY, payload.transaction_id),
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(_verify_api_url(), data=data)
        try:
            result = resp.json()
        except Exception:
            raise HTTPException(status_code=502, detail="ABA Pay gateway error")

    if result.get("responseCode") != 0:
        raise HTTPException(
            status_code=502,
            detail=result.get("responseMessage", "ABA Pay verification failed"),
        )

    d = result.get("data") or {}
    return {
        "transaction_id": payload.transaction_id,
        "status": d.get("status", "pending"),
        "amount": d.get("amount"),
    }


# ============================================================
# Public: បញ្ជាក់ការបង់ប្រាក់ (ពិនិត្យឡើងវិញជាមួយ Gateway មុនប្តូរ Order -> paid)
# ============================================================
@router.post("/confirm")
async def confirm_payment(
    payload: schemas.PaymentStatusRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    if not payment_configured():
        raise HTTPException(status_code=400, detail="ABA Pay (KHQRcc) is not configured")

    # ពិនិត្យឡើងវិញជាមួយ Gateway (កុំជឿ Frontend តែម្នាក់ឯង)
    data = {
        "transaction_id": payload.transaction_id,
        "hash": _sha1(settings.KHQRCC_SECRET_KEY, payload.transaction_id),
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(_verify_api_url(), data=data)
        try:
            result = resp.json()
        except Exception:
            raise HTTPException(status_code=502, detail="ABA Pay gateway error")

    if result.get("responseCode") != 0:
        raise HTTPException(status_code=502, detail="ABA Pay verification failed")
    d = result.get("data") or {}
    if d.get("status") != "success":
        raise HTTPException(status_code=400, detail="Payment not confirmed yet")

    order = db.query(models.Order).filter(
        models.Order.payment_ref == payload.transaction_id
    ).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    if order.status != "paid":
        _mark_paid_and_notify(db, order, background_tasks)

    return {
        "order_id": order.id,
        "status": "paid",
        "amount": d.get("amount"),
    }


# ============================================================
# Webhook: Server-to-Server notification (auto-mark paid)
# Callback hash = sha256(secret + req_time + transaction_id + amount + "SUCCESS")
# ============================================================
@router.post("/callback")
async def payment_callback(
    payload: Dict,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    transaction_id = (
        payload.get("transaction_id")
        or payload.get("order_id")
        or ""
    )
    amount = payload.get("amount") or payload.get("paid_amount") or ""
    status = (payload.get("status") or "").lower()
    req_time = str(payload.get("req_time") or "")
    received_hash = payload.get("hash") or ""

    if status == "success":
        expected = _sha256(
            settings.KHQRCC_SECRET_KEY, req_time, transaction_id, amount, "SUCCESS"
        )
        if not hmac.compare_digest(expected, received_hash):
            raise HTTPException(status_code=400, detail="Invalid hash")

        order = db.query(models.Order).filter(
            models.Order.payment_ref == transaction_id
        ).first()
        if order and order.status != "paid":
            _mark_paid_and_notify(db, order, background_tasks)

    # តែងតែបញ្ជូន 200 ដើម្បីកុំឱ្យ Gateway ផ្ញើវិញដដែលៗ
    return {"received": True}


# ============================================================
# Helper: ផ្ញើ Email Receipt ពេលអ្នកប្រើបង់ប្រាក់ជោគជ័យ
# ============================================================
def _load_order_receipt_data(db: Session, order: models.Order) -> dict:
    """ប្រមូលទិន្នន័យ Order សម្រាប់ Email Receipt (ផ្ញើទៅ User Gmail)"""
    user = db.query(models.User).filter(models.User.id == order.user_id).first()
    items = (
        db.query(models.OrderItem)
        .filter(models.OrderItem.order_id == order.id)
        .all()
    )
    item_rows = []
    subtotal = 0.0
    for oi in items:
        product = (
            db.query(models.Product)
            .filter(models.Product.id == oi.product_id)
            .first()
        )
        item_rows.append(
            {
                "name": product.name if product else f"Product #{oi.product_id}",
                "quantity": oi.quantity,
                "unit_price": oi.price,
            }
        )
        subtotal += (oi.price or 0) * oi.quantity
    subtotal = round(subtotal, 2)
    discount = (
        round(subtotal - order.total_amount, 2) if subtotal > order.total_amount else 0.0
    )
    site_map = {s.key: s.value for s in db.query(models.SiteSetting).all()}
    return {
        "to_email": user.email if user else None,
        "data": {
            "site_name": site_map.get("site_name")
            or settings.SMTP_FROM_NAME
            or "Our Store",
            "site_logo": site_map.get("site_logo") or "",
            "customer_name": order.customer_name
            or (user.name if user else "Customer"),
            "order_id": order.id,
            "created_at": order.created_at,
            "items": item_rows,
            "subtotal": subtotal,
            "discount": discount,
            "total": order.total_amount,
            "phone": order.customer_phone or "",
            "address": order.shipping_address or "",
            "note": order.note or "",
            "frontend_url": settings.FRONTEND_URL,
        },
    }


def _mark_paid_and_notify(
    db: Session,
    order: models.Order,
    background_tasks: BackgroundTasks,
) -> bool:
    """ប្តូរ Order -> paid (តែម្តង) រួចដាក់ Email Receipt ចូល Background Tasks
    (ផ្ញើបន្ទាប់ពីបញ្ជូន Response ដើម្បីកុំឱ្យអតិថិជនរង់ចាំ SMTP)"""
    if order.status == "paid":
        return False
    order.status = "paid"
    db.commit()
    try:
        info = _load_order_receipt_data(db, order)
        if info["to_email"] and smtp_configured():
            background_tasks.add_task(
                send_order_receipt_email, info["to_email"], info["data"]
            )
    except Exception as e:
        logger.error(f"Failed to queue receipt email for order #{order.id}: {e}")
    return True


# ============================================================
# Helper: បង្កើត Payment ដោយស្វ័យប្រវត្តិបន្ទាប់ពី Checkout
# ============================================================
async def create_order_payment(
    order_id: int,
    amount: float,
    remark: str,
) -> Optional[Dict]:
    """ហៅ Gateway ដើម្បីយក QR Code។ បរាជ័យ -> ត្រឡប់ None (ប្រើ Mock URL ដូចពីមុន)"""
    if not payment_configured():
        return None
    try:
        transaction_id = f"ECOMM{order_id}-{uuid.uuid4().hex[:8]}"
        success_url = f"{settings.FRONTEND_URL}/order-success?order_id={order_id}"
        payload = schemas.PaymentCreateRequest(
            transaction_id=transaction_id,
            amount=amount,
            success_url=success_url,
            remark=remark,
        )
        d = await create_payment(payload)
        # Redirect checkout URL (Managed Checkout) ជាជម្រើស
        redirect_url = (
            f"{KHQRCC_BASE}/api/payment/requestv2/{settings.KHQRCC_PROFILE_ID}"
            f"?transaction_id={transaction_id}"
            f"&amount={d['amount']}"
            f"&success_url={success_url}"
            f"&remark={remark}"
            f"&hash={_sha1(settings.KHQRCC_SECRET_KEY, transaction_id, d['amount'], success_url, remark)}"
        )
        return {
            "transaction_id": d["transaction_id"],
            "qr_url": d.get("qr_url", ""),
            "qr": d.get("qr", ""),
            "url": redirect_url,
        }
    except Exception:
        return None
