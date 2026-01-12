import telebot
from telebot import types
import random
import time
import json
import os
from datetime import datetime, timedelta
import threading
from flask import Flask, request

TOKEN = "8081419751:AAFdgStEJnCZ3mWq7x4fhn2DwAMxQthyCdo"
bot = telebot.TeleBot(TOKEN)

# Hosting uchun Flask
app = Flask(__name__)

# Webhook URL (o'z hosting manzilingizni qo'ying)
WEBHOOK_URL = f"https://your-domain.com/{TOKEN}"

# Admin va kanal sozlamalari
ADMIN_IDS = [5762882070]
CHANNEL_USERNAME = "@TalabaQuiz"
CHANNEL_ID = -1003351063981

# Ma'lumotlar fayli
DATA_FILE = "quiz_data.json"

# Foydalanuvchilar ma'lumotlari
user_data = {}

# ==================== FLASK WEBHOOK ====================

@app.route(f'/{TOKEN}', methods=['POST'])
def webhook():
    """Telegram webhook"""
    json_str = request.get_data().decode('UTF-8')
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return 'OK', 200

@app.route('/')
def index():
    """Bosh sahifa"""
    return 'Quiz Bot is running! ✅'

@app.route('/stats')
def stats():
    """Statistika"""
    return f'Users: {len(user_data)} | Groups: {sum(1 for d in user_data.values() if d.get("is_group"))}'

# ==================== MA'LUMOTLARNI BOSHQARISH ====================

def load_data():
    """JSON fayldan ma'lumotlarni yuklash"""
    global user_data
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                user_data = json.load(f)
            print(f"✅ Ma'lumotlar yuklandi: {len(user_data)}")
            clean_old_data()
        else:
            user_data = {}
            print("📁 Yangi baza yaratildi")
    except Exception as e:
        print(f"❌ Ma'lumotlar yuklashda xatolik: {e}")
        user_data = {}

def save_data():
    """JSON faylga ma'lumotlarni saqlash"""
    try:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(user_data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"❌ Saqlashda xatolik: {e}")

def clean_old_data():
    """1 kundan eski ma'lumotlarni tozalash"""
    today = datetime.now().date()
    users_to_remove = []
    
    for user_id, data in user_data.items():
        last_active = data.get('last_active')
        if last_active:
            try:
                last_date = datetime.strptime(last_active, '%Y-%m-%d').date()
                if (today - last_date).days >= 1:
                    users_to_remove.append(user_id)
            except:
                users_to_remove.append(user_id)
        else:
            users_to_remove.append(user_id)
    
    for user_id in users_to_remove:
        del user_data[user_id]
    
    if users_to_remove:
        save_data()
        print(f"🗑️ Tozalandi: {len(users_to_remove)}")

def update_last_active(user_id):
    """Foydalanuvchining oxirgi faollik sanasini yangilash"""
    user_id = str(user_id)
    if user_id not in user_data:
        user_data[user_id] = {}
    
    user_data[user_id]['last_active'] = str(datetime.now().date())
    save_data()

# ==================== FUNKSIYALAR ====================

def check_subscription(user_id):
    """Foydalanuvchi kanalga obuna bo'lganligini tekshirish"""
    if not CHANNEL_ID:
        return True
    try:
        member = bot.get_chat_member(CHANNEL_ID, user_id)
        return member.status in ['member', 'administrator', 'creator']
    except:
        return False

def is_admin(user_id):
    """Admin ekanligini tekshirish"""
    return user_id in ADMIN_IDS

def subscription_required(func):
    """Majburiy obuna dekoratori"""
    def wrapper(message):
        user_id = message.from_user.id
        
        if is_admin(user_id):
            return func(message)
        
        if not check_subscription(user_id):
            markup = types.InlineKeyboardMarkup()
            markup.add(
                types.InlineKeyboardButton(
                    "📢 Kanalga obuna bo'lish",
                    url=f"https://t.me/{CHANNEL_USERNAME[1:]}"
                )
            )
            markup.add(
                types.InlineKeyboardButton("✅ Obuna bo'ldim", callback_data="check_sub")
            )
            
            bot.send_message(
                message.chat.id,
                f"⚠️ <b>Botdan foydalanish uchun kanalimizga obuna bo'ling!</b>\n\n"
                f"📢 Kanal: {CHANNEL_USERNAME}\n\n"
                f"Obuna bo'lgandan keyin '✅ Obuna bo'ldim' tugmasini bosing.",
                parse_mode='HTML',
                reply_markup=markup
            )
            return
        
        return func(message)
    return wrapper

def is_group_chat(chat_id):
    """Guruh yoki superguruh ekanligini tekshirish"""
    return chat_id < 0

# ==================== QUIZ PARSER ====================

