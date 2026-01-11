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

# Ma'lumotlar fayllari
DATA_FILE = "quiz_data.json"
GROUP_DATA_FILE = "group_data.json"

# Foydalanuvchilar va guruhlar ma'lumotlari
user_data = {}
group_data = {}
active_timers = {}  # Faol timerlar

# ==================== MA'LUMOTLARNI BOSHQARISH ====================

def load_data():
    """JSON fayldan ma'lumotlarni yuklash"""
    global user_data, group_data
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                user_data = json.load(f)
            print(f"✅ User data yuklandi: {len(user_data)} foydalanuvchi")
        else:
            user_data = {}
            
        if os.path.exists(GROUP_DATA_FILE):
            with open(GROUP_DATA_FILE, 'r', encoding='utf-8') as f:
                group_data = json.load(f)
            print(f"✅ Group data yuklandi: {len(group_data)} guruh")
        else:
            group_data = {}
            
        clean_old_data()
    except Exception as e:
        print(f"❌ Ma'lumotlar yuklashda xatolik: {e}")
        user_data = {}
        group_data = {}

def save_data():
    """JSON faylga ma'lumotlarni saqlash"""
    try:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(user_data, f, ensure_ascii=False, indent=2)
        with open(GROUP_DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(group_data, f, ensure_ascii=False, indent=2)
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

# ==================== YORDAMCHI FUNKSIYALAR ====================

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

def is_group_admin(chat_id, user_id):
    """Guruh admini ekanligini tekshirish"""
    try:
        member = bot.get_chat_member(chat_id, user_id)
        return member.status in ['administrator', 'creator']
    except:
        return False

def get_chat_type(message):
    """Chat turini aniqlash"""
    if message.chat.type in ['group', 'supergroup']:
        return 'group'
    return 'private'

def subscription_required(func):
    """Majburiy obuna dekoratori (faqat private uchun)"""
    def wrapper(message):
        chat_type = get_chat_type(message)
        user_id = message.from_user.id
        
        # Guruhda obuna tekshirmaydi
        if chat_type == 'group':
            return func(message)
        
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

# ==================== TIMER TIZIMI ====================

def cancel_timer(chat_id):
    """Timerni bekor qilish"""
    timer_key = str(chat_id)
    if timer_key in active_timers:
        try:
            active_timers[timer_key].cancel()
            del active_timers[timer_key]
        except:
            pass

def start_question_timer(chat_id, timer_seconds, is_group=False):
    """Savol uchun timer boshlash"""
    cancel_timer(chat_id)
    
    def timer_callback():
        try:
            if is_group:
                next_group_question(chat_id)
            else:
                next_private_question(chat_id)
        except Exception as e:
            print(f"Timer error: {e}")
    
    timer = threading.Timer(timer_seconds, timer_callback)
    timer.daemon = True
    timer.start()
    
    active_timers[str(chat_id)] = timer

# ==================== PRIVATE QUIZ FUNKSIYALARI ====================

def next_private_question(chat_id):
    """Private uchun keyingi savol"""
    user_id = str(chat_id)
    
    if user_id not in user_data or not user_data[user_id].get('quiz_active'):
        return
    
    # Javob berilmagan savolni hisoblash
    current_poll = user_data[user_id].get('current_poll_id')
    if current_poll and current_poll not in user_data[user_id].get('answered_polls', {}):
        user_data[user_id]['unanswered_count'] = user_data[user_id].get('unanswered_count', 0) + 1
        
        # 2 ta javobsiz = avtomatik pauza
        if user_data[user_id]['unanswered_count'] >= 2:
            auto_pause_private(chat_id, user_id)
            return
    else:
        user_data[user_id]['unanswered_count'] = 0
    
    # Keyingi savolga o'tish
    user_data[user_id]['current_question'] += 1
    current = user_data[user_id]['current_question']
    questions = user_data[user_id]['quiz_questions']
    
    if current >= len(questions):
        show_private_results(chat_id, user_id)
        return
    
    save_data()
    send_private_poll(chat_id, user_id)

def auto_pause_private(chat_id, user_id):
    """Private uchun avtomatik pauza"""
    save_quiz_progress(user_id)
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("▶️ Davom ettirish", callback_data="resume_private"))
    
    bot.send_message(
        chat_id,
        "⏸️ <b>Avtomatik pauza!</b>\n\n"
        "Siz ketma-ket 2 ta savolga javob bermadingiz.\n"
        "Test pauza qilindi.\n\n"
        "Davom ettirish uchun tugmani bosing yoki /resume buyrug'ini yuboring.",
        parse_mode='HTML',
        reply_markup=markup
    )

def send_private_poll(chat_id, user_id):
    """Private uchun poll yuborish"""
    if not user_data[user_id].get('quiz_active'):
        return
    
    current = user_data[user_id]['current_question']
    questions = user_data[user_id]['quiz_questions']
    
    if current >= len(questions):
        show_private_results(chat_id, user_id)
        return
    
    q = questions[current]
    timer = user_data[user_id].get('quiz_timer', 15)
    
    msg = bot.send_poll(
        chat_id=chat_id,
        question=f"❓ {q['question']}",
        options=q['options'],
        type='quiz',
        correct_option_id=q['correct'],
        is_anonymous=False,
        open_period=timer if timer else 300,
        explanation=f"📊 Savol {current + 1}/{len(questions)} | ⏸️ /pause - To'xtatish"
    )
    
    user_data[user_id]['current_poll_id'] = msg.poll.id
    user_data[user_id]['poll_message_id'] = msg.message_id
    save_data()
    
    # Timer boshlash
    start_question_timer(chat_id, timer if timer else 300, is_group=False)

def show_private_results(chat_id, user_id):
    """Private natijalarni ko'rsatish"""
    cancel_timer(chat_id)
    
    correct = user_data[user_id]['correct_answers']
    answered = user_data[user_id]['current_question']
    total = len(user_data[user_id]['quiz_questions'])
    
    if answered == 0:
        bot.send_message(
            chat_id,
            "⚠️ <b>Test tugadi!</b>\n\n"
            "Hech qanday savol yechilmadi.",
            parse_mode='HTML'
        )
        user_data[user_id]['quiz_active'] = False
        save_data()
        return
    
    percentage = (correct / answered) * 100 if answered > 0 else 0
    
    elapsed_time = int(time.time() - user_data[user_id]['start_time'])
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
    
    result = (
        f"{emoji} <b>Quiz yakunlandi!</b>\n\n"
        f"📊 <b>Natija:</b>\n"
        f"✅ To'g'ri: {correct}/{answered}\n"
        f"❌ Noto'g'ri: {answered - correct}/{answered}\n"
        f"📈 Foiz: {percentage:.1f}%\n"
        f"⏱️ Vaqt: {minutes}:{seconds:02d}\n\n"
        f"🏆 <b>Baho:</b> {grade}"
    )
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🔄 Qayta boshlash", callback_data="restart_quiz"))
    
    bot.send_message(chat_id, result, reply_markup=markup, parse_mode='HTML')
    
    user_data[user_id]['quiz_questions'] = []
    user_data[user_id]['current_question'] = 0
    user_data[user_id]['correct_answers'] = 0
    user_data[user_id]['answered_polls'] = {}
    user_data[user_id]['quiz_active'] = False
    user_data[user_id]['unanswered_count'] = 0
    save_data()

# ==================== GROUP QUIZ FUNKSIYALARI ====================

def next_group_question(chat_id):
    """Guruh uchun keyingi savol"""
    group_id = str(chat_id)
    
    if group_id not in group_data or not group_data[group_id].get('quiz_active'):
        return
    
    # Hech kim javob bermagan savolni hisoblash
    current_poll = group_data[group_id].get('current_poll_id')
    if current_poll:
        # Shu poll'ga javob berganlar sonini tekshirish
        answered_members = 0
        for member_id, member_data in group_data[group_id].get('members_results', {}).items():
            if current_poll in member_data.get('answered_polls', []):
                answered_members += 1
        
        if answered_members == 0:
            group_data[group_id]['unanswered_count'] = group_data[group_id].get('unanswered_count', 0) + 1
            
            # 2 ta savolga hech kim javob bermasa = avtomatik pauza
            if group_data[group_id]['unanswered_count'] >= 2:
                auto_pause_group(chat_id, group_id)
                return
        else:
            group_data[group_id]['unanswered_count'] = 0
    
    # Keyingi savolga o'tish
    group_data[group_id]['current_question'] += 1
    current = group_data[group_id]['current_question']
    questions = group_data[group_id]['quiz_questions']
    
    if current >= len(questions):
        show_group_results(chat_id, group_id)
        return
    
    save_data()
    send_group_poll(chat_id, group_id)

def auto_pause_group(chat_id, group_id):
    """Guruh uchun avtomatik pauza"""
    save_group_progress(group_id)
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("▶️ Davom ettirish", callback_data="resume_group"))
    
    bot.send_message(
        chat_id,
        "⏸️ <b>Avtomatik pauza!</b>\n\n"
        "Ketma-ket 2 ta savolga hech kim javob bermadi.\n"
        "Test pauza qilindi.\n\n"
        "Davom ettirish uchun admin /resume buyrug'ini yuborishi kerak.",
        parse_mode='HTML',
        reply_markup=markup
    )

def send_group_poll(chat_id, group_id):
    """Guruh uchun poll yuborish"""
    if not group_data[group_id].get('quiz_active'):
        return
    
    current = group_data[group_id]['current_question']
    questions = group_data[group_id]['quiz_questions']
    
    if current >= len(questions):
        show_group_results(chat_id, group_id)
        return
    
    q = questions[current]
    timer = group_data[group_id].get('quiz_timer', 15)
    
    msg = bot.send_poll(
        chat_id=chat_id,
        question=f"❓ {q['question']}",
        options=q['options'],
        type='quiz',
        correct_option_id=q['correct'],
        is_anonymous=False,
        open_period=timer if timer else 300,
        explanation=f"📊 Savol {current + 1}/{len(questions)} | Admin: /pause"
    )
    
    group_data[group_id]['current_poll_id'] = msg.poll.id
    group_data[group_id]['poll_message_id'] = msg.message_id
    save_data()
    
    # Timer boshlash
    start_question_timer(chat_id, timer if timer else 300, is_group=True)

def show_group_results(chat_id, group_id):
    """Guruh natijalarni ko'rsatish"""
    cancel_timer(chat_id)
    
    members = group_data[group_id].get('members_results', {})
    total_questions = len(group_data[group_id]['quiz_questions'])
    
    if not members:
        bot.send_message(
            chat_id,
            "⚠️ <b>Test tugadi!</b>\n\n"
            "Hech kim test yechmadi.",
            parse_mode='HTML'
        )
        group_data[group_id]['quiz_active'] = False
        save_data()
        return
    
    # Guruhda umumiy natija
    result_text = "🏆 <b>Guruh Test Natijalari</b>\n\n"
    
    # A'zolarni natija bo'yicha saralash
    sorted_members = sorted(
        members.items(),
        key=lambda x: (x[1].get('correct', 0), -x[1].get('total', 0)),
        reverse=True
    )
    
    for i, (member_id, results) in enumerate(sorted_members[:10], 1):
        try:
            member = bot.get_chat_member(chat_id, int(member_id))
            name = member.user.first_name
        except:
            name = f"User {member_id}"
        
        correct = results.get('correct', 0)
        total = results.get('total', 0)
        percentage = (correct / total * 100) if total > 0 else 0
        
        if i == 1:
            medal = "🥇"
        elif i == 2:
            medal = "🥈"
        elif i == 3:
            medal = "🥉"
        else:
            medal = f"{i}."
        
        result_text += f"{medal} {name}: {correct}/{total} ({percentage:.0f}%)\n"
    
    bot.send_message(chat_id, result_text, parse_mode='HTML')
    
    # Har bir a'zoga shaxsiy natija
    for member_id, results in members.items():
        try:
            correct = results.get('correct', 0)
            total = results.get('total', 0)
            percentage = (correct / total * 100) if total > 0 else 0
            
            if percentage >= 90:
                grade = "⭐⭐⭐ A'lo!"
            elif percentage >= 70:
                grade = "⭐⭐ Yaxshi!"
            elif percentage >= 50:
                grade = "⭐ Qoniqarli"
            else:
                grade = "📚 Takror qiling"
            
            private_msg = (
                f"📊 <b>Guruh test natijangiz</b>\n\n"
                f"✅ To'g'ri: {correct}/{total}\n"
                f"❌ Noto'g'ri: {total - correct}/{total}\n"
                f"📈 Foiz: {percentage:.1f}%\n\n"
                f"🏆 <b>Baho:</b> {grade}"
            )
            
            bot.send_message(int(member_id), private_msg, parse_mode='HTML')
        except:
            pass
    
    group_data[group_id]['quiz_active'] = False
    group_data[group_id]['members_results'] = {}
    group_data[group_id]['quiz_questions'] = []
    group_data[group_id]['current_question'] = 0
    group_data[group_id]['unanswered_count'] = 0
    save_data()

# ==================== PAUZA FUNKSIYALARI ====================

def save_quiz_progress(user_id):
    """Private progress saqlash"""
    user_data[user_id]['paused_quiz'] = {
        'questions': user_data[user_id]['quiz_questions'],
        'current_index': user_data[user_id]['current_question'],
        'correct_count': user_data[user_id]['correct_answers'],
        'pause_time': datetime.now().isoformat(),
        'timer': user_data[user_id].get('quiz_timer'),
        'answered_polls': user_data[user_id].get('answered_polls', {}),
        'unanswered_count': user_data[user_id].get('unanswered_count', 0)
    }
    user_data[user_id]['quiz_active'] = False
    cancel_timer(int(user_id))
    save_data()

def save_group_progress(group_id):
    """Guruh progress saqlash"""
    group_data[group_id]['paused_quiz'] = {
        'questions': group_data[group_id]['quiz_questions'],
        'current_index': group_data[group_id]['current_question'],
        'pause_time': datetime.now().isoformat(),
        'timer': group_data[group_id].get('quiz_timer'),
        'members_results': group_data[group_id].get('members_results', {}),
        'unanswered_count': group_data[group_id].get('unanswered_count', 0)
    }
    group_data[group_id]['quiz_active'] = False
    cancel_timer(int(group_id))
    save_data()

def resume_private_quiz(chat_id, user_id):
    """Private testni davom ettirish"""
    if 'paused_quiz' not in user_data[user_id]:
        bot.send_message(chat_id, "❌ Pauza qilingan test yo'q!")
        return False
    
    paused = user_data[user_id]['paused_quiz']
    user_data[user_id]['quiz_questions'] = paused['questions']
    user_data[user_id]['current_question'] = paused['current_index']
    user_data[user_id]['correct_answers'] = paused['correct_count']
    user_data[user_id]['quiz_timer'] = paused['timer']
    user_data[user_id]['answered_polls'] = paused.get('answered_polls', {})
    user_data[user_id]['unanswered_count'] = paused.get('unanswered_count', 0)
    user_data[user_id]['quiz_active'] = True
    user_data[user_id]['start_time'] = time.time()
    
    del user_data[user_id]['paused_quiz']
    save_data()
    
    bot.send_message(chat_id, "▶️ Test davom ettirilmoqda...")
    time.sleep(1)
    send_private_poll(chat_id, user_id)
    return True

def resume_group_quiz(chat_id, group_id):
    """Guruh testni davom ettirish"""
    if 'paused_quiz' not in group_data[group_id]:
        bot.send_message(chat_id, "❌ Pauza qilingan test yo'q!")
        return False
    
    paused = group_data[group_id]['paused_quiz']
    group_data[group_id]['quiz_questions'] = paused['questions']
    group_data[group_id]['current_question'] = paused['current_index']
    group_data[group_id]['quiz_timer'] = paused['timer']
    group_data[group_id]['members_results'] = paused.get('members_results', {})
    group_data[group_id]['unanswered_count'] = paused.get('unanswered_count', 0)
    group_data[group_id]['quiz_active'] = True
    
    del group_data[group_id]['paused_quiz']
    save_data()
    
    bot.send_message(chat_id, "▶️ Guruh testi davom ettirilmoqda...")
    time.sleep(1)
    send_group_poll(chat_id, group_id)
    return True

# ==================== ASOSIY BUYRUQLAR ====================

@bot.message_handler(commands=['start'])
@subscription_required
def start(message):
    chat_type = get_chat_type(message)
    
    if chat_type == 'group':
        bot.send_message(
            message.chat.id,
            "🎓 <b>Quiz Bot guruhda!</b>\n\n"
            "Admin qilishi kerak:\n"
            "1. /load - Savollar yuklash\n"
            "2. /quiz - Test boshlash\n\n"
            "Yordam: /help",
            parse_mode='HTML'
        )
        return
    
    user_id = str(message.from_user.id)
    update_last_active(user_id)
    
    if user_id not in user_data:
        user_data[user_id] = {
            'questions': [],
            'mode': None,
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
        f"Boshlash uchun savollar yuklang yoki tugmalardan foydalaning!",
        parse_mode='HTML',
        reply_markup=markup
    )

# ==================== SAVOLLARNI YUKLASH ====================

@bot.message_handler(commands=['load'])
@bot.message_handler(func=lambda m: m.text == '📝 Savollar yuklash')
@subscription_required
def load_questions(message):
    chat_type = get_chat_type(message)
    user_id = str(message.from_user.id)
    chat_id = str(message.chat.id)
    
    # Guruhda faqat admin yuklashi mumkin
    if chat_type == 'group':
        if not is_group_admin(message.chat.id, message.from_user.id):
            bot.reply_to(message, "❌ Faqat adminlar savollar yuklashi mumkin!")
            return
        
        if chat_id not in group_data:
            group_data[chat_id] = {}
        
        group_data[chat_id]['mode'] = 'loading'
        group_data[chat_id]['loading_admin'] = user_id
        save_data()
    else:
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
    chat_type = get_chat_type(message)
    user_id = str(message.from_user.id)
    chat_id = str(message.chat.id)
    
    if chat_type == 'group':
        if chat_id in group_data:
            group_data[chat_id]['mode'] = None
            save_data()
    else:
        if user_id in user_data:
            user_data[user_id]['mode'] = None
            save_data()
    
    bot.send_message(message.chat.id, "❌ Bekor qilindi.")

@bot.message_handler(content_types=['document'])
def handle_document(message):
    chat_type = get_chat_type(message)
    user_id = str(message.from_user.id)
    chat_id = str(message.chat.id)
    
    if chat_type == 'group':
        if not is_group_admin(message.chat.id, message.from_user.id):
            return
        
        if group_data.get(chat_id, {}).get('mode') != 'loading':
            bot.send_message(message.chat.id, "Avval /load buyrug'ini yuboring!")
            return
    else:
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

@bot.message_handler(func=lambda m: user_data.get(str(m.from_user.id), {}).get('mode') == 'loading' or 
                                     group_data.get(str(m.chat.id), {}).get('mode') == 'loading')
def handle_text_questions(message):
    chat_type = get_chat_type(message)
    
    if chat_type == 'group':
        if not is_group_admin(message.chat.id, message.from_user.id):
            return
    else:
        update_last_active(message.from_user.id)
    
    process_questions_text(message, message.text)

def process_questions_text(message, text):
    chat_type = get_chat_type(message)
    user_id = str(message.from_user.id)
    chat_id = str(message.chat.id)
    
    try:
        questions = quiz_parser.parse_text(text)
        
        if questions:
            if chat_type == 'group':
                group_data[chat_id]['questions'] = questions
                group_data[chat_id]['mode'] = None
                save_data()
            else:
                user_data[user_id]['questions'] = questions
                user_data[user_id]['mode'] = None
                save_data()
            
            bot.send_message(
                message.chat.id,
                f"✅ <b>Savollar yuklandi!</b>\n\n"
                f"📊 Jami: {len(questions)} ta savol\n\n"
                f"Quiz boshlash: /quiz",
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
@bot.message_handler(func=lambda m: m.text == '📋 Savollarni ko\'rish')
@subscription_required
def view_questions(message):
    chat_type = get_chat_type(message)
    user_id = str(message.from_user.id)
    chat_id = str(message.chat.id)
    
    if chat_type == 'group':
        if chat_id not in group_data or not group_data[chat_id].get('questions'):
            bot.send_message(message.chat.id, "❌ Savollar yo'q! Admin /load")
            return
        questions = group_data[chat_id]['questions']
    else:
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

# ==================== QUIZ BOSHLASH ====================

@bot.message_handler(commands=['quiz'])
@bot.message_handler(func=lambda m: m.text == '🎯 Quiz boshlash')
@subscription_required
def start_quiz(message):
    chat_type = get_chat_type(message)
    user_id = str(message.from_user.id)
    chat_id = str(message.chat.id)
    
    if chat_type == 'group':
        if not is_group_admin(message.chat.id, message.from_user.id):
            bot.reply_to(message, "❌ Faqat adminlar test boshlashi mumkin!")
            return
        
        if chat_id not in group_data or not group_data[chat_id].get('questions'):
            bot.send_message(message.chat.id, "❌ Savollar yo'q! Admin /load")
            return
        
        total_questions = len(group_data[chat_id]['questions'])
        group_data[chat_id]['quiz_mode'] = 'selecting'
        save_data()
    else:
        update_last_active(user_id)
        
        if user_id not in user_data or not user_data[user_id].get('questions'):
            bot.send_message(message.chat.id, "❌ Savollar yo'q! /load")
            return
        
        total_questions = len(user_data[user_id]['questions'])
    
    # Test rejimini tanlash
    markup = types.InlineKeyboardMarkup(row_width=2)
    
    if chat_type == 'group':
        markup.add(
            types.InlineKeyboardButton("📊 Soni bo'yicha", callback_data=f"gmode_count_{chat_id}"),
            types.InlineKeyboardButton("🔢 Oraliq bo'yicha", callback_data=f"gmode_range_{chat_id}")
        )
    else:
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

# Qolgan kod davom etadi...
# (Callbacks, Poll handler, Pause/Resume, Admin panel va boshqalar)

# Poll Answer Handler yoki boshqa handler kodlarini qo'shishdan oldin
# Avval yuqoridagi barcha asosiy funksiyalar to'g'ri yozilganligiga ishonch hosil qiling

# POLL ANSWER HANDLER
@bot.poll_answer_handler()
def handle_poll_answer(poll_answer):
    """Poll javoblarini qayta ishlash"""
    user_id = str(poll_answer.user.id)
    
    # Private test uchun tekshirish
    if user_id in user_data and user_data[user_id].get('quiz_active'):
        update_last_active(user_id)
        
        current_poll = user_data[user_id].get('current_poll_id')
        if poll_answer.poll_id != current_poll:
            return
        
        if 'answered_polls' not in user_data[user_id]:
            user_data[user_id]['answered_polls'] = {}
        
        if poll_answer.poll_id in user_data[user_id]['answered_polls']:
            return
        
        user_data[user_id]['answered_polls'][poll_answer.poll_id] = True
        
        current = user_data[user_id]['current_question']
        questions = user_data[user_id]['quiz_questions']
        
        if current < len(questions):
            q = questions[current]
            user_answer = poll_answer.option_ids[0] if poll_answer.option_ids else -1
            
            if user_answer == q['correct']:
                user_data[user_id]['correct_answers'] += 1
            
            # Javob berildi - unanswered counter reset
            user_data[user_id]['unanswered_count'] = 0
        
        save_data()
        return
    
    # Guruh testlari uchun
    for group_id, gdata in group_data.items():
        if gdata.get('quiz_active') and gdata.get('current_poll_id') == poll_answer.poll_id:
            if user_id not in gdata.get('members_results', {}):
                gdata['members_results'][user_id] = {
                    'correct': 0,
                    'total': 0,
                    'answered_polls': []
                }
            
            if poll_answer.poll_id in gdata['members_results'][user_id].get('answered_polls', []):
                return
            
            gdata['members_results'][user_id]['answered_polls'].append(poll_answer.poll_id)
            
            current = gdata['current_question']
            questions = gdata['quiz_questions']
            
            if current < len(questions):
                q = questions[current]
                user_answer = poll_answer.option_ids[0] if poll_answer.option_ids else -1
                
                gdata['members_results'][user_id]['total'] += 1
                
                if user_answer == q['correct']:
                    gdata['members_results'][user_id]['correct'] += 1
            
            save_data()
            return

# CALLBACK HANDLERS - davom
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
        user_data[user_id]['quiz_timer'] = 300
    else:
        user_data[user_id]['quiz_timer'] = int(timer)
    
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
    
    questions = user_data[user_id]['selected_questions'][:]
    
    if order == 'random':
        random.shuffle(questions)
    
    if user_data[user_id].get('shuffle_answers', False):
        for q in questions:
            correct_answer = q['options'][q['correct']]
            random.shuffle(q['options'])
            q['correct'] = q['options'].index(correct_answer)
    
    user_data[user_id]['quiz_questions'] = questions
    user_data[user_id]['current_question'] = 0
    user_data[user_id]['correct_answers'] = 0
    user_data[user_id]['start_time'] = time.time()
    user_data[user_id]['answered_polls'] = {}
    user_data[user_id]['quiz_active'] = True
    user_data[user_id]['unanswered_count'] = 0
    save_data()
    
    timer_text = f"{user_data[user_id]['quiz_timer']}s" if user_data[user_id]['quiz_timer'] < 300 else "Cheksiz"
    
    bot.edit_message_text(
        f"✅ <b>Quiz boshlandi!</b>\n\n"
        f"📊 Savollar: {len(questions)}\n"
        f"⏱️ Vaqt: {timer_text}\n"
        f"🎲 Javoblar: {'Aralash' if user_data[user_id].get('shuffle_answers') else 'Asl'}\n\n"
        f"⚠️ <b>To'xtatish:</b> /pause\n\n"
        f"Birinchi savol yuborilmoqda...",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        parse_mode='HTML'
    )
    
    time.sleep(1)
    send_private_poll(call.message.chat.id, user_id)

# PAUSE VA RESUME
@bot.message_handler(commands=['pause'])
def pause_quiz(message):
    """Testni to'xtatish"""
    chat_type = get_chat_type(message)
    user_id = str(message.from_user.id)
    chat_id = str(message.chat.id)
    
    if chat_type == 'group':
        if not is_group_admin(message.chat.id, message.from_user.id):
            bot.reply_to(message, "❌ Faqat adminlar to'xtata oladi!")
            return
        
        if chat_id not in group_data or not group_data[chat_id].get('quiz_active'):
            bot.send_message(message.chat.id, "❌ Faol test yo'q!")
            return
        
        save_group_progress(chat_id)
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("▶️ Davom ettirish", callback_data="resume_group"))
        
        bot.send_message(
            message.chat.id,
            "⏸️ <b>Test pauza qilindi!</b>\n\n"
            "Davom ettirish: Admin /resume",
            parse_mode='HTML',
            reply_markup=markup
        )
    else:
        if user_id not in user_data or not user_data[user_id].get('quiz_active'):
            bot.send_message(message.chat.id, "❌ Faol test yo'q!")
            return
        
        save_quiz_progress(user_id)
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("▶️ Davom ettirish", callback_data="resume_private"))
        
        bot.send_message(
            message.chat.id,
            "⏸️ <b>Test pauza qilindi!</b>\n\n"
            "Davom ettirish: /resume",
            parse_mode='HTML',
            reply_markup=markup
        )

@bot.message_handler(commands=['resume'])
def resume_quiz(message):
    """Testni davom ettirish"""
    chat_type = get_chat_type(message)
    user_id = str(message.from_user.id)
    chat_id = str(message.chat.id)
    
    if chat_type == 'group':
        if not is_group_admin(message.chat.id, message.from_user.id):
            bot.reply_to(message, "❌ Faqat adminlar davom ettira oladi!")
            return
        
        resume_group_quiz(message.chat.id, chat_id)
    else:
        resume_private_quiz(message.chat.id, user_id)

@bot.callback_query_handler(func=lambda call: call.data == 'resume_private')
def resume_private_callback(call):
    user_id = str(call.from_user.id)
    bot.answer_callback_query(call.id, "▶️ Davom ettirilmoqda...")
    resume_private_quiz(call.message.chat.id, user_id)

@bot.callback_query_handler(func=lambda call: call.data == 'resume_group')
def resume_group_callback(call):
    group_id = str(call.message.chat.id)
    
    if not is_group_admin(call.message.chat.id, call.from_user.id):
        bot.answer_callback_query(call.id, "❌ Faqat adminlar!", show_alert=True)
        return
    
    bot.answer_callback_query(call.id, "▶️ Davom ettirilmoqda...")
    resume_group_quiz(call.message.chat.id, group_id)

# HELP
@bot.message_handler(commands=['help'])
@bot.message_handler(func=lambda m: m.text == '❓ Yordam')
def help_command(message):
    help_text = """
📚 <b>Qo'llanma</b>

<b>Buyruqlar:</b>
/start - Boshlash
/load - Savollar yuklash
/quiz - Test boshlash
/pause - To'xtatish
/resume - Davom ettirish
/help - Yordam

<b>Format:</b>
? Savol
+ To'g'ri
- Noto'g'ri

<b>Xususiyatlar:</b>
✅ Timer tizimi
✅ Avtomatik pauza
✅ Guruhda ishlaydi
    """
    bot.send_message(message.chat.id, help_text, parse_mode='HTML')

# OBUNA
@bot.callback_query_handler(func=lambda call: call.data == 'check_sub')
def check_subscription_callback(call):
    user_id = call.from_user.id
    
    if check_subscription(user_id):
        bot.answer_callback_query(call.id, "✅ Rahmat!")
        bot.delete_message(call.message.chat.id, call.message.message_id)
        start(call.message)
    else:
        bot.answer_callback_query(call.id, "❌ Siz hali obuna bo'lmadingiz!", show_alert=True)

# AUTO CLEAN
def auto_clean_loop():
    while True:
        time.sleep(21600)
        try:
            clean_old_data()
            print(f"🗑️ Tozalash: {datetime.now().strftime('%H:%M:%S')}")
        except Exception as e:
            print(f"❌ Xato: {e}")

# START BOT
if __name__ == '__main__':
    print("=" * 60)
    print("🤖 BOT ISHGA TUSHMOQDA...")
    print("=" * 60)
    
    load_data()
    
    print("\n✅ TAYYOR!")
    print(f"👥 Users: {len(user_data)}")
    print(f"👥 Groups: {len(group_data)}")
    print("=" * 60)
    
    clean_thread = threading.Thread(target=auto_clean_loop, daemon=True)
    clean_thread.start()
    
    try:
        bot.infinity_polling(timeout=60, long_polling_timeout=60)
    except KeyboardInterrupt:
        print("\n⏸️ To'xtatilmoqda...")
        save_data()
        print("✅ Saqlandi!")