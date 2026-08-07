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
import sqlite3
from pyrogram import Client
from pyrogram.errors import FloodWait, ChatAdminRequired, SessionPasswordNeeded, PhoneCodeInvalid, PhoneCodeExpired, AuthKeyDuplicated, AuthKeyUnregistered
from pyrogram.raw import functions, types

# ===== قفل سراسری برای جلوگیری از database is locked =====
# یک قفل کلی برای اینکه دو Client همزمان connect/disconnect نکنن
_global_connect_lock = asyncio.Lock()

# قفل به ازای هر فایل سشن - برای اینکه دو عملیات همزمان روی یک فایل
# سشن کار نکنن (مثلاً اسکن خودکار + اسکن دستی همزمان با یک اکانت)
_session_locks: dict = {}

def _get_session_lock(session_path: str) -> asyncio.Lock:
    """Get or create an asyncio lock for a specific session file."""
    key = os.path.realpath(session_path) if session_path else session_path
    if key not in _session_locks:
        _session_locks[key] = asyncio.Lock()
    return _session_locks[key]


def _enable_wal_on_session(session_path: str):
    """Set WAL journal mode on a Pyrogram session SQLite file.
    WAL allows concurrent reads + one writer without locking issues."""
    if not session_path:
        return
    db_path = session_path + ".session"
    try:
        if os.path.exists(db_path):
            conn = sqlite3.connect(db_path, timeout=5)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA busy_timeout=5000")
            conn.close()
            print(f"✅ WAL mode enabled on {os.path.basename(db_path)}", flush=True)
    except Exception as e:
        print(f"⚠️ WAL setup on {db_path}: {e}", flush=True)

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
    def __init__(self, session_name, api_id, api_hash, phone=None, in_memory=False, device_fp=None, force_fresh=False):
        if device_fp:
            fp = device_fp
        else:
            fp = random.choice(DEVICE_FP)
        # force_fresh=True: استفاده از یک فایل سشن کاملا مجزا (نه در حافظه) تا بعد از لاگین
        # با rename کردن بتوانیم آن را به دائمی تبدیل کنیم. این روش ۱۰۰٪ پایدار است و از export_session_string
        # که ممکن است auth key را ابطال کند استفاده نمی کند.
        self._tmp_finalize = False
        self._perm_session_path = None
        if phone and force_fresh:
            import secrets
            tmp_fname = f"_newtmp_{safe_phone_filename(phone)}_{int(time.time())}_{secrets.token_hex(3)}"
            session_path = os.path.join(SESSIONS_DIR, tmp_fname)
            self._perm_session_path = os.path.join(SESSIONS_DIR, f"acc_{safe_phone_filename(phone)}")
            # هر بار که force_fresh میایم اگر سشن دائمی قدیمی وجود دارد برای لاگین جدید از نو شروع میکنیم
            # ولی قبلی رو پاک نمیکنیم مگر بعد از لاگین موفق
        elif phone and not in_memory:
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
            no_updates=True,
            takeout=False
        )
        self.found_users = {}
        self.total_api_calls = 0
        self.start_time = None
        self._progress_cb = None
        self._last_progress = 0
        self._stage = "در حال آماده سازی..."
        self._last_added_name = "-"
        self._last_progress_val = 0
        self._incremental_save_cb = None  # ذخیره تدریجی
        self._stop_requested = False  # درخواست توقف از کاربر

    def request_stop(self):
        self._stop_requested = True

    def get_fp_dict(self):
        return self.fp_used

    async def persist_to_permanent(self):
        """سشن از فایل موقت را با rename به نام دائمی تبدیل میکند (۱۰۰٪ پایدار، auth key عوض نمیشود)"""
        if not self._perm_session_path:
            return
        sess_lock = _get_session_lock(self.app.name)
        perm_lock = _get_session_lock(self._perm_session_path)
        async with sess_lock:
            async with perm_lock:
                async with _global_connect_lock:
                    try:
                        await self.app.storage.close()
                        # Find actual temp session file paths (Pyrogram workdir is "." and app.name has full path)
                        tmp_base = self.app.name
                        perm_base = self._perm_session_path
                        # Rename all related session files (including .wal, .shm, .session)
                        import glob as _glob
                        for tmpf in _glob.glob(tmp_base + ".session*") + _glob.glob(tmp_base + ".session-*"):
                            suf = tmpf[len(tmp_base):]
                            permf = perm_base + suf
                            if os.path.exists(permf):
                                try: os.remove(permf)
                                except: pass
                            os.replace(tmpf, permf)
                        # فعال کردن WAL روی سشن دائمی
                        _enable_wal_on_session(perm_base)
                        # آپدیت لاک‌ها: لاک مسیر موقت رو حذف و به مسیر دائمی منتقل کن
                        if self.app.name in _session_locks:
                            old_lock = _session_locks.pop(self.app.name)
                            _session_locks[perm_base] = old_lock
                        print(f"💾 سشن به {perm_base} منتقل شد", flush=True)
                    except Exception as e:
                        print(f"⚠️ خطا در ذخیره دائمی سشن: {e}", flush=True)
                        import traceback; traceback.print_exc()

    async def connect(self):
        """اتصال امن با قفل سراسری + قفل per-session + WAL mode"""
        sess_name = self.app.name  # e.g. saved_sessions/acc_98912xxxxx
        sess_lock = _get_session_lock(sess_name)

        async with sess_lock:  # اول قفل مخصوص این سشن
            async with _global_connect_lock:  # بعد قفل سراسری
                # فعال کردن WAL mode قبل از اتصال
                _enable_wal_on_session(sess_name)

                try:
                    await self.app.connect()
                except (AuthKeyDuplicated, AuthKeyUnregistered):
                    raise

                # مجدداً WAL رو بعد از اتصال هم ست کن (Pyrogram ممکنه دیتابیس
                # رو موقع connect باز/بسته کنه و تنظیمات رو reset کنه)
                _enable_wal_on_session(sess_name)

                self.start_time = time.time()

    async def _progress(self, text=None, force=False):
        """گزارش پیشرفت زنده با نوار پراگرس بار متحرک و درصد تقریبی"""
        now = time.time()
        if text:
            self._stage = text
        if not force and now - self._last_progress < 2:  # آپدیت هر ۲ ثانیه
            return
        self._last_progress = now
        if self._progress_cb:
            try:
                elapsed = int(time.time() - self.start_time) if self.start_time else 0
                mins = elapsed // 60
                secs = elapsed % 60
                count = len(self.found_users)
                speed = int(count / (elapsed/60)) if elapsed > 10 else count*3
                # نوار پیشرفت متحرک (پر شدن به تدریج بر اساس تعداد پیدا شده)
                # تخمین پیشرفت از روی استیج
                stage_weights = {
                    "در حال اتصال": 2,
                    "آماده سازی": 5,
                    "بارگذاری لیست چت": 10,
                    "پیدا کردن گروه": 15,
                    "پیدا کردن کانال": 15,
                    "گروه/کانال هدف": 15,
                    "بررسی عضویت": 18,
                    "لیست مستقیم": 35,
                    "صفحه بندی جستجو": 55,
                    "جستجو با حرف": 60,
                    "تاریخچه پیام": 75,
                    "بررسی تاریخچه": 80,
                    "اعضای جدید": 88,
                    "اسکن ری اکشن": 70,
                    "اسکن کانال": 65,
                    "پست های کانال": 65,
                    "خروج": 95,
                    "تمام": 100,
                }
                pct = 20
                for key, val in stage_weights.items():
                    if key in self._stage:
                        pct = val
                        break
                # در طول صفحه بندی به تدریج درصد اضافه کن
                if "حرف" in self._stage and count > 0:
                    pct = min(65, 40 + count // 200)
                if "تاریخچه" in self._stage and count > 0:
                    pct = min(85, 65 + count // 150)
                pct = min(100, max(5, pct))
                filled = int(pct / 4)  # 25 خانه
                empty = 25 - filled
                bar = "🟩" * filled + "⬜" * empty
                dot = ["🟢","🟡","🟢","🔵","🟣","🟢"][int(elapsed/1.5) % 6]
                text_out = f"{dot} **وضعیت زنده عملیات**\n\n"
                text_out += f"{bar} **{pct}%**\n\n"
                text_out += f"🎯 مرحله: {self._stage}\n"
                text_out += f"✅ پیدا شده: **{count:,}** نفر\n"
                text_out += f"⏱️ زمان: {mins:02d}:{secs:02d}\n"
                text_out += f"⚡ سرعت: ~{speed} نفر در دقیقه\n"
                if self._last_added_name and self._last_added_name != "-":
                    text_out += f"👤 آخرین: {self._last_added_name[:25]}\n"
                if elapsed > 30:
                    text_out += f"\n⏳ در حال کار، صبر کنید..."
                # Return tuple of (text, reply_markup) if progress_cb supports stop button
                # We just return text; caller handles the stop button
                await self._progress_cb(text_out)
                if self._stop_requested:
                    self._stage = "توقف توسط کاربر..."
                    await self._progress_cb(text_out + "\n\n🛑 درخواست توقف داده شد...")
                    return
            except Exception:
                pass

    async def human_sleep(self, min_t=0.3, max_t=1.2):
        if self._stop_requested:
            return
        t = random.uniform(min_t, max_t)
        if random.random() < 0.05:
            t += random.uniform(0.8, 2.0)
        end_t = time.time() + t
        while time.time() < end_t:
            if self._stop_requested:
                return
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
        # ذخیره تدریجی در دیتابیس هر ۵ نفر تا در صورت کرش چیزی از بین نرود
        if self._incremental_save_cb and self._last_progress_val % 5 == 0:
            try:
                await self._incremental_save_cb(list(self.found_users.values()))
            except Exception:
                pass
        if self._last_progress_val % 3 == 0:
            await self._progress()

    async def scrape_direct_paginated(self, chat_id):
        print("\n🔍 روش ۱: لیست مستقیم...", flush=True)
        self._stage = "در حال استخراج از لیست مستقیم اعضا"
        await self._progress(force=True)
        count_added = 0
        try:
            async for member in self.app.get_chat_members(chat_id, limit=10000):
                if self._stop_requested:
                    return True
                self.total_api_calls +=1
                await self.add_user(member.user, "direct_list")
                count_added +=1
                if count_added % 10 == 0:
                    self._stage = f"📋 لیست مستقیم اعضا، {count_added} نفر..."
                    await self._progress()
                await self.human_sleep(0.1, 0.3)
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
            if self._stop_requested:
                return True
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
            if self._stop_requested:
                return
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
            if self._stop_requested:
                return
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

    async def scrape_reactions_dedicated(self, chat_id, limit=5000):
        """🆕 روش ۴: اسکن اختصاصی ری‌اکشن‌ها — مستقیم میره سراغ پیام‌هایی که ری‌اکشن دارن
        و لیست کامل ری‌اکت‌دهنده‌ها رو استخراج میکنه. این روش برای کسایی که فقط
        ری‌اکشن میدن و هیچوقت پیام نمیدن عالیه."""
        print(f"\n🔍 روش ۴: اسکن اختصاصی ری‌اکشن ها (تا {limit} پیام)...", flush=True)
        self._stage = f"در حال اسکن ری‌اکشن ها (تا {limit} پیام)"
        await self._progress(force=True)
        msg_count = 0
        reaction_count = 0
        async for msg in self.app.get_chat_history(chat_id, limit=limit):
            if self._stop_requested:
                return
            self.total_api_calls += 1
            msg_count += 1

            # فقط پیام‌هایی که ری‌اکشن دارن رو پردازش کن
            if not msg.reactions or not msg.reactions.reactions:
                if msg_count % 200 == 0:
                    self._stage = f"اسکن ری‌اکشن: {msg_count} پیام بررسی شد، {reaction_count} ری‌اکت پیدا شد"
                    await self._progress()
                await self.human_sleep(0.03, 0.08)
                continue

            for react in msg.reactions.reactions:
                if self._stop_requested:
                    return
                emoji = getattr(react, 'emoji', '👍')
                count_hint = getattr(react, 'count', 0) or 0
                # اگه تعداد ری‌اکت‌ها خیلی زیاده، با offset صفحه‌بندی کن
                offset = 0
                batch_limit = min(200, max(50, count_hint))
                while True:
                    try:
                        reactors = await self.app.get_message_reactions(
                            chat_id, msg.id, emoji, limit=batch_limit, offset=offset
                        )
                        if not reactors:
                            break
                        for r in reactors:
                            if r and getattr(r, 'peer', None) and getattr(r.peer, 'user_id', None):
                                try:
                                    u = await self.app.get_users(r.peer.user_id)
                                    await self.add_user(u, f"ری‌اکشن_{emoji}")
                                    reaction_count += 1
                                except:
                                    # Fallback: add minimal info without full get_users
                                    uid = r.peer.user_id
                                    if uid not in self.found_users:
                                        self._last_added_name = str(uid)
                                        self.found_users[uid] = {
                                            "user_id": uid,
                                            "first_name": str(uid),
                                            "last_name": "",
                                            "username": "",
                                            "is_premium": "نامشخص",
                                            "source": f"ری‌اکشن_{emoji}"
                                        }
                                        reaction_count += 1
                        if len(reactors) < batch_limit:
                            break
                        offset += batch_limit
                        await self.human_sleep(0.3, 0.6)
                    except FloodWait as e:
                        await self.handle_flood(e)
                    except:
                        break

                await self.human_sleep(0.08, 0.2)

            if msg_count % 100 == 0:
                self._stage = f"اسکن ری‌اکشن: {msg_count} پیام | {reaction_count} کاربر از ری‌اکشن"
                await self._progress()

        print(f"✅ اسکن ری‌اکشن: {msg_count} پیام بررسی شد، {reaction_count} کاربر از ری‌اکشن استخراج شد", flush=True)

    async def scrape_channel_posts(self, chat_id, limit=5000):
        """🆕 روش ۵: اسکن مخصوص کانال — پست‌های کانال، نویسنده‌ها،
        فرواردها، و ری‌اکشن‌ها رو استخراج میکنه.
        برای کانال‌هایی که get_chat_members روشون جواب نمیده."""
        print(f"\n🔍 روش ۵: اسکن پست های کانال (تا {limit} پست)...", flush=True)
        self._stage = f"در حال اسکن پست های کانال (تا {limit} پست)"
        await self._progress(force=True)
        post_count = 0
        authors_found = 0
        reactors_found = 0

        async for msg in self.app.get_chat_history(chat_id, limit=limit):
            if self._stop_requested:
                return
            self.total_api_calls += 1
            post_count += 1

            # نویسنده پست (برای کانال‌هایی که با اکانت کاربری پست می‌ذارن)
            if msg.from_user:
                await self.add_user(msg.from_user, "نویسنده_کانال")
                authors_found += 1

            # نویسنده hidden (sender_chat برای پست‌های امضا شده با نام کانال)
            if msg.sender_chat and hasattr(msg.sender_chat, 'id'):
                # sender_chat خودش یک چت هست، ولی میتونیم ثبتش کنیم
                pass

            # فروارد از کانال‌های دیگه
            if msg.forward_from:
                await self.add_user(msg.forward_from, "فوروارد_کانال")
            if msg.forward_from_chat:
                # forward_from_chat خودش چت هست، ولی info مفیده
                pass
            if msg.forward_sender_name:
                # اسم فرستنده بدون اکانت - نمیشه استخراج کرد
                pass

            # ری‌اکشن‌های پست‌های کانال — منبع عالی برای استخراج
            if msg.reactions and msg.reactions.reactions:
                for react in msg.reactions.reactions:
                    if self._stop_requested:
                        return
                    emoji = getattr(react, 'emoji', '👍')
                    count_hint = getattr(react, 'count', 0) or 0
                    batch_limit = min(200, max(50, count_hint))
                    offset = 0
                    while True:
                        try:
                            reactors = await self.app.get_message_reactions(
                                chat_id, msg.id, emoji, limit=batch_limit, offset=offset
                            )
                            if not reactors:
                                break
                            for r in reactors:
                                if r and getattr(r, 'peer', None) and getattr(r.peer, 'user_id', None):
                                    try:
                                        u = await self.app.get_users(r.peer.user_id)
                                        await self.add_user(u, f"ری‌اکشن_کانال_{emoji}")
                                        reactors_found += 1
                                    except:
                                        uid = r.peer.user_id
                                        if uid not in self.found_users:
                                            self.found_users[uid] = {
                                                "user_id": uid,
                                                "first_name": str(uid),
                                                "last_name": "",
                                                "username": "",
                                                "is_premium": "نامشخص",
                                                "source": f"ری‌اکشن_کانال_{emoji}"
                                            }
                                            reactors_found += 1
                            if len(reactors) < batch_limit:
                                break
                            offset += batch_limit
                            await self.human_sleep(0.3, 0.6)
                        except FloodWait as e:
                            await self.handle_flood(e)
                        except:
                            break
                    await self.human_sleep(0.08, 0.2)

            # Entity mentions in post captions
            if msg.entities:
                for ent in msg.entities:
                    if ent.type in ("mention", "text_mention") and ent.user:
                        await self.add_user(ent.user, "منشن_کانال")

            if post_count % 100 == 0:
                self._stage = f"اسکن کانال: {post_count} پست | {authors_found} نویسنده | {reactors_found} ری‌اکت‌دهنده"
                await self._progress()
            await self.human_sleep(0.04, 0.12)

        print(f"✅ اسکن کانال: {post_count} پست | {authors_found} نویسنده | {reactors_found} ری‌اکت‌دهنده", flush=True)

    async def run_full_scrape(self, chat_id, progress_cb=None, incremental_save_cb=None):
        self._progress_cb = progress_cb
        self._incremental_save_cb = incremental_save_cb
        self._last_progress = 0
        self.start_time = time.time()
        self._stage = "در حال اتصال..."
        print("="*60, flush=True)
        print("🚀 شروع حمله MAX MODE", flush=True)
        print("="*60, flush=True)

        # یک وظیفه پس زمینه که هر ۲ ثانیه وضعیت را آپدیت نگه میدارد
        heartbeat_on = True
        async def heartbeat():
            while heartbeat_on:
                await self._progress(force=True)
                await asyncio.sleep(2)

        hb_task = asyncio.create_task(heartbeat())

        try:
            self._stage = "🔄 در حال بارگذاری لیست چت ها..."
            await self._progress(force=True)
            print("🔄 در حال بارگذاری لیست چت ها...", flush=True)
            all_chats = {}
            try:
                cnt = 0
                async for d in self.app.get_dialogs(limit=2000):
                    all_chats[d.chat.id] = d.chat
                    cnt += 1
                    if cnt % 100 == 0:
                        self._stage = f"🔄 در حال بارگذاری لیست چت ها... {cnt} چت"
                    await asyncio.sleep(0.01)
                print(f"✅ لیست چت ها بارگذاری شد: {cnt} چت", flush=True)
                await asyncio.sleep(1)
            except Exception as e:
                print(f"خطا در چت ها: {e}", flush=True)

            self._stage = "🔎 در حال پیدا کردن گروه/کانال هدف"
            await self._progress(force=True)
            target_found = None
            target_id_resolved = None
            try:
                peer = await self.app.resolve_peer(chat_id)
                target_found = await self.app.get_chat(chat_id)
                target_id_resolved = target_found.id
                print(f"🎯 هدف: {target_found.title} | {target_found.id} | type={target_found.type}", flush=True)
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
                        raise Exception("❌ گروه/کانال پیدا نشد! لطفا یک بار در تلگرام باز و اسکرول کنید.")
            chat_id = target_id_resolved

            # تشخیص نوع چت: کانال یا گروه/سوپرگروه
            is_channel = str(target_found.type).lower() == "chattype.channel"
            chat_type_str = "کانال" if is_channel else "گروه"
            print(f"✅ هدف: {target_found.title} | نوع: {chat_type_str}", flush=True)

            self._stage = f"✅ هدف: {target_found.title} | نوع: {chat_type_str} | آماده‌سازی شروع استخراج..."
            await self._progress(force=True)

            self._stage = f"🚀 شروع استخراج از {target_found.title}"
            await self._progress(force=True)

            if is_channel:
                # ═══════ استراتژی مخصوص کانال ═══════
                print("📡 حالت کانال فعال شد - استفاده از متدهای مخصوص کانال", flush=True)

                # ۱. اسکن پست‌های کانال (نویسنده‌ها + ری‌اکشن‌ها + فرواردها)
                await self.scrape_channel_posts(chat_id, limit=10000)

                # ۲. اسکن اختصاصی ری‌اکشن‌ها (دور دوم با focus بیشتر روی ری‌اکشن‌ها)
                await self.scrape_reactions_dedicated(chat_id, limit=5000)

                # ۳. تلاش برای get_chat_members (فقط برای کانال‌هایی که ادمین هستیم جواب میده)
                try:
                    await self.scrape_direct_paginated(chat_id)
                except Exception as e:
                    print(f"⚠️ get_chat_members روی کانال جواب نداد (طبیعیه): {e}", flush=True)

            else:
                # ═══════ استراتژی مخصوص گروه/سوپرگروه ═══════
                # ۱. لیست مستقیم اعضا + صفحه‌بندی الفبایی
                await self.scrape_direct_paginated(chat_id)

                # ۲. اسکن تاریخچه پیام‌ها
                await self.scrape_full_history(chat_id, limit=3000)

                # ۳. اسکن پیام‌های ورود عضو جدید
                await self.scrape_join_events(chat_id)

                # ۴. 🆕 اسکن اختصاصی ری‌اکشن‌ها (کسایی که فقط ری‌اکشن میدن)
                await self.scrape_reactions_dedicated(chat_id, limit=5000)

            # ذخیره نهایی
            if self._incremental_save_cb:
                try:
                    await self._incremental_save_cb(list(self.found_users.values()))
                except Exception:
                    pass
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
        sess_lock = _get_session_lock(self.app.name)
        async with sess_lock:
            async with _global_connect_lock:
                try:
                    await asyncio.sleep(0.3)
                    await self.app.disconnect()
                except Exception as e:
                    print(f"هنگام قطع: {e}", flush=True)
