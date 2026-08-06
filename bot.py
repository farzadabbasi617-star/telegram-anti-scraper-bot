# =================================================================
# ربات ضد اسکریپت - نسخه نهایی قطعی
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
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread

sys.path.insert(0, '.')

from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from attacker import AdvancedScraper
from defender import AdvancedDefender

API_ID = int(os.environ.get("API_ID", 6))
API_HASH = os.environ.get("API_HASH", "eb06d4abfb49dc3eeb1aeb98ae0f581e")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8790569799:AAFZuVDuVg62v87yQqmaQy3LS_w71-Q6yz0")
ADMIN_ID = int(os.environ.get("ADMIN_ID", 564234793))
PORT = int(os.environ.get("PORT", 10000))
CONFIG_FILE = "config.json"
SCRAPED_FILE = "scraped_users.json"
ADDER_LIMIT_FILE = "adder_limits.json"
MAX_ADD_PER_ACCOUNT = 50  # محدودیت اضافه کردن عضو در هر اکانت

app = Client("antiscraper_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, workers=1)

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

def main_menu():
    buttons = []
    if CURRENT_GROUP_ID:
        buttons.append([InlineKeyboardButton("📊 وضعیت دفاع", callback_data="status")])
        buttons.append([InlineKeyboardButton("⚙️ فعال/غیرفعال دفاع", callback_data="toggledef")])
        buttons.append([InlineKeyboardButton("🔄 تغییر گروه محافظت شده", callback_data="select_group")])
    else:
        buttons.append([InlineKeyboardButton("🔍 انتخاب گروه برای محافظت", callback_data="select_group")])
    buttons.append([InlineKeyboardButton("🚀 تست حمله پیشرفته", callback_data="attack")])
    buttons.append([InlineKeyboardButton("➕ تست اضافه کردن اعضا به گروه", callback_data="add_members")])
    buttons.append([InlineKeyboardButton("📋 لیست مخاطبان استخراج شده", callback_data="show_list_0")])
    buttons.append([InlineKeyboardButton("📈 آمار اکانت‌های اضافه کننده", callback_data="adder_stats")])
    return InlineKeyboardMarkup(buttons)

@app.on_message(filters.command("start") & filters.private & filters.user(ADMIN_ID))
async def start_cmd(c, m):
    global bg_started
    if defender and not bg_started:
        asyncio.create_task(defender.bg_scan())
        bg_started = True
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
        text = f"📋 **لیست مخاطبان استخراج شده**\n"
        if gname:
            text += f"👥 گروه: {gname}\n"
        text += f"🔢 تعداد کل: {total} نفر\n"
        text += f"📄 صفحه {page+1} از {total_pages}\n\n"
        for i, u in enumerate(chunk, start=start+1):
            name = u.get("first_name","") or "بدون نام"
            if u.get("last_name"):
                name += " " + u["last_name"]
            uname = f"@{u['username']}" if u.get("username") else "(بدون یوزرنیم)"
            uid = u.get("user_id", "?")
            prem = "⭐" if u.get("is_premium") == "بله" else ""
            src = u.get("source", "")
            text += f"{i}. {prem}{name}\n   └ {uname} | `{uid}`\n   └ منبع: {src}\n"
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

    if d == "attack":
        atk_state.clear()
        atk_state["step"] = "phone"
        await q.message.edit_text("🚀 تست حمله\n\nشماره اکانت تست با فرمت +98 بفرست:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("بازگشت", callback_data="home")]]))
        return

    if d == "add_members":
        atk_state.clear()
        limits = load_adder_limits()
        # چک کن از قبل به حد نرسیده
        atk_state["step"] = "adder_phone"
        warn = ""
        if limits:
            reached = [p for p,info in limits.items() if info.get("added",0) >= MAX_ADD_PER_ACCOUNT]
            if reached:
                warn = f"⚠️ {len(reached)} اکانت قبلا به سقف {MAX_ADD_PER_ACCOUNT} نفر رسیده‌اند، از شماره جدید استفاده کنید.\n\n"
        await q.message.edit_text(f"➕ **اضافه کردن اعضا از فایل CSV**\n\n{warn}⚠️ از اکانت تست استفاده کنید. سقف مجاز هر اکانت: {MAX_ADD_PER_ACCOUNT} نفر.\nشماره اکانت را با فرمت +98 بفرستید:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("بازگشت", callback_data="home")]]))
        return

@app.on_message(filters.private & filters.user(ADMIN_ID) & (filters.text | filters.document) & ~filters.command("start"))
async def steps(c, m):
    step = atk_state.get("step")
    if not step: return

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
        phone = atk_state["phone"]
        target_id = None
        target = None
        await st.edit_text("🔍 در حال پیدا کردن گروه...")
        try:
            if raw.lstrip('-').isdigit():
                target_id = int(raw)
                target = await atk.app.get_chat(target_id)
            else:
                uname = raw.replace("@", "").replace("https://t.me/", "").strip()
                target = await atk.app.get_chat(uname)
                target_id = target.id
            try:
                await atk.app.get_chat_member(target_id, "me")
            except:
                await st.edit_text("❌ اکانت تست عضو این گروه نیست! اول عضو شو دوباره امتحان کن.")
                atk_state.clear()
                return
        except Exception as e:
            await st.edit_text(f"❌ گروه پیدا نشد یا عضو نیستید:\n{str(e)}\nلطفا آیدی درست را وارد کنید.")
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
        await st.edit_text("✅ ورود موفق!\nآیدی عددی گروه مقصد (که میخواهید افراد را به آن اضافه کنید) را بفرستید:\n(با -100 شروع میشود)")

    elif step == "adder_target":
        raw = m.text.strip()
        add_client = atk_state["add_client"]
        st = atk_state["st"]
        try:
            target_gid = int(raw)
            target = await add_client.app.get_chat(target_gid)
        except Exception as e:
            await st.edit_text(f"❌ گروه پیدا نشد: {str(e)}")
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
            user_ids = []
            for row in reader:
                if "user_id" in row and str(row["user_id"]).lstrip('-').isdigit():
                    user_ids.append(int(row["user_id"]))
            added = 0
            errors = 0
            skipped_due_to_limit = 0
            remaining_slots = MAX_ADD_PER_ACCOUNT - already
            prog = await app.send_message(ADMIN_ID, f"شروع اضافه کردن...\nسقف اکانت: {MAX_ADD_PER_ACCOUNT}\nقبلا اضافه شده: {already}\nظرفیت باقیمانده: {remaining_slots}\nتعداد افراد در فایل: {len(user_ids)}")
            for uid in user_ids:
                # چک محدودیت قبل از هر اضافه کردن
                total_for_account = already + added
                if total_for_account >= MAX_ADD_PER_ACCOUNT:
                    skipped_due_to_limit = len(user_ids) - (added + errors)
                    await prog.edit_text(f"⚠️ به سقف {MAX_ADD_PER_ACCOUNT} نفر در این اکانت رسیدیم!\nادامه متوقف شد.\n\nموفق: {added}\nناموفق: {errors}\nباقیمانده در فایل (اضافه نشد): {skipped_due_to_limit}")
                    break
                try:
                    await add_client.app.add_chat_members(target_gid, uid)
                    added +=1
                    # ذخیره فوری آمار بعد از هر اضافه کردن موفق
                    limits = load_adder_limits()
                    limits[phone] = {
                        "added": already + added,
                        "last_used": int(time.time())
                    }
                    save_adder_limits(limits)
                    await asyncio.sleep(random.randint(8,15))
                    if added %5 ==0:
                        await prog.edit_text(f"در حال اضافه کردن...\nموفق: {added}\nناموفق: {errors}\nمحدودیت اکانت: {already+added}/{MAX_ADD_PER_ACCOUNT}\nباقیمانده: {len(user_ids) - added - errors}")
                except Exception as e:
                    errors +=1
                    await asyncio.sleep(2)
            else:
                # اگر به انتها رسیدیم بدون break
                await prog.edit_text(f"✅ اضافه کردن تمام شد!\nموفق: {added} نفر\nناموفق: {errors} نفر\nکل اضافه شده با این اکانت: {already+added}/{MAX_ADD_PER_ACCOUNT}")
            await add_client.disconnect()
        except Exception as e:
            await st.edit_text(f"❌ خطا در اضافه کردن: {str(e)}")
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
        self.end_headers()
        self.wfile.write(b"OK")
    def log_message(self, *a): pass

def run_health():
    HTTPServer(("0.0.0.0", PORT), Health).serve_forever()

if __name__ == "__main__":
    Thread(target=run_health, daemon=True).start()
    app.run()
