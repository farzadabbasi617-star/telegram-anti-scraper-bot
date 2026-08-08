"""
📸 Instagram Follower Scraper - High Power Edition
Supports URL input, aggressive extraction, auto-save to DB
"""
import os, time, json, random, asyncio, shutil, re

IG_USERNAME = os.environ.get("IG_USERNAME", "")
IG_PASSWORD = os.environ.get("IG_PASSWORD", "")
SESSION_DIR = "saved_sessions"
IG_SESSION_FILE = os.environ.get("IG_SESSION_FILE", os.path.join(SESSION_DIR, "instagram_session"))


def extract_username(raw):
    """Extract username from URL, @handle, or raw text"""
    raw = raw.strip().lower()
    if "instagram.com/" in raw:
        parts = raw.split("instagram.com/", 1)
        username = parts[1] if len(parts) > 1 else raw
        username = username.split("?")[0].split("#")[0].split("/")[0].strip("/")
    username = username.lstrip("@")
    username = re.sub(r'[^a-zA-Z0-9._]', '', username)
    return username


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


def scrape_followers(target_username, max_followers=1000, progress_cb=None, stop_flag=None, existing_ids=None):
    import instaloader, instaloader.exceptions as iex
    L = get_instaloader()
    if not login_instagram(L):
        return {"followers": [], "error": "Not logged in", "count": 0}

    if existing_ids is None:
        try:
            from db import get_conn
            cur = get_conn().cursor()
            cur.execute("SELECT user_id FROM scraped_users")
            existing_ids = {int(r[0]) for r in cur.fetchall()}
            cur.close()
        except: existing_ids = set()

    followers, error, count = [], None, 0
    t0 = time.time()
    try:
        profile = instaloader.Profile.from_username(L.context, target_username)
        if profile.is_private:
            return {"followers": [], "error": f"@{target_username} is private", "count": 0}
        total = profile.followers
        for i, f in enumerate(profile.get_followers()):
            if stop_flag and stop_flag[0]: error = "Stopped"; break
            if i >= max_followers: break
            if f.userid in existing_ids:
                count = i + 1
                if count % 200 == 0 and progress_cb:
                    elapsed = time.time() - t0
                    spd = int(count / max(1, elapsed) * 60)
                    progress_cb(count, total, f.username, f"{spd}/min skip:{f.username[:15]}")
                continue
            followers.append({
                "user_id": str(f.userid), "username": f.username, "full_name": f.full_name or "",
                "is_private": f.is_private, "is_verified": f.is_verified,
                "followers_count": f.followers, "source": f"instagram:@{target_username}"
            })
            count = i + 1
            if progress_cb and count % 25 == 0:
                elapsed = time.time() - t0
                spd = int(count / max(1, elapsed) * 60)
                progress_cb(count, total, f.username, f"{spd}/min new:{len(followers)}")
            if count % 200 == 0: time.sleep(0.5)
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
    return {"followers": followers, "error": error, "count": count,
            "total": profile.followers if 'profile' in dir() else 0}


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
    done = set(kv_get("ig_followed_usernames", []) or [])
    for username in target_usernames:
        if stop_flag and stop_flag[0]: break
        if followed >= remaining: break
        username = username.strip().replace("@", "").lower()
        if not username or username in done: skipped += 1; continue
        try:
            time.sleep(random.randint(40, 120))
            if random.random() < 0.3:
                try: instaloader.Profile.from_username(L.context, username); time.sleep(random.randint(3, 8))
                except: pass
            profile = instaloader.Profile.from_username(L.context, username)
            profile.follow()
            followed += 1; done.add(username)
            kv_set("ig_followed_usernames", list(done)); kv_set(today_key, already + followed)
        except iex.FollowRequestSent: followed += 1; done.add(username)
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
    kv_set("ig_followed_usernames", list(done)); kv_set(today_key, already + followed)
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
