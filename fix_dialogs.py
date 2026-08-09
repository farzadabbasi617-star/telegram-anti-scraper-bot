with open("/home/user/repo/bot.py", "r", encoding="utf-8") as f:
    content = f.read()

# Find and replace the dialogs loading in simp_add_acc_
old_dialogs = '''            # Load groups with retry
            groups = []
            try:
                async for dialog in client.app.get_dialogs(limit=500):
                    cht = dialog.chat
                    if cht and cht.type in ["supergroup", "group"]:
                        cnt = getattr(cht, "members_count", 0) or 0
                        groups.append((cht.title or "بدون نام", cht.id, cnt))
            except Exception as ge:
                print(f"dialogs error: {ge}", flush=True)'''

new_dialogs = '''            # Load groups with retry - fix enum type comparison
            groups = []
            try:
                for _w in range(3):
                    async for dialog in client.app.get_dialogs(limit=500):
                        cht = dialog.chat
                        if not cht: continue
                        # Fix: chat.type is an Enum in Pyrogram 2.x
                        t = str(cht.type).lower()
                        if "group" in t or "supergroup" in t:
                            cnt = getattr(cht, "members_count", 0) or 0
                            groups.append((cht.title or "بدون نام", cht.id, cnt))
                    if groups:
                        break
                    await asyncio.sleep(2)
                print(f"  Found {len(groups)} groups", flush=True)
            except Exception as ge:
                print(f"  dialogs error: {ge}", flush=True)'''

content = content.replace(old_dialogs, new_dialogs)

with open("/home/user/repo/bot.py", "w", encoding="utf-8") as f:
    f.write(content)

print("✅ Dialogs enum fix applied!")
