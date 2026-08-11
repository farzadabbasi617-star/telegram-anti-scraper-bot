"""
Database module - Neon PostgreSQL
تمام داده‌های مهم اینجا ذخیره میشن که حتی با ریست رندر چیزی از بین نره.
"""
import os
import json
import time
import threading
import psycopg2
from psycopg2.extras import Json, DictCursor

DB_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://neondb_owner:npg_fLk5QncJezR8@ep-lucky-queen-adg9b8qq-pooler.c-2.us-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
)

_conn = None
_conn_lock = threading.Lock()

def get_conn():
    global _conn
    with _conn_lock:
        if _conn is None or _conn.closed:
            _conn = psycopg2.connect(DB_URL, connect_timeout=10)
            _conn.autocommit = True
        return _conn

def init_tables():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS kv_store (
            key TEXT PRIMARY KEY,
            value JSONB NOT NULL,
            updated_at BIGINT NOT NULL
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS scraped_users (
            user_id BIGINT PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            phone TEXT,
            source_group_id BIGINT,
            source_group_name TEXT,
            added_at BIGINT,
            extra JSONB DEFAULT '{}'::jsonb
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS saved_accounts_tbl (
            phone TEXT PRIMARY KEY,
            name TEXT,
            username TEXT,
            device_fp JSONB NOT NULL,
            session_data BYTEA,
            created_at BIGINT,
            last_used BIGINT,
            added_count INTEGER DEFAULT 0
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS added_history_tbl (
            group_id BIGINT,
            user_id BIGINT,
            added_at BIGINT,
            account_phone TEXT,
            PRIMARY KEY (group_id, user_id)
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS adder_limits_tbl (
            phone TEXT PRIMARY KEY,
            added INTEGER DEFAULT 0,
            last_used BIGINT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS config_tbl (
            group_id BIGINT PRIMARY KEY DEFAULT 0,
            group_name TEXT DEFAULT '',
            defense_enabled BOOLEAN DEFAULT TRUE,
            owner_phone TEXT DEFAULT ''
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS projects_tbl (
            url TEXT PRIMARY KEY,
            platform TEXT,
            full_name TEXT,
            category TEXT,
            data JSONB NOT NULL,
            found_at BIGINT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS bg_scan_state (
            id INTEGER PRIMARY KEY DEFAULT 1,
            enabled BOOLEAN DEFAULT FALSE,
            target_group_id BIGINT,
            account_phone TEXT,
            interval_minutes INTEGER DEFAULT 60,
            last_run BIGINT,
            total_found INTEGER DEFAULT 0,
            status TEXT DEFAULT 'idle'
        )
    """)
    cur.execute("""
        INSERT INTO bg_scan_state (id, enabled, status)
        VALUES (1, FALSE, 'idle')
        ON CONFLICT (id) DO NOTHING
    """)
    # 🆕 جدول تاریخچه چت‌های اسکن شده (گروه/کانال) با دسته‌بندی و درصد پیشرفت
    cur.execute("""
        CREATE TABLE IF NOT EXISTS scanned_chats_tbl (
            chat_id BIGINT PRIMARY KEY,
            chat_name TEXT NOT NULL,
            chat_type TEXT DEFAULT 'group',
            category TEXT DEFAULT '',
            total_members_estimate INTEGER DEFAULT 0,
            extracted_count INTEGER DEFAULT 0,
            progress_pct INTEGER DEFAULT 0,
            last_scan BIGINT,
            first_scan BIGINT,
            scan_count INTEGER DEFAULT 0,
            is_favorite BOOLEAN DEFAULT FALSE,
            notes TEXT DEFAULT ''
        )
    """)
    conn.commit()
    cur.close()

# ---------------- KV helpers ----------------
def kv_get(key, default=None):
    try:
        cur = get_conn().cursor()
        cur.execute("SELECT value FROM kv_store WHERE key=%s", (key,))
        row = cur.fetchone()
        cur.close()
        return row[0] if row else default
    except Exception as e:
        print(f"kv_get {key} err: {e}", flush=True)
        return default

def kv_set(key, value):
    try:
        cur = get_conn().cursor()
        cur.execute("""
            INSERT INTO kv_store (key, value, updated_at)
            VALUES (%s, %s, %s)
            ON CONFLICT (key) DO UPDATE SET value=%s, updated_at=%s
        """, (key, Json(value), int(time.time()), Json(value), int(time.time())))
        cur.close()
    except Exception as e:
        print(f"kv_set {key} err: {e}", flush=True)

# ---------------- Scraped users ----------------
def save_user(user_id, username, first_name, last_name, phone, group_id, group_name):
    try:
        cur = get_conn().cursor()
        cur.execute("""
            INSERT INTO scraped_users (user_id, username, first_name, last_name, phone, source_group_id, source_group_name, added_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (user_id) DO UPDATE SET
                username = EXCLUDED.username,
                first_name = EXCLUDED.first_name,
                last_name = EXCLUDED.last_name
        """, (int(user_id), username, first_name, last_name, phone, int(group_id or 0), group_name or "", int(time.time())))
        cur.close()
    except Exception as e:
        print(f"save_user err: {e}", flush=True)

def load_users_dict():
    try:
        cur = get_conn().cursor(cursor_factory=DictCursor)
        cur.execute("SELECT user_id, username, first_name, last_name, phone, source_group_id, source_group_name FROM scraped_users")
        out = {}
        for row in cur.fetchall():
            out[int(row["user_id"])] = {
                "user_id": int(row["user_id"]),
                "username": row["username"] or "",
                "first_name": row["first_name"] or "",
                "last_name": row["last_name"] or "",
                "phone": row["phone"] or "",
            }
        cur.close()
        return out
    except Exception as e:
        print(f"load_users err: {e}", flush=True)
        return {}

def count_users():
    try:
        cur = get_conn().cursor()
        cur.execute("SELECT COUNT(*) FROM scraped_users")
        r = cur.fetchone()[0]
        cur.close()
        return r
    except:
        return 0

def bulk_save_users(users_list, group_id, group_name):
    """Bulk insert from scrape (list of dicts)"""
    if not users_list: return
    conn = get_conn()
    cur = conn.cursor()
    rows = []
    for u in users_list:
        try:
            uid = int(u.get("user_id"))
            phone = u.get("phone", "") or ""
            rows.append((uid, u.get("username",""), u.get("first_name",""), u.get("last_name",""), phone,
                         int(group_id or 0), group_name or "", int(time.time())))
        except:
            continue
    try:
        from psycopg2.extras import execute_values
        execute_values(cur, """
            INSERT INTO scraped_users (user_id, username, first_name, last_name, phone, source_group_id, source_group_name, added_at)
            VALUES %s
            ON CONFLICT (user_id) DO UPDATE SET
                username = EXCLUDED.username,
                first_name = EXCLUDED.first_name,
                last_name = EXCLUDED.last_name,
                phone = COALESCE(NULLIF(EXCLUDED.phone, ''), scraped_users.phone)
        """, rows, page_size=500)
    except Exception as e:
        print(f"bulk_save_users err: {e}", flush=True)
    cur.close()

# ---------------- Saved accounts (with session backup) ----------------
def save_account(phone, name, username, device_fp, session_blob=None):
    try:
        cur = get_conn().cursor()
        if session_blob:
            cur.execute("""
                INSERT INTO saved_accounts_tbl (phone, name, username, device_fp, session_data, created_at, last_used)
                VALUES (%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (phone) DO UPDATE SET
                    name=EXCLUDED.name, username=EXCLUDED.username, device_fp=EXCLUDED.device_fp,
                    session_data=COALESCE(EXCLUDED.session_data, saved_accounts_tbl.session_data),
                    last_used=EXCLUDED.last_used
            """, (phone, name or "", username or "", Json(device_fp), psycopg2.Binary(session_blob) if session_blob else None, int(time.time()), int(time.time())))
        else:
            cur.execute("""
                INSERT INTO saved_accounts_tbl (phone, name, username, device_fp, created_at, last_used)
                VALUES (%s,%s,%s,%s,%s,%s)
                ON CONFLICT (phone) DO UPDATE SET
                    name=EXCLUDED.name, username=EXCLUDED.username, device_fp=EXCLUDED.device_fp,
                    last_used=EXCLUDED.last_used
            """, (phone, name or "", username or "", Json(device_fp), int(time.time()), int(time.time())))
        cur.close()
    except Exception as e:
        print(f"save_account err: {e}", flush=True)

def load_accounts():
    try:
        cur = get_conn().cursor(cursor_factory=DictCursor)
        cur.execute("SELECT phone, name, username, device_fp, added_count, last_used FROM saved_accounts_tbl ORDER BY created_at ASC")
        out = {}
        for row in cur.fetchall():
            out[row["phone"]] = {
                "name": row["name"],
                "username": row["username"],
                "device_fp": row["device_fp"],
                "added_count": row["added_count"] or 0,
                "last_used": row["last_used"],
            }
        cur.close()
        return out
    except Exception as e:
        print(f"load_accounts err: {e}", flush=True)
        return {}

def delete_account(phone):
    try:
        cur = get_conn().cursor()
        cur.execute("DELETE FROM saved_accounts_tbl WHERE phone=%s", (phone,))
        cur.close()
    except: pass

def save_session_blob(phone, blob_bytes):
    try:
        cur = get_conn().cursor()
        cur.execute("UPDATE saved_accounts_tbl SET session_data=%s, last_used=%s WHERE phone=%s",
                    (psycopg2.Binary(blob_bytes), int(time.time()), phone))
        cur.close()
    except Exception as e:
        print(f"save_session_blob err: {e}", flush=True)

def load_session_blob(phone):
    try:
        cur = get_conn().cursor()
        cur.execute("SELECT session_data FROM saved_accounts_tbl WHERE phone=%s", (phone,))
        row = cur.fetchone()
        cur.close()
        if row and row[0]:
            return bytes(row[0])
        return None
    except:
        return None

def set_owner_phone(phone):
    cur = get_conn().cursor()
    cur.execute("""
        INSERT INTO config_tbl (group_id, owner_phone)
        VALUES (0, %s)
        ON CONFLICT (group_id) DO UPDATE SET owner_phone=EXCLUDED.owner_phone
    """, (phone,))
    cur.close()

def get_owner_phone():
    try:
        cur = get_conn().cursor()
        cur.execute("SELECT owner_phone FROM config_tbl WHERE group_id=0")
        r = cur.fetchone()
        cur.close()
        return r[0] if r else ""
    except:
        return ""

# ---------------- Config (protected group) ----------------
def set_config(group_id, group_name, defense_enabled=True, owner_phone=""):
    cur = get_conn().cursor()
    cur.execute("""
        INSERT INTO config_tbl (group_id, group_name, defense_enabled, owner_phone)
        VALUES (%s,%s,%s,%s)
        ON CONFLICT (group_id) DO UPDATE SET
            group_name=EXCLUDED.group_name,
            defense_enabled=EXCLUDED.defense_enabled,
            owner_phone=COALESCE(NULLIF(EXCLUDED.owner_phone,''), config_tbl.owner_phone)
    """, (int(group_id), group_name, defense_enabled, owner_phone))
    cur.close()

def get_config():
    try:
        cur = get_conn().cursor(cursor_factory=DictCursor)
        cur.execute("SELECT group_id, group_name, defense_enabled, owner_phone FROM config_tbl WHERE group_id != 0 ORDER BY group_id DESC LIMIT 1")
        r = cur.fetchone()
        cur.close()
        if r:
            return {
                "group_id": int(r["group_id"]),
                "group_name": r["group_name"] or "",
                "defense_enabled": bool(r["defense_enabled"]),
                "owner_phone": r["owner_phone"] or "",
            }
        return {"group_id": 0, "group_name": "", "defense_enabled": True, "owner_phone": ""}
    except Exception as e:
        print(f"get_config err: {e}", flush=True)
        return {"group_id": 0, "group_name": "", "defense_enabled": True, "owner_phone": ""}

# ---------------- Adder limits ----------------
def get_adder_limits():
    try:
        cur = get_conn().cursor(cursor_factory=DictCursor)
        cur.execute("SELECT phone, added, last_used, limitation_type, limitation_until FROM adder_limits_tbl")
        out = {}
        for r in cur.fetchall():
            out[r["phone"]] = {
                "added": r["added"] or 0,
                "last_used": r["last_used"],
                "limitation_type": r.get("limitation_type"),
                "limitation_until": r.get("limitation_until") or 0
            }
        cur.close()
        return out
    except:
        return {}

def set_adder_limit(phone, added, limitation_type=None, limitation_until=0):
    cur = get_conn().cursor()
    cur.execute("""
        INSERT INTO adder_limits_tbl (phone, added, last_used, limitation_type, limitation_until)
        VALUES (%s,%s,%s,%s,%s)
        ON CONFLICT (phone) DO UPDATE SET 
            added=EXCLUDED.added, 
            last_used=EXCLUDED.last_used,
            limitation_type=EXCLUDED.limitation_type,
            limitation_until=EXCLUDED.limitation_until
    """, (phone, int(added), int(time.time()), limitation_type, int(limitation_until)))
    cur.close()
    # Also update account table count
    try:
        cur2 = get_conn().cursor()
        cur2.execute("UPDATE saved_accounts_tbl SET added_count=%s, last_used=%s WHERE phone=%s", (int(added), int(time.time()), phone))
        cur2.close()
    except: pass

def reset_adder_limits():
    cur = get_conn().cursor()
    cur.execute("UPDATE adder_limits_tbl SET added=0")
    cur.close()

# ---------------- Added history ----------------

def clear_account_limitation(phone):
    """Clear limitation for an account"""
    cur = get_conn().cursor()
    cur.execute("""
        UPDATE adder_limits_tbl 
        SET limitation_type=NULL, limitation_until=0 
        WHERE phone=%s
    """, (phone,))
    cur.close()

def get_account_status(phone):
    """Get detailed status for an account"""
    limits = get_adder_limits()
    info = limits.get(phone, {})
    
    limitation_type = info.get("limitation_type")
    limitation_until = info.get("limitation_until", 0)
    
    # Check if limitation has expired
    if limitation_type and limitation_until > 0:
        if time.time() >= limitation_until:
            # Limitation expired, clear it
            clear_account_limitation(phone)
            limitation_type = None
            limitation_until = 0
    
    return {
        "phone": phone,
        "added": info.get("added", 0),
        "last_used": info.get("last_used", 0),
        "limitation_type": limitation_type,
        "limitation_until": limitation_until,
        "is_limited": limitation_type is not None,
        "remaining_seconds": max(0, limitation_until - time.time()) if limitation_until > 0 else 0
    }

def mark_added(group_id, user_id, phone):
    try:
        cur = get_conn().cursor()
        cur.execute("""
            INSERT INTO added_history_tbl (group_id, user_id, added_at, account_phone)
            VALUES (%s,%s,%s,%s)
            ON CONFLICT (group_id, user_id) DO NOTHING
        """, (int(group_id), int(user_id), int(time.time()), phone))
        cur.close()
    except Exception as e:
        print(f"mark_added err: {e}", flush=True)

def is_added(group_id, user_id):
    try:
        cur = get_conn().cursor()
        cur.execute("SELECT 1 FROM added_history_tbl WHERE group_id=%s AND user_id=%s", (int(group_id), int(user_id)))
        r = cur.fetchone()
        cur.close()
        return r is not None
    except:
        return False

def count_added(group_id=None):
    try:
        cur = get_conn().cursor()
        if group_id:
            cur.execute("SELECT COUNT(*) FROM added_history_tbl WHERE group_id=%s", (int(group_id),))
        else:
            cur.execute("SELECT COUNT(*) FROM added_history_tbl")
        r = cur.fetchone()[0]
        cur.close()
        return r
    except:
        return 0

# ---------------- BG scan state ----------------
def set_bg_scan(enabled, target_group_id=None, account_phone=None, interval_minutes=60):
    cur = get_conn().cursor()
    cur.execute("""
        UPDATE bg_scan_state SET
            enabled=%s,
            target_group_id=COALESCE(%s, target_group_id),
            account_phone=COALESCE(%s, account_phone),
            interval_minutes=COALESCE(%s, interval_minutes)
        WHERE id=1
    """, (bool(enabled), target_group_id, account_phone, interval_minutes))
    cur.close()

def get_bg_scan():
    try:
        cur = get_conn().cursor(cursor_factory=DictCursor)
        cur.execute("SELECT enabled, target_group_id, account_phone, interval_minutes, last_run, total_found, status FROM bg_scan_state WHERE id=1")
        r = cur.fetchone()
        cur.close()
        if not r:
            return {"enabled":False,"target_group_id":0,"account_phone":"","interval_minutes":60,"last_run":0,"total_found":0,"status":"idle"}
        return dict(r)
    except:
        return {"enabled":False,"target_group_id":0,"account_phone":"","interval_minutes":60,"last_run":0,"total_found":0,"status":"idle"}

def mark_bg_run(total_new):
    cur = get_conn().cursor()
    cur.execute("UPDATE bg_scan_state SET last_run=%s, total_found = total_found + %s, status='idle' WHERE id=1",
                (int(time.time()), int(total_new or 0)))
    cur.close()

def set_bg_status(status):
    try:
        cur = get_conn().cursor()
        cur.execute("UPDATE bg_scan_state SET status=%s WHERE id=1", (status,))
        cur.close()
    except: pass

# ---------------- Projects (project finder) ----------------
def save_project(url, platform, full_name, category, data):
    try:
        cur = get_conn().cursor()
        cur.execute("""
            INSERT INTO projects_tbl (url, platform, full_name, category, data, found_at)
            VALUES (%s,%s,%s,%s,%s,%s)
            ON CONFLICT (url) DO NOTHING
        """, (url, platform, full_name, category, Json(data), int(time.time())))
        cur.close()
    except Exception as e:
        print(f"save_project err: {e}", flush=True)

def load_projects(category=None):
    try:
        cur = get_conn().cursor(cursor_factory=DictCursor)
        if category:
            cur.execute("SELECT data FROM projects_tbl WHERE category=%s ORDER BY (data->>'stars')::int DESC", (category,))
        else:
            cur.execute("SELECT data FROM projects_tbl ORDER BY found_at DESC")
        out = []
        for r in cur.fetchall():
            d = r["data"]
            if d: out.append(d)
        cur.close()
        return out
    except:
        return []

def count_projects():
    try:
        cur = get_conn().cursor()
        cur.execute("SELECT COUNT(*) FROM projects_tbl")
        r = cur.fetchone()[0]
        cur.close()
        return r
    except:
        return 0

def clear_projects():
    cur = get_conn().cursor()
    cur.execute("TRUNCATE projects_tbl")
    cur.close()

# ---------------- Sync JSON->DB on first run ----------------
def migrate_json_to_db():
    """Import existing JSON files into DB on first run (one-shot)."""
    import glob
    try:
        # scraped users
        import os.path
        if os.path.exists("scraped_users.json"):
            with open("scraped_users.json", "r", encoding="utf-8") as f:
                d = json.load(f)
            users = d.get("users", []) or []
            gid = d.get("group_id", 0)
            gname = d.get("group_name", "")
            bulk_save_users(users, gid, gname)
            print(f"[migrate] imported {len(users)} users from JSON", flush=True)
        # saved accounts
        if os.path.exists("saved_accounts.json"):
            with open("saved_accounts.json","r",encoding="utf-8") as f:
                accs = json.load(f)
            for phone, info in accs.items():
                save_account(phone, info.get("name",""), info.get("username",""), info.get("device_fp"))
            print(f"[migrate] imported {len(accs)} accounts", flush=True)
        # adder limits
        if os.path.exists("adder_limits.json"):
            with open("adder_limits.json","r",encoding="utf-8") as f:
                lim = json.load(f)
            for phone, info in lim.items():
                set_adder_limit(phone, info.get("added",0))
        # config
        if os.path.exists("config.json"):
            with open("config.json","r",encoding="utf-8") as f:
                c = json.load(f)
            if c.get("group_id"):
                set_config(c["group_id"], c.get("group_name",""), c.get("defense_enabled",True))
    except Exception as e:
        print(f"migrate err: {e}", flush=True)


# Initialize at import
init_tables()



# ---------------- Scanned Chats History (group/channel tracker) ----------------
def upsert_scanned_chat(chat_id, chat_name, chat_type="group", category="",
                         total_members=0, extracted_new=0, progress_pct=None):
    """Register or update a chat in scan history"""
    try:
        cur = get_conn().cursor()
        existing = get_scanned_chat(chat_id)
        now = int(time.time())
        if existing:
            new_extracted = (existing.get("extracted_count") or 0) + int(extracted_new or 0)
            new_pct = progress_pct if progress_pct is not None else existing.get("progress_pct") or 0
            new_total = int(total_members or 0) or existing.get("total_members_estimate") or 0
            new_cat = category if category else existing.get("category") or ""
            cur.execute("""
                UPDATE scanned_chats_tbl SET
                    chat_name=%s, chat_type=%s, category=%s,
                    total_members_estimate=%s, extracted_count=%s, progress_pct=%s,
                    last_scan=%s, scan_count=COALESCE(scan_count,0)+1
                WHERE chat_id=%s
            """, (chat_name, chat_type, new_cat, new_total, new_extracted, new_pct,
                  now, int(chat_id)))
        else:
            cur.execute("""
                INSERT INTO scanned_chats_tbl
                (chat_id, chat_name, chat_type, category, total_members_estimate,
                 extracted_count, progress_pct, last_scan, first_scan, scan_count)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,1)
            """, (int(chat_id), chat_name, chat_type, category or "",
                  int(total_members or 0), int(extracted_new or 0),
                  int(progress_pct or 0), now, now))
        cur.close()
    except Exception as e:
        print(f"upsert_scanned_chat err: {e}", flush=True)


def get_scanned_chats(category=None):
    """Get list of scanned chats, optionally filtered by category"""
    try:
        cur = get_conn().cursor(cursor_factory=DictCursor)
        if category:
            cur.execute("SELECT * FROM scanned_chats_tbl WHERE category=%s ORDER BY last_scan DESC", (category,))
        else:
            cur.execute("SELECT * FROM scanned_chats_tbl ORDER BY is_favorite DESC, last_scan DESC")
        rows = cur.fetchall()
        cur.close()
        return [dict(r) for r in rows]
    except Exception as e:
        print(f"get_scanned_chats err: {e}", flush=True)
        return []


def get_scanned_chat(chat_id):
    try:
        cur = get_conn().cursor(cursor_factory=DictCursor)
        cur.execute("SELECT * FROM scanned_chats_tbl WHERE chat_id=%s", (int(chat_id),))
        r = cur.fetchone()
        cur.close()
        return dict(r) if r else None
    except:
        return None


def update_chat_category(chat_id, category):
    try:
        cur = get_conn().cursor()
        cur.execute("UPDATE scanned_chats_tbl SET category=%s WHERE chat_id=%s", (category, int(chat_id)))
        cur.close()
    except: pass


def update_chat_progress(chat_id, extracted_new, progress_pct):
    cur = get_conn().cursor()
    cur.execute("""
        UPDATE scanned_chats_tbl SET
            extracted_count = COALESCE(extracted_count,0) + %s,
            progress_pct = %s,
            last_scan = %s
        WHERE chat_id = %s
    """, (int(extracted_new), int(progress_pct or 0), int(time.time()), int(chat_id)))
    cur.close()


def get_users_by_source(source_chat_id=None, category=None, limit=2000, offset=0):
    """Get users filtered by source chat or category"""
    try:
        cur = get_conn().cursor(cursor_factory=DictCursor)
        if category:
            cur.execute("""
                SELECT u.user_id, u.username, u.first_name, u.last_name, u.source_group_id, u.source_group_name
                FROM scraped_users u
                JOIN scanned_chats_tbl c ON u.source_group_id = c.chat_id
                WHERE c.category = %s
                ORDER BY u.added_at DESC LIMIT %s OFFSET %s
            """, (category, limit, offset))
        elif source_chat_id:
            cur.execute("""
                SELECT user_id, username, first_name, last_name, source_group_id, source_group_name
                FROM scraped_users WHERE source_group_id=%s
                ORDER BY added_at DESC LIMIT %s OFFSET %s
            """, (int(source_chat_id), limit, offset))
        else:
            cur.execute("""
                SELECT user_id, username, first_name, last_name, source_group_id, source_group_name
                FROM scraped_users ORDER BY added_at DESC LIMIT %s OFFSET %s
            """, (limit, offset))
        rows = cur.fetchall()
        cur.close()
        return [dict(r) for r in rows]
    except Exception as e:
        print(f"get_users_by_source err: {e}", flush=True)
        return []


def count_users_by_source(source_chat_id=None, category=None):
    try:
        cur = get_conn().cursor()
        if category:
            cur.execute("""
                SELECT COUNT(*) FROM scraped_users u
                JOIN scanned_chats_tbl c ON u.source_group_id = c.chat_id WHERE c.category=%s
            """, (category,))
        elif source_chat_id:
            cur.execute("SELECT COUNT(*) FROM scraped_users WHERE source_group_id=%s", (int(source_chat_id),))
        else:
            cur.execute("SELECT COUNT(*) FROM scraped_users")
        r = cur.fetchone()[0]
        cur.close()
        return r
    except:
        return 0


def get_all_categories():
    try:
        cur = get_conn().cursor()
        cur.execute("SELECT DISTINCT category FROM scanned_chats_tbl WHERE category IS NOT NULL AND category != '' ORDER BY category")
        return [r[0] for r in cur.fetchall()]
    except:
        return []


def get_category_stats():
    try:
        cur = get_conn().cursor(cursor_factory=DictCursor)
        cur.execute("""
            SELECT category, COUNT(*) as chat_count,
                   COALESCE(SUM(extracted_count),0) as total_users
            FROM scanned_chats_tbl WHERE category != ''
            GROUP BY category ORDER BY total_users DESC
        """)
        return [dict(r) for r in cur.fetchall()]
    except:
        return []


def delete_scanned_chat(chat_id):
    try:
        cur = get_conn().cursor()
        cur.execute("DELETE FROM scanned_chats_tbl WHERE chat_id=%s", (int(chat_id),))
        cur.close()
    except: pass


def toggle_chat_favorite(chat_id):
    try:
        cur = get_conn().cursor()
        cur.execute("UPDATE scanned_chats_tbl SET is_favorite = NOT COALESCE(is_favorite, FALSE) WHERE chat_id=%s", (int(chat_id),))
        cur.close()
    except: pass

# ---------------- Favorites / bookmarks ----------------
def fav_add(url):
    try:
        cur = get_conn().cursor()
        cur.execute("INSERT INTO kv_store (key, value, updated_at) VALUES ('favorites', %s, %s) ON CONFLICT (key) DO NOTHING",
                    (Json([]), int(time.time())))
        cur.execute("UPDATE kv_store SET value = value || %s::jsonb WHERE key='favorites' AND NOT value @> %s::jsonb",
                    (Json([url]), Json([url])))
        cur.close()
    except Exception as e:
        print(f"fav_add err: {e}", flush=True)

def fav_remove(url):
    try:
        cur = get_conn().cursor()
        cur.execute("UPDATE kv_store SET value = (SELECT jsonb_agg(elem) FROM jsonb_array_elements(value) elem WHERE elem::text <> %s::text) WHERE key='favorites'",
                    (json.dumps(url),))
        cur.close()
    except Exception as e:
        print(f"fav_remove err: {e}", flush=True)

def fav_list():
    v = kv_get("favorites", []) or []
    return list(v)

def is_fav(url):
    return url in fav_list()


def delete_user(user_id: int) -> bool:
    try:
        cur = get_conn().cursor()
        cur.execute("DELETE FROM scraped_users WHERE user_id=%s", (int(user_id),))
        deleted = cur.rowcount > 0
        cur.close()
        return deleted
    except: return False


def delete_users_bulk(user_ids: list) -> int:
    if not user_ids: return 0
    try:
        cur = get_conn().cursor()
        cur.execute("DELETE FROM scraped_users WHERE user_id = ANY(%s)", (list(map(int, user_ids)),))
        deleted = cur.rowcount
        cur.close()
        return deleted
    except: return 0
