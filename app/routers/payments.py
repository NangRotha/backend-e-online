import base64
import hashlib
import hmac
import json
import logging
import uuid
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import Optional, Dict, List
from .. import models, schemas
from ..database import get_db
from ..config import settings
from ..email_sender import smtp_configured, brevo_api_configured, send_order_receipt_email
from ..ws_manager import broadcast_orders_changed

# qrcode ជា Optional — បើ Library មិនបានដំឡើង App នៅតែដំណើរការ (ត្រឡប់ QR ចេញពី Gateway)
try:
    from ..qr import generate_qr_png
except Exception:  # noqa: BLE001
    generate_qr_png = None

try:
    from ..storage import save_upload
except Exception:  # noqa: BLE001
    save_upload = None

router = APIRouter(prefix="/api/payments", tags=["ABA Pay (KHQRcc)"])

logger = logging.getLogger("uvicorn.error")

KHQRCC_BASE = "https://khqr.cc"
# Managed Checkout (requestv2) — Auto-redirect ទៅ ABA Pay Checkout (ប្រើជាមួយ Plugin)
KHQRCC_REDIRECT_BASE = "https://khqr.cc/api/payment/requestv2"
# Frontend Checkout URL (Managed Checkout v2) — ទំព័រ ABA Pay ផ្ទាល់ (មាន KHQR + Deeplink)
KHQRCC_CHECKOUT_BASE = "https://checkout.anajakpay.com/payment/khqrcc"


def get_khqrcc_credentials(db: Optional[Session] = None) -> tuple[str, str]:
    """ទាញយក Profile ID និង Secret Key ពី Database (SiteSetting) ឬ Environment (config.py)"""
    profile_id = (settings.KHQRCC_PROFILE_ID or "").strip()
    secret_key = (settings.KHQRCC_SECRET_KEY or "").strip()
    if db is not None:
        try:
            rows = {
                s.key: s.value
                for s in db.query(models.SiteSetting).filter(
                    models.SiteSetting.key.in_(["khqrcc_profile_id", "khqrcc_secret_key"])
                ).all()
            }
            db_profile = (rows.get("khqrcc_profile_id") or "").strip()
            db_secret = (rows.get("khqrcc_secret_key") or "").strip()
            if db_profile:
                profile_id = db_profile
            if db_secret:
                secret_key = db_secret
        except Exception as e:
            logger.warning(f"Could not load khqrcc credentials from DB: {e}")
    return profile_id, secret_key


def payment_configured(db: Optional[Session] = None) -> bool:
    """ពិនិត្យថាបានកំណត់ KHQRcc (Profile ID + Secret Key) ឬអត់"""
    profile_id, secret_key = get_khqrcc_credentials(db)
    if not (profile_id and secret_key):
        return False
    if secret_key in ("REGENERATE-THIS-KEY", "PUT_REAL_SECRET_KEY_OR_SKIP_THIS_LINE", "YOUR_SECRET_KEY"):
        return False
    return True


def _extract_qr_fields(result: dict) -> tuple[str, str]:
    """ត្រឡប់ (qr_string, qr_image_url) ពី Response របស់ Gateway

    Gateway អាចត្រឡប់ឈ្មោះ Field ផ្សេងគ្នា (ឬ JSON) ដូច្នេះយើងពិនិត្យច្រើនទម្រង់។
    """
    if not isinstance(result, dict):
        return "", ""
    data = result.get("data") if isinstance(result.get("data"), dict) else result

    def pick(*keys) -> str:
        for source in (data, result):
            for key in keys:
                value = source.get(key) if isinstance(source, dict) else None
                if isinstance(value, str) and value.strip():
                    return value.strip()
        return ""

    qr_string = pick(
        "qr", "qr_string", "qrString", "qr_code", "qrCode", "qr_data", "qrData", "emv"
    )
    qr_image = pick(
        "qr_url", "qrUrl", "qr_image", "qrImage", "qr_image_url", "qrImageUrl",
        "image_url", "imageUrl", "image",
    )
    return qr_string, qr_image


