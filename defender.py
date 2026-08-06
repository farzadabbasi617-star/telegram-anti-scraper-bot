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
        self.honeypot_msg_ids = set()

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

    async def deploy_honeypot(self):
        """Send a few invisible honeypot messages into the group periodically.
        These are invisible to normal users (zero-width characters + tiny font buttons)
        but scrapers read them via API and will click or parse the 'admin' / 'secret' links,
        triggering an automatic ban.
        """
        traps = [
            # Trap 1: Invisible "Contact Admin" line (zero-width chars)
            "‌‌‍\u200b\u200c\u200d\n"
            "‌‌‍\u200b<a href=\"https://t.me/HIDDEN_ADMIN_TRAP_ZERO\">ادمین پشتیبان</a> "
            "<a href=\"https://t.me/SUPPORT_BOT_TRAP\">تماس با مدیریت</a> "
            "<code>admin_trap_token_{rnd}</code>\n"
            "‌‌‍\u200b\u200c",
        ]
        text = random.choice(traps).format(rnd=random.randint(10000,99999))
        try:
            # send silently then delete quickly so humans never see it; but it
            # remains in message history for a few seconds so that scrapers who
            # are pulling message history will pick it up.
            msg = await self.app.send_message(self.group_id, text, disable_web_page_preview=True, disable_notification=True)
            self.honeypot_msg_ids.add(msg.id)
            # keep it for 15 seconds then delete - enough time for scrapers
            await asyncio.sleep(15)
            try:
                await msg.delete()
            except:
                pass
            self.honeypot_msg_ids.discard(msg.id)
        except Exception as e:
            print(f"honeypot deploy err: {e}", flush=True)

    async def bg_scan(self):
        # Periodically plant honeypot messages every ~10 minutes
        asyncio.create_task(self._honeypot_loop())
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

    async def _honeypot_loop(self):
        # Wait for things to settle, then plant invisible traps on a schedule
        await asyncio.sleep(30)
        while True:
            try:
                await self.deploy_honeypot()
            except:
                pass
            await asyncio.sleep(random.randint(550, 700))  # every ~10 min

    async def monitor_message(self, message):
        if not message.from_user: return
        uid = message.from_user.id
        if await self.is_admin(uid): return
        self.last_activity[uid] = time.time()
        text = (message.text or message.caption or "").lower()
        # 🍯 Honeypot triggers - expanded set
        trap_keywords = [
            "hidden_admin_trap_zero", "support_bot_trap", "admin_trap_token",
            "ادمین پشتیبان  تماس با مدیریت", "ادمین پشتیبان",
            # also suspicious API-scraper behaviour: posting the invisible tokens
        ]
        if any(k.lower() in text for k in trap_keywords):
            await self.ban(uid)
            try: await message.delete()
            except: pass
            await self.alert("critical", "🍯 هانی‌پات فعال شد!",
                             f"کاربر <b>{message.from_user.first_name}</b> (آیدی <code>{uid}</code>) "
                             f"تله مخفی هانی‌پات را فعال کرد → فوراً بن شد.\n"
                             f"نشانه: اسکرپر/ربات پیام مخفی را خوانده و ری‌اکشن نشان داده.")
            return
        # Suspicious keyword patterns (still keep old basic spam-honeypot)
        if text and any(x in text for x in ["admin", "ادمین", "پشتیبان", "تماس با ما", "support"]):
            # Extra check: if message is very short and looks like a bot scraped the honeypot
            if len(text) < 40:
                await self.ban(uid)
                try: await message.delete()
                except: pass
                await self.alert("critical", "هانی پات", f"کاربر {message.from_user.first_name} تله مخفی را فعال کرد مسدود شد.")
        # 📏 Profile/behavior heuristics
        try:
            u = message.from_user
            score = 0
            name = ((u.first_name or "") + " " + (u.last_name or "")).strip()
            # Suspicious usernames
            uname = (u.username or "").lower()
            if uname and any(k in uname for k in ["sms", "verify", "bonus", "airdrop", "win", "prize", "gift", "درآمد", "کسب درآمد", "پول", "هلد", "ایردراپ", "سود"]):
                score += 3
            # All-digit name (e.g. "1234567890")
            if name.replace(" ","").isdigit() and len(name) > 5:
                score += 3
            # Arabic/English scam patterns (crypto support fake etc.)
            if name and any(k in name.lower() for k in ["support", "admin", "official", "team", "پشتیبان", "ادمین"]):
                score += 4
            if score >= 5:
                await self.restrict(uid)
                await message.delete()
                await self.alert("high", "پروفایل مشکوک تشخیص داده شد",
                                 f"کاربر {name} (@{uname or '—'}) با آیدی {uid} مشکوک به اسپم بود، موقتا محدود شد.")
        except:
            pass

    async def monitor_callback(self, callback):
        """Honeypot callback - if a user clicks an invisible button they get banned."""
        if not callback.from_user: return
        uid = callback.from_user.id
        if await self.is_admin(uid): return
        data = (callback.data or "")
        if data.startswith("hp_") or "trap" in data.lower() or "honeypot" in data.lower():
            try: await callback.answer("⚠️ دسترسی غیرمجاز!", show_alert=True)
            except: pass
            await self.ban(uid)
            await self.alert("critical", "🍯 کلیک روی دکمه هانی‌پات",
                             f"کاربر <b>{callback.from_user.first_name}</b> (آیدی <code>{uid}</code>) "
                             f"روی دکمه مخفی هانی‌پات کلیک کرد → بن شد.")

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
