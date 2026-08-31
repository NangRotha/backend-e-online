import html
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from .config import settings

logger = logging.getLogger("uvicorn.error")

# ផ្ទុកកំហុស SMTP ចុងក្រោយ (សម្រាប់ពិនិត្យលើ Production តាម /api/auth/email-config)
_last_smtp_error = None

def smtp_configured() -> bool:
    """ពិនិត្យថាបានកំណត់ SMTP credentials នៅក្នុង .env ឬអត់"""
    return bool(settings.SMTP_USER and settings.SMTP_PASSWORD)


def email_status() -> dict:
    """ស្ថានភាព Email — សម្រាប់ពិនិត្យលើ Production (curl /api/auth/email-config)"""
    return {
        "configured": smtp_configured(),
        "provider": settings.SMTP_HOST or "",
        "port": settings.SMTP_PORT,
        "use_ssl": settings.SMTP_USE_SSL,
        "sender": settings.SMTP_FROM or settings.SMTP_USER or "",
        "from_name": settings.SMTP_FROM_NAME or "",
        "last_error": _last_smtp_error,  # កំហុស SMTP ចុងក្រោយ (None = អត់មាន)
    }

def _build_otp_html(otp: str, expires_minutes: int) -> str:
    return f"""
    <div style="font-family:Arial,sans-serif;max-width:480px;margin:0 auto;padding:24px;border:1px solid #e2e8f0;border-radius:16px;">
      <h2 style="color:#0f172a;margin:0 0 8px;">Verify your email</h2>
      <p style="color:#64748b;margin:0 0 24px;">Use the code below to complete your registration. It expires in {expires_minutes} minutes.</p>
      <div style="text-align:center;font-size:40px;font-weight:800;letter-spacing:8px;color:#059669;padding:16px;background:#f0fdf4;border-radius:12px;">
        {otp}
      </div>
      <p style="color:#94a3b8;font-size:13px;margin-top:24px;">If you didn't request this, you can safely ignore this email.</p>
    </div>
    """

def _connect():
    """
    ភ្ជាប់ទៅ SMTP server — គាំទ្រទាំង SSL (port 465, ឧ. Yahoo/Zoho)
    និង STARTTLS (port 587, ឧ. Gmail/Outlook/Brevo/SendGrid)។
    """
    if settings.SMTP_USE_SSL or settings.SMTP_PORT == 465:
        server = smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT)
    else:
        server = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT)
        server.ehlo()
        server.starttls()
        server.ehlo()
    server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
    return server

def send_otp_email(to_email: str, otp: str) -> dict:
    """
    ផ្ញើ OTP ទៅកាន់អ្នកប្រើប្រាស់ **លើសកលលោក** — អាចជាអ៊ីមែលពី Gmail, Yahoo,
    Outlook, Hotmail, ឬ domain ផ្ទាល់ខ្លួនណាមួយ។ SMTP របស់យើងគ្រាន់តែជាអ្នកផ្ញើ
    (sender) ហើយ Gmail/provider ផ្សេងៗ នឹងបញ្ជូនទៅកាន់ inbox ណាក៏បានក្នុងលោក។

    បើ SMTP មិនទាន់កំណត់ -> បង្ហាញ OTP នៅ Console (Dev Mode) ហើយអាចយកទៅប្រើភ្លាមៗ។
    Returns: {"sent", "dev_otp", "reason"} — reason: None | "not_configured" | "send_failed"
    """
    if not smtp_configured():
        logger.warning(f"[DEV MODE] OTP for {to_email} = {otp}  (SMTP not configured in .env)")
        return {"sent": False, "dev_otp": otp, "reason": "not_configured"}

    from_addr = settings.SMTP_FROM or settings.SMTP_USER
    if settings.SMTP_FROM_NAME:
        from_header = f"{settings.SMTP_FROM_NAME} <{from_addr}>"
    else:
        from_header = from_addr

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Your verification code"
    msg["From"] = from_header
    msg["To"] = to_email
    msg.attach(MIMEText(_build_otp_html(otp, settings.OTP_EXPIRE_MINUTES), "html"))

    try:
        with _connect() as server:
            server.sendmail(from_addr, [to_email], msg.as_string())
        logger.info(f"OTP email sent to {to_email}")
        return {"sent": True, "dev_otp": None, "reason": None}
    except Exception as e:
        global _last_smtp_error
        _last_smtp_error = f"{type(e).__name__}: {e}"
        logger.error(f"Failed to send OTP email to {to_email}: {_last_smtp_error}")
        # Fallback: បង្ហាញ OTP នៅ Console ដើម្បីកុំឱ្យស្ទះការសាកល្បង
        logger.warning(f"[FALLBACK] OTP for {to_email} = {otp}")
        return {"sent": False, "dev_otp": otp, "reason": "send_failed"}


