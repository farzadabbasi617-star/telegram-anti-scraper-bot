"""
=================================================================
📱 Telegram Mini App (TMA) & REST API Module - @HaghBaKieBot
=================================================================
داشبورد مدیریت حرفه‌ای و مینی‌اپ تلگرام با ساختار شسته و رفته:
- تفکیک دوگانه حملات: ادد تک اکانت & ادد موازی با تمام اکانت‌ها
- منبع ادد مستقیماً از دیتابیس (scraped_users) به گروه مقصد
- پایش زنده وضعیت سلامت اکانت‌ها، میزان ادد روزانه (100) و تایمر محدودیت‌ها
- ریست اتوماتیک ۲۴ ساعته آمار عملکرد اکانت‌ها
- پشتیبانی دوگانه از aiohttp و http.server استاندارد جهت تضمین ۱۰۰٪ پورت رندر
"""
import os
import json
import time
import asyncio
import re
import random
from http.server import BaseHTTPRequestHandler, HTTPServer

import db

# Reference to Pyrogram bot and attack state (set by bot.py)
bot_app = None
atk_state_ref = None
main_event_loop = None

def set_app_refs(app_bot, atk_state):
    global bot_app, atk_state_ref
    bot_app = app_bot
    atk_state_ref = atk_state

def set_main_event_loop(loop):
    global main_event_loop
    main_event_loop = loop

def _schedule_coro(coro):
    global main_event_loop
    if main_event_loop and main_event_loop.is_running():
        asyncio.run_coroutine_threadsafe(coro, main_event_loop)
    else:
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(coro)
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.create_task(coro)


class _MiniAppMsgWrapper:
    """Mock Message wrapper for Mini App background add tasks"""
    def __init__(self, message=None):
        self.message = self

    async def edit_text(self, text, reply_markup=None, disable_web_page_preview=None, **kw):
        if atk_state_ref:
            atk_state_ref["live_status_text"] = text
            m_added = re.search(r"✅ (\d+)", text)
            m_failed = re.search(r"❌ (\d+)", text)
            m_skipped = re.search(r"⏭ (\d+)", text)
            if m_added: atk_state_ref["live_added"] = int(m_added.group(1))
            if m_failed: atk_state_ref["live_failed"] = int(m_failed.group(1))
            if m_skipped: atk_state_ref["live_skipped"] = int(m_skipped.group(1))


# -----------------------------------------------------------------
# DATA & ATTACK TRIGGER HELPERS
# -----------------------------------------------------------------