class QuizParser:
    def parse_format1(self, text):
        """Eski format: ? savol, + to'g'ri, - noto'g'ri"""
        questions = []
        lines = text.strip().split('\n')
        current_question = None
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            if line.startswith('?'):
                if current_question and current_question['correct'] != -1:
                    questions.append(current_question)
                
                current_question = {
                    'question': line[1:].strip(),
                    'options': [],
                    'correct': -1
                }
            elif line.startswith('+'):
                if current_question:
                    current_question['correct'] = len(current_question['options'])
                    current_question['options'].append(line[1:].strip())
            elif line.startswith('-'):
                if current_question:
                    current_question['options'].append(line[1:].strip())
        
        if current_question and current_question['correct'] != -1:
            questions.append(current_question)
        
        return questions
    
    def parse_format2(self, text):
        """Yangi format: Savol ====  #to'g'ri ==== noto'g'ri ++++"""
        questions = []
        blocks = text.strip().split('++++')
        
        for block in blocks:
            block = block.strip()
            if not block:
                continue
            
            parts = block.split('====')
            if len(parts) < 2:
                continue
            
            question_text = parts[0].strip()
            options = []
            correct_index = -1
            
            for i, part in enumerate(parts[1:], 0):
                option = part.strip()
                if not option:
                    continue
                
                if option.startswith('#'):
                    correct_index = len(options)
                    options.append(option[1:].strip())
                else:
                    options.append(option)
            
            if question_text and len(options) >= 2 and correct_index != -1:
                questions.append({
                    'question': question_text,
                    'options': options,
                    'correct': correct_index
                })
        
        return questions
    
    def parse_text(self, text):
        """Ikkala formatni ham qo'llab-quvvatlash"""
        questions = self.parse_format2(text)
        
        if not questions:
            questions = self.parse_format1(text)
        
        return self.validate_questions(questions)
    
    def validate_questions(self, questions):
        """Savollarni tekshirish"""
        valid_questions = []
        for q in questions:
            if (q['question'] and 
                len(q['options']) >= 2 and 
                len(q['options']) <= 10 and
                q['correct'] >= 0 and 
                q['correct'] < len(q['options'])):
                valid_questions.append(q)
        return valid_questions

quiz_parser = QuizParser()

# ==================== KETMA-KET O'TKAZISH KUZATISH (SHAXSIY) ====================

def poll_timeout_checker(chat_id, user_id, poll_id):
    """Poll muddati tugaganda tekshirish"""
    if user_id not in user_data:
        return
    
    # Timer + 2 soniya kutish
    time.sleep(user_data[user_id].get('quiz_timer', 30) + 2)
    
    # Hali ham bir xil poll va quiz faolmi?
    if (user_data[user_id].get('current_poll_id') == poll_id and 
        user_data[user_id].get('quiz_active', False)):
        
        # Bu savol javobsiz qoldi
        if 'consecutive_skips' not in user_data[user_id]:
            user_data[user_id]['consecutive_skips'] = 0
        
        user_data[user_id]['consecutive_skips'] += 1
        user_data[user_id]['skipped_questions'] = user_data[user_id].get('skipped_questions', 0) + 1
        save_data()
        
        # Agar 2 ta ketma-ket savol o'tkazib yuborilsa
        if user_data[user_id]['consecutive_skips'] >= 2:
            ask_continue_or_stop(chat_id, user_id)
        else:
            # Keyingi savolga o'tish
            user_data[user_id]['current_question'] += 1
            save_data()
            
            # Ogohlantirish xabari
            bot.send_message(
                chat_id,
                f"⏰ Vaqt tugadi! Ketma-ket {user_data[user_id]['consecutive_skips']} ta savol javobsiz qoldi.\n"
                f"⚠️ Yana bittasi o'tkazilsa test to'xtatiladi.\n\n"
                f"Keyingi savol...",
                parse_mode='HTML'
            )
            time.sleep(2)
            send_poll_question(chat_id, user_id)

def ask_continue_or_stop(chat_id, user_id):
    """Foydalanuvchidan davom yoki to'xtatishni so'rash"""
    # Quizni pauzaga olish
    user_data[user_id]['quiz_paused'] = True
    save_data()
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("✅ Davom etish", callback_data="continue_quiz"),
        types.InlineKeyboardButton("⏹️ Testni tugatish", callback_data="stop_quiz_now")
    )
    
    skipped = user_data[user_id].get('consecutive_skips', 0)
    total_skipped = user_data[user_id].get('skipped_questions', 0)
    current = user_data[user_id]['current_question']
    total = len(user_data[user_id]['quiz_questions'])
    
    bot.send_message(
        chat_id,
        f"⏸️ <b>Test pauzaga olindi!</b>\n\n"
        f"Ketma-ket {skipped} ta savolga javob bermadingiz.\n"
        f"📊 Jami o'tkazib yuborilgan: {total_skipped} ta\n"
        f"🔢 Joriy holat: {current}/{total} savol\n\n"
        f"Nimaga amal qilamiz?",
        reply_markup=markup,
        parse_mode='HTML'
    )

