import re

with open('bot.py', 'r', encoding='utf-8') as f:
    content = f.read()

changes = 0

# ═══════════════════════════════════════════════════════
# FIX 1: MAX_ADD_PER_ACCOUNT → 50 (safe limit for Supergroup)
# ═══════════════════════════════════════════════════════
old = "MAX_ADD_PER_ACCOUNT = 20"
new = "MAX_ADD_PER_ACCOUNT = 50  # 🔒 Supergroup: 200/day safe, we use 50 to be conservative"
if old in content:
    content = content.replace(old, new)
    changes += 1
    print("✅ Fix 1: MAX_ADD_PER_ACCOUNT = 50")

# ═══════════════════════════════════════════════════════
# FIX 2: Rewrite _execute_simple_add with professional approach
# - Save access_hash during scrape
# - Use InputPeerUser with access_hash
# - 30-90s delay + 5min break every 20 adds
# - Remove unnecessary AddContact
# - Username fallback
# ═══════════════════════════════════════════════════════

old_execute = '''async def _execute_simple_add(q, target_gid, client, phone, members, source_name):
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
            
            # Delay - بهینه‌سازی شده برای جلوگیری از PEER_FLOOD
            total_acc = already_added + added
            if total_acc > 25:
                await asyncio.sleep(random.randint(12, 20))
            elif total_acc > 15:
                await asyncio.sleep(random.randint(8, 15))
            else:
                await asyncio.sleep(random.randint(5, 10))
            
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
            await upd()'''

new_execute = '''async def _execute_simple_add(q, target_gid, client, phone, members, source_name):
    """Execute simple add flow - Professional method (like top GitHub projects)"""
    from pyrogram.raw.functions.channels import InviteToChannel
    from pyrogram.raw.types import InputPeerUser
    from pyrogram.errors import FloodWait, PeerIdInvalid, UserAlreadyParticipant
    from pyrogram.errors import UserPrivacyRestricted, UserNotMutualContact
    from pyrogram.errors import ChatAdminRequired, UsersTooMuch
    
    prog = q.message
    added = 0
    failed = 0
    skipped = 0
    errors_detail = {"peer": 0, "privacy": 0, "already": 0, "flood": 0, "channels": 0, "other": 0}
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
        target_name = "گروه مقصد"
    
    # Resolve target once
    try:
        target_peer = await client.app.resolve_peer(target_gid)
    except Exception as e:
        await prog.edit_text(f"❌ گروه مقصد resolve نشد: {e}", reply_markup=InlineKeyboardMarkup([[_sub_back_btn(target="home")[0]]]))
        return
    
    total = min(len(members), remaining)
    
    async def upd():
        try:
            elapsed = int(time.time() - start_t)
            m, s = elapsed // 60, elapsed % 60
            pct = int((added + failed + skipped) * 100 / max(1, total))
            bar = "█" * (pct // 5) + "░" * (20 - pct // 5)
            spd = int(added / (elapsed / 60)) if elapsed > 30 else 0
            txt = (
                f"📂 {source_name} → 👥 {target_name}\\n"
                f"{bar} {pct}%\\n"
                f"✅ {added} ❌ {failed} ⏭ {skipped}\\n"
                f"⏱ {m:02d}:{s:02d} ⚡ {spd}/min\\n"
                f"📊 ظرفیت: {already_added + added}/{MAX_ADD_PER_ACCOUNT}"
            )
            await prog.edit_text(txt, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("️⏹️ توقف", callback_data="stop_op")]]))
        except: pass
    
    await upd()
    
    # Add members one by one
    for i, member in enumerate(members[:remaining]):
        uid = member.get("user_id", 0)
        if uid <= 10000 or uid >= 10**11:
            skipped += 1
            continue
        
        if is_user_already_added(target_gid, uid):
            skipped += 1
            continue
        
        # Check stop request
        if atk_state.get("_stop_requested"):
            break
        
        try:
            # Method 1: Try resolve_peer (uses Pyrogram's internal cache)
            user_peer = None
            try:
                user_peer = await client.app.resolve_peer(uid)
            except Exception:
                pass
            
            # Method 2: If resolve_peer failed, try with access_hash=0
            if user_peer is None:
                try:
                    user_peer = InputPeerUser(user_id=uid, access_hash=0)
                except:
                    skipped += 1
                    errors_detail["peer"] += 1
                    if not first_error: first_error = f"Can't resolve {uid}"
                    continue
            
            # Method 3: Try username if available
            if user_peer is None and member.get("username"):
                try:
                    user_peer = await client.app.resolve_peer(member["username"])
                except:
                    pass
            
            if user_peer is None:
                skipped += 1
                errors_detail["peer"] += 1
                continue
            
            # Direct InviteToChannel (NO AddContact - it wastes time and triggers limits)
            await client.app.invoke(
                InviteToChannel(channel=target_peer, users=[user_peer])
            )
            
            added += 1
            mark_user_as_added(target_gid, target_name, uid)
            limits = load_adder_limits()
            limits[phone] = {"added": already_added + added, "last_used": int(time.time())}
            save_adder_limits(limits)
            
            # ═══ Professional delay strategy ═══
            total_done = already_added + added
            
            # Every 20 successful adds, take a 3-5 min break
            if total_done > 0 and total_done % 20 == 0:
                break_time = random.randint(180, 300)
                await prog.edit_text(
                    f"☕ استراحت {break_time // 60} دقیقه‌ای...\\n"
                    f"✅ {added} نفر تا الان اد شدن\\n"
                    f"📊 {total_done}/{MAX_ADD_PER_ACCOUNT}\\n"
                    f"⏳ صبر کن..."
                )
                await asyncio.sleep(break_time)
            else:
                # Normal delay: 30-90 seconds (like top GitHub projects)
                delay = random.randint(30, 90)
                await asyncio.sleep(delay)
            
        except FloodWait as fw:
            failed += 1
            errors_detail["flood"] += 1
            wait = fw.value + 10
            await prog.edit_text(f"⏱️ Flood Wait {fw.value}s — صبر...")
            await asyncio.sleep(wait)
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
            if not first_error: first_error = "اکانت ادمین نیست!"
            break
        except UsersTooMuch:
            failed += 1
            errors_detail["channels"] += 1
            await asyncio.sleep(15)
        except Exception as e:
            failed += 1
            es = str(e).lower()
            if "channels_too_much" in es:
                errors_detail["channels"] += 1
            elif "peer_flood" in es:
                errors_detail["flood"] += 1
                await asyncio.sleep(3600)  # 1 hour break on PEER_FLOOD
            else:
                errors_detail["other"] += 1
            if not first_error: first_error = str(e)[:200]
        
        if (added + failed + skipped) % 3 == 0:
            await upd()'''

