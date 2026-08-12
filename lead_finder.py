"""
=================================================================
🎮 Game Lead Finder & Scoring Module - @HaghBaKieBot
=================================================================
ماژول هوشمند کشف لیدهای حوزه گیمینگ/کریپتو، پیدا کردن گروه‌های تلگرامی، امتیازدهی و مدیریت لیدها
"""
import re
import json
import time
import random
import urllib.parse
import urllib.request
import asyncio
import os

import db

PERSIAN_DIGITS = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')

CATEGORY_RULES = {
    'کلش رویال': ['کلش رویال', 'clash royale', 'clash_royale', 'رویال'],
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


async def search_telegram_groups_by_topic(query: str, app_bot=None) -> list:
    """Find Telegram Groups and Channels matching topic (e.g. 'کلش رویال') via Telegram MTProto Search & Web Search"""
    results = []
    clean_q = query.strip()
    if not clean_q:
        return []

    seen_usernames = set()

    # Phase 1: Try Pyrogram MTProto contacts.Search iterating through accounts
    try:
        accs = db.load_accounts()
        for phone, info in accs.items():
            st = db.get_account_status(phone)
            if st.get("status") == "banned":
                continue

            from attacker import AdvancedScraper, SESSIONS_DIR, safe_phone_filename
            from bot import API_ID, API_HASH
            from pyrogram.raw import functions, types

            sess_path = os.path.join(SESSIONS_DIR, f"acc_{safe_phone_filename(phone)}")
            blob = db.load_session_blob(phone)
            if blob and (not os.path.exists(sess_path + ".session") or os.path.getsize(sess_path + ".session") == 0):
                try:
                    with open(sess_path + ".session", "wb") as f:
                        f.write(blob)
                except: pass

            client = AdvancedScraper(
                session_name=sess_path,
                api_id=API_ID,
                api_hash=API_HASH,
                phone=phone
            )
            try:
                await client.connect()
                mtproto_res = await client.app.invoke(functions.contacts.Search(q=clean_q, limit=50))
                chats = getattr(mtproto_res, 'chats', []) or []

                for chat in chats:
                    un = getattr(chat, 'username', '') or ''
                    un = un.strip().lower()
                    if un and un not in seen_usernames:
                        seen_usernames.add(un)
                        title = getattr(chat, 'title', f"گروه @{un}") or f"گروه @{un}"
                        members = getattr(chat, 'participants_count', 0) or 0
                        is_megagroup = getattr(chat, 'megagroup', False)

                        lead_item = {
                            "title": title,
                            "url": f"https://t.me/{un}",
                            "source": "Telegram Search",
                            "category": detect_category(title, clean_q),
                            "phone": "",
                            "telegram_username": f"@{un}",
                            "instagram_username": "",
                            "score": min(95, 55 + (members // 200)),
                            "status": "new",
                            "members": members,
                            "chat_id": chat.id,
                            "notes": f"👥 {members:,} عضو | {'گروه عمومی' if is_megagroup else 'کانال عمومی تلگرام'}"
                        }

                        db.save_lead(
                            title=lead_item["title"],
                            url=lead_item["url"],
                            source=lead_item["source"],
                            category=lead_item["category"],
                            telegram=lead_item["telegram_username"],
                            score=lead_item["score"],
                            notes=lead_item["notes"]
                        )
                        db.upsert_scanned_chat(
                            chat_id=chat.id,
                            chat_name=title,
                            chat_type='group' if is_megagroup else 'channel',
                            category=lead_item["category"],
                            total_members=members
                        )
                        results.append(lead_item)

                if results:
                    break  # Search succeeded with this account

            except Exception as acc_err:
                print(f"Account {phone} search error: {acc_err}", flush=True)
                continue
            finally:
                try: await client.disconnect()
                except: pass
    except Exception as e:
        print(f"MTProto group search error: {e}", flush=True)

    # Phase 2: Web Search for Telegram Group links (site:t.me ...)
    try:
        from group_finder import search_via_web
        web_res = await asyncio.to_thread(search_via_web, clean_q, 15)
        for item in web_res:
            un = (item.get("chat_username") or "").strip().lower()
            if un and un not in seen_usernames:
                seen_usernames.add(un)
                title = f"گروه @{un}"
                lead_item = {
                    "title": title,
                    "url": f"https://t.me/{un}",
                    "source": "Telegram Web Search",
                    "category": detect_category(title, clean_q),
                    "phone": "",
                    "telegram_username": f"@{un}",
                    "instagram_username": "",
                    "score": 65,
                    "status": "new",
                    "members": 0,
                    "notes": f"📢 لینک تلگرام پیدا شده برای موضوع {clean_q}"
                }
                db.save_lead(
                    title=lead_item["title"],
                    url=lead_item["url"],
                    source=lead_item["source"],
                    category=lead_item["category"],
                    telegram=lead_item["telegram_username"],
                    score=65,
                    notes=lead_item["notes"]
                )
                results.append(lead_item)
    except Exception as e:
        print(f"Web group search error: {e}", flush=True)

    # Phase 3: General web search fallback
    if len(results) < 5:
        try:
            web_leads = await search_leads_online(clean_q)
            for w in web_leads:
                un = (w.get("telegram_username") or "").strip().lower().replace("@", "")
                if un and un not in seen_usernames:
                    seen_usernames.add(un)
                    results.append(w)
                elif not un:
                    results.append(w)
        except Exception as e: pass

    return results
