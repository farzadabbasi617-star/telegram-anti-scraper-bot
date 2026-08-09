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
from pyrogram.errors import SessionPasswordNeeded, AuthKeyDuplicated, AuthKeyUnregistered, FloodWait, PhoneCodeExpired, PhoneCodeInvalid

from attacker import AdvancedScraper, SESSIONS_DIR, safe_phone_filename, DEVICE_FP, _get_session_lock, _enable_wal_on_session
# _global_connect_lock حالا از attacker میاد
from attacker import _global_connect_lock as _connect_lock
from defender import AdvancedDefender
# 🔍 Group Finder module
try:
    import group_finder as gf
except Exception as e:
    print(f"GF import failed: {e}")
    gf = None
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
    migrate_json_to_db,
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
MAX_ADD_PER_ACCOUNT = 50  # 🔒 Supergroup: 200/day safe, we use 50 to be conservative  # 🔒 محدودیت امن — تلگرام بعد از 30-50 اد PEER_FLOOD میده

# گروه مقصد ثابت - ممبرها همیشه به این گروه اضافه میشن
FIXED_TARGET_LINK = "https://t.me/+gLScToU4DZdjZmM0"
FIXED_TARGET_GID = None  # will be resolved on first use

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


# ═══════════════════════════════════════════════════════
# AUTO-RECOVERY SYSTEM FOR SESSION ERRORS
# ═══════════════════════════════════════════════════════

def cleanup_session_files(session_path):
    """Clean up WAL, SHM, and Journal files for a session"""
    patterns = [
        f"{session_path}.session-wal",
        f"{session_path}.session-shm",
        f"{session_path}.session-journal",
        f"{session_path}-journal",
        f"{session_path}-wal",
        f"{session_path}-shm",
    ]
    
    cleaned = []
    for pattern in patterns:
        files = glob.glob(pattern)
        for f in files:
            try:
                os.remove(f)
                cleaned.append(os.path.basename(f))
                print(f"🧹 Cleaned: {os.path.basename(f)}", flush=True)
            except Exception as e:
                print(f"⚠️ Could not clean {f}: {e}", flush=True)
    
    return cleaned

def cleanup_all_session_locks():
    """Clean up all session lock files"""
    patterns = [
        "sessions/*.session-wal",
        "sessions/*.session-shm",
        "sessions/*.session-journal",
        "*.session-wal",
        "*.session-shm",
        "*.session-journal",
    ]
    
    cleaned = []
    for pattern in patterns:
        for f in glob.glob(pattern):
            try:
                os.remove(f)
                cleaned.append(os.path.basename(f))
            except:
                pass
    
    if cleaned:
        print(f"🧹 Cleaned {len(cleaned)} lock files", flush=True)
    return cleaned

async def safe_connect_with_recovery(client, phone, max_retries=3):
    """
    Connect to Telegram with auto-recovery for disk I/O errors
    
    Args:
        client: AdvancedScraper instance
        phone: Phone number for session recovery
        max_retries: Maximum retry attempts
    
    Returns:
        bool: True if connected successfully, False otherwise
    """
    from attacker import safe_phone_filename
    
    session_name = client.app.name if hasattr(client, 'app') else client.name
    session_path = os.path.join(SESSIONS_DIR, session_name)
    
    for attempt in range(max_retries):
        try:
            # Try to connect
            await client.connect()
            
            # Test connection
            me = await client.app.get_me()
            print(f"✅ Connected: {me.first_name}", flush=True)
            return True
            
        except Exception as e:
            error_msg = str(e).lower()
            
            # Check if it's a disk I/O error
            if "disk i/o" in error_msg or "database" in error_msg or "locked" in error_msg:
                print(f"⚠️ Attempt {attempt + 1}/{max_retries}: Disk I/O error detected", flush=True)
                
                # Disconnect first
                try:
                    await client.disconnect()
                except:
                    pass
                
                # Clean up session files
                cleaned = cleanup_session_files(session_path)
                if cleaned:
                    print(f"🧹 Cleaned {len(cleaned)} files, retrying...", flush=True)
                
                # Wait a bit
                await asyncio.sleep(2)
                
                # If this is the last attempt, try reloading from database
                if attempt == max_retries - 2:
                    print("🔄 Trying to reload session from database...", flush=True)
                    try:
                        # Delete current session file
                        session_file = f"{session_path}.session"
                        if os.path.exists(session_file):
                            os.remove(session_file)
                            print(f"🗑️ Deleted: {session_file}", flush=True)
                        
                        # Reload from database
                        blob = db.load_session_blob(phone)
                        if blob:
                            with open(session_file, "wb") as f:
                                f.write(blob)
                            print(f"✅ Reloaded session from database ({len(blob)} bytes)", flush=True)
                        else:
                            print(f"⚠️ No session blob in database for {phone}", flush=True)
                    except Exception as reload_err:
                        print(f"❌ Reload failed: {reload_err}", flush=True)
                
                # Wait before retry
                await asyncio.sleep(3)
                continue
                
            else:
                # Not a disk I/O error, re-raise
                print(f"❌ Connection error: {e}", flush=True)
                raise
    
    # All retries failed
    print(f"❌ Failed to connect after {max_retries} attempts", flush=True)
    return False

async def robust_connect_v2(client, phone=None, max_retries=5):
    """
    Enhanced robust_connect with auto-recovery
    Use this instead of robust_connect for better error handling
    """
    from attacker import _enable_wal_on_session
    
    session_name = client.app.name if hasattr(client, 'app') else client.name
    
    for attempt in range(1, max_retries + 1):
        try:
            # Disconnect first
            try:
                await client.disconnect()
            except:
                pass
            
            await asyncio.sleep(0.5)
            
            # Enable WAL
            try:
                _enable_wal_on_session(session_name)
            except:
                pass
            
            # Connect
            await client.connect()
            
            # Enable WAL again
            try:
                _enable_wal_on_session(session_name)
            except:
                pass
            
            return True
            
        except Exception as e:
            error_msg = str(e).lower()
            
            # Check for disk I/O errors
            if any(keyword in error_msg for keyword in ["disk i/o", "database", "locked", "corrupt"]):
                print(f"⚠️ Disk error (attempt {attempt}/{max_retries}): {e}", flush=True)
                
                if attempt < max_retries:
                    # Clean up session files
                    session_path = os.path.join(SESSIONS_DIR, session_name)
                    cleanup_session_files(session_path)
                    
                    # If we have phone number and this is attempt 3+, try reload from DB
                    if phone and attempt >= 3:
                        try:
                            session_file = f"{session_path}.session"
                            if os.path.exists(session_file):
                                os.remove(session_file)
                            
                            blob = db.load_session_blob(phone)
                            if blob:
                                with open(session_file, "wb") as f:
                                    f.write(blob)
                                print(f"✅ Reloaded session from DB", flush=True)
                        except:
                            pass
                    
                    # Exponential backoff
                    await asyncio.sleep(2 * attempt)
                    continue
            
            # For other errors or last attempt
            if attempt == max_retries:
                raise
            
            await asyncio.sleep(2 * attempt)
    
    return False

# ═══════════════════════════════════════════════════════
# END AUTO-RECOVERY SYSTEM
# ═══════════════════════════════════════════════════════


async def robust_connect(client, max_retries=6, phone=None):
    """اتصال با تلاش مجدد و auto-recovery برای disk I/O errors"""
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
            
            # Check for disk I/O errors
            if any(keyword in msg for keyword in ["disk i/o", "database", "locked", "corrupt"]) and attempt < max_retries:
                print(f"⚠️ Disk I/O error، تلاش {attempt+1}/{max_retries}: {e}", flush=True)
                
                try:
                    client_name = client.app.name if hasattr(client, 'app') else client.name
                    
                    # Clean up all session lock files
                    for pat in [
                        client_name + ".session-journal",
                        client_name + ".session-wal",
                        client_name + ".session-shm",
                        "*.session-journal",
                        "*.session-wal",
                        "*.session-shm"
                    ]:
                        for f in _glob.glob(pat):
                            try:
                                os.remove(f)
                                print(f"🧹 Cleaned: {os.path.basename(f)}", flush=True)
                            except:
                                pass
                    
                    # If we have phone and this is attempt 3+, try reload from DB
                    if phone and attempt >= 3:
                        from attacker import safe_phone_filename
                        fname = safe_phone_filename(phone)
                        session_file = os.path.join(SESSIONS_DIR, f"acc_{fname}.session")
                        
                        if os.path.exists(session_file):
                            os.remove(session_file)
                            print(f"🗑️ Deleted corrupt session: {session_file}", flush=True)
                        
                        blob = db.load_session_blob(phone)
                        if blob:
                            with open(session_file, "wb") as f:
                                f.write(blob)
                            print(f"✅ Reloaded session from database ({len(blob)} bytes)", flush=True)
                        else:
                            print(f"⚠️ No session blob in database", flush=True)
                
                except Exception as cleanup_err:
                    print(f"⚠️ Cleanup error: {cleanup_err}", flush=True)
                
                # Exponential backoff
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

def build_welcome_text():
    """Build the rich status/welcome text shown at top of main menu."""
    saved_accs = list_saved_accounts()
    acc_count = len(saved_accs)
    users, gname, _ = load_scraped()
    total_users = len(users)
    total_added = _db_count_added()
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
    text += "🔹 استخراج فالوورها از URL یا username\n"
    text += "🔹 ذخیره در دیتابیس مشترک با تلگرام\n"
    text += "🔹 skip خودکار کاربرای تکراری\n"
    text += "🔹 سرعت بالا + progress زنده\n\n"
    
    # Check login status — try session first, then auto-login
    logged_in = False
    try:
        L = ig_scraper.get_instaloader()
        L.test_login()
        logged_in = True
    except:
        # Try auto-login with env credentials
        try:
            if ig_scraper.login_instagram():
                logged_in = True
        except:
            pass
    
    if logged_in:
        text += "🟢 <b>وضعیت:</b> به اینستاگرام متصلی\n"
        text += f"👤 اکانت: <code>{ig_scraper.IG_USERNAME or '?'}</code>\n"
    else:
        if ig_scraper.IG_USERNAME:
            text += "🔴 <b>وضعیت:</b> لاگین نشد (پسورد اشتباه یا چالش امنیتی)\n"
            text += f"👤 اکانت تنظیم شده: <code>{ig_scraper.IG_USERNAME}</code>\n"
        else:
            text += "🔴 <b>وضعیت:</b> هنوز لاگین نشدی\n"
    
    text += "\n⚠️ <b>محدودیت‌ها:</b>\n"
    text += "• سرعت: ~۲۰۰ فالوور در ساعت\n"
    text += "• فقط پیج‌های عمومی\n"
    text += "• ریسک Shadow ban در صورت استفاده سنگین\n"
    text += "• Render IP ممکنه چالش امنیتی بخوره → از آپلود سشن استفاده کن\n"
    
    buttons = []
    if logged_in:
        buttons.append([InlineKeyboardButton("🔍 اسکرپ فالوورهای یک پیج", callback_data="ig_scrape_prompt")])
        buttons.append([InlineKeyboardButton("📋 نتایج اسکرپ", callback_data="ig_list")])
        buttons.append([InlineKeyboardButton("➕ Follow اسکرپ‌شده‌ها", callback_data="ig_follow_menu")])
        buttons.append([InlineKeyboardButton("🚪 خروج از اکانت", callback_data="ig_logout")])
    else:
        buttons.append([InlineKeyboardButton("🔐 تنظیم لاگین", callback_data="ig_login")])
        buttons.append([InlineKeyboardButton("📥 آپلود سشن (2FA)", callback_data="ig_upload_session")])
        if ig_scraper.IG_USERNAME:
            buttons.append([InlineKeyboardButton("🔄 تلاش مجدد لاگین خودکار", callback_data="ig_retry_login")])
    
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
    """Start Instagram follower scraping — accepts URL or username"""
    # Extract username from URL if needed
    target = ig_scraper.extract_username(target)
    
    # Try session first, then auto-login
    logged_in = False
    try:
        L = ig_scraper.get_instaloader()
        L.test_login()
        logged_in = True
    except:
        try:
            if ig_scraper.login_instagram():
                logged_in = True
        except:
            pass
    
    if not logged_in:
        await q.answer("❌ لاگین نشدی! پسورد اشتباهه یا اینستاگرام چالش امنیتی داده.\nاز «📥 آپلود سشن» استفاده کن.", show_alert=True)
        return
    
    prog = await q.message.edit_text(
        f"📸 <b>شروع اسکرپ فالوورها</b>\n"
        f"👤 هدف: @{target}\n"
        f"⏳ در حال اسکن...")
    
    async def run_ig():
        stop = [0]
        found = [0]; total = [0]
        last_update = [0]
        
        def progress_cb(cnt, total_f, username, status):
            found[0] = cnt; total[0] = total_f
        
        async def update_progress():
            import time as _t
            while True:
                await asyncio.sleep(3)
                try:
                    c = found[0]; t = total[0]; spd = int(c / max(1, _t.time() - t0) * 60) if found[0] > 10 else 0
                    text = (
                        f"📸 <b>اسکرپ @{target}</b>\n"
                        f"━━━━━━━━━━━━━━━━━━\n"
                        f"👤 اسکن شده: <b>{c:,}</b> از {t or '?'}\n"
                        f"⚡ سرعت: ~{spd}/min\n"
                        f"━━━━━━━━━━━━━━━━━━\n"
                        f"⏳ در حال کار... صبور باش")
                    await prog.edit_text(text, disable_web_page_preview=True)
                except: break
        
        t0 = time.time()
        updater = asyncio.create_task(update_progress())
        
        try:
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(
                None,
                lambda: ig_scraper.scrape_followers(target, max_followers=1000, progress_cb=progress_cb, stop_flag=stop)
            )
            try: updater.cancel()
            except: pass
            
            if result.get("error"):
                await prog.edit_text(
                    f"❌ خطا در اسکرپ:\n{result['error'][:300]}\n\n"
                    f"👤 استخراج شده: {result['count']:,}",
                    reply_markup=InlineKeyboardMarkup([[_sub_back_btn(target="ig_menu")[0]]]))
            else:
                await prog.edit_text(
                    f"✅ <b>اسکرپ @{target} تمام شد!</b>\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"👤 فالوور جدید: <b>{result['count']:,}</b>\n"
                    f"💾 در دیتابیس Neon ذخیره شد\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"از «📋 نتایج» یا «🗂️ چت‌ها» ببین.",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("📋 نتایج IG", callback_data="ig_list")],
                        [_sub_back_btn(target="ig_menu")[0]]
                    ]))
        except Exception as e:
            try: updater.cancel()
            except: pass
            await prog.edit_text(f"❌ خطا: {str(e)[:300]}", 
                reply_markup=InlineKeyboardMarkup([[_sub_back_btn(target="ig_menu")[0]]]))
    
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

# ═══════════════ 🤖 AI Menu ═══════════════
async def _show_ai_menu(q):
    """AI-powered tools menu"""
    users, gname, _ = load_scraped()
    total_users = len(users)
    chats = get_scanned_chats()
    text = "🤖 <b>تحلیل هوشمند (AI)</b>\n━━━━━━━━━━━━━━━━━━\n"
    text += "🔹 تشخیص خودکار موضوع چت‌ها\n"
    text += "🔹 رتبه‌بندی گروه‌ها در گروه‌یاب\n"
    text += f"👥 کاربران: {total_users:,} | 🗂️ چت‌ها: {len(chats)}\n"
    categorized = sum(1 for c in chats if c.get('category'))
    text += f"🏷️ دسته‌بندی شده: {categorized}/{len(chats)}\n"
    buttons = []
    if chats:
        uncat = [c for c in chats if not c.get('category')][:6]
        for ch in uncat:
            icon = _chat_type_icon(ch.get('chat_type', ''))
            name = ch['chat_name'][:35]
            buttons.append([InlineKeyboardButton(f"🔍 تحلیل {icon} {name}", callback_data=f"ai_analyze_{ch['chat_id']}")])
        if len([c for c in chats if not c.get('category')]) > 6:
            buttons.append([InlineKeyboardButton("🔍 تحلیل همه چت‌های بدون دسته", callback_data="ai_batch_analyze")])
    buttons.append([InlineKeyboardButton("📊 آمار تحلیل", callback_data="ai_stats")])
    buttons.append(_sub_back_btn())
    await q.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons), disable_web_page_preview=True)


