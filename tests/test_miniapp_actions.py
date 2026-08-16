"""
تست‌های دکمه‌های مینی‌اپ.

پس‌زمینه (نسخه ۱.۴.۴):
مالک گزارش داد صفحه «ادد» در مینی‌اپ «کار نمی‌کند و دکور است». بررسی نشان
داد هر دو endpoint ادد پس از ۹۰ ثانیه پاسخ خالی برمی‌گرداندند.

علت: `trigger_parallel_add` تابع `collect_ready_accounts()` را مستقیماً
داخل هندلر HTTP صدا می‌زد. آن تابع برای هر اکانت سشن را از دیتابیس
بازیابی و بازرسی می‌کند — با ۸ اکانت ده‌ها عملیات دیسک/DB. درخواست تا
پایان کار بلاک می‌ماند و مینی‌اپ تایم‌اوت می‌خورد.

این تست‌ها تضمین می‌کنند مسیر درخواست سریع بماند و حذف اکانت درست کار کند.
"""
import re
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
WEB_APP_SRC = (ROOT / "web_app.py").read_text(encoding="utf-8")


def _function_body(name):
    """متن یک تابع سطح-بالا را برمی‌گرداند."""
    match = re.search(
        rf"^def {re.escape(name)}\(.*?\n(.*?)(?=\n(?:def |class )|\Z)",
        WEB_APP_SRC,
        re.S | re.M,
    )
    assert match, f"تابع {name} پیدا نشد"
    return match.group(1)


# ───────────────────── مسیر درخواست باید سریع باشد ─────────────────────

def test_parallel_add_does_not_block_the_request():
    """
    هسته باگ: collect_ready_accounts() نباید در مسیر همگام درخواست باشد.

    باید داخل کوروتین پس‌زمینه و با asyncio.to_thread اجرا شود.
    """
    body = _function_body("trigger_parallel_add")

    assert "collect_ready_accounts" in body, "تابع باید همچنان اکانت‌ها را جمع کند"
    assert "asyncio.to_thread(collect_ready_accounts)" in body, (
        "collect_ready_accounts باید با asyncio.to_thread اجرا شود تا "
        "حلقه رویداد و مسیر درخواست بلاک نشود"
    )

    # باید داخل تابع async پس‌زمینه باشد، نه در بدنه اصلی
    job = re.search(r"async def run_parallel_job\(\):(.*?)(?=\n        _schedule_coro)", body, re.S)
    assert job, "کوروتین پس‌زمینه run_parallel_job پیدا نشد"
    assert "collect_ready_accounts" in job.group(1), (
        "جمع‌آوری اکانت‌ها باید داخل کار پس‌زمینه انجام شود"
    )


def test_parallel_add_schedules_work_and_returns():
    """تابع باید کار را زمان‌بندی کند و فوراً پیام موفقیت بدهد."""
    body = _function_body("trigger_parallel_add")
    assert "_schedule_coro(run_parallel_job())" in body
    schedule_at = body.index("_schedule_coro(run_parallel_job())")
    returns_after = body.index("return True", schedule_at)
    assert returns_after > schedule_at, "بعد از زمان‌بندی باید بلافاصله return کند"


@pytest.mark.parametrize("fn", ["trigger_parallel_add", "trigger_single_add"])
def test_add_triggers_refuse_when_already_running(fn):
    """
    دو عملیات همزمان روی یک سشن = AUTH_KEY_DUPLICATED و سوختن سشن.
    هر دو مسیر باید جلویش را بگیرند.
    """
    body = _function_body(fn)
    assert 'atk_state_ref.get("add_in_progress")' in body, (
        f"{fn} باید قبل از شروع، اجرای همزمان را رد کند"
    )


@pytest.mark.parametrize("fn", ["trigger_parallel_add", "trigger_single_add"])
def test_add_triggers_surface_errors_to_ui(fn):
    """
    خطای پس‌زمینه نباید بی‌صدا بماند — کاربر باید در همان صفحه ببیند،
    وگرنه دکمه دوباره «کار نمی‌کند» به نظر می‌رسد.
    """
    body = _function_body(fn)
    assert "live_status_text" in body, f"{fn} باید خطا/وضعیت را به UI بدهد"


@pytest.mark.parametrize("fn", ["trigger_parallel_add", "trigger_single_add"])
def test_add_in_progress_always_cleared(fn):
    """
    اگر پرچم add_in_progress پاک نشود، همه اددهای بعدی برای همیشه رد
    می‌شوند. باید در finally پاک شود.
    """
    body = _function_body(fn)
    assert re.search(r"finally:\s*\n\s*if atk_state_ref:\s*\n\s*atk_state_ref\[\"add_in_progress\"\] = False", body), (
        f"{fn} باید add_in_progress را در finally پاک کند"
    )


# ───────────────────── حذف اکانت ─────────────────────

def test_delete_endpoint_registered_on_both_servers():
    """مینی‌اپ روی aiohttp اجرا می‌شود ولی سرور استاندارد هم fallback است."""
    assert "app.router.add_post('/api/accounts/delete', aio_api_delete_account)" in WEB_APP_SRC
    assert "'/api/accounts/delete'" in WEB_APP_SRC
    assert WEB_APP_SRC.count("/api/accounts/delete") >= 3, (
        "باید در هر دو سرور و در فرانت‌اند وجود داشته باشد"
    )


def test_delete_removes_session_files_not_just_db_row():
    """
    اگر فقط رکورد DB پاک شود، فایل سشن روی دیسک می‌ماند و دفعه بعد
    همان شماره با سشن قدیمیِ احتمالاً سوخته وصل می‌شود.
    """
    body = _function_body("delete_account_fully")
    assert "db.delete_account" in body
    assert "os.remove" in body
    assert ".session" in body
    for suffix in ("-journal", "-wal", "-shm"):
        assert suffix in body, f"فایل جانبی {suffix} هم باید پاک شود"


def test_delete_refuses_busy_account():
    """حذف اکانتی که وسط عملیات است، ورکر را می‌شکند."""
    body = _function_body("delete_account_fully")
    assert "busy_label" in body
    assert "مشغول" in body


def test_delete_validates_input():
    body = _function_body("delete_account_fully")
    assert "if not phone" in body, "شماره خالی باید رد شود"
    assert "not in accs" in body, "اکانت ناموجود باید پیام واضح بدهد"


def test_delete_invalidates_cache():
    """
    لیست اکانت‌ها کش می‌شود؛ بدون باطل کردن کش، اکانت حذف‌شده تا
    انقضای کش همچنان در UI دیده می‌شود.
    """
    body = _function_body("delete_account_fully")
    assert "_ACCOUNTS_CACHE" in body


# ───────────────────── فرانت‌اند ─────────────────────

def test_ui_has_delete_button_with_confirmation():
    assert "deleteAccount(" in WEB_APP_SRC
    delete_fn = re.search(r"async function deleteAccount\(.*?\n(.*?)\n        \}", WEB_APP_SRC, re.S)
    assert delete_fn, "تابع deleteAccount در فرانت‌اند پیدا نشد"
    assert "confirm(" in delete_fn.group(1), "حذف باید تأیید بگیرد"


def test_ui_refreshes_after_delete():
    """بعد از حذف، لیست‌ها باید تازه شوند وگرنه کاربر فکر می‌کند نشد."""
    delete_fn = re.search(r"async function deleteAccount\(.*?\n(.*?)\n        \}", WEB_APP_SRC, re.S)
    body = delete_fn.group(1)
    assert "loadAccounts()" in body
    assert "loadAttackAccounts()" in body


def test_add_account_guide_points_to_the_real_bot_flow():
    """
    افزودن اکانت نمی‌تواند در مرورگر انجام شود (کد تأیید تلگرام و رمز
    دو مرحله‌ای). راهنما باید کاربر را به فلوی واقعی داخل ربات بفرستد.
    """
    assert "showAddAccountGuide" in WEB_APP_SRC
    guide = re.search(r"function showAddAccountGuide\(\)\s*\{(.*?)\n        \}", WEB_APP_SRC, re.S)
    assert guide, "تابع راهنما پیدا نشد"
    text = guide.group(1)
    assert "مدیریت اکانت" in text, "باید مسیر منوی واقعی ربات را بگوید"
    assert "/start" in text

    # و آن فلو واقعاً باید در ربات وجود داشته باشد
    bot_src = (ROOT / "bot.py").read_text(encoding="utf-8")
    assert 'callback_data="manage_accounts"' in bot_src
    assert 'callback_data="add_new_account"' in bot_src


# ───────────────────── کوئری N+1 ─────────────────────

@pytest.mark.parametrize("fn", ["trigger_parallel_add", "trigger_single_add"])
def test_no_database_query_inside_member_filter_loop(fn):
    """
    باگی که دکمه ادد را واقعاً از کار انداخته بود.

    فیلتر ضد تکرار به ازای *هر* کاربر یک بار `db.is_added()` صدا می‌زد.
    با ۱۰٬۰۰۰ ممبر یعنی ۱۰٬۰۰۰ رفت‌وبرگشت جداگانه به Postgres. چند دقیقه
    طول می‌کشید و چون در مسیر همگام درخواست بود، مینی‌اپ تایم‌اوت می‌خورد
    و کاربر فکر می‌کرد دکمه «دکور» است.

    درست: یک کوئری دسته‌ای قبل از حلقه.
    """
    body = _function_body(fn)
    loop = re.search(
        r"for u in raw_users:(.*?)(?=\n        filtered = prefer)", body, re.S
    )
    assert loop, f"حلقه فیلتر در {fn} پیدا نشد"

    queries = re.findall(r"db\.(\w+)\(", loop.group(1))
    assert not queries, (
        f"{fn} داخل حلقه کوئری دیتابیس می‌زند: {queries}. "
        "با ۱۰٬۰۰۰ ممبر این یعنی هزاران کوئری و تایم‌اوت مینی‌اپ. "
        "قبل از حلقه یک‌بار دسته‌ای بگیر."
    )


@pytest.mark.parametrize("fn", ["trigger_parallel_add", "trigger_single_add"])
def test_dedup_uses_bulk_lookup(fn):
    """ضد تکرار باید همچنان کار کند — فقط با یک کوئری دسته‌ای."""
    body = _function_body(fn)
    assert "get_added_user_ids" in body, "باید مجموعه اددشده‌ها را یکجا بگیرد"
    assert "already_added_ids" in body, "باید در حافظه چک شود"


def test_bulk_lookup_returns_a_set():
    """
    باید set برگرداند نه list — چک عضویت در list یعنی O(n) به ازای هر
    کاربر و همان کندی از راه دیگری برمی‌گردد.
    """
    src = (ROOT / "db.py").read_text(encoding="utf-8")
    m = re.search(r"def get_added_user_ids\(.*?\n(.*?)(?=\n@|\ndef )", src, re.S)
    assert m, "تابع get_added_user_ids پیدا نشد"
    body = m.group(1)
    assert "{int(r[0])" in body or "set(" in body, "باید set بسازد"
    assert "return set()" in body, "در خطا باید set خالی بدهد نه None"
