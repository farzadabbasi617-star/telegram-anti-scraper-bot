"""
📸 Instagram Follower Scraper - Fixed
"""
import os, time, json, random, asyncio, shutil

IG_USERNAME = os.environ.get("IG_USERNAME", "")
IG_PASSWORD = os.environ.get("IG_PASSWORD", "")
SESSION_DIR = "saved_sessions"
IG_SESSION_FILE = os.environ.get("IG_SESSION_FILE", os.path.join(SESSION_DIR, "instagram_session"))


def get_instaloader():
    import instaloader
    L = instaloader.Instaloader(sleep=True, quiet=True, download_pictures=False,
                                 download_videos=False, download_video_thumbnails=False, compress_json=False)
    if os.path.exists(IG_SESSION_FILE):
        try: L.load_session_from_file(IG_USERNAME, filename=IG_SESSION_FILE)
        except: pass
    return L


def login_instagram(L=None):
    import instaloader, instaloader.exceptions as iex
    if L is None: L = get_instaloader()
    if not IG_USERNAME or not IG_PASSWORD: return False
    try: L.test_login(); return True
    except: pass
    passwords = [IG_PASSWORD]
    if '$' in IG_PASSWORD:
        parts = IG_PASSWORD.rsplit('$', 1)
        if len(parts) == 2 and parts[1].isdigit(): passwords.append(parts[0] + '$')
    for pwd in passwords:
        try:
            L.login(IG_USERNAME, pwd)
            os.makedirs(SESSION_DIR, exist_ok=True)
            L.save_session_to_file(IG_SESSION_FILE)
            return True
        except iex.BadCredentialsException: continue
        except Exception: return False
    return False


def scrape_followers(target_username, max_followers=500, progress_cb=None, stop_flag=None):
    import instaloader, instaloader.exceptions as iex
    L = get_instaloader()
    if not login_instagram(L): return {"followers": [], "error": "Not logged in", "count": 0}
    followers, error, count = [], None, 0
    try:
        profile = instaloader.Profile.from_username(L.context, target_username)
        if profile.is_private: return {"followers": [], "error": f"@{target_username} is private", "count": 0}
        total = profile.followers
        for i, f in enumerate(profile.get_followers()):
            if stop_flag and stop_flag[0]: error = "Stopped"; break
            if i >= max_followers: break
            followers.append({"user_id": str(f.userid), "username": f.username, "full_name": f.full_name or "",
                              "is_private": f.is_private, "is_verified": f.is_verified,
                              "followers_count": f.followers, "source": f"instagram:@{target_username}"})
            count = i + 1
            if progress_cb and count % 10 == 0: progress_cb(count, total, f.username)
            if count % 50 == 0: time.sleep(3)
        if followers:
            from db import bulk_save_users as bsu, upsert_scanned_chat as usc
            udb = [{"user_id": int(hash(x["username"]) % (10**12)), "username": x["username"],
                     "first_name": x["full_name"], "last_name": "", "phone": ""} for x in followers]
            ig_id = -200000000000 - hash(target_username) % 1000000000
            bsu(udb, ig_id, f"IG:@{target_username}")
            usc(chat_id=ig_id, chat_name=f"IG:@{target_username}", chat_type="instagram",
                total_members=total, extracted_new=len(followers))
    except iex.ProfileNotExistsException: error = f"@{target_username} does not exist"
    except Exception as e: error = str(e)[:200]
    return {"followers": followers, "error": error, "count": count}


def follow_users(target_usernames, max_follows=40, progress_cb=None, stop_flag=None):
    import instaloader, instaloader.exceptions as iex
    from db import kv_get, kv_set
    L = get_instaloader()
    if not login_instagram(L): return {"followed": 0, "failed": 0, "skipped": 0, "error": "Not logged in"}
    today_key = f"ig_follow_count_{time.strftime('%Y%m%d')}"
    already = int(kv_get(today_key, 0) or 0)
    if already >= 60: return {"followed": 0, "failed": 0, "skipped": 0, "error": f"Daily limit: {already}/60"}
    remaining = min(max_follows, 60 - already)
    followed, failed, skipped, error = 0, 0, 0, None
    fsk = "ig_followed_usernames"
    done = set(kv_get(fsk, []) or [])
    for username in target_usernames:
        if stop_flag and stop_flag[0]: error = "Stopped"; break
        if followed >= remaining: break
        username = username.strip().replace("@", "").lower()
        if not username or username in done: skipped += 1; continue
        try:
            for _ in range(random.randint(40, 120)):
                if stop_flag and stop_flag[0]: break
                time.sleep(1)
            if stop_flag and stop_flag[0]: break
            if random.random() < 0.3:
                try:
                    instaloader.Profile.from_username(L.context, username)
                    time.sleep(random.randint(3, 8))
                except: pass
            profile = instaloader.Profile.from_username(L.context, username)
            L.context.username = IG_USERNAME
            profile.follow()
            followed += 1; done.add(username)
            kv_set(fsk, list(done)); kv_set(today_key, already + followed)
        except iex.FollowRequestSent: followed += 1; done.add(username); kv_set(fsk, list(done))
        except iex.ConnectionException as e:
            failed += 1
            if any(x in str(e).lower() for x in ["429", "too many", "block"]):
                error = f"Rate limited after {followed} follows"; break
            time.sleep(60)
        except Exception as e:
            failed += 1
            if any(x in str(e).lower() for x in ["feedback_required", "challenge"]):
                error = f"Challenge after {followed} follows"; break
            time.sleep(5)
    kv_set(fsk, list(done)); kv_set(today_key, already + followed)
    return {"followed": followed, "failed": failed, "skipped": skipped, "error": error}


def get_ig_follow_stats():
    from db import kv_get
    today = int(kv_get(f"ig_follow_count_{time.strftime('%Y%m%d')}", 0) or 0)
    total = len(kv_get("ig_followed_usernames", []) or [])
    return {"today": today, "total_ever": total, "daily_limit": 60}


def upload_ig_session(session_file_path):
    if not os.path.exists(session_file_path): return False
    try:
        os.makedirs(SESSION_DIR, exist_ok=True)
        shutil.copy2(session_file_path, IG_SESSION_FILE)
        return True
    except: return False
