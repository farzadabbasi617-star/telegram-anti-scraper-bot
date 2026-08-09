with open("/home/user/repo/bot.py", "r", encoding="utf-8") as f:
    content = f.read()

# Find the "dir_add_go_" handler and update it to use live_source_gid
old_handler = '''    if d.startswith("dir_add_go_"):
        gid = int(d.split("_")[3])
        asyncio.create_task(_execute_direct_add(q, gid))
        return'''

new_handler = '''    if d.startswith("dir_add_go_"):
        gid = int(d.split("_")[3])
        # Make sure we have a source group
        if not atk_state.get("live_source_gid"):
            # Redirect to source picker
            q.data = f"live_add_pick_src_{gid}"
            await _cb_impl(c, q)
            return
        asyncio.create_task(_execute_direct_add(q, gid))
        return

    # ═══════════ LIVE ADD: Pick source group ═══════════
    if d.startswith("live_add_pick_src_"):
        gid = int(d.split("_")[4])
        accs = list_saved_accounts()
        phone = atk_state.get("phone", list(accs.keys())[0] if accs else None)
        if not phone or phone not in accs:
            await q.answer("اکانت مشخص نیست!", show_alert=True)
            return
        fp = accs[phone].get("device_fp") or random.choice(DEVICE_FP)
        from attacker import safe_phone_filename as spfn
        sess_path = os.path.join(SESSIONS_DIR, f"acc_{spfn(phone)}")
        
        prog = await q.message.edit_text(" در حال بارگذاری گروه‌ها...")
        try:
            client = AdvancedScraper(sess_path, API_ID, API_HASH, phone=phone, device_fp=fp)
            _enable_wal_on_session(client.app.name)
            await client.connect()
            _enable_wal_on_session(client.app.name)
            
            groups = []
            async for dialog in client.app.get_dialogs(limit=500):
                if dialog.chat.type in ["supergroup", "group"]:
                    cnt = getattr(dialog.chat, "members_count", 0) or 0
                    groups.append((dialog.chat.title, dialog.chat.id, cnt))
            
            atk_state["_live_client"] = client
            atk_state["_live_phone"] = phone
            
            text = f"📂 <b>گروه منبع را انتخاب کن</b>\\n"
            text += f"کاربران این گروه الان اسکرپ و ادد میشن!\\n\\n"
            buttons = []
            for gname, gid2, gcnt in sorted(groups, key=lambda x:-x[2])[:25]:
                buttons.append([InlineKeyboardButton(f"👥 {gname[:28]} ({gcnt:,})", callback_data=f"live_add_src_{gid}_{gid2}")])
            buttons.append([InlineKeyboardButton(" بازگشت", callback_data=f"add_target_{gid}")])
            
            await prog.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
        except Exception as e:
            await prog.edit_text(f"❌ خطا: {e}", reply_markup=InlineKeyboardMarkup([[_sub_back_btn(target="home")[0]]]))
        return

    # ═══════════ LIVE ADD: Source selected, start adding ═══════════
    if d.startswith("live_add_src_"):
        parts = d.split("_")
        target_gid = int(parts[3])
        source_gid = int(parts[4])
        
        client = atk_state.get("_live_client")
        phone = atk_state.get("_live_phone")
        
        if not client or not phone:
            await q.answer("خطا در وضعیت!", show_alert=True)
            return
        
        # Store source and use existing add_client
        atk_state["live_source_gid"] = source_gid
        atk_state["add_client"] = client
        atk_state["phone"] = phone
        
        # Get source name
        try:
            src = await client.app.get_chat(source_gid)
            source_name = src.title
        except:
            source_name = "گروه منبع"
        
        try:
            tgt = await client.app.get_chat(target_gid)
            target_name = tgt.title
        except:
            target_name = "کانال مقصد"
        
        await q.message.edit_text(
            f"🔄 <b>آماده اسکرپ + ادد!</b>\\n"
            f"━━━━━━━━━━━━━━━\\n"
            f" منبع: {source_name}\\n"
            f"🎯 مقصد: {target_name}\\n"
            f" اکانت: {phone}\\n"
            f"━━━━━━━━━━━━━━━\\n"
            f"الان اعضای گروه منبع اسکرپ میشن\\n"
            f"و به کانال مقصد اضافه میشن!\\n\\n"
            f"آماده‌ای؟",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("▶️ شروع!", callback_data=f"dir_add_go_{target_gid}")],
                [InlineKeyboardButton("🔙 گروه دیگه", callback_data=f"live_add_pick_src_{target_gid}")],
            ]))
        return

'''

content = content.replace(old_handler, new_handler)

# Also update _start_direct_add to redirect to live_add_pick_src
old_start = '''    prog = await q.message.edit_text(
        f" <b>ادد مستقیم از دیتابیس</b>\\n"
        f"━━━━━━━━━━━━━━━━━━\\n"
        f"📂 منبع: {src_label}\\n"
        f"🎯 مقصد: {target_name}\\n"
        f"👤 اکانت: <code>{phone}</code>\\n"
        f"📊 ظرفیت: {already_added}/{MAX_ADD_PER_ACCOUNT}\\n"
        f"━━━━━━━━━━━━━━━━━━\\n"
        f" آماده ادد: <b>{total}</b> نفر\\n"
        f"⏱️ زمان تخمینی: ~{total * 12 // 60} دقیقه\\n\\n"
        f"آماده‌ای؟",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(f"▶️ شروع ادد ({total} نفر)", callback_data=f"dir_add_go_{target_gid}")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data=f"add_target_{target_gid}")],
        ]),
        disable_web_page_preview=True)'''

new_start = '''    # Redirect to LIVE source picker
    atk_state["live_target_gid"] = target_gid
    atk_state["live_target_name"] = target_name
    await q.message.edit_text(
        f" <b>اسکرپ زنده + ادد فوری</b>\\n"
        f"━━━━━━━━━━━━━━━━━━\\n"
        f" مقصد: {target_name}\\n"
        f"👤 اکانت: <code>{phone}</code>\\n"
        f" ظرفیت: {already_added}/{MAX_ADD_PER_ACCOUNT}\\n"
        f"━━━━━━━━━━━━━━━━━━\\n"
        f"📂 حالا گروه منبع رو انتخاب کن:\\n"
        f"اعضای فعلی گروه الان اسکرپ و ادد میشن!",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📂 انتخاب گروه منبع", callback_data=f"live_add_pick_src_{target_gid}")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data=f"add_target_{target_gid}")],
        ]),
        disable_web_page_preview=True)'''

content = content.replace(old_start, new_start)

with open("/home/user/repo/bot.py", "w", encoding="utf-8") as f:
    f.write(content)

print("✅ Callbacks added!")
