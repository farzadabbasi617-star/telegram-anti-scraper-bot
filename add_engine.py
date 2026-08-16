"""
=================================================================
🧠 Add Engine — موتور ادد (ضد بن + ضد تکرار)
=================================================================
- تاخیرهای انسانی با نویز تصادفی و استراحت‌های دوره‌ای
- کش در حافظه لیست «هرگز دوباره ادد نشود» (صفر کوئری به ازای هر ممبر)
- ثبت کاربران ممنوعه (پروفایل قفل / لفت داده / آیدی نامعتبر)
"""
import time
import random
import logging
import re

import config
import db as _db

logger = logging.getLogger("antiscraper.add_engine")


# -----------------------------------------------------------------
# 🐌 Human-like delays (ضد بن شدن اکانت‌ها)
# -----------------------------------------------------------------

def human_delay(add_mode="fast"):
    """تاخیر شبیه‌سازی‌شده به رفتار انسان — با نویز تصادفی و مکث‌های گاه‌به‌گاه."""
    lo, hi = config.DELAY_RANGES.get(add_mode, config.DELAY_RANGES["fast"])
    base = random.uniform(lo, hi)
    # بعضی وقت‌ها مثل یک انسان واقعی بیشتر صبر می‌کند (چک کردن گوشی، حرف زدن و...)
    if random.random() < config.HUMAN_JITTER_CHANCE:
        base *= random.uniform(*config.HUMAN_JITTER_FACTOR)
    # نویز کوچک پایانی
    base *= random.uniform(0.9, 1.15)
    return base


def human_break_seconds(add_mode="fast"):
    """استراحت تصادفی بین دسته‌های ادد (قهوه/استراحت انسانی)"""
    lo, hi = config.BREAK_RANGES.get(add_mode, config.BREAK_RANGES["fast"])
    return random.randint(lo, hi)


# -----------------------------------------------------------------
# 🚫 Do-Not-Add cache (لیست ممنوعه در حافظه)
# -----------------------------------------------------------------

_BLOCKED_IDS_CACHE = {"ids": None, "ts": 0}
_BLOCKED_CACHE_TTL = 120  # ثانیه


def get_blocked_ids_cached():
    """ست آیدی کاربران ممنوعه (ادد شده قبلی + لیست ممنوعه) با کش ۲ دقیقه‌ای"""
    now = time.time()
    if _BLOCKED_IDS_CACHE["ids"] is None or (now - _BLOCKED_IDS_CACHE["ts"]) > _BLOCKED_CACHE_TTL:
        try:
            _BLOCKED_IDS_CACHE["ids"] = _db.get_blocked_user_ids()
            _BLOCKED_IDS_CACHE["ts"] = now
        except Exception as e:
            logger.warning("blocked cache err: %s", e)
            return set()
    return _BLOCKED_IDS_CACHE["ids"] or set()


def invalidate_blocked_cache():
    _BLOCKED_IDS_CACHE["ids"] = None
    _BLOCKED_IDS_CACHE["ts"] = 0


def mark_added_local(uid):
    """همگام‌سازی کش در حافظه بعد از هر ادد موفق (برای چک‌های بعدی بدون کوئری)"""
    try:
        if _BLOCKED_IDS_CACHE["ids"] is not None:
            _BLOCKED_IDS_CACHE["ids"].add(int(uid))
    except Exception:
        pass


def never_add_again(uid, reason=""):
    """حذف از دیتابیس ممبرها + ثبت در لیست «هرگز دوباره ادد نشود»"""
    try:
        _db.add_do_not_add(uid, reason)
    except Exception as e:
        logger.warning("dna err: %s", e)
    try:
        _db.delete_user(uid)
    except Exception as e:
        logger.warning("del err: %s", e)
    invalidate_blocked_cache()


def prefer_addable_members(members):
    """اول یوزرنیم‌دارها (نرخ عضویت واقعی خیلی بالاتر است)، بعد شماره‌دار، بعد فقط ID."""
    def _key(u):
        un = (u.get("username") or "").strip()
        ph = (u.get("phone") or "").strip()
        if un:
            return (0, un)
        if ph:
            return (1, ph)
        return (2, str(u.get("user_id") or 0))
    return sorted(members or [], key=_key)


def _looks_like_chat_ref(raw):
    s = (raw or "").strip()
    if not s:
        return False
    if s.lstrip("-").isdigit():
        return True
    if s.startswith("@") or "t.me/" in s or s.startswith("http"):
        return True
    # یوزرنیم عمومی تلگرام بدون @
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{3,31}", s):
        return True
    return False


def normalize_chat_ref(raw):
    """لینک / یوزرنیم / آیدی را به چیزی که get_chat می‌فهمد تبدیل می‌کند."""
    s = (raw or "").strip()
    if not s:
        return s
    if s.lstrip("-").isdigit():
        return int(s)
    if "t.me/" in s:
        tail = s.split("t.me/", 1)[1].split("?")[0].strip("/")
        if not tail:
            return s
        if tail.startswith("+") or tail.startswith("joinchat/"):
            return s
        if tail.lstrip("-").isdigit():
            return int(tail)
        return "@" + tail.lstrip("@")
    if s.startswith("@"):
        return s
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{3,31}", s):
        return "@" + s
    return s


