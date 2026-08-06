import asyncio
import time
import random
import io
import csv
import string
import os
from pyrogram import Client
from pyrogram.errors import FloodWait, ChatAdminRequired, SessionPasswordNeeded, PhoneCodeInvalid, PhoneCodeExpired
from pyrogram.raw import functions, types

# فینگرپرینت دستگاه های مختلف برای دور زدن تشخیص
DEVICE_FP = [
    {"device_model": "Samsung Galaxy S24 Ultra", "system_version": "Android 14", "app_version": "10.13.2", "lang_code": "fa"},
    {"device_model": "iPhone 15 Pro Max", "system_version": "iOS 17.6.1", "app_version": "10.15", "lang_code": "fa"},
    {"device_model": "Xiaomi 14 Pro", "system_version": "HyperOS 1.0", "app_version": "10.12.4", "lang_code": "en"},
]

SESSIONS_DIR = "saved_sessions"
os.makedirs(SESSIONS_DIR, exist_ok=True)

def safe_phone_filename(phone):
    """تبدیل شماره تلفن به نام فایل امن"""
    return ''.join(c for c in str(phone) if c.isdigit() or c == '+').strip('+')

class AdvancedScraper:
    def __init__(self, session_name, api_id, api_hash, phone=None, in_memory=False):
        fp = random.choice(DEVICE_FP)
        # اگر شماره تلفن داده شد از فایل سشن دائمی استفاده کن
        if phone and not in_memory:
            fname = safe_phone_filename(phone)
            session_path = os.path.join(SESSIONS_DIR, f"acc_{fname}")
        else:
            session_path = session_name
        self.phone = phone
        self.app = Client(
            session_path,
            api_id=api_id,
            api_hash=api_hash,
            phone_number=phone,
            device_model=fp["device_model"],
            system_version=fp["system_version"],
            app_version=fp["app_version"],
            lang_code=fp["lang_code"],
            in_memory=False,  # سشن ها دائمی روی دیسک ذخیره شوند
            sleep_threshold=10,
            workdir="."
        )
        self.found_users = {}
        self.total_api_calls = 0
        self.start_time = None

    async def connect(self):
        await self.app.connect()
        self.start_time = time.time()

    async def human_sleep(self, min_t=0.3, max_t=1.2):
        t = random.uniform(min_t, max_t)
        if random.random() < 0.05:
            t += random.uniform(0.8, 2.0)
        await asyncio.sleep(t)

    async def handle_flood(self, e):
        wait = e.value + random.randint(1,4)
        print(f"⏱️ محدودیت سرعت، {wait} ثانیه صبر...", flush=True)
        await asyncio.sleep(wait)

    async def add_user(self, user, source):
        if not user or user.is_bot or user.is_deleted or user.is_scam or user.is_fake or user.id in self.found_users:
            return
        self.found_users[user.id] = {
            "user_id": user.id,
            "first_name": user.first_name,
            "last_name": user.last_name or "",
            "username": user.username or "",
            "is_premium": "بله" if user.is_premium else "خیر",
            "source": source
        }
        print(f"✅ [{len(self.found_users)}] {user.first_name} | {source}", flush=True)

    async def scrape_direct_paginated(self, chat_id):
        """تکنیک صفحه بندی حروف الفبا - استخراج حداکثری از لیست مستقیم"""
        print("\n🔍 روش 1: استخراج مستقیم لیست با صفحه بندی الفبایی...", flush=True)
        count_added = 0
        # اول لیست معمولی
        try:
            async for member in self.app.get_chat_members(chat_id, limit=10000):
                self.total_api_calls +=1
                await self.add_user(member.user, "direct_list")
                count_added +=1
                await self.human_sleep(0.2, 0.6)
            print(f"✅ لیست اولیه {count_added} عضو", flush=True)
        except ChatAdminRequired:
            print("❌ دسترسی به لیست مخفی، به روش های جایگزین میروم", flush=True)
            return False
        except FloodWait as e:
            await self.handle_flood(e)
        except Exception as e:
            print(f"خطا در لیست اولیه: {e}", flush=True)
            return False

        # صفحه بندی با پیشوند الفبای فارسی و انگلیسی
        search_prefixes = list(string.ascii_lowercase) + list("ابپتثجچحخدذرزژسشصضطظعغفقکگلمنوهی") + ["1","2","3","4","5","6","7","8","9","0"]
        print(f"🔍 شروع صفحه بندی با {len(search_prefixes)} پیشوند...", flush=True)
        peer = await self.app.resolve_peer(chat_id)
        for prefix in search_prefixes:
            try:
                offset = 0
                while True:
                    self.total_api_calls +=1
                    res = await self.app.invoke(
                        functions.contacts.Search(q=prefix, limit=200)
                    )
                    found_in_page = 0
                    for u in res.users:
                        # چک کن که در این گروه عضو هست
                        try:
                            mem = await self.app.get_chat_member(chat_id, u.id)
                            if mem:
                                if u.id not in self.found_users:
                                    await self.add_user(u, f"search_prefix_{prefix}")
                                    count_added +=1
                                    found_in_page +=1
                        except:
                            pass
                    if len(res.users) < 200:
                        break
                    offset +=200
                    await self.human_sleep(0.4, 0.9)
                await self.human_sleep(0.2, 0.5)
            except FloodWait as e:
                await self.handle_flood(e)
            except Exception as e:
                continue
        print(f"✅ صفحه بندی الفبایی تمام شد، مجموع تا کنون {len(self.found_users)}", flush=True)
        return True

    async def scrape_full_history(self, chat_id, limit=50000):
        """اسکن کامل تاریخچه پیام ها، ری اکشن ها، پاسخ ها"""
        print(f"\n🔍 روش 2: اسکن کامل {limit} پیام، ری اکشن، پاسخ...", flush=True)
        msg_count = 0
        async for msg in self.app.get_chat_history(chat_id, limit=limit):
            self.total_api_calls +=1
            msg_count +=1
            # نویسنده پیام
            if msg.from_user:
                await self.add_user(msg.from_user, "message_author")
            # کاربر فوروارد شده
            if msg.forward_from:
                await self.add_user(msg.forward_from, "forwarded_from")
            # کسی که بهش پاسخ داده شده
            if msg.reply_to_message and msg.reply_to_message.from_user:
                await self.add_user(msg.reply_to_message.from_user, "reply_to")
            # کاربران تگ شده در متن
            if msg.entities:
                for ent in msg.entities:
                    if ent.type in ("mention", "text_mention") and ent.user:
                        await self.add_user(ent.user, "mentioned_user")
            # بررسی واکنش ها
            if msg.reactions:
                for react in msg.reactions.reactions:
                    try:
                        reactors = await self.app.get_message_reactions(chat_id, msg.id, react.emoji, limit=100)
                        for r in reactors:
                            if r.peer.user_id:
                                try:
                                    u = await self.app.get_users(r.peer.user_id)
                                    await self.add_user(u, "reaction_user")
                                except:
                                    pass
                    except:
                        pass
            if msg_count % 500 == 0:
                print(f"🔄 {msg_count} پیام اسکن شد، مجموع کاربر: {len(self.found_users)}", flush=True)
            await self.human_sleep(0.05, 0.15)
        print(f"✅ اسکن پیام تمام شد، {msg_count} پیام بررسی، مجموع {len(self.found_users)}", flush=True)

    async def scrape_join_events(self, chat_id):
        """اسکن تمام پیام های ورود اعضا حتی افرادی که پیام ندادند"""
        print("\n🔍 روش 3: اسکن پیام های ورود اعضا...", flush=True)
        async for msg in self.app.get_chat_history(chat_id, limit=100000):
            self.total_api_calls +=1
            if msg.new_chat_members:
                for u in msg.new_chat_members:
                    await self.add_user(u, "join_event")
            await self.human_sleep(0.05, 0.1)
        print(f"✅ پیام ورود اسکن شد، مجموع: {len(self.found_users)}", flush=True)

    async def run_full_scrape(self, chat_id):
        print("="*60, flush=True)
        print("🚀 شروع حمله MAX MODE", flush=True)
        print("="*60, flush=True)

        # گرم کردن کش دیالوگ ها - این کار مانع ارور CHAT_INVALID و عضو نبودن میشه
        print("🔄 در حال بارگذاری لیست چت ها برای گرم کردن کش تلگرام...", flush=True)
        try:
            cnt = 0
            async for _ in self.app.get_dialogs(limit=2000):
                cnt +=1
                if cnt % 200 == 0:
                    await self.human_sleep(0.1, 0.3)
            print(f"✅ {cnt} چت بارگذاری شد", flush=True)
        except Exception as e:
            print(f"توجه: خطا در بارگذاری چت ها: {e}", flush=True)

        # پیدا کردن گروه هدف با کش کامل
        target_found = None
        try:
            target_found = await self.app.get_chat(chat_id)
            print(f"🎯 هدف: {target_found.title} | {target_found.id}", flush=True)
        except Exception as e:
            # اگر مستقیم پیدا نشد تمام دیالوگ ها رو بگرد
            print(f"🔍 هدف مستقیم پیدا نشد، در حال جستجو در لیست دیالوگ...", flush=True)
            async for d in self.app.get_dialogs(limit=2000):
                if d.chat.id == chat_id:
                    target_found = d.chat
                    break
            if not target_found:
                raise Exception("گروه پیدا نشد، لطفا یک بار با اکانت وارد گروه شوید.")
        chat_id = target_found.id

        # چک عضویت با چند بار تلاش برای اطمینان
        is_member = False
        for attempt in range(3):
            try:
                me = await self.app.get_chat_member(chat_id, "me")
                if me and me.status in ["administrator", "creator", "member", "restricted"]:
                    is_member = True
                    break
            except Exception as e:
                print(f"⏱️ تلاش {attempt+1} برای چک عضویت ناموفق بود، ۲ ثانیه صبر...", flush=True)
                await asyncio.sleep(2)
                # یک بار دیگه لیست رو رفرش کن
                async for _ in self.app.get_dialogs(limit=500):
                    pass
        if not is_member:
            raise Exception("❌ اکانت تست عضو این گروه نیست! لطفا ابتدا خودتان دستی با اکانت وارد گروه شوید (یک بار چت را باز کنید) و دوباره امتحان کنید.")
        print("✅ تایید شد که در گروه عضو هستم", flush=True)

        # مرحله ۱: لیست مستقیم با صفحه بندی الفبایی
        direct_ok = await self.scrape_direct_paginated(chat_id)

        # اگر لیست اعضا مخفی بود روش های جایگزین
        if not direct_ok:
            await self.scrape_full_history(chat_id)
            await self.scrape_join_events(chat_id)
        else:
            # در هر حال هم اسکن پیام و هم اسکن ورود رو انجام بده برای اطمینان
            await self.scrape_full_history(chat_id, limit=5000)
            await self.scrape_join_events(chat_id)

        # خروج از گروه بعد از تاخیر
        await asyncio.sleep(random.randint(5,12))
        try:
            await self.app.leave_chat(chat_id)
            print("🚪 از گروه خارج شدم", flush=True)
        except: pass
        total = time.time() - self.start_time
        print(f"\n🏁 تمام شد در {int(total)} ثانیه. مجموع استخراج: {len(self.found_users)} کاربر", flush=True)
        return self.found_users

    def export_csv(self):
        out = io.StringIO()
        if self.found_users:
            keys = list(list(self.found_users.values())[0].keys())
            w = csv.DictWriter(out, fieldnames=keys)
            w.writeheader()
            w.writerows(self.found_users.values())
        return out.getvalue().encode("utf-8-sig")

    async def disconnect(self):
        await self.app.disconnect()
