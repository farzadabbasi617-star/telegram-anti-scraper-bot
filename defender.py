# =================================================================
# 🛡️ ماژول دفاع پیشرفته
# =================================================================
import time
import asyncio
import random
import os
from datetime import datetime
from pyrogram.types import ChatPermissions, ChatMember
from pyrogram import filters
from collections import defaultdict
import db

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
        self._load_banned_from_db()

    def _load_banned_from_db(self):
        """بارگذاری لیست بن شده ها از دیتابیس"""
        try:
            cfg = db.get_config("defender_banned", "")
            if cfg:
                import json as _json
                self.banned_scrapers = set(_json.loads(cfg))
        except:
            pass

    def _save_banned_to_db(self):
        try:
            import json as _json
            db.set_config("defender_banned", _json.dumps(list(self.banned_scrapers)))
        except:
            pass

    async def alert(self, level, title, details):
        icons = {"critical":"🚨", "high":"⚠️", "info":"✅"}
        ic = icons.get(level, "ℹ️")
        try:
            await self.app.send_message(self.admin_id, f"{ic} **{title}**\n\n{details}\n⏰ {datetime.now().strftime('%H:%M:%S')}")
        except Exception:
            pass

    async def is_admin(self, uid):
        try:
            m = await self.app.get_chat_member(self.group_id, uid)
            return m.status in ["administrator", "creator"]
        except:
            return False

    async def restrict(self, uid, can_send=False):
        try:
            perms = ChatPermissions(
                can_send_messages=can_send,
                can_send_media_messages=can_send,
                can_send_other_messages=can_send,
                can_add_web_page_previews=can_send,
                can_invite_users=False,
                can_pin_messages=False,
                can_change_info=False,
            )
            await self.app.restrict_chat_member(self.group_id, uid, perms)
        except Exception:
            pass

    async def ban(self, uid, reason=""):
        if uid in self.banned_scrapers:
            return
        try:
            self.banned_scrapers.add(uid)
            self._save_banned_to_db()
            await self.app.ban_chat_member(self.group_id, uid)
            await asyncio.sleep(2)
            try:
                await self.app.unban_chat_member(self.group_id, uid)
            except:
                pass
        except Exception:
            pass

    async def on_join(self, user):
        if not user or getattr(user, 'is_bot', False) or user.is_self:
            return
        if await self.is_admin(user.id):
            return
        self.user_join_times[user.id] = time.time()
        self.last_activity[user.id] = time.time()

        # بررسی سن اکانت
        try:
            acct_ts = getattr(user, 'date', 0)
            if acct_ts:
                age = datetime.now() - datetime.fromtimestamp(acct_ts)
                if age.days < self.MIN_ACCOUNT_AGE_DAYS:
                    await self.ban(user.id)
                    await self.alert("critical", "مسدود خودکار اکانت جدید",
                        f"کاربر {user.first_name} (آیدی `{user.id}`) با سن اکانت {age.days} روز مسدود شد.")
                    return
        except:
            pass

        await self.restrict(user.id, False)
        self.pending_captcha.add(user.id)
        captcha_code = random.randint(1000,9999)
        captcha_phrase = f"من انسان هستم {captcha_code}"
        self.captcha_codes[user.id] = captcha_phrase
        try:
            cap_msg = await self.app.send_message(
                self.group_id,
                f"سلام {user.first_name} 👋\n"
                f"برای تایید هویت در {self.CAPTCHA_TIMEOUT} ثانیه عبارت زیر را در پاسخ به همین پیام ارسال کنید:\n\n"
                f"<code>{captcha_phrase}</code>"
            )
        except Exception as e:
            self.pending_captcha.discard(user.id)
            return
        # Wait for the captcha response properly
        def cap_filter(_, __, m):
            return (m.from_user and m.from_user.id == user.id
                    and m.text
                    and captcha_phrase in (m.text or ""))
        try:
            answer = await self.app.listen(self.group_id, timeout=self.CAPTCHA_TIMEOUT, filters=filters.create(cap_filter))
            await self.restrict(user.id, True)
            self.pending_captcha.discard(user.id)
            self.captcha_codes.pop(user.id, None)
            try:
                await cap_msg.delete()
            except:
                pass
            await self.app.send_message(self.group_id, f"✅ {user.first_name} تایید شد، خوش آمدید!")
        except TimeoutError:
            await self.ban(user.id)
            try:
                await cap_msg.delete()
            except:
                pass
            await self.alert("high", "عدم پاسخ به کپچا",
                f"کاربر {user.first_name} (آیدی {user.id}) به کپچا پاسخ نداد و مسدود شد.")
            self.pending_captcha.discard(user.id)
            self.captcha_codes.pop(user.id, None)
        except Exception:
            self.pending_captcha.discard(user.id)
            self.captcha_codes.pop(user.id, None)

    async def on_leave(self, user):
        if not user:
            return
        if user.id not in self.user_join_times:
            return
        spent = time.time() - self.user_join_times.pop(user.id)
        if spent < self.MAX_QUICK_LEAVE_SECONDS:
            await self.ban(user.id)
            await self.alert("critical", "تشخیص قطعی اسکریپت!",
                f"کاربر {user.first_name} (آیدی `{user.id}`) فقط {int(spent)} ثانیه در گروه بود و خارج شد. فورا مسدود شد.")

    async def deploy_honeypot(self):
        """ارسال پیام‌های هانی‌پات نامرئی با zero-width char.
        - پیام برای کاربران عادی قابل مشاهده نیست (چون محتوا فقط کاراکترهای نامرئی + لینک تله مخفی است)
        - اسکریپت‌های اسکرپر که API history را میخوانند، لینک 'ادمین' را میبینند و روی آن کلیک/فوروارد میکنند و شناسایی میشوند.
        """
        rnd = random.randint(100000, 999999)
        # مخفی: فقط کاراکترهای Zero-width بدون محتوای قابل مشاهده که کلمه «ادمین» دارد اما دیده نمیشود
        z1 = "\u200b\u200c\u200d\ufeff"
        z2 = "\u200b\u200c\u200d"
        text = (f"{z1}<a href=\"https://t.me/HP_ADMIN_{rnd}\">{z2}</a>"
                f"{z2}<a href=\"https://t.me/HP_SUPPORT_{rnd}\">{z2}</a>"
                f"{z2}<code>hp_trap_{rnd}</code>{z2}")
        try:
            msg = await self.app.send_message(
                self.group_id, text,
                disable_web_page_preview=True,
                disable_notification=True,
            )
            self.honeypot_msg_ids.add(msg.id)
            # بعد از ۱۵ ثانیه حذف کن تا هیچ کاربری نبینه
            await asyncio.sleep(15)
            try:
                await msg.delete()
            except:
                pass
            self.honeypot_msg_ids.discard(msg.id)
        except Exception as e:
            pass  # silently skip if channel invalid

    async def _honeypot_loop(self):
        await asyncio.sleep(30)
        while True:
            try:
                await self.deploy_honeypot()
            except Exception:
                pass
            await asyncio.sleep(random.randint(550, 700))

    async def bg_scan(self):
        """حلقه اصلی پس‌زمینه دفاع: کاشت هانی‌پات + پاکسازی کاربران غیرفعال"""
        asyncio.create_task(self._honeypot_loop())
        while True:
            await asyncio.sleep(120)
            now = time.time()
            for uid in list(self.user_join_times.keys()):
                try:
                    if await self.is_admin(uid):
                        continue
                    in_time = now - self.user_join_times[uid]
                    last_act = now - self.last_activity.get(uid, self.user_join_times[uid])
                    if in_time > 180 and last_act > 180 and uid in self.pending_captcha:
                        await self.ban(uid)
                        await self.alert("high", "کاربر غیرفعال مشکوک",
                            f"کاربر با آیدی {uid} بدون فعالیت مسدود شد.")
                        self.pending_captcha.discard(uid)
                except Exception:
                    pass

    async def monitor_message(self, message):
        if not message or not message.from_user:
            return
        uid = message.from_user.id
        if await self.is_admin(uid):
            return
        # آپدیت آخرین فعالیت
        self.last_activity[uid] = time.time()
        text = (message.text or message.caption or "").lower()
        # تشخیص هانی‌پات
        if "hp_trap_" in text or "hp_admin_" in text or "hp_support_" in text:
            await self.ban(uid)
            try:
                await message.delete()
            except:
                pass
            await self.alert("critical", "🍯 هانی‌پات فعال شد!",
                f"کاربر <b>{message.from_user.first_name}</b> (آیدی <code>{uid}</code>) "
                f"تله مخفی هانی‌پات را خواند → فوراً بن شد.")
            return
        # امتیازدهی بر اساس نام/یوزرنیم
        try:
            u = message.from_user
            name = ((u.first_name or "") + " " + (u.last_name or "")).strip()
            uname = (u.username or "").lower()
            score = 0
            bad_name_keys = ["sms", "verify", "bonus", "airdrop", "win", "prize", "gift",
                             "درآمد", "کسب درآمد", "پول", "هلد", "ایردراپ", "سود",
                             "support", "admin", "official", "team", "پشتیبان", "ادمین"]
            if uname and any(k in uname for k in bad_name_keys):
                score += 4
            if name.replace(" ","").isdigit() and len(name) > 5:
                score += 3
            if name and any(k in name.lower() for k in ["support", "admin", "official", "پشتیبان", "ادمین"]):
                score += 4
            if score >= 6:
                await self.restrict(uid)
                try:
                    await message.delete()
                except:
                    pass
                await self.alert("high", "پروفایل مشکوک تشخیص داده شد",
                    f"کاربر {name} (@{uname or '—'}) با آیدی {uid} مشکوک به اسپم بود، موقتا محدود شد.")
        except Exception:
            pass

    async def monitor_callback(self, callback):
        if not callback or not callback.from_user:
            return
        uid = callback.from_user.id
        if await self.is_admin(uid):
            return
        data = (callback.data or "").lower()
        if "hp_" in data or "trap" in data or "honeypot" in data:
            try:
                await callback.answer("⚠️ دسترسی غیرمجاز!", show_alert=True)
            except:
                pass
            await self.ban(uid)
            await self.alert("critical", "🍯 کلیک روی دکمه هانی‌پات",
                f"کاربر <b>{callback.from_user.first_name}</b> (آیدی <code>{uid}</code>) "
                f"روی لینک مخفی هانی‌پات کلیک کرد → بن شد.")
