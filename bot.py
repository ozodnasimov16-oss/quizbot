import telebot
from telebot import types
import random
import time
import json
import os
from datetime import datetime, timedelta
import threading

TOKEN = "8081419751:AAFdgStEJnCZ3mWq7x4fhn2DwAMxQthyCdo"
bot = telebot.TeleBot(TOKEN)

# Admin va kanal sozlamalari
ADMIN_IDS = [5762882070]
CHANNEL_USERNAME = "@TalabaQuiz"
CHANNEL_ID = -1003351063981

# Ma'lumotlar fayli
DATA_FILE = "quiz_data.json"

# Foydalanuvchilar ma'lumotlari
user_data = {}
group_quizzes = {}

# ==================== MA'LUMOTLARNI BOSHQARISH ====================

def load_data():
    """JSON fayldan ma'lumotlarni yuklash"""
    global user_data
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                user_data = json.load(f)
            print(f"✅ Ma'lumotlar yuklandi: {len(user_data)} foydalanuvchi")
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
        print(f"🗑️ Tozalandi: {len(users_to_remove)} foydalanuvchi")

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

# ==================== GURUH TESTI ====================

def get_group_key(chat_id):
    """Guruh identifikatori"""
    return f"group_{chat_id}"

# ==================== POLL TIMER CHECKER ====================

def poll_timeout_checker(chat_id, user_id, poll_id, is_group=False):
    """Poll muddati tugaganda tekshirish"""
    quiz_key = get_group_key(chat_id) if is_group else str(user_id)
    data_source = group_quizzes if is_group else user_data
    
    if quiz_key not in data_source:
        return
    
    # Timer + 2 soniya kutish
    time.sleep(data_source[quiz_key].get('quiz_timer', 30) + 2)
    
    # Hali ham bir xil poll va quiz faolmi?
    if (data_source[quiz_key].get('current_poll_id') == poll_id and 
        data_source[quiz_key].get('quiz_active', False)):
        
        # Bu savol javobsiz qoldi
        if 'consecutive_skips' not in data_source[quiz_key]:
            data_source[quiz_key]['consecutive_skips'] = 0
        
        data_source[quiz_key]['consecutive_skips'] += 1
        data_source[quiz_key]['skipped_questions'] = data_source[quiz_key].get('skipped_questions', 0) + 1
        
        if not is_group:
            save_data()
        
        # Agar 2 ta ketma-ket savol o'tkazib yuborilsa
        if data_source[quiz_key]['consecutive_skips'] >= 2:
            ask_continue_or_stop(chat_id, user_id, is_group)
        else:
            # Keyingi savolga o'tish
            data_source[quiz_key]['current_question'] += 1
            
            if not is_group:
                save_data()
            
            bot.send_message(
                chat_id,
                f"⏰ Vaqt tugadi! Ketma-ket {data_source[quiz_key]['consecutive_skips']} ta savol javobsiz qoldi.\n"
                f"⚠️ Yana bittasi o'tkazilsa test to'xtatiladi.\n\n"
                f"Keyingi savol...",
                parse_mode='HTML'
            )
            time.sleep(2)
            send_poll_question(chat_id, user_id, is_group)

def ask_continue_or_stop(chat_id, user_id, is_group=False):
    """Foydalanuvchidan davom yoki to'xtatishni so'rash"""
    quiz_key = get_group_key(chat_id) if is_group else str(user_id)
    data_source = group_quizzes if is_group else user_data
    
    # Quizni pauzaga olish
    data_source[quiz_key]['quiz_paused'] = True
    
    if not is_group:
        save_data()
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    callback_prefix = "group_" if is_group else ""
    markup.add(
        types.InlineKeyboardButton("✅ Davom etish", callback_data=f"{callback_prefix}continue_quiz"),
        types.InlineKeyboardButton("⏹️ Testni tugatish", callback_data=f"{callback_prefix}stop_quiz_now")
    )
    
    skipped = data_source[quiz_key].get('consecutive_skips', 0)
    total_skipped = data_source[quiz_key].get('skipped_questions', 0)
    current = data_source[quiz_key]['current_question']
    total = len(data_source[quiz_key]['quiz_questions'])
    
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

# ==================== CALLBACK HANDLERLAR ====================

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    """Barcha callback query'larni qayta ishlash"""
    data = call.data
    
    if data == 'check_sub':
        check_subscription_callback(call)
    elif data == 'continue_quiz':
        continue_quiz_callback(call)
    elif data == 'group_continue_quiz':
        continue_quiz_callback(call)
    elif data == 'stop_quiz_now':
        stop_quiz_callback(call)
    elif data == 'group_stop_quiz_now':
        stop_quiz_callback(call)
    elif data in ['mode_count', 'mode_range']:
        handle_quiz_mode(call)
    elif data.startswith('qcount_'):
        handle_question_count(call)
    elif data.startswith('timer_'):
        handle_timer(call)
    elif data.startswith('shuffle_'):
        handle_shuffle(call)
    elif data.startswith('order_'):
        handle_order(call)
    elif data == 'restart_quiz':
        restart_quiz(call)
    elif data.startswith('group_'):
        handle_group_callbacks(call)
    elif data in ['admin_stats', 'admin_broadcast', 'admin_clean']:
        handle_admin_callbacks(call)

def handle_quiz_mode(call):
    """Quiz mode callback"""
    if call.data == 'mode_count':
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
    elif call.data == 'mode_range':
        user_id = str(call.from_user.id)
        user_data[user_id]['mode'] = 'range_start'
        save_data()
        
        bot.edit_message_text(
            f"🔢 <b>Oraliq tanlash</b>\n\n"
            f"Boshlanish raqamini yuboring (masalan: 170)\n\n"
            f"❌ Bekor: /cancel",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            parse_mode='HTML'
        )

def handle_question_count(call):
    """Question count callback"""
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

def handle_timer(call):
    """Timer callback"""
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

def handle_shuffle(call):
    """Shuffle callback"""
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