async def _handle_ai_batch_analyze(q):
    """Analyze all uncategorized chats at once"""
    chats = get_scanned_chats()
    uncat = [c for c in chats if not c.get('category')]
    if not uncat:
        await q.answer("همه چت‌ها دسته‌بندی شدن!", show_alert=True)
        return
    await q.answer(f"🤖 تحلیل {len(uncat)} چت...", show_alert=False)
    prog = await q.message.edit_text(f"🤖 در حال تحلیل هوشمند {len(uncat)} چت...\n⏳ صبر کن...")
    from chat_analyzer import smart_analyze
    results = []
    for ch in uncat:
        try:
            analysis = smart_analyze(ch['chat_name'], '')
            if analysis.get('category'):
                update_chat_category(ch['chat_id'], analysis['category'])
                results.append((ch['chat_name'], analysis.get('icon', '📁'), analysis['category'], analysis.get('confidence', 0)))
        except: pass
        await asyncio.sleep(0.3)
    text = f"✅ تحلیل {len(uncat)} چت تمام شد!\n\n"
    if results:
        for title, icon, cat, conf in results:
            text += f"{icon} <b>{title[:40]}</b> → {cat} ({conf}%)\n"
    else:
        text += "⚠️ نتونستم موضوعی تشخیص بدم.\n"
    await prog.edit_text(text, reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("🗂️ دیدن چت‌ها", callback_data="chats_manager")],
        [InlineKeyboardButton("🔙 منوی AI", callback_data="ai_menu")],
    ]), disable_web_page_preview=True)


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
    """LIVE scrape from source group + AddContact+InviteToChannel to target."""
    add_client = atk_state.get("add_client")
    phone = atk_state.get("phone", "")
    already_added = atk_state.get("already_added", 0)
    remaining = MAX_ADD_PER_ACCOUNT - already_added
    prog_msg = q.message
    target_name = "گروه"

    if not add_client:
        try:
            await prog_msg.edit_text(" اکانت متصل نیست!\nاول از منوی ادد ممبر اکانت رو وصل کن.",
                reply_markup=InlineKeyboardMarkup([[_sub_back_btn(target="home")[0]]]))
        except: pass
        return

    try:
        tgt = await add_client.app.get_chat(target_gid)
        target_name = tgt.title
    except Exception as e:
        await prog_msg.edit_text(f"❌ کانال پیدا نشد: {e}",
            reply_markup=InlineKeyboardMarkup([[_sub_back_btn(target="home")[0]]]))
        return

    # Get source group
    source_gid = atk_state.get("live_source_gid")
    if not source_gid:
        await prog_msg.edit_text("❌ گروه منبع مشخص نیست!",
            reply_markup=InlineKeyboardMarkup([[_sub_back_btn(target="home")[0]]]))
        return

    # Get source group name
    try:
        src_chat = await add_client.app.get_chat(source_gid)
        source_name = src_chat.title
    except:
        source_name = "گروه منبع"

    # Check admin on target
    try:
        await add_client.app.get_dialogs(limit=200)
    except: pass
    
    added = 0; failed = 0; skipped = 0
    errors_detail = {"peer": 0, "privacy": 0, "already": 0, "flood": 0, "other": 0}
    first_error = ""
    start_t = time.time()
    atk_state["add_in_progress"] = True

    from pyrogram.raw.functions.contacts import AddContact
    from pyrogram.raw.functions.channels import InviteToChannel

    async def upd():
        try:
            elapsed = int(time.time() - start_t)
            m, s = elapsed // 60, elapsed % 60
            pct = int((added + failed) * 100 / max(1, total)) if total > 0 else 0
            bar = "█" * (pct // 5) + "░" * (20 - pct // 5)
            spd = int(added / (elapsed / 60)) if elapsed > 30 else 0
            txt = f"🔄 اسکرپ از: {source_name}\n🎯 ادد به: {target_name}\n{bar} {pct}%\n✅ {added} ❌ {failed} ⏭ {skipped}\n⏱ {m:02d}:{s:02d} ⚡ {spd}/min"
            await prog_msg.edit_text(txt,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⏹️ توقف", callback_data="stop_op")]]),
                disable_web_page_preview=True)
        except: pass

    await upd()

    # ═══════════════ PHASE 1: LIVE SCRAPE FROM SOURCE GROUP ═══════════════
    print(f"🔄 Phase 1: Live scraping from {source_name} ({source_gid})...", flush=True)
    await prog_msg.edit_text(f"🔄 در حال اسکرپ از <b>{source_name}</b>...\n⏳ صبر کنید",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⏹️ توقف", callback_data="stop_op")]]))

    # Resolve target once
    try:
        target_peer = await add_client.app.resolve_peer(target_gid)
    except Exception as e:
        await prog_msg.edit_text(f"❌ کانال مقصد resolve نشد: {e}",
            reply_markup=InlineKeyboardMarkup([[_sub_back_btn(target="home")[0]]]))
        return

    # Scrape members from source group
    valid_peers = {}
    total = 0
    scanned = 0
    try:
        async for member in add_client.app.get_chat_members(source_gid, limit=10000):
            if atk_state.get("_stop_requested"):
                break
            scanned += 1
            u = member.user
            if not u or getattr(u, 'is_bot', False) or getattr(u, 'is_deleted', False):
                continue
            uid = u.id
            if uid <= 10000 or uid >= 10**11:
                continue
            if is_user_already_added(target_gid, uid):
                skipped += 1
                continue
            # Skip if over remaining
            if (added + failed) >= remaining:
                break
            try:
                peer = await add_client.app.resolve_peer(uid)
                valid_peers[uid] = peer
                total += 1
                if scanned % 100 == 0:
                    print(f"  📊 Scanned {scanned}: {total} resolved, {skipped} already", flush=True)
                    await upd()
            except:
                pass
            await asyncio.sleep(0.01)
    except Exception as se:
        print(f"  ⚠️ Scrape error: {se}", flush=True)
        first_error = f"Scrape: {str(se)[:200]}"

    print(f"  ✅ Phase 1 done: {scanned} scanned, {total} resolved, {skipped} skipped", flush=True)

    if total == 0:
        await prog_msg.edit_text(
            f" هیچ کاربر جدیدی پیدا نشد!\n\n"
            f"📊 اسکن شد: {scanned}\n"
            f"⏭ رد شده (قبلاً اضافه شده): {skipped}\n"
            f"\n💡 احتمالاً همه اعضای این گروه قبلاً اضافه شدن.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 اسکرپ از گروه دیگه", callback_data=f"live_add_pick_src_{target_gid}")],
                [InlineKeyboardButton(" خانه", callback_data="home")],
            ]))
        return

    # ═══════════════ PHASE 2: ADD TO TARGET CHANNEL ═══════════════
    print(f"🔄 Phase 2: Adding {total} users to {target_name}...", flush=True)
    
    for uid, user_peer in list(valid_peers.items())[:remaining]:
        if atk_state.get("_stop_requested"):
            break
        try:
            # AddContact
            try:
                await add_client.app.invoke(
                    AddContact(id=user_peer, first_name=str(uid)[:30], last_name="", phone="", add_phone_privacy_exception=False)
                )
                await asyncio.sleep(0.3)
            except: pass

            # InviteToChannel
            await add_client.app.invoke(
                InviteToChannel(channel=target_peer, users=[user_peer])
            )

            added += 1
            mark_user_as_added(target_gid, target_name, uid)
            limits = load_adder_limits()
            limits[phone] = {"added": already_added + added, "last_used": int(time.time())}
            save_adder_limits(limits)

            total_acc = already_added + added
            if total_acc > 80:
                await asyncio.sleep(random.randint(15, 25))
            elif total_acc > 50:
                await asyncio.sleep(random.randint(10, 18))
            else:
                await asyncio.sleep(random.randint(7, 13))

        except FloodWait as fw:
            failed += 1; errors_detail["flood"] += 1
            print(f"⏱ FloodWait {fw.value}s", flush=True)
            await asyncio.sleep(fw.value + 5)
        except Exception as e:
            failed += 1; es = str(e); es_l = es.lower()
            if not first_error: first_error = es[:200]
            if "peer_id_invalid" in es_l: errors_detail["peer"] += 1
            elif "privacy" in es_l or "not_mutual" in es_l: errors_detail["privacy"] += 1
            elif "already" in es_l or "participant" in es_l:
                errors_detail["already"] += 1
                mark_user_as_added(target_gid, target_name, uid)
            elif "flood" in es_l: errors_detail["flood"] += 1
            elif "admin" in es_l or "right" in es_l:
                errors_detail["other"] += 1
                if not first_error: first_error = f"ADMIN_REQUIRED: {es[:100]}"
                print(f"❌ ADMIN ERROR: {es[:200]}", flush=True)
            else:
                errors_detail["other"] += 1
            await asyncio.sleep(random.randint(2, 5))

        if (added + failed) % 3 == 0:
            await upd()

    # ═══════════════ FINAL REPORT ═══════════════
    elapsed = int(time.time() - start_t)
    m, s = elapsed // 60, elapsed % 60
    text = f"✅ <b>تمام شد — {target_name}</b>\n{'━'*20}\n"
    text += f"📂 منبع: {source_name}\n"
    text += f"📊 اسکن شد: {scanned}\n"
    text += f"⏭ رد شده: {skipped}\n"
    text += f"✅ اضافه شده: {added}\n"
    text += f"❌ ناموفق: {failed}\n"
    text += f"⏱ زمان: {m:02d}:{s:02d}\n"
    text += f"📊 ظرفیت: {already_added + added}/{MAX_ADD_PER_ACCOUNT}"
    if failed > 0:
        text += f"\n{'━'*20}\n📋 جزئیات خطا:\n"
        if errors_detail["peer"]: text += f"🔍 Peer Invalid: {errors_detail['peer']}\n"
        if errors_detail["privacy"]: text += f"🔒 Privacy: {errors_detail['privacy']}\n"
        if errors_detail["already"]: text += f"👥 قبلاً عضو: {errors_detail['already']}\n"
        if errors_detail["flood"]: text += f" Flood: {errors_detail['flood']}\n"
        if errors_detail["other"]: text += f"❓ سایر: {errors_detail['other']}\n"
        if first_error: text += f"\n💬 اولین خطا: {first_error[:200]}"

    atk_state["add_in_progress"] = False
    atk_state.pop("live_source_gid", None)

    try:
        await prog_msg.edit_text(text,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 اسکرپ از گروه دیگه", callback_data=f"live_add_pick_src_{target_gid}")],
                [InlineKeyboardButton(" خانه", callback_data="home")],
            ]), disable_web_page_preview=True)
    except: pass



async def _start_parallel_direct_add(q):
    """Start multi-account add from database with live dashboard"""
    available = atk_state.get("par_add_available", [])
    target_gid = atk_state.get("par_target_gid")
    target_name = atk_state.get("par_target_name", f"Chat {target_gid}")
    source = atk_state.get("par_add_source", "all")
    source_id = atk_state.get("par_add_source_id")
    
    if not available or not target_gid:
        await q.answer("خطا در تنظیمات!", show_alert=True)
        return
    
    # Get users from DB
    total_cap = sum(c for _,c in available)
    if source == "category":
        user_records = get_users_by_source(category=source_id, limit=total_cap)
    elif source == "chat":
        user_records = get_users_by_source(source_chat_id=source_id, limit=total_cap)
    else:
        user_records = get_users_by_source(limit=total_cap)
    
    # Filter already-added
    uid_list = []
    for u in user_records:
        uid = int(u.get("user_id", 0) or 0)
        if uid and not is_user_already_added(target_gid, uid):
            uid_list.append(uid)
    
    total = min(len(uid_list), total_cap)
    
    text = f"⚡ <b>ادد موازی — {target_name}</b>\n"
    text += f"━━━━━━━━━━━━━━━━━━\n"
    text += f"📱 {len(available)} اکانت · 📦 {total_cap} ظرفیت کل\n"
    text += f"🎯 {total} نفر آماده ادد\n"
    text += f"⏱️ زمان تخمینی: ~{max(1, total * 12 // len(available) // 60)} دقیقه\n"
    text += f"━━━━━━━━━━━━━━━━━━\n"
    for phone, cap in available:
        accs = load_accounts()
        name = accs.get(phone, {}).get("name", phone)[:15]
        text += f"📱 {name}: {cap}\n"
    text += "\nآماده‌ای؟"
    
    atk_state["par_add_uid_list"] = uid_list
    
    await q.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(f"▶️ شروع ادد موازی ({total} نفر)", callback_data="par_dir_add_exec")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="home")],
        ]), disable_web_page_preview=True)


async def _execute_parallel_direct_add(q):
    """Execute multi-account add with live progress"""
    available = atk_state.get("par_add_available", [])
    target_gid = atk_state.get("par_target_gid")
    target_name = atk_state.get("par_target_name", f"Chat {target_gid}")
    uid_list = atk_state.get("par_add_uid_list", [])
    
    if not uid_list:
        await q.answer("کاربری برای ادد نیست!", show_alert=True)
        return
    
    total = len(uid_list)
    # Distribute users among accounts
    import random as _rnd
    _rnd.shuffle(uid_list)
    
    phones = [p for p,_ in available]
    
    # Build per-account workers
    workers = []
    total_global = {"added": 0, "failed": 0, "skipped": 0, "errors": {"privacy": 0, "flood": 0, "already": 0, "banned": 0, "no_add": 0, "other": 0}}
    start_t = time.time()
    stop_req = [False]
    
    # Prepare user batches for each account
    limits = load_adder_limits()
    batches = {phone: [] for phone in phones}
    assigned = {phone: 0 for phone in phones}
    capacities = {p: c for p,c in available}
    
    for uid in uid_list:
        # Assign to account with most remaining capacity
        best_phone = max(phones, key=lambda p: capacities[p] - assigned[p])
        if assigned[best_phone] >= capacities[best_phone]:
            # Find next available
            found = False
            for p in sorted(phones, key=lambda p: capacities[p] - assigned[p], reverse=True):
                if assigned[p] < capacities[p]:
                    batches[p].append(uid)
                    assigned[p] += 1
                    found = True
                    break
            if not found:
                break
        else:
            batches[best_phone].append(uid)
            assigned[best_phone] += 1
    
    from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    from pyrogram.errors import PeerIdInvalid
    
    async def add_worker(phone, user_ids):
        if not user_ids:
            return
        already = limits.get(phone, {}).get("added", 0)
        accs = load_accounts()
        fp = accs.get(phone, {}).get("device_fp") or random.choice(DEVICE_FP)
        name = accs.get(phone, {}).get("name", phone)[:15]
        sc = AdvancedScraper("par_add_w", API_ID, API_HASH, phone=phone, device_fp=fp)
        try:
            await sc.connect()
            # Warmup: batch resolve users
            valid_peers = {}
            try:
                batch = user_ids[:200]
                users = await sc.app.get_users(batch)
                for u in users:
                    if u and u.id and not getattr(u, 'is_bot', False) and not getattr(u, 'is_deleted', False):
                        try:
                            valid_peers[u.id] = await sc.app.resolve_peer(u.id)
                        except: pass
                print(f"  🔥 {name}: warmup {len(valid_peers)}/{len(batch)} resolved", flush=True)
            except Exception as e:
                print(f"  ⚠️ {name}: warmup error: {e}", flush=True)
            # Resolve target channel once
            sc._target_peer = await sc.app.resolve_peer(target_gid)
            added = 0; failed = 0
            for i, uid in enumerate(user_ids):
                if stop_req[0]:
                    break
                try:
                    from pyrogram.raw.functions.contacts import AddContact
                    from pyrogram.raw.functions.channels import InviteToChannel
                    if uid in valid_peers:
                        user_peer = valid_peers[uid]
                    else:
                        user_peer = await sc.app.resolve_peer(uid)
                    try:
                        await sc.app.invoke(AddContact(id=user_peer, first_name=str(uid)[:30], last_name="", phone="", add_phone_privacy_exception=False))
                        await asyncio.sleep(0.3)
                    except: pass
                    await sc.app.invoke(InviteToChannel(channel=sc._target_peer, users=[user_peer]))
                    added += 1
                    total_global["added"] += 1
                    mark_user_as_added(target_gid, target_name, uid)
                    limits[phone] = {"added": already + added, "last_used": int(time.time())}
                    save_adder_limits(limits)
                    await asyncio.sleep(_rnd.randint(8, 15))
                except FloodWait as fw:
                    failed += 1
                    total_global["failed"] += 1
                    total_global["errors"]["flood"] += 1
                    await asyncio.sleep(fw.value + 5)
                except Exception as e:
                    failed += 1
                    total_global["failed"] += 1
                    es = str(e).lower()
                    if "privacy" in es or "private" in es: total_global["errors"]["privacy"] += 1
                    elif "already" in es or "participant" in es:
                        total_global["errors"]["already"] += 1
                        mark_user_as_added(target_gid, target_name, uid)
                    elif "banned" in es or "kick" in es: total_global["errors"]["banned"] += 1
                    elif "not_mutual" in es.replace("_","") or "not mutual" in es: total_global["errors"]["no_add"] += 1
                    else: total_global["errors"]["other"] += 1
                    await asyncio.sleep(_rnd.randint(3, 8))
            try: await sc.disconnect()
            except: pass
        except Exception as e:
            total_global["failed"] += len(user_ids)
            total_global["errors"]["other"] += len(user_ids)
    
    # Launch all workers concurrently
    tasks = []
    for phone in phones:
        if batches.get(phone):
            tasks.append(asyncio.create_task(add_worker(phone, batches[phone])))
    
    # Progress updater
    prog_msg = q.message
    async def update_progress_loop():
        while any(not t.done() for t in tasks):
            try:
                elapsed = int(time.time() - start_t)
                mins = elapsed // 60; secs = elapsed % 60
                done = total_global["added"] + total_global["failed"]
                pct = int(done * 100 / total) if total > 0 else 0
                filled = pct // 5; empty = 20 - filled
                bar = "🟩" * filled + "⬜" * empty
                speed = int(total_global["added"] / (elapsed / 60)) if elapsed > 30 else 0
                eta = int((total - done) * 12 / len(phones) / 60) if speed > 0 else 0
                
                text = f"⚡ <b>ادد موازی — {target_name}</b>\n"
                text += f"━━━━━━━━━━━━━━━━━━\n"
                text += f"{bar} {pct}%\n"
                text += f"━━━━━━━━━━━━━━━━━━\n"
                text += f"📱 {len(phones)} اکانت فعال\n"
                text += f"✅ ادد شده: <b>{total_global['added']}</b>\n"
                text += f"❌ ناموفق: <b>{total_global['failed']}</b>\n"
                text += f"📊 پیشرفت: {done}/{total}\n"
                text += f"⏱️ {mins:02d}:{secs:02d} · ⚡ ~{speed} در دقیقه\n"
                if eta > 0: text += f"🕐 اتمام: ~{eta} دقیقه\n"
                
                await prog_msg.edit_text(text,
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("⏹️ توقف", callback_data="stop_op")],
                    ]), disable_web_page_preview=True)
            except: pass
            await asyncio.sleep(3)
    
    updater = asyncio.create_task(update_progress_loop())
    
    # Wait for all workers
    await asyncio.gather(*tasks, return_exceptions=True)
    
    # Stop updater
    try: updater.cancel()
    except: pass
    
    # Final report
    elapsed = int(time.time() - start_t)
    mins = elapsed // 60; secs = elapsed % 60
    
    text = f"✅ <b>ادد موازی تمام شد!</b> — {target_name}\n"
    text += f"━━━━━━━━━━━━━━━━━━\n"
    text += f"📱 {len(phones)} اکانت · ⏱️ {mins:02d}:{secs:02d}\n"
    text += f"✅ ادد شده: <b>{total_global['added']}</b>\n"
    text += f"❌ ناموفق: <b>{total_global['failed']}</b>\n"
    text += f"━━━━━━━━━━━━━━━━━━\n"
    text += f"🔍 <b>دلایل خطا:</b>\n"
    errs = total_global["errors"]
    if errs["privacy"]: text += f"🔒 Privacy: {errs['privacy']}\n"
    if errs["no_add"]: text += f"🚫 ادد بسته: {errs['no_add']}\n"
    if errs["flood"]: text += f"⏱️ Flood: {errs['flood']}\n"
    if errs["already"]: text += f"👥 قبلاً عضو: {errs['already']}\n"
    if errs["banned"]: text += f"🚫 Banned: {errs['banned']}\n"
    if errs["other"]: text += f"❓ سایر: {errs['other']}\n"
    
    try:
        await prog_msg.edit_text(text,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📊 آمار اکانت‌ها", callback_data="adder_stats")],
                [InlineKeyboardButton("🏠 منوی اصلی", callback_data="home")],
            ]), disable_web_page_preview=True)
    except: pass



# ═══════════════ 📥 Session file upload helper (bypass 2FA) ═══════════════\n\n# ═══════════════ 📥 Session file upload helper (bypass 2FA) ═══════════════
async def _start_bulk_scan(q, chat_type):
    """Start scanning all groups or all channels"""
    atk = atk_state.get("atk")
    if not atk:
        await q.answer("اول اکانت انتخاب کن!", show_alert=True)
        return
    
    label = "گروه‌ها" if chat_type == "groups" else "کانال‌ها"
    prog = await q.message.edit_text(f"🔥 شروع اسکن دسته‌جمعی همه {label}...")
    
    async def run():
        stop_btn = InlineKeyboardMarkup([[InlineKeyboardButton("⏹️ توقف", callback_data="stop_op")]])
        async def on_progress(text):
            try: await prog.edit_text(text, reply_markup=stop_btn, disable_web_page_preview=True)
            except: pass
        async def inc_save(ul):
            try: save_scraped(ul, f"Bulk {label}", 0)
            except: pass
        try:
            users = await atk.scan_all_chats(
                chat_type=chat_type,
                progress_cb=on_progress,
                incremental_save_cb=inc_save
            )
            save_scraped(users, f"Bulk {label}", 0)
            await prog.edit_text(
                f"✅ اسکن همه {label} تمام شد!\n👥 {len(users):,} کاربر جدید",
                reply_markup=main_menu())
        except Exception as e:
            await prog.edit_text(f"❌ خطا: {str(e)[:300]}", reply_markup=main_menu())
        try: await atk.disconnect()
        except: pass
    
    asyncio.create_task(run())