@bot.callback_query_handler(func=lambda call: call.data == 'continue_quiz')
def continue_quiz_callback(call):
    """Testni davom ettirish"""
    user_id = str(call.from_user.id)
    
    if user_id not in user_data:
        bot.answer_callback_query(call.id, "❌ Test topilmadi!")
        return
    
    # Counter'larni nolga tushirish va pauzani olib tashlash
    user_data[user_id]['consecutive_skips'] = 0
    user_data[user_id]['quiz_paused'] = False
    user_data[user_id]['current_question'] += 1
    save_data()
    
    bot.edit_message_text(
        "✅ Test davom ettirilmoqda...",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id
    )
    
    time.sleep(1)
    send_poll_question(call.message.chat.id, user_id)

@bot.callback_query_handler(func=lambda call: call.data == 'stop_quiz_now')
def stop_quiz_callback(call):
    """Testni to'xtatish"""
    user_id = str(call.from_user.id)
    
    if user_id not in user_data:
        bot.answer_callback_query(call.id, "❌ Test topilmadi!")
        return
    
    user_data[user_id]['quiz_active'] = False
    user_data[user_id]['quiz_paused'] = False
    save_data()
    
    bot.edit_message_text(
        "⏹️ <b>Test to'xtatildi!</b>\n\n"
        "Natijani ko'rish uchun /results",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        parse_mode='HTML'
    )

# ==================== ASOSIY BUYRUQLAR ====================

@bot.message_handler(commands=['start'])
def start(message):
    """Bosh menyu"""
    if is_group_chat(message.chat.id):
        group_start(message)
    else:
        personal_start(message)

def personal_start(message):
    """Shaxsiy foydalanuvchi uchun start"""
    user_id = str(message.from_user.id)
    
    update_last_active(user_id)
    
    if user_id not in user_data:
        user_data[user_id] = {
            'is_group': False,
            'questions': [],
            'mode': None,
            'consecutive_skips': 0,
            'skipped_questions': 0,
            'last_active': str(datetime.now().date())
        }
        save_data()
    
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row('📝 Savollar yuklash', '🎯 Quiz boshlash')
    markup.row('📋 Savollarni ko\'rish', '❓ Yordam')
    
    if is_admin(message.from_user.id):
        markup.row('👨‍💼 Admin Panel')
    
    bot.send_message(
        message.chat.id,
        f"🎓 <b>Quiz Bot'ga xush kelibsiz!</b>\n\n"
        f"👤 {message.from_user.first_name}\n\n"
        f"✅ <b>Yangi: Ketma-ket 2 ta savol javobsiz qolsa test pauzaga olinadi!</b>\n\n"
        f"Boshlash uchun savollar yuklang yoki tugmalardan foydalaning!",
        parse_mode='HTML',
        reply_markup=markup
    )

def group_start(message):
    """Guruh uchun start"""
    chat_id = message.chat.id
    group_id = str(chat_id)
    
    # Guruh ma'lumotlarini yaratish
    if group_id not in user_data:
        user_data[group_id] = {
            'is_group': True,
            'chat_title': message.chat.title,
            'questions': [],
            'participants': {},
            'active_quiz': False,
            'created_at': str(datetime.now()),
            'last_active': str(datetime.now().date())
        }
        save_data()
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📝 Savol yuklash", callback_data=f"group_load_{group_id}"),
        types.InlineKeyboardButton("🎯 Quiz boshlash", callback_data=f"group_start_{group_id}")
    )
    markup.add(
        types.InlineKeyboardButton("📊 Natijalar", callback_data=f"group_results_{group_id}"),
        types.InlineKeyboardButton("❓ Yordam", callback_data=f"group_help_{group_id}")
    )
    
    data = user_data[group_id]
    
    bot.send_message(
        chat_id,
        f"👥 <b>Guruh Quiz Bot'i</b>\n\n"
        f"🏷️ Guruh: {message.chat.title}\n"
        f"👥 Ishtirokchilar: {len(data.get('participants', {}))}\n"
        f"📚 Savollar: {len(data.get('questions', []))}\n"
        f"🎯 Faol quiz: {'Ha' if data.get('active_quiz') else 'Yo\'q'}\n\n"
        f"Quyidagilardan birini tanlang:",
        parse_mode='HTML',
        reply_markup=markup
    )

# ==================== SHAXSIY FOYDALANUVCHI FUNKSIYALARI ====================