def handle_order(call):
    """Order callback"""
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
    send_poll_question(call.message.chat.id, user_id, is_group=False)

def handle_group_callbacks(call):
    """Guruh callback'lari"""
    data = call.data
    chat_id = call.message.chat.id
    group_key = get_group_key(chat_id)
    
    if data == 'group_mode_count':
        if group_key not in group_quizzes:
            bot.answer_callback_query(call.id, "❌ Test topilmadi!")
            return
        
        total_questions = len(group_quizzes[group_key]['questions'])
        
        markup = types.InlineKeyboardMarkup(row_width=3)
        options = [5, 10, 15, 20, 30, 50]
        buttons = []
        
        for num in options:
            if num <= total_questions:
                buttons.append(types.InlineKeyboardButton(str(num), callback_data=f"group_qcount_{num}"))
        
        buttons.append(types.InlineKeyboardButton(f"Hammasi ({total_questions})", callback_data=f"group_qcount_all"))
        
        for i in range(0, len(buttons), 3):
            markup.row(*buttons[i:i+3])
        
        bot.edit_message_text(
            f"📊 <b>Savollar soni</b>\n\n"
            f"Nechta savol yechmoqchisiz?",
            chat_id=chat_id,
            message_id=call.message.message_id,
            reply_markup=markup,
            parse_mode='HTML'
        )
    
    elif data.startswith('group_qcount_'):
        count = data.split('_')[2]
        
        if group_key not in group_quizzes:
            bot.answer_callback_query(call.id, "❌ Test topilmadi!")
            return
        
        if count == 'all':
            group_quizzes[group_key]['quiz_count'] = len(group_quizzes[group_key]['questions'])
            group_quizzes[group_key]['selected_questions'] = group_quizzes[group_key]['questions'][:]
        else:
            group_quizzes[group_key]['quiz_count'] = int(count)
            group_quizzes[group_key]['selected_questions'] = group_quizzes[group_key]['questions'][:int(count)]
        
        # Vaqt tanlash
        markup = types.InlineKeyboardMarkup(row_width=3)
        markup.add(
            types.InlineKeyboardButton("10s", callback_data="group_timer_10"),
            types.InlineKeyboardButton("15s", callback_data="group_timer_15"),
            types.InlineKeyboardButton("20s", callback_data="group_timer_20")
        )
        markup.add(
            types.InlineKeyboardButton("30s", callback_data="group_timer_30"),
            types.InlineKeyboardButton("60s", callback_data="group_timer_60")
        )
        
        bot.edit_message_text(
            f"⏱️ <b>Vaqt rejimi</b>\n\n"
            f"Har bir savol uchun qancha vaqt?",
            chat_id=chat_id,
            message_id=call.message.message_id,
            reply_markup=markup,
            parse_mode='HTML'
        )
    
    elif data.startswith('group_timer_'):
        timer = int(data.split('_')[2])
        
        if group_key not in group_quizzes:
            bot.answer_callback_query(call.id, "❌ Test topilmadi!")
            return
        
        group_quizzes[group_key]['quiz_timer'] = timer
        
        # Javoblarni aralash
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("🎲 Aralash", callback_data="group_shuffle_yes"),
            types.InlineKeyboardButton("📌 Asl", callback_data="group_shuffle_no")
        )
        
        bot.edit_message_text(
            "🎲 <b>Javoblar tartibi</b>\n\n"
            "Javoblarni aralashtirishni xohlaysizmi?",
            chat_id=chat_id,
            message_id=call.message.message_id,
            reply_markup=markup,
            parse_mode='HTML'
        )
    
    elif data.startswith('group_shuffle_'):
        shuffle = data.split('_')[2] == 'yes'
        
        if group_key not in group_quizzes:
            bot.answer_callback_query(call.id, "❌ Test topilmadi!")
            return
        
        group_quizzes[group_key]['shuffle_answers'] = shuffle
        
        # Savollar tartibini tanlash
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("🔀 Aralash", callback_data="group_order_random"),
            types.InlineKeyboardButton("📋 Tartib", callback_data="group_order_sequential")
        )
        
        bot.edit_message_text(
            "📝 <b>Savollar tartibi</b>\n\n"
            "Savollar qanday tartibda bo'lsin?",
            chat_id=chat_id,
            message_id=call.message.message_id,
            reply_markup=markup,
            parse_mode='HTML'
        )
    
    elif data.startswith('group_order_'):
        order = data.split('_')[2]
        
        if group_key not in group_quizzes:
            bot.answer_callback_query(call.id, "❌ Test topilmadi!")
            return
        
        # Tanlangan savollarni olish
        questions = group_quizzes[group_key]['selected_questions'][:]
        
        if order == 'random':
            random.shuffle(questions)
        
        # Javoblarni aralash
        if group_quizzes[group_key].get('shuffle_answers', False):
            for q in questions:
                correct_answer = q['options'][q['correct']]
                random.shuffle(q['options'])
                q['correct'] = q['options'].index(correct_answer)
        
        # Guruh testini boshlash
        group_quizzes[group_key]['quiz_questions'] = questions
        group_quizzes[group_key]['current_question'] = 0
        group_quizzes[group_key]['consecutive_skips'] = 0
        group_quizzes[group_key]['skipped_questions'] = 0
        group_quizzes[group_key]['start_time'] = time.time()
        group_quizzes[group_key]['answered_polls'] = {}
        group_quizzes[group_key]['quiz_active'] = True
        group_quizzes[group_key]['quiz_paused'] = False
        
        timer_text = f"{group_quizzes[group_key]['quiz_timer']}s"
        
        bot.edit_message_text(
            f"✅ <b>Guruh testi boshlandi!</b>\n\n"
            f"📊 Savollar: {len(questions)}\n"
            f"⏱️ Vaqt: {timer_text}\n"
            f"🎲 Javoblar: {'Aralash' if group_quizzes[group_key].get('shuffle_answers') else 'Asl'}\n\n"
            f"⚠️ <b>DIQQAT:</b>\n"
            f"• Ketma-ket 2 ta savol javobsiz qolsa test pauzaga olinadi\n"
            f"• Kim nechta to'g'ri yechganini ko'rish: /groupresults\n\n"
            f"Birinchi savol yuborilmoqda...",
            chat_id=chat_id,
            message_id=call.message.message_id,
            parse_mode='HTML'
        )
        
        time.sleep(2)
        send_poll_question(chat_id, None, is_group=True)