def _ensure_qr_image(qr_string: str, qr_image_url: str, transaction_id: str) -> str:
    """ធានាថាមានរូប QR — បើ Gateway មិនផ្តល់រូប យើងបង្កើតខ្លួនឯងពី EMV string"""
    if qr_image_url:
        return qr_image_url
    if not qr_string or generate_qr_png is None or save_upload is None:
        return ""
    try:
        png = generate_qr_png(qr_string)
        saved = save_upload(png, f"khqr-{transaction_id}.png", folder="qr")
        return saved.get("url", "") or ""
    except Exception as exc:  # noqa: BLE001
        logger.error(f"QR image generation failed for {transaction_id}: {exc}")
        return ""


def _encode_items(items: Optional[List[Dict]]) -> str:
    """Base64(JSON) នៃ Cart Items — តាមឯកសារ KHQRcc (items parameter)"""
    if not items:
        return ""
    try:
        raw = json.dumps(items, ensure_ascii=False, separators=(",", ":"))
        return base64.b64encode(raw.encode()).decode()
    except Exception:  # noqa: BLE001
        return ""


def _payment_params(
    secret_key: str,
    transaction_id: str,
    amount: str,
    success_url: str,
    remark: str = "",
    cancel_url: str = "",
    items_b64: str = "",
    custom_fields_b64: str = "",
) -> dict:
    """បង្កើត Parameters តាមឯកសារ KHQRcc (hash = sha1(secret+id+amount+success_url+remark))"""
    params = {
        "transaction_id": transaction_id,
        "amount": amount,
        "success_url": success_url,
        "remark": remark,
        "hash": _sha1(
            secret_key, transaction_id, amount, success_url, remark
        ),
    }
    if cancel_url:
        params["cancel_url"] = cancel_url
    if items_b64:
        params["items"] = items_b64
    if custom_fields_b64:
        params["custom_fields"] = custom_fields_b64
    return params


def build_redirect_url(
    profile_id: str,
    secret_key: str,
    transaction_id: str,
    amount: str,
    success_url: str,
    remark: str = "",
    cancel_url: str = "",
    items_b64: str = "",
    custom_fields_b64: str = "",
) -> str:
    """Managed Checkout (requestv2) — Gateway នឹង Auto-redirect ទៅ ABA Pay Checkout

    ⚠️ នេះជា URL ដែល **KHQRcc Checkout Plugin** ត្រូវការ (`KhqrPayway.openCheckout`).
    """
    query = urlencode(
        _payment_params(
            secret_key, transaction_id, amount, success_url, remark, cancel_url, items_b64, custom_fields_b64
        )
    )
    return f"{KHQRCC_REDIRECT_BASE}/{profile_id}?{query}"


def build_checkout_url(
    profile_id: str,
    secret_key: str,
    transaction_id: str,
    amount: str,
    success_url: str,
    remark: str = "",
    cancel_url: str = "",
    items_b64: str = "",
    custom_fields_b64: str = "",
) -> str:
    """Frontend Checkout URL ផ្ទាល់ (`checkout.anajakpay.com/payment/khqrcc/{profile}`)

    លឿនជាងមួយជំហាត់ (មិនបាច់ Redirect) — ប្រើសម្រាប់ Link / “Open checkout”
    """
    query = urlencode(
        _payment_params(
            secret_key, transaction_id, amount, success_url, remark, cancel_url, items_b64, custom_fields_b64
        )
    )
    return f"{KHQRCC_CHECKOUT_BASE}/{profile_id}?{query}"


def _encode_custom_fields(data: Optional[Dict]) -> str:
    """Base64(JSON) នៃទិន្នន័យបន្ថែម (Gateway ផ្ញើមកវិញពេល Callback)"""
    if not data:
        return ""
    try:
        raw = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        return base64.b64encode(raw.encode()).decode()
    except Exception:  # noqa: BLE001
        return ""



def _fmt_amount(amount: float) -> str:
    """បម្លែងចំនួនទឹកប្រាក់ទៅជាខ្សែអក្សរ PHP-style (12.50 -> '12.5', 12.00 -> '12')"""
    return f"{amount:.2f}".rstrip("0").rstrip(".")


def _sha1(*parts) -> str:
    return hashlib.sha1("".join(str(p) for p in parts).encode()).hexdigest()


