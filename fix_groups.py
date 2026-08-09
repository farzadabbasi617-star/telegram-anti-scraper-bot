# Fix to load both channels AND groups (supergroups) for target selection

with open('bot.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find and replace the channels loading section
old_code = """        # Load channels for target selection
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
            text += "\\n⚠️ کانالی پیدا نشد!"
            buttons.append([InlineKeyboardButton(" خانه", callback_data="home")])
        else:
            buttons.append([InlineKeyboardButton("🔙 گروه دیگه", callback_data=f"simp_add_acc_{phone}")])"""

new_code = """        # Load channels AND groups (supergroups) for target selection
        targets = []
        try:
            async for dialog in client.app.get_dialogs(limit=500):
                chat_type = str(dialog.chat.type).lower()
                # Include both channels and supergroups (not basic groups)
                if "channel" in chat_type or "supergroup" in chat_type:
                    cnt = getattr(dialog.chat, "members_count", 0) or 0
                    icon = "📡" if "channel" in chat_type else "👥"
                    targets.append((dialog.chat.title, dialog.chat.id, cnt, icon))
        except: pass
        
        text = f"✅ اسکرپ کامل شد!\\n"
        text += f"━━━━━━━━━━━━━━━\\n"
        text += f"📂 منبع: {source_name}\\n"
        text += f"👥 اعضا: {len(members)} نفر\\n\\n"
        text += "<b>مرحله ۳: کانال یا گروه مقصد را انتخاب کن</b>\\n"
        
        buttons = []
        for tname, tid, tcnt, icon in sorted(targets, key=lambda x:-x[2])[:20]:
            buttons.append([InlineKeyboardButton(f"{icon} {tname[:28]} ({tcnt:,})", callback_data=f"simp_add_tgt_{tid}")])
        
        if not targets:
            text += "\\n⚠️ کانال یا گروهی پیدا نشد!"
            buttons.append([InlineKeyboardButton(" خانه", callback_data="home")])
        else:
            buttons.append([InlineKeyboardButton("🔙 گروه دیگه", callback_data=f"simp_add_acc_{phone}")])"""

content = content.replace(old_code, new_code)

with open('bot.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("✅ Fix applied: now loads both channels AND supergroups for target selection")
