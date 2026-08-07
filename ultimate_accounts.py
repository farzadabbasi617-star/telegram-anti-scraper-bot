"""Ultimate Account Manager - Proxy + Device Spoofing"""

import os, json, time

PROXIES_FILE = "proxies.json"

def load_proxies():
    if os.path.exists(PROXIES_FILE):
        try:
            with open(PROXIES_FILE, "r") as f: return json.load(f)
        except: pass
    return {"proxies": []}

def save_proxies(p):
    with open(PROXIES_FILE, "w") as f: json.dump(p, f, indent=2)

def add_proxy(scheme="socks5", host="", port=1080, username="", password=""):
    proxies = load_proxies()
    proxies["proxies"].append({"scheme": scheme, "host": host, "port": int(port),
        "username": username, "password": password, "added": int(time.time()),
        "failures": 0, "last_used": 0, "cooldown_until": 0})
    save_proxies(proxies)

def get_best_proxy():
    proxies = load_proxies()
    now = time.time()
    available = []
    for p in proxies.get("proxies", []):
        if p.get("cooldown_until", 0) > now: continue
        score = p.get("failures", 0) * 100 - (now - p.get("last_used", 0))
        available.append((score, p))
    if not available: return None
    available.sort(key=lambda x: x[0])
    return available[0][1]

def mark_proxy_failure(host, port):
    proxies = load_proxies()
    for p in proxies.get("proxies", []):
        if p["host"] == host and p["port"] == port:
            p["failures"] = p.get("failures", 0) + 1
            if p["failures"] >= 3:
                p["cooldown_until"] = int(time.time() + min(300*(2**(p["failures"]-3)), 3600))
            break
    save_proxies(proxies)

def build_proxy_dict(proxy_info):
    if not proxy_info: return None
    d = {"scheme": proxy_info.get("scheme","socks5"), "hostname": proxy_info["host"],
         "port": proxy_info["port"]}
    if proxy_info.get("username"): d["username"] = proxy_info["username"]
    if proxy_info.get("password"): d["password"] = proxy_info["password"]
    return d
