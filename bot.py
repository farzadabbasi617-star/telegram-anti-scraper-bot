# =================================================================
# ربات ضد اسکریپت - نسخه نهایی قطعی + سشن دائمی اکانت ها
# =================================================================
import asyncio
import sys
import os
import json
import re
import traceback
import glob as _glob

# Pyrogram 2.x needs an event loop set at import time (Python 3.10+ deprecates auto-loop)
try:
    _loop = asyncio.get_event_loop()
except RuntimeError:
    _loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_loop)

import io
import csv
import time
import random
import glob
import shutil
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread

sys.path.insert(0, '.')

from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import SessionPasswordNeeded, AuthKeyDuplicated, AuthKeyUnregistered, FloodWait

from attacker import AdvancedScraper, SESSIONS_DIR, safe_phone_filename, DEVICE_FP, _get_session_lock, _enable_wal_on_session
# _global_connect_lock حالا از attacker میاد
from attacker import _global_connect_lock as _connect_lock
from defender import AdvancedDefender
# hunter kept for backward compat (existing data still accessible)
from hunter import (
    scan_text, check_balance_of_findings, load_found, save_found,
    load_hunter_state, save_hunter_state, export_found_csv,
    start_auto_scanner
)
# new project finder module
from project_finder import (
    check_project_updates,
    CATEGORIES as PF_CATS, scan_category, scan_trending, search_trending_github,
    scan_custom_query, merge_new, to_jalali_age,
    load_found as pf_load, load_state as pf_state, save_state as pf_save_state,
    projects_by_category, export_csv as pf_export, clear_all as pf_clear,
)
import parallel
import db
from db import (
    save_user, load_users_dict as _db_load_users, bulk_save_users as _db_bulk_users,
    count_users as _db_count_users, save_account, load_accounts as _db_load_accounts,
    delete_account as _db_delete_account, save_session_blob as _db_save_sess,
    get_config as _db_get_config, set_config as _db_set_config,
    get_adder_limits as _db_get_limits, set_adder_limit as _db_set_limit,
    reset_adder_limits as _db_reset_limits, mark_added as _db_mark_added,
    is_added as _db_is_added, count_added as _db_count_added,
    set_bg_scan, get_bg_scan, get_owner_phone, set_owner_phone,
    save_project, load_projects, count_projects, clear_projects, migrate_json_to_db,
    get_scanned_chats, get_scanned_chat, update_chat_category,
    get_users_by_source, count_users_by_source, get_all_categories, get_category_stats,
    delete_scanned_chat, toggle_chat_favorite, upsert_scanned_chat,
)
from bg_scraper import start_in_background as bg_scraper_start, _backup_session
try:
    import instagram_scraper as ig_scraper
except Exception as e:
    print(f"IG import failed (OK): {e}", flush=True)
    ig_scraper = type('_',(),{
        '__getattr__':lambda s,n:lambda *a,**kw:None,
        'IG_USERNAME':'','IG_PASSWORD':'',
        'get_instaloader':lambda s=None:None,
        'login_instagram':lambda s=None,*a,**kw:False,
        'get_ig_follow_stats':lambda s=None:{'today':0,'total_ever':0,'daily_limit':60},
        'scrape_followers':lambda *a,**kw:{'followers':[],'error':'IG not available','count':0},
        'follow_users':lambda *a,**kw:{'followed':0,'failed':0,'skipped':0,'error':'IG not available'},
        'upload_ig_session':lambda *a,**kw:False,
    })()

API_ID = int(os.environ.get("API_ID", 6))
API_HASH = os.environ.get("API_HASH", "eb06d4abfb49dc3eeb1aeb98ae0f581e")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8790569799:AAFZuVDuVg62v87yQqmaQy3LS_w71-Q6yz0")
ADMIN_ID = int(os.environ.get("ADMIN_ID", 564234793))
PORT = int(os.environ.get("PORT", 10000))
CONFIG_FILE = "config.json"
SCRAPED_FILE = "scraped_users.json"
ADDER_LIMIT_FILE = "adder_limits.json"
ADDED_MEMBERS_FILE = "added_members_history.json"
ACCOUNTS_FILE = "saved_accounts.json"
MAX_ADD_PER_ACCOUNT = 50  # محدودیت اضافه کردن عضو در هر اکانت

LAST_ERROR = ""  # آخرین خطای رخ داده برای دیباگ
# Regex for detecting URLs in messages
URL_REGEX = re.compile(r"https?://[^\s<>\"')]+")
# قفل سراسری برای اتصال Client ها - حالا از attacker.py ایمپورت میشه
# _connect_lock = asyncio.Lock()  # ← از attacker import شده

def _log_err(e, where=""):
    global LAST_ERROR
    LAST_ERROR = f"[{where}] {type(e).__name__}: {str(e)[:400]}"
    print(f"❌ ERROR {where}: {LAST_ERROR}", flush=True)
    traceback.print_exc()

def _make_progress_updater(msg_ref, is_retry=False):
    stop_btn = InlineKeyboardMarkup([[InlineKeyboardButton("⏹️ توقف عملیات", callback_data="stop_op")]])
    async def updater(text):
        try:
            prefix = "🔄 تلاش مجدد\n" if is_retry else ""
            await msg_ref.edit_text(prefix + text, reply_markup=stop_btn, disable_web_page_preview=True)
        except Exception:
            pass
    return updater

app = Client("antiscraper_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, workers=1)

def _cleanup_session_locks():
    """پاک کردن فایل‌های قفل و ژورنال قدیمی Pyrogram/SQLite که از کرش قبلی مانده‌اند"""
    try:
        import glob as _g
        for pat in [
            os.path.join(SESSIONS_DIR, "*.session-journal"),
            os.path.join(SESSIONS_DIR, "*session-wal"),
            os.path.join(SESSIONS_DIR, "*session-shm"),
            os.path.join(SESSIONS_DIR, "_newtmp_*.session"),
            "antiscraper_bot.session-journal",
            "antiscraper_bot.session-wal",
            "antiscraper_bot.session-shm",
            "*.session-journal",
            "*.session-wal",
            "*.session-shm",
            "tmp_*.session",
            "tmp_*.session-journal",
        ]:
            for f in _g.glob(pat):
                try:
                    os.remove(f)
                    print(f"🧹 قفل قدیمی پاک شد: {os.path.basename(f)}", flush=True)
                except Exception:
                    pass
        # فعال کردن WAL mode روی سشن خود ربات
        _enable_wal_on_session("antiscraper_bot")
        # و روی همه سشن‌های موجود
        for f in _g.glob(os.path.join(SESSIONS_DIR, "acc_*.session")):
            base = f[:-8]  # حذف .session از آخر
            _enable_wal_on_session(base)
        # 🆕 پاکسازی WAL/SHM قفل‌شده سشن بات
        for pat in ["antiscraper_bot.session-wal", "antiscraper_bot.session-shm"]:
            if os.path.exists(pat):
                try: os.remove(pat)
                except: pass
                print(f"🧹 WAL/SHM بات پاک شد: {pat}", flush=True)
    except Exception:
        pass

# پاکسازی در لحظه ایمپورت
_cleanup_session_locks()

async def robust_connect(client, max_retries=6):
    """اتصال با تلاش مجدد. قفل داخل AdvancedScraper.connect() هست — اینجا دیگه قفل نمیگیریم"""
    for attempt in range(1, max_retries + 1):
        try:
            try:
                await client.disconnect()
            except Exception:
                pass
            await asyncio.sleep(0.3)
            try:
                sess_name = client.app.name if hasattr(client, 'app') else client.name
                _enable_wal_on_session(sess_name)
            except:
                pass
            await client.connect()
            try:
                sess_name = client.app.name if hasattr(client, 'app') else client.name
                _enable_wal_on_session(sess_name)
            except:
                pass
            return
        except Exception as e:
            msg = str(e).lower()
            if ("locked" in msg or "database" in msg) and attempt < max_retries:
                print(f"⚠️ قفل دیتابیس سشن، تلاش {attempt+1}/{max_retries}", flush=True)
                try:
                    client_name = client.app.name if hasattr(client, 'app') else client.name
                    for pat in [client_name + ".session-journal", client_name + ".session-wal", client_name + ".session-shm", "*.session-journal", "*.session-wal", "*.session-shm"]:
                        for f in _glob.glob(pat):
                            try: os.remove(f)
                            except: pass
                except Exception:
                    pass
                await asyncio.sleep(2 * attempt)
                continue
            raise

async def robust_resolve_chat(client, raw, max_attempts=8):
    """تلاش چند باره برای پیدا کردن هر نوع گروه/سوپرگروه/کانال/مگاگروه
    با چند روش مختلف تا مطمئن شویم پیدا میشه."""
    raw = str(raw).strip()
    uname = raw.replace("@", "").replace("https://t.me/", "").replace("http://t.me/", "").rstrip("/")
    is_id = raw.lstrip('-').isdigit()
    target = None
    last_err = None
    for attempt in range(1, max_attempts + 1):
        try:
            # اول کش را کاملا گرم کن با لیست کامل دیالوگ ها
            try:
                async for _ in client.app.get_dialogs(limit=2000):
                    pass
            except Exception:
                pass
            await asyncio.sleep(0.5)
            # روش ۱: مستقیم با مقدار خام
            if is_id:
                tid = int(raw)
                target = await client.app.get_chat(tid)
            else:
                target = await client.app.get_chat(uname)
            if target:
                return target
        except Exception as e:
            last_err = e
        try:
            # روش ۲: resolve_peer سپس get_chat
            try:
                if is_id:
                    peer = await client.app.resolve_peer(int(raw))
                else:
                    peer = await client.app.resolve_peer(uname)
                target = await client.app.get_chat(peer)
                if target:
                    return target
            except Exception:
                pass
            # روش ۳: گشتن در لیست دیالوگ ها
            async for d in client.app.get_dialogs(limit=2000):
                cht = d.chat
                if not cht: continue
                if is_id and cht.id == int(raw):
                    return cht
                if not is_id:
                    c_uname = (cht.username or "").lower()
                    c_title = (cht.title or "").lower()
                    if c_uname == uname.lower() or uname.lower() in c_title:
                        return cht
            # روش ۴: یک بار join_chat/export_chat_invite با لینک
            if not is_id and ("t.me/" in raw or raw.startswith("+")):
                try:
                    await client.app.join_chat(raw)
                    await asyncio.sleep(2)
                    async for d in client.app.get_dialogs(limit=200):
                        if d.chat and (d.chat.username or "").lower() == uname.lower():
                            return d.chat
                except Exception:
                    pass
            # روش ۵: get_dialogs دوباره با تاخیر
            await asyncio.sleep(2)
            try:
                async for _ in client.app.get_dialogs(limit=200):
                    pass
            except:
                pass
        except Exception as e:
            last_err = e
        await asyncio.sleep(1.5 * attempt)
    raise Exception(f"پس از {max_attempts} تلاش پیدا نشد: {last_err}")

# One-time JSON->DB migration (harmless if already done)
try:
    migrate_json_to_db()
except Exception as e:
    print(f"migration: {e}", flush=True)


def load_added_history():
    """سازگاری با نسخه قدیمی - از DB میخواند"""
    return {}  # history now in db via is_added/mark_added

def save_added_history(hist):
    pass  # no-op, db is source of truth

def mark_user_as_added(chat_id, chat_title, user_id):
    """ثبت کردن این کاربر که به این گروه اضافه شد (در DB)"""
    _db_mark_added(chat_id, user_id, "")

def is_user_already_added(chat_id, user_id):
    """چک میکند که این کاربر قبلا به این گروه اضافه شده یا نه"""
    return _db_is_added(chat_id, user_id)


def load_accounts():
    return _db_load_accounts()

def save_accounts(accs):
    """هم در فایل لوکال و هم در DB ذخیره میکند"""
    try:
        with open(ACCOUNTS_FILE, "w", encoding="utf-8") as f:
            json.dump(accs, f, ensure_ascii=False)
    except: pass
    # Sync to DB
    try:
        existing = _db_load_accounts()
        # Upsert accounts in accs
        for phone, info in accs.items():
            name = info.get("name","")
            uname = info.get("username","")
            fp = info.get("device_fp")
            if fp:
                save_account(phone, name, uname, fp)
        # (don't delete accounts that exist in DB but not in dict - user may have deleted via UI separately)
    except Exception as e:
        print(f"save_accounts sync err: {e}", flush=True)

def list_saved_accounts():
    """لیست اکانت‌های معتبر که فایل سشن شان موجود است"""
    from bg_scraper import _ensure_session
    accounts = _db_load_accounts()
    valid = {}
    os.makedirs(SESSIONS_DIR, exist_ok=True)
    for phone, info in accounts.items():
        fname = safe_phone_filename(phone)
        sfile = os.path.join(SESSIONS_DIR, f"acc_{fname}.session")
        if os.path.exists(sfile) and os.path.getsize(sfile) > 100:
            valid[phone] = info
        else:
            # try restoring from DB
            blob = db.load_session_blob(phone)
            if blob:
                with open(sfile, "wb") as f:
                    f.write(blob)
                valid[phone] = info
    return valid

def load_config():
    c = _db_get_config()
    return {"defend_group": c.get("group_id") or None, "defense_enabled": c.get("defense_enabled", True),
            "group_name": c.get("group_name",""), "owner_phone": c.get("owner_phone","")}

def save_config(cfg):
    gid = cfg.get("defend_group") or 0
    gname = cfg.get("group_name","")
    _db_set_config(gid, gname, cfg.get("defense_enabled", True), cfg.get("owner_phone",""))

def load_scraped():
    d = _db_load_users()
    users_list = list(d.values())
    c = _db_get_config()
    return users_list, c.get("group_name",""), c.get("group_id",0)

def save_scraped(users, group_name="", group_id=0):
    if isinstance(users, dict):
        users_list = list(users.values())
    else:
        users_list = users
    _db_bulk_users(users_list, group_id, group_name)
    if group_id:
        c = _db_get_config()
        _db_set_config(group_id, group_name or c.get("group_name",""), c.get("defense_enabled",True), c.get("owner_phone",""))

def load_adder_limits():
    return _db_get_limits()

def save_adder_limits(limits):
    for phone, info in limits.items():
        added = info.get("added",0) if isinstance(info, dict) else int(info or 0)
        _db_set_limit(phone, added)

config = load_config()
CURRENT_GROUP_ID = config.get("defend_group")
defender = None
if CURRENT_GROUP_ID:
    defender = AdvancedDefender(app, CURRENT_GROUP_ID, ADMIN_ID)
    defender.MIN_ACCOUNT_AGE_DAYS = 25 if config.get("defense_enabled", True) else 0
atk_state = {}
bg_started = False
hunter_bg_started = False
pf_scanning = False  # project finder progress lock

def build_welcome_text():
    """Build the rich status/welcome text shown at top of main menu."""
    saved_accs = list_saved_accounts()
    acc_count = len(saved_accs)
    users, gname, _ = load_scraped()
    total_users = len(users)
    total_added = _db_count_added()
    pf_total = count_projects()
    bg_st = get_bg_scan()
    bg_state_txt = "🟢 روشن" if bg_st.get("enabled") else "🔴 خاموش"
    bg_target_txt = gname or "—"
    def_state_txt = "🟢 فعال" if (CURRENT_GROUP_ID and defender and defender.MIN_ACCOUNT_AGE_DAYS > 0) else ("⚪ تنظیم نشده" if not CURRENT_GROUP_ID else "🔴 غیرفعال")
    owner_p = get_owner_phone()
    txt = "🛡️ <b>پنل مدیریتی ضد اسکریپت تلگرام</b>\n"
    txt += "━━━━━━━━━━━━━━━━━━\n"
    txt += f"🎯 گروه محافظت: <b>{gname if CURRENT_GROUP_ID else 'انتخاب نشده'}</b>\n"
    txt += f"🛡️ وضعیت دفاع: <b>{def_state_txt}</b>\n"
    txt += f"📱 اکانت‌های فعال: <b>{acc_count}</b>"
    if owner_p: txt += f" · 👤 مالک: <code>{owner_p}</code>"
    txt += "\n"
    txt += f"👥 ممبرهای استخراج شده: <b>{total_users:,}</b>\n"
    txt += f"✅ مجموع ادد شده‌ها: <b>{total_added:,}</b>\n"
    txt += f"⏱️ اسکن خودکار: <b>{bg_state_txt}</b>\n"
    txt += f"🔭 پروژه‌های اوپن‌سورس: <b>{pf_total:,}</b>\n"
    txt += "━━━━━━━━━━━━━━━━━━\n"
    txt += "<i>از دکمه‌های زیر بخش مورد نظر را انتخاب کنید:</i>"
    return txt


def _back_btn(target="home", text="🏠 منوی اصلی"):
    return [InlineKeyboardButton(text, callback_data=target)]

def _sub_back_btn(target="home"):
    return [InlineKeyboardButton("🔙 بازگشت", callback_data=target),
            InlineKeyboardButton("🏠 خانه", callback_data="home")]


# ═══════════════ 🆕 UI Functions: Chats Manager ═══════════════
def _progress_bar(pct):
    """نمایش نوار پیشرفت ۱۰ خانه‌ای"""
    filled = int(pct / 10)
    empty = 10 - filled
    return "🟦" * filled + "⬜" * empty

def _chat_type_icon(ct):
    return "📡" if ct == "channel" else "👥"

async def _show_chats_manager(q, category=None):
    """نمایش لیست گروه/کانال‌های اسکن شده با درصد پیشرفت"""
    chats = get_scanned_chats(category=category)
    title = f"📂 دسته‌بندی: {category}" if category else "🗂️ گروه/کانال‌های اسکن شده"
    text = f"<b>{title}</b>\n━━━━━━━━━━━━━━━━━━\n"

    if not chats:
        text += "\n⚠️ هنوز هیچ گروه/کانالی اسکن نشده.\n"
        text += "از منوی «🚀 حمله» یک گروه/کانال جدید اسکن کنید.\n"
    else:
        for i, ch in enumerate(chats[:30], 1):
            icon = _chat_type_icon(ch.get("chat_type", ""))
            pct = ch.get("progress_pct") or 0
            extracted = ch.get("extracted_count") or 0
            total = ch.get("total_members_estimate") or 0
            fav = "⭐ " if ch.get("is_favorite") else ""
            cat_tag = f" [{ch.get('category')}]" if ch.get("category") else ""
            bar = _progress_bar(pct)
            scans = ch.get("scan_count") or 1

            text += f"\n{i}. {fav}<b>{ch['chat_name'][:35]}</b> {icon}{cat_tag}\n"
            text += f"   {bar} {pct}% | {extracted:,}/{total or '?'} 👤\n"
            text += f"   🆔 <code>{ch['chat_id']}</code> · 🔄 {scans} بار اسکن\n"

    buttons = []
    # Add each chat as a selectable button (limit to 12 rows, 2 per row)
    for ch in chats[:24]:
        icon = _chat_type_icon(ch.get("chat_type", ""))
        name = ch["chat_name"][:20]
        pct = ch.get("progress_pct") or 0
        fav = "⭐" if ch.get("is_favorite") else ""
        cid = ch["chat_id"]
        buttons.append([
            InlineKeyboardButton(f"{fav}{icon} {name} ({pct}%)", callback_data=f"chat_select_{cid}"),
            InlineKeyboardButton("⚙️", callback_data=f"chat_cat_{cid}"),
        ])

    # Navigation row
    nav = []
    cats = get_all_categories()
    if not category:
        nav.append(InlineKeyboardButton("📂 دسته‌بندی‌ها", callback_data="categories_menu"))
    else:
        nav.append(InlineKeyboardButton("🔙 همه چت‌ها", callback_data="chats_manager"))
    if cats:
        for c in cats[:3]:
            if c != category:
                nav.append(InlineKeyboardButton(f"📁 {c}", callback_data=f"cat_view_{c}"))
    buttons.append(nav)
    buttons.append(_sub_back_btn())
    await q.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons), disable_web_page_preview=True)


async def _handle_chat_select(q, chat_id):
    """نمایش جزئیات یک چت و گزینه‌های عملیات"""
    ch = get_scanned_chat(chat_id)
    if not ch:
        await q.answer("چت پیدا نشد!", show_alert=True)
        return

    icon = _chat_type_icon(ch.get("chat_type", ""))
    pct = ch.get("progress_pct") or 0
    extracted = ch.get("extracted_count") or 0
    total = ch.get("total_members_estimate") or 0
    cat = ch.get("category") or "—"
    fav = ch.get("is_favorite", False)
    name = ch["chat_name"]
    ctype = "کانال" if ch.get("chat_type") == "channel" else "گروه/سوپرگروه"

    # Count users from this specific source
    source_users = count_users_by_source(source_chat_id=chat_id)

    text = f"<b>{icon} {name}</b>\n"
    text += "━━━━━━━━━━━━━━━━━━\n"
    text += f"🆔 آیدی: <code>{chat_id}</code>\n"
    text += f"📁 نوع: {ctype}\n"
    text += f"🏷️ دسته‌بندی: {cat}\n"
    text += f"📊 پیشرفت: {_progress_bar(pct)} {pct}%\n"
    text += f"👥 استخراج شده: {extracted:,} از ~{total or '?'}\n"
    text += f"📦 کل در دیتابیس: {source_users:,} کاربر\n"
    text += f"🔄 تعداد اسکن: {ch.get('scan_count', 1)} بار\n"
    text += f"⭐ علاقه‌مندی: {'بله' if fav else 'خیر'}\n"

    buttons = []
    # Row 1: Attack + Add members
    buttons.append([
        InlineKeyboardButton("🚀 اسکن مجدد", callback_data=f"attack_from_chat_{chat_id}"),
        InlineKeyboardButton("➕ ادد از این منبع", callback_data=f"source_filter_{chat_id}"),
    ])
    # Row 2: Category + Favorite
    buttons.append([
        InlineKeyboardButton("🏷️ تغییر دسته‌بندی", callback_data=f"cat_set_{chat_id}"),
        InlineKeyboardButton("⭐" if not fav else "❌⭐", callback_data=f"chat_fav_{chat_id}"),
    ])
    # Row 3: AI Analyze + View users
    buttons.append([
        InlineKeyboardButton("🔍 تحلیل هوشمند موضوع", callback_data=f"ai_analyze_{chat_id}"),
        InlineKeyboardButton(f"👥 کاربران ({source_users})", callback_data=f"show_list_source_{chat_id}"),
    ])
    # Row 4: Delete
    buttons.append([
        InlineKeyboardButton("🗑️ حذف از تاریخچه", callback_data=f"chat_del_{chat_id}"),
    ])
    buttons.append(_sub_back_btn(target="chats_manager"))
    await q.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons), disable_web_page_preview=True)


async def _start_attack_from_chat(q, chat_id):
    """شروع حمله روی یک چت از قبل اسکن شده"""
    ch = get_scanned_chat(chat_id)
    if not ch:
        await q.answer("چت پیدا نشد!", show_alert=True)
        return
    atk_state["target_chat_id"] = chat_id
    atk_state["target_chat_name"] = ch["chat_name"]
    await q.message.edit_text(
        f"🎯 هدف: <b>{ch['chat_name']}</b> ({chat_id})\n"
        f"📊 پیشرفت قبلی: {ch.get('progress_pct') or 0}%\n\n"
        "یک اکانت برای حمله انتخاب کنید:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀 حمله تک‌اکانت", callback_data="pick_account_attack")],
            [InlineKeyboardButton("⚡ حمله موازی", callback_data="par_pick_target_attack")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data=f"chat_select_{chat_id}")],
        ])
    )


async def _handle_chat_category_prompt(q, chat_id):
    """نمایش پرامپت انتخاب دسته‌بندی"""
    ch = get_scanned_chat(chat_id)
    if not ch:
        await q.answer("چت پیدا نشد!", show_alert=True)
        return

    existing_cats = get_all_categories()
    text = f"🏷️ تغییر دسته‌بندی <b>{ch['chat_name']}</b>\n"
    text += f"دسته فعلی: <b>{ch.get('category') or '—'}</b>\n\n"
    text += "یک دسته انتخاب کنید یا دسته جدید تایپ کنید:"

    buttons = []
    # Show existing categories
    for cat in existing_cats[:8]:
        label = f"✅ {cat}" if cat == ch.get("category") else cat
        buttons.append([InlineKeyboardButton(label, callback_data=f"cat_apply_{chat_id}_{cat}")])

    # Remove category option
    if ch.get("category"):
        buttons.append([InlineKeyboardButton("❌ حذف دسته‌بندی", callback_data=f"cat_apply_{chat_id}_none")])

    # Common predefined categories
    predefined = ["گیمینگ", "آشپزی", "تکنولوژی", "کریپتو", "فیلم", "موسیقی", "ورزشی", "آموزشی", "فروشگاهی"]
    row = []
    for cat in predefined:
        if cat not in existing_cats:
            row.append(InlineKeyboardButton(cat, callback_data=f"cat_apply_{chat_id}_{cat}"))
            if len(row) == 3:
                buttons.append(row)
                row = []
    if row:
        buttons.append(row)

    buttons.append(_sub_back_btn(target=f"chat_select_{chat_id}"))
    await q.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons), disable_web_page_preview=True)


