#!/usr/bin/env python3
"""
Chat History Manager for Flexa AI
Stores recent messages and provides context for better responses.
"""

import sqlite3
import time
from typing import List, Dict, Optional
from datetime import datetime, timedelta

DB_PATH = "chat_history.db"
MAX_MESSAGES = 100  # Keep last 100 messages per group


def init_db():
    """Initialize the chat history database"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            username TEXT,
            first_name TEXT,
            message TEXT NOT NULL,
            timestamp INTEGER NOT NULL,
            is_question INTEGER DEFAULT 0
        )
    """)
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_chat_timestamp 
        ON chat_history(chat_id, timestamp)
    """)
    
    conn.commit()
    conn.close()
    print("✅ Chat history database initialized", flush=True)


def save_message(
    chat_id: int,
    user_id: int,
    username: Optional[str],
    first_name: Optional[str],
    message: str,
    is_question: bool = False
):
    """Save a message to the chat history"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Save the message
    cursor.execute("""
        INSERT INTO chat_history 
        (chat_id, user_id, username, first_name, message, timestamp, is_question)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (chat_id, user_id, username, first_name, message, int(time.time()), int(is_question)))
    
    # Clean old messages (keep only last MAX_MESSAGES)
    cursor.execute("""
        DELETE FROM chat_history 
        WHERE chat_id = ? AND id NOT IN (
            SELECT id FROM chat_history 
            WHERE chat_id = ? 
            ORDER BY timestamp DESC 
            LIMIT ?
        )
    """, (chat_id, chat_id, MAX_MESSAGES))
    
    conn.commit()
    conn.close()


def get_recent_messages(chat_id: int, limit: int = 20, hours: int = 24) -> List[Dict]:
    """
    Get recent messages from a chat.
    
    Args:
        chat_id: Chat ID
        limit: Maximum number of messages to return
        hours: Only get messages from last N hours
        
    Returns:
        List of message dictionaries
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cutoff = int(time.time()) - (hours * 3600)
    
    cursor.execute("""
        SELECT user_id, username, first_name, message, timestamp, is_question
        FROM chat_history
        WHERE chat_id = ? AND timestamp > ?
        ORDER BY timestamp DESC
        LIMIT ?
    """, (chat_id, cutoff, limit))
    
    messages = []
    for row in cursor.fetchall():
        messages.append({
            "user_id": row[0],
            "username": row[1],
            "first_name": row[2],
            "message": row[3],
            "timestamp": row[4],
            "is_question": bool(row[5])
        })
    
    conn.close()
    
    # Reverse to chronological order
    return list(reversed(messages))


def build_context_from_history(chat_id: int, limit: int = 15, hours: int = 12) -> str:
    """
    Build a context string from recent chat history.
    
    Args:
        chat_id: Chat ID
        limit: Maximum number of messages
        hours: Only get messages from last N hours
        
    Returns:
        Formatted context string
    """
    messages = get_recent_messages(chat_id, limit, hours)
    
    if not messages:
        return ""
    
    context_lines = ["📜 مکالمات اخیر گروه:", ""]
    
    for msg in messages:
        name = msg["first_name"] or msg["username"] or "کاربر"
        time_str = datetime.fromtimestamp(msg["timestamp"]).strftime("%H:%M")
        context_lines.append(f"[{time_str}] {name}: {msg['message'][:200]}")
    
    context_lines.append("")
    context_lines.append("💡 با توجه به مکالمات بالا، به سوال کاربر پاسخ بده.")
    
    return "\n".join(context_lines)


def get_chat_stats(chat_id: int) -> Dict:
    """Get statistics about a chat's history"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Total messages
    cursor.execute("SELECT COUNT(*) FROM chat_history WHERE chat_id = ?", (chat_id,))
    total = cursor.fetchone()[0]
    
    # Messages in last 24h
    cutoff_24h = int(time.time()) - 86400
    cursor.execute(
        "SELECT COUNT(*) FROM chat_history WHERE chat_id = ? AND timestamp > ?",
        (chat_id, cutoff_24h)
    )
    last_24h = cursor.fetchone()[0]
    
    # Questions asked
    cursor.execute(
        "SELECT COUNT(*) FROM chat_history WHERE chat_id = ? AND is_question = 1",
        (chat_id,)
    )
    questions = cursor.fetchone()[0]
    
    # Most active users
    cursor.execute("""
        SELECT first_name, COUNT(*) as count
        FROM chat_history
        WHERE chat_id = ?
        GROUP BY user_id
        ORDER BY count DESC
        LIMIT 5
    """, (chat_id,))
    top_users = cursor.fetchall()
    
    conn.close()
    
    return {
        "total_messages": total,
        "messages_24h": last_24h,
        "questions_asked": questions,
        "top_users": [{"name": row[0], "count": row[1]} for row in top_users]
    }


def is_question(text: str) -> bool:
    """Detect if a message is a question"""
    question_markers = ["؟", "?", "چطور", "چگونه", "چرا", "کی", "کجا", "چی", "چه"]
    text_lower = text.lower()
    return any(marker in text_lower for marker in question_markers)


# Initialize database on import
init_db()


if __name__ == "__main__":
    # Test the module
    print("Testing Chat History Manager...")
    
    # Save some test messages
    save_message(
        chat_id=123,
        user_id=456,
        username="test_user",
        first_name="Test",
        message="سلام بچه‌ها!"
    )
    
    save_message(
        chat_id=123,
        user_id=789,
        username="gamer1",
        first_name="Ali",
        message="چطوری تو تورنومنت ثبت‌نام کنم؟",
        is_question=True
    )
    
    # Get recent messages
    messages = get_recent_messages(123, limit=10)
    print(f"\n📜 Recent messages: {len(messages)}")
    for msg in messages:
        print(f"  [{msg['timestamp']}] {msg['first_name']}: {msg['message']}")
    
    # Build context
    context = build_context_from_history(123)
    print(f"\n📝 Context:\n{context}")
    
    # Get stats
    stats = get_chat_stats(123)
    print(f"\n📊 Stats: {stats}")
