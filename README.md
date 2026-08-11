# 🛡️ Telegram Anti-Scraper Bot — @HaghBaKieBot

**Production Telegram bot for scraping members from groups/channels and adding them to target groups with advanced features.**

**Last update:** 2026-08-11 | **Admin:** @FarzadoVs | **Built by:** Arena.ai Agent Mode

---

## 🎯 Project Overview

This bot provides a complete solution for:
1. **Scraping members** from Telegram groups/channels (12 methods)
2. **Adding members** to target groups (single account or parallel)
3. **Managing accounts** with status tracking and limitation monitoring
4. **Protecting groups** from scrapers (captcha, honeypot, account age filter)

**Key Features:**
- ✅ 12 scraping methods (direct, history, join events, etc.)
- ✅ Single account add with 3 speed modes (Safe/Fast/Ultra Fast)
- ✅ Parallel add with multiple accounts (10+ accounts)
- ✅ Account status tracking with limitation monitoring
- ✅ Ultra Fast Mode: 50-100 adds in 5-10 minutes
- ✅ Default target group support (@gament_super_gp)
- ✅ Database-driven member storage (PostgreSQL)
- ✅ AI-powered chat analysis (9 free models)
- ✅ Group finder with AI ranking
- ✅ Instagram scraper (blocked on Render, works locally)

---

## 📊 Quick Stats

| Metric | Value |
|--------|-------|
| **Total Lines** | ~8,000 |
| **Main Files** | 12 Python files |
| **Database Tables** | 10 PostgreSQL tables |
| **Scraping Methods** | 12 methods |
| **Add Speed Modes** | 3 modes (Safe/Fast/Ultra) |
| **Max Accounts** | Unlimited (tested with 10+) |

---

## 🚀 Quick Links