def get_dashboard_dict():
    try:
        total_members = db.count_users()
        accounts = db.load_accounts()
        
        healthy_count = 0
        limited_count = 0
        today_total_adds = 0
        
        for phone in accounts:
            st = db.get_account_status(phone)
            status_str = st.get("status", "healthy")
            today_total_adds += st.get("added", 0)
            if status_str == "healthy":
                healthy_count += 1
            elif status_str == "limited":
                limited_count += 1
                
        cfg = db.get_config()
        target_group = cfg.get("group_name") or "@gament_super_gp"
        
        is_running = False
        add_progress = {}
        if atk_state_ref:
            is_running = atk_state_ref.get("add_in_progress", False)
            add_progress = {
                "added": atk_state_ref.get("live_added", 0),
                "failed": atk_state_ref.get("live_failed", 0),
                "skipped": atk_state_ref.get("live_skipped", 0),
                "total": atk_state_ref.get("live_total", 0),
                "mode": atk_state_ref.get("live_mode", "-"),
                "status_text": atk_state_ref.get("live_status_text", "در حال اجرا...")
            }
            
        return {
            "ok": True,
            "metrics": {
                "total_members": total_members,
                "total_accounts": len(accounts),
                "healthy_accounts": healthy_count,
                "limited_accounts": limited_count,
                "today_adds": today_total_adds,
                "target_group": target_group,
                "is_adding": is_running,
                "add_progress": add_progress
            }
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


def get_accounts_dict():
    try:
        accs = db.load_accounts()
        out = []
        for phone, info in accs.items():
            st = db.get_account_status(phone)
            out.append({
                "phone": phone,
                "name": info.get("name", "اکانت"),
                "username": info.get("username", ""),
                "added_today": st.get("added", 0),
                "max_limit": 100,
                "status": st.get("status", "healthy"),
                "limitation_type": st.get("limitation_type"),
                "remaining_seconds": st.get("remaining_seconds", 0),
                "last_used": info.get("last_used", 0)
            })
        return {"ok": True, "accounts": out}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def get_members_stats_dict():
    try:
        users = db.load_users_dict()
        phone_count = 0
        username_count = 0
        id_only_count = 0
        
        for u in users.values():
            if u.get("phone"):
                phone_count += 1
            elif u.get("username"):
                username_count += 1
            else:
                id_only_count += 1
                
        return {
            "ok": True,
            "stats": {
                "total": len(users),
                "with_phone": phone_count,
                "with_username": username_count,
                "id_only": id_only_count
            }
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


def trigger_single_add(phone, add_type):
    """Trigger single account add from DB members to target group"""
    try:
        raw_users = db.get_users_by_source(limit=5000)
        if not raw_users:
            raw_users = list(db.load_users_dict().values())

        filtered = []
        for u in raw_users:
            uid = u.get("user_id") or u.get("id")
            if not uid: continue
            if add_type == "phone" and not u.get("phone"): continue
            if add_type == "username" and not u.get("username"): continue
            if add_type == "id" and (u.get("phone") or u.get("username")): continue
            filtered.append(u)

        if not filtered:
            return False, "هیچ کاربری با این فیلتر در دیتابیس یافت نشد."

        cfg = db.get_config()
        target_gid = cfg.get("group_id") or "@gament_super_gp"

        if atk_state_ref:
            atk_state_ref["add_in_progress"] = True
            atk_state_ref["live_added"] = 0
            atk_state_ref["live_failed"] = 0
            atk_state_ref["live_skipped"] = 0
            atk_state_ref["live_total"] = len(filtered)
            atk_state_ref["live_mode"] = "تک اکانت"
            atk_state_ref["_stop_requested"] = False

        wrapper = _MiniAppMsgWrapper()

        async def run_single_job():
            try:
                from attacker import AdvancedScraper, SESSIONS_DIR, safe_phone_filename
                from bot import API_ID, API_HASH, _execute_simple_add
                accs = db.load_accounts()
                acc_info = accs.get(phone, {})
                client = AdvancedScraper(
                    session_name=os.path.join(SESSIONS_DIR, f"acc_{safe_phone_filename(phone)}"),
                    api_id=API_ID,
                    api_hash=API_HASH,
                    phone=phone,
                    device_fp=acc_info.get("device_fp")
                )
                await client.connect()
                await _execute_simple_add(wrapper, target_gid, client, phone, filtered, "دیتابیس مینی‌اپ")
            except Exception as e:
                print(f"MiniApp single add error: {e}", flush=True)
            finally:
                if atk_state_ref:
                    atk_state_ref["add_in_progress"] = False

        _schedule_coro(run_single_job())
        return True, f"عملیات ادد تک اکانت ({phone}) با موفقیت شروع شد."
    except Exception as e:
        return False, str(e)


def trigger_parallel_add(add_mode, add_type):
    """Trigger parallel multi-account add from DB members to target group"""
    try:
        raw_users = db.get_users_by_source(limit=10000)
        if not raw_users:
            raw_users = list(db.load_users_dict().values())

        filtered = []
        for u in raw_users:
            uid = u.get("user_id") or u.get("id")
            if not uid: continue
            if add_type == "phone" and not u.get("phone"): continue
            if add_type == "username" and not u.get("username"): continue
            if add_type == "id" and (u.get("phone") or u.get("username")): continue
            filtered.append(u)

        if not filtered:
            return False, "هیچ کاربری با این فیلتر در دیتابیس یافت نشد."

        accs = db.load_accounts()
        healthy_accs = {}
        for p, info in accs.items():
            st = db.get_account_status(p)
            if st.get("status") == "healthy" and st.get("added", 0) < 100:
                healthy_accs[p] = info

        if not healthy_accs:
            return False, "هیچ اکانت سالمی برای ادد موازی یافت نشد!"

        cfg = db.get_config()
        target_gid = cfg.get("group_id") or "@gament_super_gp"

        if atk_state_ref:
            atk_state_ref["add_in_progress"] = True
            atk_state_ref["live_added"] = 0
            atk_state_ref["live_failed"] = 0
            atk_state_ref["live_skipped"] = 0
            atk_state_ref["live_total"] = len(filtered)
            atk_state_ref["live_mode"] = f"موازی ({add_mode})"
            atk_state_ref["_stop_requested"] = False
            atk_state_ref["stop_parallel_add"] = False

        wrapper = _MiniAppMsgWrapper()
        from bot import _execute_parallel_add

        async def run_parallel_job():
            try:
                await _execute_parallel_add(wrapper, target_gid, healthy_accs, filtered, add_type, add_mode)
            except Exception as e:
                print(f"MiniApp parallel add error: {e}", flush=True)
            finally:
                if atk_state_ref:
                    atk_state_ref["add_in_progress"] = False

        _schedule_coro(run_parallel_job())
        return True, f"عملیات ادد موازی با {len(healthy_accs)} اکانت شروع شد."
    except Exception as e:
        return False, str(e)


# -----------------------------------------------------------------
# MINI APP HTML FRONTEND (Persian RTL SPA)
# -----------------------------------------------------------------

MINI_APP_HTML = """<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>داشبورد مدیریت ربات ضد اسکریپت</title>
    <script src="https://telegram.org/js/telegram-web_app.js"></script>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://cdn.jsdelivr.net/gh/rastikerdar/vazirmatn@v33.003/Vazirmatn-font-face.css" rel="stylesheet" type="text/css" />
    <style>
        body {
            font-family: 'Vazirmatn', sans-serif;
            background-color: #0f172a;
            color: #f8fafc;
            user-select: none;
            -webkit-user-select: none;
        }
        .glass-card {
            background: rgba(30, 41, 59, 0.7);
            backdrop-filter: blur(12px);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 16px;
        }
        .active-tab {
            background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
            color: #ffffff;
            box-shadow: 0 4px 14px rgba(59, 130, 246, 0.4);
        }
        .pulse-live {
            animation: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite;
        }
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: .5; }
        }
    </style>
</head>
<body class="pb-20">

    <!-- HEADER -->
    <header class="sticky top-0 z-50 glass-card mx-2 mt-2 p-4 flex items-center justify-between shadow-lg">
        <div class="flex items-center gap-3">
            <div class="w-10 h-10 rounded-xl bg-blue-600/20 border border-blue-500/30 flex items-center justify-center text-2xl">
                🛡️
            </div>
            <div>
                <h1 class="text-base font-bold text-white">سامانه آنتی‌اسکریپت</h1>
                <div class="flex items-center gap-1.5 text-xs text-emerald-400 font-medium">
                    <span class="w-2 h-2 rounded-full bg-emerald-500 pulse-live"></span>
                    <span id="status-text">سیستم آماده به کار</span>
                </div>
            </div>
        </div>
        <button onclick="reset24hLimits()" class="px-3 py-1.5 bg-amber-500/20 hover:bg-amber-500/30 border border-amber-500/40 text-amber-300 text-xs rounded-xl flex items-center gap-1 transition">
            🔄 ریست ۲۴ساعته
        </button>
    </header>

    <!-- CONTENT CONTAINERS -->
    <main class="p-3 max-w-lg mx-auto space-y-4">

        <!-- TAB 1: DASHBOARD -->
        <section id="tab-dashboard" class="tab-content space-y-4">
            
            <!-- METRICS GRID -->
            <div class="grid grid-cols-2 gap-3">
                <div class="glass-card p-4 text-center">
                    <div class="text-3xl font-extrabold text-blue-400" id="m-members">...</div>
                    <div class="text-xs text-slate-400 mt-1">👥 ممبرهای دیتابیس</div>
                </div>
                <div class="glass-card p-4 text-center">
                    <div class="text-3xl font-extrabold text-emerald-400" id="m-accounts">...</div>
                    <div class="text-xs text-slate-400 mt-1">📱 اکانت‌های سالم</div>
                </div>
                <div class="glass-card p-4 text-center">
                    <div class="text-3xl font-extrabold text-purple-400" id="m-adds">...</div>
                    <div class="text-xs text-slate-400 mt-1">➕ اددهای امروز</div>
                </div>
                <div class="glass-card p-4 text-center">
                    <div class="text-3xl font-extrabold text-amber-400" id="m-limited">...</div>
                    <div class="text-xs text-slate-400 mt-1">🔴 اکانت‌های محدود</div>
                </div>
            </div>

            <!-- TARGET GROUP SETTING -->
            <div class="glass-card p-4 space-y-3">
                <div class="flex items-center justify-between">
                    <span class="text-sm font-bold text-slate-200">🎯 گروه مقصد پیش‌فرض</span>
                    <span id="target-label" class="text-xs font-mono bg-blue-500/20 text-blue-300 px-2.5 py-1 rounded-lg">@gament_super_gp</span>
                </div>
                <div class="flex gap-2">
                    <input type="text" id="input-target" placeholder="لینک یا یوزرنیم گروه..." class="w-full bg-slate-900/80 border border-slate-700 text-xs text-white rounded-xl px-3 py-2.5 outline-none focus:border-blue-500">
                    <button onclick="saveTargetGroup()" class="bg-blue-600 hover:bg-blue-500 text-white text-xs font-bold px-4 py-2.5 rounded-xl transition">ذخیره</button>
                </div>
            </div>

            <!-- QUICK ATTACK LAUNCHERS -->
            <div class="glass-card p-4 space-y-3">
                <h3 class="text-sm font-bold text-white flex items-center gap-2">
                    <span>⚡ شتاب‌دهنده عملیات ادد</span>
                </h3>
                <div class="grid grid-cols-2 gap-2.5">
                    <button onclick="switchTab('attack')" class="p-3 bg-gradient-to-br from-blue-600 to-indigo-700 text-white text-xs font-bold rounded-xl shadow-lg hover:brightness-110 flex flex-col items-center gap-1">
                        <span class="text-xl">📱</span>
                        <span>ادد تک اکانت</span>
                    </button>
                    <button onclick="switchTab('attack')" class="p-3 bg-gradient-to-br from-emerald-600 to-teal-700 text-white text-xs font-bold rounded-xl shadow-lg hover:brightness-110 flex flex-col items-center gap-1">
                        <span class="text-xl">⚡⚡⚡</span>
                        <span>ادد موازی</span>
                    </button>
                </div>
            </div>
        </section>


        <!-- TAB 2: ATTACK CENTER -->
        <section id="tab-attack" class="tab-content hidden space-y-4">
            
            <!-- ATTACK MODE SELECTOR -->
            <div class="glass-card p-1.5 flex gap-1">
                <button id="btn-mode-single" onclick="setAttackCategory('single')" class="flex-1 py-2.5 text-xs font-bold rounded-xl transition active-tab">
                    📱 ۱. ادد تک اکانت
                </button>
                <button id="btn-mode-parallel" onclick="setAttackCategory('parallel')" class="flex-1 py-2.5 text-xs font-bold text-slate-400 rounded-xl transition">
                    ⚡ ۲. ادد موازی
                </button>
            </div>

            <!-- SINGLE ACCOUNT ADD FORM -->
            <div id="form-single" class="glass-card p-4 space-y-4">
                <h3 class="text-sm font-bold text-blue-400">📱 تنظیمات ادد تک اکانت</h3>
                
                <div>
                    <label class="block text-xs text-slate-300 mb-1.5">انتخاب اکانت ادد کننده:</label>
                    <select id="select-single-account" class="w-full bg-slate-900 border border-slate-700 text-xs text-white rounded-xl p-2.5 outline-none">
                        <option value="">در حال بارگذاری اکانت‌ها...</option>
                    </select>
                </div>

                <div>
                    <label class="block text-xs text-slate-300 mb-1.5">نوع مخاطبین دیتابیس:</label>
                    <select id="select-single-type" class="w-full bg-slate-900 border border-slate-700 text-xs text-white rounded-xl p-2.5 outline-none">
                        <option value="all">🌐 همه مخاطبین دیتابیس</option>
                        <option value="phone">📱 فقط شماره‌دارها</option>
                        <option value="username">🏷️ فقط آیدی‌دارها (Username)</option>
                        <option value="id">🆔 فقط ID عددی</option>
                    </select>
                </div>

                <div class="pt-2">
                    <button onclick="startSingleAdd()" class="w-full py-3 bg-gradient-to-r from-blue-600 to-indigo-600 text-white text-xs font-bold rounded-xl shadow-lg hover:brightness-110">
                        ▶️ شروع ادد تک اکانت از دیتابیس
                    </button>
                </div>
            </div>

            <!-- PARALLEL ADD FORM -->
            <div id="form-parallel" class="glass-card p-4 space-y-4 hidden">
                <h3 class="text-sm font-bold text-emerald-400">⚡ تنظیمات ادد موازی (چند اکانت همزمان)</h3>

                <div>
                    <label class="block text-xs text-slate-300 mb-1.5">انتخاب سرعت و مود ادد:</label>
                    <div class="grid grid-cols-3 gap-2">
                        <button onclick="setParallelSpeed('safe')" id="speed-safe" class="p-2 bg-slate-800 border border-slate-700 text-slate-300 text-xs font-bold rounded-xl text-center hover:border-blue-500">
                            🐌 Safe
                        </button>
                        <button onclick="setParallelSpeed('fast')" id="speed-fast" class="p-2 bg-slate-800 border border-slate-700 text-slate-300 text-xs font-bold rounded-xl text-center hover:border-blue-500">
                            ⚡ Fast
                        </button>
                        <button onclick="setParallelSpeed('ultra')" id="speed-ultra" class="p-2 bg-emerald-600/30 border border-emerald-500 text-emerald-300 text-xs font-bold rounded-xl text-center">
                            ⚡⚡⚡ Ultra
                        </button>
                    </div>
                </div>

                <div>
                    <label class="block text-xs text-slate-300 mb-1.5">فیلتر ممبرها از دیتابیس:</label>
                    <select id="select-parallel-type" class="w-full bg-slate-900 border border-slate-700 text-xs text-white rounded-xl p-2.5 outline-none">
                        <option value="all">🌐 همه کاربران دیتابیس</option>
                        <option value="phone">📱 فقط شماره‌دارها</option>
                        <option value="username">🏷️ فقط شناسه دارها</option>
                        <option value="id">🆔 فقط ID</option>
                    </select>
                </div>

                <div class="pt-2">
                    <button onclick="startParallelAdd()" class="w-full py-3 bg-gradient-to-r from-emerald-600 to-teal-600 text-white text-xs font-bold rounded-xl shadow-lg hover:brightness-110">
                        ⚡⚡⚡ شروع ادد موازی با تمام اکانت‌ها
                    </button>
                </div>
            </div>

            <!-- LIVE MONITORING BOX -->
            <div id="card-live-progress" class="glass-card p-4 space-y-3 hidden">
                <div class="flex items-center justify-between">
                    <span class="text-xs font-bold text-blue-300 flex items-center gap-1.5">
                        <span class="w-2 h-2 rounded-full bg-blue-400 pulse-live"></span>
                        پایش عملیات ادد زنده
                    </span>
                    <button onclick="stopAddOperation()" class="px-2.5 py-1 bg-rose-500/20 text-rose-300 border border-rose-500/40 text-xs font-bold rounded-lg hover:bg-rose-500/30">
                        ⏹️ توقف عملیات
                    </button>
                </div>
                <div class="w-full bg-slate-800 rounded-full h-2.5 overflow-hidden">
                    <div id="prog-bar" class="bg-blue-500 h-2.5 rounded-full transition-all duration-500" style="width: 0%"></div>
                </div>
                <div class="grid grid-cols-3 text-center text-xs pt-1">
                    <div>✅ موفق: <span id="prog-added" class="font-bold text-emerald-400">0</span></div>
                    <div>❌ خطا: <span id="prog-failed" class="font-bold text-rose-400">0</span></div>
                    <div>⏭️ رد شده: <span id="prog-skipped" class="font-bold text-amber-400">0</span></div>
                </div>
            </div>
        </section>


        <!-- TAB 3: ACCOUNTS HEALTH -->
        <section id="tab-accounts" class="tab-content hidden space-y-3">
            <div class="flex items-center justify-between px-1">
                <h3 class="text-sm font-bold text-white">📊 وضعیت سلامت و ظرفیت اکانت‌ها</h3>
                <span class="text-xs text-slate-400">ظرفیت روزانه: ۱۰۰ ادد</span>
            </div>
            
            <div id="accounts-list" class="space-y-2.5">
                <div class="text-center text-slate-400 text-xs py-8">در حال بارگذاری اکانت‌ها...</div>
            </div>
        </section>


        <!-- TAB 4: MEMBER DB -->
        <section id="tab-members" class="tab-content hidden space-y-4">
            <div class="glass-card p-4 space-y-3">
                <h3 class="text-sm font-bold text-white">📂 آمار تفکیکی دیتابیس ممبرها</h3>
                <div class="grid grid-cols-3 gap-2 text-center text-xs">
                    <div class="p-2.5 bg-slate-900/80 rounded-xl">
                        <div class="font-bold text-blue-400" id="db-phone">0</div>
                        <div class="text-slate-400 text-[10px] mt-0.5">شماره‌دار</div>
                    </div>
                    <div class="p-2.5 bg-slate-900/80 rounded-xl">
                        <div class="font-bold text-emerald-400" id="db-username">0</div>
                        <div class="text-slate-400 text-[10px] mt-0.5">شناسه‌دار</div>
                    </div>
                    <div class="p-2.5 bg-slate-900/80 rounded-xl">
                        <div class="font-bold text-amber-400" id="db-id">0</div>
                        <div class="text-slate-400 text-[10px] mt-0.5">فقط ID</div>
                    </div>
                </div>
            </div>
        </section>

    </main>

    <!-- BOTTOM NAVBAR -->
    <nav class="fixed bottom-0 left-0 right-0 glass-card mx-2 mb-2 p-1.5 flex justify-around items-center z-50">
        <button onclick="switchTab('dashboard')" id="nav-dashboard" class="flex-1 py-2 text-xs font-bold text-center rounded-xl transition active-tab">
            📊 داشبورد
        </button>
        <button onclick="switchTab('attack')" id="nav-attack" class="flex-1 py-2 text-xs font-bold text-slate-400 text-center rounded-xl transition">
            ⚡ ادد ممبر
        </button>
        <button onclick="switchTab('accounts')" id="nav-accounts" class="flex-1 py-2 text-xs font-bold text-slate-400 text-center rounded-xl transition">
            📱 اکانت‌ها
        </button>
        <button onclick="switchTab('members')" id="nav-members" class="flex-1 py-2 text-xs font-bold text-slate-400 text-center rounded-xl transition">
            📂 دیتابیس
        </button>
    </nav>

    <!-- JS APP LOGIC -->
    <script>
        const tg = window.Telegram?.WebApp;
        if (tg) {
            tg.ready();
            tg.expand();
        }

        let selectedParallelSpeed = 'ultra';
        let activeTab = 'dashboard';

        function switchTab(tabId) {
            activeTab = tabId;
            document.querySelectorAll('.tab-content').forEach(el => el.classList.add('hidden'));
            document.getElementById('tab-' + tabId).classList.remove('hidden');

            document.querySelectorAll('nav button').forEach(btn => {
                btn.classList.remove('active-tab');
                btn.classList.add('text-slate-400');
            });
            const activeBtn = document.getElementById('nav-' + tabId);
            if (activeBtn) {
                activeBtn.classList.add('active-tab');
                activeBtn.classList.remove('text-slate-400');
            }

            if (tabId === 'dashboard') loadDashboard();
            if (tabId === 'accounts') loadAccounts();
            if (tabId === 'members') loadMembersStats();
            if (tabId === 'attack') loadAttackAccounts();
        }

        function setAttackCategory(cat) {
            if (cat === 'single') {
                document.getElementById('form-single').classList.remove('hidden');
                document.getElementById('form-parallel').classList.add('hidden');
                document.getElementById('btn-mode-single').classList.add('active-tab');
                document.getElementById('btn-mode-parallel').classList.remove('active-tab');
            } else {
                document.getElementById('form-single').classList.add('hidden');
                document.getElementById('form-parallel').classList.remove('hidden');
                document.getElementById('btn-mode-single').classList.remove('active-tab');
                document.getElementById('btn-mode-parallel').classList.add('active-tab');
            }
        }

        function setParallelSpeed(speed) {
            selectedParallelSpeed = speed;
            ['safe', 'fast', 'ultra'].forEach(s => {
                const btn = document.getElementById('speed-' + s);
                if (s === speed) {
                    btn.className = "p-2 bg-emerald-600/30 border border-emerald-500 text-emerald-300 text-xs font-bold rounded-xl text-center";
                } else {
                    btn.className = "p-2 bg-slate-800 border border-slate-700 text-slate-300 text-xs font-bold rounded-xl text-center hover:border-blue-500";
                }
            });
        }

        async function startSingleAdd() {
            const account = document.getElementById('select-single-account').value;
            const addType = document.getElementById('select-single-type').value;

            if (!account) {
                alert('لطفاً یک اکانت انتخاب کنید.');
                return;
            }

            if (!confirm(`آیا از شروع ادد تک اکانت با اکانت ${account} مطمئن هستید؟`)) return;

            try {
                const res = await fetch('/api/add/single', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ phone: account, add_type: addType })
                });
                const data = await res.json();
                alert(data.message || (data.ok ? 'عملیات شروع شد' : data.error));
                if (data.ok) {
                    document.getElementById('card-live-progress').classList.remove('hidden');
                    loadDashboard();
                }
            } catch (e) {
                alert('خطا در برقراری ارتباط با سرور: ' + e);
            }
        }

        async function startParallelAdd() {
            const addType = document.getElementById('select-parallel-type').value;

            if (!confirm(`آیا از شروع ادد موازی با تمام اکانت‌ها در مود ${selectedParallelSpeed.toUpperCase()} مطمئن هستید؟`)) return;

            try {
                const res = await fetch('/api/add/parallel', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ mode: selectedParallelSpeed, add_type: addType })
                });
                const data = await res.json();
                alert(data.message || (data.ok ? 'عملیات ادد موازی شروع شد' : data.error));
                if (data.ok) {
                    document.getElementById('card-live-progress').classList.remove('hidden');
                    loadDashboard();
                }
            } catch (e) {
                alert('خطا در برقراری ارتباط با سرور: ' + e);
            }
        }

        async function loadDashboard() {
            try {
                const res = await fetch('/api/dashboard');
                const data = await res.json();
                if (data.ok) {
                    const m = data.metrics;
                    document.getElementById('m-members').innerText = m.total_members.toLocaleString('fa-IR');
                    document.getElementById('m-accounts').innerText = m.healthy_accounts;
                    document.getElementById('m-adds').innerText = m.today_adds;
                    document.getElementById('m-limited').innerText = m.limited_accounts;
                    document.getElementById('target-label').innerText = m.target_group;

                    if (m.is_adding) {
                        document.getElementById('card-live-progress').classList.remove('hidden');
                        document.getElementById('prog-added').innerText = (m.add_progress.added || 0).toLocaleString('fa-IR');
                        document.getElementById('prog-failed').innerText = (m.add_progress.failed || 0).toLocaleString('fa-IR');
                        document.getElementById('prog-skipped').innerText = (m.add_progress.skipped || 0).toLocaleString('fa-IR');
                        const total = m.add_progress.total || 1;
                        const current = (m.add_progress.added || 0) + (m.add_progress.failed || 0) + (m.add_progress.skipped || 0);
                        const pct = Math.min(100, Math.round((current / total) * 100));
                        document.getElementById('prog-bar').style.width = pct + '%';
                        document.getElementById('status-text').innerText = 'در حال انجام عملیات ادد...';
                    } else {
                        document.getElementById('status-text').innerText = 'سیستم آماده به کار';
                    }
                }
            } catch (e) { console.error(e); }
        }

        async function loadAccounts() {
            try {
                const res = await fetch('/api/accounts');
                const data = await res.json();
                if (data.ok) {
                    const list = document.getElementById('accounts-list');
                    list.innerHTML = '';
                    data.accounts.forEach(acc => {
                        let statusBadge = '<span class="px-2 py-0.5 bg-emerald-500/20 text-emerald-300 text-[10px] rounded-lg">✅ سالم</span>';
                        if (acc.status === 'limited') {
                            const min = Math.ceil(acc.remaining_seconds / 60);
                            statusBadge = `<span class="px-2 py-0.5 bg-rose-500/20 text-rose-300 text-[10px] rounded-lg">🔴 محدود (${min}m)</span>`;
                        } else if (acc.added_today >= 100) {
                            statusBadge = '<span class="px-2 py-0.5 bg-amber-500/20 text-amber-300 text-[10px] rounded-lg">⚠️ ظرفیت پر</span>';
                        }

                        const pct = Math.min(100, Math.round((acc.added_today / 100) * 100));

                        list.innerHTML += `
                            <div class="glass-card p-3 space-y-2">
                                <div class="flex items-center justify-between">
                                    <div>
                                        <div class="text-xs font-bold text-white">${acc.name}</div>
                                        <div class="text-[10px] font-mono text-slate-400">${acc.phone}</div>
                                    </div>
                                    ${statusBadge}
                                </div>
                                <div class="space-y-1">
                                    <div class="flex justify-between text-[10px] text-slate-400">
                                        <span>ادد امروز</span>
                                        <span class="font-bold text-blue-300">${acc.added_today} / 100</span>
                                    </div>
                                    <div class="w-full bg-slate-800 h-1.5 rounded-full overflow-hidden">
                                        <div class="bg-blue-500 h-1.5 rounded-full" style="width: ${pct}%"></div>
                                    </div>
                                </div>
                            </div>
                        `;
                    });
                }
            } catch (e) { console.error(e); }
        }

        async function loadAttackAccounts() {
            try {
                const res = await fetch('/api/accounts');
                const data = await res.json();
                if (data.ok) {
                    const sel = document.getElementById('select-single-account');
                    sel.innerHTML = '';
                    data.accounts.forEach(acc => {
                        sel.innerHTML += `<option value="${acc.phone}">${acc.name} (${acc.phone}) — ${acc.added_today}/100 ادد</option>`;
                    });
                }
            } catch (e) { console.error(e); }
        }

        async function loadMembersStats() {
            try {
                const res = await fetch('/api/members/stats');
                const data = await res.json();
                if (data.ok) {
                    document.getElementById('db-phone').innerText = data.stats.with_phone.toLocaleString('fa-IR');
                    document.getElementById('db-username').innerText = data.stats.with_username.toLocaleString('fa-IR');
                    document.getElementById('db-id').innerText = data.stats.id_only.toLocaleString('fa-IR');
                }
            } catch (e) { console.error(e); }
        }

        async function reset24hLimits() {
            if (!confirm('آیا از ریست کردن شمارنده ادد تمام اکانت‌ها مطمئن هستید؟')) return;
            const res = await fetch('/api/accounts/reset', { method: 'POST' });
            const data = await res.json();
            alert(data.message || 'انجام شد.');
            loadDashboard();
        }

        async function saveTargetGroup() {
            const val = document.getElementById('input-target').value;
            if (!val) return;
            const res = await fetch('/api/settings/target', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ target: val })
            });
            const data = await res.json();
            if (data.ok) alert('گروه مقصد با موفقیت آپدیت شد.');
            loadDashboard();
        }

        async function stopAddOperation() {
            await fetch('/api/add/stop', { method: 'POST' });
            alert('دستور توقف ارسال شد.');
        }

        // Auto Refresh
        setInterval(() => {
            loadDashboard();
            if (activeTab === 'accounts') loadAccounts();
        }, 2000);

        // Initial Load
        loadDashboard();
    </script>
</body>
</html>
"""


# -----------------------------------------------------------------
# STANDARD LIBRARY HTTP SERVER FALLBACK (Zero Dependencies)
# -----------------------------------------------------------------

class StandardWebAppHandler(BaseHTTPRequestHandler):
    """Fallback HTTP Handler using pure standard library (http.server)"""
    def log_message(self, format, *args):
        pass

    def do_HEAD(self):
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()

    def do_GET(self):
        try:
            path = self.path.split('?')[0]
            if path in ['/', '/app', '/index.html']:
                body = MINI_APP_HTML.encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif path == '/api/dashboard':
                data = get_dashboard_dict()
                body = json.dumps(data, ensure_ascii=False).encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif path == '/api/accounts':
                data = get_accounts_dict()
                body = json.dumps(data, ensure_ascii=False).encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif path == '/api/members/stats':
                data = get_members_stats_dict()
                body = json.dumps(data, ensure_ascii=False).encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_response(200)
                self.send_header('Content-Type', 'text/plain; charset=utf-8')
                self.end_headers()
                self.wfile.write(b"OK")
        except Exception as e:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(str(e).encode('utf-8'))

    def do_POST(self):
        try:
            path = self.path.split('?')[0]
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = {}
            if content_length > 0:
                body_bytes = self.rfile.read(content_length)
                try: post_data = json.loads(body_bytes.decode('utf-8'))
                except: pass

            if path == '/api/add/single':
                phone = post_data.get("phone", "")
                add_type = post_data.get("add_type", "all")
                ok, msg = trigger_single_add(phone, add_type)
                body = json.dumps({"ok": ok, "message": msg}).encode('utf-8')
            elif path == '/api/add/parallel':
                add_mode = post_data.get("mode", "ultra")
                add_type = post_data.get("add_type", "all")
                ok, msg = trigger_parallel_add(add_mode, add_type)
                body = json.dumps({"ok": ok, "message": msg}).encode('utf-8')
            elif path == '/api/accounts/reset':
                db.reset_adder_limits()
                body = json.dumps({"ok": True, "message": "آمار عملکرد تمام اکانت‌ها با موفقیت ریست شد."}).encode('utf-8')
            elif path == '/api/settings/target':
                target = post_data.get("target", "").strip()
                if target:
                    cfg = db.get_config()
                    db.set_config(cfg.get("group_id", 0), target, cfg.get("defense_enabled", True))
                body = json.dumps({"ok": True, "target": target}).encode('utf-8')
            elif path == '/api/add/stop':
                if atk_state_ref:
                    atk_state_ref["_stop_requested"] = True
                    atk_state_ref["stop_parallel_add"] = True
                body = json.dumps({"ok": True, "message": "درخواست توقف ارسال شد."}).encode('utf-8')
            else:
                body = json.dumps({"ok": True}).encode('utf-8')

            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(str(e).encode('utf-8'))


def run_standard_server(port):
    """Run pure standard library HTTP server (zero external dependencies)"""
    server = HTTPServer(("0.0.0.0", port), StandardWebAppHandler)
    server.serve_forever()


# -----------------------------------------------------------------
# AIOHTTP ROUTER REGISTRATION
# -----------------------------------------------------------------

def create_web_app(app_bot=None, atk_state=None):
    set_app_refs(app_bot, atk_state)
    try:
        from aiohttp import web
        
        async def aio_serve_mini_app(request):
            return web.Response(text=MINI_APP_HTML, content_type='text/html', charset='utf-8')

        async def aio_api_dashboard(request):
            return web.json_response(get_dashboard_dict())

        async def aio_api_accounts(request):
            return web.json_response(get_accounts_dict())

        async def aio_api_members_stats(request):
            return web.json_response(get_members_stats_dict())

        async def aio_api_add_single(request):
            try:
                data = await request.json()
                phone = data.get("phone", "")
                add_type = data.get("add_type", "all")
                ok, msg = trigger_single_add(phone, add_type)
                return web.json_response({"ok": ok, "message": msg})
            except Exception as e:
                return web.json_response({"ok": False, "error": str(e)}, status=400)

        async def aio_api_add_parallel(request):
            try:
                data = await request.json()
                add_mode = data.get("mode", "ultra")
                add_type = data.get("add_type", "all")
                ok, msg = trigger_parallel_add(add_mode, add_type)
                return web.json_response({"ok": ok, "message": msg})
            except Exception as e:
                return web.json_response({"ok": False, "error": str(e)}, status=400)

        async def aio_api_reset_limits(request):
            db.reset_adder_limits()
            return web.json_response({"ok": True, "message": "آمار عملکرد تمام اکانت‌ها با موفقیت ریست شد."})

        async def aio_api_set_target(request):
            try:
                data = await request.json()
                target = data.get("target", "").strip()
                if target:
                    cfg = db.get_config()
                    db.set_config(cfg.get("group_id", 0), target, cfg.get("defense_enabled", True))
                return web.json_response({"ok": True, "target": target})
            except Exception as e:
                return web.json_response({"ok": False, "error": str(e)}, status=400)

        async def aio_api_stop_add(request):
            if atk_state_ref:
                atk_state_ref["_stop_requested"] = True
                atk_state_ref["stop_parallel_add"] = True
            return web.json_response({"ok": True, "message": "درخواست توقف ارسال شد."})

        app = web.Application()
        app.router.add_get('/', aio_serve_mini_app)
        app.router.add_get('/app', aio_serve_mini_app)
        app.router.add_get('/api/dashboard', aio_api_dashboard)
        app.router.add_get('/api/accounts', aio_api_accounts)
        app.router.add_get('/api/members/stats', aio_api_members_stats)
        app.router.add_post('/api/add/single', aio_api_add_single)
        app.router.add_post('/api/add/parallel', aio_api_add_parallel)
        app.router.add_post('/api/accounts/reset', aio_api_reset_limits)
        app.router.add_post('/api/settings/target', aio_api_set_target)
        app.router.add_post('/api/add/stop', aio_api_stop_add)
        return app
    except ImportError:
        return None
