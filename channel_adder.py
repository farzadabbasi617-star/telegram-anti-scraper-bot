"""
╔══════════════════════════════════════════════════════════╗
║         🚀 Telegram Channel Member Adder               ║
║    AddContact + InviteToChannel — نسخه ساده و پایدار    ║
╚══════════════════════════════════════════════════════════╝

فقط یک کار: اضافه کردن ممبر به کانال تلگرام
متد: AddContact → InviteToChannel (استاندارد حرفه‌ای)

نحوه استفاده:
    pip install pyrogram tgcrypto
    python channel_adder.py

Requirements:
    - اکانت باید ادمین کانال باشه (دسترسی Invite Users)
    - API_ID و API_HASH از environment variables یا my.telegram.org
"""

import asyncio
import os
import sys
import csv
import io
import time
import random
import json
from datetime import datetime

from pyrogram import Client
from pyrogram.errors import (
    FloodWait, PeerIdInvalid, ChatAdminRequired,
    SessionPasswordNeeded, PhoneCodeExpired, PhoneCodeInvalid,
    UserAlreadyParticipant, UserPrivacyRestricted,
    UserNotMutualContact, UsersTooMuch, UserBannedInChannel,
    ChannelsTooMuch, ChannelPrivate
)
from pyrogram.raw.functions.contacts import AddContact
from pyrogram.raw.functions.channels import InviteToChannel

# ══════════════════════════════════════════════
# تنظیمات — از environment variables
# ══════════════════════════════════════════════

API_ID = int(os.environ.get("API_ID", 6))
API_HASH = os.environ.get("API_HASH", "eb06d4abfb49dc3eeb1aeb98ae0f581e")

