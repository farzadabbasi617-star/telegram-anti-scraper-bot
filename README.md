<div dir="rtl" align="right">

# 🛡️ Telegram Anti-Scraper Bot (هق با کی - HaghBaKie)

**پیشرفته‌ترین ربات تلگرام — ۱۲ متد اسکرپ، ادد هوشمند چند-اکانته، تحلیل AI، اینستاگرام**

<p align="center">
  <img src="https://img.shields.io/badge/version-2.0-ff69b4" alt="version">
  <img src="https://img.shields.io/badge/python-3.11%2B-blue" alt="python">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="license">
  <img src="https://img.shields.io/badge/AI--Powered-9%20models-purple" alt="ai">
  <img src="https://img.shields.io/badge/scraper%20methods-12-red" alt="methods">
</p>

---

## 🤖 ساخته شده توسط Arena.ai Agent Mode

**این پروژه با همکاری مستقیم یک ایجنت هوش مصنوعی از Arena.ai توسعه داده شده است.**

ایجنت AI به صورت زنده کد را بررسی، دیباگ، بهینه‌سازی و deploy کرده است. تمام تغییرات از طریق API رندر و گیت‌هاب به صورت خودکار اعمال شده‌اند. ایجنت توانایی خواندن کد، جستجوی وب، تحقیق روی best practices، و push مستقیم به production را دارد.

> 💡 **مدل AI:** Arena.ai Agent Mode از ترکیب چندین مدل قدرتمند (Claude، ChatGPT، Gemini، Grok، Qwen، Kimi) با قابلیت اجرای کد، مدیریت فایل، و deploy خودکار استفاده می‌کند.

---

## ⚠️ هشدار مهم قانونی و اخلاقی

**استفاده از این ابزار برای هدف‌گیری گروه‌ها یا کانال‌هایی که مالک آن نیستید، ممنوع و خلاف قوانین تلگرام و قوانین کشوری است.**

---

## 🚀 قابلیت‌های اصلی

### 🎯 ۱۲ متد استخراج پیشرفته (Ultimate Scraper)

| # | متد | توضیح | منبع تحقیق |
|---|------|-------|-----------|
| ۱ | **direct_paginated** | لیست مستقیم + صفحه‌بندی الفبایی فارسی/انگلیسی | Telethon Community |
| ۲ | **deep_history** 🔥 | اسکن عمیق ۲۰K پیام با offset هوشمند و شافل | AbirHasan2005/PRO |
| ۳ | **join_events** | پیام‌های «عضو جدید» | TelegramScraper.shop |
| ۴ | **reactions_dedicated** | اسکن اختصاصی ری‌اکشن‌ها (۱۰K پیام) | KenzaByte |
| ۵ | **channel_posts** | اسکن پست‌های کانال + نویسنده + فروارد + ری‌اکشن | Telegradd |
| ۶ | **import_contacts** | بررسی Contact List + چت‌های مشترک برای اعضای مخفی | Pyrogram Docs |
| ۷ | **global_search** | جستجوی سراسری و cross-reference با گروه | Telethon Community |
| ۸ | **forwarded_messages** 🔥 | اسکن فرواردها، reply authorها و poll voterها | TG-All-In-One |
| ۹ | **aggressive_pagination** 🔥 | صفحه‌بندی Unicode کامل (عربی، سیریلیک، CJK، ایموجی) | Telegradd |
| ۱۰ | **group_intersection** 🔥⭐ | اشتراک گروهی — قوی‌ترین روش برای اعضای مخفی! | AbirHasan2005/PRO |
| ۱۱ | **deep_history_batch** | Batch history با offset پویا | CodebyDevX |
| ۱۲ | **mtproto_resolve** | Batch MTProto raw API resolve | Telethon Internals |

> 🔥 = از بهترین اسکرپرهای دنیا الگوبرداری شده | ⭐ = قوی‌ترین متد

### ⚡ اجرای موازی (۳-۴x سریع‌تر)

