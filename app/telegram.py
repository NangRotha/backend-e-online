import html
import hashlib
import hmac
import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List
import httpx
from sqlalchemy.orm import Session
from .config import settings
from .database import SessionLocal
from . import models

logger = logging.getLogger(__name__)

TELEGRAM_API_BASE = "https://api.telegram.org"
CAMBODIA_TZ = timezone(timedelta(hours=7))


def get_telegram_settings(db: Optional[Session] = None) -> Dict[str, Any]:
    """ទាញយកការកំណត់ Telegram Bot (Token, Chat ID, Username, Enabled)
    ដោយផ្តល់អាទិភាពដល់ `site_settings` ក្នុង Database ហើយ Fallback ទៅ `settings` ក្នុង .env"""
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True

    try:
        keys = [
            "telegram_bot_token",
            "telegram_bot_username",
            "telegram_chat_id",
            "telegram_notifications_enabled",
        ]
        db_settings = {
            s.key: s.value
            for s in db.query(models.SiteSetting)
            .filter(models.SiteSetting.key.in_(keys))
            .all()
        }

        bot_token = (
            db_settings.get("telegram_bot_token")
            or settings.TELEGRAM_BOT_TOKEN
            or ""
        ).strip()
        bot_username = (
            db_settings.get("telegram_bot_username")
            or settings.TELEGRAM_BOT_USERNAME
            or ""
        ).strip()
        chat_id = (
            db_settings.get("telegram_chat_id")
            or settings.TELEGRAM_CHAT_ID
            or ""
        ).strip()

        raw_enabled = db_settings.get("telegram_notifications_enabled")
        if raw_enabled is not None:
            enabled = str(raw_enabled).lower() in ("true", "1", "yes", "on")
        else:
            enabled = bool(settings.TELEGRAM_NOTIFICATIONS_ENABLED)

        return {
            "bot_token": bot_token,
            "bot_username": bot_username,
            "chat_id": chat_id,
            "enabled": enabled,
        }
    finally:
        if close_db:
            db.close()


def telegram_configured(db: Optional[Session] = None) -> bool:
    """ពិនិត្យថាបានកំណត់ Telegram Bot Token + Username (សម្រាប់ Login Widget)"""
    cfg = get_telegram_settings(db)
    tok = cfg["bot_token"]
    user = cfg["bot_username"]
    if not (tok and user):
        return False
    if tok in ("123456:ABC-your-token", "PUT_REAL_BOT_TOKEN_OR_SKIP_THIS_LINE") or "your-token" in tok:
        return False
    return True


def telegram_notifications_active(db: Optional[Session] = None) -> bool:
    """ពិនិត្យថា Telegram Bot បានកំណត់រួចរាល់សម្រាប់ផ្ញើ Order Notifications"""
    cfg = get_telegram_settings(db)
    return bool(cfg["enabled"] and cfg["bot_token"] and cfg["chat_id"])


def verify_telegram_auth(data: dict, max_age_seconds: int = 86400) -> bool:
    """ផ្ទៀងផ្ទាត់ hash ពី Telegram Login Widget (Checking authorization)"""
    cfg = get_telegram_settings()
    tok = cfg["bot_token"]
    if not tok:
        return False

    received_hash = data.get("hash")
    if not received_hash:
        return False

    try:
        auth_date = int(data.get("auth_date", 0))
    except (TypeError, ValueError):
        return False
    if time.time() - auth_date > max_age_seconds:
        return False

    fields = {
        k: v
        for k, v in data.items()
        if k != "hash" and v is not None and v != ""
    }
    data_check_string = "\n".join(f"{k}={fields[k]}" for k in sorted(fields))

    secret_key = hashlib.sha256(tok.encode()).digest()
    computed = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    return hmac.compare_digest(computed, received_hash)


def send_telegram_message(
    text: str,
    chat_id: Optional[str] = None,
    inline_keyboard: Optional[List[List[Dict[str, str]]]] = None,
    parse_mode: str = "HTML",
    db: Optional[Session] = None,
) -> bool:
    """ផ្ញើសារតាម Telegram Bot ទៅកាន់ Chat ID ដោយប្រើ HTTP POST

    - បើមិនបញ្ជាក់ chat_id នឹងប្រើ chat_id ពីការកំណត់
    - គាំទ្រ Inline Keyboard buttons
    - ដំណើរការដោយសុវត្ថិភាព (Exception safe — មិនបង្កឱ្យ Request ដើម Error)
    """
    cfg = get_telegram_settings(db)
    token = cfg["bot_token"]
    target_chat_id = (chat_id or cfg["chat_id"] or "").strip()

    if not token or not target_chat_id:
        logger.warning("Telegram message skipped: bot_token or chat_id is missing.")
        return False

    payload: Dict[str, Any] = {
        "chat_id": target_chat_id,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    }

    if inline_keyboard:
        payload["reply_markup"] = {"inline_keyboard": inline_keyboard}

    url = f"{TELEGRAM_API_BASE}/bot{token}/sendMessage"
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(url, json=payload)
            data = resp.json()
            if not data.get("ok"):
                desc = str(data.get("description", ""))
                logger.error(f"Telegram API error: {desc}")
                # Fallback to plain text if HTML entity parsing fails
                if "parse entities" in desc.lower() or "can't parse" in desc.lower():
                    payload.pop("parse_mode", None)
                    resp2 = client.post(url, json=payload)
                    return bool(resp2.json().get("ok"))
                return False
            return True
    except Exception as exc:
        logger.error(f"Failed to send Telegram message: {exc}")
        return False


