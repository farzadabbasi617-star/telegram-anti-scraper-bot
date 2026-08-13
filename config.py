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


# -----------------------------------------------------------------
# Telegram Bot
# -----------------------------------------------------------------
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8790569799:AAFZuVDuVg62v87yQqmaQy3LS_w71-Q6yz0")
ADMIN_ID = _int("ADMIN_ID", 564234793)

# -----------------------------------------------------------------
# Telegram API (user accounts)
# -----------------------------------------------------------------
API_ID = _int("API_ID", 2040)
API_HASH = os.environ.get("API_HASH", "b18441a1ff607e10a989891a5462e627")

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
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://neondb_owner:npg_fLk5QncJezR8@ep-lucky-queen-adg9b8qq-pooler.c-2.us-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require",
)
DB_POOL_SIZE = _int("DB_POOL_SIZE", 6)
SESSION_ENCRYPTION_KEY = os.environ.get("SESSION_ENCRYPTION_KEY", "")

# -----------------------------------------------------------------
# Add Engine (ضد بن)
# -----------------------------------------------------------------
MAX_ADD_PER_ACCOUNT = _int("MAX_ADD_PER_ACCOUNT", 100)          # سقف امن روزانه هر اکانت
MODE_DAILY_CAP = {                                               # سقف روزانه به تفکیک حالت
    "ultra": _int("CAP_ULTRA", 50),
    "fast": _int("CAP_FAST", 100),
    "safe": _int("CAP_SAFE", 100),
}
# بازه تاخیر انسانی بین هر ادد (ثانیه)
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
APP_VERSION = "1.3.2"
APP_NAME = "Telegram Anti-Scraper Bot (@HaghBaKieBot)"
