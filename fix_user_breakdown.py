with open('bot.py', 'r', encoding='utf-8') as f:
    content = f.read()

changes = 0

# ═══════════════════════════════════════════════════════
# FIX 1: Add "📊 تفکیک" button to main menu next to مخاطبین
# ═══════════════════════════════════════════════════════
old_menu = '''        InlineKeyboardButton(f"👥 مخاطبین ({total_users})", callback_data="show_list_0"),
        InlineKeyboardButton(f"📈 آمار ادد", callback_data="adder_stats"),'''

new_menu = '''        InlineKeyboardButton(f"👥 مخاطبین ({total_users})", callback_data="show_list_0"),
        InlineKeyboardButton("📊 تفکیک", callback_data="user_breakdown"),'''

if old_menu in content:
    content = content.replace(old_menu, new_menu)
    changes += 1
    print("✅ Fix 1: Added breakdown button to main menu")

# ═══════════════════════════════════════════════════════
# FIX 2: Add "📊 تفکیک مخاطبین" button to show_list_0 page
# ═══════════════════════════════════════════════════════
old_list_btn = '''        nav_buttons.append([InlineKeyboardButton("📥 دانلود CSV کامل", callback_data="download_csv")])'''
new_list_btn = '''        nav_buttons.append([InlineKeyboardButton("📊 تفکیک مخاطبین", callback_data="user_breakdown"),
                            InlineKeyboardButton("📥 دانلود CSV", callback_data="download_csv")])'''

if old_list_btn in content:
    content = content.replace(old_list_btn, new_list_btn)
    changes += 1
    print("✅ Fix 2: Added breakdown button to list page")

# ═══════════════════════════════════════════════════════
# FIX 3: Add the user_breakdown handler (after show_list_source_)
# Find the end of show_list_source_ handler
# ═══════════════════════════════════════════════════════

