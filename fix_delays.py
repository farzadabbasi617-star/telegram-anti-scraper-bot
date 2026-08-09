import re

# Fix delays in _execute_simple_add
with open('bot.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Better delay strategy - more conservative
old_delay = """            # Delay
            total_acc = already_added + added
            if total_acc > 80:
                await asyncio.sleep(random.randint(15, 25))
            elif total_acc > 50:
                await asyncio.sleep(random.randint(10, 18))
            else:
                await asyncio.sleep(random.randint(7, 13))"""

new_delay = """            # Delay - بهینه‌سازی شده برای جلوگیری از PEER_FLOOD
            total_acc = already_added + added
            if total_acc > 25:
                await asyncio.sleep(random.randint(12, 20))
            elif total_acc > 15:
                await asyncio.sleep(random.randint(8, 15))
            else:
                await asyncio.sleep(random.randint(5, 10))"""

content = content.replace(old_delay, new_delay)

with open('bot.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("✅ Fix 2: delay strategy improved")
