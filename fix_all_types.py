import re

with open("/home/user/repo/bot.py", "r", encoding="utf-8") as f:
    content = f.read()

# Fix all chat.type comparisons
replacements = [
    # Pattern 1: dialog.chat.type in ["supergroup", "group"]
    ('dialog.chat.type in ["supergroup", "group"]', 
     '"group" in str(dialog.chat.type).lower()'),
    
    # Pattern 2: cht.type in ["supergroup", "group"]
    ('cht.type in ["supergroup", "group"]',
     '"group" in str(cht.type).lower()'),
    
    # Pattern 3: dialog.chat.type == "channel"
    ('dialog.chat.type == "channel"',
     '"channel" in str(dialog.chat.type).lower()'),
]

for old, new in replacements:
    content = content.replace(old, new)

with open("/home/user/repo/bot.py", "w", encoding="utf-8") as f:
    f.write(content)

print("✅ All chat.type comparisons fixed!")
