# 📓 یادداشت‌های عامل (Agent Notes)

اطلاعات حیاتی برای هر عامل/توسعه‌دهنده بعدی که روی این پروژه کار می‌کند.

## 🔑 اطلاعات حیاتی

| مورد | مقدار |
|------|-------|
| ربات | @HaghBaKieBot |
| ادمین | 564234793 (@FarzadoVs) |
| گروه مقصد پیش‌فرض | @gament_super_gp (قابل تنظیم با `DEFAULT_TARGET_USERNAME`) |
| دیتابیس | Neon PostgreSQL (`DATABASE_URL` در env) |
| میزبانی | Render (پورت 10000) — دیپلوی خودکار با push روی main |
| پایتون | 3.11.9 |

## 🗂️ ساختار پروژه

```
├── bot.py              # ورودی اصلی — منوها، کالبک‌ها، هندلرها، فلوهای ادد
├── config.py           # ⚙️ پیکربندی مرکزی (env / .env) — همه از اینجا می‌خوانند
├── logging_setup.py    # 📜 لاگینگ (کنسول + فایل چرخشی + شکار print)
├── add_engine.py       # 🧠 تاخیر انسانی + کش «هرگز دوباره ادد نشود»
├── attacker.py         # ۱۲ متد اسکرپ ممبر
├── defender.py         # کپچا / هانی‌پات / فیلتر سن اکانت
├── db.py               # PostgreSQL: ۱۰ جدول + پول اتصال + رمزنگاری سشن
├── web_app.py          # مینی‌اپ تلگرام + REST API
├── bg_scraper.py       # اسکن خودکار پس‌زمینه
├── channel_adder.py    # ادد ممبر به کانال
├── group_manager.py    # مدیریت گروه (بان/میوت/آنتی‌لینک و…)
├── chat_analyzer.py    # دسته‌بندی موضوعی گروه‌های اسکرپ‌شده (کیورد + AI fallback)
├── lead_finder.py      # شکار لید و گروه‌ها
├── group_finder.py     # جستجوی گروه بر اساس موضوع
├── instagram_scraper.py # اسکرپ فالوور اینستاگرام (اختیاری)
├── tests/              # 🧪 تست‌های خودکار (pytest)
└── .github/workflows/  # CI
```

## 🛠️ گردش کار توسعه

```bash
make ci        # اجرای کامل CI محلی (سینتکس + lint + تست)
make test      # فقط تست‌ها
make lint      # pyflakes روی ماژول‌های اصلی
make run       # اجرای بات
```

⚠️ **قانون طلایی:** قبل از هر push، حداقل `make ci` را اجرا کن.
CI گیت‌هاب هم روی هر push اجرا می‌شود و پوش شکسته را نمی‌گذارد رد شود.

## 🚧 دامنه پروژه — قبل از هر کاری بخوان

**این ربات فقط دو کار می‌کند: اسکرپ ممبر، و ادد ممبر به گروه‌های خودِ مالک.**

در نسخه ۱.۴.۰ کدهای بی‌ربطی که از ریپوهای دیگر همین حساب داخل این پروژه
ادغام شده بودند حذف شدند. **دوباره اضافه‌شان نکن.** `tests/test_scope_clean.py`
نگهبان این قانون است و اگر برگردند CI قرمز می‌شود.

| حذف‌شده | چرا | جای درستش |
|---------|-----|-----------|
| `ai_chat.py`, `flexa_*`, `chat_history.py` | چت‌بات Flexa — ربطی به اسکرپر ندارد | ریپو `Flexa_app` |
| `hunter.py` | اسکنر کیف پول کریپتو | ریپو `crypto-treasure-hunter` |
| `project_finder.py` | اسکنر پروژه گیت‌هاب | جای دیگر |
| `downloader.py` | دانلودر مدیا | جای دیگر |
| `simple_flow.py`, `patch*.py`, `ultimate_accounts.py` | کد مرده، هیچ ارجاعی نداشتند | — |

