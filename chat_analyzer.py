"""
🔍 Smart Chat Analyzer - تشخیص خودکار موضوع گروه/کانال
========================================================
سیستم چندلایه با fallback خودکار:

لایه ۱: Keyword matching (رایگان، آنی) — اگه confidence ≥ 60٪
لایه ۲: Groq → اگر rate limit خورد → OpenRouter → اگر خورد → HuggingFace
         هر provider چندتا مدل رایگان داره که auto-switch میشن
لایه ۳: برمیگرده به نتیجه keyword حتی با confidence پایین

Providers + Free Models:
  Groq (رایگان):
    - llama-3.3-70b-versatile (1000 req/day)
    - llama-3.1-8b-instant (7000 req/day)
    - mixtral-8x7b-32768 (14000 req/day)
  OpenRouter (رایگان):
    - google/gemini-flash-1.5 (1500 req/day)
    - meta-llama/llama-3.2-3b-instruct (رایگان)
    - qwen/qwen-2.5-7b-instruct (رایگان)
  HuggingFace (رایگان):
    - mistralai/Mistral-7B-Instruct-v0.3
    - google/gemma-2-2b-it
"""

import re
import json
import os
import time
import threading

# ═══════════════ API Keys (set via Render env vars) ═══════════════
# Set these in Render Dashboard → Environment Variables:
#   GROQ_API_KEY, OPENROUTER_API_KEY, HUGGINGFACE_API_KEY (or HF_API_KEY)

GROQ_KEYS = [
    os.environ.get("GROQ_API_KEY", ""),
]
OPENROUTER_KEYS = [
    os.environ.get("OPENROUTER_API_KEY", ""),
]
HF_KEYS = [
    os.environ.get("HUGGINGFACE_API_KEY", ""),
    os.environ.get("HF_API_KEY", ""),
]

def _get_key(key_list):
    """Return first non-empty key"""
    for k in key_list:
        if k and k.strip():
            return k.strip()
    return ""

# ═══════════════ Provider Models (sorted by preference) ═══════════════
PROVIDER_MODELS = {
    "groq": [
        {"model": "llama-3.3-70b-versatile", "name": "Llama 3.3 70B", "max_tokens": 150},
        {"model": "llama-3.1-8b-instant", "name": "Llama 3.1 8B", "max_tokens": 100},
        {"model": "mixtral-8x7b-32768", "name": "Mixtral 8x7B", "max_tokens": 100},
    ],
    "openrouter": [
        {"model": "google/gemini-flash-1.5", "name": "Gemini Flash 1.5", "max_tokens": 150},
        {"model": "meta-llama/llama-3.2-3b-instruct:free", "name": "Llama 3.2 3B", "max_tokens": 100},
        {"model": "qwen/qwen-2.5-7b-instruct:free", "name": "Qwen 2.5 7B", "max_tokens": 100},
        {"model": "google/gemma-2-9b-it:free", "name": "Gemma 2 9B", "max_tokens": 100},
    ],
    "huggingface": [
        {"model": "mistralai/Mistral-7B-Instruct-v0.3", "name": "Mistral 7B", "max_tokens": 100},
        {"model": "google/gemma-2-2b-it", "name": "Gemma 2 2B", "max_tokens": 60},
    ],
}

# ═══════════════ Rate Limit Tracking ═══════════════
_rate_limit_cooldowns: dict = {}  # "groq:model" -> timestamp until cooldown ends
_cooldown_lock = threading.Lock()

def _is_cooled_down(key: str) -> bool:
    with _cooldown_lock:
        until = _rate_limit_cooldowns.get(key, 0)
        return time.time() < until

def _set_cooldown(key: str, seconds: int = 300):
    with _cooldown_lock:
        _rate_limit_cooldowns[key] = time.time() + seconds

def _is_rate_limited(error_str: str, status_code: int = 0) -> bool:
    """Detect rate limit / quota exceeded errors"""
    err_lower = error_str.lower()
    if status_code in (429, 403):
        return True
    if any(x in err_lower for x in ["rate limit", "rate_limit", "too many requests",
                                      "quota exceeded", "quota_exceeded", "insufficient_quota",
                                      "model is overloaded", "service unavailable",
                                      "503", "server error", "capacity"]):
        return True
    return False