SESSIONS_DIR = "sessions"
DATA_DIR = "data"
os.makedirs(SESSIONS_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

# حداکثر ادد در هر اکانت (برای جلوگیری از بن)
MAX_ADD_PER_ACCOUNT = 30

# فیلتر user ID معتبر
MIN_UID = 10_000
MAX_UID = 10 ** 11

# Device fingerprints
DEVICES = [
    {"device_model": "Samsung Galaxy S24 Ultra", "system_version": "Android 14", "app_version": "10.13.2", "lang_code": "fa"},
    {"device_model": "iPhone 15 Pro Max", "system_version": "iOS 17.6.1", "app_version": "10.15", "lang_code": "fa"},
    {"device_model": "Xiaomi 14 Pro", "system_version": "HyperOS 1.0", "app_version": "10.12.4", "lang_code": "en"},
]

# ══════════════════════════════════════════════
# لاگین و مدیریت اکانت
# ══════════════════════════════════════════════

def load_accounts():
    """بارگذاری لیست اکانت‌های ذخیره شده"""
    path = os.path.join(DATA_DIR, "accounts.json")
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return {}

def save_accounts(accs):
    """ذخیره لیست اکانت‌ها"""
    path = os.path.join(DATA_DIR, "accounts.json")
    with open(path, "w") as f:
        json.dump(accs, f, indent=2, ensure_ascii=False)

def load_add_limits():
    path = os.path.join(DATA_DIR, "add_limits.json")
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return {}

def save_add_limits(limits):
    path = os.path.join(DATA_DIR, "add_limits.json")
    with open(path, "w") as f:
        json.dump(limits, f, indent=2, ensure_ascii=False)

def load_added_history():
    path = os.path.join(DATA_DIR, "added_history.json")
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return {}

def save_added_history(hist):
    path = os.path.join(DATA_DIR, "added_history.json")
    with open(path, "w") as f:
        json.dump(hist, f, indent=2, ensure_ascii=False)

def is_already_added(channel_id, user_id):
    hist = load_added_history()
    key = str(channel_id)
    return user_id in hist.get(key, [])

def mark_added(channel_id, channel_name, user_id):
    hist = load_added_history()
    key = str(channel_id)
    if key not in hist:
        hist[key] = []
    hist[key].append(user_id)
    hist[f"{key}_name"] = channel_name
    save_added_history(hist)


async def login_account():
    """لاگین اکانت جدید و ذخیره سشن"""
    print("\n" + "="*50)
    print("📱 افزودن اکانت جدید")
    print("="*50)

    phone = input("📞 شماره تلفن (مثال +989123456789): ").strip()
    if not phone.startswith("+"):
        phone = "+" + phone

    fp = random.choice(DEVICES)
    session_name = os.path.join(SESSIONS_DIR, f"acc_{''.join(c for c in phone if c.isdigit())}")

    client = Client(
        session_name,
        api_id=API_ID,
        api_hash=API_HASH,
        phone_number=phone,
        device_model=fp["device_model"],
        system_version=fp["system_version"],
        app_version=fp["app_version"],
        lang_code=fp["lang_code"],
        in_memory=False,
        sleep_threshold=30,
        no_updates=True,
    )

    try:
        await client.connect()
        sent = await client.send_code(phone)
        code = input(f"\n✅ کد تایید به {phone} ارسال شد\n📱 کد ۵ رقمی: ").strip()

        try:
            await client.sign_in(phone, sent.phone_code_hash, code)
        except SessionPasswordNeeded:
            pwd = input("🔐 این اکانت 2FA داره. رمز یا کد TOTP: ").strip()
            await client.check_password(pwd)

        me = await client.get_me()
        print(f"\n✅ خوش آمدی {me.first_name}!")

        # ذخیره اطلاعات اکانت
        accs = load_accounts()
        accs[phone] = {
            "name": f"{me.first_name or ''} {me.last_name or ''}".strip(),
            "user_id": me.id,
            "username": me.username or "",
            "phone": phone,
            "session_path": session_name,
            "device_fp": fp,
            "added_at": int(time.time()),
        }
        save_accounts(accs)

        await client.disconnect()
        print(f"💾 سشن ذخیره شد: {session_name}.session")
        return phone

    except (PhoneCodeExpired, PhoneCodeInvalid) as e:
        print(f"❌ کد نامعتبر یا منقضی: {e}")
        await client.disconnect()
        return None
    except Exception as e:
        print(f"❌ خطا: {e}")
        try: await client.disconnect()
        except: pass
        return None


# ══════════════════════════════════════════════
# اسکرپ کاربران از گروه/کانال
# ══════════════════════════════════════════════

async def scrape_users_from_chat(client, chat_id, max_msgs=5000):
    """استخراج کاربران از تاریخچه پیام یک گروه/کانال"""
    users = {}
    print(f"\n🔍 اسکن گروه/کانال {chat_id}...")

    # روش 1: تاریخچه پیام‌ها
    count = 0
    async for msg in client.get_chat_history(chat_id, limit=max_msgs):
        count += 1
        if msg.from_user:
            u = msg.from_user
            if not getattr(u, 'is_bot', False) and not getattr(u, 'deleted', False):
                if MIN_UID < u.id < MAX_UID:
                    users[u.id] = {
                        "user_id": u.id,
                        "username": u.username or "",
                        "first_name": u.first_name or "",
                        "last_name": u.last_name or "",
                    }
        if msg.forward_from:
            u = msg.forward_from
            if not getattr(u, 'is_bot', False) and MIN_UID < u.id < MAX_UID:
                users[u.id] = {
                    "user_id": u.id,
                    "username": u.username or "",
                    "first_name": u.first_name or "",
                    "last_name": u.last_name or "",
                }
        # mentions
        if msg.entities:
            for ent in msg.entities:
                if ent.user and MIN_UID < ent.user.id < MAX_UID:
                    u = ent.user
                    users[u.id] = {
                        "user_id": u.id,
                        "username": u.username or "",
                        "first_name": u.first_name or "",
                        "last_name": u.last_name or "",
                    }

        if count % 500 == 0:
            print(f"  📊 {count} پیام اسکن شد — {len(users)} کاربر پیدا شد")
            await asyncio.sleep(0.5)

    # روش 2: لیست اعضا (فقط گروه‌ها)
    try:
        async for member in client.get_chat_members(chat_id, limit=5000):
            u = member.user
            if not getattr(u, 'is_bot', False) and not getattr(u, 'deleted', False):
                if MIN_UID < u.id < MAX_UID:
                    users[u.id] = {
                        "user_id": u.id,
                        "username": u.username or "",
                        "first_name": u.first_name or "",
                        "last_name": u.last_name or "",
                    }
            if len(users) % 200 == 0:
                await asyncio.sleep(0.3)
    except Exception:
        pass  # کانال‌ها member list ندارن

    # روش 3: new_chat_members service messages
    try:
        async for msg in client.get_chat_history(chat_id, limit=3000):
            if msg.new_chat_members:
                for u in msg.new_chat_members:
                    if MIN_UID < u.id < MAX_UID:
                        users[u.id] = {
                            "user_id": u.id,
                            "username": u.username or "",
                            "first_name": u.first_name or "",
                            "last_name": u.last_name or "",
                        }
    except Exception:
        pass

    print(f"✅ مجموع: {len(users)} کاربر از {count} پیام")
    return users


def load_users_from_csv(filepath):
    """بارگذاری کاربران از فایل CSV"""
    users = {}
    with open(filepath, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                uid = int(row.get("user_id", 0) or 0)
                if MIN_UID < uid < MAX_UID:
                    users[uid] = {
                        "user_id": uid,
                        "username": row.get("username", ""),
                        "first_name": row.get("first_name", ""),
                        "last_name": row.get("last_name", ""),
                    }
            except (ValueError, TypeError):
                continue
    print(f"✅ {len(users)} کاربر از CSV لود شد")
    return users


def save_users_csv(users, filename):
    """ذخیره کاربران در CSV"""
    path = os.path.join(DATA_DIR, filename)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["user_id", "username", "first_name", "last_name"])
        writer.writeheader()
        for u in users.values():
            writer.writerow(u)
    print(f"💾 ذخیره شد: {path}")


# ══════════════════════════════════════════════
# 🚀 CORE: Add to Channel
# ══════════════════════════════════════════════

async def add_members_to_channel(client, channel_id, channel_name, user_ids, phone):
    """
    FIXED: Add members to channel with warmup + AddContact + InviteToChannel
    
    Improvements:
    - Scans account's groups first to resolve peers (warmup)
    - Falls back to direct resolve for remaining users
    - Progress reporting
    - Better delay strategy for 30-user limit
    """
    limits = load_add_limits()
    already = limits.get(phone, {}).get("added", 0)
    remaining = MAX_ADD_PER_ACCOUNT - already

    # Filter: skip already-added
    filtered = [uid for uid in user_ids if not is_already_added(channel_id, uid)]
    
    total = min(len(filtered), remaining)
    if total == 0:
        print("⚠️ هیچ کاربری برای ادد نیست (همه قبلاً اضافه شدن یا ظرفیت پر)")
        return 0, 0

    print(f"\n{'='*50}")
    print(f"🚀 شروع ادد به کانال: {channel_name}")
    print(f"📊 {total} نفر از {len(filtered)} کاربر")
    print(f"📱 اکانت: {phone}")
    print(f"📈 ظرفیت: {already}/{MAX_ADD_PER_ACCOUNT}")
    print(f"{'='*50}\n")

    # Resolve target channel once
    try:
        target_peer = await client.resolve_peer(channel_id)
    except Exception as e:
        print(f"❌ کانال پیدا نشد: {e}")
        return 0, 0

    added = 0
    failed = 0
    skipped = 0
    errors = {"peer": 0, "privacy": 0, "already": 0, "flood": 0, "channel_admin": 0, "other": 0}
    start_time = time.time()

    # ─── Warmup: scan account's groups to build peer cache ───
    print(f"🔥 Warmup: scanning groups to resolve peers...", flush=True)
    valid_peers = {}
    uid_set_for_warmup = set(filtered[:total])
    
    try:
        async for dialog in client.get_dialogs(limit=200):
            if "group" in str(dialog.chat.type).lower():
                try:
                    async for member in client.get_chat_members(dialog.chat.id, limit=500):
                        u = member.user
                        if u and u.id in uid_set_for_warmup:
                            try:
                                valid_peers[u.id] = await client.resolve_peer(u.id)
                            except: pass
                except: pass
                await asyncio.sleep(0.3)
                if len(valid_peers) >= total * 0.8:
                    break
        print(f"  ✅ Warmup: {len(valid_peers)}/{total} peers resolved", flush=True)
    except Exception as we:
        print(f"  ⚠️ Warmup error: {we}", flush=True)

    # Fallback: direct resolve for remaining
    for uid in filtered[:total]:
        if uid not in valid_peers:
            try:
                valid_peers[uid] = await client.resolve_peer(uid)
            except: pass
            await asyncio.sleep(0.02)
    
    print(f"  📊 Total resolved: {len(valid_peers)}/{total}", flush=True)

    # ─── Main add loop ───
    for i, uid in enumerate(filtered[:total]):
        try:
            # Get peer from warmup cache or resolve directly
            if uid in valid_peers:
                user_peer = valid_peers[uid]
            else:
                try:
                    user_peer = await client.resolve_peer(uid)
                    valid_peers[uid] = user_peer
                except Exception:
                    failed += 1
                    errors["peer"] += 1
                    skipped += 1
                    continue

            # AddContact (needed for channel invite)
            try:
                await client.invoke(
                    AddContact(
                        id=user_peer,
                        first_name=str(uid)[:30],
                        last_name="",
                        phone="",
                        add_phone_privacy_exception=False
                    )
                )
                await asyncio.sleep(0.3)
            except: pass  # already in contacts

            # InviteToChannel
            await client.invoke(
                InviteToChannel(
                    channel=target_peer,
                    users=[user_peer]
                )
            )

            added += 1
            mark_added(channel_id, channel_name, uid)

            # Update limits
            limits[phone] = {"added": already + added, "last_used": int(time.time())}
            save_add_limits(limits)

        except FloodWait as fw:
            failed += 1
            errors["flood"] += 1
            print(f"  ⏱️ FloodWait {fw.value}s — صبر...", flush=True)
            await asyncio.sleep(fw.value + 5)
            continue

        except UserAlreadyParticipant:
            failed += 1
            errors["already"] += 1
            mark_added(channel_id, channel_name, uid)
            await asyncio.sleep(1)
            continue

        except (UserPrivacyRestricted, UserNotMutualContact):
            failed += 1
            errors["privacy"] += 1
            await asyncio.sleep(random.randint(2, 5))
            continue

        except (ChatAdminRequired, ChannelPrivate):
            print(f"\n❌ ادمین نیستی یا کانال پرایوته!", flush=True)
            failed += 1
            errors["channel_admin"] += 1
            break

        except UsersTooMuch:
            failed += 1
            errors["other"] += 1
            await asyncio.sleep(random.randint(5, 10))
            continue

        except Exception as e:
            failed += 1
            es = str(e).lower()
            if "privacy" in es:
                errors["privacy"] += 1
            elif "already" in es:
                errors["already"] += 1
                mark_added(channel_id, channel_name, uid)
            else:
                errors["other"] += 1
            await asyncio.sleep(random.randint(2, 5))
            continue

        # Progress
        done = added + failed
        elapsed = int(time.time() - start_time)
        mins, secs = elapsed // 60, elapsed % 60
        speed = int(added / (elapsed / 60)) if elapsed > 30 else 0
        pct = int(done * 100 / total) if total > 0 else 0
        bar_filled = pct // 5
        bar = "█" * bar_filled + "░" * (20 - bar_filled)

        print(f"  [{bar}] {pct}% | ✅ {added} ❌ {failed} | ⏱ {mins:02d}:{secs:02d} | UID: {uid}", flush=True)

        # Delay (adjusted for 30-user limit)
        total_done = already + added
        if total_done > 25:
            delay = random.randint(12, 20)
        elif total_done > 15:
            delay = random.randint(8, 15)
        else:
            delay = random.randint(5, 10)
        await asyncio.sleep(delay)

    # Final report
    elapsed = int(time.time() - start_time)
    mins, secs = elapsed // 60, elapsed % 60

    print(f"\n{'='*50}")
    print(f"✅ عملیات تمام شد — {channel_name}")
    print(f"{'='*50}")
    print(f"✅ اضافه شده: {added}")
    print(f"❌ ناموفق:    {failed}")
    print(f"⏭ رد شده:    {skipped}")
    print(f"⏱ زمان:       {mins:02d}:{secs:02d}")
    print(f"📊 ظرفیت:     {already + added}/{MAX_ADD_PER_ACCOUNT}")

    if failed > 0:
        print(f"\n دلایل خطا:")
        if errors["peer"]:    print(f"   🔍 Peer Invalid: {errors['peer']}")
        if errors["privacy"]: print(f"   🔒 Privacy:      {errors['privacy']}")
        if errors["already"]: print(f"   👥 قبلاً عضو:     {errors['already']}")
        if errors["flood"]:   print(f"   ⏱ Flood:        {errors['flood']}")
        if errors["other"]:   print(f"   ❓ سایر:         {errors['other']}")

    print(f"{'='*50}\n")
    return added, failed



# ══════════════════════════════════════════════
# منوی اصلی
# ══════════════════════════════════════════════

async def main():
    print("\n" + "╔══════════════════════════════════════════╗")
    print("║   🚀 Telegram Channel Member Adder         ║")
    print("║   AddContact + InviteToChannel             ║")
    print("╚══════════════════════════════════════════════╝\n")

    while True:
        accs = load_accounts()
        limits = load_add_limits()

        print(f"📱 اکانت‌ها: {len(accs)}")
        for phone, info in accs.items():
            added = limits.get(phone, {}).get("added", 0)
            remaining = MAX_ADD_PER_ACCOUNT - added
            print(f"   📱 {phone} ({info.get('name','')}) — ادد: {added}/{MAX_ADD_PER_ACCOUNT} — باقیمانده: {remaining}")

        print(f"\n{'─'*40}")
        print("  1. ➕ افزودن اکانت جدید")
        print("  2. 🚀 ادد ممبر به کانال")
        print("  3. 🔍 اسکرپ کاربران از گروه")
        print("  4. 📄 بارگذاری CSV")
        print("  5. 📋 لیست کاربران موجود")
        print("  6. 🗑️ ریست محدودیت ادد")
        print("  0. خروج")
        print(f"{'─'*40}")

        choice = input("انتخاب: ").strip()

        if choice == "0":
            print("👋 خداحافظ!")
            break

        elif choice == "1":
            await login_account()

        elif choice == "2":
            if not accs:
                print("❌ اول یه اکانت اضافه کن (گزینه ۱)")
                continue
            await _flow_add_members(accs, limits)

        elif choice == "3":
            if not accs:
                print("❌ اول یه اکانت اضافه کن")
                continue
            await _flow_scrape(accs)

        elif choice == "4":
            path = input("مسیر فایل CSV: ").strip()
            if os.path.exists(path):
                users = load_users_from_csv(path)
                fname = f"imported_{int(time.time())}.csv"
                save_users_csv(users, fname)
                print(f"✅ {len(users)} کاربر آماده")
            else:
                print(f"❌ فایل پیدا نشد: {path}")

        elif choice == "5":
            # نمایش کاربران موجود در data/
            csv_files = [f for f in os.listdir(DATA_DIR) if f.endswith(".csv") and ("imported" in f or "scraped" in f)]
            if not csv_files:
                print("📭 هیچ لیستی نیست. اول اسکرپ کن یا CSV لود کن.")
            else:
                for f in csv_files:
                    fpath = os.path.join(DATA_DIR, f)
                    with open(fpath, "r") as fh:
                        cnt = sum(1 for _ in fh) - 1  # minus header
                    print(f"  📄 {f}: {cnt} کاربر")

        elif choice == "6":
            phone = input("شماره اکانت برای ریست (یا 'all'): ").strip()
            limits = load_add_limits()
            if phone == "all":
                limits = {}
                print("✅ همه محدودیت‌ها ریست شد")
            elif phone in limits:
                del limits[phone]
                print(f"✅ محدودیت {phone} ریست شد")
            else:
                print("❌ شماره پیدا نشد")
            save_add_limits(limits)


async def _flow_add_members(accs, limits):
    """فلو کامل ادد ممبر به کانال"""
    # انتخاب اکانت
    phones = list(accs.keys())
    available = [(p, MAX_ADD_PER_ACCOUNT - limits.get(p, {}).get("added", 0))
                 for p in phones if limits.get(p, {}).get("added", 0) < MAX_ADD_PER_ACCOUNT]

    if not available:
        print("❌ همه اکانت‌ها ظرفیتشون پر شده! ریست کن.")
        return

    print("\n📱 اکانت‌های آماده:")
    for i, (phone, cap) in enumerate(available):
        name = accs[phone].get("name", "")
        print(f"  {i+1}. {phone} ({name}) — ظرفیت: {cap}")

    if len(available) == 1:
        idx = 0
    else:
        idx = int(input("شماره اکانت: ").strip()) - 1

    phone = available[idx][0]
    remaining = available[idx][1]

    # اتصال
    fp = accs[phone].get("device_fp", random.choice(DEVICES))
    session_path = accs[phone].get("session_path", os.path.join(SESSIONS_DIR, f"acc_{''.join(c for c in phone if c.isdigit())}"))

    client = Client(
        session_path,
        api_id=API_ID,
        api_hash=API_HASH,
        device_model=fp["device_model"],
        system_version=fp["system_version"],
        app_version=fp["app_version"],
        lang_code=fp.get("lang_code", "fa"),
        in_memory=False,
        sleep_threshold=30,
        no_updates=True,
    )

    try:
        await client.connect()
        me = await client.get_me()
        print(f"\n✅ متصل: {me.first_name}")
    except Exception as e:
        print(f"❌ خطا اتصال: {e}")
        return

    # انتخاب کانال مقصد
    print("\n📡 کانال‌های شما:")
    channels = []
    try:
        async for dialog in client.get_dialogs(limit=500):
            if dialog.chat.type == "channel":
                cnt = getattr(dialog.chat, "members_count", 0) or 0
                channels.append((dialog.chat.title, dialog.chat.id, cnt))
                print(f"  {len(channels)}. {dialog.chat.title} ({cnt:,} عضو)")
    except Exception as e:
        print(f"⚠️ خطا در لود کانال‌ها: {e}")

    if channels:
        print(f"  {len(channels)+1}. ✍️ وارد کردن دستی آیدی")
        ch_choice = input("شماره کانال مقصد: ").strip()
        if int(ch_choice) == len(channels) + 1:
            channel_id = int(input("آیدی عددی کانال (با -100): ").strip())
            channel_name = "کانال دستی"
        else:
            channel_name, channel_id, _ = channels[int(ch_choice) - 1]
    else:
        channel_id = int(input("آیدی عددی کانال (با -100): ").strip())
        channel_name = "کانال"

    # بررسی ادمین بودن
    try:
        me_member = await client.get_chat_member(channel_id, "me")
        if me_member.status not in ["administrator", "creator"]:
            print("⚠️ اکانت شما ادمین این کانال نیست! ممکنه خطا بده.")
            cont = input("ادامه؟ (y/n): ").strip()
            if cont.lower() != 'y':
                await client.disconnect()
                return
    except Exception as e:
        print(f"⚠️ خطا در بررسی ادمین: {e}")

    # انتخاب منبع کاربران
    print(f"\n📂 منبع کاربران:")
    print("  1. 📄 از فایل CSV")
    print("  2. 🔍 اسکرپ از گروه")

    src = input("انتخاب: ").strip()
    user_ids = []

    if src == "1":
        # لیست CSV ها
        csv_files = [f for f in os.listdir(DATA_DIR) if f.endswith(".csv")]
        if not csv_files:
            print("❌ هیچ CSV نیست. اول اسکرپ کن یا CSV لود کن.")
            await client.disconnect()
            return
        print("\n📄 فایل‌ها:")
        for i, f in enumerate(csv_files):
            fpath = os.path.join(DATA_DIR, f)
            with open(fpath, "r") as fh:
                cnt = sum(1 for _ in fh) - 1
            print(f"  {i+1}. {f} ({cnt} کاربر)")
        fidx = int(input("شماره فایل: ").strip()) - 1
        users = load_users_from_csv(os.path.join(DATA_DIR, csv_files[fidx]))
        user_ids = list(users.keys())

    elif src == "2":
        # لیست گروه‌ها
        print("\n👥 گروه‌های شما:")
        groups = []
        async for dialog in client.get_dialogs(limit=500):
            if dialog.chat.type in ["supergroup", "group"]:
                cnt = getattr(dialog.chat, "members_count", 0) or 0
                groups.append((dialog.chat.title, dialog.chat.id, cnt))
                print(f"  {len(groups)}. {dialog.chat.title} ({cnt:,} عضو)")

        if not groups:
            print("❌ گروهی پیدا نشد")
            await client.disconnect()
            return

        gidx = int(input("شماره گروه: ").strip()) - 1
        gname, gid, gcnt = groups[gidx]
        print(f"\n🔍 اسکن {gname}...")
        users = await scrape_users_from_chat(client, gid)

        # ذخیره
        save_users_csv(users, f"scraped_{int(time.time())}.csv")
        user_ids = list(users.keys())

    if not user_ids:
        print("❌ کاربری پیدا نشد!")
        await client.disconnect()
        return

    random.shuffle(user_ids)
    print(f"\n📊 {len(user_ids)} کاربر آماده — ظرفیت: {remaining}")

    confirm = input("شروع ادد؟ (y/n): ").strip()
    if confirm.lower() != 'y':
        await client.disconnect()
        return

    # 🚀 ادد!
    added, failed = await add_members_to_channel(client, channel_id, channel_name, user_ids, phone)

    await client.disconnect()
    print(f"\n✅ تمام شد. {added} نفر اضافه شد، {failed} ناموفق.")


async def _flow_scrape(accs):
    """فلو اسکرپ کاربران از گروه"""
    phones = list(accs.keys())
    phone = phones[0]
    if len(phones) > 1:
        print("\n📱 اکانت‌ها:")
        for i, p in enumerate(phones):
            print(f"  {i+1}. {p}")
        idx = int(input("شماره اکانت: ").strip()) - 1
        phone = phones[idx]

    fp = accs[phone].get("device_fp", random.choice(DEVICES))
    session_path = accs[phone].get("session_path", os.path.join(SESSIONS_DIR, f"acc_{''.join(c for c in phone if c.isdigit())}"))

    client = Client(
        session_path,
        api_id=API_ID,
        api_hash=API_HASH,
        device_model=fp["device_model"],
        system_version=fp["system_version"],
        app_version=fp["app_version"],
        lang_code=fp.get("lang_code", "fa"),
        in_memory=False,
        sleep_threshold=30,
        no_updates=True,
    )

    try:
        await client.connect()
    except Exception as e:
        print(f"❌ خطا اتصال: {e}")
        return

    print("\n👥 گروه‌های شما:")
    groups = []
    try:
        async for dialog in client.get_dialogs(limit=500):
            if dialog.chat.type in ["supergroup", "group"]:
                cnt = getattr(dialog.chat, "members_count", 0) or 0
                groups.append((dialog.chat.title, dialog.chat.id, cnt))
                print(f"  {len(groups)}. {dialog.chat.title} ({cnt:,} عضو)")
    except Exception as e:
        print(f"⚠️ خطا: {e}")

    if not groups:
        print("❌ گروهی نیست")
        await client.disconnect()
        return

    gidx = int(input("شماره گروه: ").strip()) - 1
    gname, gid, _ = groups[gidx]

    users = await scrape_users_from_chat(client, gid)
    if users:
        fname = f"scraped_{int(time.time())}.csv"
        save_users_csv(users, fname)
    else:
        print("⚠️ کاربری پیدا نشد")

    await client.disconnect()


# ══════════════════════════════════════════════
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 خداحافظ!")