@bot.message_handler(commands=['load'])
@bot.message_handler(func=lambda m: m.text and m.text == '📝 Savollar yuklash')
@subscription_required
def load_questions(message):
    """Savollar yuklash"""
    user_id = str(message.from_user.id)
    
    update_last_active(user_id)
    
    if user_id not in user_data:
        user_data[user_id] = {'questions': [], 'mode': None}
    
    user_data[user_id]['mode'] = 'loading'
    save_data()
    
    bot.send_message(
        message.chat.id,
        "📥 <b>Savollarni yuklash</b>\n\n"
        "<b>Format 1 (eski):</b>\n"
        "<code>? Savol\n"
        "+ To'g'ri javob\n"
        "- Noto'g'ri javob</code>\n\n"
        "<b>Format 2 (yangi):</b>\n"
        "<code>Savol\n"
        "====\n"
        "#To'g'ri javob\n"
        "====\n"
        "Noto'g'ri javob\n"
        "++++</code>\n\n"
        "Matn yoki .txt fayl yuboring.\n\n"
        "❌ Bekor: /cancel",
        parse_mode='HTML'
    )

@bot.message_handler(commands=['quiz'])
@bot.message_handler(func=lambda m: m.text and m.text == '🎯 Quiz boshlash')
@subscription_required
def start_quiz(message):
    """Quiz boshlash"""
    user_id = str(message.from_user.id)
    
    update_last_active(user_id)
    
    if user_id not in user_data or not user_data[user_id].get('questions'):
        bot.send_message(message.chat.id, "❌ Savollar yo'q! /load")
        return
    
    total_questions = len(user_data[user_id]['questions'])
    
    # Test rejimini tanlash
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📊 Soni bo'yicha", callback_data="mode_count"),
        types.InlineKeyboardButton("🔢 Oraliq bo'yicha", callback_data="mode_range")
    )
    
    bot.send_message(
        message.chat.id,
        f"⚙️ <b>Test rejimi</b>\n\n"
        f"Jami savollar: {total_questions}\n\n"
        f"Qanday tanlashni xohlaysiz?",
        reply_markup=markup,
        parse_mode='HTML'
    )

@bot.callback_query_handler(func=lambda call: call.data == 'mode_count')
def select_count_mode(call):
    user_id = str(call.from_user.id)
    total_questions = len(user_data[user_id]['questions'])
    
    markup = types.InlineKeyboardMarkup(row_width=3)
    
    options = [5, 10, 15, 20, 30, 50]
    buttons = []
    
    for num in options:
        if num <= total_questions:
            buttons.append(types.InlineKeyboardButton(str(num), callback_data=f"qcount_{num}"))
    
    buttons.append(types.InlineKeyboardButton(f"Hammasi ({total_questions})", callback_data=f"qcount_all"))
    
    for i in range(0, len(buttons), 3):
        markup.row(*buttons[i:i+3])
    
    bot.edit_message_text(
        f"📊 <b>Savollar soni</b>\n\n"
        f"Nechta savol yechmoqchisiz?",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=markup,
        parse_mode='HTML'
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('qcount_'))
def set_question_count(call):
    user_id = str(call.from_user.id)
    count = call.data.split('_')[1]
    
    if count == 'all':
        user_data[user_id]['quiz_count'] = len(user_data[user_id]['questions'])
        user_data[user_id]['selected_questions'] = user_data[user_id]['questions'][:]
    else:
        user_data[user_id]['quiz_count'] = int(count)
        user_data[user_id]['selected_questions'] = user_data[user_id]['questions'][:int(count)]
    
    save_data()
    
    markup = types.InlineKeyboardMarkup(row_width=3)
    markup.add(
        types.InlineKeyboardButton("10s", callback_data="timer_10"),
        types.InlineKeyboardButton("15s", callback_data="timer_15"),
        types.InlineKeyboardButton("20s", callback_data="timer_20")
    )
    markup.add(
        types.InlineKeyboardButton("30s", callback_data="timer_30"),
        types.InlineKeyboardButton("60s", callback_data="timer_60"),
        types.InlineKeyboardButton("♾️ Vaqtsiz", callback_data="timer_off")
    )
    
    bot.edit_message_text(
        f"⏱️ <b>Vaqt rejimi</b>\n\n"
        f"Har bir savol uchun qancha vaqt?",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=markup,
        parse_mode='HTML'
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('timer_'))
def set_timer(call):
    user_id = str(call.from_user.id)
    timer = call.data.split('_')[1]
    
    if timer == 'off':
        user_data[user_id]['quiz_timer'] = None
    else:
        user_data[user_id]['quiz_timer'] = int(timer)
    
    # Javoblarni aralash
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🎲 Aralash", callback_data="shuffle_yes"),
        types.InlineKeyboardButton("📌 Asl", callback_data="shuffle_no")
    )
    
    bot.edit_message_text(
        "🎲 <b>Javoblar tartibi</b>\n\n"
        "Javoblarni aralashtirishni xohlaysizmi?",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=markup,
        parse_mode='HTML'
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('shuffle_'))
def set_shuffle(call):
    user_id = str(call.from_user.id)
    shuffle = call.data.split('_')[1] == 'yes'
    
    user_data[user_id]['shuffle_answers'] = shuffle
    
    # Savollar tartibini tanlash
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🔀 Aralash", callback_data="order_random"),
        types.InlineKeyboardButton("📋 Tartib", callback_data="order_sequential")
    )
    
    bot.edit_message_text(
        "📝 <b>Savollar tartibi</b>\n\n"
        "Savollar qanday tartibda bo'lsin?",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=markup,
        parse_mode='HTML'
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('order_'))
def set_order(call):
    user_id = str(call.from_user.id)
    order = call.data.split('_')[1]
    
    # Tanlangan savollarni olish
    questions = user_data[user_id]['selected_questions'][:]
    
    if order == 'random':
        random.shuffle(questions)
    
    # Javoblarni aralash
    if user_data[user_id].get('shuffle_answers', False):
        for q in questions:
            correct_answer = q['options'][q['correct']]
            random.shuffle(q['options'])
            q['correct'] = q['options'].index(correct_answer)
    
    # Yangi o'zgaruvchilarni nolga tushirish
    user_data[user_id]['quiz_questions'] = questions
    user_data[user_id]['current_question'] = 0
    user_data[user_id]['correct_answers'] = 0
    user_data[user_id]['consecutive_skips'] = 0
    user_data[user_id]['skipped_questions'] = 0
    user_data[user_id]['start_time'] = time.time()
    user_data[user_id]['answered_polls'] = {}
    user_data[user_id]['quiz_active'] = True
    user_data[user_id]['quiz_paused'] = False
    save_data()
    
    timer_text = f"{user_data[user_id]['quiz_timer']}s" if user_data[user_id]['quiz_timer'] else "Cheksiz"
    
    bot.edit_message_text(
        f"✅ <b>Quiz boshlandi!</b>\n\n"
        f"📊 Savollar: {len(questions)}\n"
        f"⏱️ Vaqt: {timer_text}\n"
        f"🎲 Javoblar: {'Aralash' if user_data[user_id].get('shuffle_answers') else 'Asl'}\n\n"
        f"⚠️ <b>DIQQAT: Ketma-ket 2 ta savol javobsiz qolsa test pauzaga olinadi!</b>\n\n"
        f"⚠️ To'xtatish: /stop\n"
        f"⏭️ O'tkazib yuborish: /skip\n\n"
        f"Birinchi savol yuborilmoqda...",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        parse_mode='HTML'
    )
    
    time.sleep(1)
    send_poll_question(call.message.chat.id, user_id)

