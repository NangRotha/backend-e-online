from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, ForeignKey, JSON
from sqlalchemy.sql import func
from .database import Base

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(String, default="user")  # 'admin' or 'user'
    email_verified = Column(Boolean, default=False)  # បានផ្ទៀងផ្ទាត់ OTP ឬអត់
    telegram_id = Column(Integer, unique=True, index=True, nullable=True)  # Telegram user id (Login ជាមួយ Telegram)
    profile_image = Column(String, default="")  # URL រូប Profile របស់អ្នកប្រើ
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    name_kh = Column(String, default="")  # ឈ្មោះជាភាសាខ្មែរ
    description = Column(String)
    description_kh = Column(String, default="")  # ពណ៌នាសង្ខេបជាភាសាខ្មែរ
    price = Column(Float)
    stock = Column(Integer, default=0)
    image_url = Column(String, default="")  # រូបមេ (Main Image)
    images = Column(JSON, default=list)  # បញ្ជីរូបទាំងអស់ (រូបទី១ = Main)
    video_url = Column(String, default="")  # វីដេអូផលិតផល (Admin Upload ពីកុំព្យូទ័រ)
    variants = Column(JSON, default=list)  # បញ្ជីប្រភេទ/ជម្រើសផលិតផល (ឧ. ["Pink", "Black", "White"])
    sizes = Column(JSON, default=list)  # បញ្ជីទំហំផលិតផល (ឧ. ["S", "M", "L", "XL"] ឬ ["36", "37", "38"])
    category = Column(String)
    is_on_sale = Column(Boolean, default=False)
    sale_percent = Column(Float, default=0)  # ឧទាហរណ៍ 10 = 10% discount
    original_price = Column(Float, nullable=True, default=None)  # តម្លៃដើម/ចាស់ (Strikethrough price ឧ. $25)
    rating = Column(Float, default=5.0)  # ពិន្ទុផ្កាយផលិតផល (1.0 ដល់ 5.0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Category(Base):
    __tablename__ = "categories"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)  # ឈ្មោះ Category (ឧ. Electronics)
    name_kh = Column(String, default="")  # ឈ្មោះ Category ជាភាសាខ្មែរ (ឧ. គ្រឿងអេឡិចត្រូនិច)
    description = Column(String, default="")  # ពណ៌នាសង្ខេប
    description_kh = Column(String, default="")  # ពណ៌នាសង្ខេបជាភាសាខ្មែរ
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Slide(Base):
    __tablename__ = "slides"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, default="")  # ចំណងជើងរបស់ Slide
    subtitle = Column(String, default="")  # អត្ថបទរង
    media_type = Column(String, default="image")  # 'image' | 'video' | 'youtube'
    media_url = Column(String, default="")  # URL រូបភាព / វីដេអូដែល Upload
    youtube_url = Column(String, default="")  # តំណ YouTube ពេញ (បើ media_type = 'youtube')
    link_url = Column(String, default="")  # តំណពេលចុចលើ Slide (មិនបាច់ក៏បាន)
    sort_order = Column(Integer, default=0)  # លំដាប់បង្ហាញ (តូច = មុនគេ)
    is_active = Column(Boolean, default=True)  # បង្ហាញលើ Storefront ឬអត់
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    total_amount = Column(Float)
    status = Column(String, default="pending")  # 'pending', 'paid', 'shipped'
    promo_code = Column(String, nullable=True)
    payment_ref = Column(String, nullable=True)
    payment_qr_url = Column(String, default="")   # រូប QR (KHQR) — រក្សាទុកដើម្បីបង្ហាញឡើងវិញ
    payment_qr = Column(String, default="")       # EMV QR String (សម្រាប់ Deeplink / ABA Mobile App)
    payment_url = Column(String, default="")      # Redirect Checkout URL (ABA Pay requestv2)
    payment_checkout_url = Column(String, default="")  # Frontend Checkout URL
    # ព័ត៌មានអ្នកទទួល / ដឹកជញ្ជូន (បញ្ចូលពីទំព័រ Checkout)
    customer_name = Column(String, nullable=True)   # ឈ្មោះអ្នកទទួល (auto ពី Profile ឬបំពេញដោយខ្លួនឯង)
    customer_phone = Column(String, nullable=True)  # លេខទូរសព្ទ
    customer_email = Column(String, default="")     # អ៊ីមែលអតិថិជន (Guest Checkout — សម្រាប់ផ្ញើ Receipt)
    shipping_address = Column(String, default="")   # អាសយដ្ឋានដឹកជញ្ជូន
    payment_method = Column(String, default="aba_pay")  # 'cod' (Cash on Delivery) | 'aba_pay' (ABA KHQR)
    note = Column(String, default="")               # កំណត់ចំណាំ (optional)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class OrderItem(Base):
    __tablename__ = "order_items"
    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"))
    product_id = Column(Integer, ForeignKey("products.id"))
    quantity = Column(Integer)
    price = Column(Float)
    variant = Column(String, nullable=True)

class Discount(Base):
    __tablename__ = "discounts"
    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, index=True)
    percent = Column(Float)  # 10 = 10% off
    max_uses = Column(Integer, default=100)
    used_count = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    expiry_date = Column(DateTime, nullable=True)

class SiteSetting(Base):
    __tablename__ = "site_settings"
    id = Column(Integer, primary_key=True)
    key = Column(String, unique=True)  # 'site_name', 'site_logo'
    value = Column(String)

class Alert(Base):
    """ការជូនដំណឹង / Popup ដែល Admin បង្កើតពី Admin Panel ហើយបង្ហាញលើ Storefront"""
    __tablename__ = "alerts"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, default="")          # ចំណងជើងរបស់ Alert
    message = Column(String, default="")        # អត្ថបទលម្អិត
    alert_type = Column(String, default="info") # 'info' | 'success' | 'warning' | 'danger'
    style = Column(String, default="both")      # 'banner' | 'popup' | 'both'
    image_url = Column(String, default="")      # រូបភាព (Upload ពីកុំព្យូទ័រ ឬ URL)
    link_url = Column(String, default="")       # តំណពេលចុចលើ Alert (optional)
    is_active = Column(Boolean, default=True)   # បង្ហាញលើ Storefront ឬអត់
    starts_at = Column(DateTime(timezone=True), nullable=True)  # ចាប់ផ្តើមបង្ហាញ (optional)
    expires_at = Column(DateTime(timezone=True), nullable=True) # បញ្ចប់ការបង្ហាញ (optional)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class OtpCode(Base):
    __tablename__ = "otp_codes"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, index=True, nullable=False)
    code = Column(String, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())