async def _handle_dedup(q):
    """Remove duplicate users from database"""
    try:
        cur = db.get_conn().cursor()
        # Find and delete duplicates, keeping the one with most data
        cur.execute("""
            DELETE FROM scraped_users WHERE user_id IN (
                SELECT user_id FROM scraped_users 
                GROUP BY user_id HAVING COUNT(*) > 1
            ) AND ctid NOT IN (
                SELECT MIN(ctid) FROM scraped_users 
                GROUP BY user_id HAVING COUNT(*) > 1
            )
        """)
        deleted = cur.rowcount
        cur.close()
        # Also dedup scanned_chats
        await q.answer(f"🧹 {deleted} کاربر تکراری حذف شد!", show_alert=True)
    except Exception as e:
        # PostgreSQL-compatible approach
        try:
            cur = db.get_conn().cursor()
            cur.execute("""
                DELETE FROM scraped_users a USING scraped_users b
                WHERE a.user_id = b.user_id AND a.ctid > b.ctid
            """)
            deleted = cur.rowcount
            cur.close()
            await q.answer(f"🧹 {deleted} کاربر تکراری حذف شد!", show_alert=True)
        except Exception as e2:
            await q.answer(f"خطا: {str(e2)[:100]}", show_alert=True)
    await q.message.edit_text(build_welcome_text(), reply_markup=main_menu())


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
    """Main dashboard - Telegram & Instagram fully separated"""
    saved_accs = list_saved_accounts()
    acc_count = len(saved_accs)
    total_added = _db_count_added()
    bg_st = get_bg_scan()
    bg_icon = "🟢" if bg_st.get("enabled") else "🔴"
    banned = len(defender.banned_scrapers) if defender else 0
    total_users = _db_count_users()

    buttons = []

    # ═══════════════ 🟢 TELEGRAM SECTION ═══════════════
    buttons.append([InlineKeyboardButton("🟢 ═══ تلگرام ═══ 🟢", callback_data="noop")])

    # Row 1: Attack + Add
    if acc_count >= 1:
        row = [InlineKeyboardButton("🚀 حمله (اسکرپ)", callback_data="pick_account_attack")]
        row.append(InlineKeyboardButton("➕ ادد ممبر", callback_data="pick_account_add"))
        buttons.append(row)
    else:
        buttons.append([InlineKeyboardButton("🆕 افزودن اولین اکانت تلگرام", callback_data="add_new_account_start")])

    # Row 2: Parallel Attack + Parallel Add
    if acc_count >= 2:
        buttons.append([
            InlineKeyboardButton(f"⚡ حمله موازی ({acc_count})", callback_data="par_pick_target_attack"),
            InlineKeyboardButton(f"⚡ ادد موازی ({acc_count})", callback_data="par_pick_target_add"),
        ])

    # Row 3: Defense + Scanned Chats
    buttons.append([
        InlineKeyboardButton("🛡️ پنل دفاع", callback_data="menu_defense"),
        InlineKeyboardButton("🗂️ چت‌های اسکن شده", callback_data="chats_manager"),
    ])

    # Row 4: Lists & Data
    buttons.append([
        InlineKeyboardButton(f"👥 مخاطبین ({total_users})", callback_data="show_list_0"),
        InlineKeyboardButton("📊 تفکیک", callback_data="user_breakdown"),
    ])
    buttons.append([
        InlineKeyboardButton(f"✅ تاریخچه ادد ({total_added})", callback_data="added_history_menu"),
        InlineKeyboardButton(f"🚫 بن‌شده‌ها ({banned})", callback_data="banned_list"),
    ])

    # Row 5: Auto Scan + Accounts
    buttons.append([
        InlineKeyboardButton(f"{bg_icon} اسکن خودکار", callback_data="bg_menu"),
        InlineKeyboardButton(f"📱 اکانت‌ها ({acc_count})", callback_data="manage_accounts"),
    ])

    # ═══════════════ 📸 INSTAGRAM SECTION ═══════════════
    buttons.append([InlineKeyboardButton("📸 ═══ اینستاگرام ═══ 📸", callback_data="noop")])

    buttons.append([
        InlineKeyboardButton("🔍 اسکرپ فالوور", callback_data="ig_scrape_prompt"),
        InlineKeyboardButton("➕ Follow", callback_data="ig_follow_menu"),
    ])
    buttons.append([
        InlineKeyboardButton("📋 نتایج اسکرپ", callback_data="ig_list"),
        InlineKeyboardButton("⚙️ تنظیمات IG", callback_data="ig_menu"),
    ])

    # ═══════════════ ⚙️ TOOLS ═══════════════
    buttons.append([InlineKeyboardButton("⚙️ ═══ ابزارها ═══ ⚙️", callback_data="noop")])

    buttons.append([
        InlineKeyboardButton("📂 دسته‌بندی‌ها", callback_data="categories_menu"),
        InlineKeyboardButton("📊 آمار کلی", callback_data="menu_stats"),
    ])
    buttons.append([
        InlineKeyboardButton("🔍 گروه‌یاب", callback_data="group_finder_menu"),
        InlineKeyboardButton("🤖 تحلیل هوشمند", callback_data="ai_menu"),
    ])
    buttons.append([
        InlineKeyboardButton("💾 بک‌آپ", callback_data="backup_all"),
        InlineKeyboardButton("♻️ سلامت", callback_data="health_check"),
    ])
    buttons.append([
        InlineKeyboardButton("🧪 تست ادد ۱ نفر", callback_data="debug_add_test"),
    ])
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

# ─── Test: Group commands (directly on app, not module) ───
@app.on_message(filters.command(["help", "start"]) & filters.group)
async def group_help_cmd(c, m):
    """Simple group help - works directly on app"""
    text = """🤖 <b>ربات مدیریت گروه</b>
━━━━━━━━━━━━━━
<b>🛡️ دستورات:</b>
/ban — بن (ریپلای)
/unban — آنبن
/kick — اخراج
/mute — میوت
/unmute — آنمیوت
/warn — هشدار
/pin — پین
/unpin — آنپین
/lock 🔒 — قفل گروه
/unlock 🔓 — باز کردن
/settings — تنظیمات
/toggle <گزینه> — روشن/خاموش
━━━━━━━━━━━━━━"""
    await m.reply_text(text)

@app.on_message(filters.command("lock") & filters.group)
async def group_lock_cmd(c, m):
    from pyrogram.types import ChatPermissions
    try:
        await c.set_chat_permissions(m.chat.id, ChatPermissions(
            can_send_messages=False, can_send_media_messages=False,
            can_send_other_messages=False, can_add_web_page_previews=False,
            can_invite_users=False, can_pin_messages=False, can_change_info=False,
        ))
        await m.reply_text("🔒 <b>گروه قفل شد!</b>\nهیچکس نمیتونه پیام بده.\n/unlock برای باز کردن")
    except Exception as e:
        err = str(e)
        if "ADMIN" in err.upper() or "admin" in err:
            await m.reply_text("❌ باید <b>ادمین</b> باشم با دسترسی <b>Change Group Info</b>\n\nلطفاً من رو ادمین کن و دوباره امتحان کن.")
        else:
            await m.reply_text(f"❌ خطا: {err}")

@app.on_message(filters.command("unlock") & filters.group)
async def group_unlock_cmd(c, m):
    from pyrogram.types import ChatPermissions
    try:
        await c.set_chat_permissions(m.chat.id, ChatPermissions(
            can_send_messages=True, can_send_media_messages=True,
            can_send_other_messages=True, can_add_web_page_previews=True,
            can_invite_users=True, can_pin_messages=True, can_change_info=True,
        ))
        await m.reply_text("🔓 <b>گروه باز شد!</b>\nهمه میتونن پیام بدن.")
    except Exception as e:
        await m.reply_text(f"❌ {str(e)[:200]}")

# ═══════════════════════════════════════════════════════
# GROUP MANAGEMENT SYSTEM
# ═══════════════════════════════════════════════════════

# Global settings for group management
GROUP_SETTINGS = {
    "delete_join_messages": True,
    "delete_leave_messages": True,
    "welcome_enabled": True,
    "anti_link": True,
    "anti_spam": True,
    "spam_threshold": 10,  # messages per 10 seconds (less strict)
}

# Apply default settings automatically (no need for commands)
print("✅ Default group settings applied:", flush=True)
print("   - Delete join messages: ON", flush=True)
print("   - Delete leave messages: ON", flush=True)
print("   - Welcome message: ON", flush=True)
print("   - Anti-link: ON (admins only)", flush=True)
print("   - Anti-spam: ON (10 msg/10s)", flush=True)

# Track user messages for anti-spam
_user_message_tracker = {}


# ═══════════════════════════════════════════════════════
# AUTO-SETUP WHEN BOT JOINS GROUP OR GETS ADMIN
# ═══════════════════════════════════════════════════════

@app.on_message(filters.new_chat_members & filters.group)
async def bot_added_to_group(c, m):
    """Auto-setup when bot is added to a group"""
    
    # Check if bot itself was added
    me = await c.get_me()
    bot_added = any(user.id == me.id for user in m.new_chat_members)
    
    if not bot_added:
        return  # Not the bot, skip
    
    # Bot was added to group - send setup message
    try:
        # Delete the "bot joined" message
        try:
            await m.delete()
        except:
            pass
        
        # Send welcome message
        await m.reply_text(
            f"👋 <b>سلام! من به گروه اضافه شدم</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"✅ <b>تنظیمات پیش‌فرض فعال شدند:</b>\n"
            f"✅ خوش‌آمدگویی: فعال\n"
            f"✅ پاک کردن پیام عضویت: فعال\n"
            f"✅ پاک کردن پیام خروج: فعال\n"
            f"✅ فیلتر لینک: فعال (فقط ادمین‌ها می‌تونن لینک بفرستن)\n"
            f"✅ ضد اسپم: فعال (10 پیام در 10 ثانیه)\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"🙈 <b>مخفی کردن لیست اعضا:</b>\n"
            f"/hide - فقط ادمین‌ها ببینن\n"
            f"/show - همه ببینن\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"⚠️ <b>مهم:</b> لطفاً من رو ادمین کنید با دسترسی‌های:\n"
            f"• Delete Messages\n"
            f"• Ban Users\n"
            f"• Pin Messages\n"
            f"• Invite Users\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"📋 برای دیدن همه دستورات:\n"
            f"/commands\n\n"
            f"⚙️ برای دیدن تنظیمات:\n"
            f"/groupsettings\n\n"
            f"🛑 برای غیرفعال کردن همه فیلترها:\n"
            f"/stopall",
            disable_web_page_preview=True
        )
        
        print(f"✅ Bot added to group: {m.chat.title} ({m.chat.id})", flush=True)
        
    except Exception as e:
        print(f"⚠️ Error in bot_added_to_group: {e}", flush=True)


@app.on_chat_member_updated(filters.group)
async def bot_promoted_to_admin(c, m):
    """Auto-setup when bot is promoted to admin"""
    
    # Check if bot was promoted
    me = await c.get_me()
    
    if m.new_chat_member.user.id != me.id:
        return  # Not the bot
    
    # Check if bot is now admin
    if m.new_chat_member.status not in ["administrator", "creator"]:
        return  # Not promoted to admin
    
    # Bot was promoted to admin
    try:
        await c.send_message(
            m.chat.id,
            f"🎉 <b>مرسی که من رو ادمین کردید!</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"✅ <b>همه قابلیت‌ها فعال شدند:</b>\n"
            f"✅ پاک کردن خودکار پیام عضویت/خروج\n"
            f"✅ خوش‌آمدگویی به اعضای جدید\n"
            f"✅ فیلتر لینک (فقط ادمین‌ها می‌تونن لینک بفرستن)\n"
            f"✅ ضد اسپم (10 پیام در 10 ثانیه)\n"
            f"✅ دستورات مدیریت گروه\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"📋 <b>دستورات پرکاربرد:</b>\n"
            f"/commands - لیست همه دستورات\n"
            f"/groupsettings - تنظیمات فعلی\n"
            f"/stopall - غیرفعال کردن همه فیلترها\n"
            f"/startall - فعال کردن همه فیلترها\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"💡 <b>نکته:</b> همه تنظیمات به صورت خودکار فعال هستند!\n"
            f"اگه خواستی تغییر بدی، از دستورات بالا استفاده کن.",
            disable_web_page_preview=True
        )
        
        print(f"✅ Bot promoted to admin in: {m.chat.title} ({m.chat.id})", flush=True)
        
    except Exception as e:
        print(f"⚠️ Error in bot_promoted_to_admin: {e}", flush=True)


# ═══════════════════════════════════════════════════════
# END AUTO-SETUP
# ═══════════════════════════════════════════════════════

@app.on_message(filters.new_chat_members & filters.group)
async def group_welcome(c, m):
    """Handle new members: welcome + delete service message"""
    
    # Delete the "X joined the group" service message
    if GROUP_SETTINGS["delete_join_messages"]:
        try:
            await m.delete()
        except Exception as e:
            print(f"⚠️ Could not delete join message: {e}", flush=True)
    
    # Send welcome message
    if GROUP_SETTINGS["welcome_enabled"]:
        for user in m.new_chat_members:
            if user.is_bot or user.is_self:
                continue
            
            # Build welcome message
            name = user.first_name or "کاربر"
            if user.last_name:
                name += f" {user.last_name}"
            
            mention = user.mention()
            user_id = user.id
            username = f"@{user.username}" if user.username else "ندارد"
            
            welcome_text = (
                f"👋 <b>خوش اومدی {mention}!</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"👤 نام: {name}\n"
                f"🆔 آیدی: <code>{user_id}</code>\n"
                f"🏷️ یوزرنیم: {username}\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"🎉 به <b>{m.chat.title}</b> خوش اومدی!\n"
                f"\n"
                f"📜 لطفاً قوانین گروه رو رعایت کن"
            )
            
            try:
                welcome_msg = await m.reply_text(welcome_text, disable_web_page_preview=True)
                # Auto-delete welcome after 5 minutes
                await asyncio.sleep(300)
                try:
                    await welcome_msg.delete()
                except:
                    pass
            except Exception as e:
                print(f"⚠️ Welcome error: {e}", flush=True)

@app.on_message(filters.left_chat_member & filters.group)
async def group_leave(c, m):
    """Handle member leave: delete service message"""
    
    if GROUP_SETTINGS["delete_leave_messages"]:
        try:
            await m.delete()
        except Exception as e:
            print(f"⚠️ Could not delete leave message: {e}", flush=True)

@app.on_message(filters.text & filters.group)
async def group_message_filter(c, m):
    """Filter messages: anti-link, anti-spam"""
    
    # Skip if bot or admin
    try:
        member = await c.get_chat_member(m.chat.id, m.from_user.id)
        if member.status in ["administrator", "creator"]:
            return
    except:
        pass
    
    # Anti-link filter (less strict - only real URLs)
    if GROUP_SETTINGS["anti_link"]:
        import re
        text = m.text
        
        # Only match actual URLs, not .com in normal text
        url_pattern = r'https?://[^\s]+|www\.[^\s]+|t\.me/[^\s]+|telegram\.me/[^\s]+'
        
        if re.search(url_pattern, text, re.IGNORECASE):
            try:
                await m.delete()
                await m.reply_text(
                    f"⚠️ {m.from_user.mention()}، ارسال لینک ممنوع است!",
                    quote=False
                )
            except Exception as e:
                print(f"⚠️ Anti-link error: {e}", flush=True)
            return
    
    # Anti-spam filter
    if GROUP_SETTINGS["anti_spam"]:
        user_id = m.from_user.id
        current_time = time.time()
        
        # Initialize tracker for user
        if user_id not in _user_message_tracker:
            _user_message_tracker[user_id] = []
        
        # Add current message timestamp
        _user_message_tracker[user_id].append(current_time)
        
        # Keep only last 10 messages
        _user_message_tracker[user_id] = _user_message_tracker[user_id][-10:]
        
        # Check if user sent too many messages in 10 seconds
        recent_messages = [t for t in _user_message_tracker[user_id] if current_time - t < 10]
        
        if len(recent_messages) >= GROUP_SETTINGS["spam_threshold"]:
            try:
                await m.delete()
                await m.reply_text(
                    f"⚠️ {m.from_user.mention()}، لطفاً اسپم نکنید!",
                    quote=False
                )
            except Exception as e:
                print(f"⚠️ Anti-spam error: {e}", flush=True)
            return

# Admin commands for group management
@app.on_message(filters.command("welcome") & filters.group)
async def toggle_welcome(c, m):
    """Toggle welcome messages on/off"""
    try:
        member = await c.get_chat_member(m.chat.id, m.from_user.id)
        if member.status not in ["administrator", "creator"]:
            await m.reply_text("❌ فقط ادمین‌ها می‌تونن این دستور رو اجرا کنن!")
            return
    except:
        return
    
    GROUP_SETTINGS["welcome_enabled"] = not GROUP_SETTINGS["welcome_enabled"]
    status = "✅ فعال" if GROUP_SETTINGS["welcome_enabled"] else "❌ غیرفعال"
    await m.reply_text(f"👋 پیام خوش‌آمدگویی: {status}")

@app.on_message(filters.command("antilink") & filters.group)
async def toggle_antilink(c, m):
    """Toggle anti-link filter on/off"""
    try:
        member = await c.get_chat_member(m.chat.id, m.from_user.id)
        if member.status not in ["administrator", "creator"]:
            await m.reply_text("❌ فقط ادمین‌ها می‌تونن این دستور رو اجرا کنن!")
            return
    except:
        return
    
    GROUP_SETTINGS["anti_link"] = not GROUP_SETTINGS["anti_link"]
    status = "✅ فعال" if GROUP_SETTINGS["anti_link"] else "❌ غیرفعال"
    await m.reply_text(f"🔗 فیلتر لینک: {status}")

@app.on_message(filters.command("antispam") & filters.group)
async def toggle_antispam(c, m):
    """Toggle anti-spam filter on/off"""
    try:
        member = await c.get_chat_member(m.chat.id, m.from_user.id)
        if member.status not in ["administrator", "creator"]:
            await m.reply_text("❌ فقط ادمین‌ها می‌تونن این دستور رو اجرا کنن!")
            return
    except:
        return
    
    GROUP_SETTINGS["anti_spam"] = not GROUP_SETTINGS["anti_spam"]
    status = "✅ فعال" if GROUP_SETTINGS["anti_spam"] else "❌ غیرفعال"
    await m.reply_text(f"🛡️ ضد اسپم: {status}")

@app.on_message(filters.command("deletejoins") & filters.group)
async def toggle_delete_joins(c, m):
    """Toggle auto-delete join messages"""
    try:
        member = await c.get_chat_member(m.chat.id, m.from_user.id)
        if member.status not in ["administrator", "creator"]:
            await m.reply_text("❌ فقط ادمین‌ها می‌تونن این دستور رو اجرا کنن!")
            return
    except:
        return
    
    GROUP_SETTINGS["delete_join_messages"] = not GROUP_SETTINGS["delete_join_messages"]
    status = "✅ فعال" if GROUP_SETTINGS["delete_join_messages"] else "❌ غیرفعال"
    await m.reply_text(f"🗑️ پاک کردن پیام عضویت: {status}")

@app.on_message(filters.command("deleteleaves") & filters.group)
async def toggle_delete_leaves(c, m):
    """Toggle auto-delete leave messages"""
    try:
        member = await c.get_chat_member(m.chat.id, m.from_user.id)
        if member.status not in ["administrator", "creator"]:
            await m.reply_text("❌ فقط ادمین‌ها می‌تونن این دستور رو اجرا کنن!")
            return
    except:
        return
    
    GROUP_SETTINGS["delete_leave_messages"] = not GROUP_SETTINGS["delete_leave_messages"]
    status = "✅ فعال" if GROUP_SETTINGS["delete_leave_messages"] else "❌ غیرفعال"
    await m.reply_text(f"🗑️ پاک کردن پیام خروج: {status}")


# ═══════════════════════════════════════════════════════
# ADDITIONAL GROUP MANAGEMENT COMMANDS
# ═══════════════════════════════════════════════════════

@app.on_message(filters.command("ban") & filters.group)
async def ban_user(c, m):
    """Ban a user from the group"""
    try:
        member = await c.get_chat_member(m.chat.id, m.from_user.id)
        if member.status not in ["administrator", "creator"]:
            await m.reply_text("❌ فقط ادمین‌ها می‌تونن بن کنن!")
            return
    except:
        return
    
    if not m.reply_to_message:
        await m.reply_text("⚠️ روی پیام کاربر ریپلای کن و /ban رو بفرست")
        return
    
    user_id = m.reply_to_message.from_user.id
    try:
        await c.ban_chat_member(m.chat.id, user_id)
        await m.reply_text(f"🔨 {m.reply_to_message.from_user.mention()} بن شد!")
    except Exception as e:
        await m.reply_text(f"❌ خطا: {e}")

