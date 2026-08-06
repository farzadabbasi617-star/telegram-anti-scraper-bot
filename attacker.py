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

    def get_fp_dict(self):
        return self.fp_used

    async def connect(self):
        try:
            await self.app.connect()
        except (AuthKeyDuplicated, AuthKeyUnregistered):
            raise
        self.start_time = time.time()

    async def _progress(self, text):
        """گزارش پیشرفت هر ۱۸ ثانیه یکبار"""
        now = time.time()
        if now - self._last_progress < 18:
            return
        self._last_progress = now
        if self._progress_cb:
            try:
                await self._progress_cb(f"⏳ {text}\n✅ تا کنون {len(self.found_users)} کاربر پیدا شده")
            except Exception:
                pass

    async def human_sleep(self, min_t=0.3, max_t=1.2):
        t = random.uniform(min_t, max_t)
        if random.random() < 0.05:
            t += random.uniform(0.8, 2.0)
        await asyncio.sleep(t)

    async def handle_flood(self, e):
        wait = e.value + random.randint(1,4)
        print(f"⏱️ فلود {wait}s", flush=True)
        if self._progress_cb:
            try:
                await self._progress_cb(f"⏱️ محدودیت سرعت تلگرام، {wait} ثانیه صبر...")
            except:
                pass
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

    async def scrape_direct_paginated(self, chat_id):
        print("\n🔍 روش ۱: لیست مستقیم...", flush=True)
        await self._progress("در حال استخراج از لیست مستقیم اعضا...")
        count_added = 0
        try:
            async for member in self.app.get_chat_members(chat_id, limit=10000):
                self.total_api_calls +=1
                await self.add_user(member.user, "direct_list")
                count_added +=1
                if count_added % 100 == 0:
                    await self._progress(f"از لیست مستقیم {count_added} نفر خوانده شد...")
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
        await self._progress("در حال جستجو با حروف الفبا (صفحه بندی عمیق)...")
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
                if pi % 5 == 0:
                    await self._progress(f"صفحه بندی حروف... حرف {prefix}")
                await self.human_sleep(0.2, 0.5)
            except FloodWait as e:
                await self.handle_flood(e)
            except Exception:
                continue
        print(f"✅ صفحه بندی تمام، مجموع {len(self.found_users)}", flush=True)
        return True

    async def scrape_full_history(self, chat_id, limit=50000):
        print(f"\n🔍 روش ۲: اسکن {limit} پیام...", flush=True)
        await self._progress(f"در حال اسکن تاریخچه پیام ها (حداکثر {limit} پیام)...")
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
            if msg_count % 200 == 0:
                await self._progress(f"اسکن تاریخچه: {msg_count} پیام بررسی شد")
            await self.human_sleep(0.05, 0.15)
        print(f"✅ اسکن پیام: {msg_count}", flush=True)

    async def scrape_join_events(self, chat_id):
        print("\n🔍 روش ۳: اسکن پیام های ورود عضو...", flush=True)
        await self._progress("در حال اسکن پیام های عضو جدید...")
        cnt = 0
        async for msg in self.app.get_chat_history(chat_id, limit=100000):
            self.total_api_calls +=1
            cnt +=1
            if msg.new_chat_members:
                for u in msg.new_chat_members:
                    await self.add_user(u, "ورود عضو")
            if cnt % 500 == 0:
                await self._progress(f"بررسی پیام های ورود: {cnt} پیام")
            await self.human_sleep(0.05, 0.1)
        print(f"✅ پیام ورود اسکن شد", flush=True)

    async def run_full_scrape(self, chat_id, progress_cb=None):
        self._progress_cb = progress_cb
        self._last_progress = 0
        print("="*60, flush=True)
        print("🚀 شروع حمله MAX MODE", flush=True)
        print("="*60, flush=True)

        if progress_cb:
            try:
                await progress_cb("🔄 در حال بارگذاری لیست چت ها و گرم کردن کش...")
            except: pass

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
        await asyncio.sleep(3)

        if progress_cb:
            try:
                await progress_cb("🔎 در حال پیدا کردن گروه هدف...")
            except: pass

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
                    await asyncio.sleep(3)
                    target_found = await self.app.get_chat(chat_id)
                    target_id_resolved = target_found.id
                except:
                    raise Exception("❌ گروه پیدا نشد! لطفا یک بار گروه را در تلگرام باز و اسکرول کنید.")
        chat_id = target_id_resolved
        print(f"✅ هدف: {target_found.title}", flush=True)
        if progress_cb:
            try:
                await progress_cb(f"🎯 هدف: {target_found.title}\nدر حال بررسی عضویت...")
            except: pass

        is_member = None
        for attempt in range(5):
            try:
                me = await self.app.get_chat_member(chat_id, "me")
                if me and me.status in ["administrator", "creator", "member", "restricted"]:
                    is_member = True
                    break
            except Exception as e:
                print(f"⏱️ تلاش {attempt+1} عضویت: {e}", flush=True)
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

        if progress_cb:
            try:
                await progress_cb(f"🚀 شروع استخراج از گروه {target_found.title}")
            except: pass

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
        try:
            await asyncio.sleep(0.3)
            await self.app.disconnect()
        except Exception as e:
            print(f"هنگام قطع: {e}", flush=True)
