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
from hunter import (
    scan_text, check_balance_of_findings, load_found, save_found,
    load_hunter_state, save_hunter_state, export_found_csv,
    start_auto_scanner
)

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


def load_added_history():
    """بارگذاری تاریخچه افرادی که به گروه ها اضافه شده اند"""
    try:
        with open(ADDED_MEMBERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def save_added_history(hist):
    with open(ADDED_MEMBERS_FILE, "w", encoding="utf-8") as f:
        json.dump(hist, f, ensure_ascii=False)

def mark_user_as_added(chat_id, chat_title, user_id):
    """ثبت کردن این کاربر که به این گروه اضافه شد"""
    hist = load_added_history()
    ckey = str(chat_id)
    if ckey not in hist:
        hist[ckey] = {"group_title": chat_title, "added_user_ids": [], "last_added_at": 0}
    if user_id not in hist[ckey]["added_user_ids"]:
        hist[ckey]["added_user_ids"].append(user_id)
    hist[ckey]["last_added_at"] = int(time.time())
    save_added_history(hist)

def is_user_already_added(chat_id, user_id):
    """چک کنه که این کاربر قبلا به این گروه اضافه شده یا نه"""
    hist = load_added_history()
    ckey = str(chat_id)
    return ckey in hist and user_id in hist[ckey].get("added_user_ids", [])


def load_accounts():
    """بارگذاری لیست اکانت های ذخیره شده"""
    try:
        with open(ACCOUNTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def save_accounts(accs):
    with open(ACCOUNTS_FILE, "w", encoding="utf-8") as f:
        json.dump(accs, f, ensure_ascii=False)

def list_saved_accounts():
    """برگرداندن لیست اکانت های معتبر که فایل سشن شان موجود است"""
    accounts = load_accounts()
    valid = {}
    for phone, info in accounts.items():
        fname = safe_phone_filename(phone)
        sfile = os.path.join(SESSIONS_DIR, f"acc_{fname}.session")
        if os.path.exists(sfile):
            valid[phone] = info
    return valid

def load_config():
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {"defend_group": None, "defense_enabled": True}

def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f)

def load_scraped():
    """بارگذاری لیست مخاطبان استخراج شده از فایل"""
    try:
        with open(SCRAPED_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("users", []), data.get("group_name", ""), data.get("group_id", 0)
    except:
        return [], "", 0

def save_scraped(users, group_name="", group_id=0):
    """ذخیره لیست استخراج شده در فایل دائمی"""
    data = {
        "users": list(users.values()) if isinstance(users, dict) else users,
        "group_name": group_name,
        "group_id": group_id,
        "saved_at": int(time.time())
    }
    with open(SCRAPED_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)

def load_adder_limits():
    """بارگذاری آمار اضافه کردن هر اکانت"""
    try:
        with open(ADDER_LIMIT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def save_adder_limits(limits):
    with open(ADDER_LIMIT_FILE, "w", encoding="utf-8") as f:
        json.dump(limits, f, ensure_ascii=False)

config = load_config()
CURRENT_GROUP_ID = config.get("defend_group")
defender = None
if CURRENT_GROUP_ID:
    defender = AdvancedDefender(app, CURRENT_GROUP_ID, ADMIN_ID)
    defender.MIN_ACCOUNT_AGE_DAYS = 25 if config.get("defense_enabled", True) else 0
atk_state = {}
bg_started = False
hunter_bg_started = False

def main_menu():
    buttons = []
    if CURRENT_GROUP_ID:
        buttons.append([InlineKeyboardButton("📊 وضعیت دفاع", callback_data="status")])
        buttons.append([InlineKeyboardButton("⚙️ فعال/غیرفعال دفاع", callback_data="toggledef")])
        buttons.append([InlineKeyboardButton("🔄 تغییر گروه محافظت شده", callback_data="select_group")])
    else:
        buttons.append([InlineKeyboardButton("🔍 انتخاب گروه برای محافظت", callback_data="select_group")])
    saved_accs = list_saved_accounts()
    acc_count = len(saved_accs)
    buttons.append([InlineKeyboardButton("🚀 تست حمله پیشرفته", callback_data="pick_account_attack")])
    buttons.append([InlineKeyboardButton("➕ تست اضافه کردن اعضا به گروه", callback_data="pick_account_add")])
    buttons.append([InlineKeyboardButton("📋 لیست مخاطبان استخراج شده", callback_data="show_list_0")])
    buttons.append([InlineKeyboardButton("📈 آمار اکانت‌های اضافه کننده", callback_data="adder_stats")])
    add_hist = load_added_history()
    total_added = sum(len(g.get("added_user_ids", [])) for g in add_hist.values())
    buttons.append([InlineKeyboardButton(f"✅ تاریخچه اعضای اضافه شده ({total_added})", callback_data="added_history_menu")])
    # --- شکارچی گنج ---
    found_list = load_found()
    hstate = load_hunter_state()
    hunter_status = "🟢" if hstate.get("running") else "🔴"
    buttons.append([InlineKeyboardButton(f"{hunter_status} 🕵️ شکارچی کیف پول ({len(found_list)})", callback_data="hunter_menu")])
    buttons.append([InlineKeyboardButton(f"📱 مدیریت اکانت‌های من ({acc_count})", callback_data="manage_accounts")])
    return InlineKeyboardMarkup(buttons)

@app.on_message(filters.command("start") & filters.private & filters.user(ADMIN_ID))
async def start_cmd(c, m):
    global bg_started, hunter_bg_started
    if defender and not bg_started:
        asyncio.create_task(defender.bg_scan())
        bg_started = True
    # Start the crypto hunter 24/7 scanner once
    if not hunter_bg_started:
        start_auto_scanner(app, ADMIN_ID)
        hunter_bg_started = True
    try:
        await app.set_bot_commands([])
    except:
        pass
    welcome = "✅ ربات ضد اسکریپت آماده است!\n\n"
    if CURRENT_GROUP_ID:
        welcome += "🛡️ سیستم دفاع فعال است.\n"
    users, gname, _ = load_scraped()
    if users:
        welcome += f"📋 {len(users)} مخاطب استخراج شده در حافظه ذخیره شده.\n"
    found_list = load_found()
    if found_list:
        welcome += f"💰 شکارچی: {len(found_list)} مورد پیدا شده.\n"
    await m.reply_text(welcome, reply_markup=main_menu())

@app.on_callback_query(filters.user(ADMIN_ID))
async def cb(c, q):
    global CURRENT_GROUP_ID, defender, bg_started, config
    d = q.data

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

    if d == "home":
        await q.message.edit_text("منوی اصلی:", reply_markup=main_menu())
        return

    if d == "status" and CURRENT_GROUP_ID:
        try:
            chat = await app.get_chat(CURRENT_GROUP_ID)
            bot_mem = await app.get_chat_member(CURRENT_GROUP_ID, "me")
            is_adm = bot_mem.status in ["administrator", "creator"]
            text = "📊 وضعیت:\n\n"
            text += f"🛡️ دفاع: {'✅ روشن' if defender.MIN_ACCOUNT_AGE_DAYS>0 else '❌ خاموش'}\n"
            text += f"👑 ادمین: {'✅' if is_adm else '❌'}\n"
            text += f"🙈 لیست اعضا مخفی: {'✅' if chat.has_hidden_members else '❌ لطفا فعال کنید'}\n"
            text += f"👥 اعضا: {chat.members_count}\n"
            text += f"🚫 مسدود شده: {len(defender.banned_scrapers)}"
        except Exception as e:
            text = f"❌ خطا: {str(e)}"
        await q.message.edit_text(text, reply_markup=main_menu())
        return

    if d == "toggledef" and defender:
        defender.MIN_ACCOUNT_AGE_DAYS = 0 if defender.MIN_ACCOUNT_AGE_DAYS>0 else 25
        config["defense_enabled"] = defender.MIN_ACCOUNT_AGE_DAYS >0
        save_config(config)
        await q.answer("تغییر کرد", show_alert=True)
        await q.message.edit_text("✅ وضعیت تغییر کرد", reply_markup=main_menu())
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
        add_hist = load_added_history()
        all_added_ids = set()
        for ginfo in add_hist.values():
            all_added_ids.update(ginfo.get("added_user_ids", []))
        added_in_list = sum(1 for u in users if u.get("user_id") in all_added_ids)
        text = f"📋 **لیست مخاطبان استخراج شده**\n"
        if gname:
            text += f"👥 گروه: {gname}\n"
        text += f"🔢 تعداد کل: {total} نفر\n"
        text += f"✅ تا کنون ادد شده: {added_in_list} نفر\n"
        text += f"📄 صفحه {page+1} از {total_pages}\n\n"
        for i, u in enumerate(chunk, start=start+1):
            name = u.get("first_name","") or "بدون نام"
            if u.get("last_name"):
                name += " " + u["last_name"]
            uname = f"@{u['username']}" if u.get("username") else "(بدون یوزرنیم)"
            uid = u.get("user_id", "?")
            prem = "⭐" if u.get("is_premium") == "بله" else ""
            added = "✅" if uid in all_added_ids else ""
            src = u.get("source", "")
            text += f"{i}. {added}{prem}{name}\n   └ {uname} | `{uid}`\n   └ منبع: {src}\n"
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
        nav_buttons.append([InlineKeyboardButton("🔙 بازگشت به منو", callback_data="home")])
        await q.message.edit_text(text, reply_markup=InlineKeyboardMarkup(nav_buttons), disable_web_page_preview=True)
        return

    # ==================== تاریخچه اعضای اضافه شده ====================
    if d == "added_history_menu":
        hist = load_added_history()
        text = f"✅ **تاریخچه اعضای اضافه شده**\n\n"
        total_all = sum(len(g.get("added_user_ids", [])) for g in hist.values())
        text += f"🔢 مجموع کل ادد شده ها: {total_all} نفر\n\n"
        if not hist:
            text += "هنوز هیچ کس به هیچ گروهی اضافه نشده."
        else:
            for gid, ginfo in hist.items():
                cnt = len(ginfo.get("added_user_ids", []))
                title = ginfo.get("group_title", "گروه ناشناخته")
                last = ginfo.get("last_added_at", 0)
                date_str = time.strftime("%Y-%m-%d %H:%M", time.localtime(last)) if last else "-"
                text += f"👥 {title}\n   └ تعداد ادد شده: {cnt} نفر\n   └ آخرین ادد: {date_str}\n\n"
        buttons = []
        for gid in hist:
            buttons.append([InlineKeyboardButton(f"👁️ مشاهده لیست: {hist[gid].get('group_title','?')[:25]}", callback_data=f"view_added_{gid}_0")])
        buttons.append([InlineKeyboardButton("🗑️ پاک کردن تاریخچه تکراری برای یک گروه", callback_data="clear_added_pick")])
        buttons.append([InlineKeyboardButton("🔙 بازگشت به منو", callback_data="home")])
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
        text = f"📈 **آمار اکانت‌های اضافه کننده**\n\n"
        text += f"🚨 سقف مجاز هر اکانت: **{MAX_ADD_PER_ACCOUNT} نفر**\n\n"
        if not limits:
            text += "هنوز هیچ اکانت برای اضافه کردن استفاده نشده."
        else:
            for phone, info in limits.items():
                count = info.get("added", 0)
                remaining = MAX_ADD_PER_ACCOUNT - count
                status = "✅ سالم" if remaining > 0 else "⚠️ به سقف رسید"
                last_use = info.get("last_used", 0)
                last_str = time.strftime("%Y-%m-%d %H:%M", time.localtime(last_use)) if last_use else "-"
                bar_len = 10
                filled = int(bar_len * min(count, MAX_ADD_PER_ACCOUNT) / MAX_ADD_PER_ACCOUNT)
                bar = "█" * filled + "░" * (bar_len - filled)
                text += f"📱 {phone}\n"
                text += f"   {bar} {count}/{MAX_ADD_PER_ACCOUNT}\n"
                text += f"   وضعیت: {status}\n"
                text += f"   آخرین استفاده: {last_str}\n\n"
        buttons = [[InlineKeyboardButton("🔄 ریست آمار یک اکانت", callback_data="reset_adder_pick")]]
        buttons.append([InlineKeyboardButton("🗑️ ریست کامل همه آمار", callback_data="reset_adder_all")])
        buttons.append([InlineKeyboardButton("🔙 بازگشت", callback_data="home")])
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

    # ==================== شکارچی گنج ====================
    if d == "hunter_menu":
        found = load_found()
        hs = load_hunter_state()
        total_with_balance = sum(1 for f in found if (f.get("balance",0) or 0) > 0.0001)
        total_val = sum((f.get("balance",0) or 0) for f in found)
        total_games = sum(1 for f in found if f.get("type") == "game_account")
        text = f"🕵️ <b>شکارچی حرفه‌ای کیف پول</b>\n\n"
        text += f"🟢 وضعیت: {'روشن و در حال کار' if hs.get('running') else 'خاموش'}\n"
        text += f"🔄 تعداد بررسی: {hs.get('checked',0)} دور\n"
        text += f"📂 گیست اسکن شده: {hs.get('scanned_gists',0)}\n"
        text += f"💎 کیف پول با موجودی پیدا شده: {total_with_balance}\n"
        text += f"🎮 کمبو اکانت/بازی پیدا شده: {total_games}\n\n"
        text += "⚙️ تنظیمات:\n"
        text += "• فقط داده‌های آخر ۲ سال اسکن میشوند\n"
        text += "• فقط seed و کلید خصوصی WIF بررسی میشوند (آدرس‌های عمومی نادیده گرفته میشوند)\n"
        text += "• موجودی کمتر از ۰.۰۰۰۱ کوین گزارش نمی‌شود\n"
        text += "• کمبوهای اکانت/بازی با نام سرویس برچسب‌گذاری میشوند\n"
        text += "• در صورت پیدا شدن فورا به شما اطلاع داده میشود"
        buttons = [
            [InlineKeyboardButton("💰 لیست کیف پول‌های با موجودی", callback_data="hunter_list")],
            [InlineKeyboardButton(f"🎮 لیست اکانت‌های بازی/کمبو ({total_games})", callback_data="hunter_games")],
            [InlineKeyboardButton("🔍 اسکن متن/فایل دلخواه", callback_data="hunter_scan_text")],
            [InlineKeyboardButton("🗑️ پاک کردن لیست پیدا شده", callback_data="hunter_clear")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="home")]
        ]
        await q.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
        return

    if d == "hunter_list":
        found = load_found()
        found_with_money = [f for f in found if (f.get("balance",0) or 0) > 0.0001]
        if not found_with_money:
            await q.answer("هنوز هیچ کیف پولی با موجودی واقعی پیدا نشده است. اسکن در حال اجراست...", show_alert=True)
            return
        text = f"💰 <b>{len(found_with_money)} کیف پول با موجودی واقعی:</b>\n\n"
        for i, item in enumerate(found_with_money[:20], 1):
            bal = item.get("balance",0) or 0
            coin = item.get("coin","")
            t = item["type"]
            val = item["value"][:50] + ("..." if len(item["value"])>50 else "")
            text += f"{i}. 💎 <b>{bal:.8f} {coin}</b>\n"
            text += f"   └ {t}\n"
            text += f"   └ <code>{val}</code>\n\n"
        if len(found_with_money) > 20:
            text += f"... و {len(found_with_money)-20} مورد دیگر"
        buttons = [[InlineKeyboardButton("🔙 بازگشت", callback_data="hunter_menu")]]
        await q.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
        # CSV
        csv_bytes = export_found_csv(found)
        await app.send_document(ADMIN_ID, io.BytesIO(csv_bytes), file_name=f"wallets_with_balance_{int(time.time())}.csv", caption=f"📥 لیست کامل {len(found)} مورد (فقط {len(found_with_money)} مورد موجودی دارند)")
        return

    if d == "hunter_games":
        found = load_found()
        games = [f for f in found if f.get("type") == "game_account"]
        # Aggregate by service
        svc_counter = {}
        for f in games:
            s = f.get("service", "❓نامشخص") or "❓نامشخص"
            svc_counter[s] = svc_counter.get(s, 0) + 1
        if not games:
            await q.answer("هنوز هیچ کمبوی بازی/سرویسی پیدا نشده است.", show_alert=True)
            return
        text = f"🎮 <b>{len(games)} کمبو اکانت بازی/سرویس</b>\n\n"
        text += "<b>📊 آمار به تفکیک سرویس:</b>\n"
        for svc, cnt in sorted(svc_counter.items(), key=lambda x: -x[1])[:15]:
            text += f"  • {svc}: <b>{cnt}</b>\n"
        text += "\n<b>🕐 آخرین ۱۵ مورد:</b>\n"
        for i, item in enumerate(games[-15:][::-1], 1):
            svc = item.get("service", "❓")
            src = item.get("source", "")
            v = item["value"]
            if len(v) > 45: v = v[:45] + "…"
            src_str = f" ({src})" if src else ""
            text += f"\n{i}. 🏷️ {svc}{src_str}\n   <code>{v}</code>"
        buttons = [[InlineKeyboardButton("🔙 بازگشت", callback_data="hunter_menu")]]
        await q.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
        # Also send CSV of just game accounts
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["service","email:password","source","timestamp"])
        for f in games:
            w.writerow([f.get("service",""), f.get("value",""), f.get("source",""), f.get("ts","")])
        await app.send_document(ADMIN_ID, _io.BytesIO(buf.getvalue().encode("utf-8-sig")),
                                file_name=f"game_accounts_{int(time.time())}.csv",
                                caption=f"📥 لیست کامل {len(games)} اکانت/کمبو به صورت CSV")
        return

    if d == "hunter_scan_text":
        atk_state["hunter_step"] = "await_text"
        await q.message.edit_text("🔍 لطفا متنی که می‌خواهی در آن دنبال کیف پول یا اکانت بازی بگردی را بفرست.\nهمچنین می‌توانی فایل متنی .txt/.csv را آپلود کنی.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="hunter_menu")]]))
        await q.answer()
        return

    if d == "hunter_clear":
        save_found([])
        await q.answer("لیست پاک شد، اسکن دوباره از نو ادامه پیدا میکند.", show_alert=True)
        await q.message.edit_text("✅ لیست کیف پول‌ها پاک شد.", reply_markup=main_menu())
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
        text = f"📱 **اکانت های ذخیره شده شما** ({len(accounts)} اکانت)\n\n"
        if not accounts:
            text += "⚠️ هنوز هیچ اکانتی به صورت دائمی ذخیره نشده.\nوقتی اولین بار لاگین کنی خودکار ذخیره میشه."
        else:
            for phone, info in accounts.items():
                added_count = load_adder_limits().get(phone, {}).get("added", 0)
                name = info.get("name", phone)
                added_at = info.get("added_at", 0)
                date_str = time.strftime("%Y-%m-%d", time.localtime(added_at)) if added_at else "-"
                text += f"🔹 {name}\n   📱 {phone}\n   📅 اضافه شده: {date_str}\n   ➕ تا کنون {added_count} نفر اد کرده\n\n"
        text += "\n💡 نکته: سشن‌ها روی سرور ذخیره دائمی هستند و فقط برای استفاده خودت هست."
        buttons = []
        if accounts:
            buttons.append([InlineKeyboardButton("🗑️ حذف یک اکانت", callback_data="acc_delete_pick")])
            for phone in accounts:
                pass
        buttons.append([InlineKeyboardButton("➕ افزودن اکانت جدید", callback_data="add_new_account")])
        buttons.append([InlineKeyboardButton("📤 دانلود فایل سشن (بک آپ)", callback_data="acc_backup_pick")])
        buttons.append([InlineKeyboardButton("🔙 بازگشت به منو", callback_data="home")])
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

    # ========== Hunter manual scan ==========
    if hstep == "await_text":
        text = ""
        if m.document:
            status = await m.reply_text("📥 در حال دانلود و خواندن فایل...")
            try:
                file = await app.download_media(m.document, in_memory=True)
                text = file.getvalue().decode("utf-8-sig", errors="ignore")
            except Exception as e:
                await status.edit_text(f"❌ خطا در خواندن فایل: {str(e)}")
                atk_state["hunter_step"] = None
                return
        else:
            text = m.text or ""
            status = await m.reply_text("🔍 در حال اسکن...")
        if not text.strip():
            await status.edit_text("❌ متن خالی است.")
            atk_state["hunter_step"] = None
            return
        findings = scan_text(text, source="manual")
        wallets = [f for f in findings if f["type"] in ("seed_phrase","btc_wif")]
        games = [f for f in findings if f["type"] == "game_account"]
        await status.edit_text(f"✅ تشخیص داده شد:\n💰 {len(wallets)} کیف پول/seed\n🎮 {len(games)} اکانت/کمبو\n⏳ در حال بررسی موجودی آنلاین...")
        wallets_checked = check_balance_of_findings(wallets)
        # Save new findings
        existing = load_found()
        seen = set((f["type"], f["value"]) for f in existing)
        new_wallets = 0
        new_games = 0
        total_money = 0
        for f in wallets_checked + games:
            k = (f["type"], f["value"])
            if k not in seen:
                existing.append(f)
                seen.add(k)
                if f["type"] == "game_account":
                    new_games += 1
                else:
                    new_wallets += 1
                    total_money += f.get("balance",0) or 0
        save_found(existing)
        msg = f"✅ اسکن کامل شد!\n\n💎 کیف پول/seed جدید: {new_wallets}\n🎮 اکانت بازی/کمبو جدید: {new_games}\n💰 مجموع موجودی پیدا شده: {total_money:.8f}"
        if wallets_checked:
            msg += "\n\n<b>نمونه کیف پول ها:</b>"
            for f in wallets_checked[:5]:
                bal = f.get("balance",0) or 0
                if bal > 0.0001:
                    msg += f"\n🚨 {bal:.6f} {f.get('coin','')} - {f['value'][:50]}"
        if games:
            # Aggregate by service
            svc_count = {}
            for f in games:
                s = f.get("service", "❓نامشخص")
                svc_count[s] = svc_count.get(s, 0) + 1
            top = sorted(svc_count.items(), key=lambda x: -x[1])[:5]
            msg += f"\n\n🎮 {len(games)} کمبو پیدا شد:\n<b>تقسیم‌بندی:</b> " + " | ".join(f"{s}×{c}" for s,c in top)
            msg += f"\n\n<b>نمونه:</b>"
            for f in games[:10]:
                svc = f.get("service", "❓")
                v = f["value"]
                if len(v) > 55: v = v[:55] + "…"
                msg += f"\n🏷️ {svc}\n   <code>{v}</code>"
        atk_state["hunter_step"] = None
        await status.edit_text(msg, reply_markup=main_menu())
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
        atk_state.clear()
        await st.edit_text(f"✅ اکانت {me.first_name} با موفقیت به صورت دائمی ذخیره شد!\n✅ شناسه دستگاه هم ثابت ذخیره شد (دیگه انقضا نمی‌خوره)\nاز این به بعد بدون نیاز به کد می‌توانی ازش استفاده کنی.", reply_markup=main_menu())
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
        atk_state.clear()
        await st.edit_text(f"✅ اکانت {me.first_name} با موفقیت ذخیره شد!", reply_markup=main_menu())
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
        atk_state.clear()
        await st.edit_text("✅ اکانت ذخیره شد! /start بزن.", reply_markup=main_menu())
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
