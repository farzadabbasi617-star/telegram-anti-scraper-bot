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
├── chat_analyzer.py    # تحلیل AI با ۹ مدل رایگان (fallback زنجیره‌ای)
├── lead_finder.py      # شکار لید و گروه‌ها
├── hunter.py / group_finder.py / project_finder.py / instagram_scraper.py
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

## 🔌 نقاط اتصال مهم (Contracts)

- **استیت زنده مینی‌اپ:** `web_app.set_app_refs(app, atk_state)` → `bot.set_atk_state_ref(atk_state)`.
  فلوهای ادد از `atk_state_ref` برای آمار زنده استفاده می‌کنند (کلیدها: `live_added`, `live_skipped`, `live_remaining`, `live_current_account`, `live_active_accounts`, `live_last_user`, `live_mode`, `live_total`, `add_in_progress`).
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