async def _handle_ai_analyze(q, chat_id):
    """تحلیل هوشمند موضوع چت با کیورد + AI"""
    from chat_analyzer import smart_analyze
    ch = get_scanned_chat(chat_id)
    if not ch:
        await q.answer("چت پیدا نشد!", show_alert=True)
        return

    await q.answer("🔍 در حال تحلیل موضوع چت...", show_alert=False)
    status = await q.message.reply_text(f"🔍 در حال تحلیل هوشمند موضوع:\n<b>{ch['chat_name']}</b>\n\n⏳ صبر کنید...")

    # Get chat details from Telegram for better analysis
    desc = ""
    title = ch["chat_name"]
    try:
        from pyrogram import Client as _C
        tmp = _C("ana_tmp", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, in_memory=True)
        await tmp.start()
        try:
            full_chat = await tmp.get_chat(chat_id)
            desc = getattr(full_chat, 'description', '') or ''
            title = full_chat.title or title
        except:
            pass
        await tmp.stop()
    except:
        pass

    # Run analysis (keyword first, AI fallback)
    result = smart_analyze(title, desc)

    if result.get("category"):
        update_chat_category(chat_id, result["category"])
        method_emoji = {"keyword": "⚡", "keyword_low_confidence": "⚡⚠️", "groq": "🤖", "openrouter": "🤖", "huggingface": "🤖"}.get(result["method"], "🔍")
        matched = ", ".join(result.get("matched_keywords", [])[:5]) or "—"
        text = f"✅ تحلیل هوشمند کامل شد!\n\n"
        text += f"📁 <b>نام چت:</b> {title[:50]}\n"
        text += f"🏷️ <b>دسته تشخیص داده شده:</b> {result.get('icon', '📁')} {result['category']}\n"
        text += f"{method_emoji} <b>روش:</b> {result['method']}\n"
        text += f"📊 <b>اطمینان:</b> {result['confidence']}%\n"
        if matched != "—":
            text += f"🔑 <b>کیوردها:</b> {matched}\n"
        if result.get("reason"):
            text += f"💡 <b>توضیح:</b> {result['reason'][:200]}\n"
    else:
        text = f"⚠️ نتونستم موضوع چت رو تشخیص بدم.\n"
        text += f"لطفاً دستی از منوی «🏷️ تغییر دسته‌بندی» انتخاب کن.\n"

    await status.edit_text(text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📂 بازگشت به جزئیات چت", callback_data=f"chat_select_{chat_id}")],
            [InlineKeyboardButton("🏠 منوی اصلی", callback_data="home")],
        ]), disable_web_page_preview=True)


async def _show_categories_menu(q):
    """نمایش آمار دسته‌بندی‌ها"""
    stats = get_category_stats()
    cats = get_all_categories()
    total_chats = len(get_scanned_chats())

    text = "📂 <b>دسته‌بندی چت‌ها</b>\n━━━━━━━━━━━━━━━━━━\n"
    text += f"📊 مجموع چت‌ها: {total_chats}\n"
    text += f"🏷️ دسته‌بندی‌ها: {len(cats)}\n\n"

    if stats:
        for s in stats[:15]:
            text += f"📁 <b>{s['category']}</b>: {s['chat_count']} چت · {s['total_users']:,} کاربر\n"
    else:
        text += "⚠️ هنوز دسته‌بندی ایجاد نشده.\nاز منوی مدیریت چت‌ها، دسته‌بندی تعیین کنید.\n"

    buttons = []
    # Show each category as button
    for c in cats[:12]:
        buttons.append([InlineKeyboardButton(f"📁 {c}", callback_data=f"cat_view_{c}")])

    buttons.append(_sub_back_btn())
    await q.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons), disable_web_page_preview=True)


async def _show_source_filter_menu(q):
    """منوی فیلتر منبع برای ادد ممبر"""
    chats = get_scanned_chats()
    cats = get_all_categories()

    text = "🎯 <b>فیلتر کاربران بر اساس منبع</b>\n"
    text += "━━━━━━━━━━━━━━━━━━\n"
    text += "انتخاب کنید کاربران استخراج شده از کدام منبع اضافه شوند:\n"

    buttons = []
    # All users
    buttons.append([InlineKeyboardButton("🌐 همه کاربران", callback_data="source_filter_all")])

    # By category
    if cats:
        text += "\n📂 <b>بر اساس دسته‌بندی:</b>\n"
        for c in cats[:8]:
            cnt = count_users_by_source(category=c)
            if cnt > 0:
                buttons.append([InlineKeyboardButton(f"📁 {c} ({cnt:,})", callback_data=f"source_filter_cat_{c}")])

    # By specific chat (favorites first, then recent)
    if chats:
        text += "\n👥 <b>بر اساس چت:</b>\n"
        for ch in chats[:10]:
            icon = _chat_type_icon(ch.get("chat_type", ""))
            cnt = count_users_by_source(source_chat_id=ch["chat_id"])
            if cnt > 0:
                name = ch["chat_name"][:25]
                buttons.append([InlineKeyboardButton(
                    f"{icon} {name} ({cnt:,})",
                    callback_data=f"source_filter_{ch['chat_id']}"
                )])

    buttons.append(_sub_back_btn())
    await q.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons), disable_web_page_preview=True)



# ═══════════════ 📸 Instagram UI ═══════════════
async def _start_ig_follow_do(q, source):
    """Actually start the follow process (after confirmation)"""
    from db import get_scanned_chats, get_conn
    from db.psycopg2.extras import DictCursor
    chats = get_scanned_chats()
    source_chat = None
    for c in chats:
        if c.get("chat_type") == "instagram" and c["chat_name"].replace("IG:@", "") == source:
            source_chat = c
            break
    if not source_chat:
        await q.answer("source not found!", show_alert=True)
        return

    users = []
    try:
        cur = get_conn().cursor(cursor_factory=DictCursor)
        cur.execute("SELECT username FROM scraped_users WHERE source_group_id = %s", (source_chat["chat_id"],))
        for r in cur.fetchall():
            uname = (r.get("username") or "").strip().lower()
            if uname and uname not in users:
                users.append(uname)
        cur.close()
    except:
        users = []

    stats = ig_scraper.get_ig_follow_stats()
    daily_left = min(40, stats["daily_limit"] - stats["today"])

    if daily_left <= 0:
        await q.answer(f'Daily limit reached! ({stats["today"]}/{stats["daily_limit"]})', show_alert=True)
        return

    prog = await q.message.edit_text(
        f"📸 در حال Follow از @{source}...\n"
        f"🎯 هدف: {min(daily_left, len(users))} نفر\n"
        f"⏱️ با تاخیر ۴۰-۱۲۰ ثانیه..."
    )

    async def run_follow():
        import random as _rnd
        _rnd.shuffle(users)
        stop = [0]

        def progress_cb(f, fail, username, status):
            pass

        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None,
            lambda: ig_scraper.follow_users(
                users[:daily_left], max_follows=daily_left,
                progress_cb=progress_cb, stop_flag=stop
            )
        )

        text = f"📸 <b>Follow از @{source} تمام شد!</b>\n━━━━━━━━━━━━━━━━━━\n"
        text += f"✅ دنبال شده: <b>{result['followed']}</b>\n"
        text += f"❌ خطا: <b>{result['failed']}</b>\n"
        text += f"⏭️ رد شده: <b>{result['skipped']}</b>\n"
        if result.get("error"):
            text += f"\n⚠️ {result['error']}\n"
        new_stats = ig_scraper.get_ig_follow_stats()
        text += f"\n📊 امروز: {new_stats['today']}/{new_stats['daily_limit']}"

        try:
            await prog.edit_text(text, reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📊 آمار follow", callback_data="ig_follow_stats")],
                [InlineKeyboardButton("🔙 منوی follow", callback_data="ig_follow_menu")],
            ]), disable_web_page_preview=True)
        except: pass

    asyncio.create_task(run_follow())
    return


async def _show_ig_follow_menu(q):
    """Show follow menu with source selection"""
    from db import get_scanned_chats, count_users_by_source
    ig_chats = [c for c in get_scanned_chats() if c.get("chat_type") == "instagram"]

    stats = ig_scraper.get_ig_follow_stats()
    daily_left = stats["daily_limit"] - stats["today"]

    text = f"📸 <b>Follow در اینستاگرام</b>\n━━━━━━━━━━━━━━━━━━\n"
    text += f"🕐 امروز: <b>{stats['today']}/{stats['daily_limit']}</b>\n"
    text += f"📦 باقیمانده: <b>{daily_left}</b>\n"
    text += f"📊 کل تاریخچه: <b>{stats['total_ever']:,}</b>\n"
    text += "\n⚠️ <b>نکات ایمنی:</b>\n"
    text += "• تاخیر ۴۰-۱۲۰ ثانیه بین هر follow\n"
    text += "• رفتار شبه{انسانی} (بازدید پروفایل)\n"
    text += "• توقف خودکار در action block\n"
    text += "• سقف روزانه: ۶۰ تا\n\n"
    text += "<b>منبع کاربران برای follow:</b>\n"

    if not ig_chats:
        text += "\n⚠️ هنوز هیچ پیجی اسکرپ نشده!"
        buttons = [[InlineKeyboardButton("🔙 بازگشت", callback_data="ig_menu")]]
    else:
        buttons = []
        for ch in ig_chats[:10]:
            cnt = count_users_by_source(source_chat_id=ch["chat_id"])
            name = ch["chat_name"].replace("IG:@", "")
            if cnt > 0:
                buttons.append([InlineKeyboardButton(
                    f"👤 @{name} ({cnt:,})",
                    callback_data=f"ig_follow_start_{name}"
                )])
        buttons.append([InlineKeyboardButton("📊 آمار follow", callback_data="ig_follow_stats")])
        buttons.append(_sub_back_btn(target="ig_menu"))

    await q.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons), disable_web_page_preview=True)


async def _show_ig_follow_stats(q):
    """Show follow statistics"""
    from db import kv_get
    stats = ig_scraper.get_ig_follow_stats()
    followed = kv_get("ig_followed_usernames", []) or []

    text = f"📊 <b>آمار Follow اینستاگرام</b>\n━━━━━━━━━━━━━━━━━━\n"
    text += f"🕐 امروز: <b>{stats['today']}/{stats['daily_limit']}</b>\n"
    text += f"📦 کل تاریخچه: <b>{stats['total_ever']:,}</b>\n\n"

    if followed:
        text += f"👤 <b>آخرین follow شده{ها}:</b>\n"
        for u in followed[-20:]:
            text += f"✅ @{u}\n"
    else:
        text += "هنوز کسی follow نشده ✨"

    buttons = [_sub_back_btn(target="ig_follow_menu")]
    await q.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons), disable_web_page_preview=True)


async def _start_ig_follow(q, source_username):
    """Show confirmation before starting follow"""
    from db import get_scanned_chats, get_conn
    from db.psycopg2.extras import DictCursor

    chats = get_scanned_chats()
    source_chat = None
    for c in chats:
        if c.get("chat_type") == "instagram" and c["chat_name"].replace("IG:@", "") == source_username:
            source_chat = c
            break

    if not source_chat:
        await q.answer("source not found!", show_alert=True)
        return

    users = []
    try:
        cur = get_conn().cursor(cursor_factory=DictCursor)
        cur.execute("SELECT username FROM scraped_users WHERE source_group_id = %s", (source_chat["chat_id"],))
        for r in cur.fetchall():
            uname = (r.get("username") or "").strip().lower()
            if uname and uname not in users:
                users.append(uname)
        cur.close()
    except:
        users = []

    if not users:
        await q.answer("no users found!", show_alert=True)
        return

    import random as _rnd
    _rnd.shuffle(users)

    stats = ig_scraper.get_ig_follow_stats()
    daily_left = stats["daily_limit"] - stats["today"]

    text = f"📸 <b>شروع Follow از @{source_username}</b>\n\n"
    text += f"👤 کاربران موجود: <b>{len(users):,}</b>\n"
    text += f"🕐 ظرفیت امروز: <b>{daily_left}</b>\n"
    text += f"⏱️ زمان تخمینی: ~{daily_left * 1.5:.0f} دقیقه\n\n"
    text += "آماده{ای}؟"

    await q.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(f"▶️ شروع ({min(daily_left, 40)} نفر)", callback_data=f"ig_follow_do_{source_username}")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="ig_follow_menu")],
        ]),
        disable_web_page_preview=True)


async def _show_ig_menu(q):
    """Show Instagram scraping menu"""
    text = "📸 <b>اسکرپر اینستاگرام</b>\n━━━━━━━━━━━━━━━━━━\n"
    text += "🔹 استخراج فالوورهای پیج‌های <b>عمومی</b>\n"
    text += "🔹 ذخیره در دیتابیس مشترک با تلگرام\n"
    text += "🔹 فیلتر و دسته‌بندی مثل تلگرام\n\n"
    
    # Check login status
    logged_in = False
    try:
        L = ig_scraper.get_instaloader()
        L.test_login()
        logged_in = True
    except:
        pass
    
    if logged_in:
        text += "🟢 <b>وضعیت:</b> به اینستاگرام متصلی\n"
        text += f"👤 اکانت: <code>{ig_scraper.IG_USERNAME or '?'}</code>\n"
    else:
        text += "🔴 <b>وضعیت:</b> هنوز لاگین نشدی\n"
    
    text += "\n⚠️ <b>محدودیت‌ها:</b>\n"
    text += "• سرعت: ~۲۰۰ فالوور در ساعت\n"
    text += "• فقط پیج‌های عمومی\n"
    text += "• ریسک Shadow ban در صورت استفاده سنگین\n"
    
    buttons = []
    if logged_in:
        buttons.append([InlineKeyboardButton("🔍 اسکرپ فالوورهای یک پیج", callback_data="ig_scrape_prompt")])
        buttons.append([InlineKeyboardButton("📋 نتایج اسکرپ", callback_data="ig_list")])
        buttons.append([InlineKeyboardButton("➕ Follow اسکرپ‌شده‌ها", callback_data="ig_follow_menu")])
        buttons.append([InlineKeyboardButton("🚪 خروج از اکانت", callback_data="ig_logout")])
    else:
        buttons.append([InlineKeyboardButton("🔐 تنظیم لاگین", callback_data="ig_login")])
        buttons.append([InlineKeyboardButton("📥 آپلود سشن (2FA)", callback_data="ig_upload_session")])
    
    buttons.append(_sub_back_btn())
    await q.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons), disable_web_page_preview=True)


async def _handle_ig_login(q):
    """Prompt for Instagram login credentials"""
    atk_state["step"] = "ig_login_username"
    await q.message.edit_text(
        "🔐 <b>لاگین اینستاگرام</b>\n\n"
        "⚠️ نکته مهم: اینستاگرام لاگین‌های متعدد رو تشخیص میده.\n"
        "پیشنهاد میشه به جای وارد کردن پسورد، از روش «📥 آپلود سشن» استفاده کنی.\n\n"
        "اگر می‌خوای ادامه بدی، اول <b>نام کاربری اینستاگرام</b> رو بفرست:",
        reply_markup=InlineKeyboardMarkup([[_sub_back_btn(target="ig_menu")[0]]]))


async def _start_ig_scrape(q, target):
    """Start Instagram follower scraping"""
    try:
        L = ig_scraper.get_instaloader()
        L.test_login()
    except:
        await q.answer("❌ اول باید لاگین کنی! از منوی اینستاگرام لاگین کن.", show_alert=True)
        return
    
    prog = await q.message.edit_text(f"📸 در حال اسکرپ فالوورهای @{target}...\n⏳ این کار ممکنه چند دقیقه طول بکشه...")
    
    async def run_ig():
        stop = [0]
        found = 0
        try:
            loop = asyncio.get_running_loop()
            def progress_cb(cnt, total, name):
                nonlocal found
                found = cnt
            result = await loop.run_in_executor(
                None, 
                lambda: ig_scraper.scrape_followers(target, max_followers=300, progress_cb=progress_cb, stop_flag=stop)
            )
            if result.get("error"):
                await prog.edit_text(
                    f"❌ خطا در اسکرپ اینستاگرام:\n{result['error'][:300]}\n\n"
                    f"👤 استخراج شده تا اینجا: {result['count']:,}",
                    reply_markup=InlineKeyboardMarkup([[_sub_back_btn(target="ig_menu")[0]]]))
            else:
                await prog.edit_text(
                    f"✅ اسکرپ @{target} تمام شد!\n\n"
                    f"👤 فالوور استخراج شده: <b>{result['count']:,}</b>\n"
                    f"💾 در دیتابیس ذخیره شد\n\n"
                    f"از «📋 نتایج قبلی» یا «🗂️ مدیریت چت‌ها» ببین.",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("📋 مشاهده نتایج", callback_data="ig_list")],
                        [_sub_back_btn(target="ig_menu")[0]]
                    ]))
        except Exception as e:
            await prog.edit_text(f"❌ خطا: {str(e)[:300]}", reply_markup=InlineKeyboardMarkup([[_sub_back_btn(target="ig_menu")[0]]]))
    
    asyncio.create_task(run_ig())


async def _show_ig_results(q):
    """Show previously scraped Instagram accounts"""
    from db import get_scanned_chats
    ig_chats = [c for c in get_scanned_chats() if c.get("chat_type") == "instagram"]
    
    text = "📸 <b>نتایج اسکرپ اینستاگرام</b>\n━━━━━━━━━━━━━━━━━━\n\n"
    if not ig_chats:
        text += "هنوز هیچ پیج اینستاگرامی اسکرپ نشده."
    else:
        for ch in ig_chats[:15]:
            pct = ch.get("progress_pct") or 0
            extracted = ch.get("extracted_count") or 0
            total = ch.get("total_members_estimate") or "?"
            text += f"📸 <b>{ch['chat_name']}</b>\n"
            text += f"   👤 {extracted:,}/{total} | {pct}%\n"
            text += f"   🕐 آخرین: {time.strftime('%Y-%m-%d', time.localtime(ch.get('last_scan',0))) if ch.get('last_scan') else '—'}\n\n"
    
    buttons = []
    if ig_chats:
        for ch in ig_chats[:10]:
            buttons.append([InlineKeyboardButton(
                f"🔍 اسکن مجدد {ch['chat_name']}",
                callback_data=f"ig_scrape_{ch['chat_name'].replace('IG:@', '')}"
            )])
    
    buttons.append(_sub_back_btn(target="ig_menu"))
    await q.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons), disable_web_page_preview=True)


# ═══════════════ End of UI Functions ═══════════════

# ═══════════════ ➕ Direct Add from Database ═══════════════
async def _start_direct_add(q, target_gid):
    """Start adding members directly from database with live progress"""
    add_client = atk_state.get("add_client")
    phone = atk_state.get("phone", "")
    already_added = atk_state.get("already_added", 0)
    remaining = MAX_ADD_PER_ACCOUNT - already_added
    
    if remaining <= 0:
        await q.answer("ظرفیت این اکانت پر شده!", show_alert=True)
        return
    
    # Get users from DB based on source filter
    source = atk_state.get("add_source", "all")
    source_id = atk_state.get("add_source_id")
    
    if source == "category":
        user_records = get_users_by_source(category=source_id, limit=remaining)
        total_avail = count_users_by_source(category=source_id)
        src_label = f"دسته {source_id}"
    elif source == "chat":
        user_records = get_users_by_source(source_chat_id=source_id, limit=remaining)
        total_avail = count_users_by_source(source_chat_id=source_id)
        ch = get_scanned_chat(source_id)
        src_label = ch["chat_name"] if ch else f"چت {source_id}"
    else:
        user_records = get_users_by_source(limit=remaining)
        total_avail = _db_count_users()
        src_label = "همه کاربران"
    
    # Filter out already-added users
    uid_list = []
    for u in user_records:
        uid = int(u.get("user_id", 0) or 0)
        if uid and not is_user_already_added(target_gid, uid):
            uid_list.append(uid)
    
    if not uid_list:
        await q.answer("همه کاربران قبلاً اضافه شدن!", show_alert=True)
        return
    
    total = min(len(uid_list), remaining)
    
    # Get target name
    try:
        tgt = await add_client.app.get_chat(target_gid)
        target_name = tgt.title
    except:
        target_name = atk_state.get("target_add_name", f"گروه {target_gid}")
    
    prog = await q.message.edit_text(
        f"➕ <b>ادد مستقیم از دیتابیس</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📂 منبع: {src_label}\n"
        f"🎯 مقصد: {target_name}\n"
        f"👤 اکانت: <code>{phone}</code>\n"
        f"📊 ظرفیت: {already_added}/{MAX_ADD_PER_ACCOUNT}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🎯 آماده ادد: <b>{total}</b> نفر\n"
        f"⏱️ زمان تخمینی: ~{total * 12 // 60} دقیقه\n\n"
        f"آماده‌ای؟",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(f"▶️ شروع ادد ({total} نفر)", callback_data=f"dir_add_go_{target_gid}")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data=f"add_target_{target_gid}")],
        ]),
        disable_web_page_preview=True)


async def _execute_direct_add(q, target_gid):
    """Execute the add operation with live progress tracking"""
    add_client = atk_state.get("add_client")
    phone = atk_state.get("phone", "")
    already_added = atk_state.get("already_added", 0)
    remaining = MAX_ADD_PER_ACCOUNT - already_added
    
    source = atk_state.get("add_source", "all")
    source_id = atk_state.get("add_source_id")
    
    if source == "category":
        user_records = get_users_by_source(category=source_id, limit=remaining)
    elif source == "chat":
        user_records = get_users_by_source(source_chat_id=source_id, limit=remaining)
    else:
        user_records = get_users_by_source(limit=remaining)
    
    uid_list = []
    for u in user_records:
        uid = int(u.get("user_id", 0) or 0)
        if uid and not is_user_already_added(target_gid, uid):
            uid_list.append(uid)
    
    uid_list = uid_list[:remaining]
    total = len(uid_list)
    
    if total == 0:
        await q.answer("کاربری برای ادد نیست!", show_alert=True)
        return
    
    # Get target name
    try:
        tgt = await add_client.app.get_chat(target_gid)
        target_name = tgt.title
    except:
        target_name = atk_state.get("target_add_name", f"Chat {target_gid}")
    
    prog_msg = q.message
    added = 0; failed = 0; skipped = 0
    errors_detail = {"flood": 0, "privacy": 0, "already": 0, "banned": 0, "other": 0, "no_add": 0}
    stop_req = [False]
    
    # Save adder state for stop/resume
    atk_state["add_in_progress"] = True
    atk_state["add_progress"] = {"added": 0, "failed": 0, "total": total, "phone": phone}
    
    # Build progress update function
    from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    
    async def update_progress():
        pct = int((added + failed + skipped) * 100 / total) if total > 0 else 0
        filled = pct // 5
        empty = 20 - filled
        bar = "🟩" * filled + "⬜" * empty
        elapsed = int(time.time() - start_t)
        mins = elapsed // 60; secs = elapsed % 60
        speed = int(added / (elapsed / 60)) if elapsed > 30 else 0
        eta = int((total - added - failed - skipped) * 12 / 60) if speed > 0 else 0
        
        text = f"➕ <b>ادد مستقیم — {target_name}</b>\n"
        text += f"━━━━━━━━━━━━━━━━━━\n"
        text += f"{bar} {pct}%\n"
        text += f"━━━━━━━━━━━━━━━━━━\n"
        text += f"👤 اکانت: <code>{phone}</code>\n"
        text += f"✅ ادد شده: <b>{added}</b>\n"
        text += f"❌ ناموفق: <b>{failed}</b>\n"
        text += f"⏭️ رد شده: <b>{skipped}</b>\n"
        text += f"📊 پیشرفت: {added+failed+skipped}/{total}\n"
        text += f"⏱️ زمان: {mins:02d}:{secs:02d} · ⚡ ~{speed} در دقیقه\n"
        if eta > 0:
            text += f"🕐 اتمام: ~{eta} دقیقه\n"
        text += f"━━━━━━━━━━━━━━━━━━\n"
        text += f"🛑 دکمه توقف برای لغو عملیات"
        
        try:
            await prog_msg.edit_text(
                text,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("⏹️ توقف", callback_data="stop_op")],
                    [InlineKeyboardButton("🏠 خانه", callback_data="home")]
                ]),
                disable_web_page_preview=True)
        except: pass
    
    start_t = time.time()
    await update_progress()
    
    for i, uid in enumerate(uid_list):
        if stop_req[0]:
            skipped = total - added - failed
            break
        
        try:
            await add_client.app.add_chat_members(target_gid, uid)
            added += 1
            mark_user_as_added(target_gid, target_name, uid)
            
            # Update account limits
            limits = load_adder_limits()
            limits[phone] = {"added": already_added + added, "last_used": int(time.time())}
            save_adder_limits(limits)
            
            # Update progress in state
            atk_state["add_progress"] = {"added": added, "failed": failed, "total": total, "phone": phone}
            
            await asyncio.sleep(random.randint(8, 15))
        except FloodWait as fw:
            failed += 1
            errors_detail["flood"] += 1
            await asyncio.sleep(fw.value + 5)
        except Exception as e:
            failed += 1
            err_str = str(e).lower()
            if "privacy" in err_str or "private" in err_str or "user_privacy_restricted" in err_str.replace("_",""):
                errors_detail["privacy"] += 1
            elif "already" in err_str or "participant" in err_str:
                errors_detail["already"] += 1
                mark_user_as_added(target_gid, target_name, uid)
            elif "banned" in err_str or "kick" in err_str:
                errors_detail["banned"] += 1
            elif "not_mutual_contact" in err_str.replace("_","") or "not mutual" in err_str:
                errors_detail["no_add"] += 1
            else:
                errors_detail["other"] += 1
            await asyncio.sleep(random.randint(3, 8))
        
        if (added + failed) % 3 == 0:
            await update_progress()
    
    # Final update
    elapsed = int(time.time() - start_t)
    mins = elapsed // 60; secs = elapsed % 60
    
    text = f"✅ <b>ادد تمام شد!</b> — {target_name}\n"
    text += f"━━━━━━━━━━━━━━━━━━\n"
    text += f"✅ ادد شده: <b>{added}</b>\n"
    text += f"❌ ناموفق: <b>{failed}</b>\n"
    text += f"⏭️ رد شده: <b>{skipped}</b>\n"
    text += f"⏱️ زمان: {mins:02d}:{secs:02d}\n"
    text += f"📊 مجموع با این اکانت: {already_added + added}/{MAX_ADD_PER_ACCOUNT}\n"
    if failed > 0:
        text += f"━━━━━━━━━━━━━━━━━━\n"
        text += f"🔍 <b>دلایل خطا:</b>\n"
        if errors_detail["privacy"]: text += f"🔒 Privacy: {errors_detail['privacy']}\n"
        if errors_detail["no_add"]: text += f"🚫 تنظیمات ادد بسته: {errors_detail['no_add']}\n"
        if errors_detail["flood"]: text += f"⏱️ Flood: {errors_detail['flood']}\n"
        if errors_detail["already"]: text += f"👥 Already in chat: {errors_detail['already']}\n"
        if errors_detail["banned"]: text += f"🚫 Banned: {errors_detail['banned']}\n"
        if errors_detail["other"]: text += f"❓ Other: {errors_detail['other']}\n"
    
    atk_state["add_in_progress"] = False
    atk_state["add_progress"] = {"added": added, "failed": failed, "total": total, "phone": phone}
    
    try:
        await prog_msg.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📊 آمار اکانت‌ها", callback_data="adder_stats")],
                [InlineKeyboardButton("🏠 منوی اصلی", callback_data="home")],
            ]),
            disable_web_page_preview=True)
    except: pass