def send_poll_question(chat_id, user_id):
    """Telegram Poll formatida savol yuborish"""
    # Quiz faol yoki pauzada emasligini tekshirish
    if not user_data[user_id].get('quiz_active', False) or user_data[user_id].get('quiz_paused', False):
        return
    
    current = user_data[user_id]['current_question']
    questions = user_data[user_id]['quiz_questions']
    
    if current >= len(questions):
        show_results(chat_id, user_id)
        return
    
    # Agar 2 ta ketma-ket savol o'tkazib yuborilgan bo'lsa
    if user_data[user_id].get('consecutive_skips', 0) >= 2:
        ask_continue_or_stop(chat_id, user_id)
        return
    
    q = questions[current]
    timer = user_data[user_id]['quiz_timer']
    
    msg = bot.send_poll(
        chat_id=chat_id,
        question=f"❓ {q['question']}",
        options=q['options'],
        type='quiz',
        correct_option_id=q['correct'],
        is_anonymous=False,
        open_period=timer if timer else 300,
        explanation=f"📊 Savol {current + 1}/{len(questions)} | /stop - To'xtatish | /skip - O'tkazib yuborish"
    )
    
    # Poll ma'lumotlarini saqlash
    user_data[user_id]['current_poll_id'] = msg.poll.id
    user_data[user_id]['poll_message_id'] = msg.message_id
    user_data[user_id]['poll_start_time'] = time.time()
    save_data()
    
    # Timeout thread yaratish
    if user_data[user_id].get('quiz_timer'):
        timer_thread = threading.Thread(
            target=poll_timeout_checker,
            args=(chat_id, user_id, msg.poll.id),
            daemon=True
        )
        timer_thread.start()

