with open("/home/user/repo/bot.py", "r", encoding="utf-8") as f:
    content = f.read()

# Add _execute_simple_add function before _do_quick_add
add_func = '''
async def _execute_simple_add(q, target_gid, client, phone, members, source_name):
    """Execute simple add flow"""
    from pyrogram.raw.functions.contacts import AddContact
    from pyrogram.raw.functions.channels import InviteToChannel
    from pyrogram.errors import FloodWait, PeerIdInvalid, UserAlreadyParticipant
    from pyrogram.errors import UserPrivacyRestricted, UserNotMutualContact
    from pyrogram.errors import ChatAdminRequired, UsersTooMuch
    
    prog = q.message
    added = 0
    failed = 0
    skipped = 0
    errors_detail = {"peer": 0, "privacy": 0, "already": 0, "flood": 0, "other": 0}
    first_error = ""
    start_t = time.time()
    
    limits = load_adder_limits()
    already_added = limits.get(phone, {}).get("added", 0)
    remaining = MAX_ADD_PER_ACCOUNT - already_added
    
    # Get target name
    try:
        tgt = await client.app.get_chat(target_gid)
        target_name = tgt.title
    except:
        target_name = "کانال مقصد"
    
    # Resolve target channel
    try:
        target_peer = await client.app.resolve_peer(target_gid)
    except Exception as e:
        await prog.edit_text(f"❌ کانال resolve نشد: {e}", reply_markup=InlineKeyboardMarkup([[_sub_back_btn(target="home")[0]]]))
        return
    
    total = min(len(members), remaining)
    
    async def upd():
        try:
            elapsed = int(time.time() - start_t)
            m, s = elapsed // 60, elapsed % 60
            pct = int((added + failed + skipped) * 100 / max(1, total))
            bar = "█" * (pct // 5) + "░" * (20 - pct // 5)
            spd = int(added / (elapsed / 60)) if elapsed > 30 else 0
            txt = f"📂 {source_name} → 📡 {target_name}\\n{bar} {pct}%\\n✅ {added} ❌ {failed} ⏭ {skipped}\\n⏱ {m:02d}:{s:02d} ⚡ {spd}/min"
            await prog.edit_text(txt, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("️ توقف", callback_data="stop_op")]]))
        except: pass
    
    await upd()
    
    # Add members
    for i, member in enumerate(members[:remaining]):
        uid = member.get("user_id", 0)
        if uid <= 10000 or uid >= 10**11:
            skipped += 1
            continue
        
        if is_user_already_added(target_gid, uid):
            skipped += 1
            continue
        
        try:
            # Resolve user
            try:
                user_peer = await client.app.resolve_peer(uid)
            except Exception as re:
                skipped += 1
                errors_detail["peer"] += 1
                if not first_error: first_error = f"Can't resolve {uid}"
                continue
            
            # AddContact
            try:
                await client.app.invoke(
                    AddContact(id=user_peer, first_name=str(uid)[:30], last_name="", phone="", add_phone_privacy_exception=False)
                )
                await asyncio.sleep(0.3)
            except: pass
            
            # InviteToChannel
            await client.app.invoke(
                InviteToChannel(channel=target_peer, users=[user_peer])
            )
            
            added += 1
            mark_user_as_added(target_gid, target_name, uid)
            limits = load_adder_limits()
            limits[phone] = {"added": already_added + added, "last_used": int(time.time())}
            save_adder_limits(limits)
            
            # Delay
            total_acc = already_added + added
            if total_acc > 80:
                await asyncio.sleep(random.randint(15, 25))
            elif total_acc > 50:
                await asyncio.sleep(random.randint(10, 18))
            else:
                await asyncio.sleep(random.randint(7, 13))
            
        except FloodWait as fw:
            failed += 1
            errors_detail["flood"] += 1
            await asyncio.sleep(fw.value + 5)
        except UserAlreadyParticipant:
            skipped += 1
            errors_detail["already"] += 1
            mark_user_as_added(target_gid, target_name, uid)
        except (UserPrivacyRestricted, UserNotMutualContact):
            failed += 1
            errors_detail["privacy"] += 1
        except PeerIdInvalid:
            failed += 1
            errors_detail["peer"] += 1
        except ChatAdminRequired:
            failed += 1
            errors_detail["other"] += 1
            if not first_error: first_error = "اکانت ادمین کانال نیست!"
            break
        except UsersTooMuch:
            failed += 1
            errors_detail["other"] += 1
            await asyncio.sleep(15)
        except Exception as e:
            failed += 1
            errors_detail["other"] += 1
            if not first_error: first_error = str(e)[:200]
        
        if (added + failed + skipped) % 5 == 0:
            await upd()
    
    # Final report
    elapsed = int(time.time() - start_t)
    m, s = elapsed // 60, elapsed % 60
    text = f"✅ <b>تمام شد!</b>\\n"
    text += f"━━━━━━━━━━━━━━━\\n"
    text += f"📂 منبع: {source_name}\\n"
    text += f"📡 مقصد: {target_name}\\n"
    text += f"✅ اضافه شده: {added}\\n"
    text += f"❌ ناموفق: {failed}\\n"
    text += f"⏭ رد شده: {skipped}\\n"
    text += f"⏱ زمان: {m:02d}:{s:02d}\\n"
    text += f"📊 ظرفیت: {already_added + added}/{MAX_ADD_PER_ACCOUNT}"
    
    if failed > 0 or errors_detail.get("peer", 0) > 0:
        text += f"\\n\\n<b>جزئیات خطا:</b>\\n"
        if errors_detail["peer"]: text += f"🔍 Peer Invalid: {errors_detail['peer']}\\n"
        if errors_detail["privacy"]: text += f"🔒 Privacy: {errors_detail['privacy']}\\n"
        if errors_detail["already"]: text += f"👥 قبلاً عضو: {errors_detail['already']}\\n"
        if errors_detail["flood"]: text += f"⏱ Flood: {errors_detail['flood']}\\n"
        if errors_detail["other"]: text += f"❓ سایر: {errors_detail['other']}\\n"
        if first_error: text += f"\\n💬 اولین خطا: {first_error[:200]}"
    
    # Cleanup
    atk_state.pop("_simp_client", None)
    atk_state.pop("_simp_members", None)
    
    buttons = [
        [InlineKeyboardButton("🔄 ادد از گروه دیگه", callback_data="pick_account_add")],
        [InlineKeyboardButton(" خانه", callback_data="home")],
    ]
    
    try:
        await prog.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
    except: pass


'''

# Insert before _do_quick_add
marker = "async def _do_quick_add"
content = content.replace(marker, add_func + marker)

with open("/home/user/repo/bot.py", "w", encoding="utf-8") as f:
    f.write(content)

print("✅ _execute_simple_add added!")