def test_telegram_connection(
    bot_token: Optional[str] = None,
    chat_id: Optional[str] = None,
    db: Optional[Session] = None,
) -> Dict[str, Any]:
    """ធ្វើតេស្តការតភ្ជាប់ Telegram Bot និងផ្ញើសារសាកល្បងទៅកាន់ Chat ID"""
    cfg = get_telegram_settings(db)
    token = (bot_token or cfg["bot_token"] or "").strip()
    target_chat_id = (chat_id or cfg["chat_id"] or "").strip()

    if not token:
        return {"success": False, "error": "Telegram Bot Token is missing."}

    # 1. ពិនិត្យ Bot តាម getMe
    bot_info = {}
    try:
        with httpx.Client(timeout=10.0) as client:
            res = client.get(f"{TELEGRAM_API_BASE}/bot{token}/getMe")
            data = res.json()
            if not data.get("ok"):
                return {"success": False, "error": f"Bot verification failed: {data.get('description')}"}
            bot_info = data.get("result", {})
    except Exception as e:
        return {"success": False, "error": f"Could not connect to Telegram API: {e}"}

    # 2. ផ្ញើសារសាកល្បងទៅកាន់ Chat ID (បើមាន)
    sent_msg = False
    if target_chat_id:
        admin_url = getattr(settings, "ADMIN_FRONTEND_URL", "https://frontend-admin-e-online.vercel.app")
        now_kh = datetime.now(CAMBODIA_TZ).strftime("%d/%m/%Y %I:%M:%S %p")
        test_text = (
            f"🤖 <b>តេស្តប្រព័ន្ធ Telegram Bot ជោគជ័យ!</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"• <b>Bot:</b> @{bot_info.get('username', 'Bot')}\n"
            f"• <b>Admin ID:</b> <code>{target_chat_id}</code>\n"
            f"• <b>ស្ថានភាព:</b> ដំណើរការល្អ (Online)\n"
            f"• <b>កាលបរិច្ឆេទ:</b> {now_kh}\n\n"
            f"🎉 ប្រព័ន្ធ Telegram បានភ្ជាប់រួចរាល់សម្រាប់ទទួលដំណឹងការកុម្ម៉ង់ទិញថ្មី!"
        )
        keyboard = [
            [{"text": "🛒 ចូលមើល Admin Orders", "url": f"{admin_url}/orders"}]
        ]
        sent_msg = send_telegram_message(
            text=test_text,
            chat_id=target_chat_id,
            inline_keyboard=keyboard,
            db=db,
        )

    return {
        "success": True,
        "bot": {
            "id": bot_info.get("id"),
            "username": bot_info.get("username"),
            "first_name": bot_info.get("first_name"),
        },
        "chat_id": target_chat_id,
        "test_message_sent": sent_msg,
    }


