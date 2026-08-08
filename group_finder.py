"""
🔍 Telegram Group Finder — searches public groups by topic
Uses Telegram search + AI relevance ranking
"""
import asyncio, time, json, os, re

SEARCH_CACHE = {}
SEARCH_CACHE_TIME = {}


async def search_telegram_groups(client, query, limit=30):
    """Search Telegram for public groups/channels. Returns list of dicts."""
    results = []
    try:
        async for chat in client.app.search_public_chats(query):
            ctype = str(chat.type).lower()
            is_channel = 'channel' in ctype and 'group' not in ctype
            results.append({
                'title': chat.title or f'Chat {chat.id}',
                'chat_id': chat.id,
                'chat_username': chat.username or '',
                'members': getattr(chat, 'members_count', 0) or 0,
                'type': 'channel' if is_channel else 'group',
            })
            if len(results) >= limit:
                break
    except Exception as e:
        print(f"search_public_chats error: {e}")
    return results


def search_via_web(query, limit=15):
    """Web search for Telegram group links. Returns list of dicts."""
    results = []
    try:
        import urllib.request, urllib.parse
        encoded = urllib.parse.quote(f'تلگرام گروه {query} site:t.me')
        url = f'https://www.google.com/search?q={encoded}&num={limit}'
        headers = {
            'User-Agent': 'Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml',
            'Accept-Language': 'en-US,en;q=0.9',
        }
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode('utf-8', errors='ignore')
        tme_links = re.findall(r'(?:t\.me|telegram\.me)/([a-zA-Z0-9_]+)', html)
        seen = set()
        for username in tme_links:
            username = username.strip().lower()
            if username in seen or len(username) < 3:
                continue
            if any(x in username.lower() for x in ['joinchat', 'share', 'addlist', 'proxy', 'socks', 'bot']):
                continue
            seen.add(username)
            results.append({
                'title': f'@{username}',
                'chat_id': None,
                'chat_username': username,
                'members': 0,
                'type': 'group',
                'source': 'web'
            })
    except Exception as e:
        print(f"web search error: {e}")
    return results


def rank_by_ai(query, groups):
    """AI relevance ranking. Falls back to keyword matching."""
    if not groups:
        return groups
    
    try:
        from chat_analyzer import smart_analyze
        scored = []
        query_lower = query.lower()
        for g in groups:
            title = g.get('title', '')
            desc = g.get('description', '')
            analysis = smart_analyze(title, desc)
            score = 0
            category = (analysis.get('category') or '').lower()
            # Direct word matches
            for word in query_lower.split():
                if word in title.lower():
                    score += 30
            # Category match
            if query_lower in category or category in query_lower:
                score += 50
            # Partial category
            for cat_word in category.split():
                if cat_word in query_lower or query_lower in cat_word:
                    score += 20
            # Size bonus
            m = g.get('members', 0)
            if m > 50000: score += 20
            elif m > 10000: score += 15
            elif m > 1000: score += 10
            # AI confidence
            score += analysis.get('confidence', 0) // 5
            g['relevance'] = score
            g['category'] = analysis.get('category', '?')
            scored.append(g)
        scored.sort(key=lambda x: -x.get('relevance', 0))
        return scored
    except Exception as e:
        print(f"AI ranking error: {e}")
    
    # Fallback keyword matching
    query_words = set(query.lower().split())
    for g in groups:
        title = g.get('title', '').lower()
        score = sum(30 for w in query_words if w in title)
        if g.get('members', 0) > 10000:
            score += 10
        g['relevance'] = score
        g['category'] = '?'
    groups.sort(key=lambda x: -x.get('relevance', 0))
    return groups


async def find_groups(query, client=None, max_results=40, use_web=True, use_ai=True):
    """Main group finder. Returns ranked list of group dicts."""
    now = time.time()
    cache_key = query.lower().strip()
    
    if cache_key in SEARCH_CACHE and (now - SEARCH_CACHE_TIME.get(cache_key, 0)) < 300:
        return SEARCH_CACHE[cache_key]
    
    all_groups = []
    
    # Telegram search
    if client:
        tg = await search_telegram_groups(client, query, limit=max_results)
        all_groups.extend(tg)
    
    # Web search
    if use_web:
        loop = asyncio.get_event_loop()
        web = await loop.run_in_executor(None, lambda: search_via_web(query, limit=15))
        all_groups.extend(web)
    
    # Deduplicate
    seen = set()
    unique = []
    for g in all_groups:
        key = str(g.get('chat_id') or g.get('chat_username', ''))
        if key not in seen:
            seen.add(key)
            unique.append(g)
    
    # AI ranking
    if use_ai and len(unique) > 1:
        unique = rank_by_ai(query, unique)
    
    SEARCH_CACHE[cache_key] = unique
    SEARCH_CACHE_TIME[cache_key] = now
    return unique