**ربات‌های دیگر این حساب را با این یکی قاطی نکن:**
- `@HaghBaKieBot` ← **همین ریپو** — Pyrogram — اسکرپ/ادد
- بات داوری «حق با کیه» ← `Flexa_app/haghbakie/` — python-telegram-bot
- `@FlexaTournamentBot` ← `Flexa_app/telegram_bot/` — python-telegram-bot

هر سه اسم مشابه دارند ولی **فریم‌ورکشان ناسازگار است**. هرگز
`python-telegram-bot` را به `requirements.txt` این ریپو اضافه نکن.

## ⚠️ تله‌ی هندلرهای Pyrogram

اگر چند هندلر روی یک فیلتر مشترک (مثل `filters.text & filters.group`) ثبت شوند
و همه در group پیش‌فرض (`0`) باشند، **فقط اولی اجرا می‌شود** و بقیه بی‌صدا
خاموش می‌مانند — بدون هیچ خطایی در لاگ.

این دقیقاً باگی بود که تا نسخه ۱.۴.۰ `defender.monitor_message` را از کار
انداخته بود. الان:

| هندلر | خط | group |
|-------|-----|-------|
| `group_message_filter` (آنتی‌لینک/اسپم) | ~۲۵۶۸ | `0` (پیش‌فرض) |
| `mon` (فیلتر سن اکانت) | ~۷۶۳۷ | `1` |

هر هندلر catch-all جدیدی اضافه کردی، `group=` یکتا بده.

## 🔌 نقاط اتصال مهم (Contracts)

- **استیت زنده مینی‌اپ:** `web_app.set_app_refs(app, atk_state)` → `bot.set_atk_state_ref(atk_state)`.
  فلوهای ادد از `atk_state_ref` برای آمار زنده استفاده می‌کنند (کلیدها: `live_added`, `live_skipped`, `live_remaining`, `live_current_account`, `live_active_accounts`, `live_last_user`, `live_mode`, `live_total`, `add_in_progress`).
- **اشغال اکانت:** قبل از connect به هر سشن `account_state.mark_busy(phone, label)` و در finally `release`.
  اسکن خودکار با `account_doctor.pick_scrape_account()` بین همه اکانت‌های آزاد می‌چرخد.
- **لیست ممنوعه:** همه‌جا از `add_engine.get_blocked_ids_cached()` (کش ۱۲۰ ثانیه‌ای).
  ثبت ممنوعه: `add_engine.never_add_again(uid, reason)` — دلایل: `privacy`, `left`, `invalid`.
- **رمزنگاری سشن:** فرمت `SES3` = MAGIC + nonce(16) + AES-CTR + HMAC-SHA256.
  `decrypt_session_blob` فرمت قدیمی (CTR ساده) و داده خام را هم می‌خواند — چیزی را دستی مایگریت نکن.
- **پول دیتابیس:** `db.get_conn()` یک `_PooledConn` برمی‌گرداند؛ همیشه `cur.close()` را صدا بزن
  (اتصال خودکار آزاد می‌شود؛ `__del__` هم توری ایمنی دارد).

## ➕ افزودن قابلیت جدید

| قابلیت | فایل‌ها |
|--------|---------|
| متد اسکرپ جدید | `attacker.py` (متد) + pipeline در `bot.py` |
| حالت سرعت ادد جدید | `config.py` (DELAY_RANGES / MODE_DAILY_CAP) + `add_engine.py` |
| دکمه منو جدید | `bot.py` (منو + هندلر کالبک) |
| جدول DB جدید | `db.init_tables()` + توابع CRUD در `db.py` |
| ویجت مینی‌اپ جدید | `web_app.py` (HTML + JS + API) + تست در `tests/test_webapp.py` |

## ✅ چک‌لیست پیش از دیپلوی

- [ ] `make ci` سبز است
- [ ] `python -c "compile(open('bot.py').read(),'bot.py','exec')"`
- [ ] `curl -s https://telegram-anti-scraper-bot.onrender.com/` → 200
- [ ] متغیرهای محیطی Render کامل هستند (`.env.example` را ببین)
- [ ] صفحه وضعیت اکانت‌ها درست نمایش می‌دهد