# ============================================================
# Payment receipt email — ផ្ញើទៅអ្នកប្រើពេលបង់ប្រាក់ជោគជ័យ
# ============================================================
def _fmt_money(n: float) -> str:
    return f"${n:,.2f}"



def _build_receipt_html(data: dict) -> str:
    """HTML Email ស្អាត និងអាចបង្ហាញលើ Gmail (inline CSS + table layout)"""
    site_name = html.escape(data.get("site_name") or "Our Store")
    site_logo = (data.get("site_logo") or "").strip()
    customer_name = html.escape(data.get("customer_name") or "Customer")
    order_id = data.get("order_id")
    created_at = data.get("created_at") or ""
    if hasattr(created_at, "strftime"):
        created_at = created_at.strftime("%B %d, %Y · %I:%M %p")
    created_at = html.escape(str(created_at))

    items = data.get("items") or []
    subtotal = data.get("subtotal") or 0
    discount = data.get("discount") or 0
    total = data.get("total") or 0
    phone = html.escape(data.get("phone") or "")
    address = html.escape(data.get("address") or "")
    note = html.escape(data.get("note") or "")
    frontend_url = (data.get("frontend_url") or "").strip() or "#"

    # Header (logo ឬ ឈ្មោះ)
    if site_logo:
        header_html = (
            f'<img src="{html.escape(site_logo)}" alt="{site_name}" '
            'style="height:44px;max-width:180px;object-fit:contain;" />'
        )
    else:
        header_html = (
            f'<span style="font-size:22px;font-weight:800;color:#059669;">'
            f"🛍️ {site_name}</span>"
        )

    # បន្ទាត់ Items
    rows = ""
    for it in items:
        name = html.escape(it.get("name") or "Item")
        qty = it.get("quantity") or 0
        unit = it.get("unit_price") or 0
        rows += f"""
          <tr>
            <td style="padding:10px 12px;border-bottom:1px solid #f1f5f9;color:#334155;font-size:14px;">{name}</td>
            <td style="padding:10px 12px;border-bottom:1px solid #f1f5f9;color:#64748b;font-size:14px;text-align:center;">× {qty}</td>
            <td style="padding:10px 12px;border-bottom:1px solid #f1f5f9;color:#0f172a;font-size:14px;text-align:right;font-weight:600;">{_fmt_money(unit * qty)}</td>
          </tr>"""

    discount_row = ""
    if discount > 0:
        discount_row = f"""
          <tr>
            <td colspan="2" style="padding:8px 12px;color:#64748b;font-size:14px;">Discount</td>
            <td style="padding:8px 12px;color:#059669;font-size:14px;text-align:right;font-weight:600;">−{_fmt_money(discount)}</td>
          </tr>"""

    delivery_rows = ""
    if phone:
        delivery_rows += f'<tr><td style="padding:4px 0;color:#64748b;font-size:13px;width:80px;">Phone</td><td style="padding:4px 0;color:#0f172a;font-size:13px;font-weight:600;">{phone}</td></tr>'
    if address:
        delivery_rows += f'<tr><td style="padding:4px 0;color:#64748b;font-size:13px;width:80px;">Address</td><td style="padding:4px 0;color:#0f172a;font-size:13px;font-weight:600;">{address}</td></tr>'
    if note:
        delivery_rows += f'<tr><td style="padding:4px 0;color:#64748b;font-size:13px;width:80px;">Note</td><td style="padding:4px 0;color:#0f172a;font-size:13px;">📝 {note}</td></tr>'

    delivery_html = ""
    if phone or address or note:
        delivery_html = f"""
          <tr>
            <td style="padding:16px 32px 0;">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#ecfdf5;border:1px solid #d1fae5;border-radius:14px;">
                <tr>
                  <td style="padding:16px 20px;">
                    <div style="color:#059669;font-size:12px;letter-spacing:.5px;text-transform:uppercase;font-weight:700;margin-bottom:6px;">🚚 Delivery details</div>
                    <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
                      {delivery_rows}
                    </table>
                  </td>
                </tr>
              </table>
            </td>
          </tr>"""


    return f"""<!DOCTYPE html>
<html lang="en">
<body style="margin:0;padding:0;background:#f1f5f9;font-family:Arial,Helvetica,sans-serif;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f1f5f9;padding:24px 12px;">
    <tr>
      <td align="center">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;background:#ffffff;border-radius:20px;overflow:hidden;box-shadow:0 4px 24px rgba(15,23,42,.06);">

          <!-- Header -->
          <tr>
            <td align="center" style="padding:32px 32px 8px;">
              {header_html}
            </td>
          </tr>

          <!-- Badge -->
          <tr>
            <td align="center" style="padding:16px 32px 0;">
              <span style="display:inline-block;background:#ecfdf5;color:#059669;font-size:13px;font-weight:700;padding:8px 18px;border-radius:999px;">✓ Payment Confirmed</span>
            </td>
          </tr>

          <!-- Heading -->
          <tr>
            <td align="center" style="padding:20px 32px 0;">
              <h1 style="margin:0;color:#0f172a;font-size:22px;line-height:1.3;">Thank you, {customer_name}!</h1>
              <p style="margin:8px 0 0;color:#64748b;font-size:14px;">Your payment was successful. We've received your order and will start processing it right away.</p>
            </td>
          </tr>

          <!-- Order summary card -->
          <tr>
            <td style="padding:24px 32px 0;">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:14px;">
                <tr>
                  <td style="padding:16px 20px;">
                    <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
                      <tr>
                        <td style="color:#94a3b8;font-size:12px;letter-spacing:.5px;text-transform:uppercase;">Order Number</td>
                        <td style="color:#94a3b8;font-size:12px;letter-spacing:.5px;text-transform:uppercase;text-align:right;">Date</td>
                      </tr>
                      <tr>
                        <td style="color:#0f172a;font-size:16px;font-weight:800;padding-top:4px;">#{order_id}</td>
                        <td style="color:#334155;font-size:13px;padding-top:4px;text-align:right;">{created_at}</td>
                      </tr>
                    </table>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Items table -->
          <tr>
            <td style="padding:20px 32px 0;">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
                <tr>
                  <td style="padding:8px 12px;color:#94a3b8;font-size:12px;letter-spacing:.5px;text-transform:uppercase;">Item</td>
                  <td style="padding:8px 12px;color:#94a3b8;font-size:12px;letter-spacing:.5px;text-transform:uppercase;text-align:center;">Qty</td>
                  <td style="padding:8px 12px;color:#94a3b8;font-size:12px;letter-spacing:.5px;text-transform:uppercase;text-align:right;">Amount</td>
                </tr>
                {rows}
              </table>
            </td>
          </tr>

          <!-- Totals -->
          <tr>
            <td style="padding:12px 32px 0;">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
                <tr>
                  <td style="padding:8px 12px;color:#64748b;font-size:14px;">Subtotal</td>
                  <td style="padding:8px 12px;color:#0f172a;font-size:14px;text-align:right;font-weight:600;">{_fmt_money(subtotal)}</td>
                </tr>
                {discount_row}
                <tr>
                  <td style="padding:12px;border-top:2px solid #059669;color:#0f172a;font-size:15px;font-weight:800;">Total</td>
                  <td style="padding:12px;border-top:2px solid #059669;color:#059669;font-size:18px;text-align:right;font-weight:800;">{_fmt_money(total)}</td>
                </tr>
              </table>
            </td>
          </tr>

          {delivery_html}

          <!-- Button -->
          <tr>
            <td align="center" style="padding:28px 32px 8px;">
              <a href="{html.escape(frontend_url)}"
                 style="display:inline-block;background:#059669;color:#ffffff;font-size:15px;font-weight:700;text-decoration:none;padding:14px 36px;border-radius:12px;">
                Visit {site_name}
              </a>
            </td>
          </tr>
          <tr>
            <td align="center" style="padding:8px 32px 28px;">
              <p style="margin:0;color:#94a3b8;font-size:12px;">Questions about your order? Just reply to this email.</p>
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td align="center" style="background:#f8fafc;padding:20px 32px;border-top:1px solid #f1f5f9;">
              <p style="margin:0;color:#64748b;font-size:12px;">© {site_name} · Thank you for shopping with us!</p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def _build_receipt_text(data: dict) -> str:
    """Plain-text fallback (សម្រាប់ email client ចាស់ៗ)"""
    lines = [
        "Payment Confirmed ✓",
        f"Thank you, {data.get('customer_name') or 'Customer'}!",
        "",
        f"Order #{data.get('order_id')} — {data.get('created_at') or ''}",
        "------------------------------------",
    ]
    for it in data.get("items") or []:
        lines.append(
            f"{it.get('name')}  x{it.get('quantity')}   "
            f"{_fmt_money((it.get('unit_price') or 0) * (it.get('quantity') or 0))}"
        )
    lines.append("------------------------------------")
    lines.append(f"Subtotal: {_fmt_money(data.get('subtotal') or 0)}")
    if (data.get("discount") or 0) > 0:
        lines.append(f"Discount: -{_fmt_money(data.get('discount'))}")
    lines.append(f"TOTAL: {_fmt_money(data.get('total') or 0)}")
    if data.get("phone"):
        lines.append("")
        lines.append(f"Phone: {data.get('phone')}")
    if data.get("address"):
        lines.append(f"Address: {data.get('address')}")
    if data.get("note"):
        lines.append(f"Note: {data.get('note')}")
    lines.append("")
    lines.append(
        f"Thank you for shopping with {data.get('site_name') or 'our store'}!"
    )
    return "\n".join(lines)


def send_order_receipt_email(to_email: str, data: dict) -> dict:
    """
    ផ្ញើ Receipt (ការបញ្ជាក់ការបង់ប្រាក់ជោគជ័យ) ទៅកាន់អ្នកប្រើ។
    data ត្រូវតែមាន: order_id, total, items[]...
    បើ SMTP មិនបានកំណត់ -> បោះពុម្ពនៅ Console (Dev Mode) ដោយមិន crash។
    """
    if not smtp_configured():
        logger.info(
            f"[DEV MODE] Receipt email for order #{data.get('order_id')} "
            f"would be sent to {to_email}"
        )
        return {"sent": False}

    from_addr = settings.SMTP_FROM or settings.SMTP_USER
    from_name = data.get("site_name") or settings.SMTP_FROM_NAME or "Store"
    from_header = f"{from_name} <{from_addr}>"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Payment Confirmed · Order #{data.get('order_id')} — Thank you! 🎉"
    msg["From"] = from_header
    msg["To"] = to_email
    msg.attach(MIMEText(_build_receipt_text(data), "plain"))
    msg.attach(MIMEText(_build_receipt_html(data), "html"))

    try:
        with _connect() as server:
            server.sendmail(from_addr, [to_email], msg.as_string())
        logger.info(
            f"Receipt email sent to {to_email} (order #{data.get('order_id')})"
        )
        return {"sent": True}
    except Exception as e:
        global _last_smtp_error
        _last_smtp_error = f"{type(e).__name__}: {e}"
        logger.error(f"Failed to send receipt email to {to_email}: {_last_smtp_error}")
        return {"sent": False}

