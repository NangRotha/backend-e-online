import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from .config import settings

logger = logging.getLogger("uvicorn.error")

def smtp_configured() -> bool:
    """ពិនិត្យថាបានកំណត់ SMTP credentials នៅក្នុង .env ឬអត់"""
    return bool(settings.SMTP_USER and settings.SMTP_PASSWORD)

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
    """
    if not smtp_configured():
        logger.warning(f"[DEV MODE] OTP for {to_email} = {otp}  (SMTP not configured in .env)")
        return {"sent": False, "dev_otp": otp}

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
        return {"sent": True, "dev_otp": None}
    except Exception as e:
        logger.error(f"Failed to send OTP email to {to_email}: {e}")
        # Fallback: បង្ហាញ OTP នៅ Console ដើម្បីកុំឱ្យស្ទះការសាកល្បង
        logger.warning(f"[FALLBACK] OTP for {to_email} = {otp}")
        return {"sent": False, "dev_otp": otp}

