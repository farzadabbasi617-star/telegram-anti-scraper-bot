with open("/home/user/repo/bot.py", "r", encoding="utf-8") as f:
    content = f.read()

old = '''    if d.startswith("simp_add_acc_"):
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
            _enable_wal_on_session(client.app.name)'''

new = '''    if d.startswith("simp_add_acc_"):
        phone = d[len("simp_add_acc_"):]
        accs = list_saved_accounts()
        if phone not in accs:
            await q.answer("اکانت پیدا نشد!", show_alert=True)
            return
        fp = accs[phone].get("device_fp") or random.choice(DEVICE_FP)
        from attacker import safe_phone_filename as spfn
        sess_path = os.path.join(SESSIONS_DIR, f"acc_{spfn(phone)}")
        
        # FULL cleanup: delete session + all related files, then re-download from DB
        import glob as _g
        import shutil
        for pat in [sess_path + ".session", sess_path + ".session-journal", 
                    sess_path + ".session-wal", sess_path + ".session-shm",
                    sess_path + ".session-*"]:
            for f in _g.glob(pat):
                try: os.remove(f)
                except: pass
        
        # Re-download session from Neon DB
        blob = db.load_session_blob(phone)
        if blob:
            with open(sess_path + ".session", "wb") as sf:
                sf.write(blob)
            print(f"  Re-downloaded session for {phone} from DB ({len(blob)} bytes)", flush=True)
        else:
            print(f"  WARNING: No session blob in DB for {phone}", flush=True)
        
        prog = await q.message.edit_text(" در حال اتصال...\\nلطفاً صبر کنید")
        client = None
        try:
            client = AdvancedScraper(sess_path, API_ID, API_HASH, phone=phone, device_fp=fp)
            # Enable WAL before connect
            _enable_wal_on_session(client.app.name)
            await robust_connect(client, max_retries=3)
            _enable_wal_on_session(client.app.name)'''

content = content.replace(old, new)

with open("/home/user/repo/bot.py", "w", encoding="utf-8") as f:
    f.write(content)

print("✅ Disk I/O fix applied!")
