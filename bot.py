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
import time

# Конфигурация
API_KEY = "AIzaSyARZYE8kSTBVlGF_A1jxFdEQdVi5-9MN38"
SELECTED_MODEL = "gemini-2.5-flash-exp-03-25"
CHANNEL_USERNAME = "@GeniAi"
ADMIN_ID = 2202291197
BOT_TOKEN = "2201851225:AAEruvQjAyxiYIcsVCwa-JoIcWaXMx4kqE8/test"

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)
executor = concurrent.futures.ThreadPoolExecutor(max_workers=20)

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

# Быстрые функции для работы с БД
def get_db():
    return sqlite3.connect('bot_stats.db', check_same_thread=False)

def add_user(user_id, username, first_name, last_name):
    conn = get_db()
    conn.execute('INSERT OR IGNORE INTO users (user_id, username, first_name, last_name) VALUES (?, ?, ?, ?)',
                (user_id, username, first_name, last_name))
    conn.commit()
    conn.close()

def update_subscription(user_id, subscribed):
    conn = get_db()
    conn.execute('UPDATE users SET subscribed = ? WHERE user_id = ?', (subscribed, user_id))
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

def add_requests(user_id, amount, reason, admin_id=None):
    current_balance = get_user_balance(user_id)
    new_balance = current_balance + amount
    update_user_balance(user_id, new_balance)
    
    conn = get_db()
    conn.execute('INSERT INTO requests_history (user_id, requests_change, reason, admin_id) VALUES (?, ?, ?, ?)',
                (user_id, amount, reason, admin_id))
    conn.commit()
    conn.close()
    return new_balance

def add_stat(user_id, action_type):
    conn = get_db()
    conn.execute('INSERT INTO stats (user_id, action_type) VALUES (?, ?)', (user_id, action_type))
    conn.commit()
    conn.close()

def get_stats():
    conn = get_db()
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

# Быстрый класс Gemini с обработкой изображений
class FastGemini:
    def __init__(self):
        self.url = f"https://generativelanguage.googleapis.com/v1/models/{SELECTED_MODEL}:generateContent?key={API_KEY}"
        self.headers = {'Content-Type': 'application/json'}
    
    def generate(self, prompt, mode="code", image_data=None):
        if mode == "project":
            system_prompt = """Создай полноценный Python проект. Включи:
- main.py (основной файл)
- README.md (инструкция)
- requirements.txt (зависимости)
- Другие нужные файлы

Формат:
ФАЙЛ: имя_файла
```код
```"""
            full_prompt = f"{system_prompt}\nЗапрос: {prompt}"
        elif mode == "plugin":
            full_prompt = f"""Создай Python плагин для exteragram. Запрос: {prompt}

Формат плагина:
__id__ = "уникальный_ид"
__name__ = "Название плагина" 
__description__ = "Описание плагина"
__author__ = "@автор"
__version__ = "1.0.0"
__min_version__ = "11.12.0"

from base_plugin import BasePlugin, MethodHook

class MyPlugin(BasePlugin):
    def on_plugin_load(self):
        pass

    def create_settings(self):
        return []"""
        elif mode == "modify":
            full_prompt = f"Улучши этот код:\n{prompt['code']}\n\nЗапрос на изменение: {prompt['request']}\n\nСохрани функциональность, добавь комментарии."
        else:
            full_prompt = f"Создай Python код для: {prompt}. Добавь комментарии и описание функциональности."
        
        contents = {"contents": [{"parts": [{"text": full_prompt}]}]}
        
        if image_data:
            contents["contents"][0]["parts"].insert(0, {
                "inline_data": {
                    "mime_type": "image/jpeg", 
                    "data": image_data
                }
            })
        
        try:
            response = requests.post(self.url, headers=self.headers, json=contents, timeout=25)
            if response.status_code == 200:
                result = response.json()
                if result.get('candidates'):
                    return result['candidates'][0]['content']['parts'][0]['text']
            return "❌ Ошибка генерации"
        except requests.exceptions.Timeout:
            return "❌ Таймаут при генерации"
        except Exception as e:
            return f"❌ Ошибка: {str(e)}"