def handle_admin_callbacks(call):
    """Admin callback'lari"""
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "❌ Ruxsat yo'q!")
        return
    
    if call.data == 'admin_stats':
        total_users = len(user_data)
        active_today = 0
        active_quiz = 0
        paused_quiz = 0
        today = str(datetime.now().date())
        
        for data in user_data.values():
            if data.get('last_active') == today:
                active_today += 1
            if data.get('quiz_active', False):
                active_quiz += 1
            if data.get('quiz_paused', False):
                paused_quiz += 1
        
        active_groups = len([g for g in group_quizzes.values() if g.get('quiz_active', False)])
        
        text = (
            f"📊 <b>Bot statistikasi</b>\n\n"
            f"👥 Jami foydalanuvchilar: {total_users}\n"
            f"🔥 Bugun faol: {active_today}\n"
            f"🎯 Faol shaxsiy testlar: {active_quiz}\n"
            f"👥 Faol guruh testlar: {active_groups}\n"
            f"⏸️ Pauzadagi testlar: {paused_quiz}\n"
            f"👨‍💼 Adminlar: {len(ADMIN_IDS)}\n"
        )
        
        bot.send_message(call.message.chat.id, text, parse_mode='HTML')
        bot.answer_callback_query(call.id)
    
    elif call.data == 'admin_clean':
        before = len(user_data)
        clean_old_data()
        after = len(user_data)
        removed = before - after
        
        bot.send_message(
            call.message.chat.id,
            f"🗑️ <b>Tozalash bajarildi!</b>\n\n"
            f"Tozalandi: {removed} foydalanuvchi\n"
            f"Qoldi: {after} foydalanuvchi",
            parse_mode='HTML'
        )
        bot.answer_callback_query(call.id, "✅ Tozalandi!")
    
    elif call.data == 'admin_broadcast':
        user_data[str(call.from_user.id)]['mode'] = 'broadcast'
        save_data()
        
        bot.send_message(
            call.message.chat.id,
            "📢 <b>Xabar yuborish</b>\n\n"
            "Barcha foydalanuvchilarga yubormoqchi bo'lgan xabaringizni yuboring.\n\n"
            "❌ Bekor: /cancel",
            parse_mode='HTML'
        )
        bot.answer_callback_query(call.id)

def check_subscription_callback(call):
    """Obuna tekshirish callback'i"""
    user_id = call.from_user.id
    
    if check_subscription(user_id):
        bot.answer_callback_query(call.id, "✅ Rahmat! Endi botdan foydalanishingiz mumkin!")
        bot.delete_message(call.message.chat.id, call.message.message_id)
        start(call.message)
    else:
        bot.answer_callback_query(
            call.id,
            "❌ Siz hali obuna bo'lmadingiz! Iltimos kanalga obuna bo'ling.",
            show_alert=True
        )

def continue_quiz_callback(call):
    """Testni davom ettirish"""
    is_group = call.data.startswith('group_')
    quiz_key = get_group_key(call.message.chat.id) if is_group else str(call.from_user.id)
    data_source = group_quizzes if is_group else user_data
    
    if quiz_key not in data_source:
        bot.answer_callback_query(call.id, "❌ Test topilmadi!")
        return
    
    # Counter'larni nolga tushirish va pauzani olib tashlash
    data_source[quiz_key]['consecutive_skips'] = 0
    data_source[quiz_key]['quiz_paused'] = False
    data_source[quiz_key]['current_question'] += 1
    
    if not is_group:
        save_data()
    
    bot.edit_message_text(
        "✅ Test davom ettirilmoqda...",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id
    )
    
    time.sleep(1)
    send_poll_question(call.message.chat.id, call.from_user.id, is_group)

def stop_quiz_callback(call):
    """Testni to'xtatish"""
    is_group = call.data.startswith('group_')
    quiz_key = get_group_key(call.message.chat.id) if is_group else str(call.from_user.id)
    data_source = group_quizzes if is_group else user_data
    
    if quiz_key not in data_source:
        bot.answer_callback_query(call.id, "❌ Test topilmadi!")
        return
    
    data_source[quiz_key]['quiz_active'] = False
    data_source[quiz_key]['quiz_paused'] = False
    
    if not is_group:
        save_data()
    
    bot.edit_message_text(
        "⏹️ <b>Test to'xtatildi!</b>\n\n"
        "Natijani ko'rish uchun /results",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        parse_mode='HTML'
    )

def restart_quiz(call):
    """Quizni qayta boshlash"""
    user_id = str(call.from_user.id)
    
    if user_id in user_data and user_data[user_id].get('questions'):
        bot.answer_callback_query(call.id, "♻️ Qayta boshlanmoqda...")
        start_quiz(call.message)
    else:
        bot.answer_callback_query(call.id, "❌ Savollar yo'q!")

# ==================== ASOSIY BUYRUQLAR ====================

@bot.message_handler(commands=['start'])
@subscription_required
def start(message):
    user_id = str(message.from_user.id)
    
    # Guruhda start buyrug'ini rad etish
    if message.chat.type in ['group', 'supergroup']:
        bot.send_message(
            message.chat.id,
            "⚠️ Bu buyruq faqat shaxsiy chatda ishlaydi!\n\n"
            "Guruhda test boshlash uchun:\n"
            "1. Menga shaxsiy chatda savollar yuklang (/load)\n"
            "2. Guruhda /groupquiz buyrug'ini yuboring"
        )
        return
    
    update_last_active(user_id)
    
    if user_id not in user_data:
        user_data[user_id] = {
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
        f"✅ <b>Yangiliklar:</b>\n"
        f"• Shaxsiy testlar\n"
        f"• Guruh testlari (/groupquiz)\n"
        f"• Ketma-ket 2 ta savol javobsiz qolsa pauza\n"
        f"• Natijalar reytingi\n\n"
        f"Boshlash uchun savollar yuklang!",
        parse_mode='HTML',
        reply_markup=markup
    )