@bot.poll_answer_handler()
def handle_poll_answer(poll_answer):
    """Poll javoblarini qayta ishlash"""
    user_id = str(poll_answer.user.id)
    
    update_last_active(user_id)
    
    if user_id not in user_data or 'quiz_questions' not in user_data[user_id]:
        return
    
    # Quiz faol yoki pauzada emasligini tekshirish
    if not user_data[user_id].get('quiz_active', False) or user_data[user_id].get('quiz_paused', False):
        return
    
    # Joriy savolni olish
    current = user_data[user_id]['current_question']
    questions = user_data[user_id]['quiz_questions']
    
    if current >= len(questions):
        return
    
    # Poll ID tekshirish
    current_poll = user_data[user_id].get('current_poll_id')
    if poll_answer.poll_id != current_poll:
        return
    
    # ✅ Javob berildi - consecutive skips ni nolga tushirish
    user_data[user_id]['consecutive_skips'] = 0
    
    # Takroriy javobni oldini olish
    if 'answered_polls' not in user_data[user_id]:
        user_data[user_id]['answered_polls'] = {}
    
    if poll_answer.poll_id in user_data[user_id]['answered_polls']:
        return
    
    user_data[user_id]['answered_polls'][poll_answer.poll_id] = True
    
    # To'g'ri javobni tekshirish
    q = questions[current]
    user_answer = poll_answer.option_ids[0] if poll_answer.option_ids else -1
    
    if user_answer == q['correct']:
        user_data[user_id]['correct_answers'] += 1
    
    # Keyingi savolga o'tish
    user_data[user_id]['current_question'] += 1
    save_data()
    
    # Keyingi savolni yuborish
    time.sleep(1)
    send_poll_question(poll_answer.user.id, user_id)

@bot.message_handler(commands=['stop'])
def stop_quiz(message):
    """Testni to'xtatish"""
    if is_group_chat(message.chat.id):
        # Guruhda to'xtatish
        group_id = str(message.chat.id)
        if group_id in user_data and user_data[group_id].get('active_quiz'):
            user_data[group_id]['active_quiz'] = False
            save_data()
            bot.send_message(message.chat.id, "⏹️ Guruh quizi to'xtatildi!")
    else:
        # Shaxsiy to'xtatish
        user_id = str(message.from_user.id)
        
        if user_id not in user_data or not user_data[user_id].get('quiz_active', False):
            bot.send_message(message.chat.id, "❌ Hozirda faol test yo'q!")
            return
        
        user_data[user_id]['quiz_active'] = False
        user_data[user_id]['quiz_paused'] = False
        save_data()
        
        show_results(message.chat.id, user_id, stopped=True)

def show_results(chat_id, user_id, stopped=False):
    """Natijalarni ko'rsatish"""
    correct = user_data[user_id]['correct_answers']
    answered = user_data[user_id]['current_question']
    total = len(user_data[user_id]['quiz_questions'])
    skipped = user_data[user_id].get('skipped_questions', 0)
    
    answered_without_skips = answered - skipped
    percentage = (correct / answered_without_skips) * 100 if answered_without_skips > 0 else 0
    
    elapsed_time = int(time.time() - user_data[user_id]['start_time'])
    minutes = elapsed_time // 60
    seconds = elapsed_time % 60
    
    if percentage >= 90:
        grade = "⭐⭐⭐ A'lo!"
    elif percentage >= 70:
        grade = "⭐⭐ Yaxshi!"
    elif percentage >= 50:
        grade = "⭐ Qoniqarli"
    else:
        grade = "📚 Takror qiling"
    
    if stopped:
        title = "⏸️ <b>Test to'xtatildi!</b>"
    else:
        title = f"🏁 <b>Quiz yakunlandi!</b>"
    
    result = (
        f"{title}\n\n"
        f"📊 <b>Natija:</b>\n"
        f"✅ To'g'ri: {correct}/{answered_without_skips}\n"
        f"❌ Noto'g'ri: {answered_without_skips - correct}\n"
        f"⏭️ O'tkazib yuborilgan: {skipped}\n"
        f"📝 Javob berilgan: {answered_without_skips}/{total}\n"
        f"📈 Foiz: {percentage:.1f}%\n"
        f"⏱️ Vaqt: {minutes}:{seconds:02d}\n\n"
        f"🏆 <b>Baho:</b> {grade}"
    )
    
    bot.send_message(chat_id, result, parse_mode='HTML')
    
    # Ma'lumotlarni tozalash
    if user_id in user_data:
        user_data[user_id]['quiz_active'] = False
        user_data[user_id]['quiz_paused'] = False

# ==================== GURUH FUNKSIYALARI ====================