| Item | Value |
|------|-------|
| **GitHub** | [farzadabbasi617-star/telegram-anti-scraper-bot](https://github.com/farzadabbasi617-star/telegram-anti-scraper-bot) |
| **Render URL** | https://telegram-anti-scraper-bot.onrender.com (port 10000) |
| **Database** | Neon PostgreSQL (10 tables) |
| **Bot Username** | @HaghBaKieBot |
| **Admin ID** | 564234793 (@FarzadoVs) |
| **Default Target** | @gament_super_gp |

---

## 🏗️ Architecture

### Main Files

| File | Lines | Purpose |
|------|-------|---------|
| `bot.py` | ~8,000 | **Main file**: menus, callbacks, handlers, UI, add logic |
| `attacker.py` | ~1,260 | 12 scraping methods, WAL mode, bare-metal extraction |
| `defender.py` | ~400 | Captcha, honeypot, account age filter |
| `db.py` | ~700 | PostgreSQL 10 tables, CRUD, session backup, limitation tracking |
| `chat_analyzer.py` | ~470 | AI topic detection (9 free models) |
| `group_finder.py` | ~160 | Search Telegram groups by topic + AI ranking |
| `instagram_scraper.py` | ~170 | IG follower scraper + follow (blocked on Render) |
| `parallel.py` | ~300 | Multi-account concurrent add (legacy, not used) |
| `bg_scraper.py` | ~200 | Background auto-scanning |
| `simple_flow.py` | ~100 | Simplified add flow (legacy) |

### Database Schema (10 Tables)

```sql
-- Core tables
users_tbl              -- User accounts (admin only)
scraped_users          -- Scraped members (user_id, username, phone, source)
saved_accounts_tbl     -- Saved Telegram accounts (phone, session, device_fp)
adder_limits_tbl       -- Add limits per account (added, limitation_type, limitation_until)
added_history_tbl      -- History of added members

-- Feature tables
kyc_profiles           -- KYC verification (not used yet)
store_listings         -- Store listings (not used yet)
store_orders           -- Store orders (not used yet)
scraped_chats_tbl      -- Scraped chat metadata
notifications_tbl      -- User notifications
```

---

## 🔧 Deployment

### Deploy to Render

```bash
# 1. Clone and configure
git clone https://github.com/farzadabbasi617-star/telegram-anti-scraper-bot.git
cd telegram-anti-scraper-bot

# 2. Set git identity
git config user.email "your-email@gmail.com"
git config user.name "your-username"

# 3. Commit and push
git add -A && git commit -m "your message" && git push origin main

# 4. Deploy (optional, auto-deploys on push)
curl -X POST "https://api.render.com/v1/services/srv-d9q5i5t3erlc738hos70/deploys" \
  -H "Authorization: Bearer $RENDER_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"clearCache":"do_not_clear"}'

# 5. Health check
curl -s "https://telegram-anti-scraper-bot.onrender.com/"
```

### Environment Variables

```bash
# Required
DATABASE_URL=postgresql://user:pass@host:port/db
BOT_TOKEN=123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
ADMIN_ID=564234793

# Optional
API_ID=123456
API_HASH=0123456789abcdef0123456789abcdef
PORT=10000
```

> **Note:** Render Free Tier sleeps after 15 minutes of inactivity. Bot has keep-alive pings every 280 seconds.

---

## 📱 Scraping — 12 Methods

### Fast Methods (Always Run)

1. **scrape_direct_paginated** — Member list with Farsi/English pagination
2. **scrape_full_history** — Last 5,000 messages
3. **scrape_join_events** — "X joined" messages

### Channel Methods

4. **scrape_channel_posts** — Last 20,000 posts
5. **scrape_channel_reactions** — Last 5,000 reactions

### Advanced Methods (Optional)

6. **scrape_imported_contacts** — Imported contacts
7. **scrape_global_search** — Global search results
8. **scrape_forwarded_messages** — Forwarded messages
9. **scrape_aggressive_pagination** — Aggressive pagination
10. **scrape_group_intersection** — Group intersection
11. **scrape_deep_history_batch** — Deep history batch
12. **mtproto_resolve** — MTProto resolve (not in default pipeline)

### Performance

- **Speed:** ~100-200 users/minute
- **Dialogs loaded:** 200 (not 2000 for speed)
- **WAL mode:** Enabled for SQLite sessions
- **AI removed:** From scrape path for speed

---

## ➕ Add Members — Critical Section

### Telegram API Limitation

**`addChatMembers` does NOT work for pure channels. Only groups/supergroups.**

### Method Used (Final — 4th Iteration)

```python
# Step 1: Add user to contacts
AddContact(user_peer, first_name, last_name="", phone="")

# Step 2: Wait 0.5 seconds
await asyncio.sleep(0.5)

# Step 3: Invite to channel/group
InviteToChannel(target_channel, [user_peer])
```

**Why this works:**
- Imports user to contacts first (bypasses some restrictions)
- Then invites them to channel/group
- Works for both channels AND groups

### Requirements

- ✅ **Account MUST be admin** of target channel with "Invite Users" permission
- ✅ User IDs must be valid: `10000 < uid < 10**11`
- ✅ Instagram-scraped users (fake IDs) are filtered out
- ✅ Target group must be Supergroup (not basic group)

### Three Speed Modes

#### 🐌 Safe Mode
```python
MAX_ADD_PER_ACCOUNT = 100
delay = random.randint(90, 180)  # 1.5-3 minutes
breaks = every 10 adds, 5-10 minutes
time = ~5 hours per account
```

#### ⚡ Fast Mode
```python
MAX_ADD_PER_ACCOUNT = 200
delay = random.randint(30, 60)  # 30-60 seconds
breaks = every 20 adds, 2-3 minutes
time = ~2 hours per account
```

#### ⚡⚡⚡ Ultra Fast Mode
```python
MAX_ADD_PER_ACCOUNT = 500
delay = random.randint(1, 3)  # 1-3 seconds
breaks = None
time = ~5-10 minutes per account
expected = 50-100 adds before limitation
recovery = 24-48 hours
```

### Error Reference

| Error | Meaning | Solution |
|-------|---------|----------|
| `PEER_ID_INVALID` | User ID doesn't exist | Skip user |
| `CHANNEL_INVALID` | Account not in channel | Join channel first |
| `CHAT_ADMIN_REQUIRED` | Account is not admin | Make account admin |
| `FLOOD_WAIT_X` | Rate limited | Auto-waits X seconds |
| `USER_PRIVACY_RESTRICTED` | User privacy settings | Skip user |
| `AUTH_KEY_UNREGISTERED` | Session expired | Re-login account |

---

## 📊 Account Status Tracking

### Features

- ✅ Real-time status for all accounts
- ✅ Limitation type tracking (FloodWait, PEER_FLOOD, etc.)
- ✅ Remaining time until limitation ends
- ✅ Auto-clears expired limitations
- ✅ Color-coded status indicators

### Status Types

| Icon | Status | Meaning |
|------|--------|---------|
| ✅ | **سالم** (Healthy) | Ready to add |
| ⚠️ | **پر شده** (Full) | Daily capacity reached |
| 🔴 | **محدود** (Limited) | FloodWait or limitation |

### Database Schema

```sql
adder_limits_tbl (
    phone TEXT PRIMARY KEY,
    added INTEGER DEFAULT 0,
    last_used INTEGER DEFAULT 0,
    limitation_type TEXT DEFAULT NULL,
    limitation_until INTEGER DEFAULT 0
)
```

### Usage

```
⚙️ تنظیمات → 📊 وضعیت اکانت‌ها

📊 وضعیت اکانت‌ها
━━━━━━━━━━━━━━━━━━

✅ Farzad
   📱 +989913928426
   📊 وضعیت: سالم
   ➕ اد امروز: 39/200

🔴 Account2
   📱 +989924237228
   📊 وضعیت: محدود (FloodWait)
   ➕ اد امروز: 150/200
   ⏰ پایان محدودیت: 2h 30m
```

---

## 🎯 Add Flows

### Flow 1: Single Account Add (ادد ممبر)

```
1. ➕ ادد ممبر (main menu)
2. 📊 تفکیک مخاطبین (redirect)
3. Select type: 📱 شماره‌دارها / 🏷️ username دارها / 🆔 ID-only / 🌐 همه
4. Select account: 📱 Farzad (+989913928426)
5. Confirm: ▶️ شروع اد
6. Add from database to @gament_super_gp
```

### Flow 2: Parallel Add (اد موازی)

```
1. ⚡ اد موازی با همه اکانت‌ها (from تفکیک)
2. Select type: 📱 شماره‌دارها / 🏷️ username دارها / 🆔 ID-only / 🌐 همه
3. Select mode: 🐌 Safe / ⚡ Fast / ⚡⚡⚡ Ultra Fast
4. Confirm: ▶️ شروع اد موازی
5. Add from database with all accounts to @gament_super_gp
```

### Flow 3: Quick Add (اد سریع)

```
1. 📊 تفکیک مخاطبین
2. Select type: 📱 شماره‌دارها
3. ⚡ اد سریع (Fast Mode)
4. Select account
5. Confirm and start
```

---

## 🤖 Bot Menu Structure

### Main Menu

```
🛡️ ربات ضد اسکریپت
━━━━━━━━━━━━━━━━━━

[🚀 حمله (اسکرپ)]
[➕ ادد ممبر] [⚡ اد موازی]
[📊 تفکیک مخاطبین]
[🛡️ دفاع] [📱 اکانت‌ها]
[⚙️ تنظیمات] [❓ راهنما]
```

### Settings Menu

```
⚙️ تنظیمات
━━━━━━━━━━━━━━━━━━

🔸 مدیریت اکانت‌ها — افزودن، حذف، بکاپ سشن
🔸 وضعیت اکانت‌ها — مشاهده وضعیت و محدودیت‌ها
🔸 اسکن خودکار — زمان‌بندی و فعالسازی
🔸 ریست آمار — پاک کردن شمارنده‌های ادد
🔸 پاک کردن لیست ممبر — خالی کردن دیتابیس
🔸 دانلود CSV — خروجی اکسل از داده‌ها

[📱 مدیریت اکانت‌ها] [📊 وضعیت اکانت‌ها]
[⏱️ اسکن خودکار] [🔄 ریست آمار ادد]
[🧹 حذف تکراری‌ها] [🗑️ پاک کردن لیست ممبر]
[📥 CSV ممبرها] [📥 CSV تاریخچه ادد]
[🔝 منوی اصلی]
```

### Account Management

```
📱 مدیریت اکانت‌ها
━━━━━━━━━━━━━━━━━━

[➕ افزودن اکانت]
[📊 وضعیت اکانت‌ها]
[🗑️ حذف اکانت]
[📤 بکاپ سشن]
[📥 بازیابی سشن]
[🔙 بازگشت]
```

---

## 🔍 Key Callbacks

| Callback | Purpose |
|----------|---------|
| `user_breakdown` | Show member breakdown (phone/username/ID) |
| `add_by_type_*` | Start single account add |
| `simple_acc_*` | Select account for single add |
| `simple_start_add` | Start single add |
| `parallel_add_breakdown` | Start parallel add |
| `parallel_type_*` | Select type for parallel add |
| `parallel_mode_*` | Select mode (Safe/Fast/Ultra) |
| `parallel_start_confirmed` | Start parallel add |
| `account_status` | Show account status page |
| `manage_accounts` | Account management menu |

---

## 🧪 Testing & Debugging

### Health Check

```bash
curl -s "https://telegram-anti-scraper-bot.onrender.com/"
```

### Syntax Check

```bash
python3 -c "compile(open('bot.py').read(), 'bot.py', 'exec'); print('OK')"
```

### Database Check

```bash
# Connect to Neon PostgreSQL
psql $DATABASE_URL

# Check tables
\dt

# Check scraped users
SELECT COUNT(*) FROM scraped_users;

# Check account limits
SELECT phone, added, limitation_type, limitation_until FROM adder_limits_tbl;
```

---

## 🐛 Known Issues & Solutions

### Issue 1: Syntax Error — `'[' was never closed`

**Cause:** Missing closing bracket in button list

**Solution:** Check line 4164 in bot.py, ensure all `[` have matching `]`

### Issue 2: `MESSAGE_NOT_MODIFIED` in progress updater

**Cause:** Trying to edit message with same content

**Solution:** Harmless, caught in try-except block

### Issue 3: Git identity lost after deploy

**Cause:** Render doesn't persist git config

**Solution:** Re-run `git config` before each commit

### Issue 4: `AUTH_KEY_UNREGISTERED` error

**Cause:** Session expired or account banned

**Solution:** Re-login account or use different account

### Issue 5: Instagram scraper blocked on Render

**Cause:** Render datacenter IP blocked by Instagram

**Solution:** Create session via Termux on phone, upload session file

---

## 📝 Notes for Next Agent

### Critical Information

1. **Default target group:** `@gament_super_gp` (hardcoded in `DEFAULT_TARGET_USERNAME`)
2. **Admin ID:** `564234793` (only this user can use bot)
3. **Database:** Neon PostgreSQL (connection string in `DATABASE_URL` env var)
4. **Render service ID:** `srv-d9q5i5t3erlc738hos70`
5. **Port:** 10000 (Render requirement)

### File Structure

- `bot.py` — **Main file** (8,000 lines, contains everything)
- `attacker.py` — Scraping logic (12 methods)
- `db.py` — Database operations
- `defender.py` — Group protection
- Other files — Auxiliary features

### Important Functions

```python
# Scraping
async def scrape_group(client, group_id) -> List[Dict]

# Adding
async def add_member_single(client, target_gid, user_peer) -> bool
async def add_member_parallel(accs, target_gid, members, mode) -> Dict

# Database
def load_adder_limits() -> Dict[str, Dict]
def save_adder_limits(limits: Dict[str, Dict]) -> None
def get_account_status(phone: str) -> Dict

# Account management
def list_saved_accounts() -> Dict[str, Dict]
def save_account(phone: str, session_blob: bytes) -> None
```

### Common Tasks

**Add new scraping method:**
1. Add method to `attacker.py`
2. Add to scraping pipeline in `bot.py` (search for `scrape_methods`)

**Add new add mode:**
1. Add mode to `bot.py` (search for `parallel_mode_`)
2. Update delay logic in `_execute_parallel_add`

**Add new menu button:**
1. Add button to menu in `bot.py` (search for menu name)
2. Add callback handler (search for `if d == "callback_name"`)

**Update database schema:**
1. Add migration to `db.py` in `ensure_schema()`
2. Update CRUD functions as needed

### Testing Checklist

- [ ] Bot starts without errors
- [ ] Health check returns 200
- [ ] Can scrape from test group
- [ ] Can add to test group (single account)
- [ ] Can add to test group (parallel)
- [ ] Account status page shows correct info
- [ ] Limitations auto-clear after expiry

---

## 📚 Resources

### Telegram API

- [Pyrogram Documentation](https://docs.pyrogram.org/)
- [Telegram API Limits](https://core.telegram.org/bots/faq)
- [MTProto Protocol](https://core.telegram.org/mtproto)

### Deployment

- [Render Documentation](https://render.com/docs)
- [Neon PostgreSQL](https://neon.tech/docs)

### Related Projects

- [Flexa_app](https://github.com/farzadabbasi617-star/Flexa_app) — Gaming tournament platform

---

## 📄 License

MIT License — Free to use and modify.

---

**Built with ❤️ by Arena.ai Agent Mode**

**Last updated:** 2026-08-11
