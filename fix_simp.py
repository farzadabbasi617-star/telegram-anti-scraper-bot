with open("/home/user/repo/bot.py", "r", encoding="utf-8") as f:
    content = f.read()

# Replace the simp_add_acc_ handler with robust version
old = '''    if d.startswith("simp_add_acc_"):
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
        return'''

new = '''    if d.startswith("simp_add_acc_"):
        phone = d[len("simp_add_acc_"):]
        accs = list_saved_accounts()
        if phone not in accs:
            await q.answer("اکانت پیدا نشد!", show_alert=True)
            return
        fp = accs[phone].get("device_fp") or random.choice(DEVICE_FP)
        from attacker import safe_phone_filename as spfn
        sess_path = os.path.join(SESSIONS_DIR, f"acc_{spfn(phone)}")
        
        # Cleanup stale locks
        import glob as _g
        for pat in [sess_path + ".session-journal", sess_path + ".session-wal", sess_path + ".session-shm"]:
            for f in _g.glob(pat):
                try: os.remove(f)
                except: pass
        
        prog = await q.message.edit_text(" در حال اتصال...\\nلطفاً صبر کنید")
        client = None
        try:
            client = AdvancedScraper(sess_path, API_ID, API_HASH, phone=phone, device_fp=fp)
            _enable_wal_on_session(client.app.name)
            await robust_connect(client, max_retries=3)
            _enable_wal_on_session(client.app.name)
            
            # Warmup dialogs with retry
            for _retry in range(3):
                try:
                    async for _ in client.app.get_dialogs(limit=200):
                        pass
                    await asyncio.sleep(1)
                    break
                except: 
                    await asyncio.sleep(2)
            
            me = await client.app.get_me()
            
            # Store client
            atk_state["_simp_client"] = client
            atk_state["_simp_phone"] = phone
            atk_state["_simp_me"] = me.first_name
            
            # Load groups with retry
            groups = []
            try:
                async for dialog in client.app.get_dialogs(limit=500):
                    cht = dialog.chat
                    if cht and cht.type in ["supergroup", "group"]:
                        cnt = getattr(cht, "members_count", 0) or 0
                        groups.append((cht.title or "بدون نام", cht.id, cnt))
            except Exception as ge:
                print(f"dialogs error: {ge}", flush=True)
            
            text = f"✅ متصل: <b>{me.first_name}</b>\\n\\n"
            
            if not groups:
                text += "⚠️ هیچ گروهی پیدا نشد!\\n\\n"
                text += "دلایل ممکن:\\n"
                text += "• اکانت عضو هیچ گروهی نیست\\n"
                text += "• مشکل در اتصال به تلگرام\\n\\n"
                text += "راه حل: دوباره امتحان کن یا اکانت دیگه‌ای انتخاب کن."
                buttons = [[InlineKeyboardButton("🔄 تلاش مجدد", callback_data=f"simp_add_acc_{phone}")]]
                buttons.append([InlineKeyboardButton("🔙 بازگشت", callback_data="pick_account_add")])
            else:
                text += f"<b>مرحله ۲: گروه منبع را انتخاب کن</b>\\n"
                text += f"━━━━━━━━━━━━━━━\\n"
                text += f"اعضای این گروه اسکرپ و ادد میشن ({len(groups)} گروه):\\n\\n"
                
                buttons = []
                for gname, gid, gcnt in sorted(groups, key=lambda x:-x[2])[:20]:
                    buttons.append([InlineKeyboardButton(f" {gname[:28]} ({gcnt:,})", callback_data=f"simp_add_src_{gid}")])
                buttons.append([InlineKeyboardButton(" بازگشت", callback_data="pick_account_add")])
            
            await prog.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
        except Exception as e:
            # Disconnect client on error to free session
            if client:
                try: await client.disconnect()
                except: pass
            await prog.edit_text(f"❌ خطا در اتصال: {str(e)[:200]}\\n\\n💡 یک دقیقه صبر کن و دوباره امتحان کن.", 
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔄 تلاش مجدد", callback_data=f"simp_add_acc_{phone}")],
                    [InlineKeyboardButton("🔙 بازگشت", callback_data="home")],
                ]))
        return'''

content = content.replace(old, new)

with open("/home/user/repo/bot.py", "w", encoding="utf-8") as f:
    f.write(content)

print("✅ Fixed!")
