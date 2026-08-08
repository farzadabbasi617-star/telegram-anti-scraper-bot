# 🛡️ Telegram Anti-Scraper Bot — @HaghBaKieBot

Production bot with 12 scraping methods and channel member adding via AddContact+InviteToChannel.

**Last update:** 2026-08-08 | **Admin:** @FarzadoVs | **Built by:** Arena.ai Agent Mode

---

## Quick Links

| Item | Value |
|------|-------|
| GitHub | farzadabbasi617-star/telegram-anti-scraper-bot |
| Render URL | https://telegram-anti-scraper-bot.onrender.com (port 10000) |
| DB | Neon PostgreSQL (10 tables) |
| Bot | @HaghBaKieBot |
| Workspace | /home/user/final_deploy_render/ |

---

## Deploy

```bash
cd /home/user/final_deploy_render
git config user.email "farzadabbasi617@gmail.com"
git config user.name "farzadabbasi617-star"
git add -A && git commit -m "message" && git push origin main

# Deploy:
curl -X POST "https://api.render.com/v1/services/srv-d9q5i5t3erlc738hos70/deploys" \
  -H "Authorization: Bearer $RENDER_API_KEY" -H "Content-Type: application/json" \
  -d '{"clearCache":"do_not_clear"}'

# Health check:
curl -s "https://telegram-anti-scraper-bot.onrender.com/"
```

> Render Free Tier sleeps after inactivity. Keep-alive pings every 280s. Double-tap /start.

---

## Architecture

| File | Lines | Purpose |
|------|-------|---------|
| `bot.py` | ~4700 | Main file: menus, callbacks, handlers, UI |
| `attacker.py` | ~1260 | 12 scrape methods, WAL, bare-metal extraction |
| `defender.py` | ~400 | Captcha, honeypot, account age filter |
| `db.py` | ~700 | PostgreSQL 10 tables, CRUD, session backup |
| `chat_analyzer.py` | ~470 | AI topic detection (9 free models) |
| `group_finder.py` | ~160 | Search Telegram groups by topic + AI ranking |
| `instagram_scraper.py` | ~170 | IG follower scraper + follow |
| `parallel.py` | ~300 | Multi-account concurrent add |
| `bg_scraper.py` | ~200 | Background auto-scanning |

---

## Scraping — 12 Methods

**3 fast methods (always run):**
1. `scrape_direct_paginated` — member list + Farsi/English pagination
2. `scrape_full_history` — 5K message history
3. `scrape_join_events` — "X joined" messages

**Channel methods:** posts (20K), reactions (5K)
**Advanced:** imported_contacts, global_search, forwarded_messages, aggressive_pagination, group_intersection, deep_history_batch, mtproto_resolve (not in default pipeline)

**Speed:** 200 dialogs loaded (not 2000). AI removed from scrape path. WAL mode. ~100-200 users/min.

---

## Add Members — Most Critical Section

### Telegram API Limitation
`addChatMembers` does NOT work for pure channels. Only groups/supergroups.

### Method Used (4th iteration — Final):
```python
AddContact(user_peer) → InviteToChannel(target_channel, [user_peer])
```
This imports the user to contacts first, then invites them. Works for both channels AND groups.

### Requirements:
- **Account MUST be admin** of the target channel with "Invite Users" permission
- User IDs must be valid: `10000 < uid < 10**11`
- Instagram-scraped users (fake IDs) are filtered out
- Progressive delay: 7-12s → 10-18s after 50 adds
- Cap: 100 adds per account

### Error Reference:
| Error | Meaning |
|-------|---------|
| `PEER_ID_INVALID` | User ID doesn't exist |
| `CHANNEL_INVALID` | Account not in channel |
| `CHAT_ADMIN_REQUIRED` | Account is not admin |
| `FLOOD_WAIT_X` | Rate limited — code auto-waits |

---

## AI Chat Analyzer
- Keyword matching: 200+ Farsi/English keywords, instant
- AI fallback: Groq → OpenRouter → HuggingFace (9 models)
- Available via `🤖 AI Menu` — NOT in scrape path (removed for speed)

## Instagram
- Code complete, blocked by Render datacenter IP (Checkpoint Challenge)
- Workaround: create session via Termux on phone

## Group Finder
- Telegram `search_public_chats` + web fallback + AI ranking
- Requires selected account for Telegram search

## Known Bugs
1. `_sub_back_btn("home")[0]` without `[...]` → TypeError. Always wrap.
2. `MESSAGE_NOT_MODIFIED` in progress updater → harmless, caught
3. git identity lost after stash → re-run `git config`

## Quick Debug
```bash
curl -s "https://telegram-anti-scraper-bot.onrender.com/"  # check health
python3 -c "compile(open('bot.py').read(), 'bot.py', 'exec'); print('OK')"  # syntax
```
