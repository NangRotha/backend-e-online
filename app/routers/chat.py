import json
import httpx
from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any
from sqlalchemy import func, or_
from .. import models, schemas
from ..config import settings
from ..database import SessionLocal

router = APIRouter(prefix="/api/chat", tags=["AI Chat"])

DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
DEEPSEEK_MODEL = "deepseek-chat"
MAX_HISTORY = 10
MAX_TOOL_ROUNDS = 3

def chat_enabled() -> bool:
    """ពិនិត្យថាបានកំណត់ DeepSeek API Key ឬអត់"""
    key = (settings.DEEPSEEK_API_KEY or "").strip()
    if not key or key in ("your-deepseek-key", "PUT_REAL_KEY_OR_SKIP_THIS_LINE"):
        return False
    return True

# ============================================================
# Tools (Function Calling) — ឲ្យ AI អាចស្វែងរកទិន្នន័យពិតក្នុង Database
# ============================================================
TOOLS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_site_info",
            "description": "Get general info about the store: site name, logo, product count and category count.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_categories",
            "description": "List all product categories with the number of products in each.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_products",
            "description": "List the latest products in the store with their price, category and stock. Use when the user asks to see what products are available or for recommendations.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Max number of products to return (1 to 20)",
                        "default": 10,
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_products",
            "description": "Search products by name, description or category. Use when the user asks about a specific product, keyword or category.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search keyword, e.g. 'headphones' or 'electronics'"}
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_product_details",
            "description": "Get full details of a specific product by name: price, stock, sale discount, description and images.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Exact or partial product name"}
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_stock",
            "description": "Check whether a product is in stock and its available quantity.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Product name"}
                },
                "required": ["name"],
            },
        },
    },
]


def _product_dict(p: models.Product) -> dict:
    """បង្កើតព័ត៌មានផលិតផលសម្រាប់ផ្ញើឲ្យ AI"""
    price = p.price
    if p.is_on_sale and p.sale_percent:
        price = p.price * (1 - p.sale_percent / 100)
    return {
        "id": p.id,
        "name": p.name,
        "description": (p.description or "")[:200],
        "price": round(price, 2),
        "original_price": p.price,
        "on_sale": bool(p.is_on_sale and p.sale_percent),
        "sale_percent": p.sale_percent,
        "category": p.category or "",
        "stock": p.stock,
        "in_stock": p.stock > 0,
        "image_url": p.image_url or "",
    }

def execute_tool(name: str, args: dict) -> Any:
    """ប្រតិបត្តិ tool ដោយស្វែងរកទិន្នន័យពិតក្នុង Database"""
    db = SessionLocal()
    try:
        if name == "get_site_info":
            site = {s.key: s.value for s in db.query(models.SiteSetting).all()}
            return {
                "site_name": site.get("site_name", ""),
                "site_logo": site.get("site_logo", ""),
                "product_count": db.query(models.Product).count(),
                "category_count": db.query(models.Category).count(),
            }

        if name == "get_categories":
            result = []
            for c in db.query(models.Category).order_by(models.Category.name.asc()).all():
                cnt = db.query(func.count(models.Product.id)).filter(
                    models.Product.category == c.name
                ).scalar()
                result.append({"name": c.name, "product_count": cnt})
            # បន្ថែម Category ដែលមានក្នុងផលិតផល តែមិនទាន់មានក្នុងតារាង categories
            existing = {r["name"] for r in result}
            for (cat,) in db.query(models.Product.category).distinct().all():
                if cat and cat not in existing:
                    cnt = db.query(func.count(models.Product.id)).filter(
                        models.Product.category == cat
                    ).scalar()
                    result.append({"name": cat, "product_count": cnt})
            return result

        if name == "list_products":
            limit = max(1, min(int(args.get("limit", 10)), 20))
            prods = db.query(models.Product).order_by(
                models.Product.created_at.desc()
            ).limit(limit).all()
            return [_product_dict(p) for p in prods]

        if name == "search_products":
            q = (args.get("query") or "").strip()
            if not q:
                return []
            like = f"%{q}%"
            prods = (
                db.query(models.Product)
                .filter(
                    or_(
                        models.Product.name.ilike(like),
                        models.Product.description.ilike(like),
                        models.Product.category.ilike(like),
                    )
                )
                .limit(10)
                .all()
            )
            return [_product_dict(p) for p in prods]

        if name == "get_product_details":
            q = (args.get("name") or "").strip()
            if not q:
                return {"error": "no product name provided"}
            p = db.query(models.Product).filter(
                models.Product.name.ilike(f"%{q}%")
            ).first()
            if not p:
                return {"error": f"product '{q}' not found in the store"}
            return _product_dict(p)

        if name == "check_stock":
            q = (args.get("name") or "").strip()
            p = db.query(models.Product).filter(
                models.Product.name.ilike(f"%{q}%")
            ).first()
            if not p:
                return {"error": f"product '{q}' not found", "in_stock": False}
            return {"name": p.name, "in_stock": p.stock > 0, "stock": p.stock}

        return {"error": f"unknown tool '{name}'"}
    except Exception as e:  # ការពារកុំឲ្យ AI ដាច់ពេល Database មានបញ្ហា
        return {"error": str(e)}
    finally:
        db.close()