@bot.callback_query_handler(func=lambda call: call.data.startswith('group_load_'))
def group_load_callback(call):
    """Guruhga savol yuklash"""
    group_id = call.data.split('_')[2]
    
    user_data[group_id]['mode'] = 'group_loading'
    save_data()
    
    bot.edit_message_text(
        "📥 <b>Guruhga savol yuklash</b>\n\n"
        "Matn yoki .txt fayl yuboring.\n\n"
        "❌ Bekor: /cancel",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        parse_mode='HTML'
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('group_start_'))
def group_start_callback(call):
    """Guruhda quiz boshlash"""
    group_id = call.data.split('_')[2]
    
    if group_id not in user_data or not user_data[group_id].get('questions'):
        bot.answer_callback_query(call.id, "❌ Avval savollar yuklang!")
        return
    
    data = user_data[group_id]
    questions = data['questions'][:15]  # Guruh uchun 15 ta savol
    
    # Quizni boshlash
    data['active_quiz'] = True
    data['quiz_questions'] = questions
    data['current_question'] = 0
    data['current_poll_id'] = None
    data['participants'] = {}
    data['start_time'] = time.time()
    save_data()
    
    bot.edit_message_text(
        f"🎯 <b>Guruh Quiz boshlandi!</b>\n\n"
        f"Savollar: {len(questions)} ta\n"
        f"Vaqt: 30 soniya/savol\n"
        f"🏷️ Guruh: {data['chat_title']}\n\n"
        f"Barcha ishtirokchilar tayyor bo'lsin!",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        parse_mode='HTML'
    )
    
    time.sleep(3)
    send_next_group_question(call.message.chat.id, group_id)

def send_next_group_question(chat_id, group_id):
    """Guruhga keyingi savolni yuborish"""
    data = user_data[group_id]
    
    if not data.get('active_quiz', False):
        return
    
    current = data['current_question']
    questions = data['quiz_questions']
    
    if current >= len(questions):
        # Quiz tugadi
        finish_group_quiz(chat_id, group_id)
        return
    
    q = questions[current]
    
    poll = bot.send_poll(
        chat_id=chat_id,
        question=f"❓ {q['question']}",
        options=q['options'],
        type='quiz',
        correct_option_id=q['correct'],
        is_anonymous=False,
        open_period=30
    )
    
    data['current_poll_id'] = poll.poll.id
    data['current_question'] += 1
    save_data()
    
    # 35 soniyadan keyin keyingi savol
    timer = threading.Timer(35, send_next_group_question, args=[chat_id, group_id])
    timer.start()

@bot.poll_answer_handler()
def handle_group_poll(poll_answer):
    """Guruh poll javoblarini qayta ishlash"""
    # Guruh poll'ini topish
    for group_id, data in user_data.items():
        if data.get('is_group', False) and data.get('current_poll_id') == poll_answer.poll_id:
            # Natijani saqlash
            user_id = str(poll_answer.user.id)
            
            if 'participants' not in data:
                data['participants'] = {}
            
            if user_id not in data['participants']:
                data['participants'][user_id] = {
                    'name': f"{poll_answer.user.first_name} {poll_answer.user.last_name or ''}".strip(),
                    'correct': 0,
                    'total': 0
                }
            
            # Javobni tekshirish
            current_q = data.get('current_question', 1) - 1
            question = data['quiz_questions'][current_q]
            user_answer = poll_answer.option_ids[0] if poll_answer.option_ids else -1
            
            data['participants'][user_id]['total'] += 1
            
            if user_answer == question['correct']:
                data['participants'][user_id]['correct'] += 1
            
            save_data()
            break

def finish_group_quiz(chat_id, group_id):
    """Guruh quizini tugatish"""
    data = user_data[group_id]
    data['active_quiz'] = False
    save_data()
    
    # Natijalarni hisoblash
    participants = sorted(
        data.get('participants', {}).values(),
        key=lambda x: (x.get('correct', 0), -x.get('total', 0)),
        reverse=True
    )
    
    result_text = f"🏁 <b>Guruh Quiz Yakunlandi!</b>\n\n"
    result_text += f"🏷️ Guruh: {data['chat_title']}\n"
    result_text += f"📊 Ishtirokchilar: {len(participants)}\n"
    result_text += f"📚 Savollar: {len(data['quiz_questions'])}\n\n"
    
    if participants:
        result_text += "🏆 <b>G'oliblar:</b>\n"
        for i, p in enumerate(participants[:5], 1):
            medal = "🥇" if i == 1 else ("🥈" if i == 2 else ("🥉" if i == 3 else f"{i}."))
            correct = p.get('correct', 0)
            total = p.get('total', 0)
            percentage = (correct / total * 100) if total > 0 else 0
            
            result_text += f"{medal} <b>{p.get('name', 'Noma\'lum')}</b>\n"
            result_text += f"   ✅ {correct}/{total} • 📈 {percentage:.1f}%\n"
    
    bot.send_message(chat_id, result_text, parse_mode='HTML')

