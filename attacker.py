# =================================================================
# 🚨 ماژول حمله پیشرفته نسخه MAX - برای تست حداکثری
# =================================================================
import asyncio
import time
import random
import io
import csv
import string
import os
from pyrogram import Client
from pyrogram.errors import FloodWait, ChatAdminRequired, SessionPasswordNeeded, PhoneCodeInvalid, PhoneCodeExpired, AuthKeyDuplicated, AuthKeyUnregistered
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
    return ''.join(c for c in str(phone) if c.isdigit() or c == '+').strip('+')

class AdvancedScraper:
    def __init__(self, session_name, api_id, api_hash, phone=None, in_memory=False, device_fp=None):
        if device_fp:
            fp = device_fp
        else:
            fp = random.choice(DEVICE_FP)
        if phone and not in_memory:
            fname = safe_phone_filename(phone)
            session_path = os.path.join(SESSIONS_DIR, f"acc_{fname}")
        else:
            session_path = session_name
        self.phone = phone
        self.fp_used = fp
        self.app = Client(
            session_path,
            api_id=api_id,
            api_hash=api_hash,
            phone_number=phone,
            device_model=fp["device_model"],
            system_version=fp["system_version"],
            app_version=fp["app_version"],
            lang_code=fp["lang_code"],
            in_memory=False,
            sleep_threshold=30,
            workdir=".",
            no_updates=True
        )
        self.found_users = {}
        self.total_api_calls = 0
        self.start_time = None
        self._progress_cb = None
        self._last_progress = 0
        self._stage = "در حال آماده سازی..."
        self._last_added_name = "-"
        self._last_progress_val = 0

    def get_fp_dict(self):
        return self.fp_used

    async def connect(self):
        try:
            await self.app.connect()
        except (AuthKeyDuplicated, AuthKeyUnregistered):
            raise
        self.start_time = time.time()

    async def _progress(self, text=None, force=False):
        """گزارش پیشرفت زنده هر ۵ ثانیه"""
        now = time.time()
        if text:
            self._stage = text
        if not force and now - self._last_progress < 5:
            return
        self._last_progress = now
        if self._progress_cb:
            try:
                elapsed = int(time.time() - self.start_time) if self.start_time else 0
                mins = elapsed // 60
                secs = elapsed % 60
                count = len(self.found_users)
                speed = int(count / (elapsed/60)) if elapsed > 10 else 0
                # چراغ متحرک
                dots = ["🟢", "🟢", "🟡", "🟢"][int(elapsed/2) % 4]
                text_out = f"{dots} **وضعیت زنده**\n\n"
                text_out += f"🎯 مرحله: {self._stage}\n"
                text_out += f"✅ پیدا شده: **{count:,}** نفر\n"
                text_out += f"⏱️ زمان سپری: {mins} دقیقه و {secs} ثانیه\n"
                text_out += f"⚡ سرعت: ~{speed} نفر در دقیقه\n"
                text_out += f"📡 درخواست به تلگرام: {self.total_api_calls}\n"
                text_out += f"👤 آخرین فرد: {self._last_added_name}\n\n"
                if elapsed > 60:
                    text_out += f"💡 کار در حال اجرا، لطفا صبر کنید..."
                await self._progress_cb(text_out)
            except Exception:
                pass

    async def human_sleep(self, min_t=0.3, max_t=1.2):
        t = random.uniform(min_t, max_t)
        if random.random() < 0.05:
            t += random.uniform(0.8, 2.0)
        # در طول اسلیپ هم پیشرفت را بروزرسانی کن
        end_t = time.time() + t
        while time.time() < end_t:
            await asyncio.sleep(min(0.5, end_t - time.time()))
            if time.time() - self._last_progress >= 5:
                await self._progress()

    async def handle_flood(self, e):
        wait = e.value + random.randint(1,4)
        print(f"⏱️ فلود {wait}s", flush=True)
        self._stage = f"محدودیت سرعت تلگرام، {wait} ثانیه صبر..."
        await self._progress(force=True)
        await asyncio.sleep(wait)

    async def add_user(self, user, source):
        if not user or user.is_bot or user.is_deleted or user.is_scam or user.is_fake or user.id in self.found_users:
            return
        fullname = user.first_name or ""
        if user.last_name:
            fullname += " " + user.last_name
        if not fullname:
            fullname = f"کاربر {user.id}"
        self._last_added_name = fullname
        self.found_users[user.id] = {
            "user_id": user.id,
            "first_name": user.first_name,
            "last_name": user.last_name or "",
            "username": user.username or "",
            "is_premium": "بله" if user.is_premium else "خیر",
            "source": source
        }
        self._last_progress_val += 1
        if self._last_progress_val % 5 == 0:
            await self._progress()

    async def scrape_direct_paginated(self, chat_id):
        print("\n🔍 روش ۱: لیست مستقیم...", flush=True)
        self._stage = "در حال استخراج از لیست مستقیم اعضا"
        await self._progress(force=True)
        count_added = 0
        try:
            async for member in self.app.get_chat_members(chat_id, limit=10000):
                self.total_api_calls +=1
                await self.add_user(member.user, "direct_list")
                count_added +=1
                if count_added % 30 == 0:
                    self._stage = f"لیست مستقیم، {count_added} نفر خوانده شد"
                    await self._progress()
                await self.human_sleep(0.2, 0.6)
            print(f"✅ لیست اولیه {count_added} عضو", flush=True)
        except ChatAdminRequired:
            print("❌ لیست اعضا مخفی است", flush=True)
            return False
        except FloodWait as e:
            await self.handle_flood(e)
        except Exception as e:
            print(f"خطا در لیست: {e}", flush=True)
            return False

        search_prefixes = list(string.ascii_lowercase) + list("ابپتثجچحخدذرزژسشصضطظعغفقکگلمنوهی") + list("1234567890")
        print(f"🔍 صفحه بندی با {len(search_prefixes)} حرف...", flush=True)
        self._stage = f"صفحه بندی جستجو با حروف الفبا"
        await self._progress(force=True)
        for pi, prefix in enumerate(search_prefixes):
            try:
                while True:
                    self.total_api_calls +=1
                    res = await self.app.invoke(functions.contacts.Search(q=prefix, limit=200))
                    for u in res.users:
                        try:
                            mem = await self.app.get_chat_member(chat_id, u.id)
                            if mem and u.id not in self.found_users:
                                await self.add_user(u, f"search_{prefix}")
                                count_added +=1
                        except:
                            pass
                    if len(res.users) < 200:
                        break
                    await self.human_sleep(0.4, 0.9)
                if pi % 3 == 0:
                    self._stage = f"جستجو با حرف '{prefix}' | {count_added} جدید"
                    await self._progress()
                await self.human_sleep(0.2, 0.5)
            except FloodWait as e:
                await self.handle_flood(e)
            except Exception:
                continue
        print(f"✅ صفحه بندی تمام، مجموع {len(self.found_users)}", flush=True)
        return True

    async def scrape_full_history(self, chat_id, limit=50000):
        print(f"\n🔍 روش ۲: اسکن {limit} پیام...", flush=True)
        self._stage = f"در حال اسکن تاریخچه پیام ها (تا {limit} پیام)"
        await self._progress(force=True)
        msg_count = 0
        async for msg in self.app.get_chat_history(chat_id, limit=limit):
            self.total_api_calls +=1
            msg_count +=1
            if msg.from_user:
                await self.add_user(msg.from_user, "پیام")
            if msg.forward_from:
                await self.add_user(msg.forward_from, "فوروارد")
            if msg.reply_to_message and msg.reply_to_message.from_user:
                await self.add_user(msg.reply_to_message.from_user, "پاسخ")
            if msg.entities:
                for ent in msg.entities:
                    if ent.type in ("mention", "text_mention") and ent.user:
                        await self.add_user(ent.user, "منشن")
            if msg.reactions:
                for react in msg.reactions.reactions:
                    try:
                        reactors = await self.app.get_message_reactions(chat_id, msg.id, react.emoji, limit=100)
                        for r in reactors:
                            if r.peer.user_id:
                                try:
                                    u = await self.app.get_users(r.peer.user_id)
                                    await self.add_user(u, "ری اکشن")
                                except: pass
                    except: pass
            if msg_count % 100 == 0:
                self._stage = f"بررسی تاریخچه، {msg_count} پیام اسکن شد"
                await self._progress()
            await self.human_sleep(0.05, 0.15)
        print(f"✅ اسکن پیام: {msg_count}", flush=True)

    async def scrape_join_events(self, chat_id):
        print("\n🔍 روش ۳: اسکن پیام های ورود عضو...", flush=True)
        self._stage = "در حال اسکن پیام های «عضو جدید»"
        await self._progress(force=True)
        cnt = 0
        async for msg in self.app.get_chat_history(chat_id, limit=100000):
            self.total_api_calls +=1
            cnt +=1
            if msg.new_chat_members:
                for u in msg.new_chat_members:
                    await self.add_user(u, "ورود عضو")
            if cnt % 200 == 0:
                self._stage = f"بررسی پیام های ورود: {cnt} پیام"
                await self._progress()
            await self.human_sleep(0.05, 0.1)
        print(f"✅ پیام ورود اسکن شد", flush=True)

    async def run_full_scrape(self, chat_id, progress_cb=None):
        self._progress_cb = progress_cb
        self._last_progress = 0
        self.start_time = time.time()
        self._stage = "در حال اتصال..."
        print("="*60, flush=True)
        print("🚀 شروع حمله MAX MODE", flush=True)
        print("="*60, flush=True)

        # یک وظیفه پس زمینه که هر ۵ ثانیه بدون توجه به کار اصلی وضعیت را آپدیت نگه میدارد
        heartbeat_on = True
        async def heartbeat():
            while heartbeat_on:
                await self._progress()
                await asyncio.sleep(4)

        hb_task = asyncio.create_task(heartbeat())

        try:
            self._stage = "🔄 در حال بارگذاری لیست چت ها و گرم کردن کش"
            await self._progress(force=True)
            print("🔄 در حال بارگذاری لیست چت ها...", flush=True)
            all_chats = {}
            try:
                for _pass in range(2):
                    cnt = 0
                    async for d in self.app.get_dialogs(limit=2000):
                        all_chats[d.chat.id] = d.chat
                        cnt +=1
                        await asyncio.sleep(0.01)
                    print(f"🔄 پاس {_pass+1}: {cnt} چت", flush=True)
                    await asyncio.sleep(2)
            except Exception as e:
                print(f"خطا در چت ها: {e}", flush=True)
            await asyncio.sleep(2)

            self._stage = "🔎 در حال پیدا کردن گروه هدف"
            await self._progress(force=True)
            target_found = None
            target_id_resolved = None
            try:
                peer = await self.app.resolve_peer(chat_id)
                target_found = await self.app.get_chat(chat_id)
                target_id_resolved = target_found.id
                print(f"🎯 هدف: {target_found.title} | {target_found.id}", flush=True)
            except Exception as e:
                print(f"🔍 رزول مستقیم نشد: {e}", flush=True)
                if chat_id in all_chats:
                    target_found = all_chats[chat_id]
                    target_id_resolved = target_found.id
                else:
                    async for d in self.app.get_dialogs(limit=2000):
                        if d.chat.id == chat_id:
                            target_found = d.chat
                            target_id_resolved = d.chat.id
                            break
                    await asyncio.sleep(1)
                if not target_found:
                    try:
                        await asyncio.sleep(2)
                        target_found = await self.app.get_chat(chat_id)
                        target_id_resolved = target_found.id
                    except:
                        raise Exception("❌ گروه پیدا نشد! لطفا یک بار گروه را در تلگرام باز و اسکرول کنید.")
            chat_id = target_id_resolved
            print(f"✅ هدف: {target_found.title}", flush=True)

            self._stage = f"✅ هدف: {target_found.title} | در حال بررسی عضویت"
            await self._progress(force=True)
            is_member = None
            for attempt in range(5):
                try:
                    me = await self.app.get_chat_member(chat_id, "me")
                    if me and me.status in ["administrator", "creator", "member", "restricted"]:
                        is_member = True
                        break
                except Exception as e:
                    print(f"⏱️ تلاش {attempt+1} عضویت: {e}", flush=True)
                    self._stage = f"تلاش {attempt+1} برای تایید عضویت در گروه"
                    await self._progress()
                    await asyncio.sleep(2.5)
                    try:
                        await self.app.resolve_peer(chat_id)
                    except: pass
                    try:
                        async for _ in self.app.get_dialogs(limit=200):
                            pass
                    except: pass
            if is_member is not True:
                print("⚠️ چک عضویت ناموفق بود ولی ادامه میدهم...", flush=True)

            self._stage = f"🚀 شروع استخراج از {target_found.title}"
            await self._progress(force=True)

            direct_ok = await self.scrape_direct_paginated(chat_id)
            if not direct_ok:
                await self.scrape_full_history(chat_id)
                await self.scrape_join_events(chat_id)
            else:
                await self.scrape_full_history(chat_id, limit=5000)
                await self.scrape_join_events(chat_id)

            await asyncio.sleep(random.randint(5,12))
            try:
                await self.app.leave_chat(chat_id)
                print("🚪 خارج شدم", flush=True)
            except: pass
            total = time.time() - self.start_time
            print(f"\n🏁 تمام شد در {int(total)}s، مجموع {len(self.found_users)} کاربر", flush=True)
            self._stage = f"✅ تمام شد! در حال آماده سازی فایل خروجی..."
            await self._progress(force=True)
            return self.found_users
        finally:
            heartbeat_on = False
            try:
                await hb_task
            except:
                pass

    def export_csv(self):
        out = io.StringIO()
        if self.found_users:
            keys = list(list(self.found_users.values())[0].keys())
            w = csv.DictWriter(out, fieldnames=keys)
            w.writeheader()
            w.writerows(self.found_users.values())
        return out.getvalue().encode("utf-8-sig")

    async def disconnect(self):
        try:
            await asyncio.sleep(0.3)
            await self.app.disconnect()
        except Exception as e:
            print(f"هنگام قطع: {e}", flush=True)