# ═══════════════ Keyword Classification Database ═══════════════
CATEGORY_KEYWORDS = {
    "گیمینگ": {
        "fa": ["گیم", "بازی", "پلی", "گیمر", "کالاف", "پابجی", "فورتنایت", "ماینکرفت", "جی تی ای",
               "کانتر", "دوتا", "لیگ", "افلاین", "آنلاین", "کنسول", "ایکس باکس", "پلی استیشن",
               "استیم", "اپیک", "گیمینگ", "دانلود بازی", "مود", "چیت", "هک بازی", "ps4", "ps5",
               "xbox", "pc gaming", "valorant", "apex", "warzone", "roblox", "free fire"],
        "en": ["game", "gaming", "gamer", "play", "pubg", "fortnite", "minecraft", "gta",
               "counter strike", "csgo", "cs2", "dota", "league", "steam", "epic",
               "playstation", "xbox", "nintendo", "valorant", "apex", "warzone", "roblox",
               "free fire", "cod", "fifa", "esports"],
        "icon": "🎮"
    },
    "تکنولوژی": {
        "fa": ["تکنولوژی", "فناوری", "برنامه", "کد", "پایتون", "جاوا", "هوش مصنوعی", "ربات",
               "کامپیوتر", "موبایل", "گوشی", "لپ تاپ", "نرم افزار", "سخت افزار",
               "جاوااسکریپت", "ریکت", "وب", "اندروید", "ios", "سرور", "شبکه", "امنیت",
               "هک", "لینوکس", "گیت", "گیتهاب", "docker", "devops", "cloud", "database"],
        "en": ["tech", "technology", "programming", "coding", "python", "javascript", "ai",
               "computer", "mobile", "software", "hardware", "react", "app", "android",
               "ios", "server", "network", "security", "linux", "git", "github",
               "api", "docker", "devops", "cloud", "database", "frontend", "backend"],
        "icon": "💻"
    },
    "کریپتو": {
        "fa": ["بیت کوین", "اتریوم", "کریپتو", "ارز دیجیتال", "بلاکچین", "ماین", "ماینر",
               "صرافی", "بایننس", "کوینکس", "نوبیتکس", "ولت", "متامسک", "تراست ولت",
               "دیفای", "NFT", "توکن", "ایر دراپ", "تتر", "تون", "نات کوین",
               "همستر", "تپ سواپ", "ایردراپ", "web3", "رمزارز"],
        "en": ["bitcoin", "ethereum", "crypto", "cryptocurrency", "blockchain", "mining",
               "exchange", "binance", "wallet", "metamask", "defi", "nft",
               "token", "airdrop", "btc", "eth", "usdt", "ton", "solana", "web3"],
        "icon": "₿"
    },
    "فیلم و سریال": {
        "fa": ["فیلم", "سریال", "انیمه", "انیمیشن", "سینما", "نماوا", "فیلیمو", "نتفلیکس",
               "دوبله", "زیرنویس", "دانلود فیلم", "بلوری", "تریلر", "هالیوود",
               "بالیوود", "مارول", "دیسی", "هری پاتر", "بازی تاج و تخت", "برکینگ بد"],
        "en": ["movie", "film", "series", "tv show", "anime", "animation", "cinema",
               "netflix", "hbo", "disney", "marvel", "dc", "trailer", "hollywood",
               "imdb", "streaming", "download", "subtitle", "dubbed"],
        "icon": "🎬"
    },
    "موسیقی": {
        "fa": ["موسیقی", "آهنگ", "موزیک", "خواننده", "رپ", "پاپ", "راک", "کنسرت", "گیتار",
               "پیانو", "درامز", "بیس", "میکس", "ریمیکس", "اسپاتیفای", "ساندکلود",
               "اهنگ", "ملودی", "آلبوم", "موزیک ویدیو", "کاور"],
        "en": ["music", "song", "singer", "rap", "pop", "rock", "concert", "guitar",
               "piano", "drums", "mix", "remix", "spotify", "soundcloud", "album",
               "playlist", "dj", "beat", "melody", "cover", "band"],
        "icon": "🎵"
    },
    "ورزشی": {
        "fa": ["فوتبال", "ورزش", "استقلال", "پرسپولیس", "لیگ", "بارسلونا", "رئال", "منچستر",
               "والیبال", "بسکتبال", "کشتی", "المپیک", "جام جهانی",
               "گل", "ورزشکار", "بدنسازی", "فیتنس", "باشگاه", "مربی"],
        "en": ["football", "sport", "soccer", "basketball", "tennis", "f1", "formula",
               "ufc", "boxing", "olympic", "world cup", "premier league", "laliga",
               "champions league", "gym", "fitness", "workout", "bodybuilding"],
        "icon": "⚽"
    },
    "آشپزی": {
        "fa": ["آشپزی", "غذا", "کیک", "شیرینی", "دسر", "پلو", "خورشت", "کباب", "پیتزا",
               "فست فود", "سالاد", "نوشیدنی", "ساندویچ", "صبحانه", "ناهار", "شام",
               "دستور پخت", "رسپی", "سفره", "خانگی"],
        "en": ["cooking", "food", "recipe", "cake", "dessert", "pizza", "burger",
               "fast food", "salad", "drink", "breakfast", "lunch", "dinner",
               "baking", "chef", "kitchen", "homemade", "cuisine"],
        "icon": "🍳"
    },
    "آموزشی": {
        "fa": ["آموزش", "یادگیری", "درس", "مدرسه", "دانشگاه", "کنکور", "زبان انگلیسی",
               "آیلتس", "تافل", "تدریس", "استاد", "کلاس", "دوره", "کتاب", "جزوه",
               "ریاضی", "فیزیک", "شیمی", "فلسفه", "روانشناسی"],
        "en": ["learn", "education", "tutorial", "course", "school", "university",
               "english", "ielts", "toefl", "teacher", "class", "book", "study",
               "math", "physics", "chemistry", "history", "science", "exam"],
        "icon": "📚"
    },
    "فروشگاهی": {
        "fa": ["فروش", "خرید", "قیمت", "تخفیف", "مارکت", "فروشگاه", "شاپ", "پرداخت",
               "سفارش", "کالا", "محصول", "برند", "کیف", "کفش", "لباس",
               "آگهی", "نیازمندی", "دیوار", "دیجی کالا", "آمازون"],
        "en": ["shop", "store", "buy", "sell", "price", "discount", "market",
               "payment", "order", "product", "brand", "shopping", "amazon",
               "ebay", "aliexpress", "digikala"],
        "icon": "🛒"
    },
    "سرگرمی": {
        "fa": ["سرگرمی", "فان", "شوخی", "میم", "طنز", "خنده", "جوک", "چالش",
               "تیک تاک", "اینستاگرام", "یوتوب", "ولاگ", "استریم", "لایو"],
        "en": ["fun", "meme", "joke", "challenge", "tiktok", "instagram",
               "youtube", "vlog", "stream", "live", "viral", "entertainment"],
        "icon": "🎭"
    },
}


def analyze_by_keywords(title: str, description: str = "") -> dict:
    """Keyword-based classification. Returns category, confidence, matched keywords."""
    text = f"{title} {description}".lower()
    best_category = None
    best_score = 0
    best_matches = []

    for cat_name, data in CATEGORY_KEYWORDS.items():
        score = 0
        matches = []
        for kw in data["fa"]:
            if kw in text:
                score += 2
                matches.append(kw)
        for kw in data["en"]:
            if kw in text:
                score += 1
                matches.append(kw)
        if score > best_score:
            best_score = score
            best_category = cat_name
            best_matches = matches

    if best_score == 0:
        return {"category": None, "confidence": 0, "matched_keywords": []}

    if best_score >= 12:    confidence = 95
    elif best_score >= 8:   confidence = 85
    elif best_score >= 5:   confidence = 70
    elif best_score >= 3:   confidence = 50
    else:                   confidence = 30

    return {
        "category": best_category,
        "confidence": confidence,
        "matched_keywords": best_matches[:10],
        "icon": CATEGORY_KEYWORDS.get(best_category, {}).get("icon", "📁")
    }


# ═══════════════ AI API Call Helpers ═══════════════

def _build_prompt(title: str, description: str = "") -> str:
    cats = ", ".join(CATEGORY_KEYWORDS.keys())
    return (
        f"Classify this chat. Reply with ONLY JSON: "
        f'{{"category":"...", "reason":"short Persian reason"}}\n\n'
        f"Title: {title}\nDesc: {description or 'N/A'}\nCategories: {cats}"
    )