def _sha256(*parts) -> str:
    return hashlib.sha256("".join(str(p) for p in parts).encode()).hexdigest()


def _qr_api_url(profile_id: str) -> str:
    return (
        f"{KHQRCC_BASE}/api/{profile_id}"
        "/payment-gateway/v1/payments/qr-api-khqrcc"
    )


def _verify_api_url(profile_id: str) -> str:
    return (
        f"{KHQRCC_BASE}/api/{profile_id}"
        "/payment-gateway/v1/payments/check-transv2-khqrcc"
    )


# ============================================================
# Public: ពិនិត្យថាបានបើក ABA Pay / KHQRcc ឬអត់
# ============================================================
@router.get("/config")
def payment_config(db: Session = Depends(get_db)):
    """ព័ត៌មាន Payment សម្រាប់ Storefront (Checkout + Order Success)

    រួមទាំងព័ត៌មាន Bakong Wallet ដែល Admin កំណត់ក្នុង Settings៖
    Company Name / Display Name / Bakong Wallet ID / Currency (+ KHR rate)"""
    from .orders import payment_branding  # import ក្នុង Function ដើម្បីកុំឱ្យ Circular Import

    branding = payment_branding(db)
    return {
        "enabled": payment_configured(db),
        "provider": "aba_khqrcc",
        **branding,
    }


# ============================================================
# Public: បង្កើត QR Code សម្រាប់បង់ប្រាក់ (Scan & Pay)
# ============================================================
@router.post("/create", response_model=schemas.PaymentCreateResponse)
async def create_payment(
    payload: schemas.PaymentCreateRequest,
    db: Session = Depends(get_db),
):
    if not payment_configured(db):
        raise HTTPException(status_code=400, detail="ABA Pay (KHQRcc) is not configured")

    profile_id, secret_key = get_khqrcc_credentials(db)
    amount = _fmt_amount(payload.amount)
    data = {
        "transaction_id": payload.transaction_id,
        "amount": amount,
        "success_url": payload.success_url,
        "remark": payload.remark,
        "hash": _sha1(
            secret_key,
            payload.transaction_id,
            amount,
            payload.success_url,
            payload.remark,
        ),
    }
    # Parameters ជាជម្រើស (តាមឯកសារ KHQRcc) — Gateway ផ្ញើមកវិញពេល Callback
    for key in ("cancel_url", "items", "custom_fields"):
        value = (getattr(payload, key, "") or "").strip()
        if value:
            data[key] = value
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(_qr_api_url(profile_id), data=data)
        try:
            result = resp.json()
        except Exception:
            raise HTTPException(status_code=502, detail="ABA Pay gateway error")

    if result.get("responseCode") != 0:
        raise HTTPException(
            status_code=502,
            detail=result.get("responseMessage", "ABA Pay gateway error"),
        )

    d = result.get("data") if isinstance(result.get("data"), dict) else result
    qr_string, qr_image = _extract_qr_fields(result)
    return {
        "transaction_id": d.get("transaction_id") or payload.transaction_id,
        "amount": d.get("amount") or amount,
        "qr": qr_string,
        "qr_url": qr_image,
    }


