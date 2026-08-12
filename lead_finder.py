"""
=================================================================
🎮 Game Lead Finder & Scoring Module - @HaghBaKieBot
=================================================================
ماژول هوشمند کشف لیدهای حوزه گیمینگ/کریپتو، امتیازدهی و مدیریت لیدها
"""
import re
import json
import time
import random
import urllib.parse
import urllib.request
import asyncio

import db

PERSIAN_DIGITS = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')

CATEGORY_RULES = {
    'اکانت': ['اکانت', 'account', 'کلش', 'ولورانت', 'valorant', 'steam account', 'استیم اکانت'],
    'سی‌پی کالاف': ['سی پی', 'cp', 'کالاف', 'call of duty', 'cod', 'وارزون'],
    'یوسی پابجی': ['یوسی', 'uc', 'پابجی', 'pubg'],
    'جم/الماس': ['جم', 'الماس', 'free fire', 'فری فایر', 'gem', 'diamond'],
    'گیفت کارت': ['گیفت کارت', 'gift card', 'psn', 'playstation gift', 'استیم والت', 'steam wallet', 'ایکس باکس', 'xbox'],
    'فروشگاه گیم': ['فروشگاه بازی', 'فروشگاه کنسول', 'کنسول بازی', 'پلی استیشن', 'playstation', 'xbox', 'نینتندو', 'گیمینگ'],
    'گیم‌نت': ['گیم نت', 'گیم‌نت', 'game net', 'گیم سنتر', 'باشگاه بازی'],
    'آیتم/اسکین': ['اسکین', 'آیتم', 'skin', 'item'],
}

POSITIVE_TERMS = [
    'فروش', 'خرید', 'شارژ', 'ارزان', 'فوری', 'تحویل', 'معتبر', 'فروشگاه', 'خدمات',
    'اکانت', 'جم', 'سی پی', 'cp', 'یوسی', 'uc', 'گیفت کارت', 'پلی استیشن', 'استیم',
    'کالاف', 'پابجی', 'فری فایر', 'کلش', 'ولورانت', 'گیم', 'کنسول', 'گیمینگ',
]

NEGATIVE_TERMS = [
    'استخدام', 'دانلود', 'خبر', 'آموزش رایگان', 'رایگان', 'هک', 'چیت', 'تقلب',
]


def normalize_text(value: str) -> str:
    if not value:
        return ''
    return value.lower().replace('ي', 'ی').replace('ك', 'ک').strip()


def normalize_phone(phone: str) -> str:
    if not phone:
        return ''
    digits = re.sub(r'\D+', '', phone.translate(PERSIAN_DIGITS))
    if digits.startswith('0098'):
        digits = '0' + digits[4:]
    elif digits.startswith('98') and len(digits) >= 12:
        digits = '0' + digits[2:]
    return digits


def normalize_instagram(url_or_username: str) -> str:
    if not url_or_username:
        return ''
    val = url_or_username.strip().strip('@').strip('/').lower()
    if 'instagram.com' in val:
        m = re.search(r'instagram\.com/([a-zA-Z0-9_.]{2,60})', val)
        if m: val = m.group(1)
    val = val.strip('@').strip('/').lower()
    if val in {'p', 'reel', 'explore', 'accounts', 'stories'}:
        return ''
    return val if re.fullmatch(r'[a-z0-9_.]{2,60}', val) else ''


def normalize_telegram(url_or_username: str) -> str:
    if not url_or_username:
        return ''
    val = url_or_username.strip().strip('@').strip('/').lower()
    if 't.me' in val or 'telegram.me' in val:
        m = re.search(r'(?:t\.me|telegram\.me)/([a-zA-Z0-9_]{3,80})', val)
        if m: val = m.group(1)
    val = val.strip('@').strip('/').lower()
    return val if re.fullmatch(r'[a-z0-9_]{3,80}', val) else ''


def detect_category(*texts: str) -> str:
    body = normalize_text(' '.join([t or '' for t in texts]))
    best_category = 'گیمینگ'
    best_hits = 0
    for category, terms in CATEGORY_RULES.items():
        hits = sum(1 for term in terms if normalize_text(term) in body)
        if hits > best_hits:
            best_hits = hits
            best_category = category
    return best_category


