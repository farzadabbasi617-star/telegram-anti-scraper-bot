"""
پیش‌بینی پرایوسی قبل از تلاش ادد.

🚨 مشکلی که این ماژول حل می‌کند (۱.۸.۰):

اندازه‌گیری زنده بعد از رفع throttle نشان داد فاصله‌ها درست شده
(کمینه ۱۰۰ ثانیه) ولی همچنان PEER_FLOOD می‌آمد:

    ۹ مورد «invited but not a member»
    ۰ مورد ادد موفق

هر ۹ نفر پرایوسی‌شان بسته بود. تلگرام اکانتی که پشت سر هم دعوت
بی‌نتیجه می‌فرستد را اسپمر می‌بیند — حتی با فاصله‌ی زیاد.

راه‌حل: از فیلد `status` که در همان `get_users` رایگان می‌آید،
حدس بزنیم چه کسی privacy بسته دارد.

کسی که «آخرین بازدید» را مخفی کرده، از بیرون RECENTLY / LAST_WEEK /
LAST_MONTH دیده می‌شود — و با احتمال بالا «چه کسی می‌تواند مرا اضافه
کند» را هم بسته، چون هر دو در یک صفحه‌ی تنظیمات‌اند.
"""
import pathlib

import pytest

import add_engine
from add_engine import _is_unaddable_user, _status_token

ROOT = pathlib.Path(__file__).resolve().parent.parent


class _Status:
    def __init__(self, name):
        self.name = name
        self.value = name.lower()

    def __str__(self):
        return f"UserStatus.{self.name}"


class _U:
    def __init__(self, status=None, **kw):
        self.is_deleted = False
        self.is_bot = False
        self.is_self = False
        self.is_scam = False
        self.is_fake = False
        self.status = _Status(status) if status else None
        for k, v in kw.items():
            setattr(self, k, v)


# ───────── استخراج وضعیت ─────────

@pytest.mark.parametrize("name,expected", [
    ("ONLINE", "online"),
    ("RECENTLY", "recently"),
    ("LAST_WEEK", "last_week"),
    ("LONG_AGO", "long_ago"),
])
def test_status_token_extraction(name, expected):
    assert _status_token(_U(status=name)) == expected


def test_status_token_handles_missing():
    assert _status_token(_U()) == ""
    assert _status_token(None) == ""


def test_status_token_survives_plain_str_enum():
    """اگر enum فقط __str__ داشته باشد هم باید درست پارس شود."""
    class Bare:
        def __str__(self):
            return "UserStatus.RECENTLY"

    u = _U()
    u.status = Bare()
    assert _status_token(u) == "recently"


# ───────── تشخیص غیرقابل‌ادد ─────────

@pytest.mark.parametrize("status", ["RECENTLY", "LAST_WEEK", "LAST_MONTH"])
def test_hidden_last_seen_is_skipped(status):
    bad, why = _is_unaddable_user(_U(status=status))
    assert bad and "پرایوسی" in why


@pytest.mark.parametrize("status", ["LONG_AGO", "EMPTY"])
def test_abandoned_accounts_skipped(status):
    bad, why = _is_unaddable_user(_U(status=status))
    assert bad and "رهاشده" in why


@pytest.mark.parametrize("status", ["ONLINE", "OFFLINE"])
def test_visible_users_are_attempted(status):
    """کاربری که last-seen باز دارد، شانس واقعی عضویت دارد."""
    bad, _ = _is_unaddable_user(_U(status=status))
    assert not bad


def test_scam_and_fake_skipped():
    assert _is_unaddable_user(_U(status="ONLINE", is_scam=True))[0]
    assert _is_unaddable_user(_U(status="ONLINE", is_fake=True))[0]


def test_hard_signals_always_apply():
    """ربات و حذف‌شده حتی با strict_privacy=False رد می‌شوند."""
    for kw in ({"is_bot": True}, {"is_deleted": True}, {"is_self": True}):
        assert _is_unaddable_user(_U(status="ONLINE", **kw), strict_privacy=False)[0]


def test_strict_privacy_can_be_disabled():
    """اگر صف کم بود، بتوان سخت‌گیری را خاموش کرد."""
    bad, _ = _is_unaddable_user(_U(status="RECENTLY"), strict_privacy=False)
    assert not bad


def test_none_user_is_unaddable():
    assert _is_unaddable_user(None)[0]


# ───────── یکپارچگی با پیش‌فیلتر ─────────

async def test_prefilter_drops_privacy_users(monkeypatch):
    monkeypatch.setattr(add_engine, "get_blocked_ids_cached", lambda: set())
    blocked = []
    monkeypatch.setattr(add_engine, "never_add_again",
                        lambda uid, reason: blocked.append((uid, reason)))

    users = {
        1: _U(status="ONLINE"),
        2: _U(status="RECENTLY"),
        3: _U(status="OFFLINE"),
        4: _U(status="LONG_AGO"),
    }
    for uid, u in users.items():
        u.id = uid

    class _App:
        async def get_users(self, ids):
            return [users[i] for i in ids if i in users]

    members = [{"user_id": i, "username": f"u{i}"} for i in users]
    keep, stats = await add_engine.prefilter_unaddable(_App(), members)

    kept_ids = {m["user_id"] for m in keep}
    assert kept_ids == {1, 3}, f"باید فقط کاربران قابل‌دسترس بمانند: {kept_ids}"
    assert stats["removed"] == 2

    reasons = dict(blocked)
    assert reasons[2] == "privacy", "دلیل پرایوسی باید تفکیک شود"
    assert reasons[4] == "stale"


async def test_prefilter_respects_strict_flag(monkeypatch):
    monkeypatch.setattr(add_engine, "get_blocked_ids_cached", lambda: set())
    monkeypatch.setattr(add_engine, "never_add_again", lambda uid, reason: None)

    u = _U(status="RECENTLY"); u.id = 1

    class _App:
        async def get_users(self, ids):
            return [u]

    keep, _ = await add_engine.prefilter_unaddable(
        _App(), [{"user_id": 1, "username": "a"}], strict_privacy=False
    )
    assert len(keep) == 1


# ───────── محافظ سراسری ─────────

def test_global_abort_exists():
    """
    اگر با وجود فیلتر باز هم هیچ‌کس عضو نمی‌شود، کل عملیات باید
    متوقف شود — نه اینکه تک‌تک اکانت‌ها بسوزند.
    """
    src = (ROOT / "bot.py").read_text(encoding="utf-8")
    assert "_ABORT_AFTER_FAILS" in src
    i = src.index("_ABORT_AFTER_FAILS = ")
    limit = int(src[i:i + 40].split("=")[1].split()[0])
    assert 10 <= limit <= 60, f"آستانه {limit} منطقی نیست"


def test_global_counter_is_shared_between_workers():
    """
    بدون nonlocal، هر ورکر یک شمارنده‌ی محلی می‌سازد و محافظ
    هرگز فعال نمی‌شود. (این باگ یک بار رخ داد.)
    """
    import ast

    tree = ast.parse((ROOT / "bot.py").read_text(encoding="utf-8"))
    found = False
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "_worker_account_inner":
            names = {n for x in ast.walk(node) if isinstance(x, ast.Nonlocal) for n in x.names}
            assert "_global_consecutive_fails" in names, (
                "شمارنده سراسری باید nonlocal باشد وگرنه محافظ بی‌اثر است"
            )
            found = True
    assert found, "_worker_account_inner پیدا نشد"


def test_success_resets_global_counter():
    src = (ROOT / "bot.py").read_text(encoding="utf-8")
    i = src.index("total_added += 1")
    assert "_global_consecutive_fails = 0" in src[i:i + 900]
