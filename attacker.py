# =================================================================
# 🚨 ماژول اسکریپت حمله پیشرفته
# =================================================================
import asyncio
import time
import random
import io
import csv
from pyrogram import Client
from pyrogram.errors import FloodWait, ChatAdminRequired

DEVICE_FINGERPRINTS = [
    {"device_model": "Samsung Galaxy S24 Ultra", "system_version": "Android 14", "app_version": "10.13.2", "lang_code": "fa"},
    {"device_model": "iPhone 15 Pro Max", "system_version": "iOS 17.5.1", "app_version": "10.14", "lang_code": "fa"},
]

class AdvancedScraper:
    def __init__(self, session_name, api_id, api_hash, phone=None):
        fp = random.choice(DEVICE_FINGERPRINTS)
        self.app = Client(
            session_name,
            api_id=api_id,
            api_hash=api_hash,
            phone_number=phone,
            device_model=fp["device_model"],
            system_version=fp["system_version"],
            app_version=fp["app_version"],
            lang_code=fp["lang_code"],
            in_memory=True
        )
        self.found_users = {}
        self.total_api_calls = 0
        self.start_time = None

    async def connect(self):
        await self.app.connect()
        self.start_time = time.time()

    async def human_sleep(self, min_t=0.8, max_t=2.5):
        t = random.uniform(min_t, max_t)
        if random.random() < 0.1:
            t += random.uniform(1,3)
        await asyncio.sleep(t)

    async def handle_flood(self, e):
        wait = e.value + random.randint(2, 8)
        await asyncio.sleep(wait)

    async def add_user(self, user, source):
        if not user or user.is_bot or user.is_deleted or user.id in self.found_users:
            return
        self.found_users[user.id] = {
            "user_id": user.id,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "username": user.username,
            "is_premium": user.is_premium,
            "source": source
        }
        print(f"✅ [{len(self.found_users)}] {user.first_name} | {source}", flush=True)

    async def scrape_direct(self, chat_id):
        print("\n🔍 روش ۱: لیست مستقیم", flush=True)
        try:
            async for member in self.app.get_chat_members(chat_id):
                self.total_api_calls += 1
                await self.add_user(member.user, "direct_list")
                await self.human_sleep(0.5, 1.2)
            return True
        except ChatAdminRequired:
            print("❌ لیست مخفی است", flush=True)
            return False
        except FloodWait as e:
            await self.handle_flood(e)
            return await self.scrape_direct(chat_id)
        except Exception as e:
            print(f"❌ خطا: {e}", flush=True)
            return False

    async def scrape_messages(self, chat_id, limit=1000):
        print(f"\n🔍 روش ۲: اسکن پیام ها", flush=True)
        async for msg in self.app.get_chat_history(chat_id, limit=limit):
            self.total_api_calls += 1
            if msg.from_user:
                await self.add_user(msg.from_user, "message")
            if msg.forward_from:
                await self.add_user(msg.forward_from, "forward")
            if msg.reply_to_message and msg.reply_to_message.from_user:
                await self.add_user(msg.reply_to_message.from_user, "reply")
            await self.human_sleep(0.2, 0.7)

    async def scrape_joins(self, chat_id):
        print(f"\n🔍 روش ۳: پیام ورود اعضا", flush=True)
        async for msg in self.app.get_chat_history(chat_id, limit=5000):
            self.total_api_calls += 1
            if msg.new_chat_members:
                for u in msg.new_chat_members:
                    await self.add_user(u, "join_service")
            await self.human_sleep(0.1, 0.3)

    async def run_full_scrape(self, chat_id):
        print("="*50, flush=True)
        print("🚀 شروع حمله کامل", flush=True)
        print("="*50, flush=True)

        # FIX: اول تمام دیالوگ ها را بدون محدودیت بارگذاری میکنیم تا همه پیرهارا کش کنیم
        target_found = None
        print("🔍 اسکن کامل لیست چت های اکانت (تا 2000 چت)...", flush=True)
        all_chats = []
        try:
            async for dialog in self.app.get_dialogs(limit=2000):
                all_chats.append(dialog.chat)
                if dialog.chat.id == chat_id:
                    target_found = dialog.chat
        except Exception as e:
            print(f"خطا در اسکن دیالوگ ها: {e}", flush=True)
        print(f"✅ مجموعا {len(all_chats)} چت در اکانت شما پیدا شد", flush=True)
        if not target_found:
            for chat in all_chats:
                if chat.id == chat_id:
                    target_found = chat
                    break
        if not target_found:
            try:
                target_found = await self.app.get_chat(chat_id)
            except Exception as e:
                sample_groups = "\n".join([f"• {c.title}" for c in all_chats if hasattr(c, 'title') and c.title][:10])
                raise Exception(
                    f"❌ گروه پیدا نشد! نمونه گروه های پیدا شده در اکانت شما:\n{sample_groups}\n\n"
                    f"لطفا بعد از ورود به اکانت، یک بار تلگرام را باز کنید و روی نام گروه کلیک کنید تا در لیست بارگذاری شود."
                )
        chat_id = target_found.id
        print(f"🎯 هدف نهایی: {target_found.title} | آیدی: {chat_id}", flush=True)

        direct_ok = await self.scrape_direct(chat_id)
        if not direct_ok:
            await self.scrape_messages(chat_id)
            await self.scrape_joins(chat_id)
        await asyncio.sleep(random.randint(4,9))
        await self.app.leave_chat(chat_id)
        total_time = time.time() - self.start_time
        print(f"\n🏁 در {int(total_time)} ثانیه تمام شد. مجموع: {len(self.found_users)} کاربر", flush=True)
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