def send_order_created_telegram(order_id: int):
    """Background task: ផ្ញើដំណឹង Order ថ្មីទៅកាន់ Telegram របស់ Admin"""
    db = SessionLocal()
    try:
        cfg = get_telegram_settings(db)
        if not cfg["enabled"] or not cfg["bot_token"] or not cfg["chat_id"]:
            return

        order = db.query(models.Order).filter(models.Order.id == order_id).first()
        if not order:
            return

        # ទាញយក Items និង Product
        order_items = db.query(models.OrderItem).filter(models.OrderItem.order_id == order_id).all()
        products_map = {
            p.id: p
            for p in db.query(models.Product)
            .filter(models.Product.id.in_([i.product_id for i in order_items]))
            .all()
        }

        # អត្រាប្តូរប្រាក់ KHR (ពី Site Settings)
        khr_rate_setting = db.query(models.SiteSetting).filter(models.SiteSetting.key == "payment_khr_rate").first()
        try:
            khr_rate = float(khr_rate_setting.value) if khr_rate_setting and khr_rate_setting.value else 4100.0
        except (ValueError, TypeError):
            khr_rate = 4100.0

        total_usd = float(order.total_amount or 0.0)
        total_khr = int(round(total_usd * khr_rate))

        # អាសយដ្ឋានដឹកជញ្ជូន
        raw_address = (order.shipping_address or "").strip()

        # ពិនិត្យទីតាំងភ្នំពេញ និងវិធីសាស្ត្រទូទាត់
        pp_keywords = [
            "ភ្នំពេញ", "phnom penh", "phnompenh", "ស្ទឹងមានជ័យ", "steung meanchey",
            "ទួលគោក", "toul kork", "ដូនពេញ", "daun penh", "ចំការមន", "chamkarmon",
            "៧មករា", "7មករា", "prampi makara", "បឹងកេងកង", "boeung keng kang", "bkk",
            "សែនសុខ", "sen sok", "ឫស្សីកែវ", "russei keo", "ច្បារអំពៅ", "chbar ampov",
            "ជ្រោយចង្វារ", "chroy changvar", "ព្រែកព្នៅ", "prek pnov", "ដង្កោ", "dangkao",
            "ពោធិ៍សែនជ័យ", "ពោធិសែនជ័យ", "pur senchey", "por senchey", "កំបូល", "kamboul",
            "មានជ័យ", "meanchey"
        ]
        addr_lower = raw_address.lower()
        is_pp_addr = any(k in addr_lower for k in pp_keywords)
        is_cod = (order.payment_method or "").lower() == "cod" or is_pp_addr
        payment_badge = "💵 <b>គិតលុយពេលដល់ដៃ (COD)</b>" if is_cod else "🏦 <b>ABA Pay / KHQR (ត្រូវគិតលុយមុន)</b>"

        # Format អាសយដ្ឋានដឹកឱ្យស្អាត (បើមាន '—' បំបែក រៀបចំឱ្យងាយមើល ដាក់អាសយដ្ឋានលម្អិតនៅមុខ)
        if "—" in raw_address:
            parts = [p.strip() for p in raw_address.split("—") if p.strip()]
            if len(parts) >= 2:
                shipping_display = f"{parts[1]}, {parts[0]}"
            else:
                shipping_display = raw_address
        else:
            shipping_display = raw_address or "ភ្នំពេញ"

        cust_name = html.escape(order.customer_name or "Customer")
        shipping_clean = html.escape(shipping_display)

        # បញ្ជីទំនិញ
        item_lines = []
        for it in order_items:
            prod = products_map.get(it.product_id)
            pname = html.escape(prod.name if prod else f"Product #{it.product_id}")
            variant_str = f" ({html.escape(it.variant)})" if it.variant else ""
            line_total = it.price * it.quantity
            item_lines.append(f"• <b>{pname}</b>{variant_str} × {it.quantity} = ${line_total:.2f}")

        items_text = "\n".join(item_lines) if item_lines else "• (មិនមានព័ត៌មានទំនិញ)"

        now_str = (order.created_at or datetime.now(timezone.utc)).astimezone(CAMBODIA_TZ).strftime("%d/%m/%Y %I:%M %p")

        note_section = ""
        if order.note and order.note.strip():
            note_section = f"📝 <b>ចំណាំ / Note:</b> <i>{html.escape(order.note.strip())}</i>\n"

        email_section = ""
        if order.customer_email and order.customer_email.strip():
            email_section = f"✉️ <b>អ៊ីមែល / Email:</b> {html.escape(order.customer_email.strip())}\n"

        phone_clean = (order.customer_phone or "").strip()
        phone_display = f"<code>{html.escape(phone_clean)}</code>" if phone_clean else "N/A"

        location_pin_section = ""
        map_pin_url = (getattr(order, "map_url", None) or "").strip()
        if not map_pin_url and getattr(order, "latitude", None) and getattr(order, "longitude", None):
            map_pin_url = f"https://www.google.com/maps?q={order.latitude},{order.longitude}"

        if map_pin_url:
            location_pin_section = f"🗺️ <b>ទីតាំង Google Maps:</b> <a href=\"{map_pin_url}\">បើកមើលផែនទី (Google Maps Pin)</a>\n"

        msg = (
            f"🛍 <b>ការកុម្ម៉ង់ទិញថ្មី / NEW ORDER #{order.id}</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"👤 <b>អតិថិជន:</b> {cust_name}\n"
            f"📞 <b>លេខទូរស័ព្ទ:</b> {phone_display}\n"
            f"{email_section}"
            f"📍 <b>អាសយដ្ឋានដឹក:</b> {shipping_clean}\n"
            f"{location_pin_section}"
            f"💳 <b>វិធីទូទាត់:</b> {payment_badge}\n"
            f"\n"
            f"📦 <b>ទំនិញដែលបានទិញ:</b>\n"
            f"{items_text}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"💰 <b>សរុបទឹកប្រាក់:</b> <b>${total_usd:.2f}</b> (≈ {total_khr:,} ៛)\n"
            f"{note_section}"
            f"⏰ <b>កាលបរិច្ឆេទ:</b> {now_str}\n"
        )

        admin_url = getattr(settings, "ADMIN_FRONTEND_URL", "https://frontend-admin-e-online.vercel.app")
        keyboard_buttons = []
        if map_pin_url:
            keyboard_buttons.append({"text": "📍 បើកមើលផែនទី Google Maps", "url": map_pin_url})
        keyboard_buttons.append({"text": "🛒 ចូលមើល Order ក្នុង Admin", "url": f"{admin_url}/orders"})
        keyboard = [keyboard_buttons]

        send_telegram_message(text=msg, inline_keyboard=keyboard, db=db)
    except Exception as exc:
        logger.error(f"Error in send_order_created_telegram for order #{order_id}: {exc}")
    finally:
        db.close()


def send_order_paid_telegram(order_id: int):
    """Background task: ផ្ញើដំណឹងពេលអតិថិជនបង់ប្រាក់បានជោគជ័យ (ABA Pay / KHQR)"""
    db = SessionLocal()
    try:
        cfg = get_telegram_settings(db)
        if not cfg["enabled"] or not cfg["bot_token"] or not cfg["chat_id"]:
            return

        order = db.query(models.Order).filter(models.Order.id == order_id).first()
        if not order:
            return

        total_usd = float(order.total_amount or 0.0)
        now_str = datetime.now(CAMBODIA_TZ).strftime("%d/%m/%Y %I:%M %p")
        ref = order.payment_ref or "N/A"

        msg = (
            f"✅ <b>ទូទាត់ប្រាក់ជោគជ័យ! / PAYMENT RECEIVED</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🧾 <b>Order:</b> #{order.id}\n"
            f"👤 <b>អតិថិជន:</b> {order.customer_name or 'Customer'}\n"
            f"📞 <b>លេខទូរស័ព្ទ:</b> <code>{order.customer_phone or 'N/A'}</code>\n"
            f"💵 <b>ចំនួនទឹកប្រាក់:</b> <b>${total_usd:.2f}</b>\n"
            f"🏦 <b>Payment Ref:</b> <code>{ref}</code>\n"
            f"⏰ <b>កាលបរិច្ឆេទ:</b> {now_str}\n"
        )

        admin_url = getattr(settings, "ADMIN_FRONTEND_URL", "https://frontend-admin-e-online.vercel.app")
        keyboard = [
            [{"text": "🛒 មើល Order ក្នុង Admin", "url": f"{admin_url}/orders"}]
        ]

        send_telegram_message(text=msg, inline_keyboard=keyboard, db=db)
    except Exception as exc:
        logger.error(f"Error in send_order_paid_telegram for order #{order_id}: {exc}")
    finally:
        db.close()


def send_order_status_telegram(order_id: int, new_status: str):
    """Background task: ផ្ញើដំណឹងពេល Admin ផ្លាស់ប្តូរស្ថានភាព Order (Shipped, Cancelled, etc.)"""
    db = SessionLocal()
    try:
        cfg = get_telegram_settings(db)
        if not cfg["enabled"] or not cfg["bot_token"] or not cfg["chat_id"]:
            return

        order = db.query(models.Order).filter(models.Order.id == order_id).first()
        if not order:
            return

        status_emojis = {
            "pending": "⏳ រង់ចាំដំណើរការ (Pending)",
            "paid": "✅ បានបង់ប្រាក់រួច (Paid)",
            "shipped": "🚚 កំពុងដឹកជញ្ជូន (Shipped)",
            "cancelled": "❌ បានបោះបង់ (Cancelled)",
        }
        status_label = status_emojis.get(new_status, new_status)
        now_str = datetime.now(CAMBODIA_TZ).strftime("%d/%m/%Y %I:%M %p")

        msg = (
            f"🔄 <b>បច្ចុប្បន្នភាពស្ថានភាព / ORDER STATUS UPDATED</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🧾 <b>Order:</b> #{order.id}\n"
            f"👤 <b>អតិថិជន:</b> {order.customer_name or 'Customer'}\n"
            f"🏷 <b>ស្ថានភាពថ្មី:</b> <b>{status_label}</b>\n"
            f"💰 <b>ទឹកប្រាក់:</b> ${float(order.total_amount or 0):.2f}\n"
            f"⏰ <b>កាលបរិច្ឆេទ:</b> {now_str}\n"
        )

        admin_url = getattr(settings, "ADMIN_FRONTEND_URL", "https://frontend-admin-e-online.vercel.app")
        keyboard = [
            [{"text": "🛒 មើល Order ក្នុង Admin", "url": f"{admin_url}/orders"}]
        ]

        send_telegram_message(text=msg, inline_keyboard=keyboard, db=db)
    except Exception as exc:
        logger.error(f"Error in send_order_status_telegram for order #{order_id}: {exc}")
    finally:
        db.close()
