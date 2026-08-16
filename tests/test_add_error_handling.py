"""
مدیریت خطاهای بحرانی تلگرام حین ادد.

اجرای واقعی روی سرویس زنده (۱۶ اکانت‌دقیقه) این آمار را داد:

    CHAT_WRITE_FORBIDDEN     32   ← دسترسی افزودن عضو نیست
    PEER_FLOOD               30   ← اکانت محدود شده
    invited but not a member 30   ← درست: در «رد شده» رفت
    USER_CHANNELS_TOO_MUCH    2
    Invited (موفق)            4

هیچ‌کدام از دو خطای اول مدیریت نمی‌شدند: ورکر در حلقه می‌ماند و
هزاران بار همان خطا را می‌گرفت. اکانت‌ها بی‌فایده می‌سوختند و
نرخ ادد به‌شدت پایین می‌آمد.
"""
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
BOT_SRC = (ROOT / "bot.py").read_text(encoding="utf-8")


def _parallel_worker_body():
    """
    بدنه _execute_parallel_add را بر اساس تورفتگی جدا می‌کند.

    regex ساده کار نمی‌کند چون این تابع خودش شامل
    `async def worker_account(...)` تودرتو است.
    """
    lines = BOT_SRC.split("\n")
    start = next(
        i for i, l in enumerate(lines)
        if l.startswith("async def _execute_parallel_add(")
    )
    out = [lines[start]]
    for line in lines[start + 1:]:
        if line and not line[0].isspace():   # به تعریف سطح‌بالای بعدی رسیدیم
            break
        out.append(line)
    return "\n".join(out)


@pytest.mark.parametrize("code", ["PEER_FLOOD", "CHAT_WRITE_FORBIDDEN", "USER_CHANNELS_TOO_MUCH"])
def test_critical_errors_are_handled(code):
    assert code in _parallel_worker_body(), (
        f"{code} مدیریت نمی‌شود — ورکر در حلقه می‌ماند و اکانت را می‌سوزاند"
    )


def test_peer_flood_stops_that_worker():
    """
    ادامه دادن بعد از PEER_FLOOD فقط محدودیت را تشدید می‌کند و
    هیچ اددی انجام نمی‌شود.
    """
    body = _parallel_worker_body()
    i = body.index("PEER_FLOOD")
    window = body[i:i + 900]
    assert "break" in window, "بعد از PEER_FLOOD باید ورکر متوقف شود"
    assert "set_adder_limit" in window, "اکانت باید به‌عنوان محدودشده ثبت شود"


def test_peer_flood_records_24h_cooldown():
    body = _parallel_worker_body()
    i = body.index("PEER_FLOOD")
    assert "24 * 3600" in body[i:i + 900], "محدودیت باید ۲۴ ساعته ثبت شود"


def test_write_forbidden_stops_and_explains():
    """این خطای پیکربندی است — کاربر باید بفهمد چه کار کند."""
    body = _parallel_worker_body()
    i = body.index("CHAT_WRITE_FORBIDDEN")
    window = body[i:i + 900]
    assert "break" in window
    assert "live_status_text" in window, "کاربر باید علت را در مینی‌اپ ببیند"


@pytest.mark.parametrize("code", ["PEER_FLOOD", "CHAT_WRITE_FORBIDDEN"])
def test_interrupted_member_is_requeued(code):
    """
    وقتی ورکر به‌خاطر خطای اکانت متوقف می‌شود، کاربری که در دست داشت
    نباید هدر برود — ورکر دیگری باید بتواند اضافه‌اش کند.
    """
    body = _parallel_worker_body()
    i = body.index(code)
    assert "put_nowait(member)" in body[i:i + 900], (
        f"بعد از {code} کاربر باید به صف برگردد"
    )


def test_too_many_channels_counts_as_skipped_not_failed():
    """تقصیر ما نیست — نباید جزو خطا شمرده شود."""
    body = _parallel_worker_body()
    i = body.index("USER_CHANNELS_TOO_MUCH")
    # فقط تا انتهای همین بلوک — نه هندلر بعدی
    window = body[i:body.index("continue", i) + len("continue")]
    assert "total_skipped += 1" in window
    assert "total_failed" not in window, "این خطا تقصیر ما نیست، نباید failed شمرده شود"


def test_success_still_requires_membership_confirmation():
    """
    مهم‌ترین تضمین: «۱۰۰ نوشت ولی ۱۰ تا شد» نباید برگردد.
    فقط بعد از confirm_joined باید موفق شمرده شود.
    """
    body = _parallel_worker_body()
    confirm = body.index("confirm_joined")
    added = body.index("total_added += 1")
    assert confirm < added, "تأیید عضویت باید قبل از شمردن موفقیت باشد"

    window = body[confirm:confirm + 300]
    assert "total_skipped += 1" in window, (
        "کاربر تأییدنشده باید در «رد شده» برود، نه «موفق»"
    )