def resolve_add_target(cfg=None):
    """مقصد ادد را از config واقعی می‌گیرد — group_id=0 را «خالی» حساب نمی‌کند اگر نام معتبر باشد.
    دیگر بی‌صدا به @gament_super_gp سوییچ نمی‌کند مگر اینکه هیچ مقصدی نباشد."""
    if cfg is None:
        cfg = _db.get_config() or {}
    try:
        gid = int(cfg.get("group_id") or 0)
    except Exception:
        gid = 0
    name = (cfg.get("group_name") or "").strip()
    if gid:
        return gid
    # لینک / @یوزرنیم / آیدی عددی در نام → همان مقصد
    explicit = bool(name) and (
        name.startswith("@") or "t.me/" in name or name.startswith("http") or name.lstrip("-").isdigit()
    )
    if explicit:
        return normalize_chat_ref(name)
    try:
        dest = _db.most_used_add_dest()
        if dest:
            return dest
    except Exception:
        pass
    if _looks_like_chat_ref(name):
        return normalize_chat_ref(name)
    try:
        import config as _cfg
        fallback = getattr(_cfg, "DEFAULT_TARGET_USERNAME", "gament_super_gp")
    except Exception:
        fallback = "gament_super_gp"
    return "@" + str(fallback).lstrip("@")


def persist_target_setting(raw):
    """ذخیره مقصد از مینی‌اپ: آیدی عددی را جدا از نام نگه می‌دارد."""
    ref = normalize_chat_ref(raw)
    if isinstance(ref, int):
        _db.set_config(ref, str(raw).strip() or str(ref), True)
        return ref
    name = str(ref or raw or "").strip()
    _db.set_config(0, name, True)
    return name


def invite_did_not_join(updates, uid):
    """اگر InviteToChannel کاربر را در missing_invitees برگرداند، ادد واقعی نبوده."""
    if updates is None:
        return False
    missing = getattr(updates, "missing_invitees", None) or []
    for item in missing:
        mid = getattr(item, "user_id", None)
        if mid is None:
            mid = getattr(getattr(item, "user", None), "id", None)
        try:
            if int(mid) == int(uid):
                return True
        except Exception:
            continue
    return False


# وضعیت‌هایی که یعنی کاربر واقعاً داخل گروه است
_JOINED_STATUSES = frozenset({
    "member", "administrator", "creator", "owner", "admin", "restricted",
})

# وضعیت‌هایی که یعنی کاربر داخل گروه نیست — حتی اگر API ادد «موفق» گفته باشد
_NOT_JOINED_STATUSES = frozenset({
    "left", "banned", "kicked", "restricted_banned",
})


def _normalize_member_status(mem):
    """
    استخراج نام وضعیت به‌صورت یک توکن تمیز.

    ⚠️ باگی که این تابع رفع می‌کند (نسخه ۱.۴.۲):
    Pyrogram وضعیت را به‌صورت enum برمی‌گرداند و str() آن می‌شود
    'ChatMemberStatus.LEFT'. کد قبلی چک می‌کرد آیا زیررشته 'member'
    در آن هست — و رشته 'ChatMemberStatus.LEFT' شامل 'MEMBER' است!
    نتیجه: کاربرانی که گروه را ترک کرده یا بن شده بودند «عضو» شمرده
    می‌شدند و آمار ادد کاملاً غیرواقعی می‌شد.
    """
    st = getattr(mem, "status", None)
    if st is None:
        return ""
    # enum پایتون: از .value یا .name استفاده کن، نه str(enum)
    raw = getattr(st, "value", None)
    if raw is None:
        raw = getattr(st, "name", None)
    if raw is None:
        raw = str(st)
        # 'ChatMemberStatus.LEFT' → 'LEFT'
        if "." in raw:
            raw = raw.rsplit(".", 1)[-1]
    return str(raw).strip().lower()


async def confirm_joined(client, chat_id, uid, retries=2, pause=1.1):
    """
    فقط وقتی True که کاربر واقعاً عضو گروه/کانال باشد.

    API تلگرام حتی وقتی کاربر به‌خاطر تنظیمات حریم خصوصی اضافه نشده
    ممکن است پاسخ موفق بدهد. تنها راه مطمئن، پرسیدن وضعیت عضویت است.
    """
    import asyncio
    app = getattr(client, "app", client)
    for i in range(max(1, retries)):
        try:
            mem = await app.get_chat_member(chat_id, int(uid))
            st = _normalize_member_status(mem)
            if st in _NOT_JOINED_STATUSES:
                return False          # قطعاً داخل گروه نیست — تلاش دوباره بی‌فایده
            if st in _JOINED_STATUSES:
                return True
        except Exception:
            pass
        if i + 1 < retries:
            await asyncio.sleep(pause)
    return False


def reset_cache_for_tests():
    """فقط برای تست‌ها"""
    global _BLOCKED_IDS_CACHE
    _BLOCKED_IDS_CACHE = {"ids": None, "ts": 0}
