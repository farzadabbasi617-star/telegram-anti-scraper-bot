"""
=================================================================
📱 Telegram Mini App (TMA) & REST API Module - @HaghBaKieBot
=================================================================
داشبورد مدیریت حرفه‌ای و مینی‌اپ تلگرام با ساختار شسته و رفته:
- تفکیک دوگانه حملات: ادد تک اکانت & ادد موازی با تمام اکانت‌ها
- منبع ادد مستقیماً از دیتابیس (scraped_users) به گروه مقصد
- پایش زنده وضعیت سلامت اکانت‌ها، میزان ادد روزانه (100) و تایمر محدودیت‌ها
- ریست اتوماتیک ۲۴ ساعته آمار عملکرد اکانت‌ها
- رابط کاربری مدرن فارسی (RTL) هماهنگ با Telegram WebApp SDK
"""
import os
import json
import time
import asyncio
from aiohttp import web

import db

# Reference to Pyrogram bot and attack state (set by bot.py)
bot_app = None
atk_state_ref = None
_active_add_task = None


# -----------------------------------------------------------------
# REST API HANDLERS
# -----------------------------------------------------------------

async def api_dashboard(request):
    """Get dashboard summary metrics"""
    try:
        total_members = db.count_users()
        accounts = db.load_accounts()
        limits = db.get_adder_limits()
        
        healthy_count = 0
        limited_count = 0
        today_total_adds = 0
        
        for phone, info in accounts.items():
            status_info = db.get_account_status(phone)
            st = status_info.get("status", "healthy")
            today_total_adds += status_info.get("added", 0)
            if st == "healthy":
                healthy_count += 1
            elif st == "limited":
                limited_count += 1
                
        cfg = db.get_config()
        target_group = cfg.get("group_name") or "@gament_super_gp"
        
        # Check active add task status
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
            
        return web.json_response({
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
        })
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def api_accounts(request):
    """Get detailed health status for all accounts"""
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
        return web.json_response({"ok": True, "accounts": out})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def api_members_stats(request):
    """Get scraped members breakdown from database"""
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
                
        return web.json_response({
            "ok": True,
            "stats": {
                "total": len(users),
                "with_phone": phone_count,
                "with_username": username_count,
                "id_only": id_only_count
            }
        })
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def api_reset_limits(request):
    """Reset daily add limit counter for all accounts (24h reset)"""
    try:
        db.reset_adder_limits()
        return web.json_response({"ok": True, "message": "آمار عملکرد تمام اکانت‌ها با موفقیت ریست شد."})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def api_set_target(request):
    """Update default target group setting"""
    try:
        data = await request.json()
        target = data.get("target", "").strip()
        if not target:
            return web.json_response({"ok": False, "error": "شناسه یا لینک گروه مقصد وارد نشده است."}, status=400)
            
        cfg = db.get_config()
        db.set_config(cfg.get("group_id", 0), target, cfg.get("defense_enabled", True))
        return web.json_response({"ok": True, "target": target})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def api_stop_add(request):
    """Stop active add operation"""
    try:
        if atk_state_ref:
            atk_state_ref["_stop_requested"] = True
            atk_state_ref["stop_parallel_add"] = True
        return web.json_response({"ok": True, "message": "درخواست توقف ارسال شد."})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


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
                        document.getElementById('prog-added').innerText = m.add_progress.added || 0;
                        document.getElementById('prog-failed').innerText = m.add_progress.failed || 0;
                        document.getElementById('prog-skipped').innerText = m.add_progress.skipped || 0;
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
            if (activeTab === 'dashboard') loadDashboard();
        }, 5000);

        // Initial Load
        loadDashboard();
    </script>
</body>
</html>
"""

async def serve_mini_app(request):
    """Serve Telegram Mini App SPA HTML"""
    return web.Response(text=MINI_APP_HTML, content_type='text/html', charset='utf-8')


# -----------------------------------------------------------------
# APP ROUTER REGISTRATION
# -----------------------------------------------------------------

def create_web_app(app_bot=None, atk_state=None):
    global bot_app, atk_state_ref
    bot_app = app_bot
    atk_state_ref = atk_state
    
    app = web.Application()
    app.router.add_get('/', serve_mini_app)
    app.router.add_get('/app', serve_mini_app)
    app.router.add_get('/api/dashboard', api_dashboard)
    app.router.add_get('/api/accounts', api_accounts)
    app.router.add_get('/api/members/stats', api_members_stats)
    app.router.add_post('/api/accounts/reset', api_reset_limits)
    app.router.add_post('/api/settings/target', api_set_target)
    app.router.add_post('/api/add/stop', api_stop_add)
    return app
