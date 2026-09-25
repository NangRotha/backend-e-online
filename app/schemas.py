from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import datetime

class UserCreate(BaseModel):
    name: str
    email: EmailStr
    password: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserOut(BaseModel):
    id: int
    name: str
    email: str  # str (មិនមែន EmailStr) ព្រោះអាចមានអ៊ីមែល Placeholder (ឧ. Telegram)
    role: str
    email_verified: bool = False
    profile_image: str = ""
    class Config:
        from_attributes = True

class ProfileUpdate(BaseModel):
    name: str
    profile_image: str = ""

class PasswordChange(BaseModel):
    current_password: str
    new_password: str

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

class RegisterResponse(BaseModel):
    message: str
    email: EmailStr
    dev_otp: Optional[str] = None  # បង្ហាញតែពេល SMTP មិនទាន់កំណត់ (Dev Mode)
    otp_reason: Optional[str] = None  # None | "not_configured" | "send_failed"

class VerifyOtpRequest(BaseModel):
    email: EmailStr
    code: str

class ResendOtpRequest(BaseModel):
    email: EmailStr

class TestEmailRequest(BaseModel):
    email: EmailStr

class TelegramAuthData(BaseModel):
    """ទិន្នន័យដែល Telegram Login Widget ផ្ញើមក"""
    id: int
    first_name: str = ""
    last_name: Optional[str] = None
    username: Optional[str] = None
    photo_url: Optional[str] = None
    auth_date: int
    hash: str

class TelegramTestRequest(BaseModel):
    bot_token: Optional[str] = None
    chat_id: Optional[str] = None

class AdminUserCreate(BaseModel):
    name: str
    email: EmailStr
    password: str
    role: str = "user"  # 'admin' or 'user'
    email_verified: bool = False

class AdminUserUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    password: Optional[str] = None
    role: Optional[str] = None  # 'admin' or 'user'
    email_verified: Optional[bool] = None

class CategoryCreate(BaseModel):
    name: str
    name_kh: Optional[str] = ""
    description: str = ""
    description_kh: Optional[str] = ""

class CategoryUpdate(BaseModel):
    name: str
    name_kh: Optional[str] = ""
    description: str = ""
    description_kh: Optional[str] = ""

class CategoryOut(BaseModel):
    id: int
    name: str
    name_kh: Optional[str] = ""
    description: str = ""
    description_kh: Optional[str] = ""
    product_count: int = 0  # ចំនួនផលិតផលដែលប្រើ Category នេះ
    created_at: Optional[datetime] = None
    class Config:
        from_attributes = True

class SlideCreate(BaseModel):
    title: str = ""
    subtitle: str = ""
    media_type: str = "image"  # 'image' | 'video' | 'youtube'
    media_url: str = ""        # រូប/វីដេអូដែល Upload
    youtube_url: str = ""      # តំណ YouTube ពេញ
    link_url: str = ""         # តំណពេលចុច (optional)
    sort_order: int = 0
    is_active: bool = True

class SlideUpdate(SlideCreate):
    pass

class SlideOut(SlideCreate):
    id: int
    created_at: Optional[datetime] = None
    class Config:
        from_attributes = True

class ProductCreate(BaseModel):
    name: str
    name_kh: Optional[str] = ""
    description: str = ""
    description_kh: Optional[str] = ""
    price: float
    stock: int
    image_url: str = ""  # រូបមេ
    images: Optional[List[str]] = None  # បញ្ជីរូបទាំងអស់ (រូបទី១ = Main)
    video_url: str = ""  # វីដេអូផលិតផល (mp4 / webm / mov — Admin Upload)
    variants: Optional[List[str]] = None  # បញ្ជីប្រភេទ/ជម្រើសផលិតផល (ឧ. ["Pink", "Black", "White"])
    category: str = ""
    is_on_sale: bool = False
    sale_percent: float = 0
    original_price: Optional[float] = None
    rating: Optional[float] = 5.0

class ProductUpdate(BaseModel):
    """អនុញ្ញាតកែតម្រូវដោយផ្នែក (partial) — ឧ. កែតម្លៃតែប៉ុណ្ណោះ។
    មានតែ Field ដែលផ្ញើមកប៉ុណ្ណោះនឹងត្រូវបានធ្វើបច្ចុប្បន្នភាព។"""
    name: Optional[str] = None
    name_kh: Optional[str] = None
    description: Optional[str] = None
    description_kh: Optional[str] = None
    price: Optional[float] = None
    stock: Optional[int] = None
    image_url: Optional[str] = None
    images: Optional[List[str]] = None
    video_url: Optional[str] = None
    variants: Optional[List[str]] = None
    category: Optional[str] = None
    is_on_sale: Optional[bool] = None
    sale_percent: Optional[float] = None
    original_price: Optional[float] = None
    rating: Optional[float] = None

class ProductOut(ProductCreate):
    id: int
    class Config:
        from_attributes = True