# ═══════════════ 📥 Session file upload helper (bypass 2FA) ═══════════════
async def _save_uploaded_session(st, phone, session_bytes, orig_fname):
    """Save an uploaded .session file and register the account"""
    import random as _r
    fname = safe_phone_filename(phone)
    dest = os.path.join(SESSIONS_DIR, f"acc_{fname}.session")
    os.makedirs(SESSIONS_DIR, exist_ok=True)
    try:
        with open(dest, "wb") as f:
            f.write(session_bytes)
        # Enable WAL on the new session
        _enable_wal_on_session(os.path.join(SESSIONS_DIR, f"acc_{fname}"))
    except Exception as e:
        return f"❌ خطا در ذخیره فایل: {e}"

    # Try to connect and verify
    fp = random.choice(DEVICE_FP)
    try:
        sc = AdvancedScraper("", API_ID, API_HASH, phone=phone, device_fp=fp)
        await sc.connect()
        me = await sc.app.get_me()
        # Success! Save account
        accs = load_accounts()
        accs[phone] = {
            "name": f"{me.first_name or ''} {me.last_name or ''}".strip(),
            "user_id": me.id,
            "username": me.username or "",
            "added_at": int(time.time()),
            "device_fp": fp
        }
        save_accounts(accs)
        try: _backup_session(phone)
        except: pass
        try: await sc.disconnect()
        except: pass
        return (
            f"✅ <b>اکانت با موفقیت اضافه شد!</b>\n\n"
            f"👤 {me.first_name} {me.last_name or ''}\n"
            f"📱 <code>{phone}</code>\n"
            f"🔐 سشن از فایل <code>{orig_fname}</code> بارگذاری شد\n"
            f"💾 در دیتابیس ابری هم ذخیره شد\n\n"
            f"✅ دیگه نیازی به کد و 2FA نداری!"
        )
    except FloodWait as fw:
        try: await sc.disconnect()
        except: pass
        return f"⚠️ اکانت در حالت محدودیت موقت (FloodWait {fw.value}s) - فایل ذخیره شد، بعداً امتحان کن"
    except SessionPasswordNeeded:
        try: await sc.disconnect()
        except: pass
        return (
            f"⚠️ فایل سشن ذخیره شد ولی هنوز نیاز به 2FA داره!\n"
            f"ظاهراً موقع ساخت سشن، 2FA رو وارد نکردی.\n"
            f"دوباره با اسکریپت Pyrogram لاگین کن و <b>حتماً 2FA رو هم وارد کن</b>، بعد فایل جدید رو آپلود کن."
        )
    except Exception as e:
        try: await sc.disconnect()
        except: pass
        return f"❌ خطا در تایید سشن: {str(e)[:200]}\n\nفایل سشن معتبر نیست یا منقضی شده. دوباره با Pyrogram لاگین کن."




# ═══════════════ 🚀 Fast dialog loader (no per-chat API calls) ═══════════════
async def _fast_load_chats(client, chat_types=None):
    """Quickly load all chats from dialogs WITHOUT calling get_chat_member for each.
    Returns list of (title, id, member_count, chat_type_str)."""
    chats = []
    try:
        async for dialog in client.app.get_dialogs(limit=2000):
            cht = dialog.chat
            if not cht:
                continue
            cht_type = str(cht.type).lower() if hasattr(cht, 'type') else ''
            is_group = 'group' in cht_type or 'supergroup' in cht_type
            is_channel = 'channel' in cht_type
            if not (is_group or is_channel):
                continue
            cnt = getattr(cht, 'members_count', 0) or 0
            cht_type_str = "channel" if (is_channel and not ('group' in cht_type or 'supergroup' in cht_type)) else "group"
            chats.append((cht.title or f"Chat {cht.id}", cht.id, cnt, cht_type_str))
            if len(chats) % 50 == 0:
                await asyncio.sleep(0.01)
    except Exception as e:
        print(f"_fast_load_chats err: {e}", flush=True)
    return chats


def main_menu():
    """Main dashboard with two-column modern layout + categories."""
    saved_accs = list_saved_accounts()
    acc_count = len(saved_accs)
    total_added = _db_count_added()
    pf_total = count_projects()
    bg_st = get_bg_scan()
    bg_icon = "🟢" if bg_st.get("enabled") else "🔴"
    banned = len(defender.banned_scrapers) if defender else 0

    buttons = []

    # ===== دسته ۱: داشبورد و دفاع =====
    buttons.append([
        InlineKeyboardButton("🛡️ پنل دفاع و گروه", callback_data="menu_defense"),
        InlineKeyboardButton("📊 آمار کلی", callback_data="menu_stats"),
    ])
    # ===== دسته 1.5: مدیریت چت‌ها و دسته‌بندی =====
    buttons.append([
        InlineKeyboardButton("🗂️ مدیریت چت‌ها", callback_data="chats_manager"),
        InlineKeyboardButton("📂 دسته‌بندی‌ها", callback_data="categories_menu"),
    ])

    # ===== دسته ۲: حمله/اسکرپ =====
    if acc_count >= 1:
        row = [InlineKeyboardButton("🚀 حمله تک‌اکانت", callback_data="pick_account_attack")]
        if acc_count >= 2:
            row.append(InlineKeyboardButton(f"⚡ حمله موازی ({acc_count})", callback_data="par_pick_target_attack"))
        else:
            row.append(InlineKeyboardButton("➕ اکانت جدید", callback_data="add_new_account_start"))
        buttons.append(row)
    else:
        buttons.append([InlineKeyboardButton("🆕 افزودن اولین اکانت تلگرام", callback_data="add_new_account_start")])

    # ===== دسته ۳: اضافه کردن اعضا =====
    if acc_count >= 1:
        row = [InlineKeyboardButton("➕ ادد تک‌اکانت", callback_data="pick_account_add")]
        if acc_count >= 2:
            row.append(InlineKeyboardButton(f"⚡ ادد موازی ({acc_count})", callback_data="par_pick_target_add"))
        buttons.append(row)

    # ===== دسته ۴: لیست‌ها و داده =====
    buttons.append([
        InlineKeyboardButton(f"👥 لیست ممبرها ({total_added if False else _db_count_users()})", callback_data="show_list_0"),
        InlineKeyboardButton("📈 آمار ادد", callback_data="adder_stats"),
    ])
    buttons.append([
        InlineKeyboardButton(f"✅ تاریخچه اددها ({total_added})", callback_data="added_history_menu"),
        InlineKeyboardButton(f"🚫 لیست بن‌شده‌ها ({banned})", callback_data="banned_list"),
    ])

    # ===== دسته ۵: اسکن خودکار و پروژه‌یاب =====
    buttons.append([
        InlineKeyboardButton(f"{bg_icon} ⏱️ اسکن خودکار", callback_data="bg_menu"),
        InlineKeyboardButton(f"🔭 پروژه‌یاب ({pf_total})", callback_data="pf_menu"),
    ])

    # ===== دسته ۶: ابزارها =====
    buttons.append([
        InlineKeyboardButton("⬇️ دانلودر رسانه", callback_data="downloader_menu"),
        InlineKeyboardButton(f"📱 اکانت‌ها ({acc_count})", callback_data="manage_accounts"),
    ])
    # ===== دسته ۶.۵: اینستاگرام =====
    buttons.append([
        InlineKeyboardButton("📸 اینستاگرام", callback_data="ig_menu"),
    ])

    # ===== دسته ۷: پشتیبان‌گیری =====
    buttons.append([
        InlineKeyboardButton("💾 بک‌آپ کامل", callback_data="backup_all"),
        InlineKeyboardButton("♻️ وضعیت سلامت", callback_data="health_check"),
    ])

    # ===== دسته ۸: تنظیمات و راهنما =====
    buttons.append([
        InlineKeyboardButton("⚙️ تنظیمات", callback_data="menu_settings"),
        InlineKeyboardButton("❓ راهنما", callback_data="help_page"),
    ])

    return InlineKeyboardMarkup(buttons)


def _db_count_users():
    try:
        return count_users()
    except:
        users, _, _ = load_scraped()
        return len(users)

bg_scraper_started = False
proj_tracker_started = False

async def project_tracker_loop():
    """هر ۶ ساعت پروژه‌های بوکمارک شده را چک میکند و در صورت تغییر اطلاع میدهد."""
    await asyncio.sleep(120)  # wait 2 min after boot
    while True:
        try:
            loop = asyncio.get_running_loop()
            changes = await loop.run_in_executor(None, check_project_updates)
            for c in changes:
                try:
                    name = c.get("name","")
                    msg = "🔔 <b>پروژه‌ای که دنبال می‌کنی تغییر کرد!</b>\n\n"
                    msg += f"🐙 <a href=\"{c['url']}\">{name}</a>\n"
                    if c.get("delta_stars",0) > 0:
                        msg += f"⭐ +{c['delta_stars']} ستاره جدید (مجموع {c.get('new_stars',0):,})\n"
                    if c.get("update"):
                        msg += f"🔄 {c['update']}\n"
                    if c.get("issues"):
                        msg += f"{c['issues']}\n"
                    await app.send_message(ADMIN_ID, msg, disable_web_page_preview=True)
                    await asyncio.sleep(1)
                except Exception as e:
                    print(f"tracker notify err: {e}", flush=True)
        except Exception as e:
            print(f"tracker err: {e}", flush=True)
        await asyncio.sleep(6*3600)  # every 6 hours


@app.on_message(filters.command("start") & filters.private & filters.user(ADMIN_ID))
async def start_cmd(c, m):
    global bg_started, hunter_bg_started, bg_scraper_started, proj_tracker_started
    if defender and not bg_started:
        asyncio.create_task(defender.bg_scan())
        bg_started = True
    # Start the background member scraper (NOT the old crypto hunter)
    if not bg_scraper_started:
        bg_scraper_start(app, ADMIN_ID)
        bg_scraper_started = True
    if not proj_tracker_started:
        asyncio.create_task(project_tracker_loop())
        proj_tracker_started = True
    try:
        await app.set_bot_commands([])
    except:
        pass
    await m.reply_text(build_welcome_text(), reply_markup=main_menu(), disable_web_page_preview=True)

# Honeypot callback watcher (catches non-admin users in protected group clicking trap buttons)
@app.on_callback_query(~filters.user(ADMIN_ID))
async def hp_cb(c, q):
    if not defender or not CURRENT_GROUP_ID:
        return
    try:
        if q.message and q.message.chat and q.message.chat.id == CURRENT_GROUP_ID:
            await defender.monitor_callback(q)
    except:
        pass

@app.on_callback_query(filters.user(ADMIN_ID))
async def cb(c, q):
    try:
        await _cb_impl(c, q)
    except Exception as e:
        _log_err(e, "callback handler")
        try:
            await q.answer(f"خطا: {str(e)[:100]}", show_alert=True)
            if q.message:
                await q.message.edit_text(f"❌ خطای داخلی:\n{type(e).__name__}: {str(e)[:300]}\n\nلطفا /start بزنید.", reply_markup=main_menu())
        except: pass
        atk_state.clear()

