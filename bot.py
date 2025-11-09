import requests
import json
import telebot
from telebot import types
import io
import os
import threading
import time
from flask import Flask, request
import sqlite3
from datetime import datetime

# Конфигурация
API_KEY = "AIzaSyB5goqEKTAWUedBYDL1mPxgTiBSGhuAlbM"
BOT_TOKEN = "2201851225:AAEruvQjAyxiYIcsVCwa-JoIcWaXMx4kqE8/test"
SELECTED_MODEL = "gemini-pro"
CHANNEL_USERNAME = "@GeniAi"
ADMIN_ID = 2202291197  # Твой ID

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

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
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS requests_history (
            user_id INTEGER,
            requests_change INTEGER,
            reason TEXT,
            admin_id INTEGER,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# Хранилище состояний пользователей
user_states = {}
admin_states = {}

def keep_alive():
    """Функция для поддержания бота активным"""
    while True:
        try:
            response = requests.get("https://one2-1-04er.onrender.com/", timeout=10)
            print(f"✅ Keep-alive запрос отправлен: {response.status_code}")
        except Exception as e:
            print(f"❌ Ошибка keep-alive: {e}")
        time.sleep(240)

def add_user(user_id, username, first_name, last_name):
    """Добавляет пользователя в базу"""
    conn = sqlite3.connect('bot_stats.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR IGNORE INTO users (user_id, username, first_name, last_name, requests_balance)
        VALUES (?, ?, ?, ?, 5)
    ''', (user_id, username, first_name, last_name))
    conn.commit()
    conn.close()

def update_subscription(user_id, subscribed):
    """Обновляет статус подписки"""
    conn = sqlite3.connect('bot_stats.db')
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE users SET subscribed = ? WHERE user_id = ?
    ''', (subscribed, user_id))
    conn.commit()
    conn.close()

def get_user_balance(user_id):
    """Получает баланс запросов пользователя"""
    conn = sqlite3.connect('bot_stats.db')
    cursor = conn.cursor()
    cursor.execute('SELECT requests_balance FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else 0

def update_user_balance(user_id, new_balance):
    """Обновляет баланс запросов пользователя"""
    conn = sqlite3.connect('bot_stats.db')
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE users SET requests_balance = ? WHERE user_id = ?
    ''', (new_balance, user_id))
    conn.commit()
    conn.close()

def add_requests(user_id, amount, reason, admin_id=None):
    """Добавляет запросы пользователю"""
    current_balance = get_user_balance(user_id)
    new_balance = current_balance + amount
    
    conn = sqlite3.connect('bot_stats.db')
    cursor = conn.cursor()
    
    # Обновляем баланс
    cursor.execute('UPDATE users SET requests_balance = ? WHERE user_id = ?', (new_balance, user_id))
    
    # Добавляем в историю
    cursor.execute('''
        INSERT INTO requests_history (user_id, requests_change, reason, admin_id)
        VALUES (?, ?, ?, ?)
    ''', (user_id, amount, reason, admin_id))
    
    conn.commit()
    conn.close()
    
    return new_balance

def use_request(user_id):
    """Использует один запрос"""
    current_balance = get_user_balance(user_id)
    if current_balance > 0:
        new_balance = current_balance - 1
        update_user_balance(user_id, new_balance)
        return True, new_balance
    return False, current_balance

def add_stat(user_id, action_type):
    """Добавляет статистику действия"""
    conn = sqlite3.connect('bot_stats.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO stats (user_id, action_type) VALUES (?, ?)
    ''', (user_id, action_type))
    conn.commit()
    conn.close()

def get_stats():
    """Получает общую статистику"""
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
    
    cursor.execute('SELECT SUM(requests_balance) FROM users')
    total_requests = cursor.fetchone()[0] or 0
    
    conn.close()
    
    return {
        'total_users': total_users,
        'codes_generated': codes_generated,
        'plugins_generated': plugins_generated,
        'codes_modified': codes_modified,
        'total_requests': total_requests
    }

def check_subscription(user_id):
    """Проверяет подписку пользователя на канал"""
    try:
        chat_member = bot.get_chat_member(CHANNEL_USERNAME, user_id)
        return chat_member.status in ['member', 'administrator', 'creator']
    except:
        return False

class GeminiChat:
    def __init__(self, model=SELECTED_MODEL):
        self.url = f"https://generativelanguage.googleapis.com/v1/models/{model}:generateContent?key={API_KEY}"
        self.headers = {'Content-Type': 'application/json'}
    
    def send_message(self, message, is_code_request=True, is_plugin_request=False):
        if is_plugin_request:
            prompt = f"""
            Ты - AI помощник для создания плагинов на Python. Отвечай ТОЛЬКО кодом и кратким описанием.

            Запрос пользователя: {message}

            Используй библиотеку: plugins_exteragram_app
            Используй code reasoning и context7

            Требования для плагина:
            1. Создай полноценный Python плагин для exteragram
            2. Добавь все необходимые импорты
            3. В начале файла добавь метаданные плагина
            4. Наследуй от BasePlugin
            5. Добавь все необходимые методы
            6. Добавь комментарии в код где это уместно

            Формат ответа:
            Описание: [краткое описание 2-3 предложения]
            Код: [python код плагина]
            """
        elif is_code_request:
            prompt = f"""
            Ты - AI помощник для создания Python кодов. Отвечай ТОЛЬКО кодом и кратким описанием.

            Запрос пользователя: {message}

            Требования:
            1. Создай полноценный Python код
            2. Добавь комментарии в код где это уместно
            3. В начале файла добавь многострочный комментарий с описанием что делает код

            Формат ответа:
            Описание: [краткое описание 2-3 предложения]
            Код: [python код]
            """
        else:
            prompt = f"""
            Проанализируй и улучши следующий Python код согласно запросу пользователя.

            Исходный код:
            {message['code']}

            Запрос на изменение: {message['request']}

            Требования:
            1. Сохрани основную функциональность
            2. Внеси запрошенные изменения
            3. Улучши код если это необходимо
            4. Добавь/обнови комментарии

            Формат ответа:
            Описание: [что было изменено]
            Код: [измененный python код]
            """
        
        data = {
            "contents": [{
                "parts": [{"text": prompt}]
            }]
        }
        
        try:
            response = requests.post(self.url, headers=self.headers, json=data, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                if 'candidates' in result and result['candidates']:
                    return result['candidates'][0]['content']['parts'][0]['text']
                else:
                    return "❌ Ошибка: Пустой ответ от API"
            else:
                error_data = response.json()
                error_msg = error_data.get('error', {}).get('message', 'Неизвестная ошибка')
                return f"❌ Ошибка API ({response.status_code}): {error_msg}"
                
        except requests.exceptions.Timeout:
            return "❌ Таймаут при запросе к API"
        except Exception as e:
            return f"❌ Ошибка соединения: {str(e)}"

def parse_code_response(response):
    try:
        if 'Описание:' in response and 'Код:' in response:
            parts = response.split('Код:')
            description = parts[0].replace('Описание:', '').strip()
            code = parts[1].strip()
            return description, code
        
        if '```python' in response:
            parts = response.split('```python')
            if len(parts) >= 2:
                code_part = parts[1].split('```')[0]
                description = parts[0].strip()
                return description, code_part.strip()
        
        if '```' in response:
            parts = response.split('```')
            if len(parts) >= 3:
                code = parts[1].strip()
                description = parts[0].strip() if parts[0].strip() else "📝 Сгенерированный код"
                return description, code
        
        return "📝 Сгенерированный код", response
        
    except Exception as e:
        return f"❌ Ошибка при разборе ответа", response

@app.route('/')
def home():
    return "🤖 GeniAi Bot is running!"

@app.route('/health')
def health():
    return "✅ OK"

@app.route('/webhook', methods=['POST'])
def webhook():
    update = request.get_json()
    if update:
        bot.process_new_updates([telebot.types.Update.de_json(update)])
    return 'OK'

@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    last_name = message.from_user.last_name
    
    add_user(user_id, username, first_name, last_name)
    
    if check_subscription(user_id):
        update_subscription(user_id, 1)
        show_main_menu(message)
    else:
        update_subscription(user_id, 0)
        show_subscription_request(message)

def show_subscription_request(message):
    markup = types.InlineKeyboardMarkup()
    subscribe_btn = types.InlineKeyboardButton('Подписаться ✅', url='https://t.me/GeniAi')
    check_btn = types.InlineKeyboardButton('Проверить подписку 🔄', callback_data='check_subscription')
    markup.add(subscribe_btn)
    markup.add(check_btn)
    
    text = """📢 Подпишитесь на канал чтобы продолжить:
    
👉 https://t.me/GeniAi

После подписки нажмите кнопку «Проверить подписку»"""
    
    bot.send_message(message.chat.id, text, reply_markup=markup)

def show_main_menu(message):
    user_id = message.from_user.id
    balance = get_user_balance(user_id)
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    btn1 = types.InlineKeyboardButton('📝 Написать код', callback_data='write_code')
    btn2 = types.InlineKeyboardButton('🔌 Написать плагин', callback_data='write_plugin')
    btn3 = types.InlineKeyboardButton('🔧 Изменить готовый', callback_data='modify_code')
    btn4 = types.InlineKeyboardButton('📊 Статистика', callback_data='stats')
    btn5 = types.InlineKeyboardButton('💎 Подписка', callback_data='subscription')
    btn6 = types.InlineKeyboardButton('👨‍💻 Автор бота', callback_data='author')
    
    # Добавляем админ-панель только для админа
    if message.from_user.id == ADMIN_ID:
        btn7 = types.InlineKeyboardButton('👑 Админ панель', callback_data='admin_panel')
        markup.add(btn1, btn2, btn3, btn4, btn5, btn6, btn7)
    else:
        markup.add(btn1, btn2, btn3, btn4, btn5, btn6)
    
    welcome_text = f"""🤖 Привет, я GeniAi!
Ваш помощник для создания Python кодов и плагинов

💎 Ваш баланс: {balance} запросов

Просто выберите, с чего начнём:"""
    
    bot.send_message(message.chat.id, welcome_text, reply_markup=markup)
    user_states[message.chat.id] = 'main_menu'

def show_subscription_info(message):
    user_id = message.from_user.id
    balance = get_user_balance(user_id)
    
    text = f"""💎 **Информация о подписке**

У вас **{balance} запросов** 🧑‍💻

💳 Купить запросы: @xostcodingkrytoy

📝 Для покупки отправьте админу:
- Ваш ID: `{user_id}`
- Количество запросов
- Скриншот оплаты

💰 1 запрос = 2 торта"""
    
    markup = types.InlineKeyboardMarkup()
    buy_btn = types.InlineKeyboardButton('💳 Купить запросы', url='https://t.me/xostcodingkrytoy')
    back_btn = types.InlineKeyboardButton('🔙 Назад', callback_data='back_to_menu')
    markup.add(buy_btn)
    markup.add(back_btn)
    
    bot.send_message(message.chat.id, text, reply_markup=markup, parse_mode='Markdown')

def show_admin_panel(message):
    stats = get_stats()
    
    text = f"""👑 **Админ панель**

📊 Статистика:
👥 Пользователей: {stats['total_users']}
📝 Кодов создано: {stats['codes_generated']}
🔌 Плагинов создано: {stats['plugins_generated']}
🔧 Кодов изменено: {stats['codes_modified']}
💎 Всего запросов: {stats['total_requests']}

⚙️ Команды:
/request [id] [количество] - выдать запросы пользователю
/users - список пользователей"""
    
    bot.send_message(message.chat.id, text, parse_mode='Markdown')

@bot.message_handler(commands=['request'])
def handle_request_command(message):
    if message.from_user.id != ADMIN_ID:
        return
    
    try:
        _, user_id, amount = message.text.split()
        user_id = int(user_id)
        amount = int(amount)
        
        new_balance = add_requests(user_id, amount, "Выдача админом", ADMIN_ID)
        
        # Уведомляем пользователя
        try:
            user_info = f"Пользователь {user_id}"
            conn = sqlite3.connect('bot_stats.db')
            cursor = conn.cursor()
            cursor.execute('SELECT username, first_name FROM users WHERE user_id = ?', (user_id,))
            user_data = cursor.fetchone()
            conn.close()
            
            if user_data:
                username, first_name = user_data
                user_info = f"@{username}" if username else first_name
            
            user_message = f"""🎉 Спасибо за покупку! 👑

💎 Вам было выдано **{amount}** запросов
💰 Ваш текущий баланс: **{new_balance} запросов**

Приятного использования! 🚀"""
            
            bot.send_message(user_id, user_message, parse_mode='Markdown')
        except:
            pass
        
        bot.send_message(message.chat.id, f"✅ Пользователю {user_info} выдано {amount} запросов. Новый баланс: {new_balance}")
        
    except ValueError:
        bot.send_message(message.chat.id, "❌ Неправильный формат. Используйте: /request [id] [количество]")

@bot.message_handler(commands=['users'])
def handle_users_command(message):
    if message.from_user.id != ADMIN_ID:
        return
    
    conn = sqlite3.connect('bot_stats.db')
    cursor = conn.cursor()
    cursor.execute('SELECT user_id, username, first_name, requests_balance FROM users ORDER BY created_at DESC LIMIT 10')
    users = cursor.fetchall()
    conn.close()
    
    if not users:
        bot.send_message(message.chat.id, "📭 Пользователей нет")
        return
    
    text = "👥 Последние 10 пользователей:\n\n"
    for user in users:
        user_id, username, first_name, balance = user
        user_info = f"@{username}" if username else first_name
        text += f"🆔 {user_id} | 👤 {user_info} | 💎 {balance}\n"
    
    bot.send_message(message.chat.id, text)

@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    
    if call.data == 'check_subscription':
        if check_subscription(user_id):
            update_subscription(user_id, 1)
            bot.answer_callback_query(call.id, "✅ Спасибо за подписку!")
            show_main_menu(call.message)
        else:
            bot.answer_callback_query(call.id, "❌ Вы еще не подписались на канал!")
    
    elif check_subscription(user_id):
        if call.data == 'write_code':
            balance = get_user_balance(user_id)
            if balance <= 0:
                bot.answer_callback_query(call.id, "❌ У вас закончились запросы!")
                show_subscription_info(call.message)
            else:
                msg = bot.send_message(chat_id, "💡 Опишите, какой код вам нужен:")
                bot.register_next_step_handler(msg, process_code_request)
                user_states[chat_id] = 'waiting_code_request'
            
        elif call.data == 'write_plugin':
            balance = get_user_balance(user_id)
            if balance <= 0:
                bot.answer_callback_query(call.id, "❌ У вас закончились запросы!")
                show_subscription_info(call.message)
            else:
                msg = bot.send_message(chat_id, "🔌 Опишите, какой плагин вам нужен:")
                bot.register_next_step_handler(msg, process_plugin_request)
                user_states[chat_id] = 'waiting_plugin_request'
            
        elif call.data == 'modify_code':
            balance = get_user_balance(user_id)
            if balance <= 0:
                bot.answer_callback_query(call.id, "❌ У вас закончились запросы!")
                show_subscription_info(call.message)
            else:
                msg = bot.send_message(chat_id, "📎 Отправьте ваш .py файл, который нужно изменить")
                user_states[chat_id] = 'waiting_code_file'
            
        elif call.data == 'stats':
            stats = get_stats()
            user_balance = get_user_balance(user_id)
            stats_text = f"""📊 Статистика бота:

👥 Всего пользователей: {stats['total_users']}
📝 Создано кодов: {stats['codes_generated']}
🔌 Создано плагинов: {stats['plugins_generated']}
🔧 Изменено кодов: {stats['codes_modified']}
💎 Ваш баланс: {user_balance} запросов"""
            
            bot.send_message(chat_id, stats_text)
            
        elif call.data == 'subscription':
            show_subscription_info(call.message)
            
        elif call.data == 'author':
            bot.send_message(chat_id, "👨‍💻 Автор бота: @xostcodingkrytoy")
            
        elif call.data == 'admin_panel':
            if user_id == ADMIN_ID:
                show_admin_panel(call.message)
                
        elif call.data == 'back_to_menu':
            show_main_menu(call.message)
    
    else:
        bot.answer_callback_query(call.id, "❌ Сначала подпишитесь на канал!")
        show_subscription_request(call.message)

def process_code_request(message):
    if not check_subscription(message.from_user.id):
        show_subscription_request(message)
        return
        
    user_id = message.from_user.id
    success, new_balance = use_request(user_id)
    
    if not success:
        bot.send_message(message.chat.id, "❌ У вас закончились запросы! Нажмите на подписку чтобы купить новые 💎")
        show_subscription_info(message)
        return
        
    chat_id = message.chat.id
    user_request = message.text
    
    if user_request.startswith('/'):
        show_main_menu(message)
        return
    
    processing_msg = bot.send_message(chat_id, "⚙️ Код готовится... Это может занять несколько секунд")
    
    try:
        gemini = GeminiChat()
        response = gemini.send_message(user_request, is_code_request=True)
        
        if response.startswith('❌'):
            bot.delete_message(chat_id, processing_msg.message_id)
            bot.send_message(chat_id, response)
            # Возвращаем запрос если ошибка
            add_requests(user_id, 1, "Возврат при ошибке")
        else:
            description, code = parse_code_response(response)
            
            file_buffer = io.BytesIO(code.encode('utf-8'))
            file_buffer.name = "generated_code.py"
            
            bot.delete_message(chat_id, processing_msg.message_id)
            bot.send_document(chat_id, file_buffer, 
                             caption=f"📁 Готовый код\n\n📝 Описание:\n{description}\n\n💎 Осталось запросов: {new_balance}")
            user_states[chat_id] = 'main_menu'
            
            add_stat(user_id, "code_generated")
        
    except Exception as e:
        bot.delete_message(chat_id, processing_msg.message_id)
        bot.send_message(chat_id, f"❌ Произошла ошибка при генерации кода: {str(e)}")
        # Возвращаем запрос если ошибка
        add_requests(user_id, 1, "Возврат при ошибке")

def process_plugin_request(message):
    if not check_subscription(message.from_user.id):
        show_subscription_request(message)
        return
        
    user_id = message.from_user.id
    success, new_balance = use_request(user_id)
    
    if not success:
        bot.send_message(message.chat.id, "❌ У вас закончились запросы! Нажмите на подписку чтобы купить новые 💎")
        show_subscription_info(message)
        return
        
    chat_id = message.chat.id
    user_request = message.text
    
    if user_request.startswith('/'):
        show_main_menu(message)
        return
    
    processing_msg = bot.send_message(chat_id, "⚙️ Плагин готовится... Это может занять несколько секунд")
    
    try:
        gemini = GeminiChat()
        response = gemini.send_message(user_request, is_code_request=False, is_plugin_request=True)
        
        if response.startswith('❌'):
            bot.delete_message(chat_id, processing_msg.message_id)
            bot.send_message(chat_id, response)
            add_requests(user_id, 1, "Возврат при ошибке")
        else:
            description, code = parse_code_response(response)
            
            file_buffer = io.BytesIO(code.encode('utf-8'))
            file_buffer.name = "generated_plugin.py"
            
            bot.delete_message(chat_id, processing_msg.message_id)
            bot.send_document(chat_id, file_buffer, 
                             caption=f"🔌 Готовый плагин\n\n📝 Описание:\n{description}\n\n💎 Осталось запросов: {new_balance}")
            user_states[chat_id] = 'main_menu'
            
            add_stat(user_id, "plugin_generated")
        
    except Exception as e:
        bot.delete_message(chat_id, processing_msg.message_id)
        bot.send_message(chat_id, f"❌ Произошла ошибка при генерации плагина: {str(e)}")
        add_requests(user_id, 1, "Возврат при ошибке")

@bot.message_handler(content_types=['document'])
def handle_document(message):
    if not check_subscription(message.from_user.id):
        show_subscription_request(message)
        return
        
    chat_id = message.chat.id
    
    if user_states.get(chat_id) == 'waiting_code_file':
        if message.document.file_name and message.document.file_name.endswith('.py'):
            try:
                file_info = bot.get_file(message.document.file_id)
                downloaded_file = bot.download_file(file_info.file_path)
                code_content = downloaded_file.decode('utf-8')
                
                user_states[chat_id] = {'state': 'waiting_modification_request', 'code': code_content}
                msg = bot.send_message(chat_id, "✏️ Что вы хотите изменить в коде?")
                bot.register_next_step_handler(msg, process_modification_request)
                
            except Exception as e:
                bot.send_message(chat_id, f"❌ Ошибка при чтении файла: {str(e)}")
        else:
            bot.send_message(chat_id, "❌ Пожалуйста, отправьте именно Python файл (.py)")
    else:
        bot.send_message(chat_id, "❌ Сначала нажмите 'Изменить готовый'")

def process_modification_request(message):
    if not check_subscription(message.from_user.id):
        show_subscription_request(message)
        return
        
    user_id = message.from_user.id
    success, new_balance = use_request(user_id)
    
    if not success:
        bot.send_message(message.chat.id, "❌ У вас закончились запросы! Нажмите на подписку чтобы купить новые 💎")
        show_subscription_info(message)
        return
        
    chat_id = message.chat.id
    modification_request = message.text
    
    if modification_request.startswith('/'):
        show_main_menu(message)
        return
    
    user_data = user_states.get(chat_id, {})
    original_code = user_data.get('code', '')
    
    if not original_code:
        bot.send_message(chat_id, "❌ Не удалось найти исходный код. Попробуйте снова.")
        return
    
    processing_msg = bot.send_message(chat_id, "⚙️ Вносятся изменения в код...")
    
    try:
        gemini = GeminiChat()
        request_data = {
            'code': original_code,
            'request': modification_request
        }
        response = gemini.send_message(request_data, is_code_request=False)
        
        if response.startswith('❌'):
            bot.delete_message(chat_id, processing_msg.message_id)
            bot.send_message(chat_id, response)
            add_requests(user_id, 1, "Возврат при ошибке")
        else:
            description, modified_code = parse_code_response(response)
            
            file_buffer = io.BytesIO(modified_code.encode('utf-8'))
            file_buffer.name = "modified_code.py"
            
            bot.delete_message(chat_id, processing_msg.message_id)
            bot.send_document(chat_id, file_buffer,
                             caption=f"📁 Измененный код\n\n📝 Что было сделано:\n{description}\n\n💎 Осталось запросов: {new_balance}")
            user_states[chat_id] = 'main_menu'
            
            add_stat(user_id, "code_modified")
        
    except Exception as e:
        bot.delete_message(chat_id, processing_msg.message_id)
        bot.send_message(chat_id, f"❌ Произошла ошибка при изменении кода: {str(e)}")
        add_requests(user_id, 1, "Возврат при ошибке")

@bot.message_handler(func=lambda message: True)
def handle_other_messages(message):
    if not check_subscription(message.from_user.id):
        show_subscription_request(message)
        return
        
    chat_id = message.chat.id
    if user_states.get(chat_id) not in ['waiting_code_request', 'waiting_plugin_request', 'waiting_code_file', 'waiting_modification_request']:
        show_main_menu(message)

def start_keep_alive():
    keep_alive_thread = threading.Thread(target=keep_alive, daemon=True)
    keep_alive_thread.start()
    print("🔄 Keep-alive запущен (запросы каждые 4 минуты)")

if __name__ == "__main__":
    start_keep_alive()
    bot.remove_webhook()
    
    port = int(os.environ.get('PORT', 10000))
    print(f"🚀 Bot starting on port {port}")
    print("🔄 Keep-alive активен - бот не будет выключаться")
    
    try:
        WEBHOOK_URL = "https://one2-1-04er.onrender.com/webhook"
        bot.set_webhook(url=WEBHOOK_URL)
        print(f"✅ Webhook установлен: {WEBHOOK_URL}")
        app.run(host='0.0.0.0', port=port, debug=False)
    except Exception as e:
        print(f"🔄 Используем поллинг... Ошибка: {e}")
        bot.infinity_polling()