def extract_code(text):
    """Извлекает код и описание из ответа"""
    try:
        if '```python' in text:
            parts = text.split('```python')
            if len(parts) > 1:
                code_part = parts[1].split('```')[0]
                description = parts[0].strip() if parts[0].strip() else "Сгенерированный код"
                return description, code_part.strip()
        
        if '```' in text:
            parts = text.split('```')
            if len(parts) > 2:
                code = parts[1].strip()
                description = parts[0].strip() if parts[0].strip() else "Сгенерированный код"
                return description, code
        
        return "Сгенерированный код", text.strip()
    except:
        return "Сгенерированный код", text

def parse_project_files(text):
    """Парсит несколько файлов из ответа проекта"""
    files = {}
    current_file = None
    current_content = []
    
    for line in text.split('\n'):
        if line.startswith('ФАЙЛ:') or line.startswith('FILE:'):
            if current_file and current_content:
                files[current_file] = '\n'.join(current_content).strip()
            current_file = line.split(':', 1)[1].strip()
            current_content = []
        elif line.strip() and not line.startswith('```'):
            current_content.append(line)
    
    if current_file and current_content:
        files[current_file] = '\n'.join(current_content).strip()
    
    # Если не нашли структуру с ФАЙЛ:, ищем блоки кода
    if not files:
        parts = text.split('```')
        for i in range(0, len(parts)-1, 2):
            if i+1 < len(parts):
                code_block = parts[i+1].strip()
                filename = f"file_{i//2 + 1}.py"
                files[filename] = code_block
    
    return files

def create_zip(files):
    """Создает ZIP архив из файлов"""
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for filename, content in files.items():
            zip_file.writestr(filename, content)
    zip_buffer.seek(0)
    return zip_buffer

def process_image_message(message):
    """Обрабатывает сообщения с изображениями"""
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
    except Exception as e:
        print(f"Ошибка обработки изображения: {e}")
        return caption, None

# Веб-хуки
@app.route('/')
def home():
    return "GeniAi Bot is running!"

@app.route('/health')
def health():
    return "OK"

@app.route('/webhook', methods=['POST'])
def webhook():
    json_str = request.get_data().decode('UTF-8')
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return ''

# Команды бота
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

@bot.message_handler(commands=['request'])
def handle_request_command(message):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        _, user_id, amount = message.text.split()
        user_id = int(user_id)
        amount = int(amount)
        new_balance = add_requests(user_id, amount, "Выдача админом", ADMIN_ID)
        try:
            user_message = f"""🎉 Спасибо за покупку!
📦 Вам выдано {amount} запросов
💰 Текущий баланс: {new_balance} запросов"""
            bot.send_message(user_id, user_message)
        except: pass
        bot.send_message(message.chat.id, f"✅ Пользователю {user_id} выдано {amount} запросов. Новый баланс: {new_balance}")
    except ValueError:
        bot.send_message(message.chat.id, "❌ Неправильный формат. Используйте: /request [id] [количество]")

@bot.message_handler(commands=['users'])
def handle_users_command(message):
    if message.from_user.id != ADMIN_ID:
        return
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT user_id, username, first_name, requests_balance FROM users ORDER BY created_at DESC LIMIT 10')
    users = cursor.fetchall()
    conn.close()
    if not users:
        bot.send_message(message.chat.id, "❌ Пользователей нет")
        return
    text = "👥 Последние 10 пользователей:\n\n"
    for user in users:
        user_id, username, first_name, balance = user
        user_info = f"@{username}" if username else first_name
        text += f"🆔 {user_id} | 👤 {user_info} | 💰 {balance}\n"
    bot.send_message(message.chat.id, text)

def show_subscription_request(message):
    markup = types.InlineKeyboardMarkup()
    markup.row(types.InlineKeyboardButton('📢 Подписаться', url='https://t.me/GeniAi'))
    markup.row(types.InlineKeyboardButton('✅ Проверить подписку', callback_data='check_subscription'))
    bot.send_message(message.chat.id, 
                    "📢 Подпишитесь на канал чтобы продолжить:\n\nhttps://t.me/GeniAi\n\nПосле подписки нажмите ✅ Проверить подписку", 
                    reply_markup=markup)

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
    
    welcome_text = f"""🤖 Привет, я GeniAi!
Ваш помощник для создания Python кодов

💰 Баланс: {balance} запросов
📝 Можно описывать запросы подробно
🖼️ Можно отправлять скриншоты с описанием

Выберите действие:"""
    bot.send_message(message.chat.id, welcome_text, reply_markup=markup)
    user_states[message.chat.id] = 'main_menu'

