# 🛡️ Telegram Anti-Scraper Bot — @HaghBaKieBot

ربات مدیریت تلگرام: استخراج ممبر (۱۲ متد)، ادد هوشمند ضد بن، محافظت از گروه در برابر اسکریپت، و داشبورد زنده مینی‌اپ.

<div dir="ltr">

[![CI](https://github.com/farzadabbasi617-star/telegram-anti-scraper-bot/actions/workflows/ci.yml/badge.svg)](https://github.com/farzadabbasi617-star/telegram-anti-scraper-bot/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11](https://img.shields.io/badge/Python-3.11-blue.svg)](runtime.txt)
[![Version](https://img.shields.io/badge/Version-1.3.0-green.svg)](CHANGELOG.md)

</div>

---

## ✨ قابلیت‌ها

| دسته | قابلیت |
|------|--------|
| 🎣 **استخراج** | ۱۲ متد اسکرپ ممبر از گروه/کانال (پجینیشن، هیستوری، ری‌اکشن، سرچ سراسری و…) |
| ➕ **ادد ممبر** | تک‌اکانت و موازی چند اکانتی با ۳ حالت سرعت (Safe / Fast / Ultra) |
| 🐌 **ضد بن** | تاخیرهای انسانی با نویز تصادفی، استراحت‌های دوره‌ای، سقف روزانه هوشمند |
| 🚫 **ضد تکرار** | لیست «هرگز دوباره ادد نشود» — لفت‌داده‌ها، پرایوسی‌بسته‌ها و آیدی‌های نامعتبر برای همیشه حذف می‌شوند |
| 🛡️ **دفاع گروه** | کپچا، هانی‌پات، فیلتر سن اکانت، آنتی‌لینک، آنتی‌اسپم |
| 📱 **مینی‌اپ** | داشبورد RTL فارسی با کنسول زنده عملیات، وضعیت اکانت‌ها و توقف فوری |
| 🏷️ **دسته‌بندی** | تحلیل خودکار موضوع گروه‌های اسکرپ‌شده (کیورد + AI fallback) |
| 🔎 **یافتن گروه** | جستجوی موضوعی گروه‌های تلگرام برای پیدا کردن منبع اسکرپ |

## 🏗️ معماری

```
bot.py            ← ورودی اصلی (منوها، کالبک‌ها، هندلرها)
config.py         ← ⚙️ پیکربندی مرکزی (env / .env)
logging_setup.py  ← 📜 لاگینگ (کنسول + فایل چرخشی + شکار print)
add_engine.py     ← 🧠 تاخیر انسانی + کش لیست ممنوعه + تعیین مقصد
attacker.py       ← ۱۲ متد اسکرپ
defender.py       ← محافظت گروه (کپچا / هانی‌پات)
db.py             ← PostgreSQL + پول اتصال + رمزنگاری سشن (SES3)
web_app.py        ← مینی‌اپ تلگرام + REST API
bg_scraper.py     ← اسکن خودکار پس‌زمینه
account_doctor.py ← تشخیص سلامت اکانت‌ها
account_state.py  ← قفل «اکانت مشغول» با TTL
channel_adder.py  ← ادد ممبر به کانال
group_manager.py  ← مدیریت گروه (بان/میوت/آنتی‌لینک)
chat_analyzer.py  ← دسته‌بندی موضوعی گروه‌های اسکرپ‌شده
group_finder.py   ← جستجوی گروه بر اساس موضوع
lead_finder.py    ← جستجوی گروه تلگرام بر اساس موضوع
parallel.py       ← ادد موازی چند اکانتی
tests/            ← 🧪 ۴۲ تست خودکار + CI گیت‌هاب
```

> **دامنه پروژه:** این ربات فقط برای **اسکرپ و ادد ممبر** به گروه‌های خودتان است.
> ماژول‌های بی‌ربط (داوری/دادگاه، چت‌بات Flexa، کریپتو، اینستاگرام، دانلودر) حذف شده‌اند.
> اگر به آن‌ها نیاز دارید، در ریپوهای جداگانه خودشان نگهداری شوند.

## 🚀 شروع سریع

### پیش‌نیازها
- پایتون 3.10+
- دیتابیس PostgreSQL (پیشنهاد: [Neon](https://neon.tech) رایگان)
- توکن ربات از [@BotFather](https://t.me/BotFather)

### نصب و اجرا

```bash
# ۱) کلون
git clone https://github.com/farzadabbasi617-star/telegram-anti-scraper-bot.git
cd telegram-anti-scraper-bot

# ۲) وابستگی‌ها
pip install -r requirements.txt

# ۳) تنظیم متغیرها — از روی الگو کپی کن و پر کن
cp .env.example .env

# ۴) اجرا
make run        # یا: python bot.py
```

### اجرای تست‌ها و CI

```bash
make ci         # چرخه کامل: سینتکس + lint + تست
make test       # فقط تست‌ها
```

CI گیت‌هاب روی هر push اجرا می‌شود (کامپایل، pyflakes، pytest).

## ⚙️ متغیرهای محیطی

| متغیر | الزامی | پیش‌فرض | توضیح |
|-------|--------|---------|-------|
| `BOT_TOKEN` | ✅ | — | توکن ربات |
| `API_ID` / `API_HASH` | ✅ | — | اعتبارنامه‌های API تلگرام (my.telegram.org) |
| `ADMIN_ID` | ✅ | 564234793 | آیدی عددی ادمین |
| `DATABASE_URL` | ✅ | — | آدرس PostgreSQL |
| `PORT` | — | 10000 | پورت وب (Render) |
| `DB_POOL_SIZE` | — | 6 | اندازه پول اتصال دیتابیس |
| `SESSION_ENCRYPTION_KEY` | — | خالی | رمزنگاری سشن‌ها (AES-CTR + HMAC) |
| `MAX_ADD_PER_ACCOUNT` | — | 100 | سقف روزانه ادد هر اکانت |
| `CAP_ULTRA` / `CAP_FAST` / `CAP_SAFE` | — | 50/100/100 | سقف روزانه به تفکیک حالت |
| `DEFAULT_TARGET_USERNAME` | — | gament_super_gp | گروه مقصد پیش‌فرض |
| `LOG_DIR` / `LOG_LEVEL` | — | logs / INFO | تنظیمات لاگینگ |

## ☁️ استقرار

### Render (روش فعلی)
1. ریپو را به Render وصل کن (Background Worker، دستور `python bot.py`).
2. متغیرهای محیطی بالا را در Dashboard → Environment ثبت کن.
3. دیپلوی خودکار با هر push روی `main`.

### Docker
```bash
make docker
docker run -e BOT_TOKEN=... -e DATABASE_URL=... -e ADMIN_ID=... -p 10000:10000 telegram-anti-scraper-bot
```

## 🐌 حالت‌های سرعت ادد (ضد بن)

| حالت | تاخیر بین ادها | استراحت دوره‌ای | سقف روزانه |
|------|----------------|-----------------|------------|
| 🐌 Safe | ۴۵–۹۵ ثانیه (+نویز) | ۲–۵ دقیقه | 100 |
| ⚡ Fast | ۱۶–۳۸ ثانیه (+نویز) | ۱–۳ دقیقه | 100 |
| ⚡⚡⚡ Ultra | ۵–۱۰ ثانیه (+نویز) | ۴۵–۱۲۰ ثانیه | 50 |

تاخیرها با نویز تصادفی شبیه رفتار انسان شبیه‌سازی می‌شوند؛ در ادد موازی هر اکانت ریتم مستقل خودش را دارد.

## 📚 مستندات بیشتر

- [📓 یادداشت‌های توسعه‌دهنده](docs/agent-notes.md) — قراردادهای داخلی و چک‌لیست دیپلوی
- [📜 تاریخچه تغییرات](CHANGELOG.md)

## ⚠️ سلب مسئولیت

این ابزار صرفاً برای مقاصد آموزشی/مدیریتی ساخته شده است. استفاده از آن باید مطابق با قوانین محلی و شرایط استفاده تلگرام باشد. مسئولیت استفاده بر عهده کاربر است.

## 📄 مجوز

[MIT](LICENSE) © 2026 Farzad Abbasi