@bot.callback_query_handler(func=lambda call: call.data.startswith('group_results_'))
def group_results_callback(call):
    """Guruh natijalarini ko'rsatish"""
    group_id = call.data.split('_')[2]
    
    if group_id not in user_data:
        bot.answer_callback_query(call.id, "❌ Guruh topilmadi!")
        return
    
    data = user_data[group_id]
    
    if not data.get('participants'):
        bot.edit_message_text(
            "❌ Hozircha natijalar yo'q!",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id
        )
        return
    
    participants = sorted(
        data.get('participants', {}).values(),
        key=lambda x: (x.get('correct', 0), -x.get('total', 0)),
        reverse=True
    )
    
    result_text = f"📊 <b>{data['chat_title']} - Natijalar</b>\n\n"
    
    for i, p in enumerate(participants[:10], 1):
        medal = "🥇" if i == 1 else ("🥈" if i == 2 else ("🥉" if i == 3 else f"{i}."))
        correct = p.get('correct', 0)
        total = p.get('total', 0)
        percentage = (correct / total * 100) if total > 0 else 0
        
        result_text += f"{medal} <b>{p.get('name', 'Noma\'lum')}</b>\n"
        result_text += f"   ✅ {correct}/{total} • 📈 {percentage:.1f}%\n"
    
    bot.edit_message_text(
        result_text,
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        parse_mode='HTML'
    )

# ==================== YORDAM ====================

@bot.message_handler(commands=['help'])
@bot.message_handler(func=lambda m: m.text and m.text == '❓ Yordam')
def help_command(message):
    """Yordam menyusi"""
    if is_group_chat(message.chat.id):
        help_text = """
👥 <b>Guruh uchun qo'llanma:</b>

<b>Asosiy buyruqlar:</b>
/start - Guruh menyusi
/stop - Quizni to'xtatish

<b>Guruh quiz xususiyatlari:</b>
• 15 ta savol (avtomatik)
• 30 soniya vaqt
• Ishtirokchilar reytingi
• Avtomatik natijalar

<b>Adminlar uchun:</b>
• Savollar yuklash
• Quiz boshlash
• Natijalarni ko'rish
        """
    else:
        help_text = """
📚 <b>Shaxsiy foydalanish uchun qo'llanma</b>

<b>Format 1 (eski):</b>
? Savol
+ To'g'ri javob
- Noto'g'ri javob

<b>Format 2 (yangi):</b>
Savol
====
#To'g'ri javob
====
Noto'g'ri javob
====
Noto'g'ri javob
++++

<b>Buyruqlar:</b>
/start - Boshlash
/load - Savollar yuklash
/quiz - Quiz boshlash
/stop - Testni to'xtatish
/skip - Savolni o'tkazib yuborish
/continue - Testni davom ettirish (pauzada bo'lsa)
/results - Natijani ko'rish
/help - Yordam

<b>⚠️ YANGI XUSUSIYAT:</b>
• Ketma-ket 2 ta savol javobsiz qolsa test pauzaga olinadi
        """
    
    bot.send_message(message.chat.id, help_text, parse_mode='HTML')

# ==================== BOTNI ISHGA TUSHIRISH ====================

if __name__ == '__main__':
    print("=" * 60)
    print("🤖 QUIZ BOT ISHGA TUSHMOQDA...")
    print("=" * 60)
    
    print("\n📁 Ma'lumotlar bazasi yuklanmoqda...")
    load_data()
    
    print("\n✅ BOT TAYYOR!")
    print(f"👥 Jami: {len(user_data)}")
    print(f"👤 Shaxsiy: {sum(1 for d in user_data.values() if not d.get('is_group', True))}")
    print(f"👥 Guruhlar: {sum(1 for d in user_data.values() if d.get('is_group', False))}")
    print(f"👨‍💼 Adminlar: {len(ADMIN_IDS)}")
    
    print("\n" + "=" * 60)
    print("🎯 FUNKSIYALAR:")
    print("=" * 60)
    print("  👤 Shaxsiy testlar (ketma-ket o'tkazish monitoringi)")
    print("  👥 Guruh testlari (reyting jadvali)")
    print("  📝 2 ta format (eski va yangi)")
    print("  🎯 Telegram Poll formatida testlar")
    print("  ⏸️  Ketma-ket 2 savol javobsiz → PAUZA!")
    print("  💾 1 kunlik JSON baza")
    print("  🌐 Webhook (hosting uchun)")
    print("  📢 Majburiy obuna")
    print("  👨‍💼 Admin panel")
    print("=" * 60)
    
    # Webhook o'rnatish (agar hostingda ishlayotgan bo'lsa)
    try:
        bot.remove_webhook()
        time.sleep(1)
        bot.set_webhook(url=WEBHOOK_URL)
        print(f"\n🌐 Webhook o'rnatildi: {WEBHOOK_URL}")
    except:
        print("\n🔄 Polling rejimida ishlaydi...")
    
    print("\n🔄 Bot ishlayapti... (To'xtatish uchun Ctrl+C)")
    print("=" * 60 + "\n")
    
    # Flask server
    app.run(host='0.0.0.0', port=5000, debug=False)