# ============================================================
# DeepSeek Function Calling
# ============================================================
async def _complete(messages: List[dict]) -> dict:
    """ហៅ DeepSeek API ម្តង (មាន tools)"""
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            DEEPSEEK_URL,
            headers={
                "Authorization": f"Bearer {settings.DEEPSEEK_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": DEEPSEEK_MODEL,
                "messages": messages,
                "tools": TOOLS,
                "tool_choice": "auto",
                "max_tokens": 1500,
                "temperature": 0.6,
            },
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]

async def ask_deepseek_with_tools(messages: List[dict]) -> str:
    """
    ហៅ AI ហើយអនុញ្ញាតឲ្យវាស្វែងរក Database តាមរយៈ Tools៖
    1. AI អាចសុំ tool call (ឧ. search_products)
    2. យើងប្រតិបត្តិ tool ជាមួយទិន្នន័យពិត
    3. ផ្ញើលទ្ធផលត្រឡប់ទៅ AI ដើម្បីសរសេរចម្លើយចុងក្រោយ
    """
    for _ in range(MAX_TOOL_ROUNDS):
        msg = await _complete(messages)
        tool_calls = msg.get("tool_calls")

        if not tool_calls:
            return (msg.get("content") or "").strip()

        # AI ចង់ប្រើ tool -> បន្ថែម request របស់វាទៅ conversation
        messages.append(msg)

        for tc in tool_calls:
            fn = tc.get("function", {})
            name = fn.get("name", "")
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            result = execute_tool(name, args)
            messages.append({
                "role": "tool",
                "tool_call_id": tc.get("id", ""),
                "content": json.dumps(result, ensure_ascii=False, default=str),
            })

    return "I couldn't find a complete answer. Please try rephrasing your question."

# ==========================================================
# Endpoints
# ==========================================================
@router.get("/config")
def chat_config():
    return {"enabled": chat_enabled(), "model": DEEPSEEK_MODEL}

@router.post("/message")
async def send_message(payload: schemas.ChatRequest):
    if not chat_enabled():
        raise HTTPException(status_code=400, detail="AI chat is not configured")

    message = payload.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message cannot be empty")
    if len(message) > 2000:
        raise HTTPException(status_code=400, detail="Message is too long (max 2000 characters)")

    # ឈ្មោះហាងសម្រាប់ System Prompt
    db = SessionLocal()
    try:
        site_rows = {s.key: s.value for s in db.query(models.SiteSetting).all()}
    finally:
        db.close()
    site_name = site_rows.get("site_name") or "this online store"

    system_prompt = (
        f"You are the helpful AI shopping assistant for '{site_name}'. "
        "You have access to the store's real database through tools, so you can answer "
        "questions about products, prices, stock, categories and store info accurately. "
        "When the user asks about products, prices, stock, categories or anything about the "
        "store, ALWAYS use the available tools to look up the real data instead of guessing. "
        "Be friendly, warm and concise (under ~150 words). Use the real data you retrieve in "
        "your answer. If a product or category is not found, say so honestly and suggest "
        "something similar from the data you do have."
    )

    history = payload.history or []
    history_messages = []
    for m in history[-MAX_HISTORY:]:
        if m.role in ("user", "assistant") and m.content.strip():
            history_messages.append({"role": m.role, "content": m.content.strip()[:2000]})

    messages = (
        [{"role": "system", "content": system_prompt}]
        + history_messages
        + [{"role": "user", "content": message}]
    )

    try:
        reply = await ask_deepseek_with_tools(messages)
    except httpx.HTTPStatusError as e:
        if e.response is not None and e.response.status_code == 401:
            raise HTTPException(
                status_code=502,
                detail="AI service rejected the API key. Check DEEPSEEK_API_KEY in backend/.env",
            )
        raise HTTPException(status_code=502, detail="AI service error. Please try again.")
    except Exception:
        raise HTTPException(status_code=502, detail="AI service error. Please try again.")

    return {"reply": reply}