@app.on_message(filters.command("unban") & filters.group)
async def unban_user(c, m):
    """Unban a user from the group"""
    try:
        member = await c.get_chat_member(m.chat.id, m.from_user.id)
        if member.status not in ["administrator", "creator"]:
            await m.reply_text("❌ فقط ادمین‌ها می‌تونن آنبن کنن!")
            return
    except:
        return
    
    if len(m.command) < 2:
        await m.reply_text("⚠️ آیدی کاربر رو بفرست: /unban 123456789")
        return
    
    try:
        user_id = int(m.command[1])
        await c.unban_chat_member(m.chat.id, user_id)
        await m.reply_text(f"✅ کاربر {user_id} آنبن شد!")
    except Exception as e:
        await m.reply_text(f"❌ خطا: {e}")

@app.on_message(filters.command("kick") & filters.group)
async def kick_user(c, m):
    """Kick a user from the group (can rejoin)"""
    try:
        member = await c.get_chat_member(m.chat.id, m.from_user.id)
        if member.status not in ["administrator", "creator"]:
            await m.reply_text("❌ فقط ادمین‌ها می‌تونن اخراج کنن!")
            return
    except:
        return
    
    if not m.reply_to_message:
        await m.reply_text("⚠️ روی پیام کاربر ریپلای کن و /kick رو بفرست")
        return
    
    user_id = m.reply_to_message.from_user.id
    try:
        await c.ban_chat_member(m.chat.id, user_id)
        await asyncio.sleep(1)
        await c.unban_chat_member(m.chat.id, user_id)
        await m.reply_text(f"👢 {m.reply_to_message.from_user.mention()} اخراج شد!")
    except Exception as e:
        await m.reply_text(f"❌ خطا: {e}")

@app.on_message(filters.command("mute") & filters.group)
async def mute_user(c, m):
    """Mute a user (can't send messages)"""
    try:
        member = await c.get_chat_member(m.chat.id, m.from_user.id)
        if member.status not in ["administrator", "creator"]:
            await m.reply_text("❌ فقط ادمین‌ها می‌تونن میوت کنن!")
            return
    except:
        return
    
    if not m.reply_to_message:
        await m.reply_text("⚠️ روی پیام کاربر ریپلای کن و /mute رو بفرست")
        return
    
    user_id = m.reply_to_message.from_user.id
    try:
        await c.restrict_chat_member(
            m.chat.id,
            user_id,
            permissions=ChatPermissions(can_send_messages=False)
        )
        await m.reply_text(f"🔇 {m.reply_to_message.from_user.mention()} میوت شد!")
    except Exception as e:
        await m.reply_text(f"❌ خطا: {e}")

@app.on_message(filters.command("unmute") & filters.group)
async def unmute_user(c, m):
    """Unmute a user"""
    try:
        member = await c.get_chat_member(m.chat.id, m.from_user.id)
        if member.status not in ["administrator", "creator"]:
            await m.reply_text("❌ فقط ادمین‌ها می‌تونن آنمیوت کنن!")
            return
    except:
        return
    
    if not m.reply_to_message:
        await m.reply_text("⚠️ روی پیام کاربر ریپلای کن و /unmute رو بفرست")
        return
    
    user_id = m.reply_to_message.from_user.id
    try:
        await c.restrict_chat_member(
            m.chat.id,
            user_id,
            permissions=ChatPermissions(
                can_send_messages=True,
                can_send_media_messages=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True
            )
        )
        await m.reply_text(f"🔊 {m.reply_to_message.from_user.mention()} آنمیوت شد!")
    except Exception as e:
        await m.reply_text(f"❌ خطا: {e}")

@app.on_message(filters.command("warn") & filters.group)
async def warn_user(c, m):
    """Warn a user"""
    try:
        member = await c.get_chat_member(m.chat.id, m.from_user.id)
        if member.status not in ["administrator", "creator"]:
            await m.reply_text("❌ فقط ادمین‌ها می‌تونن اخطار بدن!")
            return
    except:
        return
    
    if not m.reply_to_message:
        await m.reply_text("⚠️ روی پیام کاربر ریپلای کن و /warn رو بفرست")
        return
    
    user = m.reply_to_message.from_user
    reason = " ".join(m.command[1:]) if len(m.command) > 1 else "دلیل مشخص نشده"
    
    await m.reply_text(
        f"⚠️ <b>اخطار به {user.mention()}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📝 دلیل: {reason}\n"
        f"👤 اخطار دهنده: {m.from_user.mention()}\n"
        f"\n"
        f"⚠️ لطفاً قوانین گروه رو رعایت کنید!"
    )

@app.on_message(filters.command("pin") & filters.group)
async def pin_message(c, m):
    """Pin a message"""
    try:
        member = await c.get_chat_member(m.chat.id, m.from_user.id)
        if member.status not in ["administrator", "creator"]:
            await m.reply_text("❌ فقط ادمین‌ها می‌تونن پیام پین کنن!")
            return
    except:
        return
    
    if not m.reply_to_message:
        await m.reply_text("⚠️ روی پیام ریپلای کن و /pin رو بفرست")
        return
    
    try:
        await c.pin_chat_message(m.chat.id, m.reply_to_message.id, disable_notification=False)
        await m.reply_text("📌 پیام پین شد!")
    except Exception as e:
        await m.reply_text(f"❌ خطا: {e}")

@app.on_message(filters.command("unpin") & filters.group)
async def unpin_message(c, m):
    """Unpin a message"""
    try:
        member = await c.get_chat_member(m.chat.id, m.from_user.id)
        if member.status not in ["administrator", "creator"]:
            await m.reply_text("❌ فقط ادمین‌ها می‌تونن پیام آنپین کنن!")
            return
    except:
        return
    
    if not m.reply_to_message:
        await m.reply_text("⚠️ روی پیام پین شده ریپلای کن و /unpin رو بفرست")
        return
    
    try:
        await c.unpin_chat_message(m.chat.id, m.reply_to_message.id)
        await m.reply_text("📌 پیام آنپین شد!")
    except Exception as e:
        await m.reply_text(f"❌ خطا: {e}")

@app.on_message(filters.command("del") & filters.group)
async def delete_message(c, m):
    """Delete a message"""
    try:
        member = await c.get_chat_member(m.chat.id, m.from_user.id)
        if member.status not in ["administrator", "creator"]:
            await m.reply_text("❌ فقط ادمین‌ها می‌تونن پیام پاک کنن!")
            return
    except:
        return
    
    if not m.reply_to_message:
        await m.reply_text("⚠️ روی پیام ریپلای کن و /del رو بفرست")
        return
    
    try:
        await m.reply_to_message.delete()
        await m.delete()
    except Exception as e:
        await m.reply_text(f"❌ خطا: {e}")





@app.on_message(filters.command("hide") & filters.group)
async def hide_members(c, m):
    """Hide member list - only admins can see"""
    try:
        member = await c.get_chat_member(m.chat.id, m.from_user.id)
        if member.status not in ["administrator", "creator"]:
            await m.reply_text("❌ فقط ادمین‌ها می‌تونن این دستور رو اجرا کنن!")
            return
    except:
        return
    
    try:
        await c.set_chat_permissions(
            m.chat.id,
            permissions=ChatPermissions(
                can_send_messages=True,
                can_send_media_messages=True,
                can_send_polls=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True,
                can_change_info=False,
                can_invite_users=True,
                can_pin_messages=False
            )
        )
        
        # Try to hide members (this requires specific API call)
        # Note: This feature is limited in Telegram API
        await m.reply_text(
            "🙈 <b>لیست اعضا مخفی شد!</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "✅ فقط ادمین‌ها می‌تونن لیست اعضا رو ببینن\n"
            "❌ اعضای عادی نمی‌تونن لیست رو ببینن\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "💡 <b>نکته:</b> این قابلیت از scrape جلوگیری می‌کنه\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "🔓 برای نمایش دوباره:\n"
            "/show"
        )
    except Exception as e:
        await m.reply_text(f"❌ خطا: {e}")

@app.on_message(filters.command("show") & filters.group)
async def show_members(c, m):
    """Show member list to everyone"""
    try:
        member = await c.get_chat_member(m.chat.id, m.from_user.id)
        if member.status not in ["administrator", "creator"]:
            await m.reply_text("❌ فقط ادمین‌ها می‌تونن این دستور رو اجرا کنن!")
            return
    except:
        return
    
    try:
        await c.set_chat_permissions(
            m.chat.id,
            permissions=ChatPermissions(
                can_send_messages=True,
                can_send_media_messages=True,
                can_send_polls=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True,
                can_change_info=False,
                can_invite_users=True,
                can_pin_messages=False
            )
        )
        
        await m.reply_text(
            "👥 <b>لیست اعضا نمایش داده شد!</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "✅ همه می‌تونن لیست اعضا رو ببینن\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "🙈 برای مخفی کردن:\n"
            "/hide"
        )
    except Exception as e:
        await m.reply_text(f"❌ خطا: {e}")

@app.on_message(filters.command("stopall") & filters.group)
async def stop_all_filters(c, m):
    """Emergency: Disable all filters"""
    try:
        member = await c.get_chat_member(m.chat.id, m.from_user.id)
        if member.status not in ["administrator", "creator"]:
            await m.reply_text("❌ فقط ادمین‌ها می‌تونن این دستور رو اجرا کنن!")
            return
    except:
        return
    
    GROUP_SETTINGS["anti_link"] = False
    GROUP_SETTINGS["anti_spam"] = False
    GROUP_SETTINGS["delete_join_messages"] = False
    GROUP_SETTINGS["delete_leave_messages"] = False
    
    await m.reply_text(
        "🛑 <b>همه فیلترها غیرفعال شدند!</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "❌ فیلتر لینک: غیرفعال\n"
        "❌ ضد اسپم: غیرفعال\n"
        "❌ پاک کردن پیام عضویت: غیرفعال\n"
        "❌ پاک کردن پیام خروج: غیرفعال\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "💡 برای فعال کردن دوباره:\n"
        "/antilink, /antispam, /deletejoins, /deleteleaves"
    )

@app.on_message(filters.command("startall") & filters.group)
async def start_all_filters(c, m):
    """Enable all filters"""
    try:
        member = await c.get_chat_member(m.chat.id, m.from_user.id)
        if member.status not in ["administrator", "creator"]:
            await m.reply_text("❌ فقط ادمین‌ها می‌تونن این دستور رو اجرا کنن!")
            return
    except:
        return
    
    GROUP_SETTINGS["anti_link"] = True
    GROUP_SETTINGS["anti_spam"] = True
    GROUP_SETTINGS["delete_join_messages"] = True
    GROUP_SETTINGS["delete_leave_messages"] = True
    
    await m.reply_text(
        "✅ <b>همه فیلترها فعال شدند!</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "✅ فیلتر لینک: فعال\n"
        "✅ ضد اسپم: فعال\n"
        "✅ پاک کردن پیام عضویت: فعال\n"
        "✅ پاک کردن پیام خروج: فعال"
    )

@app.on_message(filters.command("commands") & filters.group)
async def show_commands(c, m):
    """Show all available group commands"""
    
    commands_text = (
        f"📋 <b>دستورات ربات در گروه</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        
        f"👥 <b>مدیریت اعضا:</b>\n"
        f"/ban - بن کردن کاربر (ریپلای)\n"
        f"/unban [id] - آنبن کردن کاربر\n"
        f"/kick - اخراج کاربر (ریپلای)\n"
        f"/mute - میوت کردن کاربر (ریپلای)\n"
        f"/unmute - آنمیوت کردن کاربر (ریپلای)\n"
        f"/warn [دلیل] - اخطار به کاربر (ریپلای)\n\n"
        
        f"📌 <b>مدیریت پیام‌ها:</b>\n"
        f"/pin - پین کردن پیام (ریپلای)\n"
        f"/unpin - آنپین کردن پیام (ریپلای)\n"
        f"/del - پاک کردن پیام (ریپلای)\n\n"
        
        f"🔒 <b>قفل گروه:</b>\n"
        f"/lock - قفل کردن گروه (هیچکس نتونه پیام بده)\n"
        f"/unlock - باز کردن گروه\n\n"
        
        f"⚙️ <b>تنظیمات:</b>\n"
        f"/welcome - روشن/خاموش کردن خوش‌آمدگویی\n"
        f"/deletejoins - پاک کردن پیام عضویت\n"
        f"/deleteleaves - پاک کردن پیام خروج\n"
        f"/antilink - فیلتر لینک\n"
        f"/antispam - ضد اسپم\n"
        f"/groupsettings - نمایش همه تنظیمات\n\n"
        
        f"🙈 <b>مخفی کردن اعضا:</b>\n"
        f"/hide - مخفی کردن لیست اعضا (فقط ادمین‌ها ببینن)\n"
        f"/show - نمایش لیست اعضا (همه ببینن)\n\n"
        f"📊 <b>اطلاعات:</b>\n"
        f"/botstatus - وضعیت ربات در گروه\n"
        f"/commands - نمایش این لیست\n"
        f"/help - راهنما\n\n"
        
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💡 <b>نکته:</b> همه دستورات فقط برای ادمین‌ها قابل استفاده است"
    )
    
    await m.reply_text(commands_text, disable_web_page_preview=True)

# ═══════════════════════════════════════════════════════
# END ADDITIONAL GROUP MANAGEMENT COMMANDS
# ═══════════════════════════════════════════════════════

@app.on_message(filters.command("groupsettings") & filters.group)
async def show_group_settings(c, m):
    """Show current group settings"""
    try:
        member = await c.get_chat_member(m.chat.id, m.from_user.id)
        if member.status not in ["administrator", "creator"]:
            await m.reply_text("❌ فقط ادمین‌ها می‌تونن این دستور رو اجرا کنن!")
            return
    except:
        return
    
    settings_text = (
        f"⚙️ <b>تنظیمات گروه</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👋 خوش‌آمدگویی: {'✅ فعال' if GROUP_SETTINGS['welcome_enabled'] else '❌ غیرفعال'}\n"
        f"🗑️ پاک کردن پیام عضویت: {'✅ فعال' if GROUP_SETTINGS['delete_join_messages'] else '❌ غیرفعال'}\n"
        f"🗑️ پاک کردن پیام خروج: {'✅ فعال' if GROUP_SETTINGS['delete_leave_messages'] else '❌ غیرفعال'}\n"
        f"🔗 فیلتر لینک: {'✅ فعال' if GROUP_SETTINGS['anti_link'] else '❌ غیرفعال'}\n"
        f"🛡️ ضد اسپم: {'✅ فعال' if GROUP_SETTINGS['anti_spam'] else '❌ غیرفعال'}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"<b>دستورات:</b>\n"
        f"/welcome - روشن/خاموش کردن خوش‌آمدگویی\n"
        f"/deletejoins - پاک کردن پیام عضویت\n"
        f"/deleteleaves - پاک کردن پیام خروج\n"
        f"/antilink - فیلتر لینک\n"
        f"/antispam - ضد اسپم"
    )
    
    await m.reply_text(settings_text, disable_web_page_preview=True)

# ═══════════════════════════════════════════════════════
# END GROUP MANAGEMENT SYSTEM
# ═══════════════════════════════════════════════════════

@app.on_message(filters.command(["botstatus", "ping"]) & filters.group)
async def group_botstatus_cmd(c, m):
    """Check bot status in group"""
    me = await c.get_me()
    bot_info = f"🤖 {me.first_name} (@{me.username})\nID: {me.id}"
    
    try:
        member = await c.get_chat_member(m.chat.id, me.id)
        status = member.status
        bot_info += f"\n\n📊 وضعیت من توی این گروه: <b>{status}</b>"
        if status == "administrator":
            bot_info += "\n✅ ادمین هستم!"
        elif status == "member":
            bot_info += "\n❌ ادمین نیستم! لطفاً ادمینم کن."
    except Exception as e:
        bot_info += f"\n\n❌ خطا: {e}"
    
    await m.reply_text(bot_info)

@app.on_message(filters.command("settings") & filters.group)
async def group_settings_cmd(c, m):
    text = """⚙️ <b>تنظیمات گروه</b>
━━━━━━━━━━━━━━
👋 خوشامد: ✅
🔗 ضد لینک: ✅
🔄 ضد فوروارد: ✅
🌊 ضد فلود: ✅
🤬 ضد فحش: ✅
⚠️ حد هشدار: 3
━━━━━━━━━━━━━━
/toggle welcome | anti_link | anti_fwd | anti_flood | anti_profanity"""
    await m.reply_text(text)

@app.on_message(filters.command("start") & filters.private & filters.user(ADMIN_ID))
async def start_cmd(c, m):
    global bg_started, bg_scraper_started
    if defender and not bg_started:
        asyncio.create_task(defender.bg_scan())
        bg_started = True
    # Start the background member scraper (NOT the old crypto hunter)
    if not bg_scraper_started:
        bg_scraper_start(app, ADMIN_ID)
        bg_scraper_started = True
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
        import traceback as _tb
        _log_err(e, "callback handler")
        print(_tb.format_exc(), flush=True)
        # MESSAGE_NOT_MODIFIED یعنی پیام قبلاً آپدیت شده - بی‌ضرره، skip
        if 'MESSAGE_NOT_MODIFIED' in str(e).upper():
            return
        try:
            await q.answer(f"خطا: {type(e).__name__}", show_alert=True)
        except: pass
        atk_state.clear()