# ==================== SAVOLLARNI YUKLASH ====================

@bot.message_handler(commands=['load'])
@bot.message_handler(func=lambda m: m.text == '📝 Savollar yuklash')
@subscription_required
def load_questions(message):
    # Guruhda yuklanmaydi
    if message.chat.type in ['group', 'supergroup']:
        bot.send_message(
            message.chat.id,
            "⚠️ Savollarni faqat shaxsiy chatda yuklash mumkin!\n\n"
            "Menga shaxsiy xabar yuboring: @YourBotUsername"
        )
        return
    
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

@bot.message_handler(commands=['cancel'])
def cancel(message):
    user_id = str(message.from_user.id)
    if user_id in user_data:
        user_data[user_id]['mode'] = None
        save_data()
    bot.send_message(message.chat.id, "❌ Bekor qilindi.")

@bot.message_handler(content_types=['document'])
def handle_document(message):
    user_id = str(message.from_user.id)
    update_last_active(user_id)
    
    if user_data.get(user_id, {}).get('mode') != 'loading':
        bot.send_message(message.chat.id, "Avval /load buyrug'ini yuboring!")
        return
    
    try:
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        text = downloaded_file.decode('utf-8')
        process_questions_text(message, text)
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Xatolik: {str(e)}")

@bot.message_handler(func=lambda m: user_data.get(str(m.from_user.id), {}).get('mode') == 'loading')
def handle_text_questions(message):
    update_last_active(message.from_user.id)
    process_questions_text(message, message.text)

def process_questions_text(message, text):
    user_id = str(message.from_user.id)
    
    try:
        questions = quiz_parser.parse_text(text)
        
        if questions:
            user_data[user_id]['questions'] = questions
            user_data[user_id]['mode'] = None
            save_data()
            
            bot.send_message(
                message.chat.id,
                f"✅ <b>Savollar yuklandi!</b>\n\n"
                f"📊 Jami: {len(questions)} ta savol\n\n"
                f"<b>Test boshlash:</b>\n"
                f"• Shaxsiy: /quiz\n"
                f"• Guruhda: /groupquiz",
                parse_mode='HTML'
            )
        else:
            bot.send_message(
                message.chat.id,
                "❌ Format xato yoki savollar topilmadi!\n\n"
                "Yordam: /help"
            )
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Xatolik: {str(e)}")

# ==================== SAVOLLARNI KO'RISH ====================

@bot.message_handler(commands=['view'])
@bot.message_handler(func=lambda m: m.text == "📋 Savollarni ko'rish")
@subscription_required
def view_questions(message):
    user_id = str(message.from_user.id)
    update_last_active(user_id)
    
    if user_id not in user_data or not user_data[user_id].get('questions'):
        bot.send_message(message.chat.id, "❌ Savollar yo'q! /load")
        return
    
    questions = user_data[user_id]['questions']
    
    text = f"📚 <b>Savollar ({len(questions)} ta)</b>\n\n"
    
    for i, q in enumerate(questions[:10], 1):
        text += f"<b>{i}. {q['question']}</b>\n"
        for j, opt in enumerate(q['options']):
            marker = "✅" if j == q['correct'] else "❌"
            text += f"  {marker} {opt}\n"
        text += "\n"
    
    if len(questions) > 10:
        text += f"... va yana {len(questions) - 10} ta savol"
    
    bot.send_message(message.chat.id, text, parse_mode='HTML')

# ==================== GURUH QUIZI ====================

@bot.message_handler(commands=['groupquiz'])
def start_group_quiz(message):
    """Guruhda quiz boshlash"""
    # Faqat guruhda ishlaydi
    if message.chat.type not in ['group', 'supergroup']:
        bot.send_message(
            message.chat.id,
            "⚠️ Bu buyruq faqat guruhlarda ishlaydi!\n\n"
            "Shaxsiy test: /quiz"
        )
        return
    
    user_id = str(message.from_user.id)
    chat_id = message.chat.id
    group_key = get_group_key(chat_id)
    
    # Foydalanuvchida savollar bormi?
    if user_id not in user_data or not user_data[user_id].get('questions'):
        bot.send_message(
            chat_id,
            f"❌ @{message.from_user.username}, sizda savollar yo'q!\n\n"
            f"Menga shaxsiy chatda /load buyrug'i bilan savollar yuklang."
        )
        return
    
    # Guruhda faol test bormi?
    if group_key in group_quizzes and group_quizzes[group_key].get('quiz_active', False):
        bot.send_message(
            chat_id,
            "⚠️ Guruhda allaqachon test boshlanган!\n\n"
            "To'xtatish: /stopgroup"
        )
        return
    
    # Guruh testini boshlash
    total_questions = len(user_data[user_id]['questions'])
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📊 Soni bo'yicha", callback_data="group_mode_count"),
        types.InlineKeyboardButton("🔢 Oraliq bo'yicha", callback_data="group_mode_range")
    )
    
    # Guruh ma'lumotlarini saqlash
    group_quizzes[group_key] = {
        'creator_id': user_id,
        'questions': user_data[user_id]['questions'][:],
        'mode': 'selecting',
        'participants': {}
    }
    
    bot.send_message(
        chat_id,
        f"🎯 <b>Guruh testi</b>\n\n"
        f"📝 Boshladi: @{message.from_user.username}\n"
        f"📊 Jami savollar: {total_questions}\n\n"
        f"Test rejimini tanlang:",
        reply_markup=markup,
        parse_mode='HTML'
    )