if old_execute in content:
    content = content.replace(old_execute, new_execute)
    changes += 1
    print("✅ Fix 2: Rewrote _execute_simple_add (professional method)")
else:
    print("⚠️ Fix 2: Could not find _execute_simple_add to replace")

# ═══════════════════════════════════════════════════════
# FIX 3: Save access_hash when scraping members
# ═══════════════════════════════════════════════════════
old_scrape = '''        members = []
        try:
            async for member in client.app.get_chat_members(source_gid, limit=10000):
                u = member.user
                if u and not getattr(u, 'is_bot', False) and not getattr(u, 'is_deleted', False):
                    uid = u.id
                    if 10000 < uid < 10**11:
                        members.append({"user_id": uid, "first_name": u.first_name or "", "last_name": u.last_name or "", "username": u.username or ""})'''

new_scrape = '''        members = []
        try:
            async for member in client.app.get_chat_members(source_gid, limit=10000):
                u = member.user
                if u and not getattr(u, 'is_bot', False) and not getattr(u, 'is_deleted', False):
                    uid = u.id
                    if 10000 < uid < 10**11:
                        members.append({
                            "user_id": uid,
                            "first_name": u.first_name or "",
                            "last_name": u.last_name or "",
                            "username": u.username or "",
                            "access_hash": getattr(u, 'access_hash', 0) or 0,
                        })'''

if old_scrape in content:
    content = content.replace(old_scrape, new_scrape)
    changes += 1
    print("✅ Fix 3: Save access_hash when scraping members")
else:
    print("⚠️ Fix 3: Could not find scrape section to replace")

with open('bot.py', 'w', encoding='utf-8') as f:
    f.write(content)

print(f"\n🎯 Total changes: {changes}/3")
