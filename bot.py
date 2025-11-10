import requests
import json
import telebot
from telebot import types
import io
import os
import threading
import time
import sqlite3
from datetime import datetime
import base64
import zipfile

# Конфигурация
API_KEY = "AIzaSyARZYE8kSTBVlGF_A1jxFdEQdVi5-9MN38"
SELECTED_MODEL = "gemini-2.5-flash-exp-03-25"
CHANNEL_USERNAME = "@GeniAi"
ADMIN_ID = 2202291197
BOT_TOKEN = "2201851225:AAEruvQjAyxiYIcsVCwa-JoIcWaXMx4kqE8/test"

bot = telebot.TeleBot(BOT_TOKEN)

# Инициализация базы данных
def init_db():
    conn = sqlite3.connect('bot_stats.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            subscribed INTEGER DEFAULT 0,
            requests_balance INTEGER DEFAULT 5,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS stats (
            user_id INTEGER,
            action_type TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS requests_history (
            user_id INTEGER,
            requests_change INTEGER,
            reason TEXT,
            admin_id INTEGER,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

init_db()

user_states = {}

def keep_alive():
    while True:
        try:
            response = requests.get("https://one2-1-04er.onrender.com/", timeout=10)
            print(f"Keep-alive: {response.status_code}")
        except Exception as e:
            print(f"Keep-alive error: {e}")
        time.sleep(300)

def add_user(user_id, username, first_name, last_name):
    conn = sqlite3.connect('bot_stats.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR IGNORE INTO users (user_id, username, first_name, last_name, requests_balance)
        VALUES (?, ?, ?, ?, 5)
    ''', (user_id, username, first_name, last_name))
    conn.commit()
    conn.close()

def update_subscription(user_id, subscribed):
    conn = sqlite3.connect('bot_stats.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET subscribed = ? WHERE user_id = ?', (subscribed, user_id))
    conn.commit()
    conn.close()

def get_user_balance(user_id):
    conn = sqlite3.connect('bot_stats.db')
    cursor = conn.cursor()
    cursor.execute('SELECT requests_balance FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else 0

def update_user_balance(user_id, new_balance):
    conn = sqlite3.connect('bot_stats.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET requests_balance = ? WHERE user_id = ?', (new_balance, user_id))
    conn.commit()
    conn.close()

def add_requests(user_id, amount, reason, admin_id=None):
    current_balance = get_user_balance(user_id)
    new_balance = current_balance + amount
    
    conn = sqlite3.connect('bot_stats.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET requests_balance = ? WHERE user_id = ?', (new_balance, user_id))
    cursor.execute('INSERT INTO requests_history (user_id, requests_change, reason, admin_id) VALUES (?, ?, ?, ?)',
                  (user_id, amount, reason, admin_id))
    conn.commit()
    conn.close()
    return new_balance

def use_request(user_id):
    current_balance = get_user_balance(user_id)
    if current_balance > 0:
        new_balance = current_balance - 1
        update_user_balance(user_id, new_balance)
        return True, new_balance
    return False, current_balance

def add_stat(user_id, action_type):
    conn = sqlite3.connect('bot_stats.db')
    cursor = conn.cursor()
    cursor.execute('INSERT INTO stats (user_id, action_type) VALUES (?, ?)', (user_id, action_type))
    conn.commit()
    conn.close()

def get_stats():
    conn = sqlite3.connect('bot_stats.db')
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM users')
    total_users = cursor.fetchone()[0]
    cursor.execute('SELECT COUNT(*) FROM stats WHERE action_type = "code_generated"')
    codes_generated = cursor.fetchone()[0]
    cursor.execute('SELECT COUNT(*) FROM stats WHERE action_type = "plugin_generated"')
    plugins_generated = cursor.fetchone()[0]
    cursor.execute('SELECT COUNT(*) FROM stats WHERE action_type = "code_modified"')
    codes_modified = cursor.fetchone()[0]
    cursor.execute('SELECT COUNT(*) FROM stats WHERE action_type = "project_generated"')
    projects_generated = cursor.fetchone()[0]
    cursor.execute('SELECT SUM(requests_balance) FROM users')
    total_requests = cursor.fetchone()[0] or 0
    conn.close()
    return {
        'total_users': total_users,
        'codes_generated': codes_generated,
        'plugins_generated': plugins_generated,
        'codes_modified': codes_modified,
        'projects_generated': projects_generated,
        'total_requests': total_requests
    }

def check_subscription(user_id):
    try:
        chat_member = bot.get_chat_member(CHANNEL_USERNAME, user_id)
        return chat_member.status in ['member', 'administrator', 'creator']
    except:
        return False

class GeminiChat:
    def __init__(self, model=SELECTED_MODEL):
        self.url = f"https://generativelanguage.googleapis.com/v1/models/{model}:generateContent?key={API_KEY}"
        self.headers = {'Content-Type': 'application/json'}
    
    def send_message(self, message, is_code_request=True, is_plugin_request=False, is_project_request=False, image_data=None):
        if is_plugin_request:
            prompt = f"Создай Python плагин для exteragram: {message}"
        elif is_project_request:
            prompt = f"Создай Python проект: {message}"
        elif is_code_request:
            prompt = f"Создай Python код: {message}"
        else:
            prompt = f"Улучши код: {message}"
        
        contents = {"contents": [{"parts": [{"text": prompt}]}]}
        
        if image_data:
            contents["contents"][0]["parts"].insert(0, {
                "inline_data": {
                    "mime_type": "image/jpeg",
                    "data": image_data
                }
            })
        
        try:
            response = requests.post(self.url, headers=self.headers, json=contents, timeout=30)
            if response.status_code == 200:
                result = response.json()
                if 'candidates' in result and result['candidates']:
                    return result['candidates'][0]['content']['parts'][0]['text']
            return "❌ Ошибка генерации"
        except:
            return "❌ Таймаут"

def extract_code(text):
    if '```python' in text:
        parts = text.split('```python')
        if len(parts) > 1:
            return parts[1].split('```')[0].strip()
    elif '```' in text:
        parts = text.split('```')
        if len(parts) > 2:
            return parts[1].strip()
    return text

def parse_project_files(text):
    files = {}
    current_file = None
    
    for line in text.split('\n'):
        if line.startswith('ФАЙЛ:') or line.startswith('FILE:'):
            if current_file and files.get(current_file):
                files[current_file] = files[current_file].strip()
            current_file = line.split(':', 1)[1].strip()
            files[current_file] = ""
        elif current_file and line.strip() and not line.startswith('```'):
            files[current_file] += line + '\n'
    
    if current_file and files.get(current_file):
        files[current_file] = files[current_file].strip()
    
    return files

def create_zip(files):
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    zip_buffer.seek(0)
    return zip_buffer

def process_image_message(message):
    if message.text:
        return message.text, None
    
    caption = message.caption if message.caption else ""
    
    if not (message.photo or (message.document and message.document.mime_type.startswith('image/'))):
        return caption, None
    
    try:
        if message.photo:
            file_id = message.photo[-1].file_id
        else:
            file_id = message.document.file_id
            
        file_info = bot.get_file(file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        image_data = base64.b64encode(downloaded_file).decode('utf-8')
        return caption, image_data
    except:
        return caption, None

@bot.message_handler(commands=['start'])
def start_cmd(message):
    user_id = message.from_user.id
    add_user(user_id, message.from_user.username, message.from_user.first_name, message.from_user.last_name)
    
    if check_subscription(user_id):
        update_subscription(user_id, 1)
        show_main_menu(message)
    else:
        update_subscription(user_id, 0)
        show_subscription_request(message)

def show_subscription_request(message):
    markup = types.InlineKeyboardMarkup()
    markup.row(types.InlineKeyboardButton('📢 Подписаться', url='https://t.me/GeniAi'))
    markup.row(types.InlineKeyboardButton('✅ Проверить', callback_data='check_sub'))
    bot.send_message(message.chat.id, "📢 Подпишись на канал!", reply_markup=markup)

def show_main_menu(message):
    user_id = message.from_user.id
    balance = get_user_balance(user_id)
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    btn1 = types.InlineKeyboardButton('💻 Написать код', callback_data='write_code')
    btn2 = types.InlineKeyboardButton('🚀 Собрать проект', callback_data='write_project')
    btn3 = types.InlineKeyboardButton('🔌 Написать плагин', callback_data='write_plugin')
    btn4 = types.InlineKeyboardButton('⚡ Изменить готовый', callback_data='modify_code')
    btn5 = types.InlineKeyboardButton('📊 Статистика', callback_data='stats')
    btn6 = types.InlineKeyboardButton('💎 Подписка', callback_data='subscription')
    btn7 = types.InlineKeyboardButton('👤 Автор бота', callback_data='author')
    
    if message.from_user.id == ADMIN_ID:
        btn8 = types.InlineKeyboardButton('👑 Админ панель', callback_data='admin_panel')
        markup.add(btn1, btn2, btn3, btn4, btn5, btn6, btn7, btn8)
    else:
        markup.add(btn1, btn2, btn3, btn4, btn5, btn6, btn7)
    
    bot.send_message(message.chat.id, f"🤖 GeniAI | Баланс: {balance}", reply_markup=markup)
    user_states[message.chat.id] = 'main_menu'

def show_subscription_info(message):
    user_id = message.from_user.id
    balance = get_user_balance(user_id)
    text = f"💎 Баланс: {balance}\n🛒 Купить: @xostcodingkrytoy"
    markup = types.InlineKeyboardMarkup()
    markup.row(types.InlineKeyboardButton('🛒 Купить запросы', url='https://t.me/xostcodingkrytoy'))
    markup.row(types.InlineKeyboardButton('🔙 Назад', callback_data='back_to_menu'))
    bot.send_message(message.chat.id, text, reply_markup=markup)

def show_admin_panel(message):
    stats = get_stats()
    text = f"""👑 Админ панель
Пользователей: {stats['total_users']}
Кодов: {stats['codes_generated']}
Проектов: {stats['projects_generated']}"""
    bot.send_message(message.chat.id, text)

@bot.message_handler(commands=['request'])
def handle_request_command(message):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        _, user_id, amount = message.text.split()
        user_id = int(user_id)
        amount = int(amount)
        new_balance = add_requests(user_id, amount, "Выдача админом", ADMIN_ID)
        bot.send_message(message.chat.id, f"✅ Выдано {amount} запросов пользователю {user_id}")
    except:
        bot.send_message(message.chat.id, "❌ Ошибка формата")

@bot.message_handler(commands=['users'])
def handle_users_command(message):
    if message.from_user.id != ADMIN_ID:
        return
    conn = sqlite3.connect('bot_stats.db')
    cursor = conn.cursor()
    cursor.execute('SELECT user_id, username, requests_balance FROM users ORDER BY created_at DESC LIMIT 10')
    users = cursor.fetchall()
    conn.close()
    
    text = "👥 Последние пользователи:\n"
    for user in users:
        user_id, username, balance = user
        text += f"🆔 {user_id} | 💰 {balance}\n"
    bot.send_message(message.chat.id, text)

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    
    if call.data == 'check_sub':
        if check_subscription(user_id):
            bot.answer_callback_query(call.id, "✅ Подписка активна!")
            show_main_menu(call.message)
        else:
            bot.answer_callback_query(call.id, "❌ Не подписан!")
        return
    
    if not check_subscription(user_id):
        bot.answer_callback_query(call.id, "❌ Сначала подпишись!")
        return
    
    if call.data == 'write_code':
        balance = get_user_balance(user_id)
        if balance <= 0:
            bot.answer_callback_query(call.id, "❌ Нет запросов!")
            return
        user_states[chat_id] = 'waiting_code'
        bot.send_message(chat_id, "💻 Опиши какой код нужен:")
        
    elif call.data == 'write_project':
        balance = get_user_balance(user_id)
        if balance <= 0:
            bot.answer_callback_query(call.id, "❌ Нет запросов!")
            return
        user_states[chat_id] = 'waiting_project'
        bot.send_message(chat_id, "🚀 Опиши какой проект нужен:")
        
    elif call.data == 'write_plugin':
        balance = get_user_balance(user_id)
        if balance <= 0:
            bot.answer_callback_query(call.id, "❌ Нет запросов!")
            return
        user_states[chat_id] = 'waiting_plugin'
        bot.send_message(chat_id, "🔌 Опиши какой плагин нужен:")
        
    elif call.data == 'modify_code':
        balance = get_user_balance(user_id)
        if balance <= 0:
            bot.answer_callback_query(call.id, "❌ Нет запросов!")
            return
        user_states[chat_id] = 'waiting_file'
        bot.send_message(chat_id, "⚡ Отправь .py файл:")
        
    elif call.data == 'stats':
        stats = get_stats()
        user_balance = get_user_balance(user_id)
        bot.send_message(chat_id, f"📊 Статистика:\nКоды: {stats['codes_generated']}\nПроекты: {stats['projects_generated']}\nБаланс: {user_balance}")
        
    elif call.data == 'subscription':
        show_subscription_info(call.message)
        
    elif call.data == 'author':
        bot.send_message(chat_id, "👤 @xostcodingkrytoy")
        
    elif call.data == 'admin_panel':
        if user_id == ADMIN_ID:
            show_admin_panel(call.message)
            
    elif call.data == 'back_to_menu':
        show_main_menu(call.message)

@bot.message_handler(content_types=['text', 'photo'])
def handle_messages(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    state = user_states.get(chat_id)
    
    if not state or not check_subscription(user_id):
        return
    
    user_request, image_data = process_image_message(message)
    
    if not user_request or user_request.strip() == "":
        bot.send_message(chat_id, "❌ Добавь описание")
        return
    
    if state == 'waiting_code':
        success, balance = use_request(user_id)
        if not success:
            bot.send_message(chat_id, "❌ Нет запросов!")
            return
            
        msg = bot.send_message(chat_id, "⏳ Генерирую код...")
        
        try:
            gemini = GeminiChat()
            response = gemini.send_message(user_request, is_code_request=True, image_data=image_data)
            
            if response.startswith('❌'):
                bot.edit_message_text("❌ Ошибка генерации", chat_id, msg.message_id)
                add_requests(user_id, 1, "Возврат")
            else:
                code = extract_code(response)
                file = io.BytesIO(code.encode())
                file.name = "code.py"
                
                bot.delete_message(chat_id, msg.message_id)
                bot.send_document(chat_id, file, caption=f"✅ Готово! | Баланс: {balance}")
                add_stat(user_id, "code_generated")
        except Exception as e:
            bot.edit_message_text("❌ Ошибка", chat_id, msg.message_id)
            add_requests(user_id, 1, "Возврат")
        
    elif state == 'waiting_project':
        success, balance = use_request(user_id)
        if not success:
            bot.send_message(chat_id, "❌ Нет запросов!")
            return
            
        msg = bot.send_message(chat_id, "⏳ Создаю проект...")
        
        try:
            gemini = GeminiChat()
            response = gemini.send_message(user_request, is_project_request=True, image_data=image_data)
            
            if response.startswith('❌'):
                bot.edit_message_text("❌ Ошибка генерации", chat_id, msg.message_id)
                add_requests(user_id, 1, "Возврат")
            else:
                files = parse_project_files(response)
                if files:
                    zip_file = create_zip(files)
                    zip_file.name = "project.zip"
                    
                    bot.delete_message(chat_id, msg.message_id)
                    bot.send_document(chat_id, zip_file, caption=f"🚀 Проект готов! | Баланс: {balance}")
                    add_stat(user_id, "project_generated")
                else:
                    bot.edit_message_text("❌ Не удалось создать проект", chat_id, msg.message_id)
                    add_requests(user_id, 1, "Возврат")
        except Exception as e:
            bot.edit_message_text("❌ Ошибка", chat_id, msg.message_id)
            add_requests(user_id, 1, "Возврат")
        
    elif state == 'waiting_plugin':
        success, balance = use_request(user_id)
        if not success:
            bot.send_message(chat_id, "❌ Нет запросов!")
            return
            
        msg = bot.send_message(chat_id, "⏳ Создаю плагин...")
        
        try:
            gemini = GeminiChat()
            response = gemini.send_message(user_request, is_plugin_request=True, image_data=image_data)
            
            if response.startswith('❌'):
                bot.edit_message_text("❌ Ошибка генерации", chat_id, msg.message_id)
                add_requests(user_id, 1, "Возврат")
            else:
                code = extract_code(response)
                file = io.BytesIO(code.encode())
                file.name = "plugin.py"
                
                bot.delete_message(chat_id, msg.message_id)
                bot.send_document(chat_id, file, caption=f"🔌 Плагин готов! | Баланс: {balance}")
                add_stat(user_id, "plugin_generated")
        except Exception as e:
            bot.edit_message_text("❌ Ошибка", chat_id, msg.message_id)
            add_requests(user_id, 1, "Возврат")
    
    user_states.pop(chat_id, None)

@bot.message_handler(content_types=['document'])
def handle_document(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if user_states.get(chat_id) == 'waiting_file' and message.document.file_name.endswith('.py'):
        try:
            file_info = bot.get_file(message.document.file_id)
            downloaded_file = bot.download_file(file_info.file_path)
            code_content = downloaded_file.decode('utf-8')
            
            user_states[chat_id] = 'waiting_modification'
            user_states[f"{chat_id}_code"] = code_content
            
            if message.caption:
                user_request, image_data = process_image_message(message)
                if user_request and user_request.strip():
                    process_modification(chat_id, user_id, user_request, image_data)
                else:
                    bot.send_message(chat_id, "⚡ Что изменить в коде?")
            else:
                bot.send_message(chat_id, "⚡ Что изменить в коде?")
                
        except Exception as e:
            bot.send_message(chat_id, f"❌ Ошибка чтения файла")
    
    elif user_states.get(chat_id) == 'waiting_modification':
        user_request, image_data = process_image_message(message)
        if user_request and user_request.strip():
            process_modification(chat_id, user_id, user_request, image_data)

def process_modification(chat_id, user_id, user_request, image_data):
    success, balance = use_request(user_id)
    if not success:
        bot.send_message(chat_id, "❌ Нет запросов!")
        return
        
    msg = bot.send_message(chat_id, "⏳ Вношу изменения...")
    original_code = user_states.get(f"{chat_id}_code", "")
    
    try:
        gemini = GeminiChat()
        request_data = f"Код: {original_code}\nЗапрос: {user_request}"
        response = gemini.send_message(request_data, is_code_request=False, image_data=image_data)
        
        if response.startswith('❌'):
            bot.edit_message_text("❌ Ошибка", chat_id, msg.message_id)
            add_requests(user_id, 1, "Возврат")
        else:
            code = extract_code(response)
            file = io.BytesIO(code.encode())
            file.name = "modified_code.py"
            
            bot.delete_message(chat_id, msg.message_id)
            bot.send_document(chat_id, file, caption=f"✅ Изменения применены! | Баланс: {balance}")
            add_stat(user_id, "code_modified")
    except Exception as e:
        bot.edit_message_text("❌ Ошибка", chat_id, msg.message_id)
        add_requests(user_id, 1, "Возврат")
    
    user_states.pop(chat_id, None)
    user_states.pop(f"{chat_id}_code", None)

@bot.message_handler(func=lambda message: True)
def handle_other(message):
    if not check_subscription(message.from_user.id):
        show_subscription_request(message)
        return
    chat_id = message.chat.id
    if user_states.get(chat_id) not in ['waiting_code', 'waiting_project', 'waiting_plugin', 'waiting_file', 'waiting_modification']:
        show_main_menu(message)

def start_keep_alive():
    thread = threading.Thread(target=keep_alive, daemon=True)
    thread.start()

if __name__ == "__main__":
    start_keep_alive()
    print("🚀 Bot started with polling!")
    bot.infinity_polling(timeout=60, long_polling_timeout=60)