# ==================== SHAXSIY QUIZ BOSHLASH ====================

@bot.message_handler(commands=['quiz'])
@bot.message_handler(func=lambda m: m.text == '🎯 Quiz boshlash')
@subscription_required
def start_quiz(message):
    # Guruhda ishlamaydi
    if message.chat.type in ['group', 'supergroup']:
        bot.send_message(
            message.chat.id,
            "⚠️ Shaxsiy testni faqat shaxsiy chatda boshlash mumkin!\n\n"
            "Guruh testi uchun: /groupquiz"
        )
        return
    
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

# ==================== SAVOL YUBORISH ====================

def send_poll_question(chat_id, user_id, is_group=False):
    """Telegram Poll formatida savol yuborish"""
    quiz_key = get_group_key(chat_id) if is_group else str(user_id)
    data_source = group_quizzes if is_group else user_data
    
    # Quiz faol yoki pauzada emasligini tekshirish
    if quiz_key not in data_source or not data_source[quiz_key].get('quiz_active', False) or data_source[quiz_key].get('quiz_paused', False):
        return
    
    current = data_source[quiz_key]['current_question']
    questions = data_source[quiz_key]['quiz_questions']
    
    if current >= len(questions):
        show_results(chat_id, user_id, is_group=is_group)
        return
    
    # Agar 2 ta ketma-ket savol o'tkazib yuborilgan bo'lsa
    if data_source[quiz_key].get('consecutive_skips', 0) >= 2:
        ask_continue_or_stop(chat_id, user_id, is_group)
        return
    
    q = questions[current]
    timer = data_source[quiz_key]['quiz_timer']
    
    try:
        msg = bot.send_poll(
            chat_id=chat_id,
            question=f"❓ {q['question']}",
            options=q['options'],
            type='quiz',
            correct_option_id=q['correct'],
            is_anonymous=False,
            open_period=timer if timer else 300,
            explanation=f"📊 Savol {current + 1}/{len(questions)}"
        )
        
        # Poll ma'lumotlarini saqlash
        data_source[quiz_key]['current_poll_id'] = msg.poll.id
        data_source[quiz_key]['poll_message_id'] = msg.message_id
        data_source[quiz_key]['poll_start_time'] = time.time()
        
        if not is_group:
            save_data()
        
        # Timeout thread yaratish
        if timer:
            timer_thread = threading.Thread(
                target=poll_timeout_checker,
                args=(chat_id, user_id, msg.poll.id, is_group),
                daemon=True
            )
            timer_thread.start()
    except Exception as e:
        print(f"❌ Poll yuborishda xatolik: {e}")
        bot.send_message(chat_id, f"❌ Xatolik yuz berdi: {e}")

# ==================== POLL JAVOBLARINI QO'LLASH ====================

@bot.poll_answer_handler()
def handle_poll_answer(poll_answer):
    """Poll javoblarini qayta ishlash"""
    user_id = str(poll_answer.user.id)
    
    # Shaxsiy test uchun
    if user_id in user_data and 'quiz_questions' in user_data[user_id]:
        if not user_data[user_id].get('quiz_active', False) or user_data[user_id].get('quiz_paused', False):
            return
        
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
        send_poll_question(poll_answer.user.id, user_id, is_group=False)
    
    # Guruh testi uchun
    for group_key, group_data in group_quizzes.items():
        if group_data.get('current_poll_id') == poll_answer.poll_id:
            if not group_data.get('quiz_active', False) or group_data.get('quiz_paused', False):
                return
            
            # Consecutive skips ni nolga tushirish
            group_data['consecutive_skips'] = 0
            
            # Ishtirokchini qo'shish
            if user_id not in group_data['participants']:
                group_data['participants'][user_id] = {
                    'correct': 0,
                    'total': 0,
                    'name': poll_answer.user.first_name
                }
            
            # Takroriy javobni oldini olish
            if 'answered_polls' not in group_data:
                group_data['answered_polls'] = {}
            
            poll_key = f"{poll_answer.poll_id}_{user_id}"
            if poll_key in group_data['answered_polls']:
                return
            
            group_data['answered_polls'][poll_key] = True
            
            # To'g'ri javobni tekshirish
            current = group_data['current_question']
            questions = group_data['quiz_questions']
            
            if current < len(questions):
                q = questions[current]
                user_answer = poll_answer.option_ids[0] if poll_answer.option_ids else -1
                
                group_data['participants'][user_id]['total'] += 1
                
                if user_answer == q['correct']:
                    group_data['participants'][user_id]['correct'] += 1
            
            # Faqat bitta kishi keyingi savolga o'tkazadi (botning o'zi)
            # Bu threading orqali avtomatik amalga oshadi
            break

# ==================== GURUH NATIJALARINI KO'RSATISH ====================

@bot.message_handler(commands=['groupresults'])
def show_group_results(message):
    """Guruh test natijalarini ko'rsatish"""
    if message.chat.type not in ['group', 'supergroup']:
        bot.send_message(message.chat.id, "⚠️ Bu buyruq faqat guruhlarda ishlaydi!")
        return
    
    group_key = get_group_key(message.chat.id)
    
    if group_key not in group_quizzes or not group_quizzes[group_key].get('quiz_questions'):
        bot.send_message(message.chat.id, "❌ Faol test topilmadi!")
        return
    
    group_data = group_quizzes[group_key]
    participants = group_data.get('participants', {})
    
    if not participants:
        bot.send_message(message.chat.id, "❌ Hali hech kim javob bermagan!")
        return
    
    # Reytingni shakllantirish
    sorted_participants = sorted(
        participants.items(),
        key=lambda x: (x[1]['correct'], -x[1]['total']),
        reverse=True
    )
    
    current = group_data['current_question']
    total = len(group_data['quiz_questions'])
    
    text = f"🏆 <b>Guruh test natijalari</b>\n\n"
    text += f"📊 Savol: {current}/{total}\n"
    text += f"👥 Ishtirokchilar: {len(participants)}\n\n"
    text += f"<b>📈 Reyting:</b>\n\n"
    
    for i, (uid, data) in enumerate(sorted_participants, 1):
        name = data['name']
        correct = data['correct']
        total_answered = data['total']
        percentage = (correct / total_answered * 100) if total_answered > 0 else 0
        
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
        
        text += f"{medal} <b>{name}</b>\n"
        text += f"   ✅ {correct}/{total_answered} ({percentage:.0f}%)\n\n"
    
    bot.send_message(message.chat.id, text, parse_mode='HTML')