breakdown_handler = '''
    # ==================== 📊 تفکیک مخاطبین ====================
    if d == "user_breakdown":
        try:
            cur = db.get_conn().cursor()
            
            # Total
            cur.execute("SELECT COUNT(*) FROM scraped_users")
            total = cur.fetchone()[0]
            
            # With phone
            cur.execute("SELECT COUNT(*) FROM scraped_users WHERE phone IS NOT NULL AND phone != ''")
            with_phone = cur.fetchone()[0]
            
            # With username (no phone)
            cur.execute("""
                SELECT COUNT(*) FROM scraped_users 
                WHERE username IS NOT NULL AND username != '' 
                AND (phone IS NULL OR phone = '')
            """)
            username_only = cur.fetchone()[0]
            
            # With both phone and username
            cur.execute("""
                SELECT COUNT(*) FROM scraped_users 
                WHERE phone IS NOT NULL AND phone != '' 
                AND username IS NOT NULL AND username != ''
            """)
            both = cur.fetchone()[0]
            
            # ID only (no phone, no username)
            cur.execute("""
                SELECT COUNT(*) FROM scraped_users 
                WHERE (phone IS NULL OR phone = '') 
                AND (username IS NULL OR username = '')
            """)
            id_only = cur.fetchone()[0]
            
            # Already added
            cur.execute("SELECT COUNT(DISTINCT user_id) FROM added_history_tbl")
            already_added = cur.fetchone()[0]
            
            cur.close()
        except Exception as e:
            await q.answer(f"خطا: {str(e)[:100]}", show_alert=True)
            return
        
        text = f"📊 <b>تفکیک مخاطبین</b>\\n"
        text += f"━━━━━━━━━━━━━━━━━━\\n\\n"
        
        text += f"👥 <b>مجموع:</b> {total:,} نفر\\n"
        text += f"✅ <b>ادد شده:</b> {already_added:,} نفر\\n"
        text += f"⏳ <b>باقیمانده:</b> {total - already_added:,} نفر\\n\\n"
        
        text += f"━━━━━━━━━━━━━━━━━━\\n"
        text += f"📊 <b>تفکیک بر اساس نوع:</b>\\n\\n"
        
        # Phone users
        phone_total = with_phone  # includes those with both phone+username
        phone_pct = phone_total * 100 // max(1, total)
        phone_bar = "🟩" * (phone_pct // 10) + "⬜" * (10 - phone_pct // 10)
        text += f"📱 <b>با شماره تلفن:</b> {phone_total:,} ({phone_pct}%)\\n"
        text += f"   {phone_bar}\\n"
        text += f"   └ نرخ موفقیت اد: ~70% ≈ {int(phone_total * 0.7):,} نفر\\n\\n"
        
        # Username only
        uname_pct = username_only * 100 // max(1, total)
        uname_bar = "🟩" * (uname_pct // 10) + "⬜" * (10 - uname_pct // 10)
        text += f"🏷️ <b>فقط username (بدون شماره):</b> {username_only:,} ({uname_pct}%)\\n"
        text += f"   {uname_bar}\\n"
        text += f"   └ نرخ موفقیت اد: ~40% ≈ {int(username_only * 0.4):,} نفر\\n\\n"
        
        # Both
        text += f"⭐ <b>هم شماره هم username:</b> {both:,}\\n\\n"
        
        # ID only
        id_pct = id_only * 100 // max(1, total)
        id_bar = "🟩" * (id_pct // 10) + "⬜" * (10 - id_pct // 10)
        text += f"🆔 <b>فقط آیدی عددی:</b> {id_only:,} ({id_pct}%)\\n"
        text += f"   {id_bar}\\n"
        text += f"   └ نرخ موفقیت اد: ~15% ≈ {int(id_only * 0.15):,} نفر\\n\\n"
        
        # Summary
        text += f"━━━━━━━━━━━━━━━━━━\\n"
        est_total = int(phone_total * 0.7) + int(username_only * 0.4) + int(id_only * 0.15)
        text += f"🎯 <b>مجموع قابل اد (تخمین):</b> ~{est_total:,} نفر\\n"
        
        # Buttons for adding by type
        buttons = []
        buttons.append([
            InlineKeyboardButton(f"📱 اد شماره‌دارها ({phone_total:,})", callback_data="add_by_type_phone"),
        ])
        buttons.append([
            InlineKeyboardButton(f"🏷️ اد username دارها ({username_only:,})", callback_data="add_by_type_username"),
        ])
        buttons.append([
            InlineKeyboardButton(f"🆔 اد ID-only ها ({id_only:,})", callback_data="add_by_type_id"),
        ])
        buttons.append([
            InlineKeyboardButton("🌐 اد همه", callback_data="add_by_type_all"),
        ])
        buttons.append([
            InlineKeyboardButton("👥 لیست مخاطبین", callback_data="show_list_0"),
            InlineKeyboardButton("🏠 خانه", callback_data="home"),
        ])
        
        await q.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons), disable_web_page_preview=True)
        return

    # ==================== ➕ اد بر اساس نوع کاربر ====================
    if d.startswith("add_by_type_"):
        add_type = d[len("add_by_type_"):]
        
        # Store filter type in atk_state
        atk_state["add_member_type"] = add_type
        
        # Get counts
        try:
            cur = db.get_conn().cursor()
            if add_type == "phone":
                cur.execute("SELECT COUNT(*) FROM scraped_users WHERE phone IS NOT NULL AND phone != ''")
                count = cur.fetchone()[0]
                label = "📱 شماره‌دارها"
            elif add_type == "username":
                cur.execute("""SELECT COUNT(*) FROM scraped_users 
                    WHERE username IS NOT NULL AND username != '' AND (phone IS NULL OR phone = '')""")
                count = cur.fetchone()[0]
                label = "🏷️ username دارها"
            elif add_type == "id":
                cur.execute("""SELECT COUNT(*) FROM scraped_users 
                    WHERE (phone IS NULL OR phone = '') AND (username IS NULL OR username = '')""")
                count = cur.fetchone()[0]
                label = "🆔 فقط ID"
            else:  # all
                cur.execute("SELECT COUNT(*) FROM scraped_users")
                count = cur.fetchone()[0]
                label = "🌐 همه"
            cur.close()
        except:
            count = 0
            label = "کاربران"
        
        # Show account picker
        accs = list_saved_accounts()
        if not accs:
            await q.answer("اول اکانت اضافه کن!", show_alert=True)
            return
        
        text = f"➕ <b>اد {label}</b>\\n"
        text += f"━━━━━━━━━━━━━━━━━━\\n"
        text += f"👥 {count:,} نفر آماده\\n\\n"
        text += f"اکانت اد‌زننده رو انتخاب کن:"
        
        buttons = []
        for phone, info in accs.items():
            name = info.get("name", phone)[:20]
            limits = load_adder_limits()
            added = limits.get(phone, {}).get("added", 0)
            remaining = MAX_ADD_PER_ACCOUNT - added
            status = f"({remaining} ظرفیت)" if remaining > 0 else "⚠️ پر"
            buttons.append([InlineKeyboardButton(f"📱 {name} {status}", callback_data=f"type_add_acc_{phone}")])
        buttons.append([InlineKeyboardButton("🔙 بازگشت", callback_data="user_breakdown")])
        
        await q.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
        return

    # ==================== 🔧 اکانت انتخاب شد برای اد نوعی ====================
    if d.startswith("type_add_acc_"):
        phone = d[len("type_add_acc_"):]
        add_type = atk_state.get("add_member_type", "all")
        
        accs = list_saved_accounts()
        if phone not in accs:
            await q.answer("اکانت پیدا نشد!", show_alert=True)
            return
        
        fp = accs[phone].get("device_fp") or random.choice(DEVICE_FP)
        from attacker import safe_phone_filename as spfn
        sess_path = os.path.join(SESSIONS_DIR, f"acc_{spfn(phone)}")
        
        prog = await q.message.edit_text("🔐 در حال اتصال...")
        
        try:
            client = AdvancedScraper(sess_path, API_ID, API_HASH, phone=phone, device_fp=fp)
            _enable_wal_on_session(client.app.name)
            await robust_connect(client, max_retries=3)
            _enable_wal_on_session(client.app.name)
            me = await client.app.get_me()
            
            atk_state["_type_add_client"] = client
            atk_state["_type_add_phone"] = phone
            
            # Load target groups/channels
            targets = []
            async for dialog in client.app.get_dialogs(limit=500):
                chat_type = str(dialog.chat.type).lower()
                if "channel" in chat_type or "supergroup" in chat_type:
                    cnt = getattr(dialog.chat, "members_count", 0) or 0
                    icon = "📡" if "channel" in chat_type else "👥"
                    targets.append((dialog.chat.title, dialog.chat.id, cnt, icon))
            
            type_labels = {"phone": "📱 شماره‌دارها", "username": "🏷️ username دارها", "id": "🆔 فقط ID", "all": "🌐 همه"}
            
            text = f"✅ متصل: <b>{me.first_name}</b>\\n\\n"
            text += f"➕ <b>{type_labels.get(add_type, 'همه')}</b>\\n"
            text += f"━━━━━━━━━━━━━━━━━━\\n"
            text += f"گروه/کانال مقصد رو انتخاب کن:\\n"
            
            buttons = []
            for tname, tid, tcnt, icon in sorted(targets, key=lambda x:-x[2])[:20]:
                buttons.append([InlineKeyboardButton(f"{icon} {tname[:28]} ({tcnt:,})", callback_data=f"type_add_tgt_{tid}")])
            
            if not targets:
                text += "\\n⚠️ هیچ Supergroup/کانالی پیدا نشد!"
                buttons.append([InlineKeyboardButton("🏠 خانه", callback_data="home")])
            else:
                buttons.append([InlineKeyboardButton("🔙 بازگشت", callback_data="user_breakdown")])
            
            await prog.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
        except Exception as e:
            await prog.edit_text(f"❌ خطا: {str(e)[:200]}", reply_markup=InlineKeyboardMarkup([[_sub_back_btn(target="home")[0]]]))
        return

    # ==================== 🎯 مقصد انتخاب شد - شروع اد ====================
    if d.startswith("type_add_tgt_"):
        target_gid = int(d[len("type_add_tgt_"):])
        client = atk_state.get("_type_add_client")
        phone = atk_state.get("_type_add_phone")
        add_type = atk_state.get("add_member_type", "all")
        
        if not client:
            await q.answer("خطا!", show_alert=True)
            return
        
        # Get users based on type filter
        try:
            cur = db.get_conn().cursor(cursor_factory=db.psycopg2.extras.RealDictCursor) if hasattr(db, 'psycopg2') else db.get_conn().cursor()
            
            if add_type == "phone":
                cur.execute("SELECT user_id, username, first_name, last_name, phone FROM scraped_users WHERE phone IS NOT NULL AND phone != ''")
            elif add_type == "username":
                cur.execute("""SELECT user_id, username, first_name, last_name, phone FROM scraped_users 
                    WHERE username IS NOT NULL AND username != '' AND (phone IS NULL OR phone = '')""")
            elif add_type == "id":
                cur.execute("""SELECT user_id, username, first_name, last_name, phone FROM scraped_users 
                    WHERE (phone IS NULL OR phone = '') AND (username IS NULL OR username = '')""")
            else:
                cur.execute("SELECT user_id, username, first_name, last_name, phone FROM scraped_users")
            
            rows = cur.fetchall()
            cur.close()
            
            members = []
            for row in rows:
                if isinstance(row, dict):
                    members.append(row)
                else:
                    members.append({
                        "user_id": row[0],
                        "username": row[1] or "",
                        "first_name": row[2] or "",
                        "last_name": row[3] or "",
                        "phone": row[4] or "",
                    })
        except Exception as e:
            await q.message.edit_text(f"❌ خطا در خواندن دیتابیس: {e}", reply_markup=InlineKeyboardMarkup([[_sub_back_btn(target="home")[0]]]))
            return
        
        if not members:
            await q.answer("کاربری پیدا نشد!", show_alert=True)
            return
        
        random.shuffle(members)
        
        type_labels = {"phone": "📱 شماره‌دارها", "username": "🏷️ username دارها", "id": "🆔 فقط ID", "all": "🌐 همه"}
        
        await q.message.edit_text(f"🚀 شروع اد {type_labels.get(add_type, 'همه')} ({len(members)} نفر)...")
        
        # Use the same _execute_simple_add function
        asyncio.create_task(_execute_simple_add(q, target_gid, client, phone, members, type_labels.get(add_type, "همه")))
        return

'''

# Find the right place to insert (after show_list_source_ handler, before the next section)
# Let's insert it right before "if d == \"download_csv\":"
marker = '    if d == "download_csv":'
if marker in content and "user_breakdown" not in content:
    content = content.replace(marker, breakdown_handler + "\n" + marker)
    changes += 1
    print("✅ Fix 3: Added user_breakdown handler + add_by_type handlers")
elif "user_breakdown" in content:
    print("⚠️ user_breakdown already exists")
else:
    print("⚠️ Could not find insertion point for breakdown handler")

with open('bot.py', 'w', encoding='utf-8') as f:
    f.write(content)

print(f"\n🎯 Total changes: {changes}/3")

