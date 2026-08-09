with open("/home/user/repo/bot.py", "r", encoding="utf-8") as f:
    content = f.read()

old = '''    if d == "stop_op":
        # درخواست توقف هر عملیات در حال اجرا
        for obj in ["atk", "new_acc_client", "new_client", "add_client"]:
            try:
                o = atk_state.get(obj)
                if o and hasattr(o, "request_stop"):
                    o.request_stop()
            except: pass
        atk_state.clear()
        await q.answer("⏹️ درخواست توقف داده شد، چند لحظه...", show_alert=True)
        await q.message.edit_text("⏹️ عملیات توسط کاربر متوقف شد.", reply_markup=main_menu())
        return'''

new = '''    if d == "stop_op":
        # درخواست توقف هر عملیات در حال اجرا
        for obj in ["atk", "new_acc_client", "new_client", "add_client"]:
            try:
                o = atk_state.get(obj)
                if o and hasattr(o, "request_stop"):
                    o.request_stop()
            except: pass
        # Disconnect simple add client
        simp_client = atk_state.get("_simp_client")
        if simp_client:
            try:
                await simp_client.disconnect()
            except: pass
        atk_state.clear()
        # Cleanup session locks
        import glob as _g
        for pat in [os.path.join(SESSIONS_DIR, "*.session-journal"), os.path.join(SESSIONS_DIR, "*.session-wal"), os.path.join(SESSIONS_DIR, "*.session-shm")]:
            for f in _g.glob(pat):
                try: os.remove(f)
                except: pass
        await q.answer("️ درخواست توقف داده شد، چند لحظه...", show_alert=True)
        await q.message.edit_text("⏹️ عملیات توسط کاربر متوقف شد.", reply_markup=main_menu())
        return'''

content = content.replace(old, new)

with open("/home/user/repo/bot.py", "w", encoding="utf-8") as f:
    f.write(content)

print("✅ stop_op fixed!")
