"""
AI Chat Module - Now with Flexa (Gament AI) Integration
Uses Gament AI system prompt for gaming-focused responses.
"""
import json
import requests
from typing import Optional

# Import Flexa integration
try:
    from flexa_integration import ask_flexa
    FLEXA_AVAILABLE = True
except ImportError:
    FLEXA_AVAILABLE = False
    print("⚠️ Flexa integration not available, using fallback", flush=True)

HEADERS_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"}


def ask_ai(prompt: str, user_name: Optional[str] = None) -> dict:
    """
    Ask AI a question.
    
    Args:
        prompt: User's question
        user_name: Optional user name for personalization
        
    Returns:
        Dict with 'ok', 'reply', and 'model' keys
    """
    # Try Flexa (Gament AI) first if available
    if FLEXA_AVAILABLE:
        try:
            result = ask_flexa(prompt, user_name)
            if result.get("ok"):
                return {
                    "ok": True,
                    "reply": result["reply"],
                    "model": f"Flexa ({result['model']})"
                }
        except Exception as e:
            print(f"Flexa error: {e}", flush=True)
    
    # Fallback to original endpoints
    for fn, name in [
        (_try_airforce_correct, "GPT-4o-mini"),
        (_try_duckduckgo, "GPT-4o-mini (DuckDuckGo)"),
        (_try_textsynth, "Mistral 7B"),
    ]:
        try:
            t = fn(prompt)
            if t and len(t) > 5:
                return {"ok": True, "reply": t, "model": name}
        except Exception as e:
            print(f"{name} err: {e}", flush=True)
    
    return {"ok": False, "error": "متاسفانه هم‌اکنون سرویس‌های هوش مصنوعی در دسترس نیستند، لطفاً چند دقیقه بعد امتحان کن."}


def _try_blackforest(prompt: str) -> str:
    """Try a public free gpt4 endpoint."""
    try:
        payload = {
            "messages": [
                {"role":"system","content":"You are a helpful Persian assistant. Reply in Persian (Farsi) language, friendly and concise. Do not use English unless asked."},
                {"role":"user","content":prompt}
            ],
            "model": "gpt-4o-mini",
            "stream": False,
        }
        # Use a free chat-completion proxy
        for url in [
            "https://openrouter.ai/api/v1/chat/completions",  # requires key, skip
            "https://api.airforce/chat/completions",
            "https://api.airforce/v1/chat/completions",
        ]:
            try:
                r = requests.post(url, json=payload, headers={**HEADERS_UA,"Content-Type":"application/json"}, timeout=30)
                if r.ok:
                    j = r.json()
                    c = j.get("choices",[{}])[0].get("message",{}).get("content","")
                    if c and len(c) > 5:
                        return c.strip()
            except:
                continue
    except Exception as e:
        print(f"airforce err: {e}", flush=True)
    return ""


def _try_textsynth(prompt: str) -> str:
    try:
        r = requests.post("https://textsynth.com/v1/engines/mistral_7B/completions",
                          headers=HEADERS_UA, json={"prompt":f"پاسخ فارسی به سوال زیر بده:\n{prompt}\nپاسخ:",
                                                  "max_tokens":300,"temperature":0.7}, timeout=25)
        if r.ok:
            t = r.json().get("text","").strip()
            if t: return t
    except: pass
    return ""


def _try_duckduckgo(prompt: str) -> str:
    try:
        s = requests.Session()
        s.headers.update(HEADERS_UA)
        r = s.get("https://duckduckgo.com/duckchat/v1/status", headers={"x-vqd-accept":"1"}, timeout=10)
        token = r.headers.get("x-vqd-4")
        if not token: return ""
        payload = {
            "model": "gpt-4o-mini",
            "messages": [
                {"role":"user","content":"همیشه به فارسی پاسخ بده. پاسخ‌های کوتاه و روان. " + prompt},
            ],
        }
        r = s.post("https://duckduckgo.com/duckchat/v1/chat",
                   headers={"x-vqd-4":token,"Content-Type":"application/json"},
                   json=payload, timeout=60, stream=True)
        out = ""
        for line in r.iter_lines(decode_unicode=True):
            if line and line.startswith("data: "):
                try:
                    j = json.loads(line[6:])
                    if j.get("message"): out += j["message"]
                except: pass
        return out.strip()
    except Exception as e:
        print(f"ddg err: {e}", flush=True)
    return ""


def _try_airforce_correct(prompt: str) -> str:
    # airforce api format: https://api.airforce/chat/completions works via GET too; use GET for simplicity
    try:
        r = requests.get("https://api.airforce/chat/completions",
                         params={"prompt": prompt, "model": "gpt-4o-mini", "system": "You are a helpful Persian assistant. Always respond in Farsi/Persian language. Keep answers concise and friendly."},
                         headers=HEADERS_UA, timeout=30)
        if r.ok:
            try:
                j = r.json()
                c = j.get("choices",[{}])[0].get("message",{}).get("content","")
                if c and len(c)>5: return c.strip()
            except:
                t = r.text.strip()
                if t and len(t)>5: return t
    except Exception as e:
        print(f"airforce GET err: {e}", flush=True)
    return ""
