"""
📸 Instagram Follower Scraper
================================
استخراج فالوورهای پیج‌های عمومی اینستاگرام با Instaloader
نتایج در دیتابیس Neon (همون scraped_users) ذخیره میشن

⚠️ Limitations:
  - نیاز به لاگین با اکانت اینستاگرام
  - ~۲۰۰ درخواست در ساعت (محدودیت اینستاگرام)
  - فقط پیج‌های عمومی
  - ریسک بن/Shadow ban در صورت استفاده heavy

Environment variables (set in Render):
  IG_USERNAME  - Instagram username for login
  IG_PASSWORD  - Instagram password
  IG_SESSION_FILE - optional path to saved session file
"""

import os
import time
import json
import asyncio

# ═══════════════ Config ═══════════════
IG_USERNAME = os.environ.get("IG_USERNAME", "")
IG_PASSWORD = os.environ.get("IG_PASSWORD", "")

# Use a persistent session to avoid repeated logins (which trigger security checks)
SESSION_DIR = "saved_sessions"
IG_SESSION_FILE = os.environ.get(
    "IG_SESSION_FILE",
    os.path.join(SESSION_DIR, "instagram_session")
)


def get_instaloader():
    """Create a configured Instaloader instance with session persistence."""
    import instaloader
    L = instaloader.Instaloader(
        sleep=True,           # Auto-sleep between requests
        quiet=True,           # Less output noise
        user_agent=None,      # Let instaloader handle it
        dirname_pattern=os.path.join(SESSION_DIR, "{target}"),
        download_pictures=False,
        download_videos=False,
        download_video_thumbnails=False,
        compress_json=False,
    )
    # Try to load saved session
    session_path = IG_SESSION_FILE
    if os.path.exists(session_path):
        try:
            L.load_session_from_file(IG_USERNAME, filename=session_path)
            print(f"📸 IG session loaded for {IG_USERNAME}", flush=True)
        except Exception:
            pass
    return L


def login_instagram(L=None) -> bool:
    """Login to Instagram. Returns True if successful."""
    import instaloader
    import instaloader.exceptions as iex

    if L is None:
        L = get_instaloader()

    if not IG_USERNAME or not IG_PASSWORD:
        return False

    try:
        # Test if already logged in
        L.test_login()
        return True
    except Exception:
        pass

    try:
        L.login(IG_USERNAME, IG_PASSWORD)
        # Save session for future use
        os.makedirs(SESSION_DIR, exist_ok=True)
        L.save_session_to_file(IG_SESSION_FILE)
        print(f"📸 IG logged in as {IG_USERNAME}", flush=True)
        return True
    except iex.BadCredentialsException:
        print("❌ IG login failed: bad credentials", flush=True)
        return False
    except iex.TwoFactorAuthRequiredException:
        print("⚠️ IG 2FA required - use session file upload instead", flush=True)
        return False
    except iex.ConnectionException as e:
        print(f"⚠️ IG connection error: {e}", flush=True)
        return False
    except Exception as e:
        print(f"⚠️ IG login error: {e}", flush=True)
        return False


def scrape_followers(target_username: str, max_followers: int = 500,
                      progress_cb=None, stop_flag=None) -> dict:
    """
    Scrape followers from a public Instagram profile.
    
    Args:
        target_username: Instagram username to scrape
        max_followers: Maximum followers to extract
        progress_cb: Optional callback(extracted, total, current_name)
        stop_flag: Optional list with [0] that becomes [1] to stop
    
    Returns: 
        {"followers": [{"user_id": str, "username": str, "full_name": str, ...}],
         "error": str or None, "count": int}
    """
    import instaloader
    import instaloader.exceptions as iex

    L = get_instaloader()

    # Login
    if not login_instagram(L):
        return {
            "followers": [],
            "error": "Need IG_USERNAME and IG_PASSWORD env vars set in Render, or upload session file",
            "count": 0
        }

    followers = []
    error = None
    count = 0

    try:
        profile = instaloader.Profile.from_username(L.context, target_username)

        if profile.is_private:
            return {
                "followers": [],
                "error": f"@{target_username} is a private account - cannot scrape followers",
                "count": 0
            }

        total_followers = profile.followers
        print(f"📸 @{target_username}: {total_followers:,} followers, scraping up to {max_followers}", flush=True)

        for i, follower in enumerate(profile.get_followers()):
            if stop_flag and stop_flag[0]:
                error = "Stopped by user"
                break

            if i >= max_followers:
                break

            followers.append({
                "user_id": str(follower.userid),
                "username": follower.username,
                "full_name": follower.full_name or "",
                "is_private": follower.is_private,
                "is_verified": follower.is_verified,
                "followers_count": follower.followers,
                "source": f"instagram:@{target_username}"
            })
            count = i + 1

            if progress_cb and count % 10 == 0:
                progress_cb(count, total_followers, follower.username)

            # Instaloader has built-in sleep but we add a tiny extra safety
            if count % 50 == 0:
                time.sleep(3)

        # Save to DB
        if followers:
            from db import bulk_save_users as _bulk_save
            from db import upsert_scanned_chat as _upsert_chat
            users_for_db = []
            for f in followers:
                users_for_db.append({
                    "user_id": int(hash(f["username"]) % (10**12)),
                    "username": f["username"],
                    "first_name": f["full_name"],
                    "last_name": "",
                    "phone": ""
                })
            # Use a negative group_id-like prefix to mark IG sources: -200_xxx
            ig_source_id = -200000000000 - hash(target_username) % 1000000000
            _bulk_save(users_for_db, ig_source_id, f"IG:@{target_username}")
            _upsert_chat(
                chat_id=ig_source_id,
                chat_name=f"IG:@{target_username}",
                chat_type="instagram",
                total_members=total_followers,
                extracted_new=len(followers)
            )

        print(f"📸 Done: {count} followers from @{target_username}", flush=True)

    except iex.ProfileNotExistsException:
        error = f"@{target_username} does not exist"
    except iex.LoginRequiredException:
        error = "Instagram login required - check IG_USERNAME/IG_PASSWORD"
    except iex.ConnectionException as e:
        error = f"Instagram connection error: {e}"
    except Exception as e:
        error = str(e)[:200]
        print(f"📸 scrape error: {e}", flush=True)

    return {"followers": followers, "error": error, "count": count}


def upload_ig_session(session_file_path: str) -> bool:
    """Import a locally-saved Instagram session file.
    This bypasses login/2FA - just save the session after logging in locally."""
    if not os.path.exists(session_file_path):
        return False
    try:
        os.makedirs(SESSION_DIR, exist_ok=True)
        import shutil
        shutil.copy2(session_file_path, IG_SESSION_FILE)
        print(f"📸 IG session imported from {session_file_path}", flush=True)
        return True
    except Exception as e:
        print(f"📸 IG session import error: {e}", flush=True)
        return False
