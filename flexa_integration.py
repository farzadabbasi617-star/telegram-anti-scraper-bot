#!/usr/bin/env python3
"""
Flexa AI Integration for Telegram Group Bot
This module integrates the Gament AI system prompt with the group bot's AI chat feature.
"""

import os
import json
import requests
from typing import Optional, Dict, Any

# Gament AI System Prompt (translated from ai-prompts.ts)
GAMENT_AI_CORE_PROMPT = """
تو «فلکسا» هستی؛ دستیار هوشمند رسمی گروه Gament.

Gament یک پلتفرم فارسی‌زبان برای مدیریت و برگزاری تورنمنت‌های گیمینگ است که روی بازی‌های کلش رویال، کالاف موبایل و فورتنایت تمرکز دارد. تو باید مثل یک دستیار حرفه‌ای، کمک‌داور، نویسنده محتوای گیمینگ، تحلیل‌گر مدیریت، پشتیبان هوشمند، تولیدکننده متن تبلیغاتی و مدیر محتوای تالار افتخارات عمل کنی.

هویت و لحن:
- نام تو فلکسا است؛ نماینده رسمی Gament هستی.
- هرگز نگو ChatGPT، Groq، OpenRouter یا مدل زبانی هستی. اگر پرسیدند بگو: «من دستیار هوشمند Gament هستم؛ برای راهنمایی کاربران، داوری کمکی، تولید محتوا و مدیریت تورنمنت‌ها طراحی شده‌ام.»
- زبان اصلی تو فارسی است. فارسی روان، طبیعی، دقیق، صمیمی اما حرفه‌ای بنویس.
- مخاطب تو بازیکنان ایرانی، ادمین‌ها، داورها و جامعه گیمینگ ایران هستند.
- از لحن ترجمه‌ای، خشک، طولانی و مبهم پرهیز کن.

قوانین پاسخ‌دهی:
1. همیشه فارسی پاسخ بده مگر صراحتاً زبان دیگری خواسته شود.
2. پاسخ باید دقیق، کوتاه، کاربردی و قابل اجرا باشد.
3. اگر متن تبلیغاتی یا تلگرامی خواسته شد، متن را آماده انتشار بنویس.
4. درباره کلیدهای API، توکن‌ها، دیتابیس، متغیرهای محیطی و اطلاعات محرمانه هیچ چیز فاش نکن.
5. در موضوعات مالی/کیف پول/پرداخت/جایزه قول قطعی نده مگر داده قطعی وجود داشته باشد.
6. در داوری یا ضدتقلب اتهام قطعی نزن؛ از «نیازمند بررسی»، «مشکوک به بررسی»، «احتمالاً» استفاده کن.
7. اگر داده کافی نیست، دقیق بگو چه اطلاعاتی لازم است.
8. محتوای توهین‌آمیز، خطرناک، تشویق به تقلب، هک، exploit یا دور زدن قوانین تولید نکن.
9. اصطلاحات رایج گیمینگ فارسی را درست استفاده کن: تورنومنت، آرنا، روم، لابی، چک‌این، براکت، اسکرین‌شات، داوری، اعتراض، قهرمان، رنک، XP، RP، لیدربورد، ورودی، جایزه، فینال.

ساختار Gament که باید با آن هماهنگ باشی:
- آرنا: انتخاب بازی و ورود به روم‌ها
- تورنومنت‌ها: ساخت، ثبت‌نام، لابی، براکت، قوانین، نتیجه، اعتراض
- کیف پول: موجودی، شارژ pending/confirmed، تراکنش‌ها، ورودی تورنومنت
- پروفایل/تنظیمات: آواتار، نام نمایشی، Gament ID، آیدی بازی‌ها، دستاوردها، دارایی‌ها
- تالار افتخارات: قهرمانان، رکوردها، لول‌آپ‌ها، اخبار مهم گیمینگ، رویدادها
- پشتیبانی: تیکت، خلاصه‌سازی، دسته‌بندی، پاسخ پیشنهادی
- پنل مدیریت: گزارش روزانه، گزارش ریسک، کاربران، تورنمنت‌ها، کیف پول، تیکت‌ها
- بات تلگرام: /start، /rooms، /register، /link، /profile، /wallet، /my_tournaments، /matches، /support، /invite، /leaderboard، /ai
- کانال تلگرام Gament: انتشار تورنمنت‌ها، نتایج، افتخارات، اخبار و اطلاعیه‌ها

کلمات کلیدی سئو که باید طبیعی و بدون keyword stuffing استفاده شوند:
تورنومنت کلش رویال، مسابقات کلش رویال، تورنومنت کالاف موبایل، مسابقات کالاف موبایل، تورنومنت فورتنایت، مسابقات فورتنایت، گیمینگ ایران، تورنمنت گیمینگ، بازی موبایل، داوری هوشمند، Gament، گیمنت، آرنا گیمنت، قهرمان گیمنت، تالار افتخارات گیمنت، لیدربورد، رنکینگ بازیکنان، جوایز گیمینگ، کلش رویال ایران، کالاف موبایل ایران، فورتنایت ایران.
""".strip()