# ==================== GURUH TESTNI TO'XTATISH ====================

@bot.message_handler(commands=['stopgroup'])
def stop_group_quiz(message):
    """Guruh testni to'xtatish"""
    if message.chat.type not in ['group', 'supergroup']:
        bot.send_message(message.chat.id, "⚠️ Bu buyruq faqat guruhlarda ishlaydi!")
        return
    
    group_key = get_group_key(message.chat.id)
    
    if group_key not in group_quizzes or not group_quizzes[group_key].get('quiz_active', False):
        bot.send_message(message.chat.id, "❌ Faol test yo'q!")
        return
    
    # Quizni to'xtatish
    group_quizzes[group_key]['quiz_active'] = False
    group_quizzes[group_key]['quiz_paused'] = False
    
    show_results(message.chat.id, None, is_group=True, stopped=True)

# ==================== TESTNI TO'XTATISH ====================

@bot.message_handler(commands=['stop'])
def stop_quiz(message):
    """Shaxsiy testni to'xtatish"""
    if message.chat.type in ['group', 'supergroup']:
        bot.send_message(
            message.chat.id,
            "⚠️ Guruh testni to'xtatish uchun: /stopgroup"
        )
        return
    
    user_id = str(message.from_user.id)
    
    if user_id not in user_data or not user_data[user_id].get('quiz_active', False):
        bot.send_message(
            message.chat.id,
            "❌ Hozirda faol test yo'q!\n\n"
            "Test boshlash: /quiz"
        )
        return
    
    # Quizni to'xtatish
    user_data[user_id]['quiz_active'] = False
    user_data[user_id]['quiz_paused'] = False
    save_data()
    
    # Natijani ko'rsatish
    show_results(message.chat.id, user_id, is_group=False, stopped=True)

def show_results(chat_id, user_id, is_group=False, stopped=False):
    """Yakuniy natijalarni ko'rsatish"""
    quiz_key = get_group_key(chat_id) if is_group else str(user_id)
    data_source = group_quizzes if is_group else user_data
    
    if is_group:
        # Guruh natijalari
        participants = data_source[quiz_key].get('participants', {})
        answered = data_source[quiz_key]['current_question']
        total = len(data_source[quiz_key]['quiz_questions'])
        
        if not participants:
            bot.send_message(chat_id, "❌ Hech kim javob bermagan!")
            data_source[quiz_key]['quiz_active'] = False
            return
        
        # Reytingni shakllantirish
        sorted_participants = sorted(
            participants.items(),
            key=lambda x: (x[1]['correct'], -x[1]['total']),
            reverse=True
        )
        
        elapsed_time = int(time.time() - data_source[quiz_key]['start_time'])
        minutes = elapsed_time // 60
        seconds = elapsed_time % 60
        
        title = "⏸️ <b>Guruh testi to'xtatildi!</b>" if stopped else "🎉 <b>Guruh testi yakunlandi!</b>"
        
        text = f"{title}\n\n"
        text += f"📊 Savollar: {answered}/{total}\n"
        text += f"👥 Ishtirokchilar: {len(participants)}\n"
        text += f"⏱️ Vaqt: {minutes}:{seconds:02d}\n\n"
        text += f"<b>🏆 Yakuniy reyting:</b>\n\n"
        
        for i, (uid, data) in enumerate(sorted_participants, 1):
            name = data['name']
            correct = data['correct']
            total_answered = data['total']
            percentage = (correct / total_answered * 100) if total_answered > 0 else 0
            
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
            
            text += f"{medal} <b>{name}</b>\n"
            text += f"   ✅ To'g'ri: {correct}/{total_answered}\n"
            text += f"   📈 Foiz: {percentage:.1f}%\n\n"
        
        # G'olib e'lon qilish
        if sorted_participants:
            winner_data = sorted_participants[0][1]
            text += f"\n🎊 <b>G'olib: {winner_data['name']}!</b>\n"
            text += f"Tabriklaymiz! 🎉"
        
        bot.send_message(chat_id, text, parse_mode='HTML')
        
        # Ma'lumotlarni tozalash
        del group_quizzes[quiz_key]
        
    else:
        # Shaxsiy natijalar
        correct = data_source[quiz_key]['correct_answers']
        answered = data_source[quiz_key]['current_question']
        total = len(data_source[quiz_key]['quiz_questions'])
        skipped = data_source[quiz_key].get('skipped_questions', 0)
        
        if answered == 0:
            bot.send_message(
                chat_id,
                "⚠️ <b>Test to'xtatildi!</b>\n\n"
                "Hech qanday savol yechilmadi.",
                parse_mode='HTML'
            )
            data_source[quiz_key]['quiz_active'] = False
            data_source[quiz_key]['quiz_paused'] = False
            save_data()
            return
        
        answered_without_skips = answered - skipped
        percentage = (correct / answered_without_skips) * 100 if answered_without_skips > 0 else 0
        
        elapsed_time = int(time.time() - data_source[quiz_key]['start_time'])
        minutes = elapsed_time // 60
        seconds = elapsed_time % 60
        
        if percentage >= 90:
            grade = "⭐⭐⭐ A'lo!"
            emoji = "🎉"
        elif percentage >= 70:
            grade = "⭐⭐ Yaxshi!"
            emoji = "👍"
        elif percentage >= 50:
            grade = "⭐ Qoniqarli"
            emoji = "👌"
        else:
            grade = "📚 Takror qiling"
            emoji = "📖"
        
        if stopped:
            title = "⏸️ <b>Test to'xtatildi!</b>"
        else:
            title = f"{emoji} <b>Quiz yakunlandi!</b>"
        
        result = (
            f"{title}\n\n"
            f"📊 <b>Natija:</b>\n"
            f"✅ To'g'ri: {correct}/{answered_without_skips}\n"
            f"❌ Noto'g'ri: {answered_without_skips - correct}/{answered_without_skips}\n"
            f"⏭️ O'tkazib yuborilgan: {skipped}\n"
            f"📝 Javob berilgan: {answered_without_skips}/{total}\n"
        )
        
        if stopped:
            result += f"⏭️ Yechilmagan: {total - answered}\n"
        
        result += (
            f"📈 Foiz: {percentage:.1f}%\n"
            f"⏱️ Vaqt: {minutes}:{seconds:02d}\n\n"
            f"🏆 <b>Baho:</b> {grade}"
        )
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔄 Qayta boshlash", callback_data="restart_quiz"))
        
        bot.send_message(chat_id, result, reply_markup=markup, parse_mode='HTML')
        
        # Ma'lumotlarni tozalash
        if user_id in user_data:
            user_data[user_id]['quiz_questions'] = []
            user_data[user_id]['current_question'] = 0
            user_data[user_id]['correct_answers'] = 0
            user_data[user_id]['consecutive_skips'] = 0
            user_data[user_id]['skipped_questions'] = 0
            user_data[user_id]['answered_polls'] = {}
            user_data[user_id]['quiz_active'] = False
            user_data[user_id]['quiz_paused'] = False
            save_data()

