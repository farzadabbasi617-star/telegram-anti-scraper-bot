"""
کارایی ادد — سه خواسته‌ی صریح مالک:

    «با چند تا ادد لیمیت نخورن، تکراری ادد نکنن، قبل ادد لیمیت نشن»

🚨 چیزی که در پروداکشن دیدیم: اکانت‌ها با **صفر ادد** PEER_FLOOD
می‌گرفتند. ریشه‌یابی سه عامل نشان داد:

۱) **۳ درخواست به ازای هر کاربر قبل از ادد:**
   resolve_peer(username) → resolve_peer(uid) → AddContact → Invite
   هر کدام بودجه‌ی نرخ می‌سوزاند. AddContact یکی از شدیدترین
   rate-limit های تلگرام را دارد و به موفقیت ادد کمکی نمی‌کرد.

۲) **۲۷٪ صف غیرقابل‌ادد بود:** ۶٬۷۸۴ نفر از ۲۵٬۳۴۷ فقط user_id
   داشتند (نه یوزرنیم، نه شماره) — تقریباً هرگز resolve نمی‌شوند.

۳) **ضد-تکرار بین ورکرها نبود:** `mark_user_as_added` فقط در
   دیتابیس می‌نوشت؛ ست مشترک حافظه به‌روز نمی‌شد، پس دو ورکر
   موازی می‌توانستند سراغ یک نفر بروند.
"""
import pathlib
import re

import config
from add_engine import prefer_addable_members

ROOT = pathlib.Path(__file__).resolve().parent.parent
BOT = (ROOT / "bot.py").read_text(encoding="utf-8")


def _worker_body():
    lines = BOT.split("\n")
    st = next(i for i, l in enumerate(lines)
              if l.startswith("async def _execute_parallel_add("))
    out = [lines[st]]
    for l in lines[st + 1:]:
        if l and not l[0].isspace():
            break
        out.append(l)
    return "\n".join(out)


def _add_loop():
    """بدنه‌ی حلقه‌ی ادد — از while تا انتها."""
    b = _worker_body()
    return b[b.index("while not member_queue.empty()"):]


# ───────── ۱) قبل از ادد لیمیت نشویم ─────────

def test_addcontact_removed_from_hot_path():
    """
    AddContact یکی از شدیدترین rate-limit ها را دارد و کاربری که
    پرایوسی‌اش بسته است را هم اضافه نمی‌کند — یعنی صرفاً هدررفت.
    """
    loop = _add_loop()
    assert "AddContact(" not in loop, (
        "AddContact در مسیر داغ ادد است — ۳۳٪ درخواست اضافه به ازای هر کاربر"
    )


def test_only_one_resolve_attempt_in_happy_path():
    """
    قبلاً دو resolve_peer پشت سر هم بود. تلاش دوم فقط وقتی مجاز است
    که خطای اول ربطی به محدودیت نداشته باشد.
    """
    loop = _add_loop()
    count = len(re.findall(r"await client\.resolve_peer\(", loop))
    assert count <= 2, f"{count} فراخوانی resolve — باید حداکثر ۲ باشد"
    # و تلاش دوم باید مشروط به «خطای غیرFlood» باشد
    assert "_peer_flood_hit" in loop, "باید روی FloodWait فوراً عقب بکشد"


def test_resolve_flood_pauses_instead_of_retrying():
    """محدودیت حین resolve باید مثل PEER_FLOOD رسیدگی شود."""
    loop = _add_loop()
    i = loop.index("if _peer_flood_hit:")
    window = loop[i:i + 2200]
    assert "put_nowait(member)" in window, "کاربر نباید هدر برود"
    assert "peer_flood_cooldown" in window, "باید صبر کوتاه اعمال شود"
    assert "بن نشده" in window, "کاربر باید بداند اکانت سالم است"
    assert "continue" in window, "بعد از صبر باید دوباره تلاش کند"


