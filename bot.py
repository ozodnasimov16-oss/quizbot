import telebot
from telebot import types
import random
import time
import json
import os
from datetime import datetime, timedelta

TOKEN = "8081419751:AAFdgStEJnCZ3mWq7x4fhn2DwAMxQthyCdo"
bot = telebot.TeleBot(TOKEN)

# Admin va kanal sozlamalari
ADMIN_IDS = [5762882070]
CHANNEL_USERNAME = "@TalabaQuiz"
CHANNEL_ID = -1003351063981

# Ma'lumotlar fayli
DATA_FILE = "quiz_data.json"
CONFIG_FILE = "config.json"

# Global ma'lumotlar
user_data = {}

# Yutuqlar
ACHIEVEMENTS = {
    'first_test': {'name': '🎯 Birinchi test', 'desc': 'Birinchi testni tugatdingiz!', 'icon': '🎯'},
    'perfect_score': {'name': '💯 Mukammal', 'desc': '100% natija!', 'icon': '💯'},
    'speed_demon': {'name': '⚡ Tezkor', 'desc': '1 daqiqada 10 ta savol', 'icon': '⚡'},
    'persistent': {'name': '🔥 Qatʼiyatli', 'desc': '10 ta test topshirdingiz', 'icon': '🔥'},
    'streak_3': {'name': '📅 3 kun ketma-ket', 'desc': '3 kun davomida test yeching', 'icon': '📅'},
    'streak_7': {'name': '🌟 7 kun ketma-ket', 'desc': '7 kun davomida test yeching', 'icon': '🌟'},
    'level_5': {'name': '⭐ Daraja 5', 'desc': '5-darajaga yetdingiz!', 'icon': '⭐'},
    'level_10': {'name': '🏆 Daraja 10', 'desc': '10-darajaga yetdingiz!', 'icon': '🏆'}
}

# ==================== FUNKSIYALAR ====================

def load_config():
    """Konfiguratsiyani yuklash"""
    global ADMIN_IDS, CHANNEL_ID
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
                ADMIN_IDS = config.get('admin_ids', [])
                CHANNEL_ID = config.get('channel_id', None)
    except Exception as e:
        print(f"⚠️ Konfiguratsiya yuklashda xatolik: {e}")

def save_config():
    """Konfiguratsiyani saqlash"""
    try:
        config = {
            'admin_ids': ADMIN_IDS,
            'channel_id': CHANNEL_ID
        }
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2)
    except Exception as e:
        print(f"❌ Konfiguratsiya saqlashda xatolik: {e}")

def load_data():
    """JSON fayldan ma'lumotlarni yuklash"""
    global user_data
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                user_data = json.load(f)
            print(f"✅ Ma'lumotlar yuklandi: {len(user_data)} foydalanuvchi")
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
        
        # Adminlar uchun tekshirmaslik
        if is_admin(user_id):
            return func(message)
        
        # Obunani tekshirish
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

def get_level(total_score):
    """Ballar asosida darajani hisoblash"""
    return total_score // 100 + 1

def get_rank(level):
    """Daraja asosida unvon berish"""
    if level >= 10:
        return "🏆 Master"
    elif level >= 7:
        return "💎 Expert"
    elif level >= 5:
        return "⭐ Professional"
    elif level >= 3:
        return "🥉 Intermediate"
    else:
        return "🥇 Beginner"

def check_achievements(user_id, score, total, elapsed_time):
    """Yutuqlarni tekshirish"""
    new_achievements = []
    achievements = user_data[user_id].get('achievements', [])
    
    if user_data[user_id]['tests_completed'] == 1 and 'first_test' not in achievements:
        new_achievements.append('first_test')
    
    if score == total and 'perfect_score' not in achievements:
        new_achievements.append('perfect_score')
    
    if total >= 10 and elapsed_time <= 60 and 'speed_demon' not in achievements:
        new_achievements.append('speed_demon')
    
    if user_data[user_id]['tests_completed'] >= 10 and 'persistent' not in achievements:
        new_achievements.append('persistent')
    
    streak = user_data[user_id].get('streak', 0)
    if streak >= 3 and 'streak_3' not in achievements:
        new_achievements.append('streak_3')
    if streak >= 7 and 'streak_7' not in achievements:
        new_achievements.append('streak_7')
    
    level = get_level(user_data[user_id]['total_score'])
    if level >= 5 and 'level_5' not in achievements:
        new_achievements.append('level_5')
    if level >= 10 and 'level_10' not in achievements:
        new_achievements.append('level_10')
    
    return new_achievements

# ==================== QUIZ MANAGER ====================

class QuizManager:
    def parse_text(self, text):
        """Matn formatdagi savollarni parse qilish"""
        questions = []
        lines = text.strip().split('\n')
        current_question = None
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            if line.startswith('?'):
                if current_question:
                    questions.append(current_question)
                
                current_question = {
                    'question': line[1:].strip(),
                    'options': [],
                    'correct': -1,
                    'hint': None
                }
            elif line.startswith('+'):
                if current_question:
                    current_question['correct'] = len(current_question['options'])
                    current_question['options'].append(line[1:].strip())
            elif line.startswith('-'):
                if current_question:
                    current_question['options'].append(line[1:].strip())
            elif line.startswith('!'):
                if current_question:
                    current_question['hint'] = line[1:].strip()
        
        if current_question and current_question['correct'] != -1:
            questions.append(current_question)
        
        return questions
    
    def validate_questions(self, questions):
        """Savollarni tekshirish"""
        valid_questions = []
        for q in questions:
            if (q['question'] and 
                len(q['options']) >= 2 and 
                q['correct'] >= 0 and 
                q['correct'] < len(q['options'])):
                valid_questions.append(q)
        return valid_questions

quiz_manager = QuizManager()

# ==================== ASOSIY BUYRUQLAR ====================

@bot.message_handler(commands=['start'])
@subscription_required
def start(message):
    user_id = str(message.from_user.id)
    
    # Foydalanuvchi ma'lumotlarini initsializatsiya
    if user_id not in user_data:
        user_data[user_id] = {
            'total_score': 0,
            'tests_completed': 0,
            'achievements': [],
            'last_test_date': None,
            'streak': 0,
            'daily_challenge_date': None,
            'username': message.from_user.username or 'Nomalum',
            'first_name': message.from_user.first_name
        }
        save_data()
    
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row('📝 Savollar yuklash', '🎯 Quiz boshlash')
    markup.row('📋 Savollarni ko\'rish', '🏆 Yutuqlar')
    markup.row('📊 Statistika', '🌟 Kunlik vazifa')
    markup.row('🔔 Eslatma', '❓ Yordam')
    
    # Admin uchun qo'shimcha tugma
    if is_admin(message.from_user.id):
        markup.row('👨‍💼 Admin Panel')
    
    level = get_level(user_data[user_id]['total_score'])
    rank = get_rank(level)
    
    bot.send_message(
        message.chat.id,
        f"🎓 <b>Quiz Bot'ga xush kelibsiz!</b>\n\n"
        f"👤 Daraja: {level} {rank}\n"
        f"⭐ Jami ball: {user_data[user_id]['total_score']}\n"
        f"🔥 Ketma-ketlik: {user_data[user_id]['streak']} kun\n\n"
        f"Boshlash uchun tugmalardan foydalaning!",
        parse_mode='HTML',
        reply_markup=markup
    )

# ==================== SAVOLLARNI KO'RISH ====================

@bot.message_handler(commands=['view'])
@bot.message_handler(func=lambda m: m.text == '📋 Savollarni ko\'rish')
@subscription_required
def view_questions(message):
    user_id = str(message.from_user.id)
    
    if user_id not in user_data or 'questions' not in user_data[user_id]:
        bot.send_message(message.chat.id, "❌ Savollar yo'q! /load")
        return
    
    questions = user_data[user_id]['questions']
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📄 Matn", callback_data="view_text"),
        types.InlineKeyboardButton("📤 Fayl", callback_data="view_file")
    )
    
    bot.send_message(
        message.chat.id,
        f"📊 Jami: {len(questions)} ta savol",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data == 'view_text')
def view_text(call):
    user_id = str(call.from_user.id)
    questions = user_data[user_id]['questions']
    
    text = "📚 <b>Savollar</b>\n\n"
    
    for i, q in enumerate(questions[:10], 1):
        text += f"<b>{i}. {q['question']}</b>\n"
        for j, opt in enumerate(q['options']):
            marker = "✅" if j == q['correct'] else "❌"
            text += f"  {marker} {opt}\n"
        if q.get('hint'):
            text += f"  💡 {q['hint']}\n"
        text += "\n"
    
    if len(questions) > 10:
        text += f"... va yana {len(questions) - 10} ta savol"
    
    bot.send_message(call.message.chat.id, text, parse_mode='HTML')
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == 'view_file')
def view_file(call):
    user_id = str(call.from_user.id)
    questions = user_data[user_id]['questions']
    
    content = "SAVOLLAR TO'PLAMI\n" + "=" * 50 + "\n\n"
    
    for i, q in enumerate(questions, 1):
        content += f"{i}. {q['question']}\n"
        for j, opt in enumerate(q['options']):
            marker = "✓" if j == q['correct'] else "✗"
            content += f"   {marker} {opt}\n"
        if q.get('hint'):
            content += f"   💡 {q['hint']}\n"
        content += "\n"
    
    file = content.encode('utf-8')
    bot.send_document(
        call.message.chat.id,
        file,
        visible_file_name="savollar.txt"
    )
    bot.answer_callback_query(call.id)

# ==================== SAVOLLAR YUKLASH ====================

@bot.message_handler(commands=['load'])
@bot.message_handler(func=lambda m: m.text == '📝 Savollar yuklash')
@subscription_required
def load_questions(message):
    user_id = str(message.from_user.id)
    if user_id not in user_data:
        user_data[user_id] = {}
    
    user_data[user_id]['mode'] = 'loading'
    
    bot.send_message(
        message.chat.id,
        "📥 <b>Savollarni yuklash</b>\n\n"
        "<b>Format:</b>\n"
        "<code>? Savol\n"
        "+ To'g'ri javob\n"
        "- Noto'g'ri javob\n"
        "! Hint</code>\n\n"
        "Matn yoki .txt fayl yuboring.\n\n"
        "❌ Bekor: /cancel",
        parse_mode='HTML'
    )

@bot.message_handler(commands=['cancel'])
def cancel(message):
    user_id = str(message.from_user.id)
    if user_id in user_data:
        user_data[user_id]['mode'] = None
    bot.send_message(message.chat.id, "❌ Bekor qilindi.")

@bot.message_handler(content_types=['document'])
def handle_document(message):
    user_id = str(message.from_user.id)
    
    if user_data.get(user_id, {}).get('mode') != 'loading':
        bot.send_message(message.chat.id, "Avval /load yuboring!")
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
    process_questions_text(message, message.text)

def process_questions_text(message, text):
    user_id = str(message.from_user.id)
    
    try:
        questions = quiz_manager.parse_text(text)
        valid_questions = quiz_manager.validate_questions(questions)
        
        if valid_questions:
            user_data[user_id]['questions'] = valid_questions
            user_data[user_id]['mode'] = None
            save_data()
            
            bot.send_message(
                message.chat.id,
                f"✅ Yuklandi!\n\n📊 Savollar: {len(valid_questions)}\n\nQuiz: /quiz"
            )
        else:
            bot.send_message(message.chat.id, "❌ Format xato! /help")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Xatolik: {str(e)}")

# ==================== QUIZ BOSHLASH ====================

@bot.message_handler(commands=['quiz'])
@bot.message_handler(func=lambda m: m.text == '🎯 Quiz boshlash')
@subscription_required
def start_quiz(message):
    user_id = str(message.from_user.id)
    
    if user_id not in user_data or 'questions' not in user_data[user_id]:
        bot.send_message(message.chat.id, "❌ Savollar yo'q! /load")
        return
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("⏱️ Vaqt bilan", callback_data="timer_yes"),
        types.InlineKeyboardButton("⏸️ Vaqtsiz", callback_data="timer_no")
    )
    
    bot.send_message(
        message.chat.id,
        "⚙️ <b>Sozlamalar</b>\n\nVaqt chegarasi (30s)?",
        reply_markup=markup,
        parse_mode='HTML'
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('timer_'))
def set_timer(call):
    user_id = str(call.from_user.id)
    has_timer = call.data.split('_')[1] == 'yes'
    user_data[user_id]['has_timer'] = has_timer
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("❤️ Hayot bilan", callback_data="lives_yes"),
        types.InlineKeyboardButton("♾️ Cheksiz", callback_data="lives_no")
    )
    
    bot.edit_message_text(
        "⚙️ <b>Sozlamalar</b>\n\nHayot tizimi (3 hayot)?",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=markup,
        parse_mode='HTML'
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('lives_'))
def set_lives(call):
    user_id = str(call.from_user.id)
    has_lives = call.data.split('_')[1] == 'yes'
    user_data[user_id]['has_lives'] = has_lives
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🔀 Aralash", callback_data="qmode_random"),
        types.InlineKeyboardButton("📋 Tartib", callback_data="qmode_sequential")
    )
    
    bot.edit_message_text(
        "Savollar tartibini tanlang:",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('qmode_'))
def choose_question_mode(call):
    user_id = str(call.from_user.id)
    mode = call.data.split('_')[1]
    user_data[user_id]['question_mode'] = mode
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🎲 Aralash", callback_data="amode_shuffle"),
        types.InlineKeyboardButton("📌 Asl", callback_data="amode_original")
    )
    
    bot.edit_message_text(
        "Javoblar tartibini tanlang:",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('amode_'))
def choose_answer_mode(call):
    user_id = str(call.from_user.id)
    mode = call.data.split('_')[1]
    user_data[user_id]['answer_mode'] = mode
    
    start_quiz_game(call)

def start_quiz_game(call):
    user_id = str(call.from_user.id)
    
    questions = user_data[user_id]['questions'][:]
    
    if user_data[user_id]['question_mode'] == 'random':
        random.shuffle(questions)
    
    if user_data[user_id]['answer_mode'] == 'shuffle':
        for q in questions:
            correct_answer = q['options'][q['correct']]
            random.shuffle(q['options'])
            q['correct'] = q['options'].index(correct_answer)
    
    user_data[user_id]['quiz_questions'] = questions
    user_data[user_id]['current_question'] = 0
    user_data[user_id]['score'] = 0
    user_data[user_id]['wrong_answers'] = []
    user_data[user_id]['used_hints'] = []
    user_data[user_id]['lives'] = 3 if user_data[user_id]['has_lives'] else None
    user_data[user_id]['start_time'] = time.time()
    
    bot.send_message(call.message.chat.id, "✅ Quiz boshlandi!")
    send_question(call.message.chat.id, user_id)

def send_question(chat_id, user_id):
    current = user_data[user_id]['current_question']
    questions = user_data[user_id]['quiz_questions']
    
    if current >= len(questions):
        show_results(chat_id, user_id)
        return
    
    if user_data[user_id]['lives'] is not None and user_data[user_id]['lives'] <= 0:
        bot.send_message(chat_id, "💔 Hayotlar tugadi!")
        show_results(chat_id, user_id)
        return
    
    q = questions[current]
    markup = types.InlineKeyboardMarkup(row_width=1)
    
    for i, option in enumerate(q['options']):
        button = types.InlineKeyboardButton(text=option, callback_data=f"ans_{current}_{i}")
        markup.add(button)
    
    help_buttons = []
    if q.get('hint') and current not in user_data[user_id]['used_hints']:
        help_buttons.append(types.InlineKeyboardButton("💡 Hint", callback_data=f"hint_{current}"))
    
    if len(q['options']) > 2:
        help_buttons.append(types.InlineKeyboardButton("🎲 50:50", callback_data=f"fifty_{current}"))
    
    if help_buttons:
        markup.row(*help_buttons)
    
    progress = f"{current + 1}/{len(questions)}"
    lives_text = ""
    
    if user_data[user_id]['lives'] is not None:
        hearts = "❤️" * user_data[user_id]['lives']
        lives_text = f" | {hearts}"
    
    timer_text = ""
    if user_data[user_id]['has_timer']:
        timer_text = "\n⏱️ Vaqt: 30s"
    
    question_text = f"📊 {progress}{lives_text}{timer_text}\n\n❓ <b>{q['question']}</b>"
    
    bot.send_message(chat_id, question_text, reply_markup=markup, parse_mode='HTML')

@bot.callback_query_handler(func=lambda call: call.data.startswith('hint_'))
def show_hint(call):
    user_id = str(call.from_user.id)
    q_num = int(call.data.split('_')[1])
    
    question = user_data[user_id]['quiz_questions'][q_num]
    hint = question.get('hint', 'Hint yo\'q')
    
    user_data[user_id]['used_hints'].append(q_num)
    bot.answer_callback_query(call.id, f"💡 {hint}", show_alert=True)

@bot.callback_query_handler(func=lambda call: call.data.startswith('fifty_'))
def use_fifty_fifty(call):
    user_id = str(call.from_user.id)
    q_num = int(call.data.split('_')[1])
    
    question = user_data[user_id]['quiz_questions'][q_num]
    correct = question['correct']
    
    wrong_indices = [i for i in range(len(question['options'])) if i != correct]
    to_remove = random.sample(wrong_indices, min(2, len(wrong_indices)))
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    for i, option in enumerate(question['options']):
        if i not in to_remove:
            button = types.InlineKeyboardButton(text=option, callback_data=f"ans_{q_num}_{i}")
            markup.add(button)
    
    bot.edit_message_reply_markup(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=markup
    )
    bot.answer_callback_query(call.id, "🎲 50:50 ishlatildi!")

@bot.callback_query_handler(func=lambda call: call.data.startswith('ans_'))
def check_answer(call):
    user_id = str(call.from_user.id)
    
    if user_id not in user_data or 'quiz_questions' not in user_data[user_id]:
        bot.answer_callback_query(call.id, "Quiz topilmadi!")
        return
    
    data = call.data.split('_')
    q_num = int(data[1])
    user_answer = int(data[2])
    
    question = user_data[user_id]['quiz_questions'][q_num]
    correct = question['correct']
    
    if user_answer == correct:
        user_data[user_id]['score'] += 1
        bot.answer_callback_query(call.id, "✅ To'g'ri!")
        emoji = "✅"
        result_text = "To'g'ri!"
    else:
        if user_data[user_id]['lives'] is not None:
            user_data[user_id]['lives'] -= 1
        
        user_data[user_id]['wrong_answers'].append({
            'question': question,
            'user_answer': question['options'][user_answer]
        })
        
        bot.answer_callback_query(call.id, "❌ Noto'g'ri!")
        emoji = "❌"
        result_text = f"Noto'g'ri!\nTo'g'ri: {question['options'][correct]}"
    
    bot.edit_message_text(
        f"{call.message.text}\n\n{emoji} {result_text}",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        parse_mode='HTML'
    )
    
    user_data[user_id]['current_question'] += 1
    send_question(call.message.chat.id, user_id)

def show_results(chat_id, user_id):
    score = user_data[user_id]['score']
    total = len(user_data[user_id]['quiz_questions'])
    percentage = (score / total) * 100
    
    elapsed_time = int(time.time() - user_data[user_id]['start_time'])
    minutes = elapsed_time // 60
    seconds = elapsed_time % 60
    
    earned_points = score * 10
    user_data[user_id]['total_score'] += earned_points
    user_data[user_id]['tests_completed'] += 1
    
    today = str(datetime.now().date())
    last_date = user_data[user_id].get('last_test_date')
    
    if last_date:
        try:
            last = datetime.strptime(last_date, '%Y-%m-%d').date()
            if (datetime.now().date() - last).days == 1:
                user_data[user_id]['streak'] += 1
            elif (datetime.now().date() - last).days > 1:
                user_data[user_id]['streak'] = 1
        except:
            user_data[user_id]['streak'] = 1
    else:
        user_data[user_id]['streak'] = 1
    
    user_data[user_id]['last_test_date'] = today
    
    new_achievements = check_achievements(user_id, score, total, elapsed_time)
    if new_achievements:
        user_data[user_id]['achievements'].extend(new_achievements)
    
    save_data()
    
    level = get_level(user_data[user_id]['total_score'])
    rank = get_rank(level)
    
    if percentage >= 90:
        grade = "⭐️⭐️⭐️ A'lo!"
    elif percentage >= 70:
        grade = "⭐️⭐️ Yaxshi!"
    elif percentage >= 50:
        grade = "⭐️ Qoniqarli"
    else:
        grade = "📚 Takror qiling"
    
    result = (
        f"🎉 <b>Quiz yakunlandi!</b>\n\n"
        f"📊 Natija: {score}/{total} ({percentage:.1f}%)\n"
        f"⏱️ Vaqt: {minutes}:{seconds:02d}\n"
        f"🏆 Baho: {grade}\n\n"
        f"💰 +{earned_points} ball\n"
        f"📊 Jami: {user_data[user_id]['total_score']}\n"
        f"🎯 Daraja: {level} {rank}\n"
        f"🔥 Ketma-ketlik: {user_data[user_id]['streak']} kun\n"
    )
    
    if new_achievements:
        result += f"\n🏆 <b>Yangi yutuqlar:</b>\n"
        for ach in new_achievements:
            result += f"{ACHIEVEMENTS[ach]['icon']} {ACHIEVEMENTS[ach]['name']}\n"
    
    wrong_count = len(user_data[user_id]['wrong_answers'])
    if wrong_count > 0:
        result += f"\n❌ Xato: {wrong_count}\n"
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    
    if wrong_count > 0:
        markup.add(
            types.InlineKeyboardButton("❌ Xatolar", callback_data="show_wrong"),
            types.InlineKeyboardButton("🔄 Takrorlash", callback_data="retry_wrong")
        )
    
    markup.add(
        types.InlineKeyboardButton("📊 Statistika", callback_data="show_stats"),
        types.InlineKeyboardButton("🎓 Sertifikat", callback_data="get_certificate")
    )
    
    bot.send_message(chat_id, result, reply_markup=markup, parse_mode='HTML')

@bot.callback_query_handler(func=lambda call: call.data == 'show_wrong')
def show_wrong_answers(call):
    user_id = str(call.from_user.id)
    wrong_answers = user_data[user_id]['wrong_answers']
    
    if not wrong_answers:
        bot.answer_callback_query(call.id, "Xato yo'q!")
        return
    
    text = "❌ <b>Xato javoblar:</b>\n\n"
    
    for i, item in enumerate(wrong_answers, 1):
        q = item['question']
        text += f"<b>{i}. {q['question']}</b>\n"
        text += f"Sizning: {item['user_answer']}\n"
        text += f"To'g'ri: {q['options'][q['correct']]}\n"
        if q.get('hint'):
            text += f"💡 {q['hint']}\n"
        text += "\n"
    
    bot.send_message(call.message.chat.id, text, parse_mode='HTML')
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == 'retry_wrong')
def retry_wrong_answers(call):
    user_id = str(call.from_user.id)
    wrong_answers = user_data[user_id]['wrong_answers']
    
    if not wrong_answers:
        bot.answer_callback_query(call.id, "Xato yo'q!")
        return
    
    questions = [item['question'] for item in wrong_answers]
    
    user_data[user_id]['quiz_questions'] = questions
    user_data[user_id]['current_question'] = 0
    user_data[user_id]['score'] = 0
    user_data[user_id]['wrong_answers'] = []
    user_data[user_id]['used_hints'] = []
    user_data[user_id]['lives'] = None
    user_data[user_id]['has_timer'] = False
    user_data[user_id]['start_time'] = time.time()
    
    bot.send_message(call.message.chat.id, f"🔄 Takrorlash!\n📊 Savollar: {len(questions)}")
    send_question(call.message.chat.id, user_id)
    bot.answer_callback_query(call.id)

# ==================== STATISTIKA ====================

@bot.message_handler(commands=['stats'])
@bot.message_handler(func=lambda m: m.text == '📊 Statistika')
@bot.callback_query_handler(func=lambda call: call.data == 'show_stats')
@subscription_required
def show_stats(message_or_call):
    if isinstance(message_or_call, types.CallbackQuery):
        user_id = str(message_or_call.from_user.id)
        chat_id = message_or_call.message.chat.id
        is_callback = True
    else:
        user_id = str(message_or_call.from_user.id)
        chat_id = message_or_call.chat.id
        is_callback = False
    
    if user_id not in user_data:
        text = "📊 Hali statistika yo'q!"
        if is_callback:
            bot.answer_callback_query(message_or_call.id, text)
        else:
            bot.send_message(chat_id, text)
        return
    
    level = get_level(user_data[user_id]['total_score'])
    rank = get_rank(level)
    next_level = level * 100
    progress = user_data[user_id]['total_score'] % 100
    
    text = (
        f"📊 <b>Statistikangiz</b>\n\n"
        f"👤 Daraja: {level} {rank}\n"
        f"⭐ Jami: {user_data[user_id]['total_score']}\n"
        f"📈 Keyingi: {progress}/100\n"
        f"🎯 Testlar: {user_data[user_id]['tests_completed']}\n"
        f"🔥 Ketma-ketlik: {user_data[user_id]['streak']} kun\n"
        f"🏆 Yutuqlar: {len(user_data[user_id].get('achievements', []))}/{len(ACHIEVEMENTS)}\n"
    )
    
    if is_callback:
        bot.send_message(chat_id, text, parse_mode='HTML')
        bot.answer_callback_query(message_or_call.id)
    else:
        bot.send_message(chat_id, text, parse_mode='HTML')

# ==================== YUTUQLAR ====================

@bot.message_handler(commands=['achievements'])
@bot.message_handler(func=lambda m: m.text == '🏆 Yutuqlar')
@subscription_required
def show_achievements(message):
    user_id = str(message.from_user.id)
    
    if user_id not in user_data:
        user_data[user_id] = {'achievements': []}
    
    achievements = user_data[user_id].get('achievements', [])
    
    text = "🏆 <b>Yutuqlar</b>\n\n"
    
    if achievements:
        text += "<b>Sizning yutuqlaringiz:</b>\n"
        for ach in achievements:
            info = ACHIEVEMENTS[ach]
            text += f"{info['icon']} <b>{info['name']}</b>\n{info['desc']}\n\n"
    else:
        text += "Hali yutuqlar yo'q!\n\n"
    
    text += "<b>Barcha yutuqlar:</b>\n"
    for key, info in ACHIEVEMENTS.items():
        if key in achievements:
            text += f"✅ {info['icon']} {info['name']}\n"
        else:
            text += f"🔒 {info['icon']} {info['name']}\n"
    
    bot.send_message(message.chat.id, text, parse_mode='HTML')

# ==================== SERTIFIKAT ====================

@bot.callback_query_handler(func=lambda call: call.data == 'get_certificate')
def generate_certificate(call):
    user_id = str(call.from_user.id)
    user_name = call.from_user.first_name
    
    score = user_data[user_id]['score']
    total = len(user_data[user_id]['quiz_questions'])
    percentage = (score / total) * 100
    
    if percentage < 70:
        bot.answer_callback_query(call.id, "❌ Sertifikat uchun kamida 70% kerak!", show_alert=True)
        return
    
    level = get_level(user_data[user_id]['total_score'])
    rank = get_rank(level)
    
    certificate = f"""
═══════════════════════════════════
           🎓 SERTIFIKAT 🎓
═══════════════════════════════════

Bu sertifikat quyidagi shaxsga beriladi:

           {user_name}

Quiz botda muvaffaqiyatli test topshirganligi uchun

📊 Natija: {score}/{total} ({percentage:.1f}%)
🎯 Daraja: {level} {rank}
⭐ Jami ball: {user_data[user_id]['total_score']}
📅 Sana: {datetime.now().strftime('%d.%m.%Y')}

═══════════════════════════════════
           Quiz Bot © 2025
═══════════════════════════════════
    """
    
    bot.send_message(call.message.chat.id, f"<pre>{certificate}</pre>", parse_mode='HTML')
    bot.answer_callback_query(call.id, "✅ Sertifikat yuborildi!")

# ==================== KUNLIK VAZIFA ====================

@bot.message_handler(commands=['daily'])
@bot.message_handler(func=lambda m: m.text == '🌟 Kunlik vazifa')
@subscription_required
def daily_challenge(message):
    user_id = str(message.from_user.id)
    
    if user_id not in user_data:
        user_data[user_id] = {}
    
    today = str(datetime.now().date())
    last_daily = user_data[user_id].get('daily_challenge_date')
    
    if last_daily == today:
        bot.send_message(
            message.chat.id,
            "✅ Bugungi vazifani bajardingiz!\n🔄 Ertaga qaytadan."
        )
        return
    
    if 'questions' not in user_data[user_id] or len(user_data[user_id]['questions']) < 5:
        bot.send_message(message.chat.id, "❌ Kamida 5 ta savol kerak!")
        return
    
    all_questions = user_data[user_id]['questions']
    daily_questions = random.sample(all_questions, min(5, len(all_questions)))
    
    user_data[user_id]['quiz_questions'] = daily_questions
    user_data[user_id]['current_question'] = 0
    user_data[user_id]['score'] = 0
    user_data[user_id]['wrong_answers'] = []
    user_data[user_id]['used_hints'] = []
    user_data[user_id]['lives'] = None
    user_data[user_id]['has_timer'] = True
    user_data[user_id]['start_time'] = time.time()
    user_data[user_id]['daily_challenge_date'] = today
    
    save_data()
    
    bot.send_message(
        message.chat.id,
        "🌟 <b>Kunlik vazifa!</b>\n\n"
        "📊 5 ta savol\n"
        "⏱️ Vaqt: 30s\n"
        "💰 Bonus: +50 ball\n\n"
        "Boshlaylik!",
        parse_mode='HTML'
    )
    
    send_question(message.chat.id, user_id)

# ==================== ESLATMA ====================

@bot.message_handler(commands=['reminder'])
@bot.message_handler(func=lambda m: m.text == '🔔 Eslatma')
@subscription_required
def set_reminder(message):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🌅 9:00", callback_data="reminder_9"),
        types.InlineKeyboardButton("☀️ 12:00", callback_data="reminder_12")
    )
    markup.add(
        types.InlineKeyboardButton("🌆 18:00", callback_data="reminder_18"),
        types.InlineKeyboardButton("🌙 21:00", callback_data="reminder_21")
    )
    markup.add(
        types.InlineKeyboardButton("❌ O'chirish", callback_data="reminder_off")
    )
    
    bot.send_message(
        message.chat.id,
        "🔔 <b>Kunlik eslatma</b>\n\nQachon eslatma yuborishimni xohlaysiz?",
        reply_markup=markup,
        parse_mode='HTML'
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('reminder_'))
def handle_reminder(call):
    user_id = str(call.from_user.id)
    action = call.data.split('_')[1]
    
    if action == 'off':
        if user_id in user_data:
            user_data[user_id]['reminder_time'] = None
            save_data()
        bot.answer_callback_query(call.id, "🔕 Eslatma o'chirildi!")
    else:
        hour = int(action)
        if user_id not in user_data:
            user_data[user_id] = {}
        user_data[user_id]['reminder_time'] = hour
        save_data()
        bot.answer_callback_query(call.id, f"✅ Eslatma: {hour}:00")
    
    bot.edit_message_text(
        "✅ Sozlamalar saqlandi!",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id
    )

# ==================== TOZALASH ====================

@bot.message_handler(commands=['clear'])
def clear_data(message):
    user_id = str(message.from_user.id)
    
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("🗑 Savollar", callback_data="clear_questions")
    )
    markup.add(
        types.InlineKeyboardButton("⚠️ Hamma narsani", callback_data="clear_all")
    )
    
    bot.send_message(message.chat.id, "Nimani tozalash kerak?", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('clear_'))
def handle_clear(call):
    user_id = str(call.from_user.id)
    action = call.data.split('_')[1]
    
    if action == 'questions':
        if 'questions' in user_data.get(user_id, {}):
            del user_data[user_id]['questions']
            save_data()
        bot.answer_callback_query(call.id, "🗑 Tozalandi!")
    
    elif action == 'all':
        if user_id in user_data:
            # Faqat savollarni tozalash, statistikani saqlab qolish
            if 'questions' in user_data[user_id]:
                del user_data[user_id]['questions']
            save_data()
        bot.answer_callback_query(call.id, "✅ Savollar tozalandi!")
    
    bot.edit_message_text("✅ Tozalandi!", chat_id=call.message.chat.id, message_id=call.message.message_id)

# ==================== REYTING ====================

@bot.message_handler(commands=['ranking'])
def show_ranking(message):
    rankings = []
    for uid, data in user_data.items():
        if 'total_score' in data:
            rankings.append({
                'user_id': uid,
                'name': data.get('first_name', 'Nomalum'),
                'score': data['total_score'],
                'level': get_level(data['total_score'])
            })
    
    rankings.sort(key=lambda x: x['score'], reverse=True)
    
    text = "🏆 <b>Top Reyting</b>\n\n"
    
    if rankings:
        for i, rank in enumerate(rankings[:10], 1):
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
            rank_name = get_rank(rank['level'])
            text += f"{medal} {rank['name']} - Daraja {rank['level']} {rank_name} ({rank['score']} ball)\n"
    else:
        text += "Hali reyting yo'q!"
    
    bot.send_message(message.chat.id, text, parse_mode='HTML')

# ==================== ADMIN SOZLAMALARI ====================

@bot.message_handler(commands=['setup'])
def setup_bot(message):
    """Bot sozlamalarini o'rnatish"""
    user_id = message.from_user.id
    
    # Kanal ID ni aniqlash
    if message.chat.type in ['group', 'supergroup', 'channel']:
        global CHANNEL_ID
        CHANNEL_ID = message.chat.id
        save_config()
        
        bot.send_message(
            message.chat.id,
            f"✅ <b>Kanal ID aniqlandi!</b>\n\n"
            f"📢 Kanal ID: <code>{CHANNEL_ID}</code>\n\n"
            f"Endi /addadmin buyrug'i bilan admin qo'shing.",
            parse_mode='HTML'
        )
    else:
        bot.send_message(
            message.chat.id,
            "⚠️ Bu buyruq faqat guruh/kanalda ishlaydi!\n\n"
            "1. Botni kanalingizga admin qiling\n"
            "2. Kanalda /setup buyrug'ini yuboring"
        )

@bot.message_handler(commands=['addadmin'])
def add_admin(message):
    """Admin qo'shish"""
    user_id = message.from_user.id
    
    # Birinchi admin
    if not ADMIN_IDS:
        ADMIN_IDS.append(user_id)
        save_config()
        bot.send_message(
            message.chat.id,
            f"✅ <b>Birinchi admin qo'shildi!</b>\n\n"
            f"👤 Admin ID: <code>{user_id}</code>\n\n"
            f"Endi botdan foydalanishingiz mumkin!",
            parse_mode='HTML'
        )
        return
    
    # Faqat adminlar yangi admin qo'sha oladi
    if not is_admin(user_id):
        bot.send_message(message.chat.id, "❌ Bu buyruq faqat adminlar uchun!")
        return
    
    # Reply orqali admin qo'shish
    if message.reply_to_message:
        new_admin_id = message.reply_to_message.from_user.id
        if new_admin_id not in ADMIN_IDS:
            ADMIN_IDS.append(new_admin_id)
            save_config()
            bot.send_message(
                message.chat.id,
                f"✅ Admin qo'shildi!\n\n"
                f"👤 ID: <code>{new_admin_id}</code>",
                parse_mode='HTML'
            )
        else:
            bot.send_message(message.chat.id, "⚠️ Bu foydalanuvchi allaqachon admin!")
    else:
        bot.send_message(
            message.chat.id,
            "📝 Admin qo'shish:\n\n"
            "1. Foydalanuvchining xabariga reply qiling\n"
            "2. /addadmin buyrug'ini yuboring"
        )

@bot.message_handler(commands=['myid'])
def my_id(message):
    """Foydalanuvchi ID sini ko'rsatish"""
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    text = (
        f"🆔 <b>Sizning ma'lumotlaringiz:</b>\n\n"
        f"👤 User ID: <code>{user_id}</code>\n"
        f"💬 Chat ID: <code>{chat_id}</code>\n"
    )
    
    if message.chat.type in ['group', 'supergroup', 'channel']:
        text += f"📢 Chat Type: {message.chat.type}\n"
    
    if is_admin(user_id):
        text += f"\n✅ Siz adminsiz!"
    
    bot.send_message(message.chat.id, text, parse_mode='HTML')

@bot.message_handler(commands=['admins'])
def show_admins(message):
    """Adminlar ro'yxati"""
    if not ADMIN_IDS:
        bot.send_message(message.chat.id, "👨‍💼 Hali adminlar yo'q.\n\n/addadmin - Admin qo'shish")
        return
    
    text = "👨‍💼 <b>Adminlar ro'yxati:</b>\n\n"
    for admin_id in ADMIN_IDS:
        text += f"• <code>{admin_id}</code>\n"
    
    bot.send_message(message.chat.id, text, parse_mode='HTML')

# ==================== ADMIN PANEL ====================

@bot.message_handler(func=lambda m: m.text == '👨‍💼 Admin Panel')
def admin_panel(message):
    if not is_admin(message.from_user.id):
        bot.send_message(message.chat.id, "❌ Bu bo'lim faqat adminlar uchun!")
        return
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📊 Statistika", callback_data="admin_stats"),
        types.InlineKeyboardButton("👥 Foydalanuvchilar", callback_data="admin_users")
    )
    markup.add(
        types.InlineKeyboardButton("📢 Xabar yuborish", callback_data="admin_broadcast"),
        types.InlineKeyboardButton("💾 Backup", callback_data="admin_backup")
    )
    markup.add(
        types.InlineKeyboardButton("📥 Export", callback_data="admin_export"),
        types.InlineKeyboardButton("⚙️ Sozlamalar", callback_data="admin_settings")
    )
    
    bot.send_message(
        message.chat.id,
        "👨‍💼 <b>Admin Panel</b>\n\nAmallarni tanlang:",
        reply_markup=markup,
        parse_mode='HTML'
    )

@bot.callback_query_handler(func=lambda call: call.data == 'admin_stats')
def admin_stats(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "❌ Ruxsat yo'q!")
        return
    
    total_users = len(user_data)
    total_tests = sum(u.get('tests_completed', 0) for u in user_data.values())
    total_score = sum(u.get('total_score', 0) for u in user_data.values())
    
    active_today = 0
    today = str(datetime.now().date())
    for u in user_data.values():
        if u.get('last_test_date') == today:
            active_today += 1
    
    text = (
        f"📊 <b>Bot statistikasi</b>\n\n"
        f"👥 Jami foydalanuvchilar: {total_users}\n"
        f"🎯 Jami testlar: {total_tests}\n"
        f"⭐ Jami ballar: {total_score}\n"
        f"🔥 Bugun faol: {active_today}\n"
        f"👨‍💼 Adminlar: {len(ADMIN_IDS)}\n"
    )
    
    bot.send_message(call.message.chat.id, text, parse_mode='HTML')
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == 'admin_users')
def admin_users(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "❌ Ruxsat yo'q!")
        return
    
    text = "👥 <b>Top 10 foydalanuvchilar</b>\n\n"
    
    sorted_users = sorted(
        user_data.items(),
        key=lambda x: x[1].get('total_score', 0),
        reverse=True
    )[:10]
    
    for i, (uid, data) in enumerate(sorted_users, 1):
        name = data.get('first_name', 'Nomalum')
        score = data.get('total_score', 0)
        level = get_level(score)
        text += f"{i}. {name} - Daraja {level} ({score} ball)\n"
    
    bot.send_message(call.message.chat.id, text, parse_mode='HTML')
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == 'admin_broadcast')
def admin_broadcast(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "❌ Ruxsat yo'q!")
        return
    
    user_data[str(call.from_user.id)]['mode'] = 'broadcast'
    
    bot.send_message(
        call.message.chat.id,
        "📢 <b>Xabar yuborish</b>\n\n"
        "Barcha foydalanuvchilarga yubormoqchi bo'lgan xabaringizni yuboring.\n\n"
        "❌ Bekor: /cancel",
        parse_mode='HTML'
    )
    bot.answer_callback_query(call.id)

@bot.message_handler(func=lambda m: user_data.get(str(m.from_user.id), {}).get('mode') == 'broadcast')
def handle_broadcast(message):
    if not is_admin(message.from_user.id):
        return
    
    broadcast_text = message.text
    success = 0
    failed = 0
    
    status_msg = bot.send_message(message.chat.id, "📤 Xabar yuborilmoqda...")
    
    for user_id in user_data.keys():
        try:
            bot.send_message(int(user_id), broadcast_text)
            success += 1
            time.sleep(0.05)  # Spam oldini olish
        except:
            failed += 1
    
    user_data[str(message.from_user.id)]['mode'] = None
    
    bot.edit_message_text(
        f"✅ <b>Xabar yuborildi!</b>\n\n"
        f"✅ Muvaffaqiyatli: {success}\n"
        f"❌ Xato: {failed}",
        chat_id=message.chat.id,
        message_id=status_msg.message_id,
        parse_mode='HTML'
    )

@bot.callback_query_handler(func=lambda call: call.data == 'admin_backup')
def admin_backup(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "❌ Ruxsat yo'q!")
        return
    
    try:
        save_data()  # Avval saqlash
        with open(DATA_FILE, 'rb') as f:
            bot.send_document(
                call.message.chat.id,
                f,
                caption=f"💾 Backup - {datetime.now().strftime('%d.%m.%Y %H:%M')}"
            )
        bot.answer_callback_query(call.id, "✅ Backup yuborildi!")
    except Exception as e:
        bot.answer_callback_query(call.id, f"❌ Xatolik: {e}")

@bot.callback_query_handler(func=lambda call: call.data == 'admin_export')
def admin_export(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "❌ Ruxsat yo'q!")
        return
    
    text = "👥 FOYDALANUVCHILAR RO'YXATI\n"
    text += f"Sana: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n"
    text += "=" * 50 + "\n\n"
    
    for uid, data in user_data.items():
        name = data.get('first_name', 'Nomalum')
        username = data.get('username', 'Nomalum')
        score = data.get('total_score', 0)
        tests = data.get('tests_completed', 0)
        level = get_level(score)
        
        text += f"ID: {uid}\n"
        text += f"Ism: {name}\n"
        text += f"Username: @{username}\n"
        text += f"Daraja: {level}\n"
        text += f"Ball: {score}\n"
        text += f"Testlar: {tests}\n"
        text += "-" * 30 + "\n\n"
    
    file = text.encode('utf-8')
    bot.send_document(
        call.message.chat.id,
        file,
        visible_file_name=f"users_{datetime.now().strftime('%Y%m%d_%H%M')}.txt",
        caption="📥 Foydalanuvchilar ro'yxati"
    )
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == 'admin_settings')
def admin_settings(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "❌ Ruxsat yo'q!")
        return
    
    text = (
        f"⚙️ <b>Bot sozlamalari</b>\n\n"
        f"📢 Kanal: {CHANNEL_USERNAME}\n"
        f"🆔 Kanal ID: <code>{CHANNEL_ID or 'Sozlanmagan'}</code>\n"
        f"👨‍💼 Adminlar: {len(ADMIN_IDS)}\n\n"
        f"<b>Sozlash:</b>\n"
        f"/setup - Kanal ID ni sozlash\n"
        f"/addadmin - Admin qo'shish\n"
        f"/admins - Adminlar ro'yxati"
    )
    
    bot.send_message(call.message.chat.id, text, parse_mode='HTML')
    bot.answer_callback_query(call.id)

# ==================== OBUNA TEKSHIRISH ====================

@bot.callback_query_handler(func=lambda call: call.data == 'check_sub')
def check_subscription_callback(call):
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

# ==================== YORDAM ====================

@bot.message_handler(commands=['help'])
@bot.message_handler(func=lambda m: m.text == '❓ Yordam')
@subscription_required
def help_command(message):
    help_text = """
📚 <b>Qo'llanma</b>

<b>Format:</b>
? Savol
+ To'g'ri javob
- Noto'g'ri javob
! Hint

<b>Misol:</b>
? Python qaysi yilda yaratilgan?
- 1989
+ 1991
- 1995
! Python 1991-yilda yaratilgan

<b>Buyruqlar:</b>
/start - Boshlash
/myid - ID ni ko'rish
/load - Savollar yuklash
/quiz - Quiz boshlash
/achievements - Yutuqlar
/daily - Kunlik vazifa

<b>Admin:</b>
/setup - Kanal ID
/addadmin - Admin qo'shish
/admins - Adminlar ro'yxati
    """
    bot.send_message(message.chat.id, help_text, parse_mode='HTML')

# ==================== AVTOMATIK SAQLASH ====================

def auto_save_loop():
    """Har 5 daqiqada avtomatik saqlash"""
    while True:
        time.sleep(300)  # 5 daqiqa
        try:
            save_data()
            print(f"💾 Avtomatik saqlash: {datetime.now().strftime('%H:%M:%S')}")
        except Exception as e:
            print(f"❌ Avtomatik saqlash xatosi: {e}")

# ==================== BOTNI ISHGA TUSHIRISH ====================

if __name__ == '__main__':
    print("=" * 60)
    print("🤖 QUIZ BOT ISHGA TUSHMOQDA...")
    print("=" * 60)
    
    print("\n📁 Konfiguratsiya yuklanmoqda...")
    load_config()
    
    print("📁 Ma'lumotlar bazasi yuklanmoqda...")
    load_data()
    
    print("\n✅ BOT TAYYOR!")
    print(f"👥 Foydalanuvchilar: {len(user_data)}")
    print(f"👨‍💼 Adminlar: {len(ADMIN_IDS)}")
    print(f"📢 Kanal: {CHANNEL_USERNAME}")
    print(f"🆔 Kanal ID: {CHANNEL_ID or 'Sozlanmagan'}")
    
    if not ADMIN_IDS:
        print("\n⚠️  DIQQAT! Admin yo'q!")
        print("📝 Admin qo'shish:")
        print("   1. /addadmin buyrug'ini yuboring")
        print("   2. Avtomatik birinchi admin bo'lasiz")
    
    if not CHANNEL_ID:
        print("\n⚠️  DIQQAT! Kanal ID sozlanmagan!")
        print("📝 Kanal ID ni sozlash:")
        print("   1. Botni kanalingizga admin qiling")
        print("   2. Kanalda /setup buyrug'ini yuboring")
    
    print("\n" + "=" * 60)
    print("🎯 FUNKSIYALAR:")
    print("=" * 60)
    print("  ⏱️  Vaqt chegarasi (30s)")
    print("  📝 Xato javoblarni takrorlash")
    print("  💡 Yordam (Hint, 50:50)")
    print("  ❤️  Hayot tizimi (3 hayot)")
    print("  🏆 Yutuqlar tizimi")
    print("  📈 Reyting")
    print("  🎚️  Darajalar (Beginner → Master)")
    print("  🌟 Kunlik vazifa")
    print("  🔔 Eslatmalar")
    print("  🎓 Sertifikat")
    print("  📢 Majburiy obuna")
    print("  👨‍💼 Admin panel")
    print("  💾 Offline baza (JSON)")
    print("=" * 60)
    
    print("\n📋 ADMIN BUYRUQLARI:")
    print("=" * 60)
    print("  /setup - Kanal ID ni aniqlash")
    print("  /addadmin - Admin qo'shish")
    print("  /admins - Adminlar ro'yxati")
    print("  /myid - ID ni ko'rish")
    print("  👨‍💼 Admin Panel - Asosiy panel")
    print("=" * 60)
    
    print("\n📋 ODDIY BUYRUQLAR:")
    print("=" * 60)
    print("  /start - Boshlash")
    print("  /load - Savollar yuklash")
    print("  /quiz - Quiz boshlash")
    print("  /view - Savollarni ko'rish")
    print("  /stats - Statistika")
    print("  /achievements - Yutuqlar")
    print("  /daily - Kunlik vazifa")
    print("  /ranking - Reyting")
    print("  /reminder - Eslatma")
    print("  /help - Yordam")
    print("=" * 60)
    
    print("\n🔄 Bot ishlayapti... (To'xtatish uchun Ctrl+C)")
    print("💾 Ma'lumotlar avtomatik saqlanadi (har 5 daqiqada)")
    print("=" * 60 + "\n")
    
    # Avtomatik saqlashni alohida thread'da ishga tushirish
    import threading
    save_thread = threading.Thread(target=auto_save_loop, daemon=True)
    save_thread.start()
    
    try:
        bot.infinity_polling(timeout=60, long_polling_timeout=60)
    except KeyboardInterrupt:
        print("\n\n" + "=" * 60)
        print("⏸️  Bot to'xtatilmoqda...")
        print("=" * 60)
    finally:
        print("💾 Ma'lumotlar saqlanmoqda...")
        save_data()
        save_config()
        print("✅ Ma'lumotlar saqlandi!")
        print("👋 Bot to'xtatildi!")
        print("=" * 60)