class BulkPriceAdjustRequest(BaseModel):
    mode: str = "add_fixed"  # "add_fixed" (+ $), "add_percent" (+ %), "sub_fixed" (- $), "sub_percent" (- %)
    operation: Optional[str] = None
    value: float
    category: Optional[str] = None  # None or "All" for all products
    set_original_price: bool = True  # Preserve existing price in original_price

class CheckoutItem(BaseModel):
    product_id: int
    quantity: int
    variant: Optional[str] = None

class CheckoutRequest(BaseModel):
    items: Optional[List[CheckoutItem]] = None
    product_id: Optional[int] = None
    quantity: Optional[int] = None
    promo_code: Optional[str] = None
    shipping_address: str = ""
    customer_name: Optional[str] = None   # ឈ្មោះអ្នកទទួល (auto ពី Profile ឬបំពេញដោយខ្លួនឯង)
    customer_phone: Optional[str] = None  # លេខទូរសព្ទ
    customer_email: Optional[str] = None  # អ៊ីមែល (Guest Checkout — សម្រាប់ផ្ញើ Receipt)
    payment_method: Optional[str] = None  # 'cod' | 'aba_pay'
    note: Optional[str] = None            # កំណត់ចំណាំ (optional)

class CheckoutResponse(BaseModel):
    order_id: int
    total_amount: float
    status: str
    payment_method: Optional[str] = "aba_pay"  # 'cod' | 'aba_pay'
    payment_url: str = ""  # Redirect checkout (ABA Pay requestv2 — auto-redirect ទៅ Checkout)
    payment_checkout_url: str = ""  # Frontend Checkout ផ្ទាល់ (checkout.khqr.cc)
    payment_enabled: bool = False  # បានភ្ជាប់ ABA Pay / KHQRcc ឬអត់
    payment_transaction_id: Optional[str] = None  # Transaction ID សម្រាប់ពិនិត្យស្ថានភាព
    payment_qr_url: Optional[str] = None  # រូប QR Code (PNG)
    payment_qr: Optional[str] = None  # ខ្សែអក្សរ EMV (បើចង់ Render QR ដោយខ្លួនឯង)
    # ព័ត៌មាន Bakong Wallet (ពី Site Settings — Admin កំណត់ក្នុង Settings)
    payment_company_name: Optional[str] = None   # Company Name (ចំណងជើងលើ Checkout)
    payment_display_name: Optional[str] = None   # ឈ្មោះអ្នកទទួលប្រាក់ (បង្ហាញលើ Bakong)
    payment_bakong_id: Optional[str] = None      # Bakong Wallet ID (គណនីផ្ទេរប្រាក់)
    currency: str = "USD"                        # USD | KHR
    khr_rate: float = 4100                       # អត្រាប្តូរប្រាក់ (៛ ក្នុង ១ ដុល្លារ)

class PaymentCreateRequest(BaseModel):
    transaction_id: str
    amount: float
    success_url: str
    remark: str = ""
    cancel_url: str = ""      # ទៅណាពេលអតិថិជនបោះបង់ការបង់ប្រាក់ (optional)
    items: str = ""           # Base64(JSON) នៃ Cart Items (optional)
    custom_fields: str = ""   # Base64(JSON) ទិន្នន័យបន្ថែម ដែល Gateway ផ្ញើមកវិញ (optional)

class PaymentCreateResponse(BaseModel):
    transaction_id: str
    amount: str
    qr: str = ""
    qr_url: str = ""

class PaymentStatusRequest(BaseModel):
    transaction_id: str

class PaymentStatusResponse(BaseModel):
    transaction_id: str
    status: str  # 'pending' | 'success' | 'failed'
    amount: Optional[str] = None

class DiscountCreate(BaseModel):
    code: str
    percent: float
    max_uses: int = 100
    expiry_date: Optional[str]

class SiteSettingUpdate(BaseModel):
    key: str
    value: str

class AlertCreate(BaseModel):
    title: str = ""
    message: str = ""
    alert_type: str = "info"  # 'info' | 'success' | 'warning' | 'danger'
    style: str = "both"       # 'banner' | 'popup' | 'both'
    image_url: str = ""       # រូបភាព (Upload ពីកុំព្យូទ័រ ឬ URL)
    link_url: str = ""
    is_active: bool = True
    starts_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None

class AlertUpdate(AlertCreate):
    pass

class AlertOut(AlertCreate):
    id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    class Config:
        from_attributes = True

class ChatMessage(BaseModel):
    role: str  # 'user' | 'assistant'
    content: str

class ChatRequest(BaseModel):
    message: str
    history: Optional[List[ChatMessage]] = None

class RoleUpdate(BaseModel):
    role: str  # 'admin' or 'user'

class OrderStatusUpdate(BaseModel):
    status: str  # 'pending', 'paid', 'shipped', 'cancelled'