```
فاز ۱+۲: paginated ⚡ deep_history (همزمان)
فاز ۳+۴: join_events ⚡ reactions (همزمان)
فاز ۵: forwarded + global_search + import_contacts
فاز ۶: aggressive_pagination ⚡ group_intersection (همزمان)
```

### 📊 Pipeline کامل هر اسکن

```
گروه: paginated → deep_history(20K) → join_events → reactions(10K) → forwarded → global_search → import_contacts → aggro_pagination(80) → intersection(6)
کانال: posts(20K) ⚡ reactions(10K) → global_search → forwarded → paginated
```

---

### ➕ ادد ممبر پیشرفته

| قابلیت | توضیح |
|--------|-------|
| 🎯 **ادد مستقیم از DB** | بدون نیاز به CSV — مستقیم از scraped_users |
| ⚡ **ادد موازی چند-اکانته** | تقسیم خودکار کاربران بین اکانت‌ها بر اساس ظرفیت |
| 📊 **پنل زنده** | Progress bar ۲۰ بلوکی، سرعت، ETA، تحلیل خطا |
| 🛑 **توقف وسط کار** | دکمه توقف در همه مراحل |
| 🔍 **تحلیل خطا** | Privacy / تنظیمات ادد بسته / Flood / Already / Banned |
| 📡 **ادد به کانال** | + ساخت خودکار invite link |
| 📂 **فیلتر منبع** | انتخاب کاربران از دسته‌بندی یا چت خاص |
| 🔄 **بدون تکراری** | خودکار skip میکنه کاربرایی که قبلاً اضافه شدن |

---

### 🧠 تحلیل هوشمند با AI (۹ مدل رایگان)

- **کیورد مچینگ** (رایگان، آنی) — ۲۰۰+ کیورد فارسی و انگلیسی برای ۱۰ دسته
- **AI Fallback با auto-switch**:
  - Groq: Llama 3.3 70B → Llama 3.1 8B → Mixtral 8x7B
  - OpenRouter: Gemini Flash 1.5 → Llama 3.2 3B → Qwen 2.5 7B → Gemma 2 9B
  - HuggingFace: Mistral 7B → Gemma 2 2B
- **Rate-limit handling** — ۵ دقیقه cooldown خودکار
- **دسته‌بندی خودکار** چت‌ها هنگام اسکن

---

### 📸 Instagram Scraper + Follow

- اسکرپ فالوورهای پیج‌های عمومی
- Follow خودکار با تاخیر ۴۰-۱۲۰ ثانیه (شبه‌انسانی)
- سقف روزانه ۶۰ تا — توقف خودکار در action block
- ذخیره در دیتابیس مشترک با تلگرام
- پشتیبانی از 2FA با آپلود فایل سشن

---

### 🗂️ مدیریت هوشمند چت‌ها

- **تاریخچه اسکن** با درصد پیشرفت
- **نوار پیشرفت** ۱۰ بلوکی برای هر چت
- **دسته‌بندی** (گیمینگ، تکنولوژی، کریپتو، فیلم، موسیقی، ورزشی، آشپزی، آموزشی، فروشگاهی، سرگرمی)
- **فیلتر منبع** برای ادد هدفمند
- **اسکن دسته‌جمعی** 🔥 همه گروه‌ها / همه کانال‌ها
- **حذف تکراری‌ها** 🧹 با یک کلیک

---

### 🔐 2FA Bypass

- **آپلود مستقیم فایل سشن** — کلاً نیاز به کد و 2FA رو حذف میکنه
- ۳ خط Pyrogram روی سیستم خودت → فایل `.session` → آپلود توی ربات
- پشتیبانی از Google Authenticator / TOTP / رمز ابری

---

### 🛡️ بخش دفاع

- کپچای ۴ رقمی خودکار
- هانی‌پات نامرئی (zero-width chars)
- تشخیص خروج سریع زیر ۴ دقیقه
- فیلتر اکانت‌های زیر ۲۵ روز
- لیست بن دائمی در دیتابیس

