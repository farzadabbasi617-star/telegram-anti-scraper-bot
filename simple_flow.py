import re

with open("/home/user/repo/bot.py", "r", encoding="utf-8") as f:
    content = f.read()

# Find and replace the "pick_account_add" callback handler
old_add_start = '''    if d == "pick_account_add":
        limits = load_adder_limits()
        warn = ""
        full_count = sum(1 for p,i in limits.items() if i.get("added",0)>=MAX_ADD_PER_ACCOUNT)
        if full_count > 0:
            warn = f"\\n⚠️ {full_count} اکانت به سقف {MAX_ADD_PER_ACCOUNT} نفر رسیده"
        await show_account_picker("add", "home", f"➕ شروع اضافه کردن اعضا{warn}")
        return'''

new_add_start = '''    if d == "pick_account_add":
        # NEW FLOW: Account → Source Group → Scrape → Target → Add
        accs = list_saved_accounts()
        if not accs:
            await q.answer("اول یه اکانت اضافه کن!", show_alert=True)
            return
        
        atk_state["add_step"] = "pick_source"
        
        # Show accounts to pick
        buttons = []
        for phone, info in accs.items():
            name = info.get("name", phone)[:20]
            buttons.append([InlineKeyboardButton(f" {name} ({phone})", callback_data=f"simp_add_acc_{phone}")])
        buttons.append([InlineKeyboardButton("🔙 بازگشت", callback_data="home")])
        
        await q.message.edit_text(
            " <b>ادد ممبر - مرحله ۱</b>\\n"
            "━━━━━━━━━━━━━━━\\n"
            "اکانتی که میخوای باهاش ادد بزنی رو انتخاب کن:",
            reply_markup=InlineKeyboardMarkup(buttons))
        return

    # ── SIMPLE ADD FLOW ───
    if d.startswith("simp_add_acc_"):
        phone = d[len("simp_add_acc_"):]
        accs = list_saved_accounts()
        fp = accs[phone].get("device_fp") or random.choice(DEVICE_FP)
        from attacker import safe_phone_filename as spfn
        sess_path = os.path.join(SESSIONS_DIR, f"acc_{spfn(phone)}")
        
        prog = await q.message.edit_text(" در حال اتصال...")
        try:
            client = AdvancedScraper(sess_path, API_ID, API_HASH, phone=phone, device_fp=fp)
            _enable_wal_on_session(client.app.name)
            await client.connect()
            _enable_wal_on_session(client.app.name)
            me = await client.app.get_me()
            
            # Store client
            atk_state["_simp_client"] = client
            atk_state["_simp_phone"] = phone
            atk_state["_simp_me"] = me.first_name
            
            # Load groups
            groups = []
            async for dialog in client.app.get_dialogs(limit=500):
                if dialog.chat.type in ["supergroup", "group"]:
                    cnt = getattr(dialog.chat, "members_count", 0) or 0
                    groups.append((dialog.chat.title, dialog.chat.id, cnt))
            
            text = f"✅ متصل: <b>{me.first_name}</b>\\n\\n"
            text += "<b>مرحله ۲: گروه منبع را انتخاب کن</b>\\n"
            text += "━━━━━━━━━━━━━━━\\n"
            text += "اعضای این گروه اسکرپ و ادد میشن:\\n\\n"
            
            buttons = []
            for gname, gid, gcnt in sorted(groups, key=lambda x:-x[2])[:20]:
                buttons.append([InlineKeyboardButton(f"👥 {gname[:28]} ({gcnt:,})", callback_data=f"simp_add_src_{gid}")])
            buttons.append([InlineKeyboardButton(" بازگشت", callback_data="pick_account_add")])
            
            await prog.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
        except Exception as e:
            await prog.edit_text(f"❌ خطا: {e}", reply_markup=InlineKeyboardMarkup([[_sub_back_btn(target="home")[0]]]))
        return

    if d.startswith("simp_add_src_"):
        source_gid = int(d[len("simp_add_src_"):])
        client = atk_state.get("_simp_client")
        phone = atk_state.get("_simp_phone")
        
        if not client:
            await q.answer("خطا در وضعیت!", show_alert=True)
            return
        
        # Get source group info
        try:
            src = await client.app.get_chat(source_gid)
            source_name = src.title
        except:
            source_name = "گروه منبع"
        
        atk_state["simp_source_gid"] = source_gid
        atk_state["simp_source_name"] = source_name
        
        await q.message.edit_text(f"🔄 در حال اسکرپ از <b>{source_name}</b>...\\n⏳ صبر کنید")
        
        # Scrape members NOW
        members = []
        try:
            async for member in client.app.get_chat_members(source_gid, limit=10000):
                u = member.user
                if u and not getattr(u, 'is_bot', False) and not getattr(u, 'is_deleted', False):
                    uid = u.id
                    if 10000 < uid < 10**11:
                        members.append({"user_id": uid, "first_name": u.first_name or "", "last_name": u.last_name or "", "username": u.username or ""})
        except Exception as se:
            await q.message.edit_text(f"❌ خطا در اسکرپ: {se}", reply_markup=InlineKeyboardMarkup([[_sub_back_btn(target="home")[0]]]))
            return
        
        if not members:
            await q.message.edit_text(" هیچ عضوی پیدا نشد!", reply_markup=InlineKeyboardMarkup([[_sub_back_btn(target="home")[0]]]))
            return
        
        # Save to temp
        atk_state["_simp_members"] = members
        atk_state["simp_source_count"] = len(members)
        
        # Load channels for target selection
        channels = []
        try:
            async for dialog in client.app.get_dialogs(limit=500):
                if dialog.chat.type == "channel":
                    cnt = getattr(dialog.chat, "members_count", 0) or 0
                    channels.append((dialog.chat.title, dialog.chat.id, cnt))
        except: pass
        
        text = f"✅ اسکرپ کامل شد!\\n"
        text += f"━━━━━━━━━━━━━━━\\n"
        text += f"📂 منبع: {source_name}\\n"
        text += f"👥 اعضا: {len(members)} نفر\\n\\n"
        text += "<b>مرحله ۳: کانال مقصد را انتخاب کن</b>\\n"
        
        buttons = []
        for cname, cid, ccnt in sorted(channels, key=lambda x:-x[2])[:15]:
            buttons.append([InlineKeyboardButton(f"📡 {cname[:28]} ({ccnt:,})", callback_data=f"simp_add_tgt_{cid}")])
        
        if not channels:
            text += "\\n⚠️ کانالی پیدا نشد!"
            buttons.append([InlineKeyboardButton(" خانه", callback_data="home")])
        else:
            buttons.append([InlineKeyboardButton("🔙 گروه دیگه", callback_data=f"simp_add_acc_{phone}")])
        
        await q.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
        return

    if d.startswith("simp_add_tgt_"):
        target_gid = int(d[len("simp_add_tgt_"):])
        client = atk_state.get("_simp_client")
        phone = atk_state.get("_simp_phone")
        members = atk_state.get("_simp_members", [])
        source_name = atk_state.get("simp_source_name", "گروه")
        source_gid = atk_state.get("simp_source_gid")
        
        if not client or not members:
            await q.answer("خطا!", show_alert=True)
            return
        
        # Get target info
        try:
            tgt = await client.app.get_chat(target_gid)
            target_name = tgt.title
        except:
            target_name = "کانال مقصد"
        
        # Check admin
        try:
            me_member = await client.app.get_chat_member(target_gid, "me")
            is_admin = "owner" in str(me_member.status).lower() or "admin" in str(me_member.status).lower()
        except:
            is_admin = False
        
        limits = load_adder_limits()
        already = limits.get(phone, {}).get("added", 0)
        remaining = MAX_ADD_PER_ACCOUNT - already
        
        # Filter already added
        new_members = []
        skipped = 0
        for m in members:
            uid = m.get("user_id", 0)
            if not is_user_already_added(target_gid, uid):
                new_members.append(m)
            else:
                skipped += 1
        
        to_add = min(len(new_members), remaining)
        
        text = f"<b>مرحله ۴: تایید و شروع!</b>\\n"
        text += f"━━━━━━━━━━━━━━━\\n"
        text += f"📂 منبع: {source_name}\\n"
        text += f" مقصد: {target_name}\\n"
        text += f"👥 اسکرپ شده: {len(members)}\\n"
        text += f"⏭ قبلاً اضافه شده: {skipped}\\n"
        text += f"🆕 آماده ادد: {to_add}\\n"
        text += f"📊 ظرفیت اکانت: {already}/{MAX_ADD_PER_ACCOUNT}\\n"
        if not is_admin:
            text += f"\\n⚠️ اکانت ادمین نیست! ممکنه کار نکنه.\\n"
        text += f"━━━━━━━━━━━━━━━\\n\\n"
        text += f"آماده‌ای؟"
        
        buttons = []
        if to_add > 0:
            buttons.append([InlineKeyboardButton(f"▶️ شروع ادد ({to_add} نفر)!", callback_data=f"simp_add_exec_{target_gid}")])
        buttons.append([InlineKeyboardButton("🔙 کانال دیگه", callback_data=f"simp_add_src_{source_gid}")])
        buttons.append([InlineKeyboardButton(" خانه", callback_data="home")])
        
        await q.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
        return

    if d.startswith("simp_add_exec_"):
        target_gid = int(d[len("simp_add_exec_"):])
        client = atk_state.get("_simp_client")
        phone = atk_state.get("_simp_phone")
        members = atk_state.get("_simp_members", [])
        source_name = atk_state.get("simp_source_name", "گروه")
        source_gid = atk_state.get("simp_source_gid")
        
        if not client or not members:
            await q.answer("خطا!", show_alert=True)
            return
        
        # Start adding
        asyncio.create_task(_execute_simple_add(q, target_gid, client, phone, members, source_name))
        return'''

content = content.replace(old_add_start, new_add_start)

with open("/home/user/repo/bot.py", "w", encoding="utf-8") as f:
    f.write(content)

print("✅ Simple flow callbacks added!")
