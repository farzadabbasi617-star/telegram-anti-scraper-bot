# =================================================================
# 🛡️ ماژول دفاع پیشرفته
# =================================================================
import time
import asyncio
import random
from datetime import datetime
from pyrogram.types import ChatPermissions, ChatMember
from collections import defaultdict

class AdvancedDefender:
    def __init__(self, app, group_id, admin_id):
        self.app = app
        self.group_id = group_id
        self.admin_id = admin_id
        self.MIN_ACCOUNT_AGE_DAYS = 25
        self.CAPTCHA_TIMEOUT = 60
        self.MAX_QUICK_LEAVE_SECONDS = 240
        self.user_join_times = {}
        self.banned_scrapers = set()
        self.pending_captcha = set()
        self.user_risk_score = defaultdict(int)
        self.last_activity = {}
        self.captcha_codes = {}

    async def alert(self, level, title, details):
        icons = {"critical":"🚨", "high":"⚠️", "info":"✅"}
        ic = icons.get(level, "ℹ️")
        try:
            await self.app.send_message(self.admin_id, f"{ic} **{title}**\n\n{details}\n⏰ {datetime.now().strftime('%H:%M:%S')}")
        except: pass

    async def is_admin(self, uid):
        try:
            m = await self.app.get_chat_member(self.group_id, uid)
            return m.status in ["administrator", "creator"]
        except: return False

    async def restrict(self, uid, can_send=False):
        try:
            perms = ChatPermissions(can_send_messages=can_send, can_invite_users=False, can_send_media_messages=False)
            await self.app.restrict_chat_member(self.group_id, uid, perms)
        except: pass

    async def ban(self, uid, reason=""):
        if uid in self.banned_scrapers:
            return
        try:
            self.banned_scrapers.add(uid)
            await self.app.ban_chat_member(self.group_id, uid)
            await asyncio.sleep(2)
            await self.app.unban_chat_member(self.group_id, uid)
        except: pass

    async def on_join(self, user):
        if await self.is_admin(user.id) or user.is_self:
            return
        self.user_join_times[user.id] = time.time()
        self.last_activity[user.id] = time.time()
        
        # بررسی سن اکانت
        try:
            age = datetime.now() - datetime.fromtimestamp(user.date)
            if age.days < self.MIN_ACCOUNT_AGE_DAYS:
                await self.ban(user.id)
                await self.alert("critical", "مسدود خودکار اکانت جدید", f"کاربر {user.first_name} (آیدی `{user.id}`) با سن اکانت {age.days} روز مسدود شد.")
                return
        except: pass

        await self.restrict(user.id, False)
        self.pending_captcha.add(user.id)
        captcha_code = random.randint(1000,9999)
        self.captcha_codes[user.id] = f"من انسان هستم {captcha_code}"
        cap_msg = await self.app.send_message(
            self.group_id,
            f"سلام {user.first_name} 👋\n"
            f"برای تایید هویت در {self.CAPTCHA_TIMEOUT} ثانیه عبارت زیر را ارسال کنید:\n\n"
            f"`{self.captcha_codes[user.id]}`"
        )
        def check(_,__,m):
            return m.from_user and m.from_user.id == user.id and self.captcha_codes.get(user.id) in (m.text or "")
        try:
            await self.app.listen(self.group_id, filters=None, timeout=self.CAPTCHA_TIMEOUT, filters_=check)
            await self.restrict(user.id, True)
            self.pending_captcha.discard(user.id)
            await cap_msg.delete()
            await self.app.send_message(self.group_id, f"✅ {user.first_name} تایید شد خوش آمدید!")
        except TimeoutError:
            await self.ban(user.id)
            await cap_msg.delete()
            await self.alert("high", "عدم پاسخ به کپچا", f"کاربر {user.first_name} (آیدی {user.id}) به کپچا پاسخ نداد و مسدود شد.")
            self.pending_captcha.discard(user.id)

    async def on_leave(self, user):
        if user.id not in self.user_join_times:
            return
        spent = time.time() - self.user_join_times.pop(user.id)
        if spent < self.MAX_QUICK_LEAVE_SECONDS:
            await self.ban(user.id)
            await self.alert("critical", "تشخیص قطعی اسکریپت!", f"کاربر {user.first_name} (آیدی `{user.id}`) فقط {int(spent)} ثانیه در گروه بود و خارج شد. فورا مسدود شد.")

    async def monitor_message(self, message):
        if not message.from_user: return
        uid = message.from_user.id
        if await self.is_admin(uid): return
        self.last_activity[uid] = time.time()
        if message.text and any(x in message.text.lower() for x in ["admin", "ادمین", "پشتیبان", "تماس با ما", "support"]):
            await self.ban(uid)
            await message.delete()
            await self.alert("critical", "هانی پات", f"کاربر {message.from_user.first_name} تله مخفی را فعال کرد مسدود شد.")

    async def bg_scan(self):
        while True:
            await asyncio.sleep(120)
            now = time.time()
            for uid, jt in list(self.user_join_times.items()):
                if await self.is_admin(uid): continue
                in_time = now - jt
                last_act = now - self.last_activity.get(uid, jt)
                if in_time > 180 and last_act > 180 and uid in self.pending_captcha:
                    await self.ban(uid)
                    await self.alert("high", "کاربر غیرفعال مشکوک", f"کاربر با آیدی {uid} بدون فعالیت مسدود شد.")
