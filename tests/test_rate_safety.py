"""
ایمنی نرخ ادد — جلوگیری از PEER_FLOOD.

🚨 درس گران (۱.۵.۸):

اجرای واقعی با حالت "safe" و ۸ اکانت موازی:
    ۱۴ ادد موفق → ۵ اکانت PEER_FLOOD خوردند (بعد از ۱ تا ۷ ادد)

دو اشتباه هم‌زمان:

۱) **نرخ کلی خیلی بالا بود.** safe=(45,95) یعنی هر اکانت هر ~۷۰ ثانیه،
   ولی ۸ اکانت موازی = یک ادد هر ~۹ ثانیه به یک گروه. از دید تلگرام
   هجوم هماهنگ اسپم.

۲) **اکانت‌های نو با سقف ۱۰۰ وارد شدند.** اکانتی که هیچ سابقه‌ای ندارد
   نباید روز اول ده‌ها نفر اضافه کند.

و یک اشتباه در واکنش:

۳) **جریمه ۲۴ ساعته را ما هاردکد کرده بودیم** — تلگرام هیچ مدتی
   اعلام نمی‌کند. اکانتی که ۱ نفر ادد کرده بود یک روز از دست می‌رفت.
"""
import pathlib
import re

import pytest

import config
from add_engine import (
    peer_flood_cooldown,
    describe_cooldown,
    warmup_cap,
    stagger_delay,
)

ROOT = pathlib.Path(__file__).resolve().parent.parent


# ───────────────── بک‌آف PEER_FLOOD ─────────────────

def test_first_flood_is_a_short_rest_not_a_day():
    """
    PEER_FLOOD یعنی «آهسته‌تر»، نه «اکانت سوخت».
    اولین بار نباید اکانت را یک روز از دست بدهیم.
    """
    first = peer_flood_cooldown(1)
    assert first <= 30 * 60, f"اولین جریمه {first}s است — خیلی زیاد"
    assert first >= 5 * 60, "خیلی کم هم نباشد که بلافاصله دوباره بخورد"


def test_backoff_is_progressive():
    vals = [peer_flood_cooldown(n) for n in range(1, 6)]
    assert vals == sorted(vals), "بک‌آف باید صعودی باشد"
    assert len(set(vals)) > 1, "نباید ثابت باشد"


def test_backoff_is_capped():
    assert peer_flood_cooldown(50) <= 24 * 3600


def test_no_hardcoded_24h_penalty_in_worker():
    """جریمه باید از بک‌آف بیاید، نه عدد جادویی داخل ورکر."""
    src = (ROOT / "bot.py").read_text(encoding="utf-8")
    i = src.index('if "PEER_FLOOD" in err:')
    window = src[i:src.index("break", i)]
    assert "24 * 3600" not in window, (
        "جریمه ۲۴ ساعته نباید هاردکد باشد — از peer_flood_cooldown بیاید"
    )
    assert "peer_flood_cooldown" in window


def test_successful_add_resets_strikes():
    """
    اکانتی که دوباره موفق شده سالم است — جریمه‌های قبلی نباید
    روی هم انباشته شوند.
    """
    src = (ROOT / "bot.py").read_text(encoding="utf-8")
    assert "_peer_flood_strikes.pop(phone, None)" in src


def test_user_told_account_is_not_banned():
    """کاربر با دیدن «محدود شد» فکر می‌کند اکانتش بن شده."""
    src = (ROOT / "bot.py").read_text(encoding="utf-8")
    i = src.index('if "PEER_FLOOD" in err:')
    window = src[i:src.index("break", i)]
    assert "بن نشده" in window, "باید صریح بگوید اکانت بن نشده"


# ───────────────── نرخ امن ─────────────────

def test_safe_mode_is_actually_safe():
    """
    با ۸ اکانت موازی، فاصله مؤثر بین اددها به یک گروه نباید کمتر از
    ~۱۵ ثانیه شود.
    """
    lo, hi = config.DELAY_RANGES["safe"]
    avg = (lo + hi) / 2
    effective = avg / 8
    assert effective >= 12, (
        f"با ۸ اکانت یک ادد هر {effective:.0f}s — الگوی اسپم "
        f"(همین باعث PEER_FLOOD شد)"
    )


def test_safe_slower_than_fast():
    assert config.DELAY_RANGES["safe"][0] > config.DELAY_RANGES["fast"][0]
    assert config.BREAK_RANGES["safe"][0] > config.BREAK_RANGES["fast"][0]


# ───────────────── گرم کردن اکانت ─────────────────

def test_brand_new_account_gets_small_cap():
    cap = warmup_cap(0)
    assert cap <= 15, f"اکانت بدون سابقه نباید سقف {cap} بگیرد"


def test_cap_grows_with_history():
    caps = [warmup_cap(h) for h in (0, 20, 60, 150, 300)]
    assert caps == sorted(caps), "سقف باید با سابقه بالا برود"
    assert caps[-1] > caps[0] * 3


def test_experienced_account_reaches_full_cap():
    assert warmup_cap(1000, 100) == 100


def test_warmup_respects_mode_cap():
    assert warmup_cap(1000, 30) == 30


def test_worker_uses_warmup():
    src = (ROOT / "bot.py").read_text(encoding="utf-8")
    assert "warmup_cap" in src
    assert "count_added_by_account" in src, "سابقه واقعی باید از DB بیاید"


def test_history_function_exists_and_uses_right_column():
    src = (ROOT / "db.py").read_text(encoding="utf-8")
    assert "def count_added_by_account" in src
    i = src.index("def count_added_by_account")
    assert "account_phone" in src[i:i + 700], "ستون درست باید استفاده شود"


# ───────────────── شروع پلکانی ─────────────────

def test_accounts_do_not_start_simultaneously():
    """اگر همه با هم شروع کنند، تلگرام الگوی هماهنگ می‌بیند."""
    delays = [stagger_delay(i, "safe") for i in range(6)]
    assert max(delays) > 60, "فاصله شروع کافی نیست"
    assert len(set(int(d) for d in delays)) > 1


def test_worker_applies_stagger():
    src = (ROOT / "bot.py").read_text(encoding="utf-8")
    assert "stagger_delay" in src or "_stag(" in src
    assert "_worker_index" in src, "ایندکس ورکر باید پاس داده شود"
