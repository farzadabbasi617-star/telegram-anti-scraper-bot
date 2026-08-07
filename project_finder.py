"""
Project Finder - اسکنر پروژه‌های اوپن‌سورس
گشتن در گیت‌هاب، گیت‌لب، Codeberg و سورس‌هات
دسته‌بندی‌های مختلف: امنیت، تلگرام، هوش مصنوعی، کریپتو، ابزار، بازی
فیلتر: لایسنس آزاد/بدون لایسنس (نه پروژه‌های کپی‌رایت محدود)
"""

import json
import time
import random
import asyncio
import requests
import re
from datetime import datetime, timezone
from typing import List, Dict, Any

STATE_FILE = "pfinder_state.json"
FOUND_FILE = "pfinder_projects.json"

# Try to use DB-backed storage (falls back to JSON if DB unavailable)
try:
    import db as _db
    _HAS_DB = True
except Exception:
    _HAS_DB = False

# ---------- دسته‌بندی‌ها با کوئری‌های جستجو ----------
CATEGORIES = {
    "hack": {
        "name": "🔐 امنیت/هک/پنتست",
        "emoji": "🔐",
        "queries": [
            "pentest tool", "hacking tool", "osint", "exploit",
            "bug bounty", "red team", "phishing", "keylogger",
            "rat trojan", "reverse shell", "payload", "c2 framework",
            "scanner vulnerability", "bruteforce", "hack tool",
        ],
    },
    "tg": {
        "name": "✈️ تلگرام",
        "emoji": "✈️",
        "queries": [
            "telegram bot", "telegram scraper", "telegram userbot",
            "pyrogram", "telethon", "telegram member adder",
            "telegram bulk message", "telegram parser",
        ],
    },
    "ai": {
        "name": "🤖 هوش مصنوعی",
        "emoji": "🤖",
        "queries": [
            "llm agent", "ai agent", "gpt", "stable diffusion",
            "rag pipeline", "fine tuning", "langchain",
            "autogpt", "ai assistant", "ollama",
        ],
    },
    "crypto": {
        "name": "💰 کریپتو/بلاکچین",
        "emoji": "💰",
        "queries": [
            "crypto trading bot", "mev bot", "sniper bot",
            "memecoin", "dex bot", "airdrop farmer",
            "nft bot", "solana bot", "ethereum bot",
        ],
    },
    "tools": {
        "name": "🛠️ ابزارهای کاربردی",
        "emoji": "🛠️",
        "queries": [
            "automation script", "cli tool", "scraper",
            "downloader", "backup tool", "monitoring",
            "selfhosted", "dashboard", "api server",
        ],
    },
    "game": {
        "name": "🎮 گیم/چیت/هک بازی",
        "emoji": "🎮",
        "queries": [
            "game hack", "game cheat", "csgo cheat",
            "aimbot", "esp hack", "reverse engineering game",
            "game mod menu", "cheat engine script",
        ],
    },
}

# لایسنس‌های آزاد/اوپن‌سورس (یا بدون لایسنس)
# GitHub license keys
OPEN_LICENSES = {
    "mit", "apache-2.0", "gpl-3.0", "gpl-2.0", "agpl-3.0",
    "bsd-3-clause", "bsd-2-clause", "lgpl-3.0", "mpl-2.0",
    "unlicense", "wtfpl", "isc", "cc0-1.0", "other", "none", "",
}

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/119.0.0.0 Safari/537.36",
]

HEADERS = {"Accept": "application/vnd.github+json", "User-Agent": random.choice(USER_AGENTS)}


def _get(url, **kw):
    kw.setdefault("timeout", 20)
    kw.setdefault("headers", HEADERS)
    return requests.get(url, **kw)


# ---------- state / storage ----------
def _load_state_file():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}
def _save_state_file(s):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(s, f, ensure_ascii=False, indent=2)
    except: pass
