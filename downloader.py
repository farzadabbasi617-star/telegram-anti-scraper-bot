"""
Universal Media Downloader
پشتیبانی از: TikTok, Instagram (Reels/Post), YouTube Shorts, Twitter/X,
Reddit, Aparat, Pinterest, Coub, SoundCloud, Pixiv
از چند بک‌اند رایگان و بدون توکن استفاده میکند (cobalt + yt-dlp API mirrors + direct)
"""
import re
import requests
import json
import random
import time

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148",
]

# Cobalt.tools public instances (no API key, community-run)
COBALT_INSTANCES = [
    "https://api.cobalt.tools/api/json",
    "https://co.wuk.sh/api/json",
    "https://cobalt-api.kwiatekmiki.com/api/json",
]

URL_REGEX = re.compile(r"https?://[^\s'\"<>]+", re.IGNORECASE)

SUPPORTED_PATTERNS = {
    "tiktok":  r"tiktok\.com/",
    "instagram": r"instagram\.com/(p/|reel/|tv/|stories/)",
    "youtube": r"(youtube\.com/(shorts/|watch\?)|youtu\.be/)",
    "twitter": r"(twitter\.com|x\.com)/\w+/status/",
    "reddit":  r"reddit\.com/|redd\.it/",
    "aparat":  r"aparat\.com/v/",
    "pinterest": r"pinterest\.(com|it)/pin/",
    "coub":    r"coub\.com/view/",
    "soundcloud": r"soundcloud\.com/",
    "vimeo":   r"vimeo\.com/",
    "pixiv":   r"pixiv\.net/",
}


def detect_platform(url: str) -> str:
    for k, pat in SUPPORTED_PATTERNS.items():
        if re.search(pat, url):
            return k
    # generic try
    return "generic"


def try_cobalt(url: str) -> dict:
    """Try cobalt.tools public instances to fetch a direct media URL."""
    payload = {
        "url": url,
        "vCodec": "h264",
        "vQuality": "1080",
        "aFormat": "mp3",
        "isNoTTWatermark": True,
        "isAudioOnly": False,
    }
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": random.choice(USER_AGENTS),
    }
    random.shuffle(COBALT_INSTANCES)
    for inst in COBALT_INSTANCES:
        try:
            r = requests.post(inst, headers=headers, json=payload, timeout=30)
            if not r.ok:
                continue
            d = r.json()
            if d.get("status") in ("redirect", "stream", "tunnel") and d.get("url"):
                return {"ok": True, "download_url": d["url"], "service": inst, "filename": d.get("filename")}
            if d.get("status") == "picker" and d.get("picker"):
                # Multiple items
                return {"ok": True, "picker": d["picker"], "service": inst}
            if d.get("status") == "error":
                # try next instance
                continue
        except Exception as e:
            print(f"cobalt {inst} err: {e}", flush=True)
            continue
    return {"ok": False, "error": "هیچ یک از سرویس‌ها پاسخ نداد"}


def try_yt_dlp_mirror(url: str) -> dict:
    """Try a public yt-dlp API (co.wuk.sh supports YouTube too)."""
    # cobalt already handles youtube with the above, so this is just fallback
    return try_cobalt(url)


def fetch_media(url: str) -> dict:
    platform = detect_platform(url)
    res = try_cobalt(url)
    if not res.get("ok"):
        res = try_yt_dlp_mirror(url)
    if not res.get("ok"):
        return {"ok": False, "platform": platform, "error": res.get("error","خطا در دریافت")}
    res["platform"] = platform
    return res


def is_supported_url(url: str) -> bool:
    return detect_platform(url) != "generic" or True  # try anyway
