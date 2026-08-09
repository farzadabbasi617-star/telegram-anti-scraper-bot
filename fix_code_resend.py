import re

with open('bot.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find and fix the PhoneCodeExpired handler
old_code = '''        except (PhoneCodeExpired, PhoneCodeInvalid):
            try:
                sent = await acc_client.app.send_code(phone)
                atk_state["hash"] = sent.phone_code_hash
                await st.edit_text("⏰ کد قبلی منقضی شده بود — کد جدید ارسال شد!\\n📱 کد ۵ رقمی جدید رو بفرست:")
            except Exception as e2:
                await st.edit_text(f"❌ خطا در ارسال مجدد کد: {str(e2)[:200]}\\nلطفا از منو دوباره شروع کنید.")
                atk_state.clear()
            return'''

new_code = '''        except (PhoneCodeExpired, PhoneCodeInvalid):
            try:
                sent = await acc_client.app.send_code(phone)
                atk_state["hash"] = sent.phone_code_hash
                # Use reply instead of edit to avoid MESSAGE_NOT_MODIFIED
                new_msg = await st.reply_text(
                    "⏰ **کد قبلی منقضی شده بود**\\n\\n"
                    "✅ کد جدید ارسال شد!\\n"
                    "📱 لطفاً کد ۵ رقمی جدید رو بفرست:\\n\\n"
                    "⏱️ ۵ دقیقه فرصت داری"
                )
                atk_state["st"] = new_msg  # Update st to new message
            except Exception as e2:
                await st.reply_text(f"❌ خطا در ارسال مجدد کد: {str(e2)[:200]}\\nلطفا از منو دوباره شروع کنید.")
                atk_state.clear()
            return'''

if old_code in content:
    content = content.replace(old_code, new_code)
    print("✅ Fixed: PhoneCodeExpired handler now uses reply instead of edit")
else:
    print("⚠️ Could not find PhoneCodeExpired handler")

with open('bot.py', 'w', encoding='utf-8') as f:
    f.write(content)

