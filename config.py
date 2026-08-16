"""
=================================================================
⚙️ Central Configuration — Single Source of Truth
=================================================================
تمام تنظیمات پروژه از اینجا خوانده می‌شوند:
  1. متغیرهای محیطی (Render / Docker)
  2. فایل .env محلی (در صورت وجود)

⚠️ نکته امنیتی: مقادیر پیش‌فرض فقط برای توسعه محلی هستند.
برای محیط Production حتماً مقادیر واقعی را در Environment Variables قرار دهید.
"""
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass


def _int(name, default):
    try:
        return int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default


def _bool(name, default=False):
    raw = os.environ.get(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


# -----------------------------------------------------------------
# Telegram Bot
# -----------------------------------------------------------------
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_ID = _int("ADMIN_ID", 0)

# -----------------------------------------------------------------
# Telegram API (user accounts)
# -----------------------------------------------------------------
API_ID = _int("API_ID", 0)
API_HASH = os.environ.get("API_HASH", "")

# -----------------------------------------------------------------
# Web / Mini App
# -----------------------------------------------------------------
PORT = _int("PORT", 10000)
PUBLIC_URL = os.environ.get("RENDER_EXTERNAL_URL", "https://telegram-anti-scraper-bot.onrender.com")
KEEP_ALIVE_INTERVAL = _int("KEEP_ALIVE_INTERVAL", 280)   # ثانیه (Render حدود ۱۵ دقیقه خواب)
HEALTH_CHECK_INTERVAL = _int("HEALTH_CHECK_INTERVAL", 3600)

# -----------------------------------------------------------------
# Database
# -----------------------------------------------------------------
DATABASE_URL = os.environ.get("DATABASE_URL", "")
DB_POOL_SIZE = _int("DB_POOL_SIZE", 6)
SESSION_ENCRYPTION_KEY = os.environ.get("SESSION_ENCRYPTION_KEY", "")

# -----------------------------------------------------------------
# Add Engine (ضد بن)
# -----------------------------------------------------------------
# 🚫 سقف روزانه‌ی مصنوعی برداشته شد.
# مالک: «بذار اکانت‌ها تا حداکثر ظرفیت خودشون ادد بزنن و فقط وقتی
# تلگرام خودش محدودشون کرد صبر کنیم.»
# این اعداد حالا فقط یک سقف ایمنی خیلی بالا هستند تا حلقه بی‌نهایت
# نشود؛ عملاً تلگرام خیلی زودتر جلو را می‌گیرد.
MAX_ADD_PER_ACCOUNT = _int("MAX_ADD_PER_ACCOUNT", 1000)
MODE_DAILY_CAP = {
    "ultra": _int("CAP_ULTRA", 1000),
    "fast": _int("CAP_FAST", 1000),
    "safe": _int("CAP_SAFE", 1000),
}

# 🚫 سقف مصنوعی نداریم.
# نسخه ۱.۵.۸ یک «warm-up» اختراع کرد که اکانت‌ها را به ۱۲ ادد محدود
# می‌کرد. آن محدودیت ما بود، نه تلگرام. مالک صریحاً خواست اکانت‌ها تا
# حداکثر ظرفیت واقعی‌شان کار کنند و فقط وقتی تلگرام جلویشان را گرفت
# صبر کنیم. WARMUP_STAGES حذف شد.
#
# اگر روزی خواستی دوباره فعالش کنی، با env کنترل می‌شود:
WARMUP_ENABLED = _bool("WARMUP_ENABLED", False)

# فاصله شروع بین اکانت‌ها (ثانیه). صفر یعنی همه با هم.
# این تنها «کندسازی» باقی‌مانده است و خیلی کم نگه داشته شده — فقط
# برای اینکه ۸ اکانت در یک میلی‌ثانیه به یک گروه هجوم نبرند.
STAGGER_START = {
    "ultra": (0, 2),
    "fast": (0, 4),
    "safe": (0, 8),
}
# بازه تاخیر انسانی بین هر ادد (ثانیه)
# سرعت را کاربر با انتخاب حالت تعیین می‌کند — ما تصمیم نمی‌گیریم.
# (۱.۵.۸ حالت safe را خودسرانه دو برابر کند کرده بود؛ برگردانده شد.)
DELAY_RANGES = {
    "ultra": (5, 10),
    "fast": (16, 38),
    "safe": (45, 95),
}
# بازه استراحت انسانی بین دسته‌های ادد (ثانیه)
BREAK_RANGES = {
    "ultra": (45, 120),
    "fast": (60, 180),
    "safe": (120, 300),
}
HUMAN_JITTER_CHANCE = 0.15     # احتمال تاخیر طولانی‌تر شبیه انسان واقعی
HUMAN_JITTER_FACTOR = (1.6, 2.8)

# -----------------------------------------------------------------
# Target group (پیش‌فرض)
# -----------------------------------------------------------------
DEFAULT_TARGET_USERNAME = os.environ.get("DEFAULT_TARGET_USERNAME", "gament_super_gp")
FIXED_TARGET_LINK = os.environ.get("FIXED_TARGET_LINK", "https://t.me/+gLScToU4DZdjZmM0")

# -----------------------------------------------------------------
# Logging
# -----------------------------------------------------------------
LOG_DIR = os.environ.get("LOG_DIR", "logs")
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
LOG_FILE_MAX_BYTES = _int("LOG_FILE_MAX_BYTES", 5_000_000)       # ۵ مگابایت
LOG_BACKUP_COUNT = _int("LOG_BACKUP_COUNT", 5)

# -----------------------------------------------------------------
# App meta
# -----------------------------------------------------------------
APP_VERSION = "1.6.1"
APP_NAME = "Telegram Anti-Scraper Bot (@HaghBaKieBot)"


# -----------------------------------------------------------------
# اعتبارسنجی راه‌اندازی
# -----------------------------------------------------------------
# هیچ‌کدام از مقادیر بالا پیش‌فرض واقعی ندارند — همه باید از محیط بیایند.
# اگر چیزی جا افتاده باشد، بهتر است همین‌جا با پیام واضح متوقف شویم
# تا اینکه بعداً با خطای مبهم Unauthorized یا کانکشن دیتابیس بخوریم.
REQUIRED_ENV = {
    "BOT_TOKEN": BOT_TOKEN,
    "API_ID": API_ID,
    "API_HASH": API_HASH,
    "DATABASE_URL": DATABASE_URL,
}


def missing_env() -> list:
    """فهرست متغیرهای محیطی الزامی که تنظیم نشده‌اند."""
    return [name for name, value in REQUIRED_ENV.items() if not value]


def assert_env(strict: bool = True) -> list:
    """
    بررسی کامل بودن پیکربندی.

    strict=True  → اگر چیزی کم باشد SystemExit با پیام فارسی
    strict=False → فقط فهرست را برمی‌گرداند (برای تست‌ها)
    """
    missing = missing_env()
    if missing and strict:
        raise SystemExit(
            "❌ متغیرهای محیطی الزامی تنظیم نشده‌اند: "
            + ", ".join(missing)
            + "\n   این مقادیر باید در محیط اجرا (Render → Environment) تعریف شوند."
            + "\n   برای اجرای محلی، فایل .env.example را به .env کپی و پر کنید."
        )
    return missing
