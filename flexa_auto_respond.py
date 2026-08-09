#!/usr/bin/env python3
"""
Flexa Auto-Respond System
Allows Flexa to proactively join conversations when it can help.
"""

import random
import time
from typing import Optional
from chat_history import get_recent_messages, build_context_from_history

# Cooldown per chat (5 minutes between auto-responses)
_last_auto_response = {}
COOLDOWN_SECONDS = 300  # 5 minutes

# Probability of responding (10% chance)
RESPONSE_PROBABILITY = 0.10

# Keywords that trigger Flexa to consider responding
HELP_KEYWORDS = [
    "کمک", "نمی‌دونم", "نمیدونم", "چطوری", "چگونه", "چه کار کنم",
    "راهنمایی", "یاد بدید", "یاد بده", "توضیح بده", "بلدم نیستم",
    "help", "how", "what", "why", "when", "where"
]

# Topics Flexa is expert in (Gament-related)
GAMENT_KEYWORDS = [
    "تورنومنت", "تورنمنت", "مسابقه", "مسابقات", "روم", "لابی", "چک‌این",
    "ثبت‌نام", "ثبت نام", "کیف پول", "شارژ", "پرداخت", "جایزه", "رنک",
    "لیدربورد", "XP", "RP", "لول", "level", "تالار افتخارات", "قهرمان",
    "کلش رویال", "کالاف", "فورتنایت", "clash", "cod", "fortnite",
    "gament", "گیمنت", "آرنا", "براکت", "داوری", "اعتراض"
]

# Responses to avoid (don't respond to these)
IGNORE_PATTERNS = [
    "فلکسا", "الکسا", "alexa", "felxa",  # Already handled by trigger
    "/ai", "/ask", "/هوش",  # Commands
    "ممنون", "مرسی", "thanks", "thank you",  # Thanking
    "خداحافظ", "بای", "bye", "goodbye",  # Leaving
    "lol", "😂", "🤣", "haha",  # Just laughing
]


def should_respond(message: str, chat_id: int) -> bool:
    """
    Determine if Flexa should proactively respond to a message.
    
    Args:
        message: The message text
        chat_id: Chat ID for cooldown tracking
        
    Returns:
        True if Flexa should respond, False otherwise
    """
    message_lower = message.lower().strip()
    
    # Check cooldown
    last_time = _last_auto_response.get(chat_id, 0)
    if time.time() - last_time < COOLDOWN_SECONDS:
        return False
    
    # Skip if message contains ignore patterns
    for pattern in IGNORE_PATTERNS:
        if pattern.lower() in message_lower:
            return False
    
    # Skip very short messages
    if len(message.strip()) < 10:
        return False
    
    # Skip very long messages (probably not a question)
    if len(message.strip()) > 500:
        return False
    
    # Check if it's a question or needs help
    is_help_needed = any(keyword in message_lower for keyword in HELP_KEYWORDS)
    
    # Check if it's about Gament topics
    is_gament_topic = any(keyword in message_lower for keyword in GAMENT_KEYWORDS)
    
    # Must be either help-needed OR Gament topic
    if not (is_help_needed or is_gament_topic):
        return False
    
    # If it's a question mark, higher chance (30%)
    if "؟" in message or "?" in message:
        probability = 0.30
    else:
        probability = RESPONSE_PROBABILITY
    
    # Random chance
    return random.random() < probability


def mark_responded(chat_id: int):
    """Mark that Flexa responded to this chat (for cooldown)"""
    _last_auto_response[chat_id] = time.time()


def build_auto_response_prompt(message: str, chat_id: int, user_name: str) -> str:
    """
    Build a prompt for auto-response that includes context.
    
    Args:
        message: The original message
        chat_id: Chat ID for context
        user_name: Name of the user who sent the message
        
    Returns:
        Formatted prompt string
    """
    # Get recent chat history
    context = build_context_from_history(chat_id, limit=15, hours=6)
    
    prompt = f"""{context}

پیام جدید از {user_name}:
{message}

💡 دستورالعمل:
- اگر می‌تونی کمک کنی یا اطلاعات مفیدی داری، پاسخ بده
- پاسخ باید کوتاه، مفید و مرتبط با مکالمه باشه
- اگر سوال درباره Gament، تورنومنت‌ها، بازی‌ها یا گیمینگ هست، حتماً پاسخ بده
- از لحن صمیمی و دوستانه استفاده کن
- اگر مطمئن نیستی، پاسخ نده (ولی اینجا داری پاسخ میدی پس مطمئن باش!)
- پاسخ نباید بیشتر از 3-4 خط باشه

پاسخ تو (به عنوان فلکسا، دستیار هوشمند گروه):"""
    
    return prompt


def get_auto_response_style() -> dict:
    """
    Get styling options for auto-responses to make them feel natural.
    
    Returns:
        Dict with style options
    """
    styles = [
        {"prefix": "💡 ", "suffix": ""},
        {"prefix": "🎮 ", "suffix": ""},
        {"prefix": "✨ ", "suffix": ""},
        {"prefix": "", "suffix": " 🎯"},
        {"prefix": "", "suffix": " 💪"},
        {"prefix": "👋 ", "suffix": ""},
    ]
    
    return random.choice(styles)


if __name__ == "__main__":
    # Test the system
    print("Testing Flexa Auto-Respond System...")
    print("=" * 60)
    
    test_messages = [
        "چطوری تو تورنومنت ثبت‌نام کنم؟",
        "سلام بچه‌ها!",
        "کسی می‌دونه جایزه مسابقه چقدره؟",
        "ممنون از کمکت",
        "فلکسا ساعت چنده؟",
        "من نمی‌دونم چطوری کیف پولم رو شارژ کنم",
        "lol 😂",
        "فردا تورنومنت کلش رویال داریم، کی میاد؟",
    ]
    
    chat_id = 123
    
    for msg in test_messages:
        should = should_respond(msg, chat_id)
        print(f"\n📝 Message: {msg}")
        print(f"✅ Should respond: {should}")
        
        if should:
            prompt = build_auto_response_prompt(msg, chat_id, "Test User")
            print(f"🤖 Prompt preview:\n{prompt[:200]}...")
            
            # Mark as responded to test cooldown
            mark_responded(chat_id)
            
            # Next message should be blocked by cooldown
            should_next = should_respond("تست بعدی", chat_id)
            print(f"⏱️ Next message (should be False due to cooldown): {should_next}")
            break
    
    print("\n" + "=" * 60)
    print("✅ Test complete!")
