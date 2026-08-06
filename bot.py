# =================================================================
# ربات ضد اسکریپت - نسخه نهایی با انتخاب گروه داینامیک
# =================================================================
import asyncio
import sys
import os
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
_original_get_event_loop = asyncio.get_event_loop
def _patched_get_event_loop():
    return loop
asyncio.get_event_loop = _patched_get_event_loop

import io
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread

sys.path.insert(0, '.')

from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from attacker import AdvancedScraper
from defender import AdvancedDefender

# ========== کانفیگ ==========
API_ID = int(os.environ.get("API_ID", 6))
API_HASH = os.environ.get("API_HASH", "eb06d4abfb49dc3eeb1aeb98ae0f581e")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8790569799:AAFZuVDuVg62v87yQqmaQy3LS_w71-Q6yz0")
ADMIN_ID = int(os.environ.get("ADMIN_ID", 564234793))
PORT = int(os.environ.get("PORT", 10000))

app = Client("antiscraper_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, workers=1)

CURRENT_GROUP_ID = None
defender = None
atk_state = {}
bg_started = False

def main_menu():
    if not CURRENT_GROUP_ID:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("🔍 انتخاب گروه جهت محافظت و تست", callback_data="select_group")]
        ])
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 وضعیت سیستم دفاع", callback_data="status")],
        [InlineKeyboardButton("🚀 شروع تست حمله پیشرفته", callback_data="attack")],
        [InlineKeyboardButton("⚙️ فعال/غیرفعال دفاع", callback_data="toggledef")],
        [InlineKeyboardButton("🔄 تغییر گروه", callback_data="select_group")]
    ])

# ===== دستور استارت =====
@app.on_message(filters.command("start") & filters.private & filters.user(ADMIN_ID))
async def start_cmd(c, m):
    global bg_started
    if not bg_started:
        asyncio.create_task(defender.bg_scan() if defender else asyncio.sleep(0))
        bg_started = True
    try:
        await app.set_bot_commands([])
    except:
        pass
    await m.reply_text(
        "✅ ربات ضد اسکریپت 2026 با موفقیت فعال شد!\n\n"
        "لطفا یکی از گزینه ها را انتخاب کنید:",
        reply_markup=main_menu()
    )

# ===== هندلر کلیه دکمه ها =====
@app.on_callback_query(filters.user(ADMIN_ID))
async def cb(c, q):
    global CURRENT_GROUP_ID, defender, bg_started
    d = q.data

    if d == "select_group":
        groups = []
        async for dialog in app.get_dialogs():
            if dialog.chat.type in ["supergroup", "group"]:
                try:
                    mem = await app.get_chat_member(dialog.chat.id, "me")
                    if mem.status in ["administrator", "creator"]:
                        groups.append((dialog.chat.title, dialog.chat.id))
                except:
                    pass
        if not groups:
            await q.answer("ربات در هیچ گروهی ادمین نیست!", show_alert=True)
            await q.message.edit_text(
                "❌ ابتدا مرا به گروهی که میخواهید محافظت کنید اضافه کنید، تمام دسترسی های ادمین را به من بدهید، سپس دوباره به اینجا بیایید.",
                reply_markup=main_menu()
            )
            return
        buttons = []
        for name, gid in groups:
            buttons.append([InlineKeyboardButton(f"👥 {name}", callback_data=f"setg_{gid}")])
        buttons.append([InlineKeyboardButton("بازگشت", callback_data="home")])
        await q.message.edit_text("گروه مورد نظر را انتخاب کنید:", reply_markup=InlineKeyboardMarkup(buttons))
        return

    if d.startswith("setg_"):
        gid = int(d.split("_")[1])
        CURRENT_GROUP_ID = gid
        defender = AdvancedDefender(app, CURRENT_GROUP_ID, ADMIN_ID)
        if not bg_started:
            asyncio.create_task(defender.bg_scan())
            bg_started = True
        await q.answer("گروه با موفقیت انتخاب شد!", show_alert=True)
        await q.message.edit_text(f"✅ گروه انتخاب و سیستم دفاع فعال شد.", reply_markup=main_menu())
        return

    if d == "home":
        await q.message.edit_text("منوی اصلی:", reply_markup=main_menu())
        return

    if not CURRENT_GROUP_ID:
        await q.answer("اول یک گروه انتخاب کنید", show_alert=True)
        return

    if d == "status":
        try:
            chat = await app.get_chat(CURRENT_GROUP_ID)
            bot_mem = await app.get_chat_member(CURRENT_GROUP_ID, "me")
            is_adm = bot_mem.status in ["administrator", "creator"]
            text = "📊 وضعیت دفاع:\n\n"
            text += f"🛡️ دفاع: {'✅ فعال' if defender.MIN_ACCOUNT_AGE_DAYS>0 else '❌ خاموش'}\n"
            text += f"👑 ادمین: {'✅' if is_adm else '❌ دسترسی بدهید'}\n"
            text += f"🙈 لیست اعضا مخفی: {'✅' if chat.has_hidden_members else '❌ فعال کنید'}\n"
            text += f"👥 تعداد اعضا: {chat.members_count}\n"
            text += f"🚫 اسکریپت مسدود شده: {len(defender.banned_scrapers)}"
        except Exception as e:
            text = f"❌ خطا: {str(e)}"
        await q.message.edit_text(text, reply_markup=main_menu())

    elif d == "toggledef":
        defender.MIN_ACCOUNT_AGE_DAYS = 0 if defender.MIN_ACCOUNT_AGE_DAYS>0 else 25
        await q.answer("وضعیت تغییر کرد", show_alert=True)
        await q.message.edit_text("✅ وضعیت دفاع تغییر کرد", reply_markup=main_menu())

    elif d == "attack":
        atk_state.clear()
        atk_state["step"] = "phone"
        await q.message.edit_text(
            "🚀 **شبیه ساز حمله پیشرفته**\n\n"
            "شماره اکانت تست را با فرمت +989xxxxxxxxx بفرستید:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("بازگشت", callback_data="home")]])
        )

