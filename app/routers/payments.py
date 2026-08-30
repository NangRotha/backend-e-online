import hashlib
import hmac
import uuid
import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional, Dict
from .. import models, schemas
from ..database import get_db
from ..config import settings

router = APIRouter(prefix="/api/payments", tags=["ABA Pay (KHQRcc)"])

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
        order.status = "paid"
        db.commit()

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
async def payment_callback(payload: Dict, db: Session = Depends(get_db)):
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
            order.status = "paid"
            db.commit()

    # តែងតែបញ្ជូន 200 ដើម្បីកុំឱ្យ Gateway ផ្ញើវិញដដែលៗ
    return {"received": True}


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