def _call_groq(prompt: str, model_info: dict, api_key: str) -> dict:
    """Call Groq API with given model. Returns parsed result or raises."""
    import urllib.request
    body = json.dumps({
        "model": model_info["model"],
        "messages": [
            {"role": "system", "content": "JSON-only response. No markdown. Just the JSON object."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.1,
        "max_tokens": model_info.get("max_tokens", 150)
    }).encode()

    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=body,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    )
    resp = urllib.request.urlopen(req, timeout=12)
    data = json.loads(resp.read())
    return _parse_response(data["choices"][0]["message"]["content"])


def _call_openrouter(prompt: str, model_info: dict, api_key: str) -> dict:
    """Call OpenRouter API. Returns parsed result or raises."""
    import urllib.request
    body = json.dumps({
        "model": model_info["model"],
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
        "max_tokens": model_info.get("max_tokens", 150)
    }).encode()

    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/farzadabbasi617-star/telegram-anti-scraper-bot",
            "X-Title": "Telegram Anti Scraper Bot"
        }
    )
    resp = urllib.request.urlopen(req, timeout=15)
    data = json.loads(resp.read())
    return _parse_response(data["choices"][0]["message"]["content"])


def _call_huggingface(prompt: str, model_info: dict, api_key: str) -> dict:
    """Call HuggingFace Inference API. Returns parsed result or raises."""
    import urllib.request
    body = json.dumps({
        "inputs": prompt,
        "parameters": {"max_new_tokens": model_info.get("max_tokens", 100), "temperature": 0.1}
    }).encode()

    req = urllib.request.Request(
        f"https://api-inference.huggingface.co/models/{model_info['model']}",
        data=body,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    )
    resp = urllib.request.urlopen(req, timeout=20)
    data = json.loads(resp.read())
    content = data[0].get("generated_text", "") if isinstance(data, list) else str(data)
    # HF often returns prompt + answer; strip the prompt
    if "Reply with" in content or "Classify this" in content:
        content = content.split("\n")[-1] if "\n" in content else content
    return _parse_response(content)


def _parse_response(content: str) -> dict:
    """Extract JSON from AI response text"""
    # Try direct JSON parse first
    content_clean = content.strip()
    # Remove markdown code blocks if present
    if content_clean.startswith("```"):
        lines = content_clean.split("\n")
        content_clean = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

    try:
        result = json.loads(content_clean)
        cat = result.get("category", "")
        if cat in CATEGORY_KEYWORDS:
            return {
                "category": cat,
                "confidence": 90,
                "reason": result.get("reason", ""),
                "icon": CATEGORY_KEYWORDS[cat].get("icon", "📁")
            }
    except:
        pass

    # Try regex extraction
    json_match = re.search(r'\{[^{}]*"category"\s*:\s*"([^"]+)"[^{}]*\}', content)
    if json_match:
        cat = json_match.group(1)
        if cat in CATEGORY_KEYWORDS:
            reason_match = re.search(r'"reason"\s*:\s*"([^"]+)"', content)
            return {
                "category": cat,
                "confidence": 85,
                "reason": reason_match.group(1) if reason_match else "",
                "icon": CATEGORY_KEYWORDS[cat].get("icon", "📁")
            }

    # Last resort: find any category name in the response
    for cat in CATEGORY_KEYWORDS:
        if f'"{cat}"' in content or f"'{cat}'" in content or cat in content:
            return {
                "category": cat,
                "confidence": 70,
                "reason": content[:100],
                "icon": CATEGORY_KEYWORDS[cat].get("icon", "📁")
            }

    raise ValueError(f"Could not parse: {content[:200]}")


# ═══════════════ Multi-Provider Smart Fallback ═══════════════

def _try_provider_chain(title: str, description: str = "") -> dict:
    """
    Try all providers in order with automatic model + key fallback.
    Returns result dict or empty dict on total failure.
    """
    prompt = _build_prompt(title, description)

    # ════ Provider 1: Groq ════
    groq_key = _get_key(GROQ_KEYS)
    if groq_key:
        for model_info in PROVIDER_MODELS["groq"]:
            cache_key = f"groq:{model_info['model']}"
            if _is_cooled_down(cache_key):
                continue
            try:
                result = _call_groq(prompt, model_info, groq_key)
                result["ai_model"] = f"groq-{model_info['name']}"
                return result
            except Exception as e:
                err_str = str(e)
                print(f"⚠️ Groq/{model_info['name']}: {err_str[:120]}", flush=True)
                if _is_rate_limited(err_str):
                    _set_cooldown(cache_key, 300)  # 5 min cooldown
                # continue to next model

    # ════ Provider 2: OpenRouter ════
    or_key = _get_key(OPENROUTER_KEYS)
    if or_key:
        for model_info in PROVIDER_MODELS["openrouter"]:
            cache_key = f"openrouter:{model_info['model']}"
            if _is_cooled_down(cache_key):
                continue
            try:
                result = _call_openrouter(prompt, model_info, or_key)
                result["ai_model"] = f"openrouter-{model_info['name']}"
                return result
            except Exception as e:
                err_str = str(e)
                print(f"⚠️ OpenRouter/{model_info['name']}: {err_str[:120]}", flush=True)
                if _is_rate_limited(err_str):
                    _set_cooldown(cache_key, 300)

    # ════ Provider 3: HuggingFace ════
    hf_key = _get_key(HF_KEYS)
    if hf_key:
        for model_info in PROVIDER_MODELS["huggingface"]:
            cache_key = f"hf:{model_info['model']}"
            if _is_cooled_down(cache_key):
                continue
            try:
                result = _call_huggingface(prompt, model_info, hf_key)
                result["ai_model"] = f"hf-{model_info['name']}"
                return result
            except Exception as e:
                err_str = str(e)
                print(f"⚠️ HuggingFace/{model_info['name']}: {err_str[:120]}", flush=True)
                if _is_rate_limited(err_str):
                    _set_cooldown(cache_key, 300)

    return {}  # All providers failed


# ═══════════════ Main Smart Analyzer ═══════════════

def smart_analyze(title: str, description: str = "", force_ai: bool = False) -> dict:
    """
    Hybrid analysis: keyword → multi-provider AI fallback with auto model switching.

    Returns: {
        "category": str or None,
        "confidence": 0-100,
        "method": "keyword" | "groq" | "openrouter" | "huggingface" | "keyword_low_confidence" | "none",
        "matched_keywords": [...],
        "reason": str,
        "icon": str,
        "ai_model": str (if AI was used)
    }
    """
    # Step 1: Keyword analysis (always free, always instant)
    kw_result = analyze_by_keywords(title, description)

    if not force_ai and kw_result["confidence"] >= 60:
        return {**kw_result, "method": "keyword"}

    # Step 2: Multi-provider AI chain with auto-fallback
    ai_result = _try_provider_chain(title, description)

    if ai_result.get("category"):
        # Determine method from ai_model
        model = ai_result.get("ai_model", "")
        if "groq" in model:
            method = "groq"
        elif "openrouter" in model:
            method = "openrouter"
        elif "hf" in model:
            method = "huggingface"
        else:
            method = "ai"
        return {
            **ai_result,
            "method": method,
            "matched_keywords": kw_result.get("matched_keywords", []),
            "confidence": ai_result.get("confidence", 85),
        }

    # Step 3: Fallback to keyword result even if low confidence
    if kw_result["category"]:
        return {**kw_result, "method": "keyword_low_confidence"}

    return {
        "category": None, "confidence": 0, "method": "none",
        "matched_keywords": [], "reason": "تمام سرویس‌ها در دسترس نیستند", "icon": "📁"
    }


# ═══════════════ Fetch chat info from Telegram ═══════════════

async def fetch_chat_info(client, chat_id: int) -> dict:
    """Fetch full chat info including description for analysis"""
    try:
        chat = await client.app.get_chat(chat_id)
        return {
            "title": chat.title or f"Chat {chat_id}",
            "description": (getattr(chat, 'description', '') or '')[:500],
            "members_count": getattr(chat, 'members_count', 0) or 0,
            "chat_type": str(chat.type).lower() if hasattr(chat, 'type') else 'group'
        }
    except Exception as e:
        print(f"fetch_chat_info err: {e}", flush=True)
        return {"title": f"Chat {chat_id}", "description": "", "members_count": 0, "chat_type": "group"}