---

## 🧱 معماری پروژه

| فایل | توضیح |
|-------|-------|
| `bot.py` | فایل اصلی — ۴۲۰۰+ خط — منوها، هندلرها، UI |
| `attacker.py` | ۱۲۶۰ خط — ۱۲ متد اسکرپ، اجرای موازی، WAL mode |
| `defender.py` | دفاع پیشرفته — کپچا، هانی‌پات، امتیازدهی |
| `parallel.py` | ادد موازی چند-اکانته |
| `bg_scraper.py` | اسکن خودکار پس‌زمینه |
| `db.py` | PostgreSQL — ۱۰ جدول، بکاپ سشن، CRUD کامل |
| `chat_analyzer.py` | تحلیل AI با ۹ مدل + کیورد مچینگ |
| `instagram_scraper.py` | اسکرپ + Follow اینستاگرام با Instaloader |
| `ultimate_accounts.py` | Proxy Manager + Device Spoofing |
| `project_finder.py` | پروژه‌یاب (GitHub + GitLab + Codeberg) |
| `downloader.py` | دانلودر رسانه (cobalt API) |
| `ai_chat.py` | چت AI |

---

## 🚀 راه‌اندازی

### متغیرهای محیطی (Render):
```
BOT_TOKEN=        # از @BotFather
ADMIN_ID=         # آیدی عددی شما
API_ID=6
API_HASH=eb06d4abfb49dc3eeb1aeb98ae0f581e
DATABASE_URL=     # آدرس Neon PostgreSQL

# (اختیاری) AI:
GROQ_API_KEY=     # gsk_...
OPENROUTER_API_KEY= # sk-or-v1-...
HUGGINGFACE_API_KEY= # hf_...

# (اختیاری) Instagram:
IG_USERNAME=      # اکانت اینستاگرام
IG_PASSWORD=      # رمز اینستاگرام
```

### دیپلوی روی Render:
1. Fork کنید
2. Web Service جدید → connect to GitHub
3. متغیرهای محیطی را وارد کنید
4. Render خودکار deploy میکند

---

## 📊 آمار پروژه

| معیار | مقدار |
|-------|-------|
| 📄 خطوط کد | ~۸,۰۰۰+ |
| 🔥 متدهای اسکرپ | ۱۲ |
| 🤖 مدل‌های AI | ۹ (۳ provider) |
| 🗄️ جداول DB | ۱۰ |
| ⚡ سرعت (نسبت به v1) | ۳-۴x |
| 🐛 باگ fix شده | ۱۵+ |
| 📦 کامیت‌ها | ۶۰+ |

---

## 🤖 توسعه‌دهنده AI

این پروژه توسط **Arena.ai Agent Mode** توسعه و بهینه‌سازی شده است.

ایجنت هوش مصنوعی توانایی‌های زیر را دارد:
- 🧠 **درک عمیق کد** — خواندن و تحلیل ۸۰۰۰+ خط کد
- 🔧 **دیباگ خودکار** — شناسایی و رفع deadlock، race condition، memory leak
- 📚 **تحقیق آنلاین** — جستجوی گیت‌هاب، Stack Overflow، مستندات
- ⚡ **بهینه‌سازی** — اجرای موازی، WAL mode، batch processing
- 🚀 **Deploy خودکار** — push به گیت‌هاب + trigger رندر
- 🎨 **UI/UX** — طراحی منوها، progress bar، dashboard

---

## 📝 لایسنس
MIT

---

## 🔗 لینک‌ها
- [گیت‌هاب](https://github.com/farzadabbasi617-star/telegram-anti-scraper-bot)
- [ربات تلگرام](https://t.me/HaghBaKieBot)
- [Arena.ai](https://arena.ai)

---

*ساخته شده با ❤️ و 🤖 — Arena.ai Agent Mode*

</div>
