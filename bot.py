# =================================================================
# ربات ضد اسکریپت - نسخه دپلوی دائمی روی رندر
# =================================================================
import os
import sys
import asyncio
import io
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread

# اضافه کردن مسیر فعلی
sys.path.insert(0, '.')

from pyrogram import Client, filters, idle
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from attacker import AdvancedScraper
from defender import AdvancedDefender

# ========== کانفیگ ==========
API_ID = int(os.environ.get("API_ID", 6))
API_HASH = os.environ.get("API_HASH", "eb06d4abfb49dc3eeb1aeb98ae0f581e")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8790569799:AAFZuVDuVg62v87yQqmaQy3LS_w71-Q6yz0")
ADMIN_ID = int(os.environ.get("ADMIN_ID", 564234793))
GROUP_ID = int(os.environ.get("GROUP_ID", -1001572861284))

# ساخت کلاینت ربات
app = Client(
    "antiscraper_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
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

# ===== دستور استارت =====
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
        "✅ ربات ضد اسکریپت با موفقیت روی سرور فعال شد!\n\n"
        "🤖 **پنل کنترل دفاع و تست حمله**\n"
        "نسخه نهایی 2026\n\n"
        "یکی از گزینه ها را انتخاب کنید:",
        reply_markup=menu()
    )

# ===== هندلر دکمه ها =====
@app.on_callback_query(filters.user(ADMIN_ID))
async def cb(c, q):
    d = q.data
    if d == "status":
        try:
            chat = await app.get_chat(GROUP_ID)
            bot_mem = await app.get_chat_member(GROUP_ID, "me")
            is_adm = bot_mem.status in ["administrator", "creator"]
            text = "📊 گزارش وضعیت دفاع:\n\n"
            text += f"🛡️ سیستم دفاع: {'✅ فعال' if defender.MIN_ACCOUNT_AGE_DAYS > 0 else '❌ غیرفعال'}\n"
            text += f"👑 من در گروه ادمین هستم: {'✅' if is_adm else '❌ لطفا مرا ادمین کنید'}\n"
            text += f"🙈 لیست اعضا مخفی است: {'✅' if chat.has_hidden_members else '❌ در تنظیمات فعال کنید'}\n"
            text += f"👥 تعداد اعضای گروه: {chat.members_count}\n"
            text += f"🚫 تعداد اسکریپت مسدود شده: {len(defender.banned_scrapers)}"
        except Exception as e:
            text = f"❌ خطا در اتصال به گروه:\n{str(e)}\n\nآیا مرا به گروه اضافه کردید؟"
        await q.message.edit_text(text, reply_markup=menu())
    elif d == "toggledef":
        defender.MIN_ACCOUNT_AGE_DAYS = 0 if defender.MIN_ACCOUNT_AGE_DAYS > 0 else 25
        await q.answer("وضعیت تغییر کرد", show_alert=True)
        await q.message.edit_text("✅ وضعیت سیستم دفاع تغییر کرد.", reply_markup=menu())
    elif d == "attack":
        atk_state.clear()
        atk_state["step"] = "phone"
        await q.message.edit_text(
            "🚀 **پنل تست حمله پیشرفته**\n\n"
            "این سیستم با تمام تکنیک های جدید اسکرپرهای پولی به گروه شما حمله میکند.\n\n"
            "شماره تلفن اکانت تست را با فرمت `+989xxxxxxxxx` ارسال کنید:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ انصراف", callback_data="back")]])
        )
    elif d == "back":
        atk_state.clear()
        await q.message.edit_text("🏠 منوی اصلی", reply_markup=menu())

# ===== مراحل تست حمله =====
@app.on_message(filters.private & filters.user(ADMIN_ID) & filters.text & ~filters.command("start"))
async def attack_steps(c, m):
    step = atk_state.get("step")
    if not step:
        return
    if step == "phone":
        phone = m.text.strip()
        atk_state["phone"] = phone
        st = await m.reply_text("📡 در حال اتصال به اکانت و ارسال کد تایید...")
        try:
            atk = AdvancedScraper("atk_session", API_ID, API_HASH, phone=phone)
            await atk.connect()
            sent_code = await atk.app.send_code(phone)
            atk_state["atk"] = atk
            atk_state["hash"] = sent_code.phone_code_hash
            atk_state["st"] = st
            atk_state["step"] = "code"
            await st.edit_text("✅ کد تایید به اکانت تست ارسال شد.\nلطفا کد ۵ رقمی را اینجا ارسال کنید.")
        except Exception as e:
            await st.edit_text(f"❌ خطا در اتصال:\n{str(e)}")
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
            await m.reply_text(f"❌ کد اشتباه یا خطا:\n{str(e)}")
            return
        await st.edit_text("✅ ورود به اکانت مهاجم موفق، در حال اجرای حمله...")
        prog = await app.send_message(ADMIN_ID, "🚀 حمله شروع شد، لطفا منتظر بمانید...")
        async def run():
            try:
                users = await atk.run_full_scrape(GROUP_ID)
                csv_bytes = atk.export_csv()
                await prog.edit_text(
                    f"✅ حمله با موفقیت تمام شد!\n\n"
                    f"تعداد کاربری که اسکریپت موفق به استخراج ان شد: {len(users)} نفر\n"
                    f"فایل نتیجه در زیر ارسال میشود:\n\n"
                    f"بررسی کنید که آیا هشدار تشخیص اسکریپت توسط سیستم دفاع برایتان ارسال شده؟"
                )
                await app.send_document(
                    ADMIN_ID,
                    io.BytesIO(csv_bytes),
                    file_name=f"نتیجه_حمله_{int(time.time())}.csv"
                )
                await atk.disconnect()
            except Exception as e:
                await prog.edit_text(f"❌ خطا در حمله:\n{str(e)}")
            atk_state.clear()
        asyncio.create_task(run())

# ===== هندلرهای گروه =====
@app.on_message(filters.new_chat_members & filters.chat(GROUP_ID))
async def on_new_member(c, m):
    if defender.MIN_ACCOUNT_AGE_DAYS <= 0:
        return
    for u in m.new_chat_members:
        if u.is_self:
            continue
        asyncio.create_task(defender.on_join(u))

@app.on_message(filters.left_chat_member & filters.chat(GROUP_ID))
async def on_left_member(c, m):
    asyncio.create_task(defender.on_leave(m.left_chat_member))

@app.on_message(filters.chat(GROUP_ID) & filters.text)
async def monitor_messages(c, m):
    if defender.MIN_ACCOUNT_AGE_DAYS <=0:
        return
    await defender.monitor_message(m)

# ==========================================================
# سرور HTTP ساده برای اینکه رندر فکر کنه سرویس وب دارد و قطع نکند
# ==========================================================
class HealthCheck(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Anti-Scraper Bot is running!")
    def log_message(self, format, *args):
        return

def run_health_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), HealthCheck)
    server.serve_forever()

print("✅ ربات آماده راه اندازی...")
async def main():
    Thread(target=run_health_server, daemon=True).start()
    await app.start()
    print("✅ ربات روشن و به تلگرام متصل شد!")
    await idle()
    await app.stop()

if __name__ == "__main__":
    asyncio.run(main())