async def _cb_impl(c, q):
    global CURRENT_GROUP_ID, defender, bg_started, config
    d = q.data

    # ==================== خانه و منوهای دسته‌بندی ====================
    if d == "noop":
        await q.answer(cache_time=3)
        return

    # ==================== 🆕 Bulk scan + Dedup ====================
    if d == "bulk_scan_groups":
        await _start_bulk_scan(q, "groups")
        return

    if d == "bulk_scan_channels":
        await _start_bulk_scan(q, "channels")
        return

    if d == "dedup_users":
        await _handle_dedup(q)
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
            "🔗 <b>لینک پیج</b> یا <b>نام کاربری</b> رو بفرست:\n\n"
            "✅ مثال URL:\n<code>https://www.instagram.com/arjixgameplay/</code>\n\n"
            "✅ مثال username:\n<code>arjixgameplay</code>\n\n"
            "⚠️ فقط پیج‌های <b>عمومی</b>",
            reply_markup=InlineKeyboardMarkup([[_sub_back_btn(target="ig_menu")[0]]]))
        return

    if d == "categories_menu":
        await _show_categories_menu(q)
        return

    if d.startswith("par_dir_add_tgt_"):
        gid = int(d.split("_")[4])
        atk_state["par_target_gid"] = gid
        # Get target name
        try:
            phone0 = atk_state["par_add_available"][0][0]
            accs = load_accounts()
            fp = accs.get(phone0, {}).get("device_fp") or random.choice(DEVICE_FP)
            from attacker import safe_phone_filename as spfn
            tmp = AdvancedScraper(os.path.join(SESSIONS_DIR, f"acc_{spfn(phone0)}"), API_ID, API_HASH, device_fp=fp)
            await robust_connect(tmp)
            tgt = await tmp.app.get_chat(gid)
            atk_state["par_target_name"] = tgt.title
            try: await tmp.disconnect()
            except: pass
        except: atk_state["par_target_name"] = f"Chat {gid}"
        
        total_db = _db_count_users()
        available = atk_state["par_add_available"]
        total_cap = sum(c for _,c in available)
        actual = min(total_cap, total_db)
        
        await q.message.edit_text(
            f"⚡ <b>ادد موازی</b> — {atk_state['par_target_name']}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📱 {len(available)} اکانت · 📦 {total_cap} ظرفیت\n"
            f"🗄️ {total_db:,} کاربر در دیتابیس\n"
            f"🎯 حداکثر {actual} نفر ادد میشن\n"
            f"━━━━━━━━━━━━━━━━━━\n<b>منبع کاربران:</b>",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(f"🌐 همه ({actual:,})", callback_data=f"par_dir_add_src_all")],
                [InlineKeyboardButton("📂 دسته‌بندی", callback_data=f"par_dir_add_src_cat")],
                [InlineKeyboardButton("👥 چت خاص", callback_data=f"par_dir_add_src_chat")],
                [_sub_back_btn(target="home")[0]],
            ]), disable_web_page_preview=True)
        return

    if d == "par_dir_add_src_all":
        atk_state["par_add_source"] = "all"
        atk_state["par_add_source_id"] = None
        await _start_parallel_direct_add(q)
        return

    if d == "par_dir_add_src_cat":
        cats = get_all_categories()
        buttons = []
        for c in cats[:15]:
            cnt = count_users_by_source(category=c)
            if cnt > 0:
                buttons.append([InlineKeyboardButton(f"📁 {c} ({cnt:,})", callback_data=f"par_dir_add_go_cat_{c}")])
        buttons.append(_sub_back_btn())
        await q.message.edit_text("📂 انتخاب دسته:", reply_markup=InlineKeyboardMarkup(buttons))
        return

    if d == "par_dir_add_src_chat":
        chats = get_scanned_chats()
        buttons = []
        for ch in chats[:15]:
            cnt = count_users_by_source(source_chat_id=ch["chat_id"])
            if cnt > 0:
                buttons.append([InlineKeyboardButton(f"{_chat_type_icon(ch.get('chat_type',''))} {ch['chat_name'][:25]} ({cnt:,})", callback_data=f"par_dir_add_go_src_{ch['chat_id']}")])
        buttons.append(_sub_back_btn())
        await q.message.edit_text("👥 انتخاب چت:", reply_markup=InlineKeyboardMarkup(buttons))
        return

    if d.startswith("par_dir_add_go_cat_"):
        cat = d[18:]
        atk_state["par_add_source"] = "category"
        atk_state["par_add_source_id"] = cat
        await _start_parallel_direct_add(q)
        return

    if d.startswith("par_dir_add_go_src_"):
        src_id = int(d[19:])
        atk_state["par_add_source"] = "chat"
        atk_state["par_add_source_id"] = src_id
        await _start_parallel_direct_add(q)
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
        # Make sure we have a source group
        if not atk_state.get("live_source_gid"):
            # Redirect to source picker
            q.data = f"live_add_pick_src_{gid}"
            await _cb_impl(c, q)
            return
        asyncio.create_task(_execute_direct_add(q, gid))
        return

    # ═══════════ LIVE ADD: Pick source group ═══════════
    if d.startswith("live_add_pick_src_"):
        gid = int(d.split("_")[4])
        accs = list_saved_accounts()
        phone = atk_state.get("phone", list(accs.keys())[0] if accs else None)
        if not phone or phone not in accs:
            await q.answer("اکانت مشخص نیست!", show_alert=True)
            return
        fp = accs[phone].get("device_fp") or random.choice(DEVICE_FP)
        from attacker import safe_phone_filename as spfn
        sess_path = os.path.join(SESSIONS_DIR, f"acc_{spfn(phone)}")
        
        prog = await q.message.edit_text(" در حال بارگذاری گروه‌ها...")
        try:
            client = AdvancedScraper(sess_path, API_ID, API_HASH, phone=phone, device_fp=fp)
            _enable_wal_on_session(client.app.name)
            await client.connect()
            _enable_wal_on_session(client.app.name)
            
            groups = []
            async for dialog in client.app.get_dialogs(limit=500):
                if "group" in str(dialog.chat.type).lower():
                    cnt = getattr(dialog.chat, "members_count", 0) or 0
                    groups.append((dialog.chat.title, dialog.chat.id, cnt))
            
            atk_state["_live_client"] = client
            atk_state["_live_phone"] = phone
            
            text = f"📂 <b>گروه منبع را انتخاب کن</b>\n"
            text += f"کاربران این گروه الان اسکرپ و ادد میشن!\n\n"
            buttons = []
            for gname, gid2, gcnt in sorted(groups, key=lambda x:-x[2])[:25]:
                buttons.append([InlineKeyboardButton(f"👥 {gname[:28]} ({gcnt:,})", callback_data=f"live_add_src_{gid}_{gid2}")])
            buttons.append([InlineKeyboardButton(" بازگشت", callback_data=f"add_target_{gid}")])
            
            await prog.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
        except Exception as e:
            await prog.edit_text(f"❌ خطا: {e}", reply_markup=InlineKeyboardMarkup([[_sub_back_btn(target="home")[0]]]))
        return

    # ═══════════ LIVE ADD: Source selected, start adding ═══════════
    if d.startswith("live_add_src_"):
        parts = d.split("_")
        target_gid = int(parts[3])
        source_gid = int(parts[4])
        
        client = atk_state.get("_live_client")
        phone = atk_state.get("_live_phone")
        
        if not client or not phone:
            await q.answer("خطا در وضعیت!", show_alert=True)
            return
        
        # Store source and use existing add_client
        atk_state["live_source_gid"] = source_gid
        atk_state["add_client"] = client
        atk_state["phone"] = phone
        
        # Get source name
        try:
            src = await client.app.get_chat(source_gid)
            source_name = src.title
        except:
            source_name = "گروه منبع"
        
        try:
            tgt = await client.app.get_chat(target_gid)
            target_name = tgt.title
        except:
            target_name = "کانال مقصد"
        
        await q.message.edit_text(
            f"🔄 <b>آماده اسکرپ + ادد!</b>\n"
            f"━━━━━━━━━━━━━━━\n"
            f" منبع: {source_name}\n"
            f"🎯 مقصد: {target_name}\n"
            f" اکانت: {phone}\n"
            f"━━━━━━━━━━━━━━━\n"
            f"الان اعضای گروه منبع اسکرپ میشن\n"
            f"و به کانال مقصد اضافه میشن!\n\n"
            f"آماده‌ای؟",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("▶️ شروع!", callback_data=f"dir_add_go_{target_gid}")],
                [InlineKeyboardButton("🔙 گروه دیگه", callback_data=f"live_add_pick_src_{target_gid}")],
            ]))
        return



    if d == "par_dir_add_exec":
        asyncio.create_task(_execute_parallel_direct_add(q))
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
        # Disconnect simple add client
        simp_client = atk_state.get("_simp_client")
        if simp_client:
            try:
                await simp_client.disconnect()
            except: pass
        atk_state.clear()
        # Cleanup session locks
        import glob as _g
        for pat in [os.path.join(SESSIONS_DIR, "*.session-journal"), os.path.join(SESSIONS_DIR, "*.session-wal"), os.path.join(SESSIONS_DIR, "*.session-shm")]:
            for f in _g.glob(pat):
                try: os.remove(f)
                except: pass
        await q.answer("️ درخواست توقف داده شد، چند لحظه...", show_alert=True)
        await q.message.edit_text("⏹️ عملیات توسط کاربر متوقف شد.", reply_markup=main_menu())
        return


    # ═══════════════ 🧪 DEBUG: Test add 1 user ═══════════════
    if d == "debug_add_test":
        # Use list_saved_accounts which restores sessions from DB
        accs = list_saved_accounts()
        if not accs:
            await q.answer("❌ اکانتی نداری!", show_alert=True)
            return
        await q.answer()
        phone = list(accs.keys())[0]
        fp = accs[phone].get("device_fp") or random.choice(DEVICE_FP)
        from attacker import safe_phone_filename as spfn
        sess_path = os.path.join(SESSIONS_DIR, f"acc_{spfn(phone)}")
        
        # Clean up stale WAL/journal files
        import glob as _g
        for pat in [sess_path + ".session-journal", sess_path + ".session-wal", sess_path + ".session-shm",
                     sess_path + ".session-*"]:
            for f in _g.glob(pat):
                try: os.remove(f)
                except: pass
        
        test_client = AdvancedScraper(sess_path, API_ID, API_HASH, phone=phone, device_fp=fp)
        
        prog = await q.message.edit_text("🧪 <b>تست تشخیصی ادد</b>\n⏳ در حال اتصال...")
        
        async def run_test():
            from pyrogram.raw.functions.contacts import AddContact
            from pyrogram.raw.functions.channels import InviteToChannel
            from pyrogram.raw.types import InputPeerUser, InputUser
            
            log = ""
            try:
                # Clean and enable WAL before connect
                _enable_wal_on_session(test_client.app.name)
                await test_client.connect()
                _enable_wal_on_session(test_client.app.name)
                me = await test_client.app.get_me()
                log += f"✅ متصل: {me.first_name} (ID: {me.id})\n\n"
                
                # List all groups/channels
                log += "📡 <b>گروه‌ها و کانال‌های اکانت:</b>\n"
                groups = []
                channels = []
                async for dialog in test_client.app.get_dialogs(limit=200):
                    cht = dialog.chat
                    if "group" in str(cht.type).lower():
                        groups.append((cht.title, cht.id))
                        log += f"  👥 {cht.title} ({cht.id})\n"
                    elif cht.type == "channel":
                        channels.append((cht.title, cht.id))
                        log += f"  📡 {cht.title} ({cht.id})\n"
                
                log += f"\n📊 {len(groups)} گروه + {len(channels)} کانال\n\n"
                
                # Pick first channel as target
                if not channels:
                    log += "❌ هیچ کانالی پیدا نشد!"
                    await prog.edit_text(log, reply_markup=InlineKeyboardMarkup([[_sub_back_btn(target="home")[0]]]), disable_web_page_preview=True)
                    return
                
                target_title, target_id = channels[0]
                log += f"🎯 هدف تست: <b>{target_title}</b> ({target_id})\n\n"
                
                # Check admin
                try:
                    member = await test_client.app.get_chat_member(target_id, "me")
                    log += f"👑 وضعیت ادمین: <b>{member.status}</b>\n"
                    if hasattr(member, 'privileges') and member.privileges:
                        log += f"   invite_users: {member.privileges.invite_users}\n"
                        log += f"   other: {member.privileges}\n"
                except Exception as e:
                    log += f"❌ Admin check: {type(e).__name__}: {e}\n"
                
                # Get 1 user from DB
                users = get_users_by_source(limit=3)
                if not users:
                    log += "\n❌ کاربری توی دیتابیس نیست!"
                    await prog.edit_text(log, reply_markup=InlineKeyboardMarkup([[_sub_back_btn(target="home")[0]]]), disable_web_page_preview=True)
                    return
                
                test_uid = int(users[0].get("user_id", 0))
                log += f"\n🧪 تست با کاربر: <code>{test_uid}</code>\n"
                log += f"   نام: {users[0].get('first_name','')} {users[0].get('last_name','')}\n"
                log += f"   source: {users[0].get('source_group_id')}\n\n"
                
                # Step 1: resolve_peer
                log += "<b>Step 1: resolve_peer</b>\n"
                try:
                    peer = await test_client.app.resolve_peer(test_uid)
                    log += f"  ✅ peer type: {type(peer).__name__}\n"
                    log += f"  ✅ peer: {peer}\n\n"
                except Exception as e:
                    log += f"  ❌ {type(e).__name__}: {e}\n"
                    log += f"  → Trying InputPeerUser(access_hash=0)...\n"
                    peer = InputPeerUser(user_id=test_uid, access_hash=0)
                    log += f"  ✅ Built: {peer}\n\n"
                
                # Step 2: AddContact
                log += "<b>Step 2: AddContact</b>\n"
                try:
                    result = await test_client.app.invoke(
                        AddContact(id=peer, first_name=str(test_uid)[:30], last_name="", phone="", add_phone_privacy_exception=False)
                    )
                    log += f"  ✅ OK: {type(result).__name__}\n\n"
                except Exception as e:
                    log += f"  ❌ {type(e).__name__}: {e}\n\n"
                
                # Step 3: Resolve target
                log += "<b>Step 3: resolve target channel</b>\n"
                try:
                    target_peer = await test_client.app.resolve_peer(target_id)
                    log += f"  ✅ target peer: {type(target_peer).__name__}\n\n"
                except Exception as e:
                    log += f"  ❌ {type(e).__name__}: {e}\n\n"
                    await prog.edit_text(log, reply_markup=InlineKeyboardMarkup([[_sub_back_btn(target="home")[0]]]), disable_web_page_preview=True)
                    return
                
                # Step 4: InviteToChannel
                log += "<b>Step 4: InviteToChannel</b>\n"
                try:
                    result = await test_client.app.invoke(
                        InviteToChannel(channel=target_peer, users=[peer])
                    )
                    log += f"  ✅ SUCCESS! {type(result).__name__}\n"
                    log += f"  Result: {result}\n\n"
                except Exception as e:
                    log += f"  ❌ {type(e).__name__}: {e}\n"
                    log += f"  Code: {getattr(e, 'code', '?')}\n"
                    log += f"  Name: {getattr(e, 'NAME', '?')}\n\n"
                    
                    # Try with InputUser
                    log += "<b>Step 4b: Try InputUser(access_hash=0)</b>\n"
                    try:
                        user_input = InputUser(user_id=test_uid, access_hash=0)
                        result = await test_client.app.invoke(
                            InviteToChannel(channel=target_peer, users=[user_input])
                        )
                        log += f"  ✅ SUCCESS with InputUser!\n\n"
                    except Exception as e2:
                        log += f"  ❌ {type(e2).__name__}: {e2}\n\n"
                
                # Step 5: Verify
                log += "<b>Step 5: Check channel members count</b>\n"
                try:
                    chat = await test_client.app.get_chat(target_id)
                    log += f"  Members: {chat.members_count}\n"
                except Exception as e:
                    log += f"  ❌ {e}\n"
                
                await test_client.disconnect()
                
            except Exception as e:
                log += f"\n💥 FATAL: {type(e).__name__}: {e}\n"
                import traceback
                log += f"```{traceback.format_exc()[:500]}```"
            
            await prog.edit_text(log, reply_markup=InlineKeyboardMarkup([[_sub_back_btn(target="home")[0]]]), disable_web_page_preview=True, parse_mode="HTML")
        
        import asyncio as _asyncio
        _asyncio.create_task(run_test())
        return


    # ═══════════════ ⚡ QUICK ADD TO GROUP ═══════════════
    if d == "quick_add_start":
        accs = list_saved_accounts()
        if not accs:
            await q.answer(" اول یه اکانت اضافه کن!", show_alert=True)
            return
        atk_state["quick_step"] = "pick_account"
        buttons = []
        for phone, info in accs.items():
            name = info.get("name", phone)[:20]
            buttons.append([InlineKeyboardButton(f" {name} ({phone})", callback_data=f"quick_acc_{phone}")])
        await q.message.edit_text("📱 <b>اکانت اددکننده رو انتخاب کن:</b>", 
            reply_markup=InlineKeyboardMarkup(buttons))
        return

    if d.startswith("quick_acc_"):
        phone = d[len("quick_acc_"):]
        accs = list_saved_accounts()
        fp = accs[phone].get("device_fp") or random.choice(DEVICE_FP)
        from attacker import safe_phone_filename as spfn
        sess_path = os.path.join(SESSIONS_DIR, f"acc_{spfn(phone)}")
        atk_state["quick_phone"] = phone
        atk_state["quick_fp"] = fp
        atk_state["quick_sess"] = sess_path
        prog = await q.message.edit_text(" در حال اتصال...")
        try:
            client = AdvancedScraper(sess_path, API_ID, API_HASH, phone=phone, device_fp=fp)
            _enable_wal_on_session(client.app.name)
            await client.connect()
            _enable_wal_on_session(client.app.name)
            me = await client.app.get_me()
            # Load groups
            groups = []
            async for dialog in client.app.get_dialogs(limit=500):
                if "group" in str(dialog.chat.type).lower():
                    cnt = getattr(dialog.chat, "members_count", 0) or 0
                    groups.append((dialog.chat.title, dialog.chat.id, cnt))
            atk_state["quick_client"] = client
            text = f"✅ متصل: <b>{me.first_name}</b>\n\n👥 <b>گروه مقصد:</b>\n"
            buttons = []
            for gname, gid, gcnt in sorted(groups, key=lambda x:-x[2])[:20]:
                buttons.append([InlineKeyboardButton(f"👥 {gname[:30]} ({gcnt:,})", callback_data=f"quick_grp_{gid}")])
            buttons.append([InlineKeyboardButton("✍️ آیدی دستی", callback_data="quick_grp_manual")])
            buttons.append([InlineKeyboardButton("🔙 بازگشت", callback_data="quick_add_start")])
            await prog.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
        except Exception as e:
            await prog.edit_text(f"❌ خطا: {e}", reply_markup=InlineKeyboardMarkup([[_sub_back_btn(target="home")[0]]]))
        return

    if d.startswith("quick_grp_") and d != "quick_grp_manual":
        gid = int(d[len("quick_grp_"):])
        client = atk_state.get("quick_client")
        phone = atk_state["quick_phone"]
        try:
            chat = await client.app.get_chat(gid)
            atk_state["quick_gid"] = gid
            atk_state["quick_gname"] = chat.title
            # Check membership
            try:
                me = await client.app.get_chat_member(gid, "me")
                if me.status not in ["administrator", "creator", "member"]:
                    await q.message.edit_text("❌ اکانت عضو این گروه نیست!", 
                        reply_markup=InlineKeyboardMarkup([[_sub_back_btn(target="quick_add_start")[0]]]))
                    return
            except: pass
            await q.message.edit_text(
                f"🎯 مقصد: <b>{chat.title}</b>\n\n <b>منبع کاربران:</b>",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🌐 همه کاربران DB", callback_data="quick_src_all")],
                    [InlineKeyboardButton("📄 آپلود CSV", callback_data="quick_src_csv")],
                    [InlineKeyboardButton("🔙 بازگشت", callback_data="quick_acc_" + phone)],
                ]))
        except Exception as e:
            await q.message.edit_text(f"❌ {e}", reply_markup=InlineKeyboardMarkup([[_sub_back_btn(target="quick_add_start")[0]]]))
        return

    if d == "quick_grp_manual":
        atk_state["quick_step"] = "manual_gid"
        await q.message.edit_text("✍️ آیدی عددی گروه (با -100 شروع میشه):")
        return

    if d == "quick_src_all":
        gid = atk_state["quick_gid"]
        gname = atk_state["quick_gname"]
        phone = atk_state["quick_phone"]
        client = atk_state["quick_client"]
        # Get users from DB
        uid_list = []
        try:
            cur = db.get_conn().cursor()
            cur.execute("SELECT user_id FROM scraped_users WHERE user_id > 10000 AND user_id < 100000000000 LIMIT 200")
            for row in cur.fetchall():
                uid_list.append(int(row[0]))
            cur.close()
        except: pass
        if not uid_list:
            await q.message.edit_text(" کاربری توی دیتابیس نیست!", 
                reply_markup=InlineKeyboardMarkup([[_sub_back_btn(target="home")[0]]]))
            return
        random.shuffle(uid_list)
        await q.message.edit_text(f"⚡ شروع ادد {len(uid_list)} نفر به <b>{gname}</b>...\n⏳ صبر کن...")
        asyncio.create_task(_do_quick_add(q, gid, gname, uid_list, client, phone))
        return

    if d == "quick_src_csv":
        atk_state["quick_step"] = "csv_upload"
        await q.message.edit_text(" فایل CSV رو بفرست\n(ستون user_id لازم)")
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
             InlineKeyboardButton("🧹 حذف تکراری‌ها", callback_data="dedup_users")],
            [InlineKeyboardButton("🗑️ پاک کردن لیست ممبر", callback_data="clear_users"),
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

    if d == "ig_retry_login":
        await q.answer("🔄 در حال تلاش مجدد لاگین...", show_alert=False)
        try:
            if ig_scraper.login_instagram():
                await q.answer("✅ لاگین موفق! حالا می‌تونی اسکرپ کنی.", show_alert=True)
            else:
                await q.answer("❌ لاگین ناموفق - پسورد اشتباه یا چالش امنیتی.", show_alert=True)
        except Exception as e:
            await q.answer(f"❌ خطا: {str(e)[:100]}", show_alert=True)
        await _show_ig_menu(q)
        return

    if d == "ig_logout":
        # Delete session file
        try:
            sf = ig_scraper.IG_SESSION_FILE
            if os.path.exists(sf):
                os.remove(sf)
            # Also try in saved_sessions dir
            sf2 = os.path.join("saved_sessions", "instagram_session")
            if os.path.exists(sf2):
                os.remove(sf2)
        except:
            pass
        atk_state["ig_username"] = ""
        atk_state["ig_password"] = ""
        await q.answer("📸 از اکانت خارج شدی. فایل سشن پاک شد.", show_alert=True)
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

    # ═══ 🤖 AI Callbacks ═══
    if d == "ai_menu":
        await _show_ai_menu(q)
        return

    if d == "ai_batch_analyze":
        await _handle_ai_batch_analyze(q)
        return

    if d == "ai_stats":
        chats = get_scanned_chats()
        cats = get_all_categories()
        text = "📊 <b>آمار تحلیل هوشمند</b>\n━━━━━━━━━━━━━━━━━━\n"
        text += f"🗂️ کل چت‌ها: {len(chats)}\n🏷️ دسته‌بندی‌ها: {len(cats)}\n\n"
        if cats:
            for c in cats[:10]:
                cnt = len([x for x in chats if x.get('category') == c])
                text += f"📁 {c}: {cnt} چت\n"
        await q.message.edit_text(text, reply_markup=InlineKeyboardMarkup([[_sub_back_btn(target="ai_menu")]]), disable_web_page_preview=True)
        return

    # ═══ 🔍 Group Finder Callbacks ═══
    if d == "group_finder_menu":
        atk_state.clear()
        atk_state["step"] = "gf_query"
        await q.message.edit_text(
            "🔍 <b>گروه‌یاب تلگرام</b>\n\nموضوع گروهی که می‌خوای رو تایپ کن:\n\n"
            "✅ <b>مثال‌ها:</b>\n"
            "• <code>کریپتو</code>\n• <code>گیمینگ</code>\n"
            "• <code>برنامه‌نویسی پایتون</code>\n• <code>فروشگاه لوازم آرایشی</code>\n\n"
            "🔍 هم تلگرام هم وب جستجو میشه\n🤖 AI گروه‌ها رو رتبه‌بندی میکنه",
            reply_markup=InlineKeyboardMarkup([[_sub_back_btn()]]))
        return

    if d.startswith("gf_scan_"):
        target = d[8:]
        atk = atk_state.get("atk")
        if not atk:
            await q.answer("❌ اول یه اکانت از منوی حمله انتخاب کن!", show_alert=True)
            return
        await q.answer(f"🚀 شروع اسکن @{target}...", show_alert=False)
        async def _gf_run():
            try:
                target_chat = await robust_resolve_chat(atk, f"@{target}")
                prog = q.message
                stop_btn = InlineKeyboardMarkup([[InlineKeyboardButton("⏹️ توقف", callback_data="stop_op")]])
                async def _p(text):
                    try: await prog.edit_text(text, reply_markup=stop_btn, disable_web_page_preview=True)
                    except: pass
                async def _s(ul):
                    try: save_scraped(ul, target_chat.title, target_chat.id)
                    except: pass
                users = await atk.run_full_scrape(target_chat.id, progress_cb=_p, incremental_save_cb=_s)
                save_scraped(users, target_chat.title, target_chat.id)
                await prog.edit_text(f"✅ اسکن @{target} تمام شد!\n👥 {len(users):,} کاربر", reply_markup=main_menu())
                try: await atk.disconnect()
                except: pass
            except Exception as e:
                await q.message.edit_text(f"❌ خطا: {str(e)[:300]}", reply_markup=main_menu())
        asyncio.create_task(_gf_run())
        return

    if d == "select_group":
        groups = []
        async for dialog in app.get_dialogs():
            if "group" in str(dialog.chat.type).lower() or ("channel" in str(dialog.chat.type).lower() and getattr(dialog.chat, 'megagroup', False)):
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
        nav_buttons.append([InlineKeyboardButton("📊 تفکیک مخاطبین", callback_data="user_breakdown"),
                            InlineKeyboardButton("📥 دانلود CSV", callback_data="download_csv")])
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

    # ==================== 📊 تفکیک مخاطبین ====================
    if d == "user_breakdown":
        try:
            cur = db.get_conn().cursor()
            
            # Total
            cur.execute("SELECT COUNT(*) FROM scraped_users")
            total = cur.fetchone()[0]
            
            # With phone
            cur.execute("SELECT COUNT(*) FROM scraped_users WHERE phone IS NOT NULL AND phone != ''")
            with_phone = cur.fetchone()[0]
            
            # With username (no phone)
            cur.execute("""
                SELECT COUNT(*) FROM scraped_users 
                WHERE username IS NOT NULL AND username != '' 
                AND (phone IS NULL OR phone = '')
            """)
            username_only = cur.fetchone()[0]
            
            # With both phone and username
            cur.execute("""
                SELECT COUNT(*) FROM scraped_users 
                WHERE phone IS NOT NULL AND phone != '' 
                AND username IS NOT NULL AND username != ''
            """)
            both = cur.fetchone()[0]
            
            # ID only (no phone, no username)
            cur.execute("""
                SELECT COUNT(*) FROM scraped_users 
                WHERE (phone IS NULL OR phone = '') 
                AND (username IS NULL OR username = '')
            """)
            id_only = cur.fetchone()[0]
            
            # Already added
            cur.execute("SELECT COUNT(DISTINCT user_id) FROM added_history_tbl")
            already_added = cur.fetchone()[0]
            
            cur.close()
        except Exception as e:
            await q.answer(f"خطا: {str(e)[:100]}", show_alert=True)
            return
        
        text = f"📊 <b>تفکیک مخاطبین</b>\n"
        text += f"━━━━━━━━━━━━━━━━━━\n\n"
        
        text += f"👥 <b>مجموع:</b> {total:,} نفر\n"
        text += f"✅ <b>ادد شده:</b> {already_added:,} نفر\n"
        text += f"⏳ <b>باقیمانده:</b> {total - already_added:,} نفر\n\n"
        
        text += f"━━━━━━━━━━━━━━━━━━\n"
        text += f"📊 <b>تفکیک بر اساس نوع:</b>\n\n"
        
        # Phone users
        phone_total = with_phone
        phone_pct = phone_total * 100 // max(1, total)
        phone_bar = "🟩" * (phone_pct // 10) + "⬜" * (10 - phone_pct // 10)
        text += f"📱 <b>با شماره تلفن:</b> {phone_total:,} ({phone_pct}%)\n"
        text += f"   {phone_bar}\n"
        text += f"   └ نرخ موفقیت اد: ~70% ≈ {int(phone_total * 0.7):,} نفر\n\n"
        
        # Username only
        uname_pct = username_only * 100 // max(1, total)
        uname_bar = "🟩" * (uname_pct // 10) + "⬜" * (10 - uname_pct // 10)
        text += f"🏷️ <b>فقط username (بدون شماره):</b> {username_only:,} ({uname_pct}%)\n"
        text += f"   {uname_bar}\n"
        text += f"   └ نرخ موفقیت اد: ~40% ≈ {int(username_only * 0.4):,} نفر\n\n"
        
        # Both
        text += f"⭐ <b>هم شماره هم username:</b> {both:,}\n\n"
        
        # ID only
        id_pct = id_only * 100 // max(1, total)
        id_bar = "🟩" * (id_pct // 10) + "⬜" * (10 - id_pct // 10)
        text += f"🆔 <b>فقط آیدی عددی:</b> {id_only:,} ({id_pct}%)\n"
        text += f"   {id_bar}\n"
        text += f"   └ نرخ موفقیت اد: ~15% ≈ {int(id_only * 0.15):,} نفر\n\n"
        
        # Summary
        text += f"━━━━━━━━━━━━━━━━━━\n"
        est_total = int(phone_total * 0.7) + int(username_only * 0.4) + int(id_only * 0.15)
        text += f"🎯 <b>مجموع قابل اد (تخمین):</b> ~{est_total:,} نفر\n"
        
        # Buttons for adding by type
        buttons = []
        buttons.append([
            InlineKeyboardButton(f"📱 اد شماره‌دارها ({phone_total:,})", callback_data="add_by_type_phone"),
        ])
        buttons.append([
            InlineKeyboardButton(f"🏷️ اد username دارها ({username_only:,})", callback_data="add_by_type_username"),
        ])
        buttons.append([
            InlineKeyboardButton(f"🆔 اد ID-only ها ({id_only:,})", callback_data="add_by_type_id"),
        ])
        buttons.append([
            InlineKeyboardButton("🌐 اد همه", callback_data="add_by_type_all"),
        ])
        buttons.append([
            InlineKeyboardButton("👥 لیست مخاطبین", callback_data="show_list_0"),
            InlineKeyboardButton("🏠 خانه", callback_data="home"),
        ])
        
        await q.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons), disable_web_page_preview=True)
        return

    # ==================== ➕ اد بر اساس نوع کاربر ====================
    if d.startswith("add_by_type_"):
        add_type = d[len("add_by_type_"):]
        atk_state["add_member_type"] = add_type
        
        try:
            cur = db.get_conn().cursor()
            if add_type == "phone":
                cur.execute("SELECT COUNT(*) FROM scraped_users WHERE phone IS NOT NULL AND phone != ''")
                count = cur.fetchone()[0]
                label = "📱 شماره‌دارها"
            elif add_type == "username":
                cur.execute("""SELECT COUNT(*) FROM scraped_users 
                    WHERE username IS NOT NULL AND username != '' AND (phone IS NULL OR phone = '')""")
                count = cur.fetchone()[0]
                label = "🏷️ username دارها"
            elif add_type == "id":
                cur.execute("""SELECT COUNT(*) FROM scraped_users 
                    WHERE (phone IS NULL OR phone = '') AND (username IS NULL OR username = '')""")
                count = cur.fetchone()[0]
                label = "🆔 فقط ID"
            else:
                cur.execute("SELECT COUNT(*) FROM scraped_users")
                count = cur.fetchone()[0]
                label = "🌐 همه"
            cur.close()
        except:
            count = 0
            label = "کاربران"
        
        accs = list_saved_accounts()
        if not accs:
            await q.answer("اول اکانت اضافه کن!", show_alert=True)
            return
        
        text = f"➕ <b>اد {label}</b>\n"
        text += f"━━━━━━━━━━━━━━━━━━\n"
        text += f"👥 {count:,} نفر آماده\n\n"
        text += f"اکانت اد‌زننده رو انتخاب کن:"
        
        buttons = []
        for phone, info in accs.items():
            name = info.get("name", phone)[:20]
            limits = load_adder_limits()
            added = limits.get(phone, {}).get("added", 0)
            remaining = MAX_ADD_PER_ACCOUNT - added
            status = f"({remaining} ظرفیت)" if remaining > 0 else "⚠️ پر"
            buttons.append([InlineKeyboardButton(f"📱 {name} {status}", callback_data=f"type_add_acc_{phone}")])
        buttons.append([InlineKeyboardButton("🔙 بازگشت", callback_data="user_breakdown")])
        
        await q.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
        return

    # ==================== 🔧 اکانت انتخاب شد برای اد نوعی ====================
    if d.startswith("type_add_acc_"):
        phone = d[len("type_add_acc_"):]
        add_type = atk_state.get("add_member_type", "all")
        
        accs = list_saved_accounts()
        if phone not in accs:
            await q.answer("اکانت پیدا نشد!", show_alert=True)
            return
        
        fp = accs[phone].get("device_fp") or random.choice(DEVICE_FP)
        from attacker import safe_phone_filename as spfn
        sess_path = os.path.join(SESSIONS_DIR, f"acc_{spfn(phone)}")
        
        prog = await q.message.edit_text("🔐 در حال اتصال...")
        
        try:
            client = AdvancedScraper(sess_path, API_ID, API_HASH, phone=phone, device_fp=fp)
            _enable_wal_on_session(client.app.name)
            await robust_connect(client, max_retries=3)
            _enable_wal_on_session(client.app.name)
            me = await client.app.get_me()
            
            atk_state["_type_add_client"] = client
            atk_state["_type_add_phone"] = phone
            
            targets = []
            async for dialog in client.app.get_dialogs(limit=500):
                chat_type = str(dialog.chat.type).lower()
                if "channel" in chat_type or "supergroup" in chat_type:
                    cnt = getattr(dialog.chat, "members_count", 0) or 0
                    icon = "📡" if "channel" in chat_type else "👥"
                    targets.append((dialog.chat.title, dialog.chat.id, cnt, icon))
            
            type_labels = {"phone": "📱 شماره‌دارها", "username": "🏷️ username دارها", "id": "🆔 فقط ID", "all": "🌐 همه"}
            
            text = f"✅ متصل: <b>{me.first_name}</b>\n\n"
            text += f"➕ <b>{type_labels.get(add_type, 'همه')}</b>\n"
            text += f"━━━━━━━━━━━━━━━━━━\n"
            text += f"گروه/کانال مقصد رو انتخاب کن:\n"
            
            buttons = []
            for tname, tid, tcnt, icon in sorted(targets, key=lambda x:-x[2])[:20]:
                buttons.append([InlineKeyboardButton(f"{icon} {tname[:28]} ({tcnt:,})", callback_data=f"type_add_tgt_{tid}")])
            
            if not targets:
                text += "\n⚠️ هیچ Supergroup/کانالی پیدا نشد!"
                buttons.append([InlineKeyboardButton("🏠 خانه", callback_data="home")])
            else:
                buttons.append([InlineKeyboardButton("🔙 بازگشت", callback_data="user_breakdown")])
            
            await prog.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
        except Exception as e:
            await prog.edit_text(f"❌ خطا: {str(e)[:200]}", reply_markup=InlineKeyboardMarkup([[_sub_back_btn(target="home")[0]]]))
        return

    # ==================== 🎯 مقصد انتخاب شد - شروع اد ====================
    if d.startswith("type_add_tgt_"):
        target_gid = int(d[len("type_add_tgt_"):])
        client = atk_state.get("_type_add_client")
        phone = atk_state.get("_type_add_phone")
        add_type = atk_state.get("add_member_type", "all")
        
        if not client:
            await q.answer("خطا!", show_alert=True)
            return
        
        try:
            cur = db.get_conn().cursor()
            
            if add_type == "phone":
                cur.execute("SELECT user_id, username, first_name, last_name, phone FROM scraped_users WHERE phone IS NOT NULL AND phone != ''")
            elif add_type == "username":
                cur.execute("""SELECT user_id, username, first_name, last_name, phone FROM scraped_users 
                    WHERE username IS NOT NULL AND username != '' AND (phone IS NULL OR phone = '')""")
            elif add_type == "id":
                cur.execute("""SELECT user_id, username, first_name, last_name, phone FROM scraped_users 
                    WHERE (phone IS NULL OR phone = '') AND (username IS NULL OR username = '')""")
            else:
                cur.execute("SELECT user_id, username, first_name, last_name, phone FROM scraped_users")
            
            rows = cur.fetchall()
            cur.close()
            
            members = [{"user_id": r[0], "username": r[1] or "", "first_name": r[2] or "", "last_name": r[3] or "", "phone": r[4] or ""} for r in rows]
        except Exception as e:
            await q.message.edit_text(f"❌ خطا: {e}", reply_markup=InlineKeyboardMarkup([[_sub_back_btn(target="home")[0]]]))
            return
        
        if not members:
            await q.answer("کاربری پیدا نشد!", show_alert=True)
            return
        
        random.shuffle(members)
        type_labels = {"phone": "📱 شماره‌دارها", "username": "🏷️ username دارها", "id": "🆔 فقط ID", "all": "🌐 همه"}
        
        await q.message.edit_text(f"🚀 شروع اد {type_labels.get(add_type, 'همه')} ({len(members)} نفر)...")
        asyncio.create_task(_execute_simple_add(q, target_gid, client, phone, members, type_labels.get(add_type, "همه")))
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
                [_sub_back_btn(target="home")[0]],
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
        await q.message.edit_text("➕ افزودن اکانت جدید دائمی\n\n📱 شماره تلفن با <b>فرمت بین‌المللی</b> بفرستید:\n\n✅ <b>فرمت‌های قابل قبول:</b>\n• <code>+989123456789</code>\n• <code>09123456789</code>\n• <code>9123456789</code>\n\n⚠️ نکته: درخواست کد زیاد پشت سر هم باعث فلود ۱۸ ساعته تلگرام میشود!\nاگر اکانت از قبل در لیست هست از آن استفاده کنید.",
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
        try:
            accounts = list_saved_accounts() or {}
            text = f"{mode_label}\n\nلطفا اکانت مورد استفاده را انتخاب کنید:"
            buttons = []
            if accounts:
                limits = load_adder_limits() or {}
                for phone, info in accounts.items():
                    name = info.get("name", phone) if isinstance(info, dict) else str(phone)
                    added = limits.get(phone, {}).get("added", 0) if isinstance(limits.get(phone), dict) else 0
                    status = ""
                    if mode_label.startswith("➕") and added >= MAX_ADD_PER_ACCOUNT:
                        status = " ⚠️ پر"
                    buttons.append([InlineKeyboardButton(f"✅ {name} | {phone}{status}", callback_data=f"useacc_{callback}_{phone}")])
            buttons.append([InlineKeyboardButton("➕ افزودن اکانت جدید و استفاده", callback_data=f"newacc_{callback}")])
            buttons.append([InlineKeyboardButton("🔙 بازگشت", callback_data="home")])
            await q.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
        except Exception as e:
            _log_err(e, "show_account_picker")
            await q.answer("خطا در بارگذاری اکانت‌ها", show_alert=True)

    if d == "pick_account_attack":
        await show_account_picker("attack", "home", "🚀 شروع تست حمله پیشرفته")
        return

    if d == "pick_account_add":
        # NEW FLOW: Account → Source Group → Scrape → Target → Add
        accs = list_saved_accounts()
        if not accs:
            await q.answer("اول یه اکانت اضافه کن!", show_alert=True)
            return
        
        atk_state["add_step"] = "pick_source"
        
        # Show accounts to pick
        buttons = []
        for phone, info in accs.items():
            name = info.get("name", phone)[:20]
            buttons.append([InlineKeyboardButton(f" {name} ({phone})", callback_data=f"simp_add_acc_{phone}")])
        buttons.append([InlineKeyboardButton("🔙 بازگشت", callback_data="home")])
        
        await q.message.edit_text(
            " <b>ادد ممبر - مرحله ۱</b>\n"
            "━━━━━━━━━━━━━━━\n"
            "اکانتی که میخوای باهاش ادد بزنی رو انتخاب کن:",
            reply_markup=InlineKeyboardMarkup(buttons))
        return

    # ── SIMPLE ADD FLOW ───
    if d.startswith("simp_add_acc_"):
        phone = d[len("simp_add_acc_"):]
        accs = list_saved_accounts()
        if phone not in accs:
            await q.answer("اکانت پیدا نشد!", show_alert=True)
            return
        fp = accs[phone].get("device_fp") or random.choice(DEVICE_FP)
        from attacker import safe_phone_filename as spfn
        sess_path = os.path.join(SESSIONS_DIR, f"acc_{spfn(phone)}")
        
        # FULL cleanup: delete session + all related files, then re-download from DB
        import glob as _g
        import shutil
        for pat in [sess_path + ".session", sess_path + ".session-journal", 
                    sess_path + ".session-wal", sess_path + ".session-shm",
                    sess_path + ".session-*"]:
            for f in _g.glob(pat):
                try: os.remove(f)
                except: pass
        
        # Re-download session from Neon DB
        blob = db.load_session_blob(phone)
        if blob:
            with open(sess_path + ".session", "wb") as sf:
                sf.write(blob)
            print(f"  Re-downloaded session for {phone} from DB ({len(blob)} bytes)", flush=True)
        else:
            print(f"  WARNING: No session blob in DB for {phone}", flush=True)
        
        prog = await q.message.edit_text(" در حال اتصال...\nلطفاً صبر کنید")
        client = None
        try:
            client = AdvancedScraper(sess_path, API_ID, API_HASH, phone=phone, device_fp=fp)
            # Enable WAL before connect
            _enable_wal_on_session(client.app.name)
            await robust_connect(client, max_retries=3)
            _enable_wal_on_session(client.app.name)
            
            # Warmup dialogs with retry
            for _retry in range(3):
                try:
                    async for _ in client.app.get_dialogs(limit=200):
                        pass
                    await asyncio.sleep(1)
                    break
                except: 
                    await asyncio.sleep(2)
            
            me = await client.app.get_me()
            
            # Store client
            atk_state["_simp_client"] = client
            atk_state["_simp_phone"] = phone
            atk_state["_simp_me"] = me.first_name
            
            # Load groups with retry - fix enum type comparison
            groups = []
            try:
                for _w in range(3):
                    async for dialog in client.app.get_dialogs(limit=500):
                        cht = dialog.chat
                        if not cht: continue
                        # Fix: chat.type is an Enum in Pyrogram 2.x
                        t = str(cht.type).lower()
                        if "group" in t or "supergroup" in t:
                            cnt = getattr(cht, "members_count", 0) or 0
                            groups.append((cht.title or "بدون نام", cht.id, cnt))
                    if groups:
                        break
                    await asyncio.sleep(2)
                print(f"  Found {len(groups)} groups", flush=True)
            except Exception as ge:
                print(f"  dialogs error: {ge}", flush=True)
            
            text = f"✅ متصل: <b>{me.first_name}</b>\n\n"
            
            if not groups:
                text += "⚠️ هیچ گروهی پیدا نشد!\n\n"
                text += "دلایل ممکن:\n"
                text += "• اکانت عضو هیچ گروهی نیست\n"
                text += "• مشکل در اتصال به تلگرام\n\n"
                text += "راه حل: دوباره امتحان کن یا اکانت دیگه‌ای انتخاب کن."
                buttons = [[InlineKeyboardButton("🔄 تلاش مجدد", callback_data=f"simp_add_acc_{phone}")]]
                buttons.append([InlineKeyboardButton("🔙 بازگشت", callback_data="pick_account_add")])
            else:
                text += f"<b>مرحله ۲: گروه منبع را انتخاب کن</b>\n"
                text += f"━━━━━━━━━━━━━━━\n"
                text += f"اعضای این گروه اسکرپ و ادد میشن ({len(groups)} گروه):\n\n"
                
                buttons = []
                for gname, gid, gcnt in sorted(groups, key=lambda x:-x[2])[:20]:
                    buttons.append([InlineKeyboardButton(f" {gname[:28]} ({gcnt:,})", callback_data=f"simp_add_src_{gid}")])
                buttons.append([InlineKeyboardButton(" بازگشت", callback_data="pick_account_add")])
            
            await prog.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
        except Exception as e:
            # Disconnect client on error to free session
            if client:
                try: await client.disconnect()
                except: pass
            await prog.edit_text(f"❌ خطا در اتصال: {str(e)[:200]}\n\n💡 یک دقیقه صبر کن و دوباره امتحان کن.", 
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔄 تلاش مجدد", callback_data=f"simp_add_acc_{phone}")],
                    [InlineKeyboardButton("🔙 بازگشت", callback_data="home")],
                ]))
        return

    if d.startswith("simp_add_src_"):
        source_gid = int(d[len("simp_add_src_"):])
        client = atk_state.get("_simp_client")
        phone = atk_state.get("_simp_phone")
        
        if not client:
            await q.answer("خطا در وضعیت!", show_alert=True)
            return
        
        # Get source group info
        try:
            src = await client.app.get_chat(source_gid)
            source_name = src.title
        except:
            source_name = "گروه منبع"
        
        atk_state["simp_source_gid"] = source_gid
        atk_state["simp_source_name"] = source_name
        
        await q.message.edit_text(f"🔄 در حال اسکرپ از <b>{source_name}</b>...\n⏳ صبر کنید")
        
        # Scrape members NOW
        members = []
        try:
            async for member in client.app.get_chat_members(source_gid, limit=10000):
                u = member.user
                if u and not getattr(u, 'is_bot', False) and not getattr(u, 'is_deleted', False):
                    uid = u.id
                    if 10000 < uid < 10**11:
                        members.append({
                            "user_id": uid,
                            "first_name": u.first_name or "",
                            "last_name": u.last_name or "",
                            "username": u.username or "",
                            "access_hash": getattr(u, 'access_hash', 0) or 0,
                        })
        except Exception as se:
            await q.message.edit_text(f"❌ خطا در اسکرپ: {se}", reply_markup=InlineKeyboardMarkup([[_sub_back_btn(target="home")[0]]]))
            return
        
        if not members:
            await q.message.edit_text(" هیچ عضوی پیدا نشد!", reply_markup=InlineKeyboardMarkup([[_sub_back_btn(target="home")[0]]]))
            return
        
        # Save to temp
        atk_state["_simp_members"] = members
        atk_state["simp_source_count"] = len(members)
        
        # Load channels AND groups (supergroups) for target selection
        targets = []
        try:
            async for dialog in client.app.get_dialogs(limit=500):
                chat_type = str(dialog.chat.type).lower()
                # Include both channels and supergroups (not basic groups)
                if "channel" in chat_type or "supergroup" in chat_type:
                    cnt = getattr(dialog.chat, "members_count", 0) or 0
                    icon = "📡" if "channel" in chat_type else "👥"
                    targets.append((dialog.chat.title, dialog.chat.id, cnt, icon))
        except: pass
        
        text = f"✅ اسکرپ کامل شد!\n"
        text += f"━━━━━━━━━━━━━━━\n"
        text += f"📂 منبع: {source_name}\n"
        text += f"👥 اعضا: {len(members)} نفر\n\n"
        text += "<b>مرحله ۳: کانال یا گروه مقصد را انتخاب کن</b>\n"
        
        buttons = []
        for tname, tid, tcnt, icon in sorted(targets, key=lambda x:-x[2])[:20]:
            buttons.append([InlineKeyboardButton(f"{icon} {tname[:28]} ({tcnt:,})", callback_data=f"simp_add_tgt_{tid}")])
        
        if not targets:
            text += "\n⚠️ کانال یا گروهی پیدا نشد!"
            buttons.append([InlineKeyboardButton(" خانه", callback_data="home")])
        else:
            buttons.append([InlineKeyboardButton("🔙 گروه دیگه", callback_data=f"simp_add_acc_{phone}")])
        
        await q.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
        return

    if d.startswith("simp_add_tgt_") or d.startswith("simp_add_exec_"):
        target_gid = int(d[len("simp_add_exec_"):]) if d.startswith("simp_add_exec_") else int(d[len("simp_add_tgt_"):])
        client = atk_state.get("_simp_client")
        phone = atk_state.get("_simp_phone")
        members = atk_state.get("_simp_members", [])
        source_name = atk_state.get("simp_source_name", "گروه")
        source_gid = atk_state.get("simp_source_gid")
        
        if not client or not members:
            await q.answer("خطا!", show_alert=True)
            return
        
        # Start adding
        asyncio.create_task(_execute_simple_add(q, target_gid, client, phone, members, source_name))
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
        limits = load_adder_limits()
        available = [(p, MAX_ADD_PER_ACCOUNT - limits.get(p,{}).get("added",0)) 
                      for p in accounts if limits.get(p,{}).get("added",0) < MAX_ADD_PER_ACCOUNT]
        if not available:
            await q.answer(f"همه اکانت‌ها پر شدن!", show_alert=True)
            return
        atk_state["par_mode"] = "add"
        atk_state["par_add_available"] = available
        total_cap = sum(c for _,c in available)
        # Show available accounts
        text = f"⚡ <b>ادد موازی — مستقیم از دیتابیس</b>\n━━━━━━━━━━━━━━━━━━\n"
        text += f"📱 اکانت‌های آماده: <b>{len(available)}</b>\n"
        text += f"📦 ظرفیت کل: <b>{total_cap}</b> نفر\n"
        text += f"━━━━━━━━━━━━━━━━━━\n"
        for phone, cap in available:
            accs = load_accounts()
            name = accs.get(phone, {}).get("name", phone)
            text += f"📱 <code>{phone}</code> ({name}): <b>{cap}</b> ظرفیت\n"
        text += "\nحالا گروه/کانال مقصد رو انتخاب کن:\n"
        # Load dialogs from first available account
        try:
            phone0 = available[0][0]
            accs = load_accounts()
            fp = accs.get(phone0, {}).get("device_fp") or random.choice(DEVICE_FP)
            from attacker import safe_phone_filename as spfn
            sess_path = os.path.join(SESSIONS_DIR, f"acc_{spfn(phone0)}")
            tmp = AdvancedScraper(sess_path, API_ID, API_HASH, device_fp=fp)
            await robust_connect(tmp)
            async for _ in tmp.app.get_dialogs(limit=2000): pass
            await asyncio.sleep(2)
            chats = await _fast_load_chats(tmp)
            try: await tmp.disconnect()
            except: pass
        except Exception as e:
            await q.answer(f"خطا: {str(e)[:100]}", show_alert=True)
            return
        if not chats:
            await q.answer("چتی پیدا نشد!", show_alert=True)
            return
        buttons = []
        for gname, gid, gcount, chtype in sorted(chats, key=lambda x:-x[2])[:25]:
            icon = "📡" if chtype == "channel" else "👥"
            buttons.append([InlineKeyboardButton(f"{icon} {gname[:30]} | {gcount:,}", callback_data=f"par_dir_add_tgt_{gid}")])
        buttons.append([InlineKeyboardButton("✍️ دستی", callback_data="atk_target_manual")])
        buttons.append(_sub_back_btn())
        await q.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons), disable_web_page_preview=True)


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
                # Bulk scan buttons
                buttons.append([InlineKeyboardButton("🔥 اسکن همه گروه‌ها", callback_data="bulk_scan_groups"),
                                InlineKeyboardButton("📡 اسکن همه کانال‌ها", callback_data="bulk_scan_channels")])
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