def score_lead(title: str = "", description: str = "", url: str = "", phone: str = "", instagram: str = "", telegram: str = "") -> int:
    body = normalize_text(' '.join([title or '', description or '', url or '']))
    score = 40
    for term in POSITIVE_TERMS:
        if normalize_text(term) in body:
            score += 6
    for term in NEGATIVE_TERMS:
        if normalize_text(term) in body:
            score -= 10
    if phone:
        score += 20
    if instagram:
        score += 15
    if telegram:
        score += 15
    if any(domain in body for domain in ['instagram.com', 't.me', 'telegram.me']):
        score += 10
    return max(10, min(score, 100))


def get_invite_message(title: str = "عزیز", category: str = "محصولات و خدمات گیمینگ", target_link: str = "https://t.me/+gLScToU4DZdjZmM0") -> str:
    cat_label = category or 'گیمینگ و کنسول'
    return (
        f"سلام وقتتون بخیر 🌹\n"
        f"دیدم در زمینه {cat_label} فعالیت دارید.\n"
        f"ما یک انجمن و گروه تخصصی فروشندگان و فعالان گیمینگ راه‌اندازی کردیم که خریداران هدفمند زیادی اونجا عضو هستن.\n"
        f"خوشحال می‌شیم شما هم به جمع ما بپیوندید و خدمات/محصولاتتون رو معرفی کنید:\n"
        f"🔗 لینک عضویت: {target_link}\n"
        f"موفق باشید 🙏"
    )


async def search_leads_online(query: str, category_override: str = None) -> list:
    """Run multi-source search across DuckDuckGo HTML web search & Neshan/Public web APIs"""
    results = []
    clean_q = query.strip()
    if not clean_q:
        return []

    # Method 1: DuckDuckGo HTML search
    try:
        enc_q = urllib.parse.quote_plus(clean_q + " تلگرام یا اینستاگرام")
        req_url = f"https://html.duckduckgo.com/html/?q={enc_q}"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        
        async def fetch_ddg():
            def _get():
                r = urllib.request.Request(req_url, headers=headers)
                return urllib.request.urlopen(r, timeout=12).read().decode('utf-8')
            return await asyncio.to_thread(_get)

        html = await fetch_ddg()
        
        # Regex search for links in DDG results
        links = re.findall(r'<a class="result__url" href="([^"]+)".*?>(.*?)</a>', html, re.DOTALL)
        titles = re.findall(r'<a class="result__a"[^>]*>(.*?)</a>', html, re.DOTALL)
        snippets = re.findall(r'<a class="result__snippet"[^>]*>(.*?)</a>', html, re.DOTALL)

        for i, (link, disp) in enumerate(links[:20]):
            try:
                raw_url = urllib.parse.unquote(link)
                if 'uddg=' in raw_url:
                    m = re.search(r'uddg=([^&]+)', raw_url)
                    if m: raw_url = urllib.parse.unquote(m.group(1))

                t = titles[i] if i < len(titles) else clean_q
                t = re.sub(r'<[^>]+>', '', t).strip()
                snip = snippets[i] if i < len(snippets) else ""
                snip = re.sub(r'<[^>]+>', '', snip).strip()

                cat = category_override or detect_category(t, snip, clean_q)
                
                # Extract contacts
                phone_match = re.search(r'09\d{9}', snip + " " + t)
                phone = phone_match.group(0) if phone_match else ""

                tg_user = normalize_telegram(raw_url if 't.me' in raw_url else snip)
                ig_user = normalize_instagram(raw_url if 'instagram.com' in raw_url else snip)

                sc = score_lead(title=t, description=snip, url=raw_url, phone=phone, instagram=ig_user, telegram=tg_user)

                lead_item = {
                    "title": t or f"لید {clean_q}",
                    "url": raw_url,
                    "source": "DuckDuckGo Web",
                    "category": cat,
                    "phone": phone,
                    "telegram_username": tg_user,
                    "instagram_username": ig_user,
                    "score": sc,
                    "status": "new",
                    "notes": snip[:200]
                }
                
                # Save automatically to DB
                db.save_lead(
                    title=lead_item["title"],
                    url=lead_item["url"],
                    source=lead_item["source"],
                    category=lead_item["category"],
                    phone=lead_item["phone"],
                    telegram=lead_item["telegram_username"],
                    instagram=lead_item["instagram_username"],
                    score=lead_item["score"],
                    status="new",
                    notes=lead_item["notes"]
                )
                results.append(lead_item)
            except Exception as item_err:
                continue

    except Exception as e:
        print(f"Online lead search error: {e}", flush=True)

    return results