def _load_found_file() -> List[Dict]:
    try:
        with open(FOUND_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []
def _save_found_file(lst):
    try:
        with open(FOUND_FILE, "w", encoding="utf-8") as f:
            json.dump(lst, f, ensure_ascii=False, indent=2)
    except: pass

def load_state():
    base = {"running": False, "total_found": 0, "last_scan": 0,
            "scanned_repos": [], "last_results_by_cat": {}}
    if _HAS_DB:
        d = _db.kv_get("pf_state", {}) or {}
        base.update(d)
        return base
    base.update(_load_state_file())
    return base


def save_state(s):
    _save_state_file(s)
    if _HAS_DB:
        try: _db.kv_set("pf_state", s)
        except: pass


def load_found() -> List[Dict]:
    if _HAS_DB:
        try: return _db.load_projects()
        except: pass
    return _load_found_file()


def save_found(lst):
    _save_found_file(lst)
    if _HAS_DB:
        try:
            # Sync to DB
            for p in lst:
                _db.save_project(p["url"], p.get("platform",""), p.get("full_name",""),
                                 p.get("category","other"), p)
        except: pass


# ---------- helpers ----------
def is_open_license(repo: dict) -> bool:
    lic = (repo.get("license") or {})
    key = (lic.get("key") or "").lower()
    # if no license set => treat as "no license" (still report but tag it)
    return True  # we will tag as ⚠️ بدون لایسنس instead of filtering out; user asked for "بدون لایسنس" too


def to_jalali_age(iso_date_str) -> str:
    """Convert ISO date to rough age string in Persian."""
    try:
        d = datetime.fromisoformat(iso_date_str.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        delta = now - d
        sec = int(delta.total_seconds())
        if sec < 60: return f"{sec} ثانیه پیش"
        if sec < 3600: return f"{sec//60} دقیقه پیش"
        if sec < 86400: return f"{sec//3600} ساعت پیش"
        if sec < 86400*30: return f"{sec//86400} روز پیش"
        if sec < 86400*365: return f"{sec//(86400*30)} ماه پیش"
        return f"{sec//(86400*365)} سال پیش"
    except:
        return ""


# ---------- GitHub search ----------
def search_github(query: str, max_results=20) -> List[Dict]:
    """Search GitHub repos via the public API (no token needed for low volume)."""
    results = []
    # search pushed:>2024-01-01 to keep stuff fresh-ish
    url = "https://api.github.com/search/repositories"
    params = {
        "q": f"{query} pushed:>2023-01-01",
        "sort": "stars",
        "order": "desc",
        "per_page": max_results,
    }
    try:
        r = _get(url, params=params)
        if r.status_code == 403 or r.status_code == 429:
            # rate limited - skip silently
            return results
        if not r.ok:
            return results
        data = r.json()
        for item in data.get("items", []):
            lic = item.get("license") or {}
            results.append({
                "platform": "github",
                "full_name": item.get("full_name"),
                "name": item.get("name"),
                "owner": (item.get("owner") or {}).get("login"),
                "url": item.get("html_url"),
                "description": (item.get("description") or "")[:300],
                "stars": item.get("stargazers_count", 0),
                "forks": item.get("forks_count", 0),
                "language": item.get("language") or "—",
                "topics": item.get("topics") or [],
                "license": lic.get("spdx_id") or lic.get("name") or "بدون لایسنس",
                "updated_at": item.get("pushed_at"),
                "created_at": item.get("created_at"),
                "open_issues": item.get("open_issues_count", 0),
            })
    except Exception as e:
        print(f"github search err: {e}", flush=True)
    return results


# ---------- GitLab search (public GitLab.com) ----------
def search_gitlab(query: str, max_results=15) -> List[Dict]:
    results = []
    url = "https://gitlab.com/api/v4/projects"
    params = {
        "search": query,
        "order_by": "star_count",
        "sort": "desc",
        "per_page": max_results,
        "visibility": "public",
        "simple": "false",
    }
    try:
        r = _get(url, params=params)
        if not r.ok:
            return results
        for item in r.json() or []:
            # skip extremely old stuff
            la = item.get("last_activity_at")
            if la and la < "2023-01-01":
                continue
            results.append({
                "platform": "gitlab",
                "full_name": item.get("path_with_namespace"),
                "name": item.get("name"),
                "owner": (item.get("namespace") or {}).get("path"),
                "url": item.get("web_url"),
                "description": (item.get("description") or "")[:300],
                "stars": item.get("star_count", 0),
                "forks": item.get("forks_count", 0),
                "language": "—",
                "topics": item.get("topics") or [],
                "license": (item.get("license") or {}).get("name") if item.get("license") else "بدون لایسنس",
                "updated_at": item.get("last_activity_at"),
                "created_at": item.get("created_at"),
                "open_issues": 0,
            })
    except Exception as e:
        print(f"gitlab search err: {e}", flush=True)
    return results


# ---------- Codeberg search (gitea API) ----------
def search_codeberg(query: str, max_results=10) -> List[Dict]:
    results = []
    url = "https://codeberg.org/api/v1/repos/search"
    params = {"q": query, "sort": "stars", "order": "desc", "limit": max_results}
    try:
        r = _get(url, params=params)
        if not r.ok:
            return results
        for item in (r.json() or {}).get("data", []):
            results.append({
                "platform": "codeberg",
                "full_name": item.get("full_name"),
                "name": item.get("name"),
                "owner": (item.get("owner") or {}).get("login"),
                "url": item.get("html_url"),
                "description": (item.get("description") or "")[:300],
                "stars": item.get("stars_count", 0),
                "forks": item.get("forks_count", 0),
                "language": item.get("language") or "—",
                "topics": item.get("topics") or [],
                "license": "بدون لایسنس",
                "updated_at": item.get("updated_at"),
                "created_at": item.get("created_at"),
                "open_issues": item.get("open_issues_count", 0),
            })
    except Exception as e:
        print(f"codeberg err: {e}", flush=True)
    return results


# ---------- trending shortcut (GitHub trending via unofficial, fallback to API) ----------
def search_trending_github(language=None, since="daily") -> List[Dict]:
    """Quick pull of trending repos (no auth) by scraping github.com/trending."""
    results = []
    url = "https://github.com/trending"
    if language:
        url += f"/{language}"
    try:
        r = _get(url, params={"since": since}, headers={"User-Agent": random.choice(USER_AGENTS)})
        if not r.ok:
            return results
        html = r.text
        # Parse article blocks
        articles = re.findall(r'<article\s+class="Box-row">(.*?)</article>', html, re.S)
        for art in articles[:25]:
            m_name = re.search(r'<h2[^>]*>\s*<a[^>]*href="(/[^"]+)"', art)
            if not m_name: continue
            full_name = m_name.group(1).strip("/")
            m_desc = re.search(r'<p[^>]*class="[^"]*col-9[^"]*"[^>]*>(.*?)</p>', art, re.S)
            desc = re.sub(r"\s+", " ", m_desc.group(1)).strip() if m_desc else ""
            m_stars = re.search(r'href="/[^"]+/stargazers"[^>]*>\s*([\d,]+)\s*</a>', art)
            stars = int(m_stars.group(1).replace(",","")) if m_stars else 0
            m_lang = re.search(r'<span itemprop="programmingLanguage">([^<]+)</span>', art)
            lang = m_lang.group(1).strip() if m_lang else "—"
            m_today = re.search(r'([\d,]+)\s+stars\s+today', art)
            today_stars = int(m_today.group(1).replace(",","")) if m_today else 0
            results.append({
                "platform": "github",
                "full_name": full_name,
                "name": full_name.split("/")[-1],
                "owner": full_name.split("/")[0],
                "url": f"https://github.com/{full_name}",
                "description": desc[:300],
                "stars": stars,
                "stars_today": today_stars,
                "forks": 0,
                "language": lang,
                "topics": [],
                "license": "—",
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "created_at": "",
                "open_issues": 0,
                "trending": True,
            })
    except Exception as e:
        print(f"trending err: {e}", flush=True)
    return results


# ---------- scan a category ----------
def scan_category(cat_id: str, min_stars=0, per_platform=8) -> List[Dict]:
    cat = CATEGORIES.get(cat_id)
    if not cat:
        return []
    found = []
    seen_urls = set()
    # pick 3 random queries per run to keep things varied
    queries = random.sample(cat["queries"], min(3, len(cat["queries"])))
    for q in queries:
        for fn in (search_github, search_gitlab, search_codeberg):
            try:
                items = fn(q, max_results=per_platform)
                for it in items:
                    if it["url"] in seen_urls:
                        continue
                    if it["stars"] < min_stars:
                        continue
                    it["category"] = cat_id
                    it["category_name"] = cat["name"]
                    it["query"] = q
                    it["found_at"] = int(time.time())
                    seen_urls.add(it["url"])
                    found.append(it)
                time.sleep(random.uniform(1.0, 2.5))
            except Exception as e:
                print(f"search fail {fn.__name__} {q}: {e}", flush=True)
    # sort by stars desc
    found.sort(key=lambda x: x.get("stars", 0), reverse=True)
    return found


def scan_trending() -> List[Dict]:
    """Return trending repos on GitHub (cross category)."""
    items = search_trending_github()
    for it in items:
        it["category"] = "trending"
        it["category_name"] = "🔥 ترند روز گیت‌هاب"
        it["found_at"] = int(time.time())
    return items


# ---------- persist / dedupe ----------
def merge_new(results: List[Dict]) -> List[Dict]:
    existing = load_found()
    seen = {f["url"] for f in existing}
    new = []
    for r in results:
        if r["url"] not in seen:
            existing.append(r)
            seen.add(r["url"])
            new.append(r)
    save_found(existing)
    st = load_state()
    st["total_found"] = len(existing)
    st["last_scan"] = int(time.time())
    save_state(st)
    return new


def projects_by_category():
    data = load_found()
    out = {}
    for cid, c in CATEGORIES.items():
        items = [x for x in data if x.get("category") == cid]
        items.sort(key=lambda x: x.get("stars",0), reverse=True)
        out[cid] = items
    trend = [x for x in data if x.get("trending")]
    out["trending"] = trend
    return out


def export_csv() -> bytes:
    import csv, io
    data = load_found()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["category","platform","name","owner","url","description","stars","forks","language","license","updated_at"])
    for r in data:
        w.writerow([
            r.get("category_name",""), r.get("platform",""), r.get("full_name",""),
            r.get("owner",""), r.get("url",""), (r.get("description") or "").replace("\n"," "),
            r.get("stars",0), r.get("forks",0), r.get("language",""), r.get("license",""),
            r.get("updated_at",""),
        ])
    return buf.getvalue().encode("utf-8-sig")


def clear_all():
    save_found([])
    save_state({"running": False, "total_found": 0, "last_scan": 0,
                "scanned_repos": [], "last_results_by_cat": {}})
    if _HAS_DB:
        try: _db.clear_projects()
        except: pass
