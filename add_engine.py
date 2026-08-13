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


def reset_cache_for_tests():
    """فقط برای تست‌ها"""
    global _BLOCKED_IDS_CACHE
    _BLOCKED_IDS_CACHE = {"ids": None, "ts": 0}