async def _cb_impl(c, q):
    global CURRENT_GROUP_ID, defender, bg_started, config
    d = q.data

    # ==================== خانه و منوهای دسته‌بندی ====================
    if d == "noop":
        await q.answer(cache_time=3)
        return

    # ==================== 🆕 مدیریت چت‌ها ====================
    if d == "chats_manager":
        await _show_chats_manager(q)
        return

    if d.startswith("chat_select_"):
        chat_id = int(d.split("_")[2])
        await _handle_chat_select(q, chat_id)
        return

    if d.startswith("chat_cat_"):
        parts = d.split("_", 2)
        chat_id = int(parts[2])
        await _handle_chat_category_prompt(q, chat_id)
        return

    if d.startswith("chat_del_"):
        chat_id = int(d.split("_")[2])
        delete_scanned_chat(chat_id)
        await q.answer("🗑️ چت از تاریخچه حذف شد", show_alert=True)
        await _show_chats_manager(q)
        return

    if d.startswith("chat_fav_"):
        chat_id = int(d.split("_")[2])
        toggle_chat_favorite(chat_id)
        await _show_chats_manager(q)
        return

    if d.startswith("attack_from_chat_"):
        chat_id = int(d.split("_")[3])
        atk_state["target_chat_id"] = chat_id
        await _start_attack_from_chat(q, chat_id)
        return

    if d == "ig_scrape_prompt":
        atk_state["step"] = "ig_target_username"
        await q.message.edit_text(
            "🔍 <b>اسکرپ فالوورهای اینستاگرام</b>\n\n"
            "نام کاربری پیج عمومی مورد نظر رو بفرست:\n"
            "مثال: <code>cristiano</code> یا <code>instagram</code>\n\n"
            "⚠️ فقط پیج‌های <b>عمومی</b> قابل اسکرپ هستن.",
            reply_markup=InlineKeyboardMarkup([[_sub_back_btn(target="ig_menu")[0]]]))
        return

    if d == "categories_menu":
        await _show_categories_menu(q)
        return

    if d.startswith("cat_view_"):
        cat = d[9:]  # after "cat_view_"
        await _show_chats_manager(q, category=cat)
        return

    if d.startswith("cat_set_"):
        parts = d.split("_", 2)
        chat_id = int(parts[2])
        await _handle_chat_category_prompt(q, chat_id)
        return

    if d.startswith("ai_analyze_"):
        chat_id = int(d.split("_")[2])
        await _handle_ai_analyze(q, chat_id)
        return

    if d.startswith("dir_add_go_"):
        gid = int(d.split("_")[3])
        asyncio.create_task(_execute_direct_add(q, gid))
        return

    if d.startswith("cat_apply_"):
        parts = d.split("_")
        chat_id = int(parts[2])
        new_cat = "_".join(parts[3:])
        update_chat_category(chat_id, new_cat if new_cat != "none" else "")
        await q.answer(f"✅ دسته‌بندی به '{new_cat}' تغییر کرد" if new_cat != "none" else "✅ دسته‌بندی حذف شد", show_alert=True)
        await _show_chats_manager(q)
        return

    if d.startswith("source_filter_"):
        filter_type = d.split("_")[2]
        if filter_type == "all":
            source_chat_id = None
        elif filter_type == "cat":
            source_cat = "_".join(d.split("_")[3:])
            source_chat_id = None
            atk_state["source_cat"] = source_cat
        else:
            source_chat_id = int(d.split("_")[2]) if d.split("_")[2].isdigit() else None
        atk_state["source_filter"] = source_chat_id
        await q.answer("✅ فیلتر اعمال شد", show_alert=True)
        await q.message.edit_text(q.message.text + f"\n\n✅ فیلتر منبع اعمال شد", reply_markup=main_menu())
        return

    if d == "stop_op":
        # درخواست توقف هر عملیات در حال اجرا
        for obj in ["atk", "new_acc_client", "new_client", "add_client"]:
            try:
                o = atk_state.get(obj)
                if o and hasattr(o, "request_stop"):
                    o.request_stop()
            except: pass
        atk_state.clear()
        await q.answer("⏹️ درخواست توقف داده شد، چند لحظه...", show_alert=True)
        await q.message.edit_text("⏹️ عملیات توسط کاربر متوقف شد.", reply_markup=main_menu())
        return

    if d == "home":
        atk_state.clear()
        await q.message.edit_text(build_welcome_text(), reply_markup=main_menu(), disable_web_page_preview=True)
        return

    if d == "menu_defense":
        cname = (config.get("group_name") or "انتخاب نشده") if CURRENT_GROUP_ID else "هنوز انتخاب نشده"
        def_state = "🟢 فعال" if defender and defender.MIN_ACCOUNT_AGE_DAYS>0 else "🔴 خاموش"
        is_adm_txt = "—"
        mcount = "—"
        hidden = "—"
        if CURRENT_GROUP_ID:
            try:
                chat = await app.get_chat(CURRENT_GROUP_ID)
                try:
                    bot_mem = await app.get_chat_member(CURRENT_GROUP_ID, "me")
                    is_adm_txt = "✅ هستم" if bot_mem.status in ["administrator","creator"] else "❌ نیستم"
                except: is_adm_txt = "❓"
                mcount = f"{chat.members_count:,}" if getattr(chat, "members_count", None) else "—"
                hidden = "✅ مخفی" if getattr(chat, "has_hidden_members", False) else "❌ قابل مشاهده"
            except: pass
        banned = len(defender.banned_scrapers) if defender else 0
        text = f"🛡️ <b>پنل دفاع و گروه</b>\n━━━━━━━━━━━━━━━━━━\n"
        text += f"🎯 گروه هدف: <b>{cname}</b>\n"
        text += f"🛡️ وضعیت دفاع: <b>{def_state}</b>\n"
        text += f"👑 دسترسی ادمین ربات: <b>{is_adm_txt}</b>\n"
        text += f"👥 تعداد اعضا: <b>{mcount}</b>\n"
        text += f"🙈 حالت لیست اعضا مخفی: <b>{hidden}</b>\n"
        text += f"🚫 مجموع بن‌شده‌ها: <b>{banned}</b>\n"
        text += f"⏱️ سن حداقل اکانت تازه‌وارد: <b>۲۵ روز</b>\n"
        text += f"🍯 هانی‌پات نامرئی: <b>✅ فعال (هر ۱۰ دقیقه)</b>\n"
        text += "━━━━━━━━━━━━━━━━━━\n"
        btns = []
        if CURRENT_GROUP_ID:
            btns.append([
                InlineKeyboardButton("⚙️ خاموش/روشن دفاع", callback_data="toggledef"),
                InlineKeyboardButton("🔄 تغییر گروه", callback_data="select_group"),
            ])
            btns.append([
                InlineKeyboardButton("📊 نمایش وضعیت کامل", callback_data="status"),
                InlineKeyboardButton("🚫 لیست بن‌شده‌ها", callback_data="banned_list"),
            ])
        else:
            btns.append([InlineKeyboardButton("🔍 انتخاب گروه برای محافظت", callback_data="select_group")])
        btns.append(_sub_back_btn())
        await q.message.edit_text(text, reply_markup=InlineKeyboardMarkup(btns))
        return

    if d == "menu_stats":
        users, gname, _ = load_scraped()
        accs = list_saved_accounts()
        limits = load_adder_limits()
        total_added = _db_count_added()
        total_proj = count_projects()
        bg_st = get_bg_scan()
        # Sum remaining capacity
        total_cap = 0; used_cap = 0
        for p in accs:
            a = limits.get(p, {}).get("added", 0)
            used_cap += a
            total_cap += MAX_ADD_PER_ACCOUNT
        text = f"📊 <b>داشبورد آماری ربات</b>\n━━━━━━━━━━━━━━━━━━\n"
        text += f"👥 تعداد اکانت‌های ذخیره: <b>{len(accs)}</b>\n"
        text += f"📦 مجموع ظرفیت ادد: <b>{used_cap}/{total_cap}</b>\n"
        text += f"🗂️ تعداد ممبر استخراج شده: <b>{len(users):,}</b>\n"
        text += f"✅ مجموع اددشده‌ها: <b>{total_added:,}</b>\n"
        text += f"🚫 مجموع بن‌شده‌ها: <b>{len(defender.banned_scrapers) if defender else 0}</b>\n"
        text += f"🔭 پروژه‌های اوپن‌سورس: <b>{total_proj:,}</b>\n"
        text += f"⏱️ اسکن خودکار: <b>{'🟢 روشن' if bg_st.get('enabled') else '🔴 خاموش'}</b>\n"
        if bg_st.get("last_run"):
            import time as _t
            dt = _t.strftime("%Y-%m-%d %H:%M", _t.localtime(bg_st["last_run"]))
            text += f"🕐 آخرین اسکن خودکار: <b>{dt}</b>\n"
            text += f"👥 مجموع پیدا شده توسط اسکن خودکار: <b>{bg_st.get('total_found',0):,}</b>\n"
        text += "━━━━━━━━━━━━━━━━━━\n"
        text += "<i>در حال کار بدون وقفه...</i>"
        btns = [
            [InlineKeyboardButton("📈 آمار اکانت‌های اددکننده", callback_data="adder_stats")],
            [InlineKeyboardButton("📜 تاریخچه اددها", callback_data="added_history_menu")],
            [InlineKeyboardButton("🚫 لیست بن‌شده‌ها", callback_data="banned_list")],
            _sub_back_btn()
        ]
        await q.message.edit_text(text, reply_markup=InlineKeyboardMarkup(btns))
        return

    if d == "menu_settings":
        text = "⚙️ <b>تنظیمات ربات</b>\n━━━━━━━━━━━━━━━━━━\n"
        text += "در این بخش ابزارهای پیکربندی ربات قرار دارد:\n\n"
        text += "🔸 <b>مدیریت اکانت‌ها</b> — افزودن، حذف، بکاپ سشن\n"
        text += "🔸 <b>اسکن خودکار</b> — زمان‌بندی و فعالسازی\n"
        text += "🔸 <b>ریست آمار</b> — پاک کردن شمارنده‌های ادد\n"
        text += "🔸 <b>پاک کردن لیست ممبر</b> — خالی کردن دیتابیس اسکرپ\n"
        text += "🔸 <b>دانلود CSV</b> — خروجی اکسل از داده‌ها\n"
        btns = [
            [InlineKeyboardButton("📱 مدیریت اکانت‌ها", callback_data="manage_accounts"),
             InlineKeyboardButton("⏱️ اسکن خودکار", callback_data="bg_menu")],
            [InlineKeyboardButton("🔄 ریست آمار ادد", callback_data="reset_adder_all"),
             InlineKeyboardButton("🗑️ پاک کردن لیست ممبر", callback_data="clear_users")],
            [InlineKeyboardButton("⬇️ دانلودر رسانه", callback_data="downloader_menu"),
             InlineKeyboardButton("📥 CSV ممبرها", callback_data="export_users_csv")],
            [InlineKeyboardButton("📥 CSV تاریخچه ادد", callback_data="export_added_csv"),
             InlineKeyboardButton("🔝 منوی اصلی", callback_data="home")],
            _sub_back_btn()
        ]
        await q.message.edit_text(text, reply_markup=InlineKeyboardMarkup(btns))
        return

    if d == "help_page":
        text = "❓ <b>راهنمای ربات ضد اسکریپت</b>\n━━━━━━━━━━━━━━━━━━\n\n"
        text += "🛡️ <b>بخش دفاع:</b>\n"
        text += "• کپچای خودکار برای اعضای جدید\n"
        text += "• تشخیص خروج سریع زیر ۴ دقیقه\n"
        text += "• مسدود کردن اکانت‌های زیر ۲۵ روز\n"
        text += "• هانی‌پات نامرئی برای فریب اسکرپرها\n\n"
        text += "🚀 <b>بخش حمله/اسکرپ:</b>\n"
        text += "• با یک یا چند اکانت به صورت همزمان\n"
        text += "• پنج استراتژی ترکیبی: الفبا، تاریخچه، تازه‌وارد، گروه مشترک، لیست مستقیم\n"
        text += "• فینگرپرینت ثابت هر اکانت (جلوگیری از انقضای سشن)\n\n"
        text += "➕ <b>بخش اضافه کردن اعضا:</b>\n"
        text += "• سقف ۵۰ نفر در هر اکانت (جلوگیری از بن)\n"
        text += "• به صورت تک یا موازی\n"
        text += "• تاخیر هوشمند بین درخواست‌ها\n\n"
        text += "⏱️ <b>اسکن خودکار پس‌زمینه:</b>\n"
        text += "• بدون نیاز به روشن گذاشتن\n"
        text += "• ذخیره مستقیم در دیتابیس ابری\n"
        text += "• بدون نیاز به کد مجدد\n\n"
        text += "💾 تمام داده‌ها در دیتابیس Neon ابری ذخیره می‌شوند و با ریست رندر پاک نمی‌شوند.\n"
        btns = [_sub_back_btn()]
        await q.message.edit_text(text, reply_markup=InlineKeyboardMarkup(btns))
        return

    if d == "banned_list":
        if not defender:
            await q.answer("هنوز گروه محافظت انتخاب نشده!", show_alert=True)
            return
        ids = list(defender.banned_scrapers)
        text = f"🚫 <b>{len(ids)} کاربر مسدود شده</b>\n\n"
        if not ids:
            text += "هنوز کسی مسدود نشده ✨"
        else:
            for i, uid in enumerate(ids[-40:], 1):
                text += f"{i}. <code>{uid}</code>\n"
            if len(ids) > 40:
                text += f"\n... و {len(ids)-40} مورد دیگر"
        await q.message.edit_text(text, reply_markup=InlineKeyboardMarkup([_sub_back_btn(target="menu_defense")]))
        return

    if d == "add_new_account_start":
        atk_state["step"] = "phone_new"
        atk_state["after_auth_mode"] = "attack"
        await q.message.edit_text(
            "📱 <b>افزودن اکانت جدید تلگرام</b>\n\n"
            "شماره موبایل اکانت را با فرمت بین‌المللی بفرستید، مثلا:\n"
            "<code>+989123456789</code>\n\n"
            "⚠️ این شماره یک بار کد می‌گیرد و برای همیشه در دیتابیس ذخیره می‌شود و دیگر کد نمی‌خواهد.",
            reply_markup=InlineKeyboardMarkup([_sub_back_btn()]))
        return

    if d == "clear_users":
        try:
            cur = db.get_conn().cursor()
            cur.execute("TRUNCATE scraped_users")
            cur.close()
        except: pass
        try:
            with open(SCRAPED_FILE,"w",encoding="utf-8") as f: json.dump({"users":[],"group_name":"","group_id":0}, f)
        except: pass
        await q.answer("لیست ممبرها پاک شد.", show_alert=True)
        await q.message.edit_text("✅ لیست ممبرهای استخراج شده از دیتابیس پاک شد.", reply_markup=main_menu())
        return

    if d == "export_users_csv":
        users, gname, gid = load_scraped()
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["user_id","username","first_name","last_name","phone"])
        for u in users:
            w.writerow([u.get("user_id",""), u.get("username",""), u.get("first_name",""), u.get("last_name",""), u.get("phone","")])
        await app.send_document(ADMIN_ID, io.BytesIO(buf.getvalue().encode("utf-8-sig")),
                                file_name=f"scraped_members_{int(time.time())}.csv",
                                caption=f"📥 لیست {len(users)} ممبر استخراج شده")
        await q.answer("CSV ارسال شد ✅", show_alert=True)
        return

    if d == "export_added_csv":
        try:
            cur = db.get_conn().cursor()
            cur.execute("SELECT group_id, user_id, added_at, account_phone FROM added_history_tbl ORDER BY added_at DESC")
            rows = cur.fetchall()
            cur.close()
        except: rows = []
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["group_id","user_id","added_at","account_phone"])
        for r in rows:
            w.writerow(r)
        await app.send_document(ADMIN_ID, io.BytesIO(buf.getvalue().encode("utf-8-sig")),
                                file_name=f"added_history_{int(time.time())}.csv",
                                caption=f"📥 تاریخچه {len(rows)} مورد ادد")
        await q.answer("CSV ارسال شد ✅", show_alert=True)
        return

    if d == "backup_all":
        # Build a full JSON backup of all data and send
        try:
            cur = db.get_conn().cursor(cursor_factory=db.psycopg2.extras.RealDictCursor) if hasattr(db,"psycopg2") else None
        except: cur = None
        try:
            c = db.get_conn().cursor()
            backup = {
                "exported_at": int(time.time()),
                "version": 2,
            }
            # Users
            c.execute("SELECT user_id, username, first_name, last_name, phone, source_group_id, source_group_name, added_at FROM scraped_users")
            backup["scraped_users"] = [dict(zip([d[0] for d in c.description], row)) for row in c.fetchall()]
            # Accounts
            c.execute("SELECT phone, name, username, device_fp, created_at, last_used, added_count FROM saved_accounts_tbl")
            backup["accounts"] = [dict(zip([d[0] for d in c.description], row)) for row in c.fetchall()]
            # Adder limits
            c.execute("SELECT phone, added, last_used FROM adder_limits_tbl")
            backup["adder_limits"] = [dict(zip([d[0] for d in c.description], row)) for row in c.fetchall()]
            # Added history
            c.execute("SELECT group_id, user_id, added_at, account_phone FROM added_history_tbl")
            backup["added_history"] = [dict(zip([d[0] for d in c.description], row)) for row in c.fetchall()]
            # Config
            c.execute("SELECT group_id, group_name, defense_enabled, owner_phone FROM config_tbl")
            backup["config"] = [dict(zip([d[0] for d in c.description], row)) for row in c.fetchall()]
            # Projects
            c.execute("SELECT url, platform, full_name, category, data, found_at FROM projects_tbl")
            backup["projects"] = [dict(zip([d[0] for d in c.description], row)) for row in c.fetchall()]
            # KV
            c.execute("SELECT key, value FROM kv_store")
            backup["kv"] = {row[0]: row[1] for row in c.fetchall()}
            c.close()
            data = json.dumps(backup, ensure_ascii=False, indent=2, default=str)
            import io as _io
            await app.send_document(ADMIN_ID, _io.BytesIO(data.encode("utf-8")),
                                    file_name=f"backup_{int(time.time())}.json",
                                    caption=f"💾 بک‌آپ کامل\n"
                                            f"👥 کاربران: {len(backup['scraped_users'])}\n"
                                            f"📱 اکانت‌ها: {len(backup['accounts'])}\n"
                                            f"✅ تاریخچه ادد: {len(backup['added_history'])}\n"
                                            f"🔭 پروژه‌ها: {len(backup['projects'])}")
            await q.answer("بک‌آپ کامل ساخته و ارسال شد ✅", show_alert=True)
        except Exception as e:
            await q.answer(f"خطا: {e}", show_alert=True)
        return

    if d == "health_check":
        try:
            import platform as _pl
            c = db.get_conn().cursor()
            c.execute("SELECT (SELECT COUNT(*) FROM scraped_users), (SELECT COUNT(*) FROM saved_accounts_tbl), (SELECT COUNT(*) FROM projects_tbl), (SELECT COUNT(*) FROM added_history_tbl)")
            u,a,p,ah = c.fetchone()
            c.close()
            try:
                import psutil
                mem = psutil.virtual_memory()
                mem_pct = mem.percent
                disk = psutil.disk_usage("/").percent
            except:
                mem_pct = "-"; disk = "-"
            text = "♻️ <b>وضعیت سلامت ربات</b>\n━━━━━━━━━━━━━━━━━━\n"
            text += f"🟢 وضعیت: آنلاین\n"
            text += f"🐍 پایتون: {_pl.python_version()}\n"
            text += f"💾 حافظه رم: {mem_pct}% · دیسک: {disk}%\n"
            text += f"🗄️ دیتابیس: متصل ✅\n"
            text += f"━━━━━━━━━━━━━━━━━━\n"
            text += f"👥 ممبر در دیتابیس: <b>{u:,}</b>\n"
            text += f"📱 اکانت‌های ذخیره: <b>{a}</b>\n"
            text += f"🔭 پروژه‌ها: <b>{p:,}</b>\n"
            text += f"✅ کل اددشده‌ها: <b>{ah:,}</b>\n"
            text += f"⏱️ اسکن خودکار: <b>{'روشن' if get_bg_scan().get('enabled') else 'خاموش'}</b>\n"
        except Exception as e:
            text = f"❌ خطا در بررسی: {e}"
        await q.message.edit_text(text, reply_markup=InlineKeyboardMarkup([_sub_back_btn()]))
        return

    if d == "downloader_menu":
        text = "⬇️ <b>دانلودر همه‌کاره رسانه</b>\n━━━━━━━━━━━━━━━━━━\n\n"
        text += "لینک مورد نظر را مستقیم در چت بفرستید.\n"
        text += "<b>پلتفرم‌های پشتیبانی شده:</b>\n"
        text += "🎵 تیک‌تاک · 📸 اینستاگرام (ریلز/پست) · ▶️ یوتوب شورت\n"
        text += "🐦 توییتر/X · 👽 ردیت · 📺 آپارات · 📌 پینترست\n"
        text += "🎵 ساوندکلاود · 🎬 ویمئو · 🔗 لینک مستقیم\n\n"
        text += "<i>بدون واترمارک · کیفیت بالا · بدون تبلیغ</i>"
    if d == "ig_menu":
        await _show_ig_menu(q)
        return

    if d.startswith("ig_scrape_"):
        target = d[10:]  # after "ig_scrape_"
        await _start_ig_scrape(q, target)
        return

    if d == "ig_login":
        await _handle_ig_login(q)
        return

    if d == "ig_logout":
        atk_state["ig_username"] = ""
        atk_state["ig_password"] = ""
        await q.answer("📸 اطلاعات لاگین پاک شد", show_alert=True)
        await _show_ig_menu(q)
        return

    if d == "ig_upload_session":
        atk_state["step"] = "upload_ig_session"
        await q.message.edit_text(
            "📥 <b>آپلود فایل سشن اینستاگرام</b>\n\n"
            "🔹 این روش برای اکانت‌های دارای <b>2FA</b> یا <b>Google Authenticator</b> عالیه\n"
            "🔹 کافیه یه بار توی سیستم خودت با Instaloader لاگین کنی:\n\n"
            "<pre>pip install instaloader\n"
            "python3 -c \"\nimport instaloader\n"
            "L = instaloader.Instaloader()\n"
            "L.login('YOUR_USER', 'YOUR_PASS')\n"
            "L.save_session_to_file('ig_session')\n\"</pre>\n\n"
            "فایل <code>ig_session</code> رو همینجا آپلود کن.",
            reply_markup=InlineKeyboardMarkup([[_sub_back_btn(target="ig_menu")[0]]]),
            disable_web_page_preview=True)
        return

    if d == "ig_list":
        await _show_ig_results(q)
        return


    if d == "select_group":
        groups = []
        async for dialog in app.get_dialogs():
            if dialog.chat.type in ["supergroup", "group"] or (dialog.chat.type == "channel" and getattr(dialog.chat, 'megagroup', False)):
                groups.append((dialog.chat.title, dialog.chat.id))
        buttons = []
        for name, gid in groups:
            buttons.append([InlineKeyboardButton(f"👥 {name}", callback_data=f"setg_{gid}")])
        buttons.append([InlineKeyboardButton("بازگشت", callback_data="home")])
        await q.message.edit_text("گروهی که میخوای محافظت کنی انتخاب کن:", reply_markup=InlineKeyboardMarkup(buttons))
        return

    if d.startswith("setg_"):
        gid = int(d.split("_")[1])
        CURRENT_GROUP_ID = gid
        config["defend_group"] = gid
        config["defense_enabled"] = True
        save_config(config)
        defender = AdvancedDefender(app, CURRENT_GROUP_ID, ADMIN_ID)
        defender.MIN_ACCOUNT_AGE_DAYS = 25
        if not bg_started:
            asyncio.create_task(defender.bg_scan())
            bg_started = True
        await q.answer("انتخاب شد!", show_alert=True)
        await q.message.edit_text("✅ گروه محافظت انتخاب شد.", reply_markup=main_menu())
        return

    if d == "status" and CURRENT_GROUP_ID:
        try:
            chat = await app.get_chat(CURRENT_GROUP_ID)
            bot_mem = await app.get_chat_member(CURRENT_GROUP_ID, "me")
            is_adm = bot_mem.status in ["administrator", "creator"]
            text = "📊 <b>وضعیت کامل گروه و دفاع</b>\n━━━━━━━━━━━━━━━━━━\n"
            text += f"🎯 گروه: <b>{chat.title}</b>\n"
            text += f"🛡️ دفاع: <b>{'✅ روشن' if defender.MIN_ACCOUNT_AGE_DAYS>0 else '❌ خاموش'}</b>\n"
            text += f"👑 ربات ادمین: <b>{'✅ هستم' if is_adm else '❌ نیستم!'}</b>\n"
            text += f"🙈 لیست اعضا مخفی: <b>{'✅ مخفی' if chat.has_hidden_members else '❌ لطفا در تنظیمات فعال کنید'}</b>\n"
            text += f"👥 تعداد اعضا: <b>{chat.members_count:,}</b>\n"
            text += f"🔞 حداقل سن اکانت: <b>{defender.MIN_ACCOUNT_AGE_DAYS} روز</b>\n"
            text += f"🍯 هانی‌پات نامرئی: <b>✅ فعال</b>\n"
            text += f"🚫 مجموع مسدودشده: <b>{len(defender.banned_scrapers)}</b>\n"
            text += f"🤖 کپچای خودکار: <b>✅ فعال</b>\n"
            text += "━━━━━━━━━━━━━━━━━━"
        except Exception as e:
            text = f"❌ خطا: {str(e)}"
        await q.message.edit_text(text, reply_markup=InlineKeyboardMarkup([_sub_back_btn(target="menu_defense")]))
        return

    if d == "toggledef" and defender:
        defender.MIN_ACCOUNT_AGE_DAYS = 0 if defender.MIN_ACCOUNT_AGE_DAYS>0 else 25
        config["defense_enabled"] = defender.MIN_ACCOUNT_AGE_DAYS >0
        save_config(config)
        await q.answer("وضعیت دفاع تغییر کرد", show_alert=True)
        await q.message.edit_text(build_welcome_text(), reply_markup=main_menu())
        return

    # ==================== نمایش لیست مخاطبان ====================
    if d.startswith("show_list_"):
        page = int(d.split("_")[2])
        PER_PAGE = 15
        users, gname, gid = load_scraped()
        if not users:
            await q.answer("هنوز هیچ مخاطبی استخراج نشده! اول تست حمله بزن.", show_alert=True)
            return
        total = len(users)
        total_pages = (total + PER_PAGE - 1) // PER_PAGE
        if page >= total_pages:
            page = total_pages - 1
        if page < 0:
            page = 0
        start = page * PER_PAGE
        end = min(start + PER_PAGE, total)
        chunk = users[start:end]
        # Load added IDs from DB
        try:
            cur = db.get_conn().cursor()
            cur.execute("SELECT user_id FROM added_history_tbl")
            all_added_ids = {int(r[0]) for r in cur.fetchall()}
            cur.close()
        except:
            all_added_ids = set()
        added_in_list = sum(1 for u in users if int(u.get("user_id",0) or 0) in all_added_ids)
        text = f"📋 <b>لیست مخاطبان استخراج شده</b>\n━━━━━━━━━━━━━━━━━━\n"
        if gname:
            text += f"👥 گروه: <b>{gname}</b>\n"
        text += f"🔢 تعداد کل: <b>{total:,}</b> نفر\n"
        text += f"✅ اددشده: <b>{added_in_list:,}</b> نفر\n"
        text += f"📄 صفحه {page+1} از {total_pages}\n━━━━━━━━━━━━━━━━━━\n"
        for i, u in enumerate(chunk, start=start+1):
            name = (u.get("first_name","") or "بدون نام").strip()
            if u.get("last_name"):
                name += " " + (u["last_name"] or "").strip()
            uname = f"@{u['username']}" if u.get("username") else "(بدون یوزرنیم)"
            uid = u.get("user_id", "?")
            added = " ✅" if int(uid or 0) in all_added_ids else ""
            phone = u.get("phone","")
            text += f"{i}. <b>{name}</b>{added}\n"
            text += f"   └ {uname} · <code>{uid}</code>"
            if phone:
                text += f" · 📱 {phone}"
            text += "\n\n"
        if len(text) > 3800:
            text = text[:3800] + "\n...(ادامه در صفحه بعد)"
        nav_buttons = []
        nav_row = []
        if page > 0:
            nav_row.append(InlineKeyboardButton("⬅️ قبلی", callback_data=f"show_list_{page-1}"))
        nav_row.append(InlineKeyboardButton(f"{page+1}/{total_pages}", callback_data="noop"))
        if page < total_pages - 1:
            nav_row.append(InlineKeyboardButton("بعدی ➡️", callback_data=f"show_list_{page+1}"))
        nav_buttons.append(nav_row)
        nav_buttons.append([InlineKeyboardButton("📥 دانلود CSV کامل", callback_data="download_csv")])
        nav_buttons.append([InlineKeyboardButton("🔙 بازگشت", callback_data="menu_stats"),
                            InlineKeyboardButton("🏠 خانه", callback_data="home")])
        await q.message.edit_text(text, reply_markup=InlineKeyboardMarkup(nav_buttons), disable_web_page_preview=True)
        return

    # ==================== 🆕 لیست کاربران فیلتر شده بر اساس منبع ====================
    if d.startswith("show_list_source_"):
        chat_id = int(d.split("_")[3])
        page = int(d.split("_")[4]) if len(d.split("_")) > 4 else 0
        PER_PAGE = 15
        ch = get_scanned_chat(chat_id)
        ch_name = ch["chat_name"] if ch else f"چت {chat_id}"

        users = get_users_by_source(source_chat_id=chat_id, limit=PER_PAGE, offset=page * PER_PAGE)
        total = count_users_by_source(source_chat_id=chat_id)
        if not users:
            await q.answer("هیچ کاربری از این منبع یافت نشد!", show_alert=True)
            return

        total_pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)
        text = f"👥 کاربران استخراج شده از:\\n<b>{ch_name}</b>\\n"
        text += f"━━━━━━━━━━━━━━━━━━\\n"
        text += f"📦 تعداد کل: {total:,}\\n"
        text += f"📄 صفحه {page+1} از {total_pages}\\n"
        text += "━━━━━━━━━━━━━━━━━━\\n"

        for i, u in enumerate(users, page * PER_PAGE + 1):
            name = (u.get("first_name", "") or "بدون نام").strip()
            if u.get("last_name"):
                name += " " + (u.get("last_name") or "").strip()
            uname = f"@{u['username']}" if u.get("username") else ""
            text += f"{i}. <b>{name}</b> {uname}\n"
            text += f"   <code>{u['user_id']}</code>\\n\\n"

        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton("⬅️ قبلی", callback_data=f"show_list_source_{chat_id}_{page-1}"))
        if page < total_pages - 1:
            nav.append(InlineKeyboardButton("بعدی ➡️", callback_data=f"show_list_source_{chat_id}_{page+1}"))
        buttons = [nav] if nav else []
        buttons.append(_sub_back_btn(target=f"chat_select_{chat_id}"))
        await q.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons), disable_web_page_preview=True)
        return

    # ==================== تاریخچه اعضای اضافه شده ====================
    if d == "added_history_menu":
        # Load from DB
        try:
            cur = db.get_conn().cursor()
            cur.execute("SELECT group_id, COUNT(*) as cnt, MAX(added_at) as last_t FROM added_history_tbl GROUP BY group_id ORDER BY cnt DESC")
            rows = cur.fetchall()
            cur.close()
        except: rows = []
        total_all = sum(r[1] for r in rows) if rows else 0
        text = f"✅ <b>تاریخچه اعضای اضافه شده</b>\n━━━━━━━━━━━━━━━━━━\n"
        text += f"🔢 مجموع کل اددشده‌ها: <b>{total_all:,}</b> نفر\n\n"
        if not rows:
            text += "هنوز هیچ‌کس به هیچ گروهی اضافه نشده ✨"
        else:
            for gid, cnt, last_t in rows:
                # try to get group name
                gname = f"گروه {gid}"
                try:
                    chat = await app.get_chat(int(gid))
                    gname = chat.title or gname
                except: pass
                date_str = time.strftime("%Y-%m-%d %H:%M", time.localtime(last_t)) if last_t else "-"
                text += f"👥 <b>{gname}</b>\n   └ تعداد اددشده: {cnt:,}\n   └ آخرین ادد: {date_str}\n\n"
        buttons = []
        if rows:
            for gid, cnt, _ in rows[:20]:
                try:
                    chat = await app.get_chat(int(gid))
                    gname = chat.title or str(gid)
                except:
                    gname = f"گروه {gid}"
                buttons.append([InlineKeyboardButton(f"👁️ لیست {gname[:28]} ({cnt})", callback_data=f"view_added_{gid}_0")])
        buttons.append([InlineKeyboardButton("🗑️ پاک کردن تاریخچه", callback_data="clear_added_pick")])
        buttons.append(_sub_back_btn(target="menu_stats"))
        await q.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
        return

    if d.startswith("view_added_"):
        parts = d.split("_")
        gid_key = parts[2]
        page = int(parts[3])
        PER_PAGE = 20
        hist = load_added_history()
        ginfo = hist.get(gid_key, {})
        ids_list = ginfo.get("added_user_ids", [])
        title = ginfo.get("group_title", "?")
        total = len(ids_list)
        total_pages = max(1, (total + PER_PAGE -1) // PER_PAGE)
        if page >= total_pages:
            page = total_pages-1
        start = page * PER_PAGE
        end = min(start + PER_PAGE, total)
        chunk_ids = ids_list[start:end]
        text = f"✅ لیست {total} نفر ادد شده به:\n👥 {title}\n📄 صفحه {page+1} از {total_pages}\n\n"
        # نام ها را تا حد امکان از لیست استخراج شده بیابیم
        scraped_users, _, _ = load_scraped()
        id_to_name = {u.get("user_id"): u for u in scraped_users}
        for i, uid in enumerate(chunk_ids, start=start+1):
            info = id_to_name.get(uid, {})
            name = info.get("first_name", "") or ""
            if info.get("last_name"):
                name += " " + info["last_name"]
            if not name:
                name = f"کاربر {uid}"
            uname = f"@{info['username']}" if info.get("username") else ""
            text += f"{i}. ✅ {name} {uname} (`{uid}`)\n"
        if len(text) > 3800:
            text = text[:3800] + "\n..."
        nav = []
        nav_row = []
        if page > 0:
            nav_row.append(InlineKeyboardButton("⬅️ قبلی", callback_data=f"view_added_{gid_key}_{page-1}"))
        nav_row.append(InlineKeyboardButton(f"{page+1}/{total_pages}", callback_data="noop"))
        if page < total_pages-1:
            nav_row.append(InlineKeyboardButton("بعدی ➡️", callback_data=f"view_added_{gid_key}_{page+1}"))
        nav.append(nav_row)
        nav.append([InlineKeyboardButton("🔙 بازگشت به لیست تاریخچه", callback_data="added_history_menu")])
        await q.message.edit_text(text, reply_markup=InlineKeyboardMarkup(nav))
        return

    if d == "clear_added_pick":
        hist = load_added_history()
        buttons = []
        for gid in hist:
            cnt = len(hist[gid].get("added_user_ids", []))
            buttons.append([InlineKeyboardButton(f"❌ پاک کن: {hist[gid].get('group_title','?')[:20]} ({cnt})", callback_data=f"clr_add_{gid}")])
        buttons.append([InlineKeyboardButton("🔙 بازگشت", callback_data="added_history_menu")])
        await q.message.edit_text("تاریخچه کدام گروه را پاک کنم؟ (پاک کردن باعث میشه دوباره بتونی ان افراد رو ادد کنی)", reply_markup=InlineKeyboardMarkup(buttons))
        return

    if d.startswith("clr_add_"):
        gid_key = d[len("clr_add_"):]
        hist = load_added_history()
        if gid_key in hist:
            del hist[gid_key]
            save_added_history(hist)
        await q.answer("تاریخچه آن گروه پاک شد.", show_alert=True)
        await q.message.edit_text("✅ تاریخچه تکراری پاک شد.", reply_markup=main_menu())
        return

    if d == "download_csv":
        users, gname, gid = load_scraped()
        if not users:
            await q.answer("لیست خالی است!", show_alert=True)
            return
        out = io.StringIO()
        keys = list(users[0].keys())
        w = csv.DictWriter(out, fieldnames=keys)
        w.writeheader()
        w.writerows(users)
        csv_bytes = out.getvalue().encode("utf-8-sig")
        await app.send_document(
            ADMIN_ID,
            io.BytesIO(csv_bytes),
            file_name=f"scraped_{int(time.time())}.csv",
            caption=f"📥 لیست کامل {len(users)} مخاطب"
        )
        await q.answer("فایل ارسال شد!", show_alert=True)
        return

    if d == "noop":
        await q.answer()
        return

    # ==================== آمار اکانت‌های اضافه کننده ====================
    if d == "adder_stats":
        limits = load_adder_limits()
        text = f"📈 <b>آمار اکانت‌های اضافه کننده</b>\n━━━━━━━━━━━━━━━━━━\n"
        text += f"🚨 سقف مجاز هر اکانت: <b>{MAX_ADD_PER_ACCOUNT} نفر</b>\n\n"
        total_used = 0; total_cap = 0
        if not limits:
            text += "هنوز هیچ اکانت برای اضافه کردن استفاده نشده ✨"
        else:
            accs = load_accounts()
            for phone, info in limits.items():
                count = info.get("added", 0)
                total_used += count; total_cap += MAX_ADD_PER_ACCOUNT
                remaining = MAX_ADD_PER_ACCOUNT - count
                status = "✅ سالم" if remaining > 0 else "⚠️ پر شد"
                last_use = info.get("last_used", 0)
                last_str = time.strftime("%Y-%m-%d %H:%M", time.localtime(last_use)) if last_use else "-"
                name = accs.get(phone, {}).get("name", "")
                bar_len = 12
                filled = int(bar_len * min(count, MAX_ADD_PER_ACCOUNT) / MAX_ADD_PER_ACCOUNT)
                bar = "🟩" * filled + "⬜" * (bar_len - filled)
                text += f"📱 <code>{phone}</code>"
                if name: text += f" ({name})"
                text += "\n"
                text += f"   {bar} {count}/{MAX_ADD_PER_ACCOUNT}\n"
                text += f"   └ وضعیت: {status} · آخرین استفاده: {last_str}\n\n"
            text += f"📊 مجموع ظرفیت استفاده شده: <b>{total_used}/{total_cap}</b>"
        buttons = [[InlineKeyboardButton("🔄 ریست آمار یک اکانت", callback_data="reset_adder_pick")]]
        buttons.append([InlineKeyboardButton("🗑️ ریست کامل همه آمار", callback_data="reset_adder_all")])
        buttons.append(_sub_back_btn(target="menu_stats"))
        await q.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
        return

    if d == "reset_adder_pick":
        limits = load_adder_limits()
        if not limits:
            await q.answer("هیچ اکانتی ثبت نشده.", show_alert=True)
            return
        buttons = []
        for phone in limits.keys():
            buttons.append([InlineKeyboardButton(f"❌ {phone}", callback_data=f"reset_add_{phone}")])
        buttons.append([InlineKeyboardButton("🔙 بازگشت", callback_data="adder_stats")])
        await q.message.edit_text("اکانت مورد نظر برای ریست را انتخاب کنید:", reply_markup=InlineKeyboardMarkup(buttons))
        return

    if d.startswith("reset_add_"):
        phone = d[len("reset_add_"):]
        limits = load_adder_limits()
        if phone in limits:
            del limits[phone]
            save_adder_limits(limits)
            await q.answer(f"آمار {phone} ریست شد.", show_alert=True)
        await q.message.edit_text("✅ آمار ریست شد.", reply_markup=main_menu())
        return

    if d == "reset_adder_all":
        save_adder_limits({})
        await q.answer("همه آمار ریست شد.", show_alert=True)
        await q.message.edit_text("✅ تمام آمار اضافه کردن پاک شد.", reply_markup=main_menu())
        return

    # ==================== اسکن خودکار پس‌زمینه ====================
    if d == "bg_menu":
        st = get_bg_scan()
        accs = list_saved_accounts()
        cfg = _db_get_config()
        icon = "🟢" if st.get("enabled") else "🔴"
        text = f"⏱️ <b>اسکن خودکار پس‌زمینه</b>\n\n"
        text += f"وضعیت: {icon} {'روشن' if st.get('enabled') else 'خاموش'}\n"
        text += f"👤 اکانت انتخابی: <code>{st.get('account_phone') or '—'}</code>\n"
        text += f"👥 گروه هدف: {cfg.get('group_name') or '—'}\n"
        text += f"⏰ فاصله اسکن: {st.get('interval_minutes',60)} دقیقه\n"
        text += f"🕐 آخرین اجرا: {'ندارد' if not st.get('last_run') else time.strftime('%Y-%m-%d %H:%M', time.localtime(st['last_run']))}\n"
        text += f"👥 مجموع پیدا شده تا کنون: {st.get('total_found',0)}\n"
        text += f"📊 وضعیت فعلی: {st.get('status','idle')}\n\n"
        if not st.get("account_phone"):
            text += "⚠️ هنوز اکانت برای اسکن خودکار انتخاب نکردی.\n"
        if not cfg.get("group_id"):
            text += "⚠️ هنوز گروه هدف انتخاب نشده.\n"
        text += "\n💾 تمام داده‌ها در دیتابیس ابری Neon ذخیره می‌شوند، حتی با ریست رندر پاک نمی‌شوند."
        buttons = []
        if accs:
            for phone in accs.keys():
                sel = "✅" if st.get("account_phone") == phone else "⚪"
                buttons.append([InlineKeyboardButton(f"{sel} انتخاب {phone} بعنوان اکانت اصلی", callback_data=f"bg_acc_{phone}")])
        if cfg.get("group_id"):
            buttons.append([InlineKeyboardButton(
                f"{'🔴 خاموش' if st.get('enabled') else '🟢 روشن'} کردن اسکن خودکار",
                callback_data="bg_toggle")])
        iv_opts = [
            InlineKeyboardButton("⏱ ۳۰دقیقه", callback_data="bg_iv_30"),
            InlineKeyboardButton("⏱ ۱ساعت", callback_data="bg_iv_60"),
            InlineKeyboardButton("⏱ ۲ساعت", callback_data="bg_iv_120"),
            InlineKeyboardButton("⏱ ۴ساعت", callback_data="bg_iv_240"),
        ]
        buttons.append(iv_opts)
        buttons.append([InlineKeyboardButton("🔙 بازگشت", callback_data="home")])
        await q.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
        return

    if d.startswith("bg_acc_"):
        phone = d[len("bg_acc_"):]
        cfg = _db_get_config()
        set_bg_scan(True, target_group_id=cfg.get("group_id"), account_phone=phone,
                    interval_minutes=get_bg_scan().get("interval_minutes",60))
        set_owner_phone(phone)
        await q.answer(f"اکانت {phone} به عنوان اکانت اصلی اسکن خودکار انتخاب شد.", show_alert=True)
        q.data = "bg_menu"
        # fallthrough to redraw menu
        pass

    if d == "bg_toggle":
        st = get_bg_scan()
        if not st.get("account_phone"):
            await q.answer("اول یک اکانت انتخاب کن.", show_alert=True)
            return
        cfg = _db_get_config()
        if not cfg.get("group_id"):
            await q.answer("اول گروه محافظت شده/هدف را انتخاب کن.", show_alert=True)
            return
        set_bg_scan(not st.get("enabled"), target_group_id=cfg.get("group_id"),
                   account_phone=st.get("account_phone"), interval_minutes=st.get("interval_minutes",60))
        new_state = "روشن" if not st.get("enabled") else "خاموش"
        await q.answer(f"اسکن خودکار {new_state} شد.", show_alert=True)
        q.data = "bg_menu"
        pass

    if d.startswith("bg_iv_"):
        mins = int(d.split("_")[2])
        st = get_bg_scan()
        set_bg_scan(st.get("enabled",False), target_group_id=st.get("target_group_id"),
                   account_phone=st.get("account_phone"), interval_minutes=mins)
        await q.answer(f"فاصله اسکن: هر {mins} دقیقه", show_alert=False)
        q.data = "bg_menu"
        pass

    # ==================== پروژه یاب اوپن‌سورس ====================
    if d == "pf_menu":
        cats = projects_by_category()
        st = pf_state()
        total = sum(len(v) for v in cats.values())
        text = f"🔭 <b>پروژه‌یاب اوپن‌سورس</b>\n━━━━━━━━━━━━━━━━━━\n"
        text += f"🌐 در <b>گیت‌هاب</b> + <b>گیت‌لب</b> + <b>کدبرگ</b> می‌گردد\n"
        text += f"📦 لایسنس‌های آزاد و بدون‌لایسنس\n"
        text += f"📂 مجموع بایگانی: <b>{total}</b>\n"
        if st.get("last_scan"):
            from datetime import datetime, timezone
            dt = datetime.fromtimestamp(st["last_scan"], tz=timezone.utc)
            text += f"⏱️ آخرین اسکن: {dt.strftime('%Y-%m-%d %H:%M')} UTC\n"
        text += "━━━━━━━━━━━━━━━━━━\n"
        text += "<b>⚡ سریع:</b>"
        buttons = [
            [InlineKeyboardButton("🔥 ترند روز", callback_data="pf_scan_trending"),
             InlineKeyboardButton("🔍 جستجوی دلخواه", callback_data="pf_search")],
        ]
        buttons.append([InlineKeyboardButton("🚀 اسکن همه دسته‌ها", callback_data="pf_scan_all")])
        # Categories in two columns
        cat_list = list(PF_CATS.items())
        for i in range(0, len(cat_list), 2):
            row = []
            cid, info = cat_list[i]
            cnt = len(cats.get(cid, []))
            row.append(InlineKeyboardButton(f"{info['emoji']} {info['name'][:14]} ({cnt})", callback_data=f"pf_cat_{cid}"))
            if i+1 < len(cat_list):
                cid2, info2 = cat_list[i+1]
                cnt2 = len(cats.get(cid2, []))
                row.append(InlineKeyboardButton(f"{info2['emoji']} {info2['name'][:14]} ({cnt2})", callback_data=f"pf_cat_{cid2}"))
            buttons.append(row)
        # Saved custom searches & favorites
        custom = [x for x in (cats.get("custom") or [])]
        favs = fav_list()
        buttons.append([InlineKeyboardButton(f"⭐ علاقه‌مندی‌ها ({len(favs)})", callback_data="pf_favs"),
                        InlineKeyboardButton(f"🔍 جستجوهای من ({len(custom)})", callback_data="pf_custom_list")])
        buttons.append([InlineKeyboardButton("📥 دانلود CSV", callback_data="pf_export"),
                        InlineKeyboardButton("🗑️ پاک‌کردن", callback_data="pf_clear")])
        buttons.append([InlineKeyboardButton("🔙 بازگشت", callback_data="home")])
        await q.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
        return

    if d == "pf_search":
        atk_state["pf_step"] = "await_query"
        await q.message.edit_text(
            "🔍 <b>جستجوی دلخواه پروژه</b>\n\n"
            "کلمه کلیدی مورد نظر را بفرست (مثال: <code>voice changer</code>، <code>telegram ai bot</code>، <code>persian font</code>)،\n"
            "ربات در گیت‌هاب + گیت‌لب + کدبرگ می‌گردد و بهترین‌ها را مرتب بر اساس ستاره نمایش می‌دهد.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="pf_menu")]]))
        return

    if d == "pf_custom_list":
        custom = list({x["url"]:x for x in pf_load() if x.get("category")=="custom"}.values())
        custom.sort(key=lambda x: x.get("stars",0), reverse=True)
        if not custom:
            await q.answer("هنوز جستجوی دلخواهی نداشتی. از «🔍 جستجوی دلخواه» استفاده کن.", show_alert=True)
            return
        text = f"⭐ <b>لیست جستجوهای شما ({len(custom)})</b>\n\n"
        for i, it in enumerate(custom[:20], 1):
            plat = {"github":"🐙","gitlab":"🦊","codeberg":"🌿"}.get(it.get("platform",""),"")
            desc = (it.get("description") or "").strip()
            if len(desc) > 80: desc = desc[:80] + "…"
            qname = (it.get("query") or "")[:25]
            text += f"{i}. {plat} <a href=\"{it['url']}\"><b>{it.get('full_name','')}</b></a>\n"
            text += f"   ⭐ {it.get('stars',0):,} · {it.get('language','—')}\n"
            if qname: text += f"   🔎 {qname}\n"
            if desc: text += f"   └ {desc}\n\n"
        if len(custom) > 20:
            text += f"... و {len(custom)-20} مورد دیگر"
        buttons = [[InlineKeyboardButton("🔙 بازگشت", callback_data="pf_menu")]]
        await q.message.edit_text(text, disable_web_page_preview=True, reply_markup=InlineKeyboardMarkup(buttons))
        return


    if d == "pf_scan_trending":
        global pf_scanning
        if pf_scanning:
            await q.answer("اسکن دیگری هنوز در حال اجراست، چند ثانیه صبر کن.", show_alert=True)
            return
        pf_scanning = True
        status = await q.message.reply_text("🔥 در حال کشیدن لیست ترند روز گیت‌هاب...")
        try:
            loop = asyncio.get_running_loop()
            items = await loop.run_in_executor(None, search_trending_github)
            new_items = merge_new(items)
            text = f"🔥 <b>ترند روز گیت‌هاب</b>\n"
            text += f"✅ مجموع {len(items)} پروژه ترند، {len(new_items)} مورد جدید:\n\n"
            for i, it in enumerate(items[:15], 1):
                today = it.get("stars_today", 0)
                desc = it.get("description","").strip()
                if len(desc) > 80: desc = desc[:80] + "…"
                text += f"{i}. <a href=\"{it['url']}\"><b>{it['full_name']}</b></a>\n"
                text += f"   ⭐ {it['stars']:,} (+{today:,} امروز) · {it['language']}\n"
                if desc:
                    text += f"   └ {desc}\n"
                text += "\n"
            await status.edit_text(text, disable_web_page_preview=True,
                                   reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت به منوی پروژه‌ها", callback_data="pf_menu")]]))
        except Exception as e:
            await status.edit_text(f"❌ خطا: {e}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="pf_menu")]]))
        finally:
            pf_scanning = False
        return

    if d.startswith("pf_cat_"):
        cat_id = d[len("pf_cat_"):]
        cats = projects_by_category()
        items = cats.get(cat_id, [])
        info = PF_CATS.get(cat_id, {})
        page_key = f"pf_page_{cat_id}"
        page = atk_state.get(page_key, 0)
        per_page = 8
        total_pages = max(1, (len(items)+per_page-1)//per_page)
        start = page*per_page
        chunk = items[start:start+per_page]
        text = f"{info.get('emoji','')} <b>{info.get('name','')}</b> — صفحه {page+1}/{total_pages}\n\n"
        if not chunk:
            text += "⚠️ هنوز اسکن نشده. اول دکمه «🔄 اسکن این دسته» رو بزن.\n"
        else:
            for i, it in enumerate(chunk, start+1):
                plat = {"github":"🐙","gitlab":"🦊","codeberg":"🌿"}.get(it["platform"],"")
                desc = (it.get("description") or "").strip()
                if len(desc) > 90: desc = desc[:90] + "…"
                age = to_jalali_age(it.get("updated_at","")) if it.get("updated_at") else ""
                text += f"{i}. {plat} <a href=\"{it['url']}\"><b>{it['full_name']}</b></a>\n"
                text += f"   ⭐ {it['stars']:,} · 🍴 {it['forks']:,} · {it['language']}\n"
                if it.get("license") and it["license"] != "—":
                    text += f"   📜 {it['license']} · "
                if age:
                    text += f"🕒 {age}\n"
                if desc:
                    text += f"   └ {desc}\n"
                text += "\n"
        buttons = []
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton("⬅️ قبلی", callback_data=f"pf_prev_{cat_id}"))
        if page < total_pages-1:
            nav.append(InlineKeyboardButton("بعدی ➡️", callback_data=f"pf_next_{cat_id}"))
        if nav: buttons.append(nav)
        # Star buttons for first 8 items
        star_row1 = []
        for idx, it in enumerate(chunk[:4]):
            lbl = "⭐" if not is_fav(it['url']) else "🌟"
            star_row1.append(InlineKeyboardButton(f"{lbl}{idx+1}", callback_data=f"pf_fav_{it['url']}"))
        if star_row1: buttons.append(star_row1)
        star_row2 = []
        for idx, it in enumerate(chunk[4:8]):
            lbl = "⭐" if not is_fav(it['url']) else "🌟"
            star_row2.append(InlineKeyboardButton(f"{lbl}{idx+5}", callback_data=f"pf_fav_{it['url']}"))
        if star_row2: buttons.append(star_row2)
        buttons.append([InlineKeyboardButton("🔄 اسکن این دسته", callback_data=f"pf_scan_{cat_id}"),
                        InlineKeyboardButton("🔍 جستجوی دلخواه", callback_data="pf_search")])
        buttons.append([InlineKeyboardButton("⭐ علاقه‌مندی‌ها", callback_data="pf_favs"),
                        InlineKeyboardButton("🔙 منوی پروژه", callback_data="pf_menu"),
                        InlineKeyboardButton("🏠 خانه", callback_data="home")])
        await q.message.edit_text(text, disable_web_page_preview=True, reply_markup=InlineKeyboardMarkup(buttons))
        return

    if d.startswith("pf_fav_"):
        url = d[len("pf_fav_"):]
        if is_fav(url):
            fav_remove(url)
            await q.answer("از علاقه‌مندی‌ها حذف شد ⭕", show_alert=False)
        else:
            fav_add(url)
            await q.answer("⭐ به علاقه‌مندی‌ها اضافه شد", show_alert=False)
        return

    if d == "pf_favs":
        urls = fav_list()
        all_proj = {p["url"]: p for p in pf_load()}
        favs = [all_proj[u] for u in urls if u in all_proj]
        favs.sort(key=lambda x: x.get("stars",0), reverse=True)
        text = f"⭐ <b>علاقه‌مندی‌های من</b> ({len(favs)})\n━━━━━━━━━━━━━━━━━━\n\n"
        if not favs:
            text += "هنوز پروژه‌ای را ستاره‌دار نکردی ✨\n"
            text += "در صفحات دسته‌بندی روی دکمه ⭐ کنار هر پروژه بزن تا ذخیره شود."
        else:
            for i, it in enumerate(favs[:20], 1):
                plat = {"github":"🐙","gitlab":"🦊","codeberg":"🌿"}.get(it.get("platform",""),"")
                desc = (it.get("description") or "").strip()
                if len(desc) > 70: desc = desc[:70] + "…"
                text += f"{i}. {plat} <a href=\"{it['url']}\"><b>{it.get('full_name','')}</b></a> ⭐{it.get('stars',0):,}\n"
                if desc: text += f"   └ {desc}\n"
                text += "\n"
            if len(favs) > 20: text += f"... و {len(favs)-20} مورد دیگر"
        btns = []
        for it in favs[:8]:
            nm = (it.get('full_name','') or '')[:28]
            btns.append([InlineKeyboardButton(f"❌ حذف {nm}", callback_data=f"pf_fav_{it['url']}")])
        btns.append([InlineKeyboardButton("🔙 بازگشت به منوی پروژه‌ها", callback_data="pf_menu")])
        await q.message.edit_text(text, disable_web_page_preview=True, reply_markup=InlineKeyboardMarkup(btns))
        return

    if d.startswith("pf_next_") or d.startswith("pf_prev_"):
        cat_id = d.split("_", 2)[2]
        key = f"pf_page_{cat_id}"
        cur = atk_state.get(key, 0)
        if d.startswith("pf_next_"):
            atk_state[key] = cur + 1
        else:
            atk_state[key] = max(0, cur - 1)
        # re-render the cat page inline
        cats = projects_by_category()
        items = cats.get(cat_id, [])
        info = PF_CATS.get(cat_id, {})
        page = atk_state[key]
        per_page = 8
        total_pages = max(1, (len(items)+per_page-1)//per_page)
        if page >= total_pages:
            page = total_pages - 1
            atk_state[key] = page
        start = page*per_page
        chunk = items[start:start+per_page]
        text = f"{info.get('emoji','')} <b>{info.get('name','')}</b> — صفحه {page+1}/{total_pages}\n\n"
        if not chunk:
            text += "⚠️ هنوز اسکن نشده. اول دکمه «🔄 اسکن این دسته» رو بزن.\n"
        else:
            for i, it in enumerate(chunk, start+1):
                plat = {"github":"🐙","gitlab":"🦊","codeberg":"🌿"}.get(it["platform"],"")
                desc = (it.get("description") or "").strip()
                if len(desc) > 90: desc = desc[:90] + "…"
                age = to_jalali_age(it.get("updated_at","")) if it.get("updated_at") else ""
                text += f"{i}. {plat} <a href=\"{it['url']}\"><b>{it['full_name']}</b></a>\n"
                text += f"   ⭐ {it['stars']:,} · 🍴 {it['forks']:,} · {it['language']}\n"
                if it.get("license") and it["license"] != "—":
                    text += f"   📜 {it['license']} · "
                if age:
                    text += f"🕒 {age}\n"
                if desc:
                    text += f"   └ {desc}\n"
                text += "\n"
        buttons = []
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton("⬅️ قبلی", callback_data=f"pf_prev_{cat_id}"))
        if page < total_pages-1:
            nav.append(InlineKeyboardButton("بعدی ➡️", callback_data=f"pf_next_{cat_id}"))
        if nav: buttons.append(nav)
        # Star buttons for first 8 items
        star_row1 = []
        for idx, it in enumerate(chunk[:4]):
            lbl = "⭐" if not is_fav(it['url']) else "🌟"
            star_row1.append(InlineKeyboardButton(f"{lbl}{idx+1}", callback_data=f"pf_fav_{it['url']}"))
        if star_row1: buttons.append(star_row1)
        star_row2 = []
        for idx, it in enumerate(chunk[4:8]):
            lbl = "⭐" if not is_fav(it['url']) else "🌟"
            star_row2.append(InlineKeyboardButton(f"{lbl}{idx+5}", callback_data=f"pf_fav_{it['url']}"))
        if star_row2: buttons.append(star_row2)
        buttons.append([InlineKeyboardButton("🔄 اسکن این دسته", callback_data=f"pf_scan_{cat_id}"),
                        InlineKeyboardButton("🔍 جستجوی دلخواه", callback_data="pf_search")])
        buttons.append([InlineKeyboardButton("⭐ علاقه‌مندی‌ها", callback_data="pf_favs"),
                        InlineKeyboardButton("🔙 منوی پروژه", callback_data="pf_menu"),
                        InlineKeyboardButton("🏠 خانه", callback_data="home")])
        await q.message.edit_text(text, disable_web_page_preview=True, reply_markup=InlineKeyboardMarkup(buttons))
        return

    # handle scan_{cat} and scan_all
    if d.startswith("pf_scan_") and not d == "pf_scan_all" and not d == "pf_scan_trending":
        cat_id = d[len("pf_scan_"):]
        if pf_scanning:
            await q.answer("اسکن دیگری هنوز در حال اجراست، صبر کن.", show_alert=True)
            return
        pf_scanning = True
        info = PF_CATS.get(cat_id, {"name": cat_id})
        status = await q.message.reply_text(f"{info.get('emoji','🔍')} در حال جستجو در {info['name']}...\n(گیت‌هاب + گیت‌لب + کدبرگ)\nچند لحظه صبر کن ⏳")
        try:
            loop = asyncio.get_running_loop()
            items = await loop.run_in_executor(None, lambda: scan_category(cat_id, min_stars=0, per_platform=8))
            new_items = merge_new(items)
            # Top 10 new items
            text = f"✅ <b>اسکن {info['name']} تمام شد</b>\n"
            text += f"🔍 مجموع پیدا شده: {len(items)}\n"
            text += f"🆕 مورد جدید: {len(new_items)}\n\n"
            top = sorted(items, key=lambda x: x.get("stars",0), reverse=True)[:10]
            for i, it in enumerate(top, 1):
                plat = {"github":"🐙","gitlab":"🦊","codeberg":"🌿"}.get(it["platform"],"")
                desc = (it.get("description") or "").strip()
                if len(desc) > 80: desc = desc[:80] + "…"
                text += f"{i}. {plat} <a href=\"{it['url']}\"><b>{it['full_name']}</b></a>\n"
                text += f"   ⭐ {it['stars']:,} · {it['language']}\n"
                if desc:
                    text += f"   └ {desc}\n\n"
            text += "از دکمه دسته‌بندی در منوی اصلی می‌توانی لیست کامل را صفحه‌صفحه ببینی."
            await status.edit_text(text, disable_web_page_preview=True,
                                   reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 منوی پروژه‌ها", callback_data="pf_menu")]]))
        except Exception as e:
            await status.edit_text(f"❌ خطا در اسکن: {e}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="pf_menu")]]))
        finally:
            pf_scanning = False
        return

    if d == "pf_scan_all":
        if pf_scanning:
            await q.answer("اسکن دیگری در حال اجراست.", show_alert=True)
            return
        pf_scanning = True
        status = await q.message.reply_text(f"🚀 <b>اسکن کامل همه دسته‌ها آغاز شد</b>\n{len(PF_CATS)} دسته × ۳ پلتفرم\nحدود ۱-۲ دقیقه طول می‌کشه، لطفا صبر کن...\n\n"
                                            "در حال پردازش: ...")
        all_items = []
        total_new = 0
        try:
            loop = asyncio.get_running_loop()
            cids = list(PF_CATS.keys())
            for idx, cid in enumerate(cids, 1):
                info = PF_CATS[cid]
                try:
                    await status.edit_text(f"🚀 <b>اسکن کامل همه دسته‌ها ({idx}/{len(cids)})</b>\n"
                                           f"در حال جستجو در: {info['emoji']} {info['name']}\n"
                                           f"⏳ تا کنون: {len(all_items)} پروژه پیدا شده")
                except: pass
                items = await loop.run_in_executor(None, lambda c=cid: scan_category(c, min_stars=0, per_platform=6))
                new = merge_new(items)
                all_items.extend(items)
                total_new += len(new)
                await asyncio.sleep(1.5)
            text = f"✅ <b>اسکن کامل تمام شد!</b>\n\n"
            text += f"📦 مجموع پروژه‌های پیدا شده: {len(all_items)}\n"
            text += f"🆕 موارد جدید این اسکن: {total_new}\n\n"
            text += "<b>🔝 برترین‌های این اسکن:</b>\n"
            top = sorted(all_items, key=lambda x: x.get("stars",0), reverse=True)[:15]
            for i, it in enumerate(top, 1):
                plat = {"github":"🐙","gitlab":"🦊","codeberg":"🌿"}.get(it["platform"],"")
                desc = (it.get("description") or "").strip()
                if len(desc) > 70: desc = desc[:70] + "…"
                text += f"{i}. {plat} <a href=\"{it['url']}\"><b>{it['full_name']}</b></a> ⭐{it['stars']:,} · {it['language']}\n"
                if desc: text += f"   └ {desc}\n"
            await status.edit_text(text, disable_web_page_preview=True,
                                   reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 منوی پروژه‌ها", callback_data="pf_menu")]]))
        except Exception as e:
            await status.edit_text(f"❌ خطا در اسکن کامل: {e}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="pf_menu")]]))
        finally:
            pf_scanning = False
        return

    if d == "pf_export":
        data = pf_load()
        if not data:
            await q.answer("هنوز هیچ پروژه‌ای بایگانی نشده است.", show_alert=True)
            return
        buf_bytes = pf_export()
        await app.send_document(ADMIN_ID, io.BytesIO(buf_bytes),
                                file_name=f"open_source_projects_{int(time.time())}.csv",
                                caption=f"📥 لیست کامل {len(data)} پروژه اوپن‌سورس")
        await q.answer("CSV ارسال شد ✅", show_alert=True)
        return

    if d == "pf_clear":
        pf_clear()
        await q.answer("بایگانی پروژه‌ها پاک شد.", show_alert=True)
        await q.message.edit_text("✅ بایگانی پروژه‌ها پاک شد.", reply_markup=main_menu())
        return

    # ==================== انتخاب هدف حمله از لیست ====================
    if d.startswith("atk_target_") and not d.startswith("atk_target_manual"):
        gid = int(d.split("_")[2])
        atk = atk_state.get("atk")
        if not atk:
            atk_state.clear()
            await q.answer("خطا در وضعیت، لطفا دوباره شروع کنید.", show_alert=True)
            await q.message.edit_text("منوی اصلی:", reply_markup=main_menu())
            return
        try:
            target = await atk.app.get_chat(gid)
        except Exception as e:
            await q.answer(f"خطا در بارگذاری گروه: {str(e)}", show_alert=True)
            return
        await q.answer()
        prog = await q.message.edit_text(f"🎯 هدف: {target.title}\n🚀 در حال شروع حمله...")
        async def run():
            progress_msg = prog
            stop_btn = InlineKeyboardMarkup([[InlineKeyboardButton("⏹️ توقف عملیات", callback_data="stop_op")]])
            async def on_progress(text):
                try:
                    nonlocal progress_msg
                    await progress_msg.edit_text(text, reply_markup=stop_btn, disable_web_page_preview=True)
                except Exception:
                    pass
            async def incremental_save(user_list):
                try:
                    # ذخیره تدریجی در دیتابیس
                    save_scraped(user_list, target.title, target.id)
                except Exception:
                    pass
            try:
                users = await atk.run_full_scrape(target.id, progress_cb=on_progress, incremental_save_cb=incremental_save)
                csv_bytes = atk.export_csv()
                save_scraped(users, target.title, target.id)
                await app.send_message(ADMIN_ID, f"✅ حمله تمام شد!\nگروه: {target.title}\nتعداد استخراج: {len(users)} نفر\n\n📋 از دکمه «لیست مخاطبان استخراج شده» در منو می‌توانید ببینید.")
                await app.send_document(ADMIN_ID, io.BytesIO(csv_bytes), file_name=f"result_{int(time.time())}.csv")
                try:
                    await atk.disconnect()
                except:
                    pass
            except Exception as e:
                err_text = str(e)
                fail_msg = f"❌ خطا در حمله:\n{err_text}"
                low_err = err_text.lower()
                if "عضو" in err_text or "پیدا نشد" in err_text or "chat_invalid" in low_err or "peer" in low_err or "not found" in low_err:
                    fail_msg += "\n\n💡 لطفا الان در تلگرام دستی آن گروه را **باز کنید و یک بار اسکرول کنید** تا اطلاعات گروه لود شود، سپس روی دکمه پایین بزنید:"
                    retry_btns = InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔄 گروه را باز کردم، دوباره امتحان کن", callback_data=f"retry_attack_{gid}")],
                        [InlineKeyboardButton("🔙 بازگشت به منو", callback_data="home")]
                    ])
                    await app.send_message(ADMIN_ID, fail_msg, reply_markup=retry_btns)
                else:
                    await app.send_message(ADMIN_ID, fail_msg)
            try:
                atk_state.clear()
            except:
                pass
            await app.send_message(ADMIN_ID, "منوی اصلی:", reply_markup=main_menu())
        asyncio.create_task(run())
        return

    # رتری کردن حمله بعد از اینکه کاربر دستی به گروه رفت
    if d.startswith("retry_attack_"):
        gid = int(d.split("_")[2])
        atk = atk_state.get("atk")
        phone = atk_state.get("phone")
        if not atk and not phone:
            await q.answer("وضعیت از دست رفت، لطفا دوباره از منو شروع کنید.", show_alert=True)
            await q.message.edit_text("به منو باز می‌گردیم...", reply_markup=main_menu())
            return
        await q.answer("در حال تلاش مجدد، لطفا صبر کنید...", show_alert=False)
        await q.message.edit_text("🔄 در حال تلاش مجدد برای اسکن...")
        if not atk:
            try:
                atk = AdvancedScraper("atk_retry", API_ID, API_HASH, phone=phone)
                await robust_connect(atk)
                atk_state["atk"] = atk
            except Exception as e:
                await q.message.edit_text(f"❌ خطا در اتصال مجدد: {str(e)}", reply_markup=main_menu())
                return
        async def run_retry():
            try:
                for _ in range(2):
                    async for _ in atk.app.get_dialogs(limit=2000):
                        pass
                    await asyncio.sleep(3)
                try:
                    tchat = await atk.app.get_chat(gid)
                    tname = tchat.title
                except:
                    tname = "گروه هدف"
                progress_msg = q.message
                stop_btn = InlineKeyboardMarkup([[InlineKeyboardButton("⏹️ توقف عملیات", callback_data="stop_op")]])
                async def on_progress(text):
                    nonlocal progress_msg
                    try:
                        await progress_msg.edit_text(f"🔄 تلاش مجدد\n{text}", reply_markup=stop_btn, disable_web_page_preview=True)
                    except: pass
                async def inc_save(user_list):
                    try: save_scraped(user_list, tname, gid)
                    except: pass
                users = await atk.run_full_scrape(gid, progress_cb=on_progress, incremental_save_cb=inc_save)
                csv_bytes = atk.export_csv()
                save_scraped(users, tname, gid)
                await app.send_message(ADMIN_ID, f"✅ تلاش مجدد موفق!\nگروه: {tname}\nتعداد استخراج: {len(users)} نفر")
                await app.send_document(ADMIN_ID, io.BytesIO(csv_bytes), file_name=f"result_{int(time.time())}.csv")
                try:
                    await atk.disconnect()
                except:
                    pass
            except Exception as e:
                err_text = str(e)
                fail_msg = f"❌ هنوز خطا وجود دارد:\n{err_text}\n\n🔹 نکته: مطمئن شوید واقعا در گروه عضو هستید و در تلگرام اجازه دیدن لیست اعضا را دارید."
                await app.send_message(ADMIN_ID, fail_msg,
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔄 دوباره امتحان", callback_data=f"retry_attack_{gid}")],
                        [InlineKeyboardButton("🔙 منوی اصلی", callback_data="home")]
                    ]))
            try:
                atk_state.clear()
            except:
                pass
            await app.send_message(ADMIN_ID, "منوی اصلی:", reply_markup=main_menu())
        asyncio.create_task(run_retry())
        return

    if d == "atk_target_manual":
        await q.answer()
        atk_state["step"] = "target"
        await q.message.edit_text(
            "✍️ آیدی عددی یا یوزرنیم گروه هدف را بفرستید:\n"
            "مثال عددی: `-1002790821974`\n"
            "مثال یوزرنیم: `@MyGroup`"
        )
        return

    # ==================== انتخاب هدف اضافه کردن عضو از لیست ====================
    if d.startswith("add_target_") and not d.startswith("add_target_manual"):
        gid = int(d.split("_")[2])
        add_client = atk_state.get("add_client")
        if not add_client:
            atk_state.clear()
            await q.answer("خطا!", show_alert=True)
            await q.message.edit_text("منوی اصلی:", reply_markup=main_menu())
            return
        try:
            target = await add_client.app.get_chat(gid)
        except Exception as e:
            await q.answer(f"خطا: {str(e)}", show_alert=True)
            return
        atk_state["target_add_gid"] = gid
        atk_state["target_add_name"] = target.title
        already = atk_state.get("already_added", 0)
        remaining = MAX_ADD_PER_ACCOUNT - already
        is_channel = str(target.type).lower() == "chattype.channel" and not getattr(target, 'megagroup', False)
        chat_type_label = "📡 کانال" if is_channel else "👥 گروه"
        
        # Count available users in DB
        total_in_db = _db_count_users()
        
        await q.answer()
        await q.message.edit_text(
            f"✅ مقصد: {chat_type_label} <b>{target.title}</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📦 کاربران در دیتابیس: <b>{total_in_db:,}</b>\n"
            f"⚠️ ظرفیت باقیمانده: <b>{remaining}</b> نفر\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"<b>منبع کاربران:</b>",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(f"🌐 همه کاربران ({total_in_db:,})", callback_data=f"dir_add_all_{gid}")],
                [InlineKeyboardButton("📂 انتخاب از دسته‌بندی", callback_data=f"dir_add_cat_{gid}")],
                [InlineKeyboardButton("👥 انتخاب از چت خاص", callback_data=f"dir_add_chat_{gid}")],
                [InlineKeyboardButton("📄 آپلود فایل CSV", callback_data=f"csv_add_{gid}")],
                _sub_back_btn(target="home")[0],
            ]),
            disable_web_page_preview=True)
        return

    if d == "add_target_manual":
        await q.answer()
        atk_state["step"] = "adder_target_manual"
        await q.message.edit_text("✍️ آیدی عددی گروه مقصد را بفرستید (با -100 شروع می‌شود):")
        return

    # ==================== 🆕 Direct Add from Database ====================
    if d.startswith("dir_add_all_"):
        gid = int(d.split("_")[3])
        atk_state["add_source"] = "all"
        atk_state["add_source_id"] = None
        await _start_direct_add(q, gid)
        return

    if d.startswith("dir_add_cat_"):
        gid = int(d.split("_")[3])
        cats = get_all_categories()
        text = "📂 <b>انتخاب دسته‌بندی</b>\n\n"
        buttons = []
        for c in cats[:12]:
            cnt = count_users_by_source(category=c)
            if cnt > 0:
                text += f"📁 {c}: {cnt:,} کاربر\n"
                buttons.append([InlineKeyboardButton(f"📁 {c} ({cnt:,})", callback_data=f"dir_add_do_{gid}_cat_{c}")])
        if not buttons:
            await q.answer("هیچ دسته‌بندی با کاربر پیدا نشد!", show_alert=True)
            q.data = f"add_target_{gid}"
            return
        buttons.append(_sub_back_btn(target=f"add_target_{gid}"))
        await q.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons), disable_web_page_preview=True)
        return

    if d.startswith("dir_add_chat_"):
        gid = int(d.split("_")[3])
        chats = get_scanned_chats()
        text = "👥 <b>انتخاب چت مبدا</b>\n\n"
        buttons = []
        for ch in chats[:15]:
            cnt = count_users_by_source(source_chat_id=ch["chat_id"])
            icon = _chat_type_icon(ch.get("chat_type",""))
            if cnt > 0:
                text += f"{icon} {ch['chat_name'][:30]}: {cnt:,} کاربر\n"
                buttons.append([InlineKeyboardButton(
                    f"{icon} {ch['chat_name'][:25]} ({cnt:,})",
                    callback_data=f"dir_add_do_{gid}_src_{ch['chat_id']}"
                )])
        if not buttons:
            await q.answer("هیچ چتی با کاربر پیدا نشد!", show_alert=True)
            q.data = f"add_target_{gid}"
            return
        buttons.append(_sub_back_btn(target=f"add_target_{gid}"))
        await q.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons), disable_web_page_preview=True)
        return

    if d.startswith("dir_add_do_"):
        parts = d.split("_")
        gid = int(parts[3])
        src_type = parts[4]
        if src_type == "cat":
            cat_name = "_".join(parts[5:])
            atk_state["add_source"] = "category"
            atk_state["add_source_id"] = cat_name
        elif src_type == "src":
            src_id = int(parts[5])
            atk_state["add_source"] = "chat"
            atk_state["add_source_id"] = src_id
        await _start_direct_add(q, gid)
        return

    if d == "csv_add":
        gid = int(d.split("_")[2])
        atk_state["step"] = "adder_file"
        already = atk_state.get("already_added", 0)
        remaining = MAX_ADD_PER_ACCOUNT - already
        await q.message.edit_text(
            f"📄 آپلود فایل CSV\n\n"
            f"⚠️ ظرفیت: {remaining} نفر\n"
            f"فایل CSV رو بفرست:",
            reply_markup=InlineKeyboardMarkup([_sub_back_btn(target=f"add_target_{gid}")]))
        return

    # ==================== مدیریت اکانت های ذخیره شده ====================
    if d == "manage_accounts":
        accounts = list_saved_accounts()
        text = f"📱 <b>مدیریت اکانت‌های ذخیره شده</b>\n━━━━━━━━━━━━━━━━━━\n"
        text += f"تعداد: <b>{len(accounts)}</b> اکانت فعال\n"
        text += f"💾 سشن‌ها در دیتابیس ابری بکاپ هستند\n\n"
        if not accounts:
            text += "⚠️ هنوز هیچ اکانتی ذخیره نشده.\nاولین اکانت خود را با دکمه زیر اضافه کن:\n"
        else:
            for phone, info in accounts.items():
                added_count = load_adder_limits().get(phone, {}).get("added", 0)
                name = info.get("name", "")
                added_at = info.get("added_at", 0)
                date_str = time.strftime("%Y-%m-%d", time.localtime(added_at)) if added_at else "-"
                cap = min(added_count, MAX_ADD_PER_ACCOUNT)
                filled = int(10 * cap / MAX_ADD_PER_ACCOUNT)
                bar = "🟩"*filled + "⬜"*(10-filled)
                own = "👈 شما" if phone == get_owner_phone() else ""
                text += f"📱 <code>{phone}</code> {own}\n"
                if name: text += f"   └ نام: {name}\n"
                text += f"   └ اضافه شده: {date_str}\n"
                text += f"   └ ادد: {bar} {added_count}/{MAX_ADD_PER_ACCOUNT}\n\n"
        buttons = []
        buttons.append([InlineKeyboardButton("➕ افزودن اکانت جدید", callback_data="add_new_account"),
                        InlineKeyboardButton("📤 بک‌آپ سشن", callback_data="acc_backup_pick")])
        buttons.append([InlineKeyboardButton("📥 آپلود فایل سشن (برای 2FA)", callback_data="acc_upload_session")])
        if accounts:
            buttons.append([InlineKeyboardButton("🗑️ حذف یک اکانت", callback_data="acc_delete_pick")])
        buttons.append(_sub_back_btn(target="menu_settings"))
        await q.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
        return

    if d == "acc_delete_pick":
        accounts = list_saved_accounts()
        buttons = []
        for phone in accounts:
            buttons.append([InlineKeyboardButton(f"❌ {phone}", callback_data=f"acc_del_{phone}")])
        buttons.append([InlineKeyboardButton("🔙 بازگشت", callback_data="manage_accounts")])
        await q.message.edit_text("اکانت مورد نظر برای حذف را انتخاب کنید:", reply_markup=InlineKeyboardMarkup(buttons))
        return

    if d.startswith("acc_del_"):
        phone = d[len("acc_del_"):]
        fname = safe_phone_filename(phone)
        for pattern in [f"acc_{fname}.session", f"acc_{fname}.session-journal"]:
            p = os.path.join(SESSIONS_DIR, pattern)
            if os.path.exists(p):
                os.remove(p)
        accs = load_accounts()
        if phone in accs:
            del accs[phone]
            save_accounts(accs)
        _db_delete_account(phone)
        await q.answer(f"اکانت {phone} حذف شد.", show_alert=True)
        await q.message.edit_text("✅ اکانت با موفقیت حذف شد.", reply_markup=main_menu())
        return

    if d == "acc_backup_pick":
        accounts = list_saved_accounts()
        buttons = []
        for phone in accounts:
            buttons.append([InlineKeyboardButton(f"📤 {phone}", callback_data=f"acc_back_{phone}")])
        buttons.append([InlineKeyboardButton("🔙 بازگشت", callback_data="manage_accounts")])
        await q.message.edit_text("فایل سشن کدام اکانت را بک آپ بگیرم؟", reply_markup=InlineKeyboardMarkup(buttons))
        return

    if d.startswith("acc_back_"):
        phone = d[len("acc_back_"):]
        fname = safe_phone_filename(phone)
        sfile = os.path.join(SESSIONS_DIR, f"acc_{fname}.session")
        if os.path.exists(sfile):
            await app.send_document(ADMIN_ID, sfile, caption=f"📤 فایل سشن بک آپ اکانت {phone}\nاین فایل را نگه دار، اگر سرور ری‌استارت کرد می‌توانی دوباره آپلود کنی بدون نیاز به کد.")
            await q.answer("فایل سشن در چت ارسال شد.", show_alert=True)
        else:
            await q.answer("فایل سشن پیدا نشد!", show_alert=True)
        return

    if d == "add_new_account":
        atk_state.clear()
        atk_state["step"] = "add_new_acc_phone"
        await q.message.edit_text("➕ افزودن اکانت جدید دائمی\n\n⚠️ نکته: درخواست کد زیاد پشت سر هم باعث فلود ۱۸ ساعته تلگرام میشود!\nاگر اکانت از قبل در لیست هست از آن استفاده کنید.\n\nشماره تلفن را با فرمت +98 بفرستید:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="manage_accounts")]]))
        return

    if d == "acc_upload_session":
        atk_state.clear()
        atk_state["step"] = "upload_session"
        await q.message.edit_text(
            "📥 <b>آپلود فایل سشن تلگرام</b>\n\n"
            "🔹 مخصوص اکانت‌های دارای <b>Google Authenticator/2FA</b>\n"
            "🔹 با یه اسکریپت ساده Pyrogram روی سیستم خودت لاگین کن\n"
            "🔹 فایل <code>.session</code> رو مستقیم اینجا آپلود کن\n\n"
            "<b>📋 روش دریافت فایل سشن:</b>\n"
            "<code>pip install pyrogram</code>\n\n"
            "بعد این اسکریپت رو اجرا کن (کد تلگرام + 2FA رو می‌پرسه):\n\n"
            "<pre>from pyrogram import Client\n"
            "app = Client('my_acc', api_id=6,\n"
            "    api_hash='eb06d4abfb49dc3eeb1aeb98ae0f581e')\n"
            "app.start()\n"
            "app.stop()  # فایل my_acc.session ساخته شد</pre>\n\n"
            "فایل <code>my_acc.session</code> رو همینجا بفرست.",
            reply_markup=InlineKeyboardMarkup([[_sub_back_btn(target="manage_accounts")[0]]]),
            disable_web_page_preview=True)
        return

    # ==================== انتخاب اکانت برای شروع عملیات ====================
    async def show_account_picker(callback, back_cb, mode_label):
        """نمایش لیست اکانت ها + گزینه افزودن اکانت جدید"""
        accounts = list_saved_accounts()
        text = f"{mode_label}\n\nلطفا اکانت مورد استفاده را انتخاب کنید:"
        buttons = []
        if accounts:
            limits = load_adder_limits()
            for phone, info in accounts.items():
                name = info.get("name", phone)
                added = limits.get(phone, {}).get("added", 0)
                status = ""
                if mode_label.startswith("➕") and added >= MAX_ADD_PER_ACCOUNT:
                    status = " ⚠️ پر"
                btn = InlineKeyboardButton(f"✅ {name} | {phone}{status}", callback_data=f"useacc_{callback}_{phone}")
                buttons.append([btn])
        buttons.append([InlineKeyboardButton("➕ افزودن اکانت جدید و استفاده", callback_data=f"newacc_{callback}")])
        buttons.append([InlineKeyboardButton("🔙 بازگشت", callback_data="home")])
        await q.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))

    if d == "pick_account_attack":
        await show_account_picker("attack", "home", "🚀 شروع تست حمله پیشرفته")
        return

    if d == "pick_account_add":
        limits = load_adder_limits()
        warn = ""
        full_count = sum(1 for p,i in limits.items() if i.get("added",0)>=MAX_ADD_PER_ACCOUNT)
        if full_count > 0:
            warn = f"\n⚠️ {full_count} اکانت به سقف {MAX_ADD_PER_ACCOUNT} نفر رسیده"
        await show_account_picker("add", "home", f"➕ شروع اضافه کردن اعضا{warn}")
        return

    # ==================== Parallel multi-account ====================
    if d == "par_pick_target_attack":
        accounts = list_saved_accounts()
        if len(accounts) < 2:
            await q.answer("حداقل به ۲ اکانت ذخیره شده نیاز هست.", show_alert=True)
            return
        atk_state["par_mode"] = "scrape"
        # Let user pick target group from dialogs of first account
        try:
            phone0 = accounts[0]
            accs = load_accounts()
            fp = accs.get(phone0, {}).get("device_fp") or random.choice(DEVICE_FP)
            from attacker import safe_phone_filename as spfn
            sess_path = os.path.join(SESSIONS_DIR, f"acc_{spfn(phone0)}")
            tmp = AdvancedScraper(sess_path, API_ID, API_HASH, device_fp=fp)
            await robust_connect(tmp)
            async for _ in tmp.app.get_dialogs(limit=2000):
                pass
            await asyncio.sleep(2)
            dialogs = []
            async for dlg in tmp.app.get_dialogs(limit=200):
                if dlg.chat and (dlg.chat.type.name in ("GROUP","SUPERGROUP","CHANNEL")) or (getattr(dlg.chat,"type",None) and "group" in str(dlg.chat.type).lower()):
                    try:
                        c = await tmp.app.get_chat(dlg.chat.id)
                        cnt = 0
                        try:
                            cnt = await tmp.app.get_chat_members_count(c.id)
                        except: pass
                        if cnt > 0:
                            dialogs.append((c.id, c.title, cnt))
                    except: pass
            try: await tmp.disconnect()
            except: pass
        except Exception as e:
            await q.answer(f"خطا در بارگذاری لیست گروه‌ها: {str(e)[:100]}", show_alert=True)
            return
        if not dialogs:
            await q.answer("گروهی پیدا نشد.", show_alert=True)
            return
        dialogs.sort(key=lambda x: -x[2])
        buttons = []
        for gid, gname, gcount in dialogs[:30]:
            buttons.append([InlineKeyboardButton(f"👥 {gname[:35]} | {gcount:,}", callback_data=f"par_target_{gid}")])
        buttons.append([InlineKeyboardButton("🔙 بازگشت", callback_data="home")])
        await q.message.edit_text(
            f"⚡ <b>حمله موازی با {len(accounts)} اکانت</b>\n\n"
            f"همه اکانت‌های ذخیره شده همزمان روی گروه هدف کار میکنند.\n"
            f"استراتژی‌ها بین اکانت‌ها تقسیم میشن تا نرخ موفقیت بیشتر بشه.\n\n"
            f"گروه هدف را انتخاب کنید:",
            reply_markup=InlineKeyboardMarkup(buttons))
        return

    if d == "par_pick_target_add":
        accounts = list_saved_accounts()
        if len(accounts) < 2:
            await q.answer("حداقل به ۲ اکانت ذخیره شده نیاز هست.", show_alert=True)
            return
        # Check limits
        limits = load_adder_limits()
        available = [p for p in accounts if limits.get(p,{}).get("added",0) < MAX_ADD_PER_ACCOUNT]
        if not available:
            await q.answer(f"همه اکانت‌ها به سقف {MAX_ADD_PER_ACCOUNT} رسیده‌اند! لطفا ریست آمار کنید.", show_alert=True)
            return
        atk_state["par_mode"] = "add"
        atk_state["par_add_accounts"] = available
        # Pick target group
        try:
            phone0 = available[0]
            accs = load_accounts()
            fp = accs.get(phone0, {}).get("device_fp") or random.choice(DEVICE_FP)
            from attacker import safe_phone_filename as spfn
            sess_path = os.path.join(SESSIONS_DIR, f"acc_{spfn(phone0)}")
            tmp = AdvancedScraper(sess_path, API_ID, API_HASH, device_fp=fp)
            await robust_connect(tmp)
            async for _ in tmp.app.get_dialogs(limit=2000):
                pass
            await asyncio.sleep(2)
            dialogs = []
            async for dlg in tmp.app.get_dialogs(limit=200):
                try:
                    c = await tmp.app.get_chat(dlg.chat.id)
                    ctype = str(getattr(c.type,"","")).lower()
                    if "group" in ctype or "channel" in ctype:
                        cnt = 0
                        try: cnt = await tmp.app.get_chat_members_count(c.id)
                        except: pass
                        dialogs.append((c.id, c.title, cnt))
                except: pass
            try: await tmp.disconnect()
            except: pass
        except Exception as e:
            await q.answer(f"خطا: {str(e)[:100]}", show_alert=True)
            return
        if not dialogs:
            await q.answer("گروهی پیدا نشد.", show_alert=True)
            return
        dialogs.sort(key=lambda x: -x[2])
        buttons = []
        for gid, gname, gcount in dialogs[:30]:
            buttons.append([InlineKeyboardButton(f"👥 {gname[:35]} | {gcount:,}", callback_data=f"par_add_target_{gid}")])
        buttons.append([InlineKeyboardButton("🔙 بازگشت", callback_data="home")])
        total_slots = sum(MAX_ADD_PER_ACCOUNT - limits.get(p,{}).get("added",0) for p in available)
        await q.message.edit_text(
            f"⚡ <b>اضافه کردن موازی با {len(available)} اکانت</b>\n\n"
            f"📦 ظرفیت کل در دسترس: <b>{total_slots}</b> نفر\n"
            f"هر اکانت حداکثر {MAX_ADD_PER_ACCOUNT} نفر ادد میکند.\n\n"
            f"گروه مقصد را انتخاب کنید:",
            reply_markup=InlineKeyboardMarkup(buttons))
        return

    if d.startswith("par_target_"):
        gid = int(d.split("_")[2])
        accounts = list_saved_accounts()
        parallel.reset_dash()
        prog = await q.message.edit_text(f"⚡ در حال شروع حمله موازی با {len(accounts)} اکانت روی گروه {gid}...")
        # Fetch group title
        try:
            phone0 = accounts[0]
            accs = load_accounts()
            fp = accs.get(phone0, {}).get("device_fp") or random.choice(DEVICE_FP)
            from attacker import safe_phone_filename as spfn
            sess_p = os.path.join(SESSIONS_DIR, f"acc_{spfn(phone0)}")
            _tmp = AdvancedScraper(sess_p, API_ID, API_HASH, device_fp=fp)
            await robust_connect(_tmp)
            _chat = await _tmp.app.get_chat(gid)
            gname = _chat.title or "گروه هدف"
            parallel.dash["chat_title"] = gname
            try: await _tmp.disconnect()
            except: pass
        except:
            gname = "گروه هدف"
        users_list, gname_old, _ = load_scraped()
        lock = asyncio.Lock()
        if isinstance(users_list, dict):
            users_store = dict(users_list)
        else:
            users_store = {}
            for u in users_list:
                try:
                    uid = int(u.get("user_id"))
                    users_store[uid] = u
                except:
                    pass

        async def on_progress(text):
            try:
                await prog.edit_text(text, disable_web_page_preview=True)
            except:
                pass

        async def run_par_scrape():
            try:
                await parallel.parallel_scrape(gid, accounts, progress_cb=on_progress,
                                               users_store=users_store, users_lock=lock)
                # Save final
                save_scraped(users_store, gname, gid)
                await prog.edit_text(
                    parallel.render_dashboard(final=True) +
                    f"\n\n✅ <b>مجموع {len(users_store):,} کاربر</b> در فایل ذخیره شد.\n"
                    f"از منوی «لیست مخاطبان» می‌توانی ببینی یا دانلود کنی.",
                    reply_markup=main_menu())
            except Exception as e:
                await prog.edit_text(f"❌ خطا در حمله موازی: {e}", reply_markup=main_menu())

        asyncio.create_task(run_par_scrape())
        return

    if d.startswith("par_add_target_"):
        gid = int(d.split("_")[3])
        accounts = atk_state.get("par_add_accounts", list_saved_accounts())
        users, gname, _ = load_scraped()
        if not users:
            await q.answer("هنوز هیچ مخاطبی استخراج نشده! اول حمله بزن.", show_alert=True)
            return
        uid_list = list(users.keys())
        random.shuffle(uid_list)
        parallel.reset_dash()
        prog = await q.message.edit_text(f"⚡ شروع ادد موازی {len(uid_list)} نفر با {len(accounts)} اکانت...")

        async def on_progress(text):
            try:
                await prog.edit_text(text, disable_web_page_preview=True)
            except:
                pass

        async def run_par_add():
            try:
                await parallel.parallel_add(
                    gid, uid_list, accounts,
                    adder_limits_load=load_adder_limits,
                    save_adder_limits_fn=save_adder_limits,
                    add_history_check=is_user_already_added,
                    mark_added=mark_user_as_added,
                    max_per_account=MAX_ADD_PER_ACCOUNT,
                    progress_cb=on_progress,
                )
                await prog.edit_text(
                    parallel.render_dashboard(final=True) +
                    "\n\n✅ عملیات موازی تمام شد.",
                    reply_markup=main_menu())
            except Exception as e:
                await prog.edit_text(f"❌ خطا: {e}", reply_markup=main_menu())

        asyncio.create_task(run_par_add())
        return

    if d.startswith("useacc_"):
        parts = d.split("_")
        mode = parts[1]
        phone = "_".join(parts[2:])
        await q.answer(f"در حال اتصال به {phone}...", show_alert=False)
        prog = await q.message.edit_text(f"🔐 در حال اتصال به اکانت ذخیره شده {phone}...")
        # بارگذاری فینگرپرینت ذخیره شده برای این اکانت (ثابت نگه داشتن دستگاه)
        accs = load_accounts()
        saved_fp = accs.get(phone, {}).get("device_fp")
        if not saved_fp:
            # برای اکانت های قدیمی که فینگر پرینت نداشتند، یک مورد ثابت انتخاب و ذخیره کن
            saved_fp = DEVICE_FP[0]
            accs.setdefault(phone, {})["device_fp"] = saved_fp
            save_accounts(accs)
        try:
            # مهم: دیگر دو بار باز و بسته نکن! یک بار مستقیم وصل شو و همان اتصال را استفاده کن
            if mode == "attack":
                working_client = AdvancedScraper("atk_session", API_ID, API_HASH, phone=phone, device_fp=saved_fp)
            else:
                working_client = AdvancedScraper("add_session", API_ID, API_HASH, phone=phone, device_fp=saved_fp)
            await robust_connect(working_client)
            me = await working_client.app.get_me()
        except (AuthKeyDuplicated, AuthKeyUnregistered, ConnectionError) as e:
            # سشن واقعا خراب است
            try:
                await working_client.disconnect()
            except:
                pass
            await asyncio.sleep(1)
            # یک بار دیگر با یک فینگرپرینت متفاوت امتحان کن
            try:
                alt_fp = random.choice([f for f in DEVICE_FP if f != saved_fp])
                if mode == "attack":
                    working_client = AdvancedScraper("atk_session2", API_ID, API_HASH, phone=phone, device_fp=alt_fp)
                else:
                    working_client = AdvancedScraper("add_session2", API_ID, API_HASH, phone=phone, device_fp=alt_fp)
                await robust_connect(working_client)
                me = await working_client.app.get_me()
                # موفق شد، فینگرپرینت جدید را ذخیره کن
                accs[phone]["device_fp"] = alt_fp
                save_accounts(accs)
            except Exception as e2:
                # واقعا منقضی شده
                fname = safe_phone_filename(phone)
                for pat in [f"acc_{fname}.session", f"acc_{fname}.session-journal"]:
                    p = os.path.join(SESSIONS_DIR, pat)
                    if os.path.exists(p):
                        os.remove(p)
                if phone in accs:
                    del accs[phone]
                    save_accounts(accs)
                _db_delete_account(phone)
                await prog.edit_text(f"⚠️ سشن اکانت {phone} واقعا منقضی شده بود، حذف شد. لطفا دوباره اکانت را اضافه کنید.", reply_markup=main_menu())
                return
        except Exception as e:
            try:
                await working_client.disconnect()
            except:
                pass
            # خطای موقتی است، سشن را حذف نکن! فقط به کاربر اطلاع بده
            await prog.edit_text(f"⚠️ خطای موقت در اتصال: {str(e)[:200]}\nلطفا یک دقیقه دیگر دوباره امتحان کنید.", reply_markup=main_menu())
            return
        # سشن سالم است، شروع عملیات - مهم: همان working_client را دوباره استفاده کن، دوباره نساز!
        if mode == "attack":
            atk_state.clear()
            atk_state["phone"] = phone
            atk_state["reuse_account"] = True
            atk = working_client  # از همین اتصال استفاده کن، دوباره وصل نشو!
            atk_state["atk"] = atk
            atk_state["st"] = prog
            atk_state["step"] = "after_login_attack"
            # حالا لیست گروه ها را نشان بده
            await prog.edit_text("✅ ورود با اکانت ذخیره شده موفق!\n🔄 در حال بارگذاری لیست گروه‌های شما...")
            group_list = await _fast_load_chats(atk)
            atk_state["available_groups"] = group_list
            if group_list:
                buttons = []
                for gname, gid, gcount, chtype in sorted(group_list, key=lambda x:-x[2]):
                    ch_icon = "📡" if chtype == "channel" else "👥"
                    buttons.append([InlineKeyboardButton(f"{ch_icon} {gname[:33]} | {gcount:,}", callback_data=f"atk_target_{gid}")])
                buttons.append([InlineKeyboardButton("✍️ وارد کردن دستی آیدی", callback_data="atk_target_manual")])
                await prog.edit_text(f"✅ اکانت {me.first_name} آماده است!\nلطفا گروه هدف را انتخاب کنید ({len(group_list)} گروه):", reply_markup=InlineKeyboardMarkup(buttons))
            else:
                atk_state["step"] = "target"
                await prog.edit_text(f"✅ اکانت {me.first_name} آماده است!\nحالا آیدی عددی گروه هدف را بفرستید:")
            return

        if mode == "add":
            atk_state.clear()
            atk_state["phone"] = phone
            atk_state["reuse_account"] = True
            limits = load_adder_limits()
            already = limits.get(phone, {}).get("added", 0)
            if already >= MAX_ADD_PER_ACCOUNT:
                try:
                    await working_client.disconnect()
                except:
                    pass
                await prog.edit_text(f"⚠️ این اکانت ({phone}) به سقف {MAX_ADD_PER_ACCOUNT} نفر رسیده!", reply_markup=main_menu())
                return
            atk_state["already_added"] = already
            add_client = working_client  # دوباره نساز! همین اتصل را استفاده کن
            atk_state["add_client"] = add_client
            atk_state["st"] = prog
            me = await add_client.app.get_me()
            await prog.edit_text(f"✅ ورود با اکانت ذخیره شده موفق! ({me.first_name})\n🔄 در حال بارگذاری لیست گروه‌ها...")
            add_groups = await _fast_load_chats(add_client)
            atk_state["available_add_groups"] = add_groups
            remaining = MAX_ADD_PER_ACCOUNT - already
            if add_groups:
                buttons = []
                for gname, gid, gcount, chtype in sorted(add_groups, key=lambda x:-x[2]):
                    ch_icon = "📡" if chtype == "channel" else "👥"
                    buttons.append([InlineKeyboardButton(f"➕ {ch_icon} {gname[:30]} | {gcount:,}", callback_data=f"add_target_{gid}")])
                buttons.append([InlineKeyboardButton("✍️ وارد کردن دستی آیدی", callback_data="add_target_manual")])
                await prog.edit_text(f"✅ آماده اضافه کردن! ظرفیت باقیمانده: {remaining} نفر\nگروه مقصد را انتخاب کنید:", reply_markup=InlineKeyboardMarkup(buttons))
            else:
                atk_state["step"] = "adder_target"
                await prog.edit_text(f"✅ آماده! ظرفیت باقیمانده: {remaining} نفر\nآیدی گروه مقصد را بفرستید:")
            return

    if d.startswith("newacc_"):
        mode = d.split("_")[1]
        atk_state.clear()
        atk_state["after_auth_mode"] = mode
        atk_state["step"] = "phone_new"
        await q.message.edit_text(f"➕ افزودن اکانت جدید\n\nشماره تلفن با فرمت +98 بفرستید:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="home")]]))
        return

    # ==================== مسیر قدیمی که دیگر استفاده نمی‌شود (فقط برای سازگاری) ====================
    if d == "attack":
        atk_state.clear()
        await show_account_picker("attack", "home", "🚀 شروع تست حمله پیشرفته")
        return

    if d == "add_members":
        atk_state.clear()
        await show_account_picker("add", "home", f"➕ شروع اضافه کردن اعضا")
        return

@app.on_message(filters.private & filters.user(ADMIN_ID) & (filters.text | filters.document) & ~filters.command("start"))
async def steps(c, m):
    try:
        await _steps_impl(c, m)
    except Exception as e:
        _log_err(e, "steps handler")
        try:
            await m.reply_text(f"❌ خطای داخلی:\n{type(e).__name__}: {str(e)[:300]}\n\nلطفا /start را بزنید.", reply_markup=main_menu())
        except: pass
        atk_state.clear()

async def _steps_impl(c, m):
    step = atk_state.get("step")
    hstep = atk_state.get("hunter_step")
    pf_step = atk_state.get("pf_step")

    # ========== Universal Downloader ==========
    msg_text = (m.text or m.caption or "").strip()
    urls_in_msg = URL_REGEX.findall(msg_text)
    dl_mode = atk_state.get("downloader_mode", False)
    if urls_in_msg and dl_mode:
        url = urls_in_msg[0]
        platform = detect_platform(url)
        stat = await m.reply_text(f"⬇️ در حال دریافت از <b>{platform}</b>...\nچند لحظه صبر کنید ⏳")
        try:
            loop = asyncio.get_running_loop()
            res = await loop.run_in_executor(None, lambda: fetch_media(url))
            if not res.get("ok"):
                await stat.edit_text(f"❌ خطا: {res.get('error','نامشخص')}")
                atk_state["downloader_mode"] = False
                return
            dl_url = res.get("download_url")
            if dl_url:
                await stat.edit_text("📥 در حال ارسال فایل به تلگرام...")
                try:
                    vid_plats = ("tiktok","instagram","youtube","twitter","reddit","aparat","coub","vimeo","pinterest")
                    aud_plats = ("soundcloud",)
                    caption = f"✅ دانلود از {platform}\n🔗 {url}"
                    if platform in vid_plats:
                        await app.send_video(ADMIN_ID, dl_url, caption=caption, supports_streaming=True)
                    elif platform in aud_plats:
                        await app.send_audio(ADMIN_ID, dl_url, caption=caption)
                    else:
                        await app.send_document(ADMIN_ID, dl_url, caption=caption)
                    await stat.delete()
                except Exception as e:
                    await stat.edit_text(f"⚠️ لینک آماده شد اما ارسال مستقیم خطا داد:\n<code>{str(e)[:150]}</code>\n\n🔗 لینک دانلود:\n{dl_url}")
            elif res.get("picker"):
                text = f"📸 آلبوم چندتایی ({len(res['picker'])} مورد):\n\n"
                for i, it in enumerate(res["picker"], 1):
                    text += f"{i}. {it.get('type','?')}: {it.get('url','')}\n"
                await stat.edit_text(text, disable_web_page_preview=True)
        except Exception as e:
            await stat.edit_text(f"❌ خطا در دانلود: {str(e)[:200]}")
        atk_state["downloader_mode"] = False
        return

    # ========== Project Finder custom search ==========
    if pf_step == "await_query":
        query = (m.text or "").strip()
        atk_state["pf_step"] = None
        if not query or len(query) < 2:
            await m.reply_text("❌ عبارت جستجو خیلی کوتاه است.", reply_markup=main_menu())
            return
        status = await m.reply_text(f"🔍 در حال جستجو برای: <b>{query}</b>\n(گیت‌هاب + گیت‌لب + کدبرگ)\nچند لحظه صبر کن...")
        loop = asyncio.get_running_loop()
        try:
            items = await loop.run_in_executor(None, lambda: scan_custom_query(query, per_platform=10))
            new_items = merge_new(items)
            text = f"🔍 <b>نتایج جستجو: {query}</b>\n\n"
            text += f"✅ پیدا شد: {len(items)} مورد · {len(new_items)} مورد جدید\n\n"
            if not items:
                text += "چیزی پیدا نشد، عبارت دیگری امتحان کن."
            else:
                for i, it in enumerate(items[:15], 1):
                    plat = {"github":"🐙","gitlab":"🦊","codeberg":"🌿"}.get(it.get("platform",""),"")
                    desc = (it.get("description") or "").strip()
                    if len(desc) > 80: desc = desc[:80] + "…"
                    text += f"{i}. {plat} <a href=\"{it['url']}\"><b>{it.get('full_name','')}</b></a>\n"
                    text += f"   ⭐ {it.get('stars',0):,} · {it.get('language','—')}\n"
                    if desc: text += f"   └ {desc}\n\n"
                if len(items) > 15:
                    text += f"... و {len(items)-15} مورد دیگر در بایگانی ذخیره شد."
            await status.edit_text(text, disable_web_page_preview=True,
                                   reply_markup=InlineKeyboardMarkup([
                                       [InlineKeyboardButton("🔍 جستجوی مجدد", callback_data="pf_search"),
                                        InlineKeyboardButton("📂 لیست همه جستجوها", callback_data="pf_custom_list")],
                                       [InlineKeyboardButton("🔙 منوی پروژه‌یاب", callback_data="pf_menu")],
                                   ]))
        except Exception as e:
            await status.edit_text(f"❌ خطا در جستجو: {e}",
                                   reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="pf_menu")]]))
        return

    # ========== Hunter manual scan (deprecated - hunter replaced by project finder) ==========
    if hstep == "await_text":
        atk_state["hunter_step"] = None
        await m.reply_text("⚠️ ماژول شکارچی کیف‌پول/اکانت با «پروژه‌یاب اوپن‌سورس» جایگزین شد. از منوی اصلی استفاده کن.", reply_markup=main_menu())
        return

    if not step: return

    # ==================== آپلود مستقیم فایل سشن (دور زدن 2FA) ====================
    if step == "upload_session" and m.document:
        doc = m.document
        fname = getattr(doc, 'file_name', '') or 'unknown.session'
        if not fname.endswith('.session'):
            await m.reply_text("❌ فقط فایل با پسوند <code>.session</code> قابل قبوله!\nفایل رو دوباره بفرست.", reply_markup=main_menu())
            atk_state.clear()
            return
        st = await m.reply_text("📥 فایل سشن دریافت شد، در حال بررسی...")
        file_data = await app.download_media(m, in_memory=True)
        phone = ""
        base = fname.replace('.session', '')
        digits = ''.join(c for c in base if c.isdigit())
        if len(digits) >= 10:
            phone = '+' + digits
        if not phone:
            atk_state["pending_session_bytes"] = file_data.getvalue()
            atk_state["st"] = st
            atk_state["step"] = "upload_session_phone"
            await st.edit_text(
                "⚠️ نتونستم شماره رو از اسم فایل تشخیص بدم.\n"
                f"اسم فایل: <code>{fname}</code>\n\n"
                "لطفاً شماره تلفن این اکانت رو با فرمت +98 بفرست:\n"
                "مثال: <code>+989123456789</code>",
                reply_markup=InlineKeyboardMarkup([[_sub_back_btn(target="manage_accounts")[0]]]))
            return
        result = await _save_uploaded_session(st, phone, file_data.getvalue(), fname)
        if result:
            await st.edit_text(result, reply_markup=main_menu())
        atk_state.clear()
        return

    if step == "upload_session_phone" and m.text:
        phone = m.text.strip()
        if not phone.startswith('+') or len(phone) < 10:
            await m.reply_text("❌ فرمت شماره اشتباهه! با +98 شروع بشه.\nدوباره بفرست:", reply_markup=main_menu())
            return
        blob = atk_state.get("pending_session_bytes")
        if not blob:
            await m.reply_text("❌ خطا - فایل سشن پیدا نشد. دوباره آپلود کن.", reply_markup=main_menu())
            atk_state.clear()
            return
        st = atk_state.get("st")
        result = await _save_uploaded_session(st, phone, blob, "uploaded.session")
        if result:
            try: await st.edit_text(result, reply_markup=main_menu())
            except: await m.reply_text(result, reply_markup=main_menu())
        atk_state.clear()
        return

    # ==================== افزودن اکانت جدید از منوی مدیریت ====================
    if step == "add_new_acc_phone":
        phone = m.text.strip()
        # چک کن اکانت از قبل وجود نداشته باشه
        if phone in list_saved_accounts():
            await m.reply_text(f"⚠️ اکانت {phone} از قبل در لیست ذخیره شده است! نیازی به افزودن مجدد نیست، از لیست اکانت ها انتخاب کنید.", reply_markup=main_menu())
            atk_state.clear()
            return
        atk_state["phone"] = phone
        st = await m.reply_text("📡 در حال ارسال کد تایید...")
        try:
            chosen_fp = random.choice(DEVICE_FP)
            atk_state["chosen_fp"] = chosen_fp
            tmp_name = f"tmp_add_{int(time.time())}_{random.randint(1000,9999)}"
            acc_client = AdvancedScraper(tmp_name, API_ID, API_HASH, phone=phone, device_fp=chosen_fp, force_fresh=True)
            await robust_connect(acc_client)
            sent = await acc_client.app.send_code(phone)
            atk_state["new_acc_client"] = acc_client
            atk_state["acc_tmp_name"] = tmp_name
            atk_state["hash"] = sent.phone_code_hash
            atk_state["st"] = st
            atk_state["step"] = "add_new_acc_code"
            await st.edit_text("✅ کد تایید ارسال شد، کد ۵ رقمی را بفرست:")
        except FloodWait as fw:
            wait_h = fw.value // 3600
            wait_m = (fw.value % 3600) // 60
            await st.edit_text(f"❌ تلگرام موقتا از ارسال کد به این شماره خودداری میکند!\n⏱️ باید حدود {wait_h} ساعت و {wait_m} دقیقه صبر کنید.\n\n✅ نگران نباشید، سشن شما سالم است و اگر قبلا اکانت را افزوده بودید میتوانید بدون کد وارد شوید. این محدودیت موقت است و اکانت بن نشده.", reply_markup=main_menu())
            atk_state.clear()
        except Exception as e:
            await st.edit_text(f"❌ خطا در ارسال کد: {str(e)[:300]}\n\nلطفا چند دقیقه دیگر امتحان کنید.", reply_markup=main_menu())
            atk_state.clear()
        return

    if step == "add_new_acc_code":
        code = m.text.strip()
        acc_client = atk_state["new_acc_client"]
        phone = atk_state["phone"]
        h = atk_state["hash"]
        st = atk_state["st"]
        chosen_fp = atk_state.get("chosen_fp")
        try:
            await acc_client.app.sign_in(phone, h, code)
        except SessionPasswordNeeded:
            atk_state["step"] = "add_new_acc_2fa"
            await st.edit_text(
                "🔐 این اکانت دارای تایید دو مرحله‌ای است!\n\n"
                "✅ <b>هر دو روش پشتیبانی میشه:</b>\n"
                "• اگر <b>رمز ثابت</b> داری → همون رو بفرست\n"
                "• اگر <b>Google Authenticator</b> داری → کد ۶ رقمی فعلی رو بفرست\n"
                "• اگر <b>تلگرام پسورد ابری</b> داری → همون رو بفرست\n\n"
                "⚠️ کد TOTP هر ۳۰ ثانیه عوض میشه، سریع بفرست!\n\n"
                "یا می‌تونی از منوی «📱 مدیریت اکانت‌ها» → «📤 آپلود فایل سشن» استفاده کنی تا کلاً نیاز به 2FA نباشه.",
                disable_web_page_preview=True)
            return
        except Exception as e:
            await m.reply_text(f"❌ خطا در کد: {str(e)[:200]}")
            return
        me = await acc_client.app.get_me()
        # ذخیره دائمی سشن از حافظه به فایل
        try: await acc_client.persist_to_permanent()
        except Exception as e: print(f"persist err: {e}", flush=True)
        # ذخیره اکانت + فینگرپرینت
        accs = load_accounts()
        accs[phone] = {
            "name": f"{me.first_name or ''} {me.last_name or ''}".strip(),
            "user_id": me.id,
            "username": me.username or "",
            "added_at": int(time.time()),
            "device_fp": chosen_fp
        }
        save_accounts(accs)
        await acc_client.disconnect()
        # پاک کردن فایل موقت (اگر بود)
        try:
            tmp = atk_state.get("acc_tmp_name", "")
            if tmp and os.path.exists(tmp + ".session"):
                os.remove(tmp + ".session")
        except: pass
        # Backup session bytes to DB for persistence across render wipes
        try: _backup_session(phone)
        except: pass
        atk_state.clear()
        await st.edit_text(f"✅ اکانت {me.first_name} با موفقیت به صورت دائمی در دیتابیس ذخیره شد!\n✅ شناسه دستگاه ثابت ذخیره شد (انقضا نمی‌خورد)\n✅ فایل سشن در دیتابیس ابری بکاپ گرفته شد\nاز این به بعد بدون نیاز به کد می‌توانی ازش استفاده کنی.", reply_markup=main_menu())
        return

    if step == "add_new_acc_2fa":
        pwd = m.text.strip()
        acc_client = atk_state["new_acc_client"]
        phone = atk_state["phone"]
        st = atk_state["st"]
        chosen_fp = atk_state.get("chosen_fp")
        try:
            await acc_client.app.check_password(pwd)
        except Exception as e:
            await m.reply_text(f"❌ رمز اشتباه: {str(e)[:200]}")
            return
        me = await acc_client.app.get_me()
        try: await acc_client.persist_to_permanent()
        except Exception as e: print(f"persist err: {e}", flush=True)
        accs = load_accounts()
        accs[phone] = {
            "name": f"{me.first_name or ''} {me.last_name or ''}".strip(),
            "user_id": me.id,
            "username": me.username or "",
            "added_at": int(time.time()),
            "device_fp": chosen_fp
        }
        save_accounts(accs)
        await acc_client.disconnect()
        try:
            tmp = atk_state.get("acc_tmp_name", "")
            if tmp and os.path.exists(tmp + ".session"):
                os.remove(tmp + ".session")
        except: pass
        try: _backup_session(phone)
        except: pass
        atk_state.clear()
        await st.edit_text(f"✅ اکانت {me.first_name} با موفقیت در دیتابیس ذخیره شد!", reply_markup=main_menu())
        return

    # ==================== لاگین اکانت جدید هنگام شروع عملیات ====================
    if step == "phone_new":
        phone = m.text.strip()
        if phone in list_saved_accounts():
            await m.reply_text(f"⚠️ اکانت {phone} از قبل ذخیره شده است! لطفا از منوی انتخاب اکانت استفاده کنید.", reply_markup=main_menu())
            atk_state.clear()
            return
        atk_state["phone"] = phone
        after_mode = atk_state.get("after_auth_mode", "attack")
        st = await m.reply_text("📡 در حال ارسال کد تایید...")
        try:
            chosen_fp = random.choice(DEVICE_FP)
            atk_state["chosen_fp"] = chosen_fp
            tmp_name = f"tmp_login_{int(time.time())}_{random.randint(1000,9999)}"
            new_client = AdvancedScraper(tmp_name, API_ID, API_HASH, phone=phone, device_fp=chosen_fp, force_fresh=True)
            await robust_connect(new_client)
            sent = await new_client.app.send_code(phone)
            atk_state["new_client"] = new_client
            atk_state["new_tmp_name"] = tmp_name
            atk_state["hash"] = sent.phone_code_hash
            atk_state["st"] = st
            atk_state["step"] = "code_new"
            await st.edit_text("✅ کد تایید ارسال شد، کد ۵ رقمی را بفرست:\n⚠️ بعد از این بار دیگر نیازی به کد نخواهید داشت.")
        except FloodWait as fw:
            wait_h = fw.value // 3600
            wait_m = (fw.value % 3600) // 60
            await st.edit_text(f"❌ تلگرام موقتا کد نمیدهد!\n⏱️ لطفا حدود {wait_h} ساعت و {wait_m} دقیقه صبر کنید.\n✅ اکانت شما سالم است، نگران بن نباشید.", reply_markup=main_menu())
            atk_state.clear()
        except Exception as e:
            await st.edit_text(f"❌ خطا: {str(e)[:300]}", reply_markup=main_menu())
            atk_state.clear()
        return

    if step == "code_new":
        code = m.text.strip()
        new_client = atk_state["new_client"]
        phone = atk_state["phone"]
        h = atk_state["hash"]
        st = atk_state["st"]
        after_mode = atk_state.get("after_auth_mode", "attack")
        chosen_fp = atk_state.get("chosen_fp")
        try:
            await new_client.app.sign_in(phone, h, code)
        except SessionPasswordNeeded:
            atk_state["step"] = "code_new_2fa"
            await st.edit_text(
                "🔐 این اکانت دارای تایید دو مرحله‌ای است!\n\n"
                "✅ <b>هر دو روش پشتیبانی میشه:</b>\n"
                "• <b>رمز ثابت</b> یا <b>کد Google Authenticator</b> رو بفرست\n"
                "• یا از «📤 آپلود فایل سشن» استفاده کن\n\n"
                "⚠️ کد TOTP هر ۳۰ ثانیه عوض میشه!",
                disable_web_page_preview=True)
            return
        except Exception as e:
            await m.reply_text(f"❌ خطا در کد: {str(e)[:200]}")
            return
        # ذخیره اکانت
        me = await new_client.app.get_me()
        try: await new_client.persist_to_permanent()
        except Exception as e: print(f"persist err: {e}", flush=True)
        accs = load_accounts()
        accs[phone] = {
            "name": f"{me.first_name or ''} {me.last_name or ''}".strip(),
            "user_id": me.id,
            "username": me.username or "",
            "added_at": int(time.time()),
            "device_fp": chosen_fp
        }
        save_accounts(accs)
        try:
            await new_client.disconnect()
        except:
            pass
        try:
            tmp = atk_state.get("new_tmp_name", "")
            if tmp and os.path.exists(tmp + ".session"):
                os.remove(tmp + ".session")
        except: pass
        try: _backup_session(phone)
        except: pass
        await asyncio.sleep(1)
        # حالا مستقیم با سشن دائمی و همین فینگر وصل شو
        atk_state.clear()
        await st.edit_text(f"✅ اکانت {me.first_name} با موفقیت ذخیره شد!\nدر حال بارگذاری منوی عملیات...")
        try:
            if after_mode == "attack":
                atk_state.clear()
                atk_state["phone"] = phone
                atk_state["reuse_account"] = True
                atk = AdvancedScraper("atk_session", API_ID, API_HASH, phone=phone, device_fp=chosen_fp)
                await robust_connect(atk)
                atk_state["atk"] = atk
                atk_state["st"] = st
                atk_state["step"] = "after_login_attack"
                group_list = await _fast_load_chats(atk)
                atk_state["available_groups"] = group_list
                buttons = []
                for gname, gid, gcount, chtype in sorted(group_list, key=lambda x:-x[2]):
                    ch_icon = "📡" if chtype == "channel" else "👥"
                    buttons.append([InlineKeyboardButton(f"{ch_icon} {gname[:33]} | {gcount:,}", callback_data=f"atk_target_{gid}")])
                buttons.append([InlineKeyboardButton("✍️ وارد کردن دستی آیدی", callback_data="atk_target_manual")])
                await st.edit_text(f"✅ خوش آمدی {me.first_name}! اکانت برای همیشه ذخیره شد.\nگروه هدف را انتخاب کنید:", reply_markup=InlineKeyboardMarkup(buttons))
            else:
                atk_state.clear()
                atk_state["phone"] = phone
                atk_state["reuse_account"] = True
                limits = load_adder_limits()
                already = limits.get(phone, {}).get("added", 0)
                atk_state["already_added"] = already
                add_client = AdvancedScraper("add_session", API_ID, API_HASH, phone=phone, device_fp=chosen_fp)
                await robust_connect(add_client)
                atk_state["add_client"] = add_client
                atk_state["st"] = st
                add_groups = await _fast_load_chats(add_client)
                remaining = MAX_ADD_PER_ACCOUNT - already
                buttons = []
                for gname, gid, gcount, chtype in sorted(add_groups, key=lambda x:-x[2]):
                    ch_icon = "📡" if chtype == "channel" else "👥"
                    buttons.append([InlineKeyboardButton(f"➕ {ch_icon} {gname[:30]} | {gcount:,}", callback_data=f"add_target_{gid}")])
                buttons.append([InlineKeyboardButton("✍️ وارد کردن دستی", callback_data="add_target_manual")])
                await st.edit_text(f"✅ اکانت ذخیره شد! ظرفیت باقیمانده: {remaining} نفر\nگروه مقصد را انتخاب کنید:", reply_markup=InlineKeyboardMarkup(buttons))
        except Exception as e:
            await st.edit_text(f"✅ اکانت ذخیره شد، اما خطا در بارگذاری لیست: {str(e)[:150]}\nلطفا از منو دوباره شروع کنید.", reply_markup=main_menu())
        return

    if step == "code_new_2fa":
        pwd = m.text.strip()
        new_client = atk_state["new_client"]
        phone = atk_state["phone"]
        st = atk_state["st"]
        chosen_fp = atk_state.get("chosen_fp")
        try:
            await new_client.app.check_password(pwd)
        except Exception as e:
            await m.reply_text(f"❌ رمز اشتباه: {str(e)[:200]}")
            return
        me = await new_client.app.get_me()
        try: await new_client.persist_to_permanent()
        except Exception as e: print(f"persist err: {e}", flush=True)
        accs = load_accounts()
        accs[phone] = {
            "name": f"{me.first_name or ''} {me.last_name or ''}".strip(),
            "user_id": me.id,
            "username": me.username or "",
            "added_at": int(time.time()),
            "device_fp": chosen_fp
        }
        save_accounts(accs)
        try:
            await new_client.disconnect()
        except:
            pass
        try:
            tmp = atk_state.get("new_tmp_name", "")
            if tmp and os.path.exists(tmp + ".session"):
                os.remove(tmp + ".session")
        except: pass
        try: _backup_session(phone)
        except: pass
        atk_state.clear()
        await st.edit_text("✅ اکانت در دیتابیس ذخیره شد! /start بزن.", reply_markup=main_menu())
        return

    # ==================== مراحل قدیمی - دیگر مستقیم استفاده نمی‌شوند ====================

    if step == "phone":
        phone = m.text.strip()
        atk_state["phone"] = phone
        st = await m.reply_text("📡 در حال اتصال...")
        try:
            tmp_name = f"tmp_phone_{int(time.time())}_{random.randint(1000,9999)}"
            atk = AdvancedScraper(tmp_name, API_ID, API_HASH, phone=phone, force_fresh=True)
            await robust_connect(atk)
            sent = await atk.app.send_code(phone)
            atk_state["atk"] = atk
            atk_state["atk_tmp_name"] = tmp_name
            atk_state["hash"] = sent.phone_code_hash
            atk_state["st"] = st
            atk_state["step"] = "code"
            await st.edit_text("✅ کد ارسال شد، کد ۵ رقمی را بفرست:")
        except Exception as e:
            await st.edit_text(f"❌ خطا: {str(e)[:300]}")
            atk_state.clear()

    elif step == "code":
        code = m.text.strip()
        atk = atk_state["atk"]
        phone = atk_state["phone"]
        h = atk_state["hash"]
        st = atk_state["st"]
        try:
            await atk.app.sign_in(phone, h, code)
        except SessionPasswordNeeded:
            atk_state["step"] = "code_2fa"
            await st.edit_text(
                "🔐 این اکانت تایید دو مرحله‌ای دارد!\n\n"
                "✅ <b>رمز ثابت</b> یا <b>کد Google Authenticator</b> رو بفرست\n\n"
                "⚠️ کد TOTP هر ۳۰ ثانیه عوض میشه، سریع باش!",
                disable_web_page_preview=True)
            return
        except Exception as e:
            await m.reply_text(f"❌ خطا در کد: {str(e)[:200]}")
            return
        # ذخیره سشن در فایل دائمی
        try: await atk.persist_to_permanent()
        except Exception as e: print(f"persist err: {e}", flush=True)
        me = await atk.app.get_me()
        accs = load_accounts()
        fp_used = atk.get_fp_dict()
        accs[phone] = {
            "name": f"{me.first_name or ''} {me.last_name or ''}".strip(),
            "user_id": me.id,
            "username": me.username or "",
            "added_at": int(time.time()),
            "device_fp": fp_used
        }
        save_accounts(accs)
        try: _backup_session(phone)
        except: pass
        atk_state["step"] = "target"
        await st.edit_text(
            "✅ ورود موفق!\n"
            "🔄 در حال بارگذاری لیست گروه‌های شما (تا از این ارورها جلوگیری کنیم)...\n"
            "چند لحظه صبر کنید..."
        )
        # اسکن خودکار تمام دیالوگ ها برای گرم کردن کش تلگرام، جلوگیری از ارور CHAT_INVALID/عضو نیستی
        try:
            group_list = await _fast_load_chats(atk)
            atk_state["available_groups"] = group_list
        except Exception as e:
            print(f"اسکن دیالوگ ها با خطا مواجه شد: {e}", flush=True)
            group_list = []
            atk_state["available_groups"] = []

        if group_list:
            # به جای درخواست آیدی دستی، لیست گروه ها رو نشون بده
            buttons = []
            for gname, gid, gcount, chtype in sorted(group_list, key=lambda x: -x[2]):
                ch_icon = "📡" if chtype == "channel" else "👥"
                buttons.append([InlineKeyboardButton(f"{ch_icon} {gname[:33]} | {gcount:,}", callback_data=f"atk_target_{gid}")])
            buttons.append([InlineKeyboardButton("✍️ وارد کردن دستی آیدی", callback_data="atk_target_manual")])
            await st.edit_text(f"✅ لیست گروه‌های شما بارگذاری شد ({len(group_list)} گروه)\n\nگروه هدف را از لیست زیر انتخاب کنید، یا اگر نیست دستی وارد کنید:", reply_markup=InlineKeyboardMarkup(buttons))
        else:
            await st.edit_text(
                "✅ ورود موفق!\n\n"
                "حالا **آیدی عددی گروه هدف را بفرستید** (با -100 شروع میشود).\n"
                "مثال: `-1002790821974`\n\n"
                "اگر یوزرنیم عمومی دارد میتوانید با @ وارد کنید مثال: `@mygroup`\n\n"
                "✅ دقت کنید اکانت تست حتما عضو گروه باشد."
            )

    elif step == "target":
        raw = m.text.strip()
        atk = atk_state["atk"]
        st = atk_state["st"]
        await st.edit_text("🔍 در حال پیدا کردن گروه (چند بار تلاش میکنم، صبر کن)...")
        try:
            target = await robust_resolve_chat(atk, raw)
            target_id = target.id
        except Exception as e:
            await st.edit_text(f"❌ گروه پیدا نشد:\n{str(e)[:200]}\nلطفا یک بار دستی آن گروه/کانال را در اکانت تلگرام خود باز و چند پیامش را اسکرول کنید، بعد دوباره امتحان کنید.")
            return

        prog = await st.edit_text(f"🎯 هدف: {target.title}\n🚀 در حال شروع حمله...")
        async def run():
            try:
                progress_msg = prog
                stop_btn = InlineKeyboardMarkup([[InlineKeyboardButton("⏹️ توقف عملیات", callback_data="stop_op")]])
                async def on_progress(text):
                    try: await progress_msg.edit_text(text, reply_markup=stop_btn, disable_web_page_preview=True)
                    except: pass
                async def inc_save(user_list):
                    try: save_scraped(user_list, target.title, target.id)
                    except: pass
                users = await atk.run_full_scrape(target_id, progress_cb=on_progress, incremental_save_cb=inc_save)
                csv_bytes = atk.export_csv()
                # ذخیره دائمی در فایل
                save_scraped(users, target.title, target.id)
                await app.send_message(ADMIN_ID, f"✅ حمله تمام شد!\nگروه: {target.title}\nتعداد استخراج: {len(users)} نفر\n\n📋 از دکمه «لیست مخاطبان استخراج شده» در منو می‌توانید ببینید.")
                await app.send_document(ADMIN_ID, io.BytesIO(csv_bytes), file_name=f"result_{int(time.time())}.csv")
                await atk.disconnect()
            except Exception as e:
                await app.send_message(ADMIN_ID, f"❌ خطا در حمله:\n{str(e)}")
            atk_state.clear()
            await app.send_message(ADMIN_ID, "منوی اصلی:", reply_markup=main_menu())
        asyncio.create_task(run())

    # ==================== مراحل اضافه کردن اعضا ====================
    elif step == "adder_phone":
        phone = m.text.strip()
        # چک محدودیت قبل از اتصال
        limits = load_adder_limits()
        already = limits.get(phone, {}).get("added", 0)
        if already >= MAX_ADD_PER_ACCOUNT:
            await m.reply_text(f"⚠️ این اکانت ({phone}) قبلا {already} نفر اضافه کرده و به سقف {MAX_ADD_PER_ACCOUNT} رسیده!\nلطفا با شماره دیگری ادامه دهید یا از منوی آمار آن را ریست کنید.")
            atk_state.clear()
            await app.send_message(ADMIN_ID, "منوی اصلی:", reply_markup=main_menu())
            return
        atk_state["phone"] = phone
        atk_state["already_added"] = already
        st = await m.reply_text(f"📡 در حال اتصال به اکانت اد کننده...\n(تا کنون {already} نفر با این اکانت اضافه شده، باقیمانده: {MAX_ADD_PER_ACCOUNT-already})")
        try:
            tmp_name = f"tmp_adder_{int(time.time())}_{random.randint(1000,9999)}"
            add_client = AdvancedScraper(tmp_name, API_ID, API_HASH, phone=phone, force_fresh=True)
            await robust_connect(add_client)
            sent = await add_client.app.send_code(phone)
            atk_state["add_client"] = add_client
            atk_state["adder_tmp_name"] = tmp_name
            atk_state["hash"] = sent.phone_code_hash
            atk_state["st"] = st
            atk_state["step"] = "adder_code"
            await st.edit_text("✅ کد تایید به اکانت ارسال شد، کد ۵ رقمی را بفرست:")
        except Exception as e:
            await st.edit_text(f"❌ خطا: {str(e)[:300]}")
            atk_state.clear()

    elif step == "adder_code":
        code = m.text.strip()
        add_client = atk_state.get("add_client")
        phone = atk_state["phone"]
        h = atk_state["hash"]
        st = atk_state["st"]
        try:
            await add_client.app.sign_in(phone, h, code)
        except SessionPasswordNeeded:
            atk_state["step"] = "adder_2fa"
            await st.edit_text(
                "🔐 این اکانت تایید دو مرحله‌ای دارد!\n\n"
                "✅ <b>رمز ثابت</b> یا <b>کد Google Authenticator</b> رو بفرست\n\n"
                "⚠️ کد TOTP هر ۳۰ ثانیه عوض میشه، سریع باش!",
                disable_web_page_preview=True)
            return
        except Exception as e:
            await m.reply_text(f"❌ خطا در کد: {str(e)[:200]}")
            return
        # ذخیره دائمی سشن
        try: await add_client.persist_to_permanent()
        except Exception as e: print(f"persist err: {e}", flush=True)
        me = await add_client.app.get_me()
        accs = load_accounts()
        fp_used = add_client.get_fp_dict()
        accs[phone] = {
            "name": f"{me.first_name or ''} {me.last_name or ''}".strip(),
            "user_id": me.id,
            "username": me.username or "",
            "added_at": int(time.time()),
            "device_fp": fp_used
        }
        save_accounts(accs)
        try:
            tmp = atk_state.get("adder_tmp_name", "")
            if tmp and os.path.exists(tmp + ".session"):
                os.remove(tmp + ".session")
        except: pass
        try: _backup_session(phone)
        except: pass
        atk_state["step"] = "adder_target"
        await st.edit_text("✅ ورود موفق!\n🔄 در حال بارگذاری لیست گروه‌های شما...")
        # گرم کردن کش و تهیه لیست گروه ها
        add_groups = await _fast_load_chats(add_client)
        atk_state["available_add_groups"] = add_groups
        if add_groups:
            buttons = []
            for gname, gid, gcount, chtype in sorted(add_groups, key=lambda x: -x[2]):
                    ch_icon = "📡" if chtype == "channel" else "👥"
                    buttons.append([InlineKeyboardButton(f"➕ {ch_icon} {gname[:30]} | {gcount:,}", callback_data=f"add_target_{gid}")])
            buttons.append([InlineKeyboardButton("✍️ وارد کردن دستی آیدی", callback_data="add_target_manual")])
            await st.edit_text(f"✅ لیست گروه‌های شما آماده است ({len(add_groups)} گروه)\nگروه مقصد را انتخاب کنید:", reply_markup=InlineKeyboardMarkup(buttons))
        else:
            await st.edit_text("✅ ورود موفق!\nآیدی عددی گروه مقصد (که میخواهید افراد را به آن اضافه کنید) را بفرستید:\n(با -100 شروع میشود)")

    elif step in ["adder_target", "adder_target_manual"]:
        raw = m.text.strip()
        add_client = atk_state["add_client"]
        st = atk_state["st"]
        try:
            target = await robust_resolve_chat(add_client, raw)
            target_gid = target.id
        except Exception as e:
            await st.edit_text(f"❌ گروه/کانال پیدا نشد: {str(e)[:200]}\nلطفا یک بار دستی با اکانت خود آن گروه را در تلگرام باز کنید و دوباره امتحان کنید.")
            return
        # چک عضویت
        is_member = False
        for _ in range(3):
            try:
                me = await add_client.app.get_chat_member(target_gid, "me")
                if me and me.status in ["administrator", "creator", "member", "restricted"]:
                    is_member = True
                    break
            except:
                await asyncio.sleep(2)
                try:
                    async for _ in add_client.app.get_dialogs(limit=500):
                        pass
                except:
                    pass
        if not is_member:
            await st.edit_text("❌ اکانت شما عضو این گروه نیست یا اجازه دسترسی ندارد!\nلطفا اول دستی عضو شوید.")
            return
        atk_state["target_add_gid"] = target_gid
        atk_state["step"] = "adder_file"
        remaining = MAX_ADD_PER_ACCOUNT - atk_state.get("already_added", 0)
        # Detect channel
        is_ch = str(target.type).lower() == "chattype.channel" and not getattr(target, 'megagroup', False)
        ch_label = "📡 کانال" if is_ch else "👥 گروه"
        invite_extra = ""
        if is_ch:
            try:
                inv = await add_client.app.create_chat_invite_link(target_gid, member_limit=1)
                invite_extra = f"\n\n🔗 لینک دعوت:\n<code>{inv.invite_link}</code>"
            except: pass
        await st.edit_text(
            f"✅ مقصد: {ch_label} <b>{target.title}</b>\n"
            f"⚠️ این اکانت حداکثر می‌تواند {remaining} نفر دیگر اضافه کند."
            f"{invite_extra}\n\n"
            f"حالا **فایل CSV** که از استخراج دارید را همینجا آپلود کنید.",
            disable_web_page_preview=True)

    elif step == "adder_file" and m.document:
        add_client = atk_state.get("add_client")
        target_gid = atk_state.get("target_add_gid")
        st = atk_state["st"]
        phone = atk_state["phone"]
        already = atk_state.get("already_added", 0)
        await st.edit_text("📥 فایل دریافت شد، در حال پردازش و اضافه کردن اعضا...")
        try:
            file = await app.download_media(m.document, in_memory=True)
            content = file.getvalue().decode("utf-8-sig")
            reader = csv.DictReader(io.StringIO(content))
            raw_user_ids = []
            for row in reader:
                if "user_id" in row and str(row["user_id"]).lstrip('-').isdigit():
                    uid = int(row["user_id"])
                    # فیلتر کردن افرادی که قبلا به این گروه اضافه شده اند
                    if is_user_already_added(target_gid, uid):
                        continue
                    if uid not in raw_user_ids:
                        raw_user_ids.append(uid)
            # پیدا کردن نام گروه برای ثبت در تاریخچه
            try:
                target_chat = await add_client.app.get_chat(target_gid)
                target_title = target_chat.title
            except:
                target_title = "گروه مقصد"
            user_ids = raw_user_ids
            total_in_file = len(user_ids)
            added = 0
            errors = 0
            already_skipped = len([1 for row in csv.DictReader(io.StringIO(content)) if "user_id" in row and str(row["user_id"]).lstrip('-').isdigit()]) - total_in_file
            skipped_due_to_limit = 0
            remaining_slots = MAX_ADD_PER_ACCOUNT - already
            start_msg = f"شروع اضافه کردن...\n"
            start_msg += f"👥 گروه مقصد: {target_title}\n"
            start_msg += f"📄 تعداد در فایل: {total_in_file + already_skipped}\n"
            start_msg += f"⚠️ تکراری (قبلا ادد شده و رد شد): {already_skipped}\n"
            start_msg += f"🎯 تعداد جدید برای ادد: {total_in_file}\n"
            start_msg += f"🚀 سقف اکانت: {already}/{MAX_ADD_PER_ACCOUNT} (ظرفیت: {remaining_slots})"
            prog = await app.send_message(ADMIN_ID, start_msg)
            async def disconnect_later():
                try:
                    await add_client.disconnect()
                except:
                    pass
            for uid in user_ids:
                total_for_account = already + added
                if total_for_account >= MAX_ADD_PER_ACCOUNT:
                    skipped_due_to_limit = len(user_ids) - (added + errors)
                    await prog.edit_text(
                        f"⚠️ به سقف {MAX_ADD_PER_ACCOUNT} نفر در این اکانت رسیدیم!\nادامه متوقف شد.\n\n"
                        f"✅ جدیدا ادد شد: {added} نفر\n"
                        f"❌ ناموفق: {errors} نفر\n"
                        f"🔁 تکراری رد شده قبل از شروع: {already_skipped}\n"
                        f"🚫 به خاطر سقف ادد نشد: {skipped_due_to_limit}"
                    )
                    await disconnect_later()
                    break
                err_msg = ""
                try:
                    await add_client.app.add_chat_members(target_gid, uid)
                    added += 1
                    # ثبت در تاریخچه تکراری ها
                    mark_user_as_added(target_gid, target_title, uid)
                    # ذخیره آمار اکانت
                    limits = load_adder_limits()
                    limits[phone] = {"added": already + added, "last_used": int(time.time())}
                    save_adder_limits(limits)
                    await asyncio.sleep(random.randint(8,15))
                    if added % 5 == 0 or errors % 5 == 0:
                        done = added + errors
                        await prog.edit_text(
                            f"⏳ در حال اضافه کردن...\n"
                            f"✅ موفق: {added}\n"
                            f"❌ خطا: {errors}\n"
                            f"🔁 تکراری رد شده: {already_skipped}\n"
                            f"📊 پیشرفت اکانت: {already+added}/{MAX_ADD_PER_ACCOUNT}\n"
                            f"📉 باقیمانده: {len(user_ids) - done}"
                        )
                except Exception as e:
                    errors +=1
                    err_str = str(e).lower()
                    wait_time = 2
                    if "flood" in err_str or "too many" in err_str:
                        wait_time = 15
                    elif "already" in err_str or "participant" in err_str:
                        # کاربر الان هم در گروه هست، در لیست تکراری علامت بزن
                        mark_user_as_added(target_gid, target_title, uid)
                    await asyncio.sleep(wait_time)
            else:
                await prog.edit_text(
                    f"✅ عملیات اضافه کردن به پایان رسید!\n\n"
                    f"👥 گروه: {target_title}\n"
                    f"✅ جدیدا با موفقیت ادد شد: {added} نفر\n"
                    f"❌ ناموفق (ارور/بن/خصوصی): {errors} نفر\n"
                    f"🔁 تکراری (قبلا در گروه بود): {already_skipped} نفر\n"
                    f"📊 کل ادد شده با این اکانت: {already+added}/{MAX_ADD_PER_ACCOUNT}"
                )
                await disconnect_later()
        except Exception as e:
            await st.edit_text(f"❌ خطا در اضافه کردن: {str(e)}")
            try:
                await add_client.disconnect()
            except:
                pass
        atk_state.clear()
        await app.send_message(ADMIN_ID, "منوی اصلی:", reply_markup=main_menu())