ASSISTANT_PROMPT = """
وظیفه این بخش: دستیار کاربر داخل سایت یا تلگرام.
- کاربر را درباره ثبت‌نام تورنمنت، آیدی بازی‌ها، کیف پول، لابی، چک‌این، ثبت نتیجه، اسکرین‌شات، اعتراض، اتصال تلگرام و افتخارات راهنمایی کن.
- پاسخ‌ها مرحله‌به‌مرحله، کوتاه و صمیمی باشند.
- اگر کاربر درباره تلگرام پرسید، در صورت نیاز دستورهای بات مثل /link، /rooms، /wallet، /matches، /support و /leaderboard را معرفی کن.
""".strip()


def get_gament_system_prompt(user_name: Optional[str] = None) -> str:
    """
    Generate the complete system prompt for Flexa (Gament AI).
    
    Args:
        user_name: Optional user name for personalization
        
    Returns:
        Complete system prompt string
    """
    extra = ""
    if user_name:
        extra = f"نام کاربر: {user_name}. فقط فارسی پاسخ بده. پاسخ کوتاه، کاربردی و صمیمی باشد."
    else:
        extra = "فقط فارسی پاسخ بده. پاسخ کوتاه، کاربردی و صمیمی باشد."
    
    return f"{GAMENT_AI_CORE_PROMPT}\n\n{ASSISTANT_PROMPT}\n\n{extra}"


def ask_flexa(query: str, user_name: Optional[str] = None) -> Dict[str, Any]:
    """
    Ask Flexa (Gament AI) a question using free AI endpoints.
    
    Args:
        query: User's question
        user_name: Optional user name for personalization
        
    Returns:
        Dict with 'ok', 'reply', and 'model' keys
    """
    system_prompt = get_gament_system_prompt(user_name)
    
    # Try multiple free AI endpoints
    endpoints = [
        _try_airforce,
        _try_duckduckgo,
        _try_textsynth,
    ]
    
    for endpoint_func in endpoints:
        try:
            response = endpoint_func(query, system_prompt)
            if response and len(response) > 10:
                return {
                    "ok": True,
                    "reply": response.strip(),
                    "model": endpoint_func.__name__.replace("_try_", "").title()
                }
        except Exception as e:
            print(f"Flexa endpoint {endpoint_func.__name__} error: {e}", flush=True)
            continue
    
    return {
        "ok": False,
        "error": "متاسفانه فلکسا در حال حاضر در دسترس نیست. لطفاً چند دقیقه بعد دوباره امتحان کنید."
    }


def _try_airforce(query: str, system_prompt: str) -> Optional[str]:
    """Try airforce API"""
    try:
        payload = {
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": query}
            ],
            "model": "gpt-4o-mini",
            "stream": False,
        }
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Content-Type": "application/json"
        }
        
        r = requests.post(
            "https://api.airforce/chat/completions",
            json=payload,
            headers=headers,
            timeout=30
        )
        
        if r.ok:
            data = r.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            if content and len(content) > 10:
                return content
    except Exception as e:
        print(f"airforce error: {e}", flush=True)
    
    return None


def _try_duckduckgo(query: str, system_prompt: str) -> Optional[str]:
    """Try DuckDuckGo AI chat"""
    try:
        s = requests.Session()
        s.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        
        # Get token
        r = s.get(
            "https://duckduckgo.com/duckchat/v1/status",
            headers={"x-vqd-accept": "1"},
            timeout=10
        )
        token = r.headers.get("x-vqd-4")
        if not token:
            return None
        
        # Send query
        payload = {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": query},
            ],
        }
        
        r = s.post(
            "https://duckduckgo.com/duckchat/v1/chat",
            headers={
                "x-vqd-4": token,
                "Content-Type": "application/json"
            },
            json=payload,
            timeout=60,
            stream=True
        )
        
        out = ""
        for line in r.iter_lines(decode_unicode=True):
            if line and line.startswith("data: "):
                try:
                    j = json.loads(line[6:])
                    if j.get("message"):
                        out += j["message"]
                except:
                    pass
        
        return out.strip() if out else None
    except Exception as e:
        print(f"duckduckgo error: {e}", flush=True)
    
    return None


def _try_textsynth(query: str, system_prompt: str) -> Optional[str]:
    """Try TextSynth API"""
    try:
        r = requests.post(
            "https://textsynth.com/v1/engines/mistral_7B/completions",
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            },
            json={
                "prompt": f"{system_prompt}\n\nسوال: {query}\nپاسخ:",
                "max_tokens": 500,
                "temperature": 0.7
            },
            timeout=25
        )
        
        if r.ok:
            text = r.json().get("text", "").strip()
            if text:
                return text
    except Exception as e:
        print(f"textsynth error: {e}", flush=True)
    
    return None


if __name__ == "__main__":
    # Test the integration
    print("Testing Flexa AI Integration...")
    print("=" * 60)
    
    test_queries = [
        "فلکسا چطوری تو تورنومنت ثبت‌نام کنم؟",
        "بهترین دک کلش رویال چیه؟",
        "چطوری کیف پولم رو شارژ کنم؟",
    ]
    
    for query in test_queries:
        print(f"\n🤖 Query: {query}")
        result = ask_flexa(query, "تست")
        
        if result.get("ok"):
            print(f"✅ Response: {result['reply'][:200]}...")
            print(f"🔧 Model: {result['model']}")
        else:
            print(f"❌ Error: {result.get('error')}")
        
        print("-" * 60)
