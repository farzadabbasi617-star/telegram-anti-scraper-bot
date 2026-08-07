# =================================================================
# ربات ضد اسکریپت - نسخه نهایی قطعی + سشن دائمی اکانت ها
# =================================================================
import asyncio
import sys
import os
import json

loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
_original_get_event_loop = asyncio.get_event_loop
def _patched_get_event_loop():
    return loop
asyncio.get_event_loop = _patched_get_event_loop

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

from attacker import AdvancedScraper, SESSIONS_DIR, safe_phone_filename, DEVICE_FP
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
)
from bg_scraper import start_in_background as bg_scraper_start, _backup_session

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

app = Client("antiscraper_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, workers=1)

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
    global bg_started, hunter_bg_started, bg_scraper_started
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
    global CURRENT_GROUP_ID, defender, bg_started, config
    d = q.data

    # ==================== خانه و منوهای دسته‌بندی ====================
    if d == "noop":
        await q.answer(cache_time=3)
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
        atk_state["downloader_mode"] = True
        await q.message.edit_text(text,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="menu_settings")]]))
        return

    if d == "select_group":
        groups = []
        async for dialog in app.get_dialogs():
            if dialog.chat.type in ["supergroup", "group"] or (dialog.chat.type == "channel" and getattr(dialog.chat, 'megagroup', False)):
                try:
                    mem = await app.get_chat_member(dialog.chat.id, "me")
                    if mem.status in ["administrator", "creator"]:
                        groups.append((dialog.chat.title, dialog.chat.id))
                except:
                    pass
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
            async def on_progress(text):
                try:
                    nonlocal progress_msg
                    await progress_msg.edit_text(text, disable_web_page_preview=True)
                except Exception:
                    pass
            try:
                users = await atk.run_full_scrape(target.id, progress_cb=on_progress)
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
                await atk.connect()
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
                async def on_progress(text):
                    nonlocal progress_msg
                    try:
                        await progress_msg.edit_text(f"🔄 تلاش مجدد\n{text}", disable_web_page_preview=True)
                    except: pass
                users = await atk.run_full_scrape(gid, progress_cb=on_progress)
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
        atk_state["step"] = "adder_file"
        already = atk_state.get("already_added", 0)
        remaining = MAX_ADD_PER_ACCOUNT - already
        await q.answer()
        await q.message.edit_text(f"✅ گروه مقصد: {target.title}\n⚠️ این اکانت حداکثر می‌تواند {remaining} نفر دیگر اضافه کند.\nحالا **فایل CSV** را همینجا آپلود کنید.")
        return

    if d == "add_target_manual":
        await q.answer()
        atk_state["step"] = "adder_target_manual"
        await q.message.edit_text("✍️ آیدی عددی گروه مقصد را بفرستید (با -100 شروع می‌شود):")
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
            await tmp.connect()
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
            await tmp.connect()
            async for _ in tmp.app.get_dialogs(limit=2000):
                pass
            await asyncio.sleep(2)
            dialogs = []
            async for dlg in tmp.app.get_dialogs(limit=200):
                try:
                    c = await tmp.app.get_chat(dlg.chat.id)
                    if "group" in str(getattr(c.type,"","")).lower():
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
            await _tmp.connect()
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
            await working_client.connect()
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
                await working_client.connect()
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
            group_list = []
            try:
                async for dialog in atk.app.get_dialogs(limit=2000):
                    if dialog.chat.type in ["supergroup", "group"] or (dialog.chat.type == "channel" and getattr(dialog.chat, 'megagroup', False)):
                        try:
                            mstat = await atk.app.get_chat_member(dialog.chat.id, "me")
                            if mstat.status in ["administrator", "creator", "member", "restricted"]:
                                group_list.append((dialog.chat.title, dialog.chat.id, dialog.chat.members_count or 0))
                        except:
                            pass
                    await asyncio.sleep(0.02)
            except Exception as e:
                print(f"خطا در بارگذاری لیست: {e}", flush=True)
            atk_state["available_groups"] = group_list
            if group_list:
                buttons = []
                for gname, gid, gcount in sorted(group_list, key=lambda x:-x[2]):
                    buttons.append([InlineKeyboardButton(f"👥 {gname[:35]} | {gcount:,} نفر", callback_data=f"atk_target_{gid}")])
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
            add_groups = []
            try:
                async for dialog in add_client.app.get_dialogs(limit=2000):
                    if dialog.chat.type in ["supergroup", "group"] or (dialog.chat.type == "channel" and getattr(dialog.chat, 'megagroup', False)):
                        try:
                            mstat = await add_client.app.get_chat_member(dialog.chat.id, "me")
                            if mstat.status in ["administrator", "creator", "member"]:
                                can_add = True
                                if mstat.status == "administrator" and mstat.privileges:
                                    can_add = mstat.privileges.can_invite_users
                                if can_add:
                                    add_groups.append((dialog.chat.title, dialog.chat.id, dialog.chat.members_count or 0))
                        except:
                            pass
                    await asyncio.sleep(0.02)
            except Exception as e:
                print(f"خطا در لیست ادد: {e}", flush=True)
            atk_state["available_add_groups"] = add_groups
            remaining = MAX_ADD_PER_ACCOUNT - already
            if add_groups:
                buttons = []
                for gname, gid, gcount in sorted(add_groups, key=lambda x:-x[2]):
                    buttons.append([InlineKeyboardButton(f"➕ {gname[:35]} | {gcount:,} نفر", callback_data=f"add_target_{gid}")])
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
            acc_client = AdvancedScraper(f"newacc_tmp_{int(time.time())}", API_ID, API_HASH, phone=phone, device_fp=chosen_fp)
            await acc_client.connect()
            sent = await acc_client.app.send_code(phone)
            atk_state["new_acc_client"] = acc_client
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
            await st.edit_text("🔐 اکانت شما رمز دو عاملی دارد، لطفا پسورد 2FA را بفرستید:")
            return
        except Exception as e:
            await m.reply_text(f"❌ خطا در کد: {str(e)}")
            return
        me = await acc_client.app.get_me()
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
            await m.reply_text(f"❌ رمز اشتباه: {str(e)}")
            return
        me = await acc_client.app.get_me()
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
            new_client = AdvancedScraper(f"login_tmp_{int(time.time())}", API_ID, API_HASH, phone=phone, device_fp=chosen_fp, in_memory=False)
            await new_client.connect()
            sent = await new_client.app.send_code(phone)
            atk_state["new_client"] = new_client
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
            await st.edit_text("🔐 رمز دو عاملی لازم است، پسورد را بفرستید:")
            return
        except Exception as e:
            await m.reply_text(f"❌ خطا در کد: {str(e)}")
            return
        # ذخیره اکانت
        me = await new_client.app.get_me()
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
                await atk.connect()
                atk_state["atk"] = atk
                atk_state["st"] = st
                atk_state["step"] = "after_login_attack"
                group_list = []
                try:
                    async for dialog in atk.app.get_dialogs(limit=2000):
                        if dialog.chat.type in ["supergroup", "group"] or (dialog.chat.type == "channel" and getattr(dialog.chat, 'megagroup', False)):
                            try:
                                mstat = await atk.app.get_chat_member(dialog.chat.id, "me")
                                if mstat.status in ["administrator", "creator", "member", "restricted"]:
                                    group_list.append((dialog.chat.title, dialog.chat.id, dialog.chat.members_count or 0))
                            except: pass
                        await asyncio.sleep(0.02)
                except Exception as e:
                    print(f"خطای لیست: {e}", flush=True)
                atk_state["available_groups"] = group_list
                buttons = []
                for gname, gid, gcount in sorted(group_list, key=lambda x:-x[2]):
                    buttons.append([InlineKeyboardButton(f"👥 {gname[:35]} | {gcount:,} نفر", callback_data=f"atk_target_{gid}")])
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
                await add_client.connect()
                atk_state["add_client"] = add_client
                atk_state["st"] = st
                add_groups = []
                try:
                    async for dialog in add_client.app.get_dialogs(limit=2000):
                        if dialog.chat.type in ["supergroup", "group"] or (dialog.chat.type == "channel" and getattr(dialog.chat, 'megagroup', False)):
                            try:
                                mstat = await add_client.app.get_chat_member(dialog.chat.id, "me")
                                if mstat.status in ["administrator", "creator", "member"]:
                                    add_groups.append((dialog.chat.title, dialog.chat.id, dialog.chat.members_count or 0))
                            except: pass
                        await asyncio.sleep(0.02)
                except Exception as e:
                    print(f"خطای لیست ادد: {e}", flush=True)
                remaining = MAX_ADD_PER_ACCOUNT - already
                buttons = []
                for gname, gid, gcount in sorted(add_groups, key=lambda x:-x[2]):
                    buttons.append([InlineKeyboardButton(f"➕ {gname[:35]} | {gcount:,} نفر", callback_data=f"add_target_{gid}")])
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
            await m.reply_text(f"❌ رمز اشتباه: {str(e)}")
            return
        me = await new_client.app.get_me()
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
            atk = AdvancedScraper("atk", API_ID, API_HASH, phone=phone)
            await atk.connect()
            sent = await atk.app.send_code(phone)
            atk_state["atk"] = atk
            atk_state["hash"] = sent.phone_code_hash
            atk_state["st"] = st
            atk_state["step"] = "code"
            await st.edit_text("✅ کد ارسال شد، کد ۵ رقمی را بفرست:")
        except Exception as e:
            await st.edit_text(f"❌ خطا: {str(e)}")
            atk_state.clear()

    elif step == "code":
        code = m.text.strip()
        atk = atk_state["atk"]
        phone = atk_state["phone"]
        h = atk_state["hash"]
        st = atk_state["st"]
        try:
            await atk.app.sign_in(phone, h, code)
        except Exception as e:
            await m.reply_text(f"❌ خطا در کد: {str(e)}")
            return
        atk_state["step"] = "target"
        await st.edit_text(
            "✅ ورود موفق!\n"
            "🔄 در حال بارگذاری لیست گروه‌های شما (تا از این ارورها جلوگیری کنیم)...\n"
            "چند لحظه صبر کنید..."
        )
        # اسکن خودکار تمام دیالوگ ها برای گرم کردن کش تلگرام، جلوگیری از ارور CHAT_INVALID/عضو نیستی
        try:
            group_list = []
            async for dialog in atk.app.get_dialogs(limit=2000):
                if dialog.chat.type in ["supergroup", "group"] or (dialog.chat.type == "channel" and getattr(dialog.chat, 'megagroup', False)):
                    try:
                        # چک کن که واقعا عضو باشی
                        me = await atk.app.get_chat_member(dialog.chat.id, "me")
                        if me.status in ["administrator", "creator", "member", "restricted"]:
                            group_list.append((dialog.chat.title, dialog.chat.id, dialog.chat.members_count or 0))
                    except:
                        pass
                await asyncio.sleep(0.02)
            atk_state["available_groups"] = group_list
        except Exception as e:
            print(f"اسکن دیالوگ ها با خطا مواجه شد: {e}", flush=True)
            group_list = []
            atk_state["available_groups"] = []

        if group_list:
            # به جای درخواست آیدی دستی، لیست گروه ها رو نشون بده
            buttons = []
            for gname, gid, gcount in sorted(group_list, key=lambda x: -x[2]):
                btn_text = f"👥 {gname[:35]} | {gcount:,} نفر"
                buttons.append([InlineKeyboardButton(btn_text, callback_data=f"atk_target_{gid}")])
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
        await st.edit_text("🔍 در حال پیدا کردن گروه...")
        # اطمینان از گرم بودن کش
        try:
            async for _ in atk.app.get_dialogs(limit=2000):
                pass
        except:
            pass
        try:
            if raw.lstrip('-').isdigit():
                target_id = int(raw)
                target = await atk.app.get_chat(target_id)
            else:
                uname = raw.replace("@", "").replace("https://t.me/", "").strip()
                target = await atk.app.get_chat(uname)
                target_id = target.id
        except Exception as e:
            await st.edit_text(f"❌ گروه پیدا نشد:\n{str(e)}\nلطفا آیدی درست را وارد کنید، یا یک بار دستی آن گروه را در تلگرام باز کنید.")
            return

        prog = await st.edit_text(f"🎯 هدف: {target.title}\n🚀 در حال شروع حمله...")
        async def run():
            try:
                users = await atk.run_full_scrape(target_id)
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
            add_client = AdvancedScraper("adder_session", API_ID, API_HASH, phone=phone)
            await add_client.connect()
            sent = await add_client.app.send_code(phone)
            atk_state["add_client"] = add_client
            atk_state["hash"] = sent.phone_code_hash
            atk_state["st"] = st
            atk_state["step"] = "adder_code"
            await st.edit_text("✅ کد تایید به اکانت ارسال شد، کد ۵ رقمی را بفرست:")
        except Exception as e:
            await st.edit_text(f"❌ خطا: {str(e)}")
            atk_state.clear()

    elif step == "adder_code":
        code = m.text.strip()
        add_client = atk_state.get("add_client")
        phone = atk_state["phone"]
        h = atk_state["hash"]
        st = atk_state["st"]
        try:
            await add_client.app.sign_in(phone, h, code)
        except Exception as e:
            await m.reply_text(f"❌ خطا در کد: {str(e)}")
            return
        atk_state["step"] = "adder_target"
        await st.edit_text("✅ ورود موفق!\n🔄 در حال بارگذاری لیست گروه‌های شما...")
        # گرم کردن کش و تهیه لیست گروه ها
        add_groups = []
        try:
            async for dialog in add_client.app.get_dialogs(limit=2000):
                if dialog.chat.type in ["supergroup", "group"] or (dialog.chat.type == "channel" and getattr(dialog.chat, 'megagroup', False)):
                    try:
                        me = await add_client.app.get_chat_member(dialog.chat.id, "me")
                        if me.status in ["administrator", "creator", "member"]:
                            # برای اضافه کردن عضو باید توانایی ادد ممبر داشته باشی
                            can_add = True
                            if me.status == "administrator" and me.privileges:
                                can_add = me.privileges.can_invite_users
                            if me.status == "member":
                                # در گروه های عمومی معمولی اعضا میتونن نفر اضافه کنن
                                can_add = True
                            if can_add:
                                add_groups.append((dialog.chat.title, dialog.chat.id, dialog.chat.members_count or 0))
                    except:
                        pass
                await asyncio.sleep(0.02)
        except Exception as e:
            print(f"خطا در بارگذاری لیست گروه برای ادد: {e}", flush=True)
        atk_state["available_add_groups"] = add_groups
        if add_groups:
            buttons = []
            for gname, gid, gcount in sorted(add_groups, key=lambda x: -x[2]):
                buttons.append([InlineKeyboardButton(f"➕ {gname[:35]} | {gcount:,} نفر", callback_data=f"add_target_{gid}")])
            buttons.append([InlineKeyboardButton("✍️ وارد کردن دستی آیدی", callback_data="add_target_manual")])
            await st.edit_text(f"✅ لیست گروه‌های شما آماده است ({len(add_groups)} گروه)\nگروه مقصد را انتخاب کنید:", reply_markup=InlineKeyboardMarkup(buttons))
        else:
            await st.edit_text("✅ ورود موفق!\nآیدی عددی گروه مقصد (که میخواهید افراد را به آن اضافه کنید) را بفرستید:\n(با -100 شروع میشود)")

    elif step in ["adder_target", "adder_target_manual"]:
        raw = m.text.strip()
        add_client = atk_state["add_client"]
        st = atk_state["st"]
        # برای ادد هم مانند حمله، اول کش رو گرم کنیم
        try:
            async for _ in add_client.app.get_dialogs(limit=2000):
                pass
        except:
            pass
        try:
            if raw.lstrip('-').isdigit():
                target_gid = int(raw)
            else:
                uname = raw.replace("@", "").replace("https://t.me/", "").strip()
                chat_info = await add_client.app.get_chat(uname)
                target_gid = chat_info.id
            target = await add_client.app.get_chat(target_gid)
        except Exception as e:
            await st.edit_text(f"❌ گروه پیدا نشد: {str(e)}\nلطفا یک بار دستی با اکانت خود آن گروه را در تلگرام باز کنید و دوباره امتحان کنید.")
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
        await st.edit_text(f"✅ گروه مقصد: {target.title}\n⚠️ این اکانت حداکثر می‌تواند {remaining} نفر دیگر اضافه کند.\nحالا **فایل CSV** که از استخراج دارید را همینجا آپلود کنید.")

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
    Thread(target=run_health, daemon=True).start()
    Thread(target=keep_awake_loop, daemon=True).start()
    app.run()
