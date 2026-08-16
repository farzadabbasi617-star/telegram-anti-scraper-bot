"""
بودجه‌ی نرخ پیش‌فیلتر.

🚨 علت «با کمترین ادد لیمیت می‌خوریم» (۱.۶.۴):

لاگ زنده نشان داد اکانت‌ها با **صفر ادد** PEER_FLOOD می‌گرفتند:

    21:06:18  🚫 [+989359428854] PEER_FLOOD (بار 3) — تا اینجا 0 ادد
    21:06:22  🚫 [+989035171235] PEER_FLOOD (بار 3) — تا اینجا 0 ادد

و درست قبلش، ۲۵۲ خط از این:

    [prefilter] پیش‌فیلتر برای این دسته ناموفق بود (FloodWait)

تراکم: **۹۴ خطا در یک دقیقه**.

علت: پیش‌فیلتر روی کل صف (۹٬۶۰۰ نفر) اجرا می‌شد. هر دسته‌ی ۱۰۰تایی
یک `get_users` است ⇒ ۹۶ درخواست پشت سر هم. اکانت تمام بودجه‌ی نرخش را
**قبل از اولین ادد** می‌سوزاند.

بدتر: وقتی FloodWait می‌گرفت، حلقه ادامه می‌داد و باز درخواست می‌زد.
"""
import pathlib
import re

import pytest

import add_engine

ROOT = pathlib.Path(__file__).resolve().parent.parent


class _FloodErr(Exception):
    pass


_FloodErr.__name__ = "FloodWait"


class _User:
    """کاربر سالم — تلگرام واقعی آبجکت برمی‌گرداند، نه لیست خالی."""

    def __init__(self, uid):
        self.id = uid
        self.is_bot = False
        self.is_deleted = False
        self.is_scam = False
        self.is_fake = False
        self.first_name = "u"
        self.username = None


class _App:
    """کلاینت ساختگی که مثل تلگرام rate-limit می‌دهد."""

    def __init__(self, fail_after=0):
        self.calls = 0
        self.fail_after = fail_after

    async def get_users(self, ids):
        self.calls += 1
        if self.fail_after and self.calls > self.fail_after:
            raise _FloodErr("FLOOD_WAIT_X")
        return [_User(i) for i in ids]


def _members(n):
    return [{"user_id": 100000 + i} for i in range(n)]


async def test_prefilter_stops_when_telegram_rate_limits(monkeypatch):
    """
    مهم‌ترین تست: با اولین FloodWait باید کلاً رها کند، نه اینکه
    ۹۶ بار پشت سر هم درخواست بزند.
    """
    monkeypatch.setattr(add_engine, "get_blocked_ids_cached", lambda: set())
    app = _App(fail_after=1)
    keep, stats = await add_engine.prefilter_unaddable(
        app, _members(5000), mark_blocked=False
    )
    assert app.calls <= 3, (
        f"{app.calls} درخواست بعد از FloodWait — باید فوراً رها می‌کرد"
    )
    assert stats.get("aborted") is True
    assert len(keep) == 5000, "هیچ کاربری نباید حذف شود وقتی بررسی نشده"


async def test_prefilter_gives_up_after_repeated_failures(monkeypatch):
    """خطاهای غیرFlood هم نباید بی‌نهایت تکرار شوند."""
    monkeypatch.setattr(add_engine, "get_blocked_ids_cached", lambda: set())

    class _Broken:
        def __init__(self):
            self.calls = 0

        async def get_users(self, ids):
            self.calls += 1
            raise ValueError("boom")

    app = _Broken()
    keep, stats = await add_engine.prefilter_unaddable(
        app, _members(5000), mark_blocked=False
    )
    assert app.calls <= 4, f"{app.calls} تلاش — باید زود رها می‌کرد"
    assert len(keep) == 5000


async def test_no_user_lost_when_prefilter_aborts(monkeypatch):
    """رها کردن پیش‌فیلتر نباید باعث گم شدن کاربر شود."""
    monkeypatch.setattr(add_engine, "get_blocked_ids_cached", lambda: set())
    app = _App(fail_after=1)
    keep, _ = await add_engine.prefilter_unaddable(
        app, _members(1234), mark_blocked=False
    )
    assert len(keep) == 1234


# ───────── دامنه‌ی پیش‌فیلتر در ورکر ─────────

def test_worker_only_prefilters_head_of_queue():
    """
    نباید کل صف را بررسی کند — فقط آن مقداری که واقعاً ادد می‌شود.
    """
    src = (ROOT / "bot.py").read_text(encoding="utf-8")
    i = src.index("prefilter_unaddable(")
    window = src[max(0, i - 1200):i + 300]
    assert "_scan" in window, "دامنه بررسی باید محدود شود"
    assert "members[:_scan]" in window or "_head" in window


def test_scan_size_is_proportional_to_accounts():
    """اندازه‌ی بررسی باید با تعداد اکانت‌ها متناسب باشد، نه کل صف."""
    src = (ROOT / "bot.py").read_text(encoding="utf-8")
    m = re.search(r"_scan = min\(len\(members\), max\((\d+), len\(accs\) \* (\d+)\)\)", src)
    assert m, "فرمول محدودسازی دامنه پیدا نشد"
    floor, per_acc = int(m.group(1)), int(m.group(2))
    assert floor <= 500 and per_acc <= 100

    # با ۶ اکانت و ۹۶۰۰ نفر: چند درخواست؟
    scan = min(9600, max(floor, 6 * per_acc))
    requests = (scan + 99) // 100
    assert requests <= 8, (
        f"{requests} درخواست قبل از اولین ادد — همین باعث PEER_FLOOD شد"
    )


def test_queue_is_rebuilt_after_partial_prefilter():
    """بخش بررسی‌نشده نباید از صف حذف شود."""
    src = (ROOT / "bot.py").read_text(encoding="utf-8")
    assert "members = _head + _tail" in src, (
        "صف باید از سر بررسی‌شده + بقیه بازسازی شود، وگرنه هزاران کاربر گم می‌شوند"
    )