# ==================== /skip BUYRUG'I ====================

@bot.message_handler(commands=['skip'])
def skip_question(message):
    """Hozirgi savolni o'tkazib yuborish"""
    user_id = str(message.from_user.id)
    
    if user_id not in user_data or not user_data[user_id].get('quiz_active', False):
        bot.send_message(message.chat.id, "❌ Hozirda faol test yo'q!")
        return
    
    # Consecutive skips counter'ini oshirish
    if 'consecutive_skips' not in user_data[user_id]:
        user_data[user_id]['consecutive_skips'] = 0
    
    user_data[user_id]['consecutive_skips'] += 1
    user_data[user_id]['skipped_questions'] = user_data[user_id].get('skipped_questions', 0) + 1
    
    # Agar 2 ta ketma-ket savol o'tkazib yuborilsa
    if user_data[user_id]['consecutive_skips'] >= 2:
        ask_continue_or_stop(message.chat.id, user_id)
    else:
        # Faqat 1 ta o'tkazilgan bo'lsa
        user_data[user_id]['current_question'] += 1
        save_data()
        
        bot.send_message(
            message.chat.id,
            f"⏭️ Savol o'tkazib yuborildi.\n"
            f"⚠️ Diqqat: Ketma-ket {user_data[user_id]['consecutive_skips']}/2 - yana bittasi o'tkazilsa test pauzaga olinadi.",
            parse_mode='HTML'
        )
        time.sleep(1)
        send_poll_question(message.chat.id, user_id)

# ==================== /results BUYRUG'I ====================

@bot.message_handler(commands=['results'])
def show_current_results(message):
    """Hozirgi test natijalarini ko'rsatish"""
    user_id = str(message.from_user.id)
    
    if user_id not in user_data or 'quiz_questions' not in user_data[user_id]:
        bot.send_message(message.chat.id, "❌ Faol test topilmadi!")
        return
    
    answered = user_data[user_id]['current_question']
    correct = user_data[user_id]['correct_answers']
    total = len(user_data[user_id]['quiz_questions'])
    skipped = user_data[user_id].get('skipped_questions', 0)
    
    answered_without_skips = answered - skipped
    percentage = (correct / answered_without_skips) * 100 if answered_without_skips > 0 else 0
    
    text = (
        f"📊 <b>Hozirgi test natijalari:</b>\n\n"
        f"✅ To'g'ri: {correct}\n"
        f"❌ Noto'g'ri: {answered_without_skips - correct}\n"
        f"⏭️ O'tkazib yuborilgan: {skipped}\n"
        f"📝 Javob berilgan: {answered_without_skips}/{total}\n"
        f"📈 Foiz: {percentage:.1f}%\n\n"
    )
    
    if user_data[user_id].get('quiz_paused', False):
        text += f"⏸️ Test PAUZADA - Davom etish yoki to'xtatish kerak\n"
    elif user_data[user_id].get('consecutive_skips', 0) > 0:
        text += f"⚠️ Ketma-ket o'tkazib yuborilgan: {user_data[user_id]['consecutive_skips']}/2\n"
    
    text += f"\nTestni davom ettirish: /continue\nTestni to'xtatish: /stop"
    
    bot.send_message(message.chat.id, text, parse_mode='HTML')

# ==================== /continue BUYRUG'I ====================

@bot.message_handler(commands=['continue'])
def continue_quiz_command(message):
    """Testni davom ettirish (faqat pauzada bo'lsa)"""
    user_id = str(message.from_user.id)
    
    if user_id not in user_data:
        bot.send_message(message.chat.id, "❌ Test topilmadi!")
        return
    
    if not user_data[user_id].get('quiz_paused', False):
        bot.send_message(message.chat.id, "❌ Test pauzada emas!")
        return
    
    # Counter'larni nolga tushirish va pauzani olib tashlash
    user_data[user_id]['consecutive_skips'] = 0
    user_data[user_id]['quiz_paused'] = False
    user_data[user_id]['current_question'] += 1
    save_data()
    
    bot.send_message(message.chat.id, "✅ Test davom ettirilmoqda...")
    time.sleep(1)
    send_poll_question(message.chat.id, user_id)

# ==================== ADMIN PANEL ====================

