"""
🔍 Smart Chat Analyzer - تشخیص خودکار موضوع گروه/کانال
========================================================
۱. اول با کیوردهای فارسی و انگلیسی تشخیص میده (سریع، بدون API)
۲. اگه confidence پایین بود → میره سراغ Groq AI (Llama 3.3 70B)
۳. قابلیت تعویض به OpenRouter / Hugging Face

API Providers supported: Groq (default), OpenRouter, HuggingFace
"""

import re
import json
import os

# ═══════════════ Keyword Classification Database ═══════════════
# Format: {category_key: {"fa": [keywords], "en": [keywords], "icon": "emoji"}}
CATEGORY_KEYWORDS = {
    "گیمینگ": {
        "fa": ["گیم", "بازی", "پلی", "گیمر", "کالاف", "پابجی", "فورتنایت", "ماینکرفت", "جی تی ای",
               "کانتر", "دوتا", "لیگ", "افلاین", "آنلاین", "کنسول", "ایکس باکس", "پلی استیشن",
               "استیم", "اپیک", "گیمینگ", "دانلود بازی", "مود", "چیت", "هک بازی", "ps4", "ps5",
               "xbox", "pc gaming", "valorant", "apex", "warzone", "roblox", "free fire"],
        "en": ["game", "gaming", "gamer", "play", "pubg", "fortnite", "minecraft", "gta",
               "counter strike", "csgo", "cs2", "dota", "league of legends", "lol",
               "steam", "epic games", "playstation", "xbox", "nintendo", "valorant", "apex",
               "warzone", "roblox", "free fire", "cod", "fifa", "esports"],
        "icon": "🎮"
    },
    "تکنولوژی": {
        "fa": ["تکنولوژی", "فناوری", "برنامه", "کد", "پایتون", "جاوا", "هوش مصنوعی", "ربات",
               "دیجیتال", "کامپیوتر", "موبایل", "گوشی", "لپ تاپ", "نرم افزار", "سخت افزار",
               "جاوااسکریپت", "ریکت", "وب", "اپ", "اندروید", "ios", "سرور", "شبکه", "امنیت",
               "هک", "کریپتو", "بلاکچین", "ماین", "سیستم عامل", "لینوکس", "گیت", "گیتهاب",
               "API", "docker", "devops", "cloud", "database", "frontend", "backend"],
        "en": ["tech", "technology", "programming", "coding", "python", "javascript", "ai",
               "artificial intelligence", "ml", "robot", "digital", "computer", "mobile",
               "software", "hardware", "react", "web dev", "app", "android", "ios", "server",
               "network", "security", "crypto", "blockchain", "linux", "git", "github",
               "api", "docker", "devops", "cloud", "database", "frontend", "backend"],
        "icon": "💻"
    },
    "کریپتو": {
        "fa": ["بیت کوین", "اتریوم", "کریپتو", "ارز دیجیتال", "بلاکچین", "ماین", "ماینر",
               "فارم", "صرافی", "بایننس", "کوینکس", "نوبیتکس", "ولت", "متامسک", "تراست ولت",
               "دیفای", "NFT", "توکن", "ایر دراپ", "بیتکوین", "تتر", "تون", "نات کوین",
               "همستر", "تپ سواپ", "ایردراپ", "web3", "web 3", "رمزارز"],
        "en": ["bitcoin", "ethereum", "crypto", "cryptocurrency", "blockchain", "mining",
               "miner", "exchange", "binance", "wallet", "metamask", "defi", "nft",
               "token", "airdrop", "btc", "eth", "usdt", "ton", "solana", "web3"],
        "icon": "₿"
    },
    "فیلم و سریال": {
        "fa": ["فیلم", "سریال", "انیمه", "انیمیشن", "سینما", "نماوا", "فیلیمو", "نتفلیکس",
               "دوبله", "زیرنویس", "دانلود فیلم", "بلوری", "1080", "720", "تریلر", "هالیوود",
               "بالیوود", "مارول", "دیسی", "هری پاتر", "بازی تاج و تخت", "برکینگ بد"],
        "en": ["movie", "film", "series", "tv show", "anime", "animation", "cinema",
               "netflix", "hbo", "disney", "marvel", "dc", "trailer", "hollywood",
               "bollywood", "imdb", "streaming", "download", "subtitle", "dubbed"],
        "icon": "🎬"
    },
    "موسیقی": {
        "fa": ["موسیقی", "آهنگ", "موزیک", "خواننده", "رپ", "پاپ", "راک", "کنسرت", "گیتار",
               "پیانو", "درامز", "بیس", "میکس", "ریمیکس", "اسپاتیفای", "ساندکلود",
               "اهنگ", "ملودی", "تنظیم", "آلبوم", "موزیک ویدیو", "کاور"],
        "en": ["music", "song", "singer", "rap", "pop", "rock", "concert", "guitar",
               "piano", "drums", "mix", "remix", "spotify", "soundcloud", "album",
               "playlist", "dj", "beat", "melody", "cover", "band"],
        "icon": "🎵"
    },
    "ورزشی": {
        "fa": ["فوتبال", "ورزش", "استقلال", "پرسپولیس", "لیگ", "بارسلونا", "رئال", "منچستر",
               "والیبال", "بسکتبال", "کشتی", "وزنه برداری", "المپیک", "جام جهانی",
               "پاس", "گل", "ورزشکار", "بدنسازی", "فیتنس", "باشگاه", "مربی"],
        "en": ["football", "sport", "soccer", "basketball", "tennis", "f1", "formula",
               "ufc", "boxing", "olympic", "world cup", "premier league", "laliga",
               "champions league", "gym", "fitness", "workout", "bodybuilding"],
        "icon": "⚽"
    },
    "آشپزی": {
        "fa": ["آشپزی", "غذا", "کیک", "شیرینی", "دسر", "پلو", "خورشت", "کباب", "پیتزا",
               "فست فود", "سالاد", "نوشیدنی", "ساندویچ", "صبحانه", "ناهار", "شام",
               "دستور پخت", "رسپی", "چی بپزم", "سفره", "خانگی"],
        "en": ["cooking", "food", "recipe", "cake", "dessert", "pizza", "burger",
               "fast food", "salad", "drink", "breakfast", "lunch", "dinner",
               "baking", "chef", "kitchen", "homemade", "cuisine"],
        "icon": "🍳"
    },
    "آموزشی": {
        "fa": ["آموزش", "یادگیری", "درس", "مدرسه", "دانشگاه", "کنکور", "زبان انگلیسی",
               "آیلتس", "تافل", "تدریس", "استاد", "کلاس", "دوره", "کتاب", "جزوه",
               "ریاضی", "فیزیک", "شیمی", "تاریخ", "جغرافیا", "فلسفه", "روانشناسی"],
        "en": ["learn", "education", "tutorial", "course", "school", "university",
               "english", "ielts", "toefl", "teacher", "class", "book", "study",
               "math", "physics", "chemistry", "history", "science", "exam"],
        "icon": "📚"
    },
    "فروشگاهی": {
        "fa": ["فروش", "خرید", "قیمت", "تخفیف", "مارکت", "فروشگاه", "شاپ", "پرداخت",
               "سفارش", "موجودی", "کالا", "محصول", "برند", "کیف", "کفش", "لباس",
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
    """
    Analyze chat topic using keyword matching.
    Returns: {"category": str or None, "confidence": 0-100, "matched_keywords": [...]}
    """
    text = f"{title} {description}".lower()
    best_category = None
    best_score = 0
    best_matches = []

    for cat_name, data in CATEGORY_KEYWORDS.items():
        score = 0
        matches = []

        for kw in data["fa"]:
            if kw in text:
                score += 2  # Persian keywords weight more (title is usually Persian)
                matches.append(kw)

        for kw in data["en"]:
            if kw in text:
                score += 1
                matches.append(kw)

        if score > best_score:
            best_score = score
            best_category = cat_name
            best_matches = matches

    # Calculate confidence (0-100)
    if best_score == 0:
        return {"category": None, "confidence": 0, "matched_keywords": []}

    # Scale: 1-2 matches = 30%, 3-5 = 60%, 6+ = 90%
    if best_score >= 12:
        confidence = 95
    elif best_score >= 8:
        confidence = 85
    elif best_score >= 5:
        confidence = 70
    elif best_score >= 3:
        confidence = 50
    else:
        confidence = 30

    return {
        "category": best_category,
        "confidence": confidence,
        "matched_keywords": best_matches[:10],
        "icon": CATEGORY_KEYWORDS.get(best_category, {}).get("icon", "📁")
    }


# ═══════════════ AI-based Classification (Groq / OpenRouter / HuggingFace) ═══════════════

def _build_prompt(title: str, description: str = "") -> str:
    """Build prompt for AI classification"""
    cats = list(CATEGORY_KEYWORDS.keys())
    cats_str = ", ".join(cats)

    prompt = f"""You are a chat topic classifier. Analyze this Telegram group/channel and pick ONE category.

Title: {title}
Description: {description or "(no description)"}

Available categories: {cats_str}

Reply with ONLY JSON: {{"category": "category_name", "reason": "short reason in Persian"}}"""
    return prompt


def analyze_with_groq(title: str, description: str = "", api_key: str = None) -> dict:
    """Use Groq API (Llama 3.3 70B) for classification"""
    if not api_key:
        api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        return {"category": None, "confidence": 0, "error": "No GROQ_API_KEY"}

    try:
        import urllib.request
        import urllib.error

        prompt = _build_prompt(title, description)
        body = json.dumps({
            "model": "llama-3.3-70b-versatile",
            "messages": [
                {"role": "system", "content": "You are a JSON-only classifier. Reply with valid JSON only."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.1,
            "max_tokens": 150
        }).encode()

        req = urllib.request.Request(
            "https://api.groq.com/openai/v1/chat/completions",
            data=body,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
        )

        resp = urllib.request.urlopen(req, timeout=15)
        data = json.loads(resp.read())
        content = data["choices"][0]["message"]["content"]

        # Extract JSON from response
        # Try to find {...} in the response
        json_match = re.search(r'\{[^}]+\}', content)
        if json_match:
            result = json.loads(json_match.group())
            cat = result.get("category", "")
            # Validate category is in our list
            if cat in CATEGORY_KEYWORDS:
                return {
                    "category": cat,
                    "confidence": 90,
                    "reason": result.get("reason", ""),
                    "icon": CATEGORY_KEYWORDS.get(cat, {}).get("icon", "📁"),
                    "ai_model": "groq-llama-3.3-70b"
                }

        return {"category": None, "confidence": 0, "error": "Could not parse AI response"}

    except Exception as e:
        return {"category": None, "confidence": 0, "error": str(e)}


def analyze_with_openrouter(title: str, description: str = "", api_key: str = None, model: str = "google/gemini-flash-1.5") -> dict:
    """Use OpenRouter API for classification"""
    if not api_key:
        api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        return {"category": None, "confidence": 0, "error": "No OPENROUTER_API_KEY"}

    try:
        import urllib.request

        prompt = _build_prompt(title, description)
        body = json.dumps({
            "model": model,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.1,
            "max_tokens": 150
        }).encode()

        req = urllib.request.Request(
            "https://openrouter.ai/api/v1/chat/completions",
            data=body,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://telegram-anti-scraper-bot.onrender.com",
                "X-Title": "Telegram Anti Scraper Bot"
            }
        )

        resp = urllib.request.urlopen(req, timeout=20)
        data = json.loads(resp.read())
        content = data["choices"][0]["message"]["content"]

        json_match = re.search(r'\{[^}]+\}', content)
        if json_match:
            result = json.loads(json_match.group())
            cat = result.get("category", "")
            if cat in CATEGORY_KEYWORDS:
                return {
                    "category": cat,
                    "confidence": 88,
                    "reason": result.get("reason", ""),
                    "icon": CATEGORY_KEYWORDS.get(cat, {}).get("icon", "📁"),
                    "ai_model": f"openrouter-{model}"
                }

        return {"category": None, "confidence": 0, "error": "Could not parse"}

    except Exception as e:
        # Fallback to free Google Gemini Flash via OpenRouter
        return {"category": None, "confidence": 0, "error": str(e)}


def analyze_with_huggingface(title: str, description: str = "", api_key: str = None) -> dict:
    """Use HuggingFace Inference API"""
    if not api_key:
        api_key = os.environ.get("HF_API_KEY", "")
    if not api_key:
        return {"category": None, "confidence": 0, "error": "No HF_API_KEY"}

    try:
        import urllib.request

        cats = list(CATEGORY_KEYWORDS.keys())
        prompt = f"Classify this chat: Title='{title}' Description='{description}'. Categories: {', '.join(cats)}. Reply with ONLY the category name."

        body = json.dumps({
            "inputs": prompt,
            "parameters": {"max_new_tokens": 20, "temperature": 0.1}
        }).encode()

        req = urllib.request.Request(
            "https://api-inference.huggingface.co/models/mistralai/Mistral-7B-Instruct-v0.3",
            data=body,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
        )

        resp = urllib.request.urlopen(req, timeout=20)
        data = json.loads(resp.read())
        content = data[0].get("generated_text", "") if isinstance(data, list) else str(data)

        for cat in CATEGORY_KEYWORDS:
            if cat.lower() in content.lower():
                return {
                    "category": cat,
                    "confidence": 80,
                    "reason": content[:100],
                    "icon": CATEGORY_KEYWORDS.get(cat, {}).get("icon", "📁"),
                    "ai_model": "huggingface-mistral-7b"
                }

        return {"category": None, "confidence": 0, "error": "Could not classify"}

    except Exception as e:
        return {"category": None, "confidence": 0, "error": str(e)}


# ═══════════════ Main Smart Analyzer (keyword → AI fallback) ═══════════════

def smart_analyze(title: str, description: str = "", ai_api_key: str = None) -> dict:
    """
    Hybrid analysis: keyword first, AI fallback if confidence < 60%.
    
    Returns: {
        "category": str or None,
        "confidence": 0-100,
        "method": "keyword" | "groq" | "openrouter" | "huggingface",
        "matched_keywords": [...],
        "reason": str,
        "icon": str
    }
    """
    # Step 1: Keyword analysis (instant, free)
    kw_result = analyze_by_keywords(title, description)

    if kw_result["confidence"] >= 60:
        return {
            **kw_result,
            "method": "keyword"
        }

    # Step 2: AI fallback (if confidence is low and API key is available)
    if ai_api_key or os.environ.get("GROQ_API_KEY") or os.environ.get("OPENROUTER_API_KEY"):
        # Try Groq first (fastest, free tier)
        groq_result = analyze_with_groq(title, description, ai_api_key)
        if groq_result.get("category"):
            return {**groq_result, "method": "groq"}

        # Try OpenRouter
        or_result = analyze_with_openrouter(title, description, ai_api_key)
        if or_result.get("category"):
            return {**or_result, "method": "openrouter"}

        # Try HuggingFace
        hf_result = analyze_with_huggingface(title, description, ai_api_key)
        if hf_result.get("category"):
            return {**hf_result, "method": "huggingface"}

    # Step 3: Return keyword result even if low confidence
    if kw_result["category"]:
        return {
            **kw_result,
            "method": "keyword_low_confidence"
        }

    return {
        "category": None,
        "confidence": 0,
        "method": "none",
        "matched_keywords": [],
        "reason": "Could not determine category",
        "icon": "📁"
    }


# ═══════════════ Fetch chat description from Telegram ═══════════════

async def fetch_chat_info(client, chat_id: int) -> dict:
    """Fetch full chat info including description for analysis"""
    try:
        chat = await client.app.get_chat(chat_id)
        desc = getattr(chat, 'description', '') or ''
        # Also try to get recent messages for better context
        title = chat.title or f"Chat {chat_id}"
        return {
            "title": title,
            "description": desc[:500],  # limit description length
            "members_count": getattr(chat, 'members_count', 0) or 0,
            "chat_type": str(chat.type).lower() if hasattr(chat, 'type') else 'group'
        }
    except Exception as e:
        print(f"fetch_chat_info err: {e}", flush=True)
        return {"title": f"Chat {chat_id}", "description": "", "members_count": 0, "chat_type": "group"}
