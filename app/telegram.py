import hashlib
import hmac
import time
from .config import settings

def telegram_configured() -> bool:
    """ពិនិត្យថាបានកំណត់ Telegram Bot (Token + Username) នៅក្នុង .env ឬអត់"""
    return bool(settings.TELEGRAM_BOT_TOKEN and settings.TELEGRAM_BOT_USERNAME)

def verify_telegram_auth(data: dict, max_age_seconds: int = 86400) -> bool:
    """
    ផ្ទៀងផ្ទាត់ hash ពី Telegram Login Widget
    (យោងតាម https://core.telegram.org/widgets/login — "Checking authorization")

    1) តម្រៀប key តាមអក្ខរក្រម ហើយបង្កើត data_check_string = key1=value1\\nkey2=value2...
    2) secret_key = SHA256(bot_token)
    3) computed_hash = HMAC_SHA256(data_check_string, secret_key) → hex
    4) ប្រៀបធៀបជាមួយ hash ដែល Telegram ផ្ញើមក (constant-time)
    """
    if not telegram_configured():
        return False

    received_hash = data.get("hash")
    if not received_hash:
        return False

    # auth_date មិនត្រូវចាស់ពេក (ការពារ replay attack)
    try:
        auth_date = int(data.get("auth_date", 0))
    except (TypeError, ValueError):
        return False
    if time.time() - auth_date > max_age_seconds:
        return False

    # ត្រងយកតែ field ដែល Telegram ផ្ញើមកពិតប្រាកដប៉ុណ្ណោះ
    # សំខាន់៖ Pydantic បំពេញ field ដែល Client មិនបានផ្ញើមកដោយ default (None/"").
    # បើយក field ទាំងនោះមកគណនា hash វិញ -> hash នឹងមិនត្រូវគ្នា
    # ព្រោះ Telegram មិនដែលដាក់ field ទទេទាំងនោះក្នុងការគណនា (ឧ. អ្នកប្រើគ្មានរូប / គ្មាន username)
    fields = {
        k: v
        for k, v in data.items()
        if k != "hash" and v is not None and v != ""
    }
    data_check_string = "\n".join(f"{k}={fields[k]}" for k in sorted(fields))

    secret_key = hashlib.sha256(settings.TELEGRAM_BOT_TOKEN.encode()).digest()
    computed = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    return hmac.compare_digest(computed, received_hash)
