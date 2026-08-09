"""
📊 Database Statistics Checker
================================
این اسکریپت آمار دیتابیس رو نشون میده.

نحوه استفاده:
1. این فایل رو روی سرور اجرا کن: python check_db_stats.py
2. آمار کامل رو می‌بینی
"""

import psycopg2
import os
from collections import Counter

# ═══════════════════════════════════════════════════════
# تنظیمات دیتابیس - از environment variables بخون
# ═══════════════════════════════════════════════════════
DATABASE_URL = os.environ.get("DATABASE_URL", "")

if not DATABASE_URL:
    print("❌ DATABASE_URL environment variable پیدا نشد!")
    print("لطفاً اول export کن:")
    print("export DATABASE_URL='postgresql://...'")
    exit(1)

try:
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    
    print("=" * 60)
    print("📊 آمار دیتابیس")
    print("=" * 60)
    
    # ── Total users ──
    cursor.execute("SELECT COUNT(*) FROM scraped_users")
    total = cursor.fetchone()[0]
    print(f"\n👥 مجموع کاربران: {total:,}")
    
    # ── Users with phone numbers ──
    cursor.execute("SELECT COUNT(*) FROM scraped_users WHERE phone IS NOT NULL AND phone != ''")
    with_phone = cursor.fetchone()[0]
    print(f"📱 با شماره تلفن: {with_phone:,} ({with_phone*100//total}%)")
    
    # ── Users with username ──
    cursor.execute("SELECT COUNT(*) FROM scraped_users WHERE username IS NOT NULL AND username != ''")
    with_username = cursor.fetchone()[0]
    print(f"🏷️ با username: {with_username:,} ({with_username*100//total}%)")
    
    # ── Users with only ID ──
    cursor.execute("""
        SELECT COUNT(*) FROM scraped_users 
        WHERE (phone IS NULL OR phone = '') 
        AND (username IS NULL OR username = '')
    """)
    id_only = cursor.fetchone()[0]
    print(f"🆔 فقط ID: {id_only:,} ({id_only*100//total}%)")
    
    # ── Breakdown by source ──
    print("\n" + "=" * 60)
    print("📂 تفکیک بر اساس منبع")
    print("=" * 60)
    
    cursor.execute("""
        SELECT 
            COALESCE(source_group_name, 'نامشخص') as source,
            COUNT(*) as count,
            SUM(CASE WHEN phone IS NOT NULL AND phone != '' THEN 1 ELSE 0 END) as with_phone
        FROM scraped_users
        GROUP BY source_group_name
        ORDER BY count DESC
        LIMIT 20
    """)
    
    for source, count, phone_count in cursor.fetchall():
        print(f"  📁 {source[:40]}: {count:,} نفر ({phone_count} با شماره)")
    
    # ── Sample data ──
    print("\n" + "=" * 60)
    print("🔍 نمونه داده‌ها")
    print("=" * 60)
    
    cursor.execute("""
        SELECT user_id, username, phone, first_name, last_name, source_group_name
        FROM scraped_users
        WHERE phone IS NOT NULL AND phone != ''
        LIMIT 5
    """)
    
    print("\n📱 نمونه کاربران با شماره:")
    for row in cursor.fetchall():
        uid, uname, phone, fname, lname, source = row
        print(f"  ID: {uid} | {fname} {lname} | @{uname or '-'} | {phone} | from: {source}")
    
    cursor.execute("""
        SELECT user_id, username, first_name, last_name, source_group_name
        FROM scraped_users
        WHERE (phone IS NULL OR phone = '') AND username IS NOT NULL AND username != ''
        LIMIT 5
    """)
    
    print("\n🏷️ نمونه کاربران با username (بدون شماره):")
    for row in cursor.fetchall():
        uid, uname, fname, lname, source = row
        print(f"  ID: {uid} | {fname} {lname} | @{uname} | from: {source}")
    
    # ── Quality analysis ──
    print("\n" + "=" * 60)
    print("📈 تحلیل کیفیت")
    print("=" * 60)
    
    # High quality: phone + username
    cursor.execute("""
        SELECT COUNT(*) FROM scraped_users 
        WHERE phone IS NOT NULL AND phone != '' 
        AND username IS NOT NULL AND username != ''
    """)
    high_quality = cursor.fetchone()[0]
    
    # Medium quality: phone OR username
    cursor.execute("""
        SELECT COUNT(*) FROM scraped_users 
        WHERE (phone IS NOT NULL AND phone != '' 
        OR username IS NOT NULL AND username != '')
        AND NOT (phone IS NOT NULL AND phone != '' 
        AND username IS NOT NULL AND username != '')
    """)
    medium_quality = cursor.fetchone()[0]
    
    # Low quality: only ID
    low_quality = id_only
    
    print(f"  ⭐⭐⭐ کیفیت بالا (شماره + username): {high_quality:,} ({high_quality*100//total}%)")
    print(f"  ⭐⭐ کیفیت متوسط (شماره یا username): {medium_quality:,} ({medium_quality*100//total}%)")
    print(f"  ⭐ کیفیت پایین (فقط ID): {low_quality:,} ({low_quality*100//total}%)")
    
    # ── Recommendations ──
    print("\n" + "=" * 60)
    print("💡 پیشنهادها")
    print("=" * 60)
    
    print(f"\n✅ کاربران قابل اد (تخمین):")
    print(f"  📱 با شماره: ~{int(with_phone * 0.7):,} نفر (70% موفقیت)")
    print(f"  🏷️ با username: ~{int((with_username - high_quality) * 0.4):,} نفر (40% موفقیت)")
    print(f"  🆔 فقط ID: ~{int(id_only * 0.15):,} نفر (15% موفقیت)")
    
    total_addable = int(with_phone * 0.7) + int((with_username - high_quality) * 0.4) + int(id_only * 0.15)
    print(f"\n🎯 مجموع قابل اد: ~{total_addable:,} نفر")
    
    print(f"\n⏱️ زمان تخمینی (با 10 اکانت، 50 نفر/روز):")
    days_needed = total_addable / (10 * 50)
    print(f"  {days_needed:.1f} روز")
    
    cursor.close()
    conn.close()
    
    print("\n" + "=" * 60)
    print("✅ تحلیل کامل شد!")
    print("=" * 60)

except Exception as e:
    print(f"❌ خطا: {e}")
    import traceback
    traceback.print_exc()