def _normalize_phone(raw):
    """Normalize phone number to international format (+98...)"""
    phone = raw.strip().replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    # Already has +
    if phone.startswith("+"):
        return phone
    # Starts with 00
    if phone.startswith("00"):
        return "+" + phone[2:]
    # Iranian number starting with 0 (e.g. 0912...)
    if phone.startswith("0") and len(phone) >= 10:
        return "+98" + phone[1:]
    # Iranian number without 0 (e.g. 9123456789)
    if phone.isdigit() and len(phone) == 10 and phone[0] == "9":
        return "+98" + phone
    # Just digits but long enough
    if phone.isdigit() and len(phone) >= 11:
        return "+" + phone
    # Can't normalize
    return phone


def _validate_phone(phone):
    """Check if phone looks valid. Returns (is_valid, error_message)."""
    if not phone:
        return False, "شماره خالی است"
    if not phone.startswith("+"):
        return False, f"شماره باید با + شروع شود\nمثال: <code>+989123456789</code>\n\nشما وارد کردید: <code>{phone[:20]}</code>"
    digits = ''.join(c for c in phone if c.isdigit())
    if len(digits) < 7 or len(digits) > 15:
        return False, f"طول شماره نامعتبر است ({len(digits)} رقم)\nمثال: <code>+989123456789</code>\n\nشما وارد کردید: <code>{phone[:20]}</code>"
    return True, ""