def test_no_dangling_exception_class():
    """
    یک نسخه‌ی میانی raise می‌کرد ولی هندلرش ۶۰۰۰ خط دورتر و در تابع
    دیگری بود — یعنی ورکر کرش می‌کرد. رسیدگی حالا درجاست.
    """
    assert "_PeerFloodSignal" not in BOT, "کلاس/ارجاع بلااستفاده باقی مانده"


# ───────── ۲) صف تمیز باشد ─────────

def test_id_only_users_are_dropped():
    """کاربر بدون یوزرنیم و شماره = درخواست محکوم به شکست."""
    data = [
        {"user_id": 1, "username": "ali"},
        {"user_id": 2, "phone": "+9891"},
        {"user_id": 3},
        {"user_id": 4, "username": "", "phone": ""},
    ]
    out = prefer_addable_members(data)
    assert len(out) == 2
    assert all(u.get("username") or u.get("phone") for u in out)


def test_username_users_come_first():
    data = [{"user_id": 1, "phone": "+98"}, {"user_id": 2, "username": "b"}]
    out = prefer_addable_members(data)
    assert out[0].get("username") == "b"


def test_dropping_can_be_disabled():
    data = [{"user_id": 3}]
    assert len(prefer_addable_members(data, drop_id_only=False)) == 1


# ───────── ۳) تکراری ادد نشود ─────────

def test_successful_add_updates_shared_blocklist():
    """
    ست مشترک حافظه باید فوراً به‌روز شود، وگرنه ورکر دیگر همان
    کاربر را دوباره امتحان می‌کند.
    """
    loop = _add_loop()
    i = loop.index("total_added += 1")
    window = loop[i:i + 700]
    assert "blocked_ids.add(" in window, (
        "بعد از ادد موفق باید به ست مشترک اضافه شود"
    )


def test_all_terminal_outcomes_block_retry():
    """
    هر نتیجه‌ای که تکرارش بی‌فایده است باید کاربر را از صف خارج کند:
    عضو شد / از قبل عضو بود / پرایوسی بسته / آیدی نامعتبر / عضو نشد.
    """
    loop = _add_loop()
    for marker in (
        "except UserAlreadyParticipant:",
        "except (UserPrivacyRestricted, UserNotMutualContact) as e:",
        "except PeerIdInvalid:",
    ):
        i = loop.index(marker)
        window = loop[i:i + 500]
        assert "blocked_ids.add(" in window, f"{marker} کاربر را بلاک نمی‌کند"


def test_invited_but_not_member_is_blocked():
    loop = _add_loop()
    i = loop.index("invited but not a member")
    window = loop[max(0, i - 400):i + 200]
    assert "blocked_ids.add(" in window


def test_queue_checks_blocklist_before_each_add():
    loop = _add_loop()
    head = loop[:loop.index("user_peer = None")]
    assert "in blocked_ids" in head, "قبل از هر ادد باید ست بررسی شود"


# ───────── تنظیمات نرخ ─────────

def test_effective_rate_is_sane_with_parallel_accounts():
    """
    تأخیر «هر اکانت» است ولی اکانت‌ها موازی‌اند. فاصله‌ی مؤثر روی
    گروه = میانگین ÷ تعداد اکانت.
    """
    lo, hi = config.DELAY_RANGES["safe"]
    effective = ((lo + hi) / 2) / 6
    assert effective >= 14, (
        f"با ۶ اکانت یک ادد هر {effective:.0f}s — تلگرام هجوم می‌بیند"
    )


def test_modes_are_ordered():
    d = config.DELAY_RANGES
    assert d["ultra"][0] < d["fast"][0] < d["safe"][0]
    b = config.BREAK_RANGES
    assert b["ultra"][0] < b["fast"][0] < b["safe"][0]


def test_break_interval_from_config():
    assert hasattr(config, "ADDS_BEFORE_BREAK")
    lo, hi = config.ADDS_BEFORE_BREAK
    assert 3 <= lo <= hi <= 20
    assert "random.randint(*ADDS_BEFORE_BREAK)" in BOT, "نباید هاردکد باشد"
