import json
import os
from datetime import datetime

class GroupQuizManager:
    """Guruh testlarini boshqarish uchun class"""
    
    def __init__(self, data_file="group_games.json"):
        self.data_file = data_file
        self.active_games = self.load_games()
        self.user_scores = {}
    
    def load_games(self):
        """Saqqlangan o'yinlarni yuklash"""
        try:
            if os.path.exists(self.data_file):
                with open(self.data_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    print(f"📂 Gruppa o'yinlari yuklandi: {len(data)} ta")
                    return data
        except Exception as e:
            print(f"❌ Gruppa o'yinlarni yuklashda xatolik: {e}")
        return {}
    
    def save_games(self):
        """O'yinlarni saqlash"""
        try:
            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump(self.active_games, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"❌ Gruppa o'yinlarni saqlashda xatolik: {e}")
    
    def create_game(self, chat_id, questions, creator_id, creator_name, time_limit=30):
        """Yangi o'yin yaratish"""
        game_id = f"{chat_id}_{int(time.time())}"
        
        self.active_games[game_id] = {
            'game_id': game_id,
            'chat_id': chat_id,
            'questions': questions,
            'current_question': 0,
            'total_questions': len(questions),
            'start_time': time.time(),
            'time_limit': time_limit,
            'creator_id': creator_id,
            'creator_name': creator_name,
            'players': {},
            'is_active': True,
            'started': False,
            'created_at': datetime.now().isoformat()
        }
        
        # O'yinchi sifatida yaratuvchini qo'shish
        self.add_player(game_id, creator_id, creator_name)
        
        self.save_games()
        return game_id
    
    def add_player(self, game_id, user_id, username):
        """O'yinchi qo'shish"""
        if game_id in self.active_games:
            if str(user_id) not in self.active_games[game_id]['players']:
                self.active_games[game_id]['players'][str(user_id)] = {
                    'username': username,
                    'score': 0,
                    'correct_answers': 0,
                    'total_answers': 0,
                    'response_times': [],
                    'joined_at': datetime.now().isoformat()
                }
                self.save_games()
                return True
        return False
    
    def submit_answer(self, game_id, user_id, question_index, is_correct, response_time):
        """Javobni qabul qilish"""
        if game_id in self.active_games:
            game = self.active_games[game_id]
            user_id_str = str(user_id)
            
            if user_id_str in game['players']:
                player = game['players'][user_id_str]
                player['total_answers'] += 1
                
                if is_correct:
                    # Ballar: base + time bonus
                    base_points = 10
                    time_bonus = max(0, (game['time_limit'] - response_time) / 2)
                    total_points = base_points + time_bonus
                    
                    player['score'] += total_points
                    player['correct_answers'] += 1
                    player['response_times'].append(response_time)
                
                self.save_games()
                return player['score']
        return 0
    
    def get_leaderboard(self, game_id, limit=10):
        """Reyting jadvali"""
        if game_id not in self.active_games:
            return []
        
        game = self.active_games[game_id]
        players = game['players']
        
        # Ballar bo'yicha saralash
        sorted_players = sorted(
            players.items(),
            key=lambda x: x[1]['score'],
            reverse=True
        )
        
        leaderboard = []
        for i, (user_id, data) in enumerate(sorted_players[:limit], 1):
            avg_time = sum(data['response_times'])/len(data['response_times']) if data['response_times'] else 0
            
            leaderboard.append({
                'rank': i,
                'username': data['username'],
                'score': round(data['score'], 1),
                'correct': data['correct_answers'],
                'total': data['total_answers'],
                'accuracy': (data['correct_answers'] / data['total_answers'] * 100) if data['total_answers'] > 0 else 0,
                'avg_time': round(avg_time, 1)
            })
        
        return leaderboard
    
    def get_active_game_by_chat(self, chat_id):
        """Guruhning faol o'yinini topish"""
        for game_id, game in self.active_games.items():
            if game['chat_id'] == chat_id and game['is_active']:
                return game_id, game
        return None, None
    
    def end_game(self, game_id):
        """O'yinni tugatish"""
        if game_id in self.active_games:
            game = self.active_games[game_id].copy()
            game['is_active'] = False
            game['ended_at'] = datetime.now().isoformat()
            game['duration'] = time.time() - game['start_time']
            
            # Reytingni hisoblash
            game['final_leaderboard'] = self.get_leaderboard(game_id, 20)
            
            # Stats
            game['stats'] = {
                'total_players': len(game['players']),
                'total_questions': game['total_questions'],
                'total_correct_answers': sum(p['correct_answers'] for p in game['players'].values()),
                'total_answers': sum(p['total_answers'] for p in game['players'].values()),
                'avg_accuracy': (sum(p['correct_answers'] for p in game['players'].values()) / 
                               sum(p['total_answers'] for p in game['players'].values()) * 100) if sum(p['total_answers'] for p in game['players'].values()) > 0 else 0
            }
            
            # Saqlash uchun alohida faylga
            self.save_ended_game(game)
            
            # Faol o'yinlar ro'yxatidan o'chirish
            del self.active_games[game_id]
            self.save_games()
            
            return game
        
        return None
    
    def save_ended_game(self, game):
        """Tugagan o'yinni saqlash"""
        ended_file = "ended_games.json"
        ended_games = []
        
        try:
            if os.path.exists(ended_file):
                with open(ended_file, 'r', encoding='utf-8') as f:
                    ended_games = json.load(f)
        except:
            ended_games = []
        
        ended_games.append(game)
        
        # Faqat oxirgi 100 ta o'yinni saqlash
        if len(ended_games) > 100:
            ended_games = ended_games[-100:]
        
        try:
            with open(ended_file, 'w', encoding='utf-8') as f:
                json.dump(ended_games, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"❌ Tugagan o'yinni saqlashda xatolik: {e}")
    
    def cleanup_old_games(self, max_age_hours=24):
        """Eski o'yinlarni tozalash"""
        current_time = time.time()
        games_to_remove = []
        
        for game_id, game in self.active_games.items():
            game_age = current_time - game['start_time']
            if game_age > max_age_hours * 3600:
                games_to_remove.append(game_id)
        
        for game_id in games_to_remove:
            print(f"🗑️ Eski o'yin o'chirildi: {game_id}")
            del self.active_games[game_id]
        
        if games_to_remove:
            self.save_games()