# ============================================================
# Public: ពិនិត្យស្ថានភាពការបង់ប្រាក់ (Polling — auto-payment detection)
# ============================================================
@router.post("/status", response_model=schemas.PaymentStatusResponse)
async def check_status(
    payload: schemas.PaymentStatusRequest,
    db: Session = Depends(get_db),
):
    if not payment_configured(db):
        raise HTTPException(status_code=400, detail="ABA Pay (KHQRcc) is not configured")

    profile_id, secret_key = get_khqrcc_credentials(db)
    data = {
        "transaction_id": payload.transaction_id,
        "hash": _sha1(secret_key, payload.transaction_id),
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(_verify_api_url(profile_id), data=data)
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
    if not payment_configured(db):
        raise HTTPException(status_code=400, detail="ABA Pay (KHQRcc) is not configured")

    profile_id, secret_key = get_khqrcc_credentials(db)
    # ពិនិត្យឡើងវិញជាមួយ Gateway (កុំជឿ Frontend តែម្នាក់ឯង)
    data = {
        "transaction_id": payload.transaction_id,
        "hash": _sha1(secret_key, payload.transaction_id),
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(_verify_api_url(profile_id), data=data)
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
    profile_id, secret_key = get_khqrcc_credentials(db)
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
            secret_key, req_time, transaction_id, amount, "SUCCESS"
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
    # អ៊ីមែលទទួល Receipt: អ៊ីមែលអតិថិជន (Guest Checkout) មុន បន្ទាប់មកអ៊ីមែលគណនី
    to_email = (order.customer_email or "").strip() or (user.email if user else None)
    return {
        "to_email": to_email,
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
    # Real-time: Admin និង Storefront ទទួលដំណឹងភ្លាមៗថា Order បានបង់ប្រាក់រួច
    background_tasks.add_task(broadcast_orders_changed)
    try:
        info = _load_order_receipt_data(db, order)
        # គាំទ្រទាំង Brevo HTTP API និង SMTP (email_sender ជ្រើសរើសខ្លួនឯង)
        if info["to_email"] and (smtp_configured() or brevo_api_configured()):
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
    items: Optional[List[Dict]] = None,
    db: Optional[Session] = None,
) -> Optional[Dict]:
    """បង្កើតការបង់ប្រាក់សម្រាប់ Order មួយ៖

    1. ទាញ **QR (EMV string + រូបភាព)** ពី KHQRcc QR API
    2. បើ Gateway មិនផ្តល់រូបភាព → បង្កើតរូប QR ខ្លួនឯងពី EMV string (អតិថិជននៅតែឃើញ QR)
    3. បង្កើត **Managed Checkout URL** ក្នុងម៉ាស៊ីន (មិនបាច់រង់ចាំ Gateway)

    ដូច្នេះទោះ Gateway មានបញ្ហា/Timeout អតិថិជននៅតែអាចបង់ប្រាក់តាម Link ✓
    """
    if not payment_configured(db):
        return None

    profile_id, secret_key = get_khqrcc_credentials(db)
    transaction_id = f"ECOMM{order_id}-{uuid.uuid4().hex[:8]}"
    amount_str = _fmt_amount(amount)
    success_url = f"{settings.FRONTEND_URL}/order-success?order_id={order_id}"
    cancel_url = f"{settings.FRONTEND_URL}/checkout"

    # 1) QR ពី Gateway (QR API)
    items_b64 = _encode_items(items)
    custom_fields_b64 = _encode_custom_fields(
        {"order_id": order_id, "remark": remark, "source": "web"}
    )
    qr_string, qr_image = "", ""
    try:
        data = {
            "transaction_id": transaction_id,
            "amount": amount_str,
            "success_url": success_url,
            "remark": remark,
            "hash": _sha1(
                secret_key,
                transaction_id,
                amount_str,
                success_url,
                remark,
            ),
        }
        if cancel_url:
            data["cancel_url"] = cancel_url
        if items_b64:
            data["items"] = items_b64
        if custom_fields_b64:
            data["custom_fields"] = custom_fields_b64

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(_qr_api_url(profile_id), data=data)
            result = resp.json()
            if result.get("responseCode") == 0:
                qr_string, qr_image = _extract_qr_fields(result)
            else:
                logger.warning(
                    f"QR API returned non-zero code for order #{order_id}: {result}"
                )
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"QR API failed for order #{order_id}: {exc}")

    # 2) បើគ្មានរូបភាព QR -> បង្កើតខ្លួនឯងពី EMV string
    qr_image = _ensure_qr_image(qr_string, qr_image, transaction_id)

    # 3) Checkout URLs (គណនាក្នុងម៉ាស៊ីន — ប្រើបានភ្លាម ទោះ Gateway ជាប់)
    url_args = (
        profile_id,
        secret_key,
        transaction_id,
        amount_str,
        success_url,
        remark,
        cancel_url,
        items_b64,
        custom_fields_b64,
    )
    redirect_url = build_redirect_url(*url_args)   # requestv2 (Plugin + Redirect)
    checkout_url = build_checkout_url(*url_args)   # checkout.anajakpay.com (ផ្ទាល់)

    return {
        "transaction_id": transaction_id,
        "qr_url": qr_image,
        "qr": qr_string,
        "url": redirect_url,
        "checkout_url": checkout_url,
    }
