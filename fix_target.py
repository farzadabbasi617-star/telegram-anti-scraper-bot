with open("/home/user/repo/bot.py", "r", encoding="utf-8") as f:
    content = f.read()

# 1. Add constant near the top
old_constants = "MAX_ADD_PER_ACCOUNT = 100  # محدودیت اضافه کردن عضو در هر اکانت (تا ۵۰ تا ۸-۱۵s, بعد ۱۲-۲۰s)"
new_constants = """MAX_ADD_PER_ACCOUNT = 100  # محدودیت اضافه کردن عضو در هر اکانت (تا ۵۰ تا ۸-۱۵s, بعد ۱۲-۲۰s)

# گروه مقصد ثابت - ممبرها همیشه به این گروه اضافه میشن
FIXED_TARGET_LINK = "https://t.me/+gLScToU4DZdjZmM0"
FIXED_TARGET_GID = None  # will be resolved on first use"""

content = content.replace(old_constants, new_constants)

# 2. Find and simplify the simp_add_src_ handler - remove target selection
# After scraping, instead of asking for target, use FIXED_TARGET_LINK directly

old_src_handler_start = '''    if d.startswith("simp_add_src_"):
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
        
        await q.message.edit_text(f"🔄 در حال اسکرپ از <b>{source_name}</b>...\\n صبر کنید")
        
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
                if "channel" in str(dialog.chat.type).lower():
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
            text += "\\n️ کانالی پیدا نشد!"
            buttons.append([InlineKeyboardButton(" خانه", callback_data="home")])
        else:
            buttons.append([InlineKeyboardButton("🔙 گروه دیگه", callback_data=f"simp_add_acc_{phone}")])
        
        await q.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
        return'''

new_src_handler = '''    if d.startswith("simp_add_src_"):
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
        
        # Resolve fixed target group
        await q.message.edit_text(f"✅ اسکرپ: {len(members)} نفر\\n🔄 در حال آماده‌سازی گروه مقصد...")
        
        global FIXED_TARGET_GID
        target_gid = FIXED_TARGET_GID
        target_name = "گروه مقصد"
        
        if not target_gid:
            # Resolve the invite link
            try:
                # First try to join/resolve the link
                chat = await client.app.get_chat(FIXED_TARGET_LINK)
                target_gid = chat.id
                target_name = chat.title or "گروه مقصد"
                FIXED_TARGET_GID = target_gid
                print(f"  Resolved target: {target_name} ({target_gid})", flush=True)
            except Exception as te:
                # Try joining first
                try:
                    await client.app.join_chat(FIXED_TARGET_LINK)
                    await asyncio.sleep(2)
                    chat = await client.app.get_chat(FIXED_TARGET_LINK)
                    target_gid = chat.id
                    target_name = chat.title or "گروه مقصد"
                    FIXED_TARGET_GID = target_gid
                    print(f"  Joined & resolved target: {target_name} ({target_gid})", flush=True)
                except Exception as te2:
                    await q.message.edit_text(f"❌ خطا در دسترسی به گروه مقصد:\\n{str(te2)[:200]}\\n\\n💡 مطمئن شو اکانت ادمین این گروه هست.", 
                        reply_markup=InlineKeyboardMarkup([[_sub_back_btn(target="home")[0]]]))
                    return
        
        # Check admin on target
        is_admin = False
        try:
            me_member = await client.app.get_chat_member(target_gid, "me")
            is_admin = "owner" in str(me_member.status).lower() or "admin" in str(me_member.status).lower()
        except: pass
        
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
        
        text = f"<b>آماده ادد!</b>\\n"
        text += f"━━━━━━━━━━━━━━━\\n"
        text += f"📂 منبع: {source_name}\\n"
        text += f" مقصد: {target_name}\\n"
        text += f"👥 اسکرپ شده: {len(members)}\\n"
        text += f"⏭ قبلاً اضافه شده: {skipped}\\n"
        text += f"🆕 آماده ادد: {to_add}\\n"
        text += f"📊 ظرفیت: {already}/{MAX_ADD_PER_ACCOUNT}\\n"
        if not is_admin:
            text += f"\\n⚠️ اکانت ادمین نیست! ممکنه کار نکنه.\\n"
        text += f"━━━━━━━━━━━━━━━\\n\\n"
        text += f"آماده‌ای؟"
        
        buttons = []
        if to_add > 0:
            buttons.append([InlineKeyboardButton(f"▶️ شروع ادد ({to_add} نفر)!", callback_data=f"simp_add_exec_{target_gid}")])
        buttons.append([InlineKeyboardButton("🔙 گروه منبع دیگه", callback_data=f"simp_add_acc_{phone}")])
        buttons.append([InlineKeyboardButton(" خانه", callback_data="home")])
        
        await q.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
        return'''

content = content.replace(old_src_handler_start, new_src_handler)

# 3. Remove the simp_add_tgt_ handler entirely (no longer needed)
# Find and remove it
old_tgt_start = '''    if d.startswith("simp_add_tgt_"):
        target_gid = int(d[len("simp_add_tgt_"):])'''

# Find end of this handler (next if d.startswith)
tgt_start_idx = content.find(old_tgt_start)
if tgt_start_idx != -1:
    # Find next handler
    next_handlers = ['    if d.startswith("simp_add_exec_"):', '    if d == "home":']
    tgt_end_idx = len(content)
    for nh in next_handlers:
        idx = content.find(nh, tgt_start_idx + 100)
        if idx != -1 and idx < tgt_end_idx:
            tgt_end_idx = idx
    
    if tgt_end_idx < len(content):
        content = content[:tgt_start_idx] + content[tgt_end_idx:]
        print(f"Removed simp_add_tgt_ handler")
    else:
        print("Could not find end of simp_add_tgt_ handler")

with open("/home/user/repo/bot.py", "w", encoding="utf-8") as f:
    f.write(content)

print("✅ Target group fixed!")
