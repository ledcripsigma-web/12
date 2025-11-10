import requests
import json
import telebot
from telebot import types
import io
import os
import sqlite3
import base64
import zipfile
from flask import Flask, request
import concurrent.futures

# Конфигурация
API_KEY = "AIzaSyARZYE8kSTBVlGF_A1jxFdEQdVi5-9MN38"
SELECTED_MODEL = "gemini-2.5-flash-exp-03-25"
CHANNEL_USERNAME = "@GeniAi"
ADMIN_ID = 2202291197
BOT_TOKEN = "2201851225:AAEruvQjAyxiYIcsVCwa-JoIcWaXMx4kqE8/test"

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)
executor = concurrent.futures.ThreadPoolExecutor(max_workers=10)

# Инициализация базы данных
def init_db():
    conn = sqlite3.connect('bot_stats.db', check_same_thread=False)
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
    conn.commit()
    conn.close()

init_db()

user_states = {}

# Быстрые функции для работы с БД
def get_db():
    return sqlite3.connect('bot_stats.db', check_same_thread=False)

def add_user(user_id, username, first_name, last_name):
    conn = get_db()
    conn.execute('INSERT OR IGNORE INTO users (user_id, username, first_name, last_name) VALUES (?, ?, ?, ?)',
                (user_id, username, first_name, last_name))
    conn.commit()
    conn.close()

def get_user_balance(user_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT requests_balance FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else 0

def update_user_balance(user_id, new_balance):
    conn = get_db()
    conn.execute('UPDATE users SET requests_balance = ? WHERE user_id = ?', (new_balance, user_id))
    conn.commit()
    conn.close()

def use_request(user_id):
    current_balance = get_user_balance(user_id)
    if current_balance > 0:
        new_balance = current_balance - 1
        update_user_balance(user_id, new_balance)
        return True, new_balance
    return False, current_balance

def add_stat(user_id, action_type):
    conn = get_db()
    conn.execute('INSERT INTO stats (user_id, action_type) VALUES (?, ?)', (user_id, action_type))
    conn.commit()
    conn.close()

def check_subscription(user_id):
    try:
        chat_member = bot.get_chat_member(CHANNEL_USERNAME, user_id)
        return chat_member.status in ['member', 'administrator', 'creator']
    except:
        return False

# Супер быстрый класс Gemini
class FastGemini:
    def __init__(self):
        self.url = f"https://generativelanguage.googleapis.com/v1/models/{SELECTED_MODEL}:generateContent?key={API_KEY}"
        self.headers = {'Content-Type': 'application/json'}
    
    def generate(self, prompt, mode="code"):
        if mode == "project":
            system_prompt = "Создай Python проект. Формат: ФАЙЛ: имя_файла\n```код```"
            full_prompt = f"{system_prompt}\nЗапрос: {prompt}"
        elif mode == "plugin":
            full_prompt = f"Создай exteragram плагин: {prompt}"
        else:
            full_prompt = f"Создай Python код: {prompt}"
        
        data = {
            "contents": [{"parts": [{"text": full_prompt}]}],
            "generationConfig": {
                "temperature": 0.7,
                "maxOutputTokens": 2048,
            }
        }
        
        try:
            response = requests.post(self.url, headers=self.headers, json=data, timeout=15)
            if response.status_code == 200:
                result = response.json()
                if result.get('candidates'):
                    return result['candidates'][0]['content']['parts'][0]['text']
            return "❌ Ошибка"
        except:
            return "❌ Таймаут"

def extract_code(text):
    if '```python' in text:
        return text.split('```python')[1].split('```')[0].strip()
    elif '```' in text:
        return text.split('```')[1].strip()
    return text

def parse_project(text):
    files = {}
    current_file = None
    
    for line in text.split('\n'):
        if line.startswith('ФАЙЛ:'):
            current_file = line[5:].strip()
            files[current_file] = ""
        elif current_file and line.strip() and not line.startswith('```'):
            files[current_file] += line + '\n'
    
    return {k: v.strip() for k, v in files.items() if v.strip()}

def create_zip(files):
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    zip_buffer.seek(0)
    return zip_buffer

# Обработчики бота
@app.route('/')
def home():
    return "Bot Running!"

@app.route('/webhook', methods=['POST'])
def webhook():
    json_str = request.get_data().decode('UTF-8')
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return ''


@bot.message_handler(commands=['start'])
def start_cmd(message):
    user_id = message.from_user.id
    add_user(user_id, message.from_user.username, message.from_user.first_name, message.from_user.last_name)
    
    if check_subscription(user_id):
        show_main_menu(message)
    else:
        show_subscription_request(message)

def show_subscription_request(message):
    markup = types.InlineKeyboardMarkup()
    markup.row(types.InlineKeyboardButton('📢 Подписаться', url='https://t.me/GeniAi'))
    markup.row(types.InlineKeyboardButton('✅ Проверить', callback_data='check_sub'))
    bot.send_message(message.chat.id, "Подпишись на канал!", reply_markup=markup)

def show_main_menu(message):
    user_id = message.from_user.id
    balance = get_user_balance(user_id)
    
    markup = types.InlineKeyboardMarkup()
    markup.row(types.InlineKeyboardButton('💻 Код', callback_data='code'))
    markup.row(types.InlineKeyboardButton('🚀 Проект', callback_data='project'))
    markup.row(types.InlineKeyboardButton('🔌 Плагин', callback_data='plugin'))
    markup.row(types.InlineKeyboardButton('⚡ Изменить', callback_data='modify'))
    markup.row(types.InlineKeyboardButton('📊 Статистика', callback_data='stats'),
               types.InlineKeyboardButton('💎 Подписка', callback_data='sub_info'))
    
    if user_id == ADMIN_ID:
        markup.row(types.InlineKeyboardButton('👑 Админ', callback_data='admin'))
    
    bot.send_message(message.chat.id, f"🤖 GeniAI | Баланс: {balance}", reply_markup=markup)

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
    
    if call.data == 'code':
        if get_user_balance(user_id) <= 0:
            bot.answer_callback_query(call.id, "❌ Нет запросов!")
            return
        user_states[chat_id] = 'waiting_code'
        bot.send_message(chat_id, "💻 Опиши что нужно:")
        
    elif call.data == 'project':
        if get_user_balance(user_id) <= 0:
            bot.answer_callback_query(call.id, "❌ Нет запросов!")
            return
        user_states[chat_id] = 'waiting_project'
        bot.send_message(chat_id, "🚀 Опиши проект:")
        
    elif call.data == 'plugin':
        if get_user_balance(user_id) <= 0:
            bot.answer_callback_query(call.id, "❌ Нет запросов!")
            return
        user_states[chat_id] = 'waiting_plugin'
        bot.send_message(chat_id, "🔌 Опиши плагин:")
        
    elif call.data == 'modify':
        if get_user_balance(user_id) <= 0:
            bot.answer_callback_query(call.id, "❌ Нет запросов!")
            return
        user_states[chat_id] = 'waiting_file'
        bot.send_message(chat_id, "⚡ Отправь .py файл:")
        
    elif call.data == 'stats':
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM stats WHERE action_type = "code_generated"')
        codes = cursor.fetchone()[0]
        cursor.execute('SELECT COUNT(*) FROM stats WHERE action_type = "project_generated"')
        projects = cursor.fetchone()[0]
        conn.close()
        
        bot.send_message(chat_id, f"📊 Статистика:\nКоды: {codes}\nПроекты: {projects}\nБаланс: {get_user_balance(user_id)}")
        
    elif call.data == 'sub_info':
        bot.send_message(chat_id, "💎 Для покупки запросов: @xostcodingkrytoy")
        
    elif call.data == 'admin' and user_id == ADMIN_ID:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM users')
        users = cursor.fetchone()[0]
        conn.close()
        bot.send_message(chat_id, f"👑 Админка\nПользователей: {users}")

@bot.message_handler(content_types=['text'])
def handle_text(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    state = user_states.get(chat_id)
    
    if not state or not check_subscription(user_id):
        return
    
    text = message.text.strip()
    if not text:
        return
    
    # Используем ThreadPoolExecutor для мгновенного ответа
    if state == 'waiting_code':
        success, balance = use_request(user_id)
        if not success:
            bot.send_message(chat_id, "❌ Нет запросов!")
            return
            
        processing_msg = bot.send_message(chat_id, "⚡ Генерирую...")
        
        def generate_code():
            try:
                gemini = FastGemini()
                response = gemini.generate(text, "code")
                
                if response.startswith('❌'):
                    bot.edit_message_text("❌ Ошибка", chat_id, processing_msg.message_id)
                    update_user_balance(user_id, balance + 1)  # Возвращаем запрос
                else:
                    code = extract_code(response)
                    file = io.BytesIO(code.encode())
                    file.name = "code.py"
                    
                    bot.delete_message(chat_id, processing_msg.message_id)
                    bot.send_document(chat_id, file, caption=f"✅ Готово! | Баланс: {balance}")
                    add_stat(user_id, "code_generated")
            except Exception as e:
                bot.edit_message_text("❌ Ошибка генерации", chat_id, processing_msg.message_id)
                update_user_balance(user_id, balance + 1)
        
        executor.submit(generate_code)
        
    elif state == 'waiting_project':
        success, balance = use_request(user_id)
        if not success:
            bot.send_message(chat_id, "❌ Нет запросов!")
            return
            
        processing_msg = bot.send_message(chat_id, "⚡ Собираю проект...")
        
        def generate_project():
            try:
                gemini = FastGemini()
                response = gemini.generate(text, "project")
                
                if response.startswith('❌'):
                    bot.edit_message_text("❌ Ошибка", chat_id, processing_msg.message_id)
                    update_user_balance(user_id, balance + 1)
                else:
                    files = parse_project(response)
                    if files:
                        zip_file = create_zip(files)
                        zip_file.name = "project.zip"
                        
                        bot.delete_message(chat_id, processing_msg.message_id)
                        bot.send_document(chat_id, zip_file, caption=f"🚀 Проект готов! | Баланс: {balance}")
                        add_stat(user_id, "project_generated")
                    else:
                        bot.edit_message_text("❌ Не удалось создать проект", chat_id, processing_msg.message_id)
                        update_user_balance(user_id, balance + 1)
            except Exception as e:
                bot.edit_message_text("❌ Ошибка", chat_id, processing_msg.message_id)
                update_user_balance(user_id, balance + 1)
        
        executor.submit(generate_project)
        
    elif state == 'waiting_plugin':
        success, balance = use_request(user_id)
        if not success:
            bot.send_message(chat_id, "❌ Нет запросов!")
            return
            
        processing_msg = bot.send_message(chat_id, "⚡ Создаю плагин...")
        
        def generate_plugin():
            try:
                gemini = FastGemini()
                response = gemini.generate(text, "plugin")
                
                if response.startswith('❌'):
                    bot.edit_message_text("❌ Ошибка", chat_id, processing_msg.message_id)
                    update_user_balance(user_id, balance + 1)
                else:
                    code = extract_code(response)
                    file = io.BytesIO(code.encode())
                    file.name = "plugin.py"
                    
                    bot.delete_message(chat_id, processing_msg.message_id)
                    bot.send_document(chat_id, file, caption=f"🔌 Плагин готов! | Баланс: {balance}")
                    add_stat(user_id, "plugin_generated")
            except Exception as e:
                bot.edit_message_text("❌ Ошибка", chat_id, processing_msg.message_id)
                update_user_balance(user_id, balance + 1)
        
        executor.submit(generate_plugin)
    
    user_states.pop(chat_id, None)

@bot.message_handler(content_types=['document'])
def handle_document(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if user_states.get(chat_id) == 'waiting_file' and message.document.file_name.endswith('.py'):
        success, balance = use_request(user_id)
        if not success:
            bot.send_message(chat_id, "❌ Нет запросов!")
            return
        
        processing_msg = bot.send_message(chat_id, "⚡ Читаю файл...")
        
        def modify_code():
            try:
                file_info = bot.get_file(message.document.file_id)
                file_content = bot.download_file(file_info.file_path).decode()
                
                user_states[chat_id] = 'waiting_modification'
                user_states[f"{chat_id}_code"] = file_content
                
                bot.edit_message_text("📝 Что изменить в коде?", chat_id, processing_msg.message_id)
                
            except Exception as e:
                bot.edit_message_text("❌ Ошибка чтения файла", chat_id, processing_msg.message_id)
                update_user_balance(user_id, balance + 1)
        
        executor.submit(modify_code)
    elif user_states.get(chat_id) == 'waiting_modification':
        text = message.text.strip()
        if text:
            processing_msg = bot.send_message(chat_id, "⚡ Вношу изменения...")
            original_code = user_states.get(f"{chat_id}_code", "")
            balance = get_user_balance(user_id)
            
            def apply_modification():
                try:
                    gemini = FastGemini()
                    prompt = f"Исходный код:\n{original_code}\n\nЗапрос на изменение: {text}"
                    response = gemini.generate(prompt, "code")
                    
                    if response.startswith('❌'):
                        bot.edit_message_text("❌ Ошибка", chat_id, processing_msg.message_id)
                    else:
                        modified_code = extract_code(response)
                        file = io.BytesIO(modified_code.encode())
                        file.name = "modified_code.py"
                        
                        bot.delete_message(chat_id, processing_msg.message_id)
                        bot.send_document(chat_id, file, caption=f"✅ Изменения применены! | Баланс: {balance}")
                        add_stat(user_id, "code_modified")
                except Exception as e:
                    bot.edit_message_text("❌ Ошибка", chat_id, processing_msg.message_id)
                
                user_states.pop(chat_id, None)
                user_states.pop(f"{chat_id}_code", None)
            
            executor.submit(apply_modification)

if __name__ == "__main__":
    print("🚀 Bot started!")
    try:
        bot.remove_webhook()
        bot.polling(none_stop=True, timeout=60)
    except Exception as e:
        print(f"Error: {e}")
        bot.infinity_polling()
