with open("/home/user/repo/channel_adder.py", "r", encoding="utf-8") as f:
    content = f.read()

# 1. Change MAX_ADD_PER_ACCOUNT from 100 to 30
content = content.replace("MAX_ADD_PER_ACCOUNT = 100", "MAX_ADD_PER_ACCOUNT = 30")

# 2. Replace add_members_to_channel with improved version
old_func_start = 'async def add_members_to_channel(client, channel_id, channel_name, user_ids, phone):\n    """\n    اضافه کردن کاربران به کانال با متد AddContact + InviteToChannel'

# Find end of function (next section)
start_idx = content.find(old_func_start)
if start_idx == -1:
    print("ERROR: Function not found")
    exit(1)

next_section = "\n# ══════════════════════════════════════════════\n# منوی اصلی"
end_idx = content.find(next_section, start_idx)
if end_idx == -1:
    print("ERROR: End not found")
    exit(1)

new_func = '''async def add_members_to_channel(client, channel_id, channel_name, user_ids, phone):
    """
    FIXED: Add members to channel with warmup + AddContact + InviteToChannel
    
    Improvements:
    - Scans account's groups first to resolve peers (warmup)
    - Falls back to direct resolve for remaining users
    - Progress reporting
    - Better delay strategy for 30-user limit
    """
    limits = load_add_limits()
    already = limits.get(phone, {}).get("added", 0)
    remaining = MAX_ADD_PER_ACCOUNT - already

    # Filter: skip already-added
    filtered = [uid for uid in user_ids if not is_already_added(channel_id, uid)]
    
    total = min(len(filtered), remaining)
    if total == 0:
        print("⚠️ هیچ کاربری برای ادد نیست (همه قبلاً اضافه شدن یا ظرفیت پر)")
        return 0, 0

    print(f"\\n{'='*50}")
    print(f"🚀 شروع ادد به کانال: {channel_name}")
    print(f"📊 {total} نفر از {len(filtered)} کاربر")
    print(f"📱 اکانت: {phone}")
    print(f"📈 ظرفیت: {already}/{MAX_ADD_PER_ACCOUNT}")
    print(f"{'='*50}\\n")

    # Resolve target channel once
    try:
        target_peer = await client.resolve_peer(channel_id)
    except Exception as e:
        print(f"❌ کانال پیدا نشد: {e}")
        return 0, 0

    added = 0
    failed = 0
    skipped = 0
    errors = {"peer": 0, "privacy": 0, "already": 0, "flood": 0, "channel_admin": 0, "other": 0}
    start_time = time.time()

    # ─── Warmup: scan account's groups to build peer cache ───
    print(f"🔥 Warmup: scanning groups to resolve peers...", flush=True)
    valid_peers = {}
    uid_set_for_warmup = set(filtered[:total])
    
    try:
        async for dialog in client.get_dialogs(limit=200):
            if "group" in str(dialog.chat.type).lower():
                try:
                    async for member in client.get_chat_members(dialog.chat.id, limit=500):
                        u = member.user
                        if u and u.id in uid_set_for_warmup:
                            try:
                                valid_peers[u.id] = await client.resolve_peer(u.id)
                            except: pass
                except: pass
                await asyncio.sleep(0.3)
                if len(valid_peers) >= total * 0.8:
                    break
        print(f"  ✅ Warmup: {len(valid_peers)}/{total} peers resolved", flush=True)
    except Exception as we:
        print(f"  ⚠️ Warmup error: {we}", flush=True)

    # Fallback: direct resolve for remaining
    for uid in filtered[:total]:
        if uid not in valid_peers:
            try:
                valid_peers[uid] = await client.resolve_peer(uid)
            except: pass
            await asyncio.sleep(0.02)
    
    print(f"  📊 Total resolved: {len(valid_peers)}/{total}", flush=True)

    # ─── Main add loop ───
    for i, uid in enumerate(filtered[:total]):
        try:
            # Get peer from warmup cache or resolve directly
            if uid in valid_peers:
                user_peer = valid_peers[uid]
            else:
                try:
                    user_peer = await client.resolve_peer(uid)
                    valid_peers[uid] = user_peer
                except Exception:
                    failed += 1
                    errors["peer"] += 1
                    skipped += 1
                    continue

            # AddContact (needed for channel invite)
            try:
                await client.invoke(
                    AddContact(
                        id=user_peer,
                        first_name=str(uid)[:30],
                        last_name="",
                        phone="",
                        add_phone_privacy_exception=False
                    )
                )
                await asyncio.sleep(0.3)
            except: pass  # already in contacts

            # InviteToChannel
            await client.invoke(
                InviteToChannel(
                    channel=target_peer,
                    users=[user_peer]
                )
            )

            added += 1
            mark_added(channel_id, channel_name, uid)

            # Update limits
            limits[phone] = {"added": already + added, "last_used": int(time.time())}
            save_add_limits(limits)

        except FloodWait as fw:
            failed += 1
            errors["flood"] += 1
            print(f"  ⏱️ FloodWait {fw.value}s — صبر...", flush=True)
            await asyncio.sleep(fw.value + 5)
            continue

        except UserAlreadyParticipant:
            failed += 1
            errors["already"] += 1
            mark_added(channel_id, channel_name, uid)
            await asyncio.sleep(1)
            continue

        except (UserPrivacyRestricted, UserNotMutualContact):
            failed += 1
            errors["privacy"] += 1
            await asyncio.sleep(random.randint(2, 5))
            continue

        except (ChatAdminRequired, ChannelPrivate):
            print(f"\\n❌ ادمین نیستی یا کانال پرایوته!", flush=True)
            failed += 1
            errors["channel_admin"] += 1
            break

        except UsersTooMuch:
            failed += 1
            errors["other"] += 1
            await asyncio.sleep(random.randint(5, 10))
            continue

        except Exception as e:
            failed += 1
            es = str(e).lower()
            if "privacy" in es:
                errors["privacy"] += 1
            elif "already" in es:
                errors["already"] += 1
                mark_added(channel_id, channel_name, uid)
            else:
                errors["other"] += 1
            await asyncio.sleep(random.randint(2, 5))
            continue

        # Progress
        done = added + failed
        elapsed = int(time.time() - start_time)
        mins, secs = elapsed // 60, elapsed % 60
        speed = int(added / (elapsed / 60)) if elapsed > 30 else 0
        pct = int(done * 100 / total) if total > 0 else 0
        bar_filled = pct // 5
        bar = "█" * bar_filled + "░" * (20 - bar_filled)

        print(f"  [{bar}] {pct}% | ✅ {added} ❌ {failed} | ⏱ {mins:02d}:{secs:02d} | UID: {uid}", flush=True)

        # Delay (adjusted for 30-user limit)
        total_done = already + added
        if total_done > 25:
            delay = random.randint(12, 20)
        elif total_done > 15:
            delay = random.randint(8, 15)
        else:
            delay = random.randint(5, 10)
        await asyncio.sleep(delay)

    # Final report
    elapsed = int(time.time() - start_time)
    mins, secs = elapsed // 60, elapsed % 60

    print(f"\\n{'='*50}")
    print(f"✅ عملیات تمام شد — {channel_name}")
    print(f"{'='*50}")
    print(f"✅ اضافه شده: {added}")
    print(f"❌ ناموفق:    {failed}")
    print(f"⏭ رد شده:    {skipped}")
    print(f"⏱ زمان:       {mins:02d}:{secs:02d}")
    print(f"📊 ظرفیت:     {already + added}/{MAX_ADD_PER_ACCOUNT}")

    if failed > 0:
        print(f"\\n دلایل خطا:")
        if errors["peer"]:    print(f"   🔍 Peer Invalid: {errors['peer']}")
        if errors["privacy"]: print(f"   🔒 Privacy:      {errors['privacy']}")
        if errors["already"]: print(f"   👥 قبلاً عضو:     {errors['already']}")
        if errors["flood"]:   print(f"   ⏱ Flood:        {errors['flood']}")
        if errors["other"]:   print(f"   ❓ سایر:         {errors['other']}")

    print(f"{'='*50}\\n")
    return added, failed


'''

content = content[:start_idx] + new_func + content[end_idx:]

with open("/home/user/repo/channel_adder.py", "w", encoding="utf-8") as f:
    f.write(content)

print("✅ channel_adder.py fixed!")
