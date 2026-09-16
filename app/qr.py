"""បង្កើតរូប QR Code (PNG) សម្រាប់ KHQR / ABA Pay

ហេតុអ្វីត្រូវការ?
- KHQRcc Gateway ត្រឡប់ `qr` (EMV string) មក តែពេលខ្លះ **មិន** ត្រឡប់រូបភាព `qr_url`
- ដូច្នេះយើងបង្កើតរូប QR ខ្លួនឯងពី EMV string -> អតិថិជនឃើញ QR ជានិច្ច
"""
from __future__ import annotations

from io import BytesIO

import qrcode
from qrcode.constants import ERROR_CORRECT_M


def generate_qr_png(text: str, box_size: int = 8, border: int = 2) -> bytes:
    """បង្កើតរូប QR (PNG bytes) ពីអត្ថបទ៖ EMV KHQR string ឬ URL ណាមួយ

    box_size=8 -> រូបប្រហែល 300-400px (ច្បាស់ល្មមសម្រាប់ស្កេនលើទូរសព្ទ)
    """
    payload = (text or "").strip()
    if not payload:
        raise ValueError("QR payload is empty")

    qr = qrcode.QRCode(
        version=None,  # ជ្រើសទំហំស្វ័យប្រវត្តិតាមបរិមាណទិន្នន័យ
        error_correction=ERROR_CORRECT_M,  # កម្រិតខូច ~15% (ស្តង់ដារសម្រាប់ KHQR)
        box_size=box_size,
        border=border,
    )
    qr.add_data(payload)
    qr.make(fit=True)

    image = qr.make_image(fill_color="black", back_color="white")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()