@app.on_message(filters.new_chat_members)
async def new_mem(c, m):
    if not CURRENT_GROUP_ID or m.chat.id != CURRENT_GROUP_ID or not defender or defender.MIN_ACCOUNT_AGE_DAYS <=0:
        return
    for u in m.new_chat_members:
        if u.is_self: continue
        asyncio.create_task(defender.on_join(u))

@app.on_message(filters.left_chat_member)
async def left_mem(c, m):
    if not CURRENT_GROUP_ID or m.chat.id != CURRENT_GROUP_ID or not defender:
        return
    asyncio.create_task(defender.on_leave(m.left_chat_member))

@app.on_message(filters.text & filters.group)
async def mon(c, m):
    if not CURRENT_GROUP_ID or m.chat.id != CURRENT_GROUP_ID or not defender or defender.MIN_ACCOUNT_AGE_DAYS <=0:
        return
    await defender.monitor_message(m)

class Health(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        status = "OK"
        if atk_state:
            status += f" | task={atk_state.get('step','idle')}"
        if LAST_ERROR:
            status += f"\nLAST_ERR: {LAST_ERROR}"
        self.wfile.write(f"OK - {time.ctime()} | {status}".encode())
    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()
    def log_message(self, *a): pass

def run_health():
    HTTPServer(("0.0.0.0", PORT), Health).serve_forever()

# ضدخواب: هر ۵ دقیقه خودش به خودش درخواست میزنه که رندر متوجه فعال بودن سرویس بشه
PUBLIC_URL = os.environ.get("RENDER_EXTERNAL_URL", "https://telegram-anti-scraper-bot.onrender.com")
def keep_awake_loop():
    import urllib.request
    while True:
        time.sleep(280)  # ~4.7 دقیقه، زودتر از ۱۵ دقیقه
        try:
            req = urllib.request.Request(PUBLIC_URL + "/", headers={"User-Agent": "KeepAlive/1.0"})
            urllib.request.urlopen(req, timeout=15).read()
            print("💓 کیپ الایو پینگ شد - سرویس بیدار میماند", flush=True)
        except Exception as e:
            print(f"⚠️ کیپ الایو ناموفق: {e}", flush=True)

if __name__ == "__main__":
    # Clear any stale webhook from previous deployments so polling works
    for attempt in range(8):
        try:
            import requests as _req
            _req.get(f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook?drop_pending_updates=true", timeout=10)
            print("✅ وبهوک قدیمی پاک شد", flush=True)
            break
        except Exception as _e:
            print(f"webhook clear err: {_e}", flush=True)
    Thread(target=run_health, daemon=True).start()
    Thread(target=keep_awake_loop, daemon=True).start()
    # Run with retry on FloodWait
    while True:
        try:
            app.run()
            break
        except Exception as e:
            msg = str(e)
            print(f"app.run crashed: {e}", flush=True)
            import re as _re
            m = _re.search(r"wait of (\d+) seconds", msg)
            wait = 60
            if m: wait = int(m.group(1)) + 5
            print(f"⏱️ ری‌استارت در {wait} ثانیه...", flush=True)
            import time as _t; _t.sleep(wait)