async def _steps_impl(c, m):
    step = atk_state.get("step")
    hstep = atk_state.get("hunter_step")

    # Quick add CSV upload
    if atk_state.get("quick_step") == "csv_upload" and m.document:
        import csv as _csv
        file = await app.download_media(m.document, in_memory=True)
        reader = _csv.DictReader(io.StringIO(file.getvalue().decode("utf-8-sig")))
        uid_list = []
        for row in reader:
            try:
                uid = int(row.get("user_id", row.get("id", 0)))
                if 10000 < uid < 10**11:
                    uid_list.append(uid)
            except: continue
        if not uid_list:
            await m.reply_text("❌ user_id پیدا نشد در فایل!", reply_markup=main_menu())
            return
        random.shuffle(uid_list)
        gid = atk_state.get("quick_gid")
        gname = atk_state.get("quick_gname", "گروه")
        client = atk_state.get("quick_client")
        phone = atk_state["quick_phone"]
        await m.reply_text(f"📄 {len(uid_list)} کاربر از CSV\n⚡ شروع...")
        asyncio.create_task(_do_quick_add(_MsgWrapper(m), gid, gname, uid_list, client, phone))
        atk_state["quick_step"] = ""
        return

    # Quick add manual group ID
    if atk_state.get("quick_step") == "manual_gid":
        raw_gid = m.text.strip()
        try:
            gid = int(raw_gid)
        except:
            await m.reply_text("❌ آیدی نامعتبر!", reply_markup=main_menu())
            atk_state["quick_step"] = ""
            return
        atk_state["quick_gid"] = gid
        atk_state["quick_gname"] = f"گروه {gid}"
        phone = atk_state["quick_phone"]
        await m.reply_text(
            f"🎯 مقصد: {gid}\n\n📂 منبع:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🌐 همه کاربران DB", callback_data="quick_src_all")],
                [InlineKeyboardButton("📄 آپلود CSV", callback_data="quick_src_csv")],
            ]))
        atk_state["quick_step"] = ""
        return


    # ═══════════════ 🔍 Group Finder Query ═══════════════
    if step == "gf_query":
        query = m.text.strip()
        if not query or len(query) < 2:
            await m.reply_text("❌ عبارت جستجو خیلی کوتاهه.", reply_markup=main_menu())
            atk_state.clear()
            return
        status = await m.reply_text(f"🔍 در حال جستجوی گروه‌های <b>{query}</b>...\n⏳ صبر کن...")
        found_groups = []
        atk = atk_state.get("atk")
        if atk and gf:
            try:
                found_groups = await gf.find_groups(query, client=atk, use_web=False, use_ai=True)
            except Exception as e:
                print(f"GF error: {e}")
        if not found_groups and gf:
            try:
                found_groups = await gf.find_groups(query, client=None, use_web=True, use_ai=False)
            except: pass
        if not found_groups:
            await status.edit_text(f"❌ هیچ گروهی برای «{query}» پیدا نشد.", reply_markup=InlineKeyboardMarkup([[_sub_back_btn()]]))
            atk_state.clear()
            return
        text = f"🔍 <b>نتایج: {query}</b>\n━━━━━━━━━━━━━━━━━━\n📦 پیدا شد: <b>{len(found_groups)}</b> گروه/کانال\n\n"
        buttons = []
        for i_g, g in enumerate(found_groups[:20], 1):
            icon = _chat_type_icon(g.get('type', 'group'))
            title = g.get('title', '?')[:35]
            members = g.get('members', 0)
            relevance = g.get('relevance', 0)
            stars = "⭐" * min(5, max(1, relevance // 20))
            username = g.get('chat_username', '') or str(g.get('chat_id', ''))
            text += f"{i_g}. {icon} <b>{title}</b>\n   👤 {members:,} · {stars}\n   🔗 @{username}\n\n"
            if username and not username.startswith('-'):
                buttons.append([InlineKeyboardButton(f"{i_g}. {icon} @{username[:20]}", callback_data=f"gf_scan_{username}")])
        if len(found_groups) > 20:
            text += f"... و {len(found_groups) - 20} گروه دیگه"
        buttons.append([InlineKeyboardButton("🔍 جستجوی جدید", callback_data="group_finder_menu")])
        buttons.append([InlineKeyboardButton("🏠 منوی اصلی", callback_data="home")])
        atk_state.clear()
        await status.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons), disable_web_page_preview=True)
        return

    if not step: return
    if step == "ig_target_username":
        raw = m.text.strip()
        target = ig_scraper.extract_username(raw)
        if not target or len(target) < 2:
            await m.reply_text("❌ نتونستم نام کاربری رو تشخیص بدم!\nلینک اینستاگرام یا username رو بفرست.", reply_markup=main_menu())
            return
        atk_state.clear()
        from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton as IB
        await m.reply_text(
            f"🔍 @{target}\nشروع اسکرپ...",
            reply_markup=InlineKeyboardMarkup([[IB("▶️ شروع اسکرپ", callback_data=f"ig_scrape_{target}")]]))
        return

    # ==================== لاگین دستی اینستاگرام ====================
    if step == "ig_login_username":
        username = m.text.strip().lower()
        username = re.sub(r'[^a-zA-Z0-9._]', '', username.lstrip('@'))
        if not username or len(username) < 2:
            await m.reply_text("❌ نام کاربری نامعتبر! دوباره بفرست.", reply_markup=main_menu())
            return
        atk_state["ig_username"] = username
        atk_state["step"] = "ig_login_password"
        await m.reply_text(
            f"👤 نام کاربری: <code>{username}</code>\n\n"
            "🔑 حالا <b>پسورد</b> رو بفرست:\n\n"
            "⚠️ توجه: اینستاگرام ممکنه با IP رندر چالش بده.\n"
            "اگر لاگین نشد، از «📥 آپلود سشن» استفاده کن.",
            reply_markup=InlineKeyboardMarkup([[_sub_back_btn(target="ig_menu")[0]]]))
        return

    if step == "ig_login_password":
        password = m.text.strip()
        username = atk_state.get("ig_username", "")
        if not username:
            await m.reply_text("❌ اول نام کاربری رو بفرست!", reply_markup=main_menu())
            atk_state.clear()
            return
        st = await m.reply_text("🔐 در حال لاگین به اینستاگرام...")
        try:
            import instaloader
            L = instaloader.Instaloader(sleep=True, quiet=True, download_pictures=False,
                                         download_videos=False, download_video_thumbnails=False, compress_json=False)
            L.login(username, password)
            # Save session
            os.makedirs(ig_scraper.SESSION_DIR, exist_ok=True)
            L.save_session_to_file(ig_scraper.IG_SESSION_FILE)
            atk_state.clear()
            await st.edit_text(
                f"✅ <b>لاگین موفق!</b>\n"
                f"👤 اکانت: <code>{username}</code>\n"
                f"💾 سشن ذخیره شد.\n\n"
                "حالا می‌تونی از «🔍 اسکرپ فالوور» استفاده کنی.",
                reply_markup=InlineKeyboardMarkup([[_sub_back_btn(target="ig_menu")[0]]]))
        except Exception as e:
            err = str(e).lower()
            if "bad credentials" in err or "wrong password" in err:
                msg = "❌ پسورد اشتباهه!"
            elif "challenge" in err or "verify" in err or "suspicious" in err:
                msg = "❌ اینستاگرام چالش امنیتی داده!\n\n✅ راه حل: از «📥 آپلود سشن» استفاده کن.\nبا Instaloader روی سیستم خودت لاگین کن و فایل سشن رو آپلود کن."
            elif "2fa" in err or "two-factor" in err:
                msg = "❌ این اکانت 2FA داره!\n\n✅ از «📥 آپلود سشن» استفاده کن.\nبا Instaloader روی سیستم خودت لاگین کن (2FA رو وارد کن) و فایل سشن رو آپلود کن."
            else:
                msg = f"❌ خطا در لاگین:\n{str(e)[:300]}"
            await st.edit_text(msg, reply_markup=InlineKeyboardMarkup([[_sub_back_btn(target="ig_menu")[0]]]))
            atk_state.clear()
        # Delete the message with password for security
        try: await m.delete()
        except: pass
        return

    # ==================== 📸 آپلود فایل سشن اینستاگرام ====================
    if step == "upload_ig_session" and m.document:
        doc = m.document
        fname = getattr(doc, 'file_name', '') or 'ig_session'
        st = await m.reply_text("📥 فایل سشن اینستاگرام دریافت شد، در حال بررسی...")
        file_data = await app.download_media(m, in_memory=True)
        try:
            os.makedirs(ig_scraper.SESSION_DIR, exist_ok=True)
            with open(ig_scraper.IG_SESSION_FILE, "wb") as f:
                f.write(file_data.getvalue())
            # Test if it works
            L = ig_scraper.get_instaloader()
            L.load_session_from_file(ig_scraper.IG_USERNAME, filename=ig_scraper.IG_SESSION_FILE)
            L.test_login()
            await st.edit_text(
                "✅ <b>سشن اینستاگرام با موفقیت لود شد!</b>\n\n"
                "حالا می‌تونی اسکرپ کنی.",
                reply_markup=InlineKeyboardMarkup([[_sub_back_btn(target="ig_menu")[0]]]))
        except Exception as e:
            await st.edit_text(
                f"❌ سشن معتبر نیست یا منقضی شده:\n{str(e)[:200]}\n\n"
                "دوباره با Instaloader لاگین کن و فایل جدید آپلود کن.",
                reply_markup=InlineKeyboardMarkup([[_sub_back_btn(target="ig_menu")[0]]]))
        atk_state.clear()
        return

    # ==================== آپلود مستقیم فایل سشن تلگرام (دور زدن 2FA) ====================
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
        phone = _normalize_phone(m.text)
        # چک کن اکانت از قبل وجود نداشته باشه
        if phone in list_saved_accounts():
            await m.reply_text(f"⚠️ اکانت {phone} از قبل در لیست ذخیره شده است! نیازی به افزودن مجدد نیست، از لیست اکانت ها انتخاب کنید.", reply_markup=main_menu())
            atk_state.clear()
            return
        # Validate phone
        valid, err = _validate_phone(phone)
        if not valid:
            await m.reply_text(
                f"❌ شماره نامعتبر!\n\n{err}\n\n"
                "فرمت‌های قابل قبول:\n"
                "• <code>+989123456789</code> (بین‌المللی)\n"
                "• <code>09123456789</code> (با صفر)\n"
                "• <code>9123456789</code> (بدون صفر)", 
                reply_markup=main_menu())
            atk_state.clear()
            return
        atk_state["phone"] = phone
        st = await m.reply_text(f"📡 شماره: <code>{phone}</code>\nدر حال ارسال کد...")
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
            await st.edit_text("✅ کد تایید ارسال شد!\n\n📱 <b>کد ۵ رقمی رو بفرست:</b>\n⏱️ ۵ دقیقه فرصت داری — کد توی SMS میاد", disable_web_page_preview=True)
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
        except (PhoneCodeExpired, PhoneCodeInvalid):
            # Auto-resend code
            try:
                sent = await acc_client.app.send_code(phone)
                atk_state["hash"] = sent.phone_code_hash
                await st.edit_text(
                    "⏰ کد قبلی منقضی شده بود — کد جدید ارسال شد!\n\n"
                    "📱 <b>کد ۵ رقمی جدید رو وارد کن:</b>\n\n"
                    "⏱️ <b>۵ دقیقه فرصت داری!</b> سریع باش\n"
                    "💡 نکته: کد SMS ممکنه ۳۰-۶۰ ثانیه طول بکشه",
                    disable_web_page_preview=True)
            except Exception as e2:
                # Use reply to avoid MESSAGE_NOT_MODIFIED
                await m.reply_text(f"❌ خطا در ارسال مجدد کد: {str(e2)[:200]}\nلطفاً از منو دوباره شروع کنید.", reply_markup=main_menu())
                atk_state.clear()
                atk_state.clear()
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
        phone = _normalize_phone(m.text)
        if phone in list_saved_accounts():
            await m.reply_text(f"⚠️ اکانت {phone} از قبل ذخیره شده است! لطفا از منوی انتخاب اکانت استفاده کنید.", reply_markup=main_menu())
            atk_state.clear()
            return
        valid, err = _validate_phone(phone)
        if not valid:
            await m.reply_text(f"❌ شماره نامعتبر!\n\n{err}", reply_markup=main_menu())
            atk_state.clear()
            return
        atk_state["phone"] = phone
        after_mode = atk_state.get("after_auth_mode", "attack")
        st = await m.reply_text(f"📡 شماره: <code>{phone}</code>\nدر حال ارسال کد...")
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
            await st.edit_text("✅ کد تایید ارسال شد!\n\n📱 <b>کد ۵ رقمی رو بفرست:</b>\n⏱️ ۵ دقیقه فرصت داری\n⚠️ بعد از این بار دیگه کد نمیخوای!", disable_web_page_preview=True)
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
        except (PhoneCodeExpired, PhoneCodeInvalid):
            try:
                sent = await new_client.app.send_code(phone)
                atk_state["hash"] = sent.phone_code_hash
                await st.edit_text("⏰ کد منقضی شده بود — کد جدید ارسال شد!\n📱 کد ۵ رقمی جدید رو بفرست:")
            except Exception as e2:
                # Use reply to avoid MESSAGE_NOT_MODIFIED
                await m.reply_text(f"❌ خطا در ارسال مجدد: {str(e2)[:200]}", reply_markup=main_menu())
                atk_state.clear()
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
        phone = _normalize_phone(m.text)
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
            await st.edit_text("✅ کد ارسال شد!\n\n📱 <b>کد ۵ رقمی رو بفرست:</b>\n⏱️ ۵ دقیقه فرصت داری", disable_web_page_preview=True)
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
        except (PhoneCodeExpired, PhoneCodeInvalid):
            try:
                sent = await atk.app.send_code(phone)
                atk_state["hash"] = sent.phone_code_hash
                await st.edit_text("⏰ کد جدید ارسال شد! کد ۵ رقمی رو بفرست:")
            except Exception as e2:
                # Use reply to avoid MESSAGE_NOT_MODIFIED
                await m.reply_text(f"❌ خطا: {str(e2)[:200]}", reply_markup=main_menu())
                atk_state.clear()
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
        phone = _normalize_phone(m.text)
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
            await st.edit_text("✅ کد تایید به اکانت ارسال شد!\n\n📱 <b>کد ۵ رقمی رو بفرست:</b>\n⏱️ ۵ دقیقه فرصت داری", disable_web_page_preview=True)
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
        except (PhoneCodeExpired, PhoneCodeInvalid):
            try:
                sent = await add_client.app.send_code(phone)
                atk_state["hash"] = sent.phone_code_hash
                await st.edit_text("⏰ کد جدید ارسال شد! کد ۵ رقمی رو بفرست:")
            except Exception as e2:
                # Use reply to avoid MESSAGE_NOT_MODIFIED
                await m.reply_text(f"❌ خطا: {str(e2)[:200]}", reply_markup=main_menu())
                atk_state.clear()
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
            # Resolve target channel once for AddContact+InviteToChannel
            from pyrogram.raw.functions.contacts import AddContact as _AC2
            from pyrogram.raw.functions.channels import InviteToChannel as _ITC2
            from pyrogram.errors import PeerIdInvalid as _PID2
            _target_peer_ch = await add_client.app.resolve_peer(target_gid)
            
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
                    # AddContact + InviteToChannel (works for channels)
                    from pyrogram.raw.functions.contacts import AddContact
                    from pyrogram.raw.functions.channels import InviteToChannel
                    try:
                        user_peer = await add_client.app.resolve_peer(uid)
                        try:
                            await add_client.app.invoke(AddContact(id=user_peer, first_name=str(uid), last_name="", phone="", add_phone_privacy_exception=False))
                            await asyncio.sleep(0.3)
                        except: pass
                        await add_client.app.invoke(InviteToChannel(channel=_target_peer_ch, users=[user_peer]))
                    except PeerIdInvalid:
                        raise PeerIdInvalid
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


class _MsgWrapper:
    """Wrap a Message to look like a CallbackQuery message for _do_quick_add"""
    def __init__(self, msg):
        self._msg = msg
        self.message = msg
    async def edit_text(self, text, reply_markup=None, disable_web_page_preview=None, **kw):
        return await self._msg.edit_text(text, reply_markup=reply_markup, disable_web_page_preview=disable_web_page_preview)



async def _execute_simple_add(q, target_gid, client, phone, members, source_name):
    """Execute simple add flow - Professional method (like top GitHub projects)"""
    from pyrogram.raw.functions.channels import InviteToChannel
    from pyrogram.raw.types import InputPeerUser
    from pyrogram.errors import FloodWait, PeerIdInvalid, UserAlreadyParticipant
    from pyrogram.errors import UserPrivacyRestricted, UserNotMutualContact
    from pyrogram.errors import ChatAdminRequired, UsersTooMuch
    
    prog = q.message
    added = 0
    failed = 0
    skipped = 0
    errors_detail = {"peer": 0, "privacy": 0, "already": 0, "flood": 0, "channels": 0, "other": 0}
    first_error = ""
    start_t = time.time()
    
    limits = load_adder_limits()
    already_added = limits.get(phone, {}).get("added", 0)
    remaining = MAX_ADD_PER_ACCOUNT - already_added
    
    # Get target name
    try:
        tgt = await client.app.get_chat(target_gid)
        target_name = tgt.title
    except:
        target_name = "گروه مقصد"
    
    # Resolve target once
    try:
        target_peer = await client.app.resolve_peer(target_gid)
    except Exception as e:
        await prog.edit_text(f"❌ گروه مقصد resolve نشد: {e}", reply_markup=InlineKeyboardMarkup([[_sub_back_btn(target="home")[0]]]))
        return
    
    total = min(len(members), remaining)
    
    async def upd():
        try:
            elapsed = int(time.time() - start_t)
            m, s = elapsed // 60, elapsed % 60
            pct = int((added + failed + skipped) * 100 / max(1, total))
            bar = "█" * (pct // 5) + "░" * (20 - pct // 5)
            spd = int(added / (elapsed / 60)) if elapsed > 30 else 0
            txt = (
                f"📂 {source_name} → 👥 {target_name}\n"
                f"{bar} {pct}%\n"
                f"✅ {added} ❌ {failed} ⏭ {skipped}\n"
                f"⏱ {m:02d}:{s:02d} ⚡ {spd}/min\n"
                f"📊 ظرفیت: {already_added + added}/{MAX_ADD_PER_ACCOUNT}"
            )
            await prog.edit_text(txt, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("️⏹️ توقف", callback_data="stop_op")]]))
        except: pass
    
    await upd()
    
    # Add members one by one
    for i, member in enumerate(members[:remaining]):
        uid = member.get("user_id", 0)
        if uid <= 10000 or uid >= 10**11:
            skipped += 1
            continue
        
        if is_user_already_added(target_gid, uid):
            skipped += 1
            continue
        
        # Check stop request
        if atk_state.get("_stop_requested"):
            break
        
        try:
            user_peer = None
            
            # 🏆 Method 1: Username (BEST - always works if username exists)
            username = member.get("username", "").strip()
            if username:
                try:
                    # Remove @ if present
                    clean_username = username.lstrip("@")
                    user_peer = await client.app.resolve_peer(clean_username)
                except Exception:
                    pass  # Fall through to next method
            
            # Method 2: Try resolve_peer with user_id (works if in cache)
            if user_peer is None:
                try:
                    user_peer = await client.app.resolve_peer(uid)
                except Exception:
                    pass
            
            # Method 3: access_hash from member data (if saved during scrape)
            if user_peer is None and member.get("access_hash"):
                try:
                    user_peer = InputPeerUser(user_id=uid, access_hash=int(member["access_hash"]))
                except:
                    pass
            
            # Method 4: Last resort - access_hash=0 (rarely works)
            if user_peer is None:
                try:
                    user_peer = InputPeerUser(user_id=uid, access_hash=0)
                except:
                    skipped += 1
                    errors_detail["peer"] += 1
                    if not first_error: first_error = f"Can't resolve {uid} (no username)"
                    continue
            
            if user_peer is None:
                skipped += 1
                errors_detail["peer"] += 1
                continue
            
            # Direct InviteToChannel (NO AddContact - it wastes time and triggers limits)
            await client.app.invoke(
                InviteToChannel(channel=target_peer, users=[user_peer])
            )
            
            added += 1
            mark_user_as_added(target_gid, target_name, uid)
            limits = load_adder_limits()
            limits[phone] = {"added": already_added + added, "last_used": int(time.time())}
            save_adder_limits(limits)
            
            # ═══ Professional delay strategy ═══
            total_done = already_added + added
            
            # Every 20 successful adds, take a 3-5 min break
            if total_done > 0 and total_done % 20 == 0:
                break_time = random.randint(180, 300)
                await prog.edit_text(
                    f"☕ استراحت {break_time // 60} دقیقه‌ای...\n"
                    f"✅ {added} نفر تا الان اد شدن\n"
                    f"📊 {total_done}/{MAX_ADD_PER_ACCOUNT}\n"
                    f"⏳ صبر کن..."
                )
                await asyncio.sleep(break_time)
            else:
                # Normal delay: 30-90 seconds (like top GitHub projects)
                delay = random.randint(30, 90)
                await asyncio.sleep(delay)
            
        except FloodWait as fw:
            failed += 1
            errors_detail["flood"] += 1
            wait = fw.value + 10
            await prog.edit_text(f"⏱️ Flood Wait {fw.value}s — صبر...")
            await asyncio.sleep(wait)
        except UserAlreadyParticipant:
            skipped += 1
            errors_detail["already"] += 1
            mark_user_as_added(target_gid, target_name, uid)
        except (UserPrivacyRestricted, UserNotMutualContact):
            failed += 1
            errors_detail["privacy"] += 1
        except PeerIdInvalid:
            failed += 1
            errors_detail["peer"] += 1
        except ChatAdminRequired:
            failed += 1
            errors_detail["other"] += 1
            if not first_error: first_error = "اکانت ادمین نیست!"
            break
        except UsersTooMuch:
            failed += 1
            errors_detail["channels"] += 1
            await asyncio.sleep(15)
        except Exception as e:
            failed += 1
            es = str(e).lower()
            if "channels_too_much" in es:
                errors_detail["channels"] += 1
            elif "peer_flood" in es:
                errors_detail["flood"] += 1
                await asyncio.sleep(3600)  # 1 hour break on PEER_FLOOD
            else:
                errors_detail["other"] += 1
            if not first_error: first_error = str(e)[:200]
        
        if (added + failed + skipped) % 3 == 0:
            await upd()
    
    # Final report
    elapsed = int(time.time() - start_t)
    m, s = elapsed // 60, elapsed % 60
    text = f"✅ <b>تمام شد!</b>\n"
    text += f"━━━━━━━━━━━━━━━\n"
    text += f"📂 منبع: {source_name}\n"
    text += f"📡 مقصد: {target_name}\n"
    text += f"✅ اضافه شده: {added}\n"
    text += f"❌ ناموفق: {failed}\n"
    text += f"⏭ رد شده: {skipped}\n"
    text += f"⏱ زمان: {m:02d}:{s:02d}\n"
    text += f"📊 ظرفیت: {already_added + added}/{MAX_ADD_PER_ACCOUNT}"
    
    if failed > 0 or errors_detail.get("peer", 0) > 0:
        text += f"\n\n<b>جزئیات خطا:</b>\n"
        if errors_detail["peer"]: text += f"🔍 Peer Invalid: {errors_detail['peer']}\n"
        if errors_detail["privacy"]: text += f"🔒 Privacy: {errors_detail['privacy']}\n"
        if errors_detail["already"]: text += f"👥 قبلاً عضو: {errors_detail['already']}\n"
        if errors_detail["flood"]: text += f"⏱ Flood: {errors_detail['flood']}\n"
        if errors_detail["other"]: text += f"❓ سایر: {errors_detail['other']}\n"
        if first_error: text += f"\n💬 اولین خطا: {first_error[:200]}"
    
    # Cleanup
    atk_state.pop("_simp_client", None)
    atk_state.pop("_simp_members", None)
    
    buttons = [
        [InlineKeyboardButton("🔄 ادد از گروه دیگه", callback_data="pick_account_add")],
        [InlineKeyboardButton(" خانه", callback_data="home")],
    ]
    
    try:
        await prog.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
    except: pass


async def _do_quick_add(q, gid, gname, uid_list, client, phone):
    """Simple add to group using add_chat_members"""
    from pyrogram.errors import FloodWait, PeerIdInvalid, UserAlreadyParticipant
    from pyrogram.errors import UserPrivacyRestricted, UserNotMutualContact
    from pyrogram.errors import ChatAdminRequired, UsersTooMuch
    
    added = 0
    failed = 0
    errors = {"peer": 0, "privacy": 0, "already": 0, "flood": 0, "other": 0}
    start_t = time.time()
    total = len(uid_list)
    prog = q.message

    async def upd():
        try:
            elapsed = int(time.time() - start_t)
            m, s = elapsed // 60, elapsed % 60
            pct = int((added + failed) * 100 / total) if total > 0 else 0
            bar = "█" * (pct // 5) + "░" * (20 - pct // 5)
            txt = f"⚡ {gname}\n{bar} {pct}%\n✅ {added} ❌ {failed}\n⏱ {m:02d}:{s:02d}"
            await prog.edit_text(txt, 
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⏹️", callback_data="stop_op")]]))
        except: pass

    for i, uid in enumerate(uid_list):
        try:
            await client.app.add_chat_members(gid, uid)
            added += 1
            mark_user_as_added(gid, gname, uid)
            # Save limit
            limits = load_adder_limits()
            limits[phone] = {"added": limits.get(phone, {}).get("added", 0) + 1, "last_used": int(time.time())}
            save_adder_limits(limits)
            await asyncio.sleep(random.randint(5, 10))
        except FloodWait as fw:
            failed += 1; errors["flood"] += 1
            await asyncio.sleep(fw.value + 3)
        except UserAlreadyParticipant:
            failed += 1; errors["already"] += 1
        except (UserPrivacyRestricted, UserNotMutualContact):
            failed += 1; errors["privacy"] += 1
        except PeerIdInvalid:
            failed += 1; errors["peer"] += 1
        except ChatAdminRequired:
            failed += 1; errors["other"] += 1
            await prog.edit_text(f"❌ اکانت ادمین نیست!\n✅ {added} | ❌ {failed}")
            break
        except UsersTooMuch:
            failed += 1; errors["other"] += 1
            await asyncio.sleep(15)
        except Exception as e:
            failed += 1; errors["other"] += 1
            await asyncio.sleep(2)
        if (added + failed) % 5 == 0:
            await upd()

    elapsed = int(time.time() - start_t)
    m, s = elapsed // 60, elapsed % 60
    text = f"✅ <b>تمام شد — {gname}</b>\n{'━'*20}\n"
    text += f"✅ ادد: {added}\n❌ خطا: {failed}\n⏱ {m:02d}:{s:02d}\n"
    if errors["privacy"]: text += f"🔒 Privacy: {errors['privacy']}\n"
    if errors["already"]: text += f"👥 قبلاً عضو: {errors['already']}\n"
    if errors["flood"]: text += f"⏱ Flood: {errors['flood']}\n"
    if errors["peer"]: text += f"🔍 Peer: {errors['peer']}\n"
    if errors["other"]: text += f"❓ سایر: {errors['other']}\n"
    await prog.edit_text(text, reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("🏠 خانه", callback_data="home")],
    ]))

if __name__ == "__main__":
    # Import and register group manager handlers
    try:
        from group_manager import register_group_handlers
        register_group_handlers(app, ADMIN_ID)
        print("✅ Group Manager loaded!", flush=True)
    except Exception as e:
        print(f"⚠️ Group Manager error: {e}", flush=True)
    
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
