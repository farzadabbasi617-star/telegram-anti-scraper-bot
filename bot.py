# =================================================================
# رفع قطعی مشکل event loop - اولین خط کد!
# =================================================================
import asyncio
import sys
import os
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
# Monkey-patch get_event_loop تا همیشه لوپ ما رو برگردونه
_original_get_event_loop = asyncio.get_event_loop
def _patched_get_event_loop():
    return loop
asyncio.get_event_loop = _patched_get_event_loop

# =================================================================
# بقیه ایمپورت ها الان پایین
# =================================================================
import io
import time
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
GROUP_ID = int(os.environ.get("GROUP_ID", -1001572861284))
PORT = int(os.environ.get("PORT", 10000))

app = Client(
    "antiscraper_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    workers=1
)

defender = AdvancedDefender(app, GROUP_ID, ADMIN_ID)
atk_state = {}
bg_started = False

def menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 وضعیت سیستم دفاع", callback_data="status")],
        [InlineKeyboardButton("🚀 شروع تست حمله پیشرفته", callback_data="attack")],
        [InlineKeyboardButton("⚙️ فعال/غیرفعال دفاع", callback_data="toggledef")]
    ])

@app.on_message(filters.command("start") & filters.private & filters.user(ADMIN_ID))
async def start_cmd(c, m):
    global bg_started
    if not bg_started:
        asyncio.create_task(defender.bg_scan())
        bg_started = True
    try:
        await app.set_bot_commands([])
    except:
        pass
    await m.reply_text(
        "✅ ربات ضد اسکریپت فعال شد!\n\n"
        "🤖 **پنل کنترل دفاع و تست حمله**\n"
        "نسخه نهایی 2026\n\n"
        "یک گزینه انتخاب کنید:",
        reply_markup=menu()
    )

@app.on_callback_query(filters.user(ADMIN_ID))
async def cb(c, q):
    d = q.data
    if d == "status":
        try:
            chat = await app.get_chat(GROUP_ID)
            bot_mem = await app.get_chat_member(GROUP_ID, "me")
            is_adm = bot_mem.status in ["administrator", "creator"]
            text = "📊 گزارش وضعیت:\n\n"
            text += f"🛡️ دفاع: {'✅ فعال' if defender.MIN_ACCOUNT_AGE_DAYS > 0 else '❌ غیرفعال'}\n"
            text += f"👑 ادمین: {'✅' if is_adm else '❌ مرا ادمین کنید'}\n"
            text += f"🙈 لیست مخفی: {'✅' if chat.has_hidden_members else '❌ فعال کنید'}\n"
            text += f"👥 اعضا: {chat.members_count}\n"
            text += f"🚫 مسدود شده: {len(defender.banned_scrapers)}"
        except Exception as e:
            text = f"❌ خطا: {str(e)}"
        await q.message.edit_text(text, reply_markup=menu())
    elif d == "toggledef":
        defender.MIN_ACCOUNT_AGE_DAYS = 0 if defender.MIN_ACCOUNT_AGE_DAYS > 0 else 25
        await q.answer("تغییر کرد", show_alert=True)
        await q.message.edit_text("✅ وضعیت تغییر کرد", reply_markup=menu())
    elif d == "attack":
        atk_state.clear()
        atk_state["step"] = "phone"
        await q.message.edit_text("🚀 تست حمله\nشماره اکانت تست را با +98 بفرستید:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("انصراف", callback_data="back")]]))
    elif d == "back":
        atk_state.clear()
        await q.message.edit_text("منو اصلی", reply_markup=menu())

@app.on_message(filters.private & filters.user(ADMIN_ID) & filters.text & ~filters.command("start"))
async def attack_steps(c, m):
    step = atk_state.get("step")
    if not step: return
    if step == "phone":
        phone = m.text.strip()
        atk_state["phone"] = phone
        st = await m.reply_text("📡 در حال ارسال کد...")
        try:
            atk = AdvancedScraper("atk", API_ID, API_HASH, phone=phone)
            await atk.connect()
            sent = await atk.app.send_code(phone)
            atk_state["atk"] = atk
            atk_state["hash"] = sent.phone_code_hash
            atk_state["st"] = st
            atk_state["step"] = "code"
            await st.edit_text("✅ کد ارسال شد، کد ۵ رقمی را بفرستید.")
        except Exception as e:
            await st.edit_text(f"❌ خطا: {e}")
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
            await m.reply_text(f"❌ خطا: {e}")
            return
        await st.edit_text("✅ ورود موفق، حمله شروع شد...")
        prog = await app.send_message(ADMIN_ID, "🚀 حمله در حال اجرا...")
        async def run():
            try:
                users = await atk.run_full_scrape(GROUP_ID)
                csvb = atk.export_csv()
                await prog.edit_text(f"✅ حمله تمام شد\nتعداد استخراج: {len(users)}")
                await app.send_document(ADMIN_ID, io.BytesIO(csvb), file_name=f"attack_{int(time.time())}.csv")
                await atk.disconnect()
            except Exception as e:
                await prog.edit_text(f"❌ خطا: {e}")
            atk_state.clear()
        asyncio.create_task(run())

@app.on_message(filters.new_chat_members & filters.chat(GROUP_ID))
async def newmem(c, m):
    if defender.MIN_ACCOUNT_AGE_DAYS <=0: return
    for u in m.new_chat_members:
        if u.is_self: continue
        asyncio.create_task(defender.on_join(u))

@app.on_message(filters.left_chat_member & filters.chat(GROUP_ID))
async def leftmem(c, m):
    asyncio.create_task(defender.on_leave(m.left_chat_member))

@app.on_message(filters.chat(GROUP_ID) & filters.text)
async def mon(c, m):
    if defender.MIN_ACCOUNT_AGE_DAYS <=0: return
    await defender.monitor_message(m)

class HealthCheck(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")
    def log_message(self, *args): pass

def run_health():
    HTTPServer(("0.0.0.0", PORT), HealthCheck).serve_forever()

if __name__ == "__main__":
    Thread(target=run_health, daemon=True).start()
    app.run()