@bot.message_handler(func=lambda m: m.text == '👨‍💼 Admin Panel')
def admin_panel(message):
    if not is_admin(message.from_user.id):
        bot.send_message(message.chat.id, "❌ Bu bo'lim faqat adminlar uchun!")
        return
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📊 Statistika", callback_data="admin_stats"),
        types.InlineKeyboardButton("📢 Xabar yuborish", callback_data="admin_broadcast")
    )
    markup.add(
        types.InlineKeyboardButton("🗑️ Tozalash", callback_data="admin_clean")
    )
    
    bot.send_message(
        message.chat.id,
        "👨‍💼 <b>Admin Panel</b>\n\nAmallarni tanlang:",
        reply_markup=markup,
        parse_mode='HTML'
    )

@bot.message_handler(func=lambda m: user_data.get(str(m.from_user.id), {}).get('mode') == 'broadcast')
def handle_broadcast(message):
    if not is_admin(message.from_user.id):
        return
    
    broadcast_text = message.text
    success = 0
    failed = 0
    
    status_msg = bot.send_message(message.chat.id, "📤 Xabar yuborilmoqda...")
    
    for uid in user_data.keys():
        try:
            bot.send_message(int(uid), broadcast_text)
            success += 1
            time.sleep(0.05)
        except:
            failed += 1
    
    user_data[str(message.from_user.id)]['mode'] = None
    save_data()
    
    bot.edit_message_text(
        f"✅ <b>Xabar yuborildi!</b>\n\n"
        f"✅ Muvaffaqiyatli: {success}\n"
        f"❌ Xato: {failed}",
        chat_id=message.chat.id,
        message_id=status_msg.message_id,
        parse_mode='HTML'
    )

# ==================== YORDAM ====================

@bot.message_handler(commands=['help'])
@bot.message_handler(func=lambda m: m.text == '❓ Yordam')
@subscription_required
def help_command(message):
    help_text = """
📚 <b>Qo'llanma</b>

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

<b>Shaxsiy test buyruqlari:</b>
/start - Boshlash
/load - Savollar yuklash
/quiz - Test boshlash
/stop - Testni to'xtatish
/skip - Savolni o'tkazib yuborish
/continue - Testni davom ettirish
/results - Hozirgi natijani ko'rish
/view - Savollarni ko'rish

<b>Guruh test buyruqlari:</b>
/groupquiz - Guruh testni boshlash
/groupresults - Guruh natijalarini ko'rish
/stopgroup - Guruh testni to'xtatish

<b>Test sozlamalari:</b>
• Soni bo'yicha - 5, 10, 15, 20, 30, 50 yoki hammasi
• Oraliq bo'yicha - masalan 170-180
• Vaqt - 10s, 15s, 20s, 30s, 60s yoki cheksiz
• Javoblarni aralash - ha/yo'q
• Savollarni aralash - ha/yo'q

<b>⚠️ XUSUSIYATLAR:</b>
• Ketma-ket 2 ta savol javobsiz qolsa test pauzaga olinadi
• Guruh testlarida real-time reyting
• Kim qancha yechganini ko'rish mumkin

<b>Ma'lumotlar:</b>
• Ma'lumotlar 1 kun saqlanadi
• Keyingi kun avtomatik tozalanadi
    """
    bot.send_message(message.chat.id, help_text, parse_mode='HTML')

# ==================== AVTOMATIK TOZALASH ====================

def auto_clean_loop():
    """Har 6 soatda eski ma'lumotlarni tozalash"""
    while True:
        time.sleep(21600)  # 6 soat
        try:
            clean_old_data()
            print(f"🗑️ Avtomatik tozalash: {datetime.now().strftime('%H:%M:%S')}")
        except Exception as e:
            print(f"❌ Avtomatik tozalash xatosi: {e}")

# ==================== BOTNI ISHGA TUSHIRISH ====================

if __name__ == '__main__':
    print("=" * 60)
    print("🤖 QUIZ BOT ISHGA TUSHMOQDA...")
    print("=" * 60)
    
    print("\n📁 Ma'lumotlar bazasi yuklanmoqda...")
    load_data()
    
    print("\n✅ BOT TAYYOR!")
    print(f"👥 Foydalanuvchilar: {len(user_data)}")
    print(f"👨‍💼 Adminlar: {len(ADMIN_IDS)}")
    print(f"📢 Kanal: {CHANNEL_USERNAME}")
    print(f"🆔 Kanal ID: {CHANNEL_ID}")
    
    print("\n" + "=" * 60)
    print("🎯 YANGI XUSUSIYATLAR:")
    print("=" * 60)
    print("  ✅ Shaxsiy va guruh testlari")
    print("  ✅ Real-time guruh reytingi")
    print("  ✅ Har bir savol uchun alohida timer")
    print("  ✅ Ketma-ket 2 savol javobsiz -> pauza")
    print("  ✅ Natijalarni har qachon ko'rish")
    print("  ✅ Kim qancha yechgan - guruhda ko'rish")
    print("  ✅ Test pauzadan davom ettirish")
    print("  ✅ Telegram Poll formati")
    print("=" * 60)
    
    print("\n🔄 Bot ishlayapti... (To'xtatish uchun Ctrl+C)")
    print("🗑️  Eski ma'lumotlar avtomatik tozalanadi (har 6 soat)")
    print("=" * 60 + "\n")
    
    clean_thread = threading.Thread(target=auto_clean_loop, daemon=True)
    clean_thread.start()
    
    try:
        bot.infinity_polling(timeout=60, long_polling_timeout=60)
    except KeyboardInterrupt:
        print("\n\n" + "=" * 60)
        print("⏸️  Bot to'xtatilmoqda...")
        print("=" * 60)
    finally:
        print("💾 Ma'lumotlar saqlanmoqda...")
        save_data()
        print("✅ Ma'lumotlar saqlandi!")
        print("👋 Bot to'xtatildi!")
        print("=" * 60)