def show_subscription_info(message):
    user_id = message.from_user.id
    balance = get_user_balance(user_id)
    text = f"""💎 Информация о подписке

💰 У вас {balance} запросов

🛒 Купить запросы: @xostcodingkrytoy

📋 Для покупки отправьте админу:
- Ваш ID: {user_id}
- Количество запросов
- Скриншот оплаты

💳 1 запрос = 2 торта"""
    markup = types.InlineKeyboardMarkup()
    markup.row(types.InlineKeyboardButton('🛒 Купить запросы', url='https://t.me/xostcodingkrytoy'))
    markup.row(types.InlineKeyboardButton('🔙 Назад', callback_data='back_to_menu'))
    bot.send_message(message.chat.id, text, reply_markup=markup)

def show_admin_panel(message):
    stats = get_stats()
    text = f"""👑 Админ панель

📊 Статистика:
👥 Пользователей: {stats['total_users']}
💻 Кодов создано: {stats['codes_generated']}
🚀 Проектов создано: {stats['projects_generated']}  
🔌 Плагинов создано: {stats['plugins_generated']}
⚡ Кодов изменено: {stats['codes_modified']}
📈 Всего запросов: {stats['total_requests']}

⚙️ Команды:
/request [id] [количество] - выдать запросы
/users - список пользователей"""
    bot.send_message(message.chat.id, text)

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    
    if call.data == 'check_subscription':
        if check_subscription(user_id):
            update_subscription(user_id, 1)
            bot.answer_callback_query(call.id, "✅ Спасибо за подписку!")
            show_main_menu(call.message)
        else:
            bot.answer_callback_query(call.id, "❌ Вы еще не подписались на канал!")
        return
    
    if not check_subscription(user_id):
        bot.answer_callback_query(call.id, "❌ Сначала подпишитесь на канал!")
        show_subscription_request(call.message)
        return
    
    if call.data == 'write_code':
        balance = get_user_balance(user_id)
        if balance <= 0:
            bot.answer_callback_query(call.id, "❌ У вас закончились запросы!")
            show_subscription_info(call.message)
        else:
            user_states[chat_id] = 'waiting_code'
            bot.send_message(chat_id, "💻 Опишите какой код нужен (можно отправить скриншот с подписью):")
            
    elif call.data == 'write_project':
        balance = get_user_balance(user_id)
        if balance <= 0:
            bot.answer_callback_query(call.id, "❌ У вас закончились запросы!")
            show_subscription_info(call.message)
        else:
            user_states[chat_id] = 'waiting_project'
            bot.send_message(chat_id, "🚀 Опишите какой проект нужен (можно отправить скриншот с подписью):")
            
    elif call.data == 'write_plugin':
        balance = get_user_balance(user_id)
        if balance <= 0:
            bot.answer_callback_query(call.id, "❌ У вас закончились запросы!")
            show_subscription_info(call.message)
        else:
            user_states[chat_id] = 'waiting_plugin'
            bot.send_message(chat_id, "🔌 Опишите какой плагин нужен (можно отправить скриншот с подписью):")
            
    elif call.data == 'modify_code':
        balance = get_user_balance(user_id)
        if balance <= 0:
            bot.answer_callback_query(call.id, "❌ У вас закончились запросы!")
            show_subscription_info(call.message)
        else:
            user_states[chat_id] = 'waiting_file'
            bot.send_message(chat_id, "⚡ Отправьте .py файл для изменения (можно с описанием в подписи):")
            
    elif call.data == 'stats':
        stats = get_stats()
        user_balance = get_user_balance(user_id)
        stats_text = f"""📊 Статистика бота:

👥 Всего пользователей: {stats['total_users']}
💻 Создано кодов: {stats['codes_generated']}
🚀 Создано проектов: {stats['projects_generated']}
🔌 Создано плагинов: {stats['plugins_generated']}
⚡ Изменено кодов: {stats['codes_modified']}
💰 Ваш баланс: {user_balance} запросов"""
        bot.send_message(chat_id, stats_text)
        
    elif call.data == 'subscription':
        show_subscription_info(call.message)
        
    elif call.data == 'author':
        bot.send_message(chat_id, "👤 Автор бота: @xostcodingkrytoy")
        
    elif call.data == 'admin_panel':
        if user_id == ADMIN_ID:
            show_admin_panel(call.message)
            
    elif call.data == 'back_to_menu':
        show_main_menu(call.message)