# ===== مراحل تست حمله =====
@app.on_message(filters.private & filters.user(ADMIN_ID) & filters.text & ~filters.command("start"))
async def steps(c, m):
    step = atk_state.get("step")
    if not step:
        return
    if not CURRENT_GROUP_ID:
        await m.reply_text("اول گروه را انتخاب کنید.")
        atk_state.clear()
        return

    if step == "phone":
        phone = m.text.strip()
        atk_state["phone"] = phone
        st = await m.reply_text("📡 در حال ارسال کد تایید...")
        try:
            atk = AdvancedScraper("atk_session", API_ID, API_HASH, phone=phone)
            await atk.connect()
            sent = await atk.app.send_code(phone)
            atk_state["atk"] = atk
            atk_state["hash"] = sent.phone_code_hash
            atk_state["st"] = st
            atk_state["step"] = "code"
            await st.edit_text("✅ کد به اکانت تست ارسال شد، کد ۵ رقمی را بفرستید.")
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
            await m.reply_text(f"❌ خطا: {str(e)}")
            return
        await st.edit_text("✅ ورود موفق، حمله شروع شد...")
        prog = await app.send_message(ADMIN_ID, f"🚀 حمله به گروه در حال انجام است...")
        async def run_attack():
            try:
                users = await atk.run_full_scrape(CURRENT_GROUP_ID)
                csv_bytes = atk.export_csv()
                await prog.edit_text(
                    f"✅ حمله تمام شد!\n"
                    f"تعداد کاربر استخراج شده: {len(users)} نفر\n"
                    f"بررسی کنید هشدار تشخیص اسکریپت برای شما ارسال شده؟"
                )
                await app.send_document(ADMIN_ID, io.BytesIO(csv_bytes), file_name=f"attack_{int(time.time())}.csv")
                await atk.disconnect()
            except Exception as e:
                await prog.edit_text(f"❌ خطا در حمله: {str(e)}")
            atk_state.clear()
        asyncio.create_task(run_attack())

# ===== هندلرهای گروه =====
@app.on_message(filters.new_chat_members)
async def new_mem(c, m):
    if not CURRENT_GROUP_ID or m.chat.id != CURRENT_GROUP_ID or not defender or defender.MIN_ACCOUNT_AGE_DAYS <=0:
        return
    for u in m.new_chat_members:
        if u.is_self:
            continue
        asyncio.create_task(defender.on_join(u))

@app.on_message(filters.left_chat_member)
async def left_mem(c, m):
    if not CURRENT_GROUP_ID or m.chat.id != CURRENT_GROUP_ID or not defender:
        return
    asyncio.create_task(defender.on_leave(m.left_chat_member))

@app.on_message(filters.text & filters.group)
async def mon_msg(c, m):
    if not CURRENT_GROUP_ID or m.chat.id != CURRENT_GROUP_ID or not defender or defender.MIN_ACCOUNT_AGE_DAYS <=0:
        return
    await defender.monitor_message(m)

# ===== سرور سلامت برای رندر =====
class Health(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")
    def log_message(self, *a): pass

def health_srv():
    HTTPServer(("0.0.0.0", PORT), Health).serve_forever()

if __name__ == "__main__":
    Thread(target=health_srv, daemon=True).start()
    app.run()
