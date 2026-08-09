import re

with open("/home/user/repo/bot.py", "r", encoding="utf-8") as f:
    content = f.read()

# 1. Replace _execute_direct_add with new LIVE version
old_func_start = "async def _execute_direct_add(q, target_gid):\n    \"\"\"Add members to channel via AddContact + InviteToChannel with warmup.\"\"\"\n"

# Find the end of this function (next function definition)
start_idx = content.find(old_func_start)
if start_idx == -1:
    print("ERROR: Could not find _execute_direct_add")
    exit(1)

# Find next function after _execute_direct_add
next_funcs = [
    "\n\nasync def _start_parallel_direct_add",
    "\nasync def _start_parallel_direct_add",
    "\n\nasync def _do_quick_add",
]
end_idx = -1
for nf in next_funcs:
    idx = content.find(nf, start_idx + 100)
    if idx != -1 and (end_idx == -1 or idx < end_idx):
        end_idx = idx

if end_idx == -1:
    print("ERROR: Could not find end of _execute_direct_add")
    exit(1)

print(f"Found function from {start_idx} to {end_idx}")

new_func = '''async def _execute_direct_add(q, target_gid):
    """LIVE scrape from source group + AddContact+InviteToChannel to target."""
    add_client = atk_state.get("add_client")
    phone = atk_state.get("phone", "")
    already_added = atk_state.get("already_added", 0)
    remaining = MAX_ADD_PER_ACCOUNT - already_added
    prog_msg = q.message
    target_name = "گروه"

    if not add_client:
        try:
            await prog_msg.edit_text(" اکانت متصل نیست!\\nاول از منوی ادد ممبر اکانت رو وصل کن.",
                reply_markup=InlineKeyboardMarkup([[_sub_back_btn(target="home")[0]]]))
        except: pass
        return

    try:
        tgt = await add_client.app.get_chat(target_gid)
        target_name = tgt.title
    except Exception as e:
        await prog_msg.edit_text(f"❌ کانال پیدا نشد: {e}",
            reply_markup=InlineKeyboardMarkup([[_sub_back_btn(target="home")[0]]]))
        return

    # Get source group
    source_gid = atk_state.get("live_source_gid")
    if not source_gid:
        await prog_msg.edit_text("❌ گروه منبع مشخص نیست!",
            reply_markup=InlineKeyboardMarkup([[_sub_back_btn(target="home")[0]]]))
        return

    # Get source group name
    try:
        src_chat = await add_client.app.get_chat(source_gid)
        source_name = src_chat.title
    except:
        source_name = "گروه منبع"

    # Check admin on target
    try:
        await add_client.app.get_dialogs(limit=200)
    except: pass
    
    added = 0; failed = 0; skipped = 0
    errors_detail = {"peer": 0, "privacy": 0, "already": 0, "flood": 0, "other": 0}
    first_error = ""
    start_t = time.time()
    atk_state["add_in_progress"] = True

    from pyrogram.raw.functions.contacts import AddContact
    from pyrogram.raw.functions.channels import InviteToChannel

    async def upd():
        try:
            elapsed = int(time.time() - start_t)
            m, s = elapsed // 60, elapsed % 60
            pct = int((added + failed) * 100 / max(1, total)) if total > 0 else 0
            bar = "█" * (pct // 5) + "░" * (20 - pct // 5)
            spd = int(added / (elapsed / 60)) if elapsed > 30 else 0
            txt = f"🔄 اسکرپ از: {source_name}\\n🎯 ادد به: {target_name}\\n{bar} {pct}%\\n✅ {added} ❌ {failed} ⏭ {skipped}\\n⏱ {m:02d}:{s:02d} ⚡ {spd}/min"
            await prog_msg.edit_text(txt,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⏹️ توقف", callback_data="stop_op")]]),
                disable_web_page_preview=True)
        except: pass

    await upd()

    # ═══════════════ PHASE 1: LIVE SCRAPE FROM SOURCE GROUP ═══════════════
    print(f"🔄 Phase 1: Live scraping from {source_name} ({source_gid})...", flush=True)
    await prog_msg.edit_text(f"🔄 در حال اسکرپ از <b>{source_name}</b>...\\n⏳ صبر کنید",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⏹️ توقف", callback_data="stop_op")]]))

    # Resolve target once
    try:
        target_peer = await add_client.app.resolve_peer(target_gid)
    except Exception as e:
        await prog_msg.edit_text(f"❌ کانال مقصد resolve نشد: {e}",
            reply_markup=InlineKeyboardMarkup([[_sub_back_btn(target="home")[0]]]))
        return

    # Scrape members from source group
    valid_peers = {}
    total = 0
    scanned = 0
    try:
        async for member in add_client.app.get_chat_members(source_gid, limit=10000):
            if atk_state.get("_stop_requested"):
                break
            scanned += 1
            u = member.user
            if not u or getattr(u, 'is_bot', False) or getattr(u, 'is_deleted', False):
                continue
            uid = u.id
            if uid <= 10000 or uid >= 10**11:
                continue
            if is_user_already_added(target_gid, uid):
                skipped += 1
                continue
            # Skip if over remaining
            if (added + failed) >= remaining:
                break
            try:
                peer = await add_client.app.resolve_peer(uid)
                valid_peers[uid] = peer
                total += 1
                if scanned % 100 == 0:
                    print(f"  📊 Scanned {scanned}: {total} resolved, {skipped} already", flush=True)
                    await upd()
            except:
                pass
            await asyncio.sleep(0.01)
    except Exception as se:
        print(f"  ⚠️ Scrape error: {se}", flush=True)
        first_error = f"Scrape: {str(se)[:200]}"

    print(f"  ✅ Phase 1 done: {scanned} scanned, {total} resolved, {skipped} skipped", flush=True)

    if total == 0:
        await prog_msg.edit_text(
            f" هیچ کاربر جدیدی پیدا نشد!\\n\\n"
            f"📊 اسکن شد: {scanned}\\n"
            f"⏭ رد شده (قبلاً اضافه شده): {skipped}\\n"
            f"\\n💡 احتمالاً همه اعضای این گروه قبلاً اضافه شدن.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 اسکرپ از گروه دیگه", callback_data=f"live_add_pick_src_{target_gid}")],
                [InlineKeyboardButton(" خانه", callback_data="home")],
            ]))
        return

    # ═══════════════ PHASE 2: ADD TO TARGET CHANNEL ═══════════════
    print(f"🔄 Phase 2: Adding {total} users to {target_name}...", flush=True)
    
    for uid, user_peer in list(valid_peers.items())[:remaining]:
        if atk_state.get("_stop_requested"):
            break
        try:
            # AddContact
            try:
                await add_client.app.invoke(
                    AddContact(id=user_peer, first_name=str(uid)[:30], last_name="", phone="", add_phone_privacy_exception=False)
                )
                await asyncio.sleep(0.3)
            except: pass

            # InviteToChannel
            await add_client.app.invoke(
                InviteToChannel(channel=target_peer, users=[user_peer])
            )

            added += 1
            mark_user_as_added(target_gid, target_name, uid)
            limits = load_adder_limits()
            limits[phone] = {"added": already_added + added, "last_used": int(time.time())}
            save_adder_limits(limits)

            total_acc = already_added + added
            if total_acc > 80:
                await asyncio.sleep(random.randint(15, 25))
            elif total_acc > 50:
                await asyncio.sleep(random.randint(10, 18))
            else:
                await asyncio.sleep(random.randint(7, 13))

        except FloodWait as fw:
            failed += 1; errors_detail["flood"] += 1
            print(f"⏱ FloodWait {fw.value}s", flush=True)
            await asyncio.sleep(fw.value + 5)
        except Exception as e:
            failed += 1; es = str(e); es_l = es.lower()
            if not first_error: first_error = es[:200]
            if "peer_id_invalid" in es_l: errors_detail["peer"] += 1
            elif "privacy" in es_l or "not_mutual" in es_l: errors_detail["privacy"] += 1
            elif "already" in es_l or "participant" in es_l:
                errors_detail["already"] += 1
                mark_user_as_added(target_gid, target_name, uid)
            elif "flood" in es_l: errors_detail["flood"] += 1
            elif "admin" in es_l or "right" in es_l:
                errors_detail["other"] += 1
                if not first_error: first_error = f"ADMIN_REQUIRED: {es[:100]}"
                print(f"❌ ADMIN ERROR: {es[:200]}", flush=True)
            else:
                errors_detail["other"] += 1
            await asyncio.sleep(random.randint(2, 5))

        if (added + failed) % 3 == 0:
            await upd()

    # ═══════════════ FINAL REPORT ═══════════════
    elapsed = int(time.time() - start_t)
    m, s = elapsed // 60, elapsed % 60
    text = f"✅ <b>تمام شد — {target_name}</b>\\n{'━'*20}\\n"
    text += f"📂 منبع: {source_name}\\n"
    text += f"📊 اسکن شد: {scanned}\\n"
    text += f"⏭ رد شده: {skipped}\\n"
    text += f"✅ اضافه شده: {added}\\n"
    text += f"❌ ناموفق: {failed}\\n"
    text += f"⏱ زمان: {m:02d}:{s:02d}\\n"
    text += f"📊 ظرفیت: {already_added + added}/{MAX_ADD_PER_ACCOUNT}"
    if failed > 0:
        text += f"\\n{'━'*20}\\n📋 جزئیات خطا:\\n"
        if errors_detail["peer"]: text += f"🔍 Peer Invalid: {errors_detail['peer']}\\n"
        if errors_detail["privacy"]: text += f"🔒 Privacy: {errors_detail['privacy']}\\n"
        if errors_detail["already"]: text += f"👥 قبلاً عضو: {errors_detail['already']}\\n"
        if errors_detail["flood"]: text += f" Flood: {errors_detail['flood']}\\n"
        if errors_detail["other"]: text += f"❓ سایر: {errors_detail['other']}\\n"
        if first_error: text += f"\\n💬 اولین خطا: {first_error[:200]}"

    atk_state["add_in_progress"] = False
    atk_state.pop("live_source_gid", None)

    try:
        await prog_msg.edit_text(text,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 اسکرپ از گروه دیگه", callback_data=f"live_add_pick_src_{target_gid}")],
                [InlineKeyboardButton(" خانه", callback_data="home")],
            ]), disable_web_page_preview=True)
    except: pass


'''

content = content[:start_idx] + new_func + content[end_idx:]

with open("/home/user/repo/bot.py", "w", encoding="utf-8") as f:
    f.write(content)

print("✅ _execute_direct_add replaced with LIVE version!")