# Обработка текстовых сообщений и изображений
@bot.message_handler(content_types=['text', 'photo'])
def handle_messages(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    state = user_states.get(chat_id)
    
    if not state or not check_subscription(user_id):
        return
    
    user_request, image_data = process_image_message(message)
    
    if not user_request or user_request.strip() == "":
        bot.send_message(chat_id, "❌ Пожалуйста, добавьте описание к запросу")
        return
        
    if user_request.startswith('/'):
        show_main_menu(message)
        return
    
    if state == 'waiting_code':
        success, balance = use_request(user_id)
        if not success:
            bot.send_message(chat_id, "❌ У вас закончились запросы!")
            return
            
        processing_msg = bot.send_message(chat_id, "⏳ Код готовится...")
        
        def generate_code():
            try:
                gemini = FastGemini()
                response = gemini.generate(user_request, "code", image_data)
                
                if response.startswith('❌'):
                    bot.edit_message_text("❌ Ошибка при генерации", chat_id, processing_msg.message_id)
                    add_requests(user_id, 1, "Возврат при ошибке")
                else:
                    description, code = extract_code(response)
                    file_buffer = io.BytesIO(code.encode('utf-8'))
                    file_buffer.name = "generated_code.py"
                    
                    bot.delete_message(chat_id, processing_msg.message_id)
                    bot.send_document(chat_id, file_buffer, 
                                     caption=f"✅ Готовый код\n\n📝 Описание:\n{description}\n\n💰 Осталось запросов: {balance}")
                    add_stat(user_id, "code_generated")
            except Exception as e:
                bot.edit_message_text("❌ Ошибка", chat_id, processing_msg.message_id)
                add_requests(user_id, 1, "Возврат при ошибке")
            finally:
                user_states.pop(chat_id, None)
        
        executor.submit(generate_code)
        
    elif state == 'waiting_project':
        success, balance = use_request(user_id)
        if not success:
            bot.send_message(chat_id, "❌ У вас закончились запросы!")
            return
            
        processing_msg = bot.send_message(chat_id, "🚀 Собираю проект...")
        
        def generate_project():
            try:
                gemini = FastGemini()
                response = gemini.generate(user_request, "project", image_data)
                
                if response.startswith('❌'):
                    bot.edit_message_text("❌ Ошибка при генерации", chat_id, processing_msg.message_id)
                    add_requests(user_id, 1, "Возврат при ошибке")
                else:
                    files = parse_project_files(response)
                    if files:
                        zip_buffer = create_zip(files)
                        zip_buffer.name = "project.zip"
                        
                        file_list = "\n".join([f"📄 {filename}" for filename in files.keys()])
                        
                        bot.delete_message(chat_id, processing_msg.message_id)
                        bot.send_document(chat_id, zip_buffer,
                                         caption=f"🚀 Готовый проект!\n\n📁 Файлы в проекте:\n{file_list}\n\n💰 Осталось запросов: {balance}")
                        add_stat(user_id, "project_generated")
                    else:
                        bot.edit_message_text("❌ Не удалось создать проект", chat_id, processing_msg.message_id)
                        add_requests(user_id, 1, "Возврат при ошибке")
            except Exception as e:
                bot.edit_message_text("❌ Ошибка", chat_id, processing_msg.message_id)
                add_requests(user_id, 1, "Возврат при ошибке")
            finally:
                user_states.pop(chat_id, None)
        
        executor.submit(generate_project)
        
    elif state == 'waiting_plugin':
        success, balance = use_request(user_id)
        if not success:
            bot.send_message(chat_id, "❌ У вас закончились запросы!")
            return
            
        processing_msg = bot.send_message(chat_id, "⏳ Плагин готовится...")
        
        def generate_plugin():
            try:
                gemini = FastGemini()
                response = gemini.generate(user_request, "plugin", image_data)
                
                if response.startswith('❌'):
                    bot.edit_message_text("❌ Ошибка при генерации", chat_id, processing_msg.message_id)
                    add_requests(user_id, 1, "Возврат при ошибке")
                else:
                    description, code = extract_code(response)
                    file_buffer = io.BytesIO(code.encode('utf-8'))
                    file_buffer.name = "generated_plugin.plugin"
                    
                    bot.delete_message(chat_id, processing_msg.message_id)
                    bot.send_document(chat_id, file_buffer, 
                                     caption=f"✅ Готовый плагин\n\n📝 Описание:\n{description}\n\n💰 Осталось запросов: {balance}")
                    add_stat(user_id, "plugin_generated")
            except Exception as e:
                bot.edit_message_text("❌ Ошибка", chat_id, processing_msg.message_id)
                add_requests(user_id, 1, "Возврат при ошибке")
            finally:
                user_states.pop(chat_id, None)
        
        executor.submit(generate_plugin)

# Обработка документов
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
            
            # Если есть подпись, используем ее как запрос
            if message.caption:
                user_request, image_data = process_image_message(message)
                if user_request and user_request.strip():
                    process_modification_request(chat_id, user_id, user_request, image_data)
                else:
                    bot.send_message(chat_id, "⚡ Что изменить в коде? (можно отправить скриншот с подписью):")
            else:
                bot.send_message(chat_id, "⚡ Что изменить в коде? (можно отправить скриншот с подписью):")
                
        except Exception as e:
            bot.send_message(chat_id, f"❌ Ошибка при чтении файла: {str(e)}")
    
    elif user_states.get(chat_id) == 'waiting_modification':
        user_request, image_data = process_image_message(message)
        if user_request and user_request.strip():
            process_modification_request(chat_id, user_id, user_request, image_data)

def process_modification_request(chat_id, user_id, user_request, image_data):
    """Обрабатывает запрос на изменение кода"""
    success, balance = use_request(user_id)
    if not success:
        bot.send_message(chat_id, "❌ У вас закончились запросы!")
        return
        
    processing_msg = bot.send_message(chat_id, "⏳ Вносятся изменения...")
    original_code = user_states.get(f"{chat_id}_code", "")
    
    def apply_modification():
        try:
            gemini = FastGemini()
            request_data = {'code': original_code, 'request': user_request}
            response = gemini.generate(request_data, "modify", image_data)
            
            if response.startswith('❌'):
                bot.edit_message_text("❌ Ошибка при изменении кода", chat_id, processing_msg.message_id)
                add_requests(user_id, 1, "Возврат при ошибке")
            else:
                description, modified_code = extract_code(response)
                file_buffer = io.BytesIO(modified_code.encode('utf-8'))
                file_buffer.name = "modified_code.py"
                
                bot.delete_message(chat_id, processing_msg.message_id)
                bot.send_document(chat_id, file_buffer,
                                 caption=f"✅ Измененный код\n\n📝 Что сделано:\n{description}\n\n💰 Осталось запросов: {balance}")
                add_stat(user_id, "code_modified")
        except Exception as e:
            bot.edit_message_text("❌ Ошибка", chat_id, processing_msg.message_id)
            add_requests(user_id, 1, "Возврат при ошибке")
        finally:
            user_states.pop(chat_id, None)
            user_states.pop(f"{chat_id}_code", None)
    
    executor.submit(apply_modification)

if __name__ == "__main__":
    print("🚀 GeniAi Bot started!")
    try:
        bot.remove_webhook()
        time.sleep(1)
        bot.polling(none_stop=True, timeout=60)
    except Exception as e:
        print(f"Error: {e}")
        time.sleep(5)
        bot.infinity_polling()
