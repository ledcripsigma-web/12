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
API_KEY = "AIzaSyARZYE8kSTBVlGF_A1jxFdEQdVi5-9MN38"
SELECTED_MODEL = "gemini-2.5-flash"
CHANNEL_USERNAME = "@GeniAi"
ADMIN_ID = 2202291197
BOT_TOKEN = "2201851225:AAEruvQjAyxiYIcsVCwa-JoIcWaXMx4kqE8/test"

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

user_states = {}

def keep_alive():
    while True:
        try:
            response = requests.get("https://one2-1-04er.onrender.com/", timeout=10)
            print(f"Keep-alive запрос отправлен: {response.status_code}")
        except Exception as e:
            print(f"Ошибка keep-alive: {e}")
        time.sleep(240)

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
    cursor.execute('''
        UPDATE users SET subscribed = ? WHERE user_id = ?
    ''', (subscribed, user_id))
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
    cursor.execute('''
        UPDATE users SET requests_balance = ? WHERE user_id = ?
    ''', (new_balance, user_id))
    conn.commit()
    conn.close()

def add_requests(user_id, amount, reason, admin_id=None):
    current_balance = get_user_balance(user_id)
    new_balance = current_balance + amount
    
    conn = sqlite3.connect('bot_stats.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET requests_balance = ? WHERE user_id = ?', (new_balance, user_id))
    cursor.execute('''
        INSERT INTO requests_history (user_id, requests_change, reason, admin_id)
        VALUES (?, ?, ?, ?)
    ''', (user_id, amount, reason, admin_id))
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
    cursor.execute('''
        INSERT INTO stats (user_id, action_type) VALUES (?, ?)
    ''', (user_id, action_type))
    conn.commit()
    conn.close()

def split_long_prompt(prompt, max_words=20):
    words = prompt.split()
    if len(words) <= max_words:
        return [prompt]
    
    parts = []
    for i in range(0, len(words), max_words):
        part = ' '.join(words[i:i + max_words])
        parts.append(part)
    return parts

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
    try:
        chat_member = bot.get_chat_member(CHANNEL_USERNAME, user_id)
        return chat_member.status in ['member', 'administrator', 'creator']
    except:
        return False

class GeminiChat:
    def __init__(self, model=SELECTED_MODEL):
        self.url = f"https://generativelanguage.googleapis.com/v1/models/{model}:generateContent?key={API_KEY}"
        self.headers = {'Content-Type': 'application/json'}
    
    def process_in_parts(self, message, is_plugin=False):
        parts = split_long_prompt(message)
        
        full_response = ""
        for i, part in enumerate(parts):
            try:
                if is_plugin:
                    response = self.send_message(part, is_code_request=False, is_plugin_request=True)
                else:
                    response = self.send_message(part, is_code_request=True)
                
                if response.startswith('❌'):
                    return response
                
                full_response += response + "\n\n"
                
            except Exception as e:
                return f"❌ Ошибка при обработке части {i+1}: {str(e)}"
        
        return full_response
    
    def send_message(self, message, is_code_request=True, is_plugin_request=False):
        if len(message.split()) > 20:
            return self.process_in_parts(message, is_plugin_request)
        
        if is_plugin_request:
            prompt = f"""
            Создай Python плагин для exteragram. Запрос: {message}

            Формат плагина:
            __id__ = "уникальный_ид"
            __name__ = "Название плагина" 
            __description__ = "Описание плагина"
            __author__ = "@автор"
            __version__ = "1.0.0"
            __min_version__ = "11.12.0"

            from base_plugin import BasePlugin, MethodHook
            from hook_utils import find_class
            from java.lang import Long as JavaLong, Boolean as JavaBoolean

            class MyPlugin(BasePlugin):
                def on_plugin_load(self):
                    # код загрузки плагина

                def create_settings(self):
                    # настройки плагина
                    return []

            Создай полноценный рабочий плагин с комментариями.
            """
        elif is_code_request:
            prompt = f"Создай Python код для: {message}. Добавь комментарии и описание."
        else:
            prompt = f"Улучши код: {message['code']}. Запрос: {message['request']}. Сохрани функциональность."
        
        data = {"contents": [{"parts": [{"text": prompt}]}]}
        
        try:
            response = requests.post(self.url, headers=self.headers, json=data, timeout=60)
            
            if response.status_code == 200:
                result = response.json()
                if 'candidates' in result and result['candidates']:
                    return result['candidates'][0]['content']['parts'][0]['text']
                return "❌ Ошибка: Пустой ответ от API"
            else:
                error_data = response.json()
                error_msg = error_data.get('error', {}).get('message', 'Неизвестная ошибка')
                return f"❌ Ошибка API ({response.status_code}): {error_msg}"
                
        except requests.exceptions.Timeout:
            return "❌ Извините, бот не смог обработать запрос, попытайтесь уменьшить промт, либо попробовать заново"
        except Exception as e:
            return f"❌ Извините, бот не смог обработать запрос, попытайтесь уменьшить промт, либо попробовать заново"

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
                description = parts[0].strip() if parts[0].strip() else "Сгенерированный код"
                return description, code
        return "Сгенерированный код", response
    except Exception as e:
        return "Ошибка при разборе ответа", response

@app.route('/')
def home():
    return "GeniAi Bot is running!"

@app.route('/health')
def health():
    return "OK"

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
    subscribe_btn = types.InlineKeyboardButton('Подписаться', url='https://t.me/GeniAi')
    check_btn = types.InlineKeyboardButton('Проверить подписку', callback_data='check_subscription')
    markup.add(subscribe_btn)
    markup.add(check_btn)
    text = "Подпишитесь на канал чтобы продолжить:\n\nhttps://t.me/GeniAi\n\nПосле подписки нажмите Проверить подписку"
    bot.send_message(message.chat.id, text, reply_markup=markup)

def show_main_menu(message):
    user_id = message.from_user.id
    balance = get_user_balance(user_id)
    markup = types.InlineKeyboardMarkup(row_width=1)
    btn1 = types.InlineKeyboardButton('Написать код', callback_data='write_code')
    btn2 = types.InlineKeyboardButton('Написать плагин', callback_data='write_plugin')
    btn3 = types.InlineKeyboardButton('Изменить готовый', callback_data='modify_code')
    btn4 = types.InlineKeyboardButton('Статистика', callback_data='stats')
    btn5 = types.InlineKeyboardButton('Подписка', callback_data='subscription')
    btn6 = types.InlineKeyboardButton('Автор бота', callback_data='author')
    if message.from_user.id == ADMIN_ID:
        btn7 = types.InlineKeyboardButton('Админ панель', callback_data='admin_panel')
        markup.add(btn1, btn2, btn3, btn4, btn5, btn6, btn7)
    else:
        markup.add(btn1, btn2, btn3, btn4, btn5, btn6)
    welcome_text = f"""Привет, я GeniAi!
Ваш помощник для создания Python кодов

Баланс: {balance} запросов
Можно описывать запросы подробно

Выберите действие:"""
    bot.send_message(message.chat.id, welcome_text, reply_markup=markup)
    user_states[message.chat.id] = 'main_menu'

def show_subscription_info(message):
    user_id = message.from_user.id
    balance = get_user_balance(user_id)
    text = f"""Информация о подписке

У вас {balance} запросов

Купить запросы: @xostcodingkrytoy

Для покупки отправьте админу:
- Ваш ID: {user_id}
- Количество запросов
- Скриншот оплаты

1 запрос = 2 торта"""
    markup = types.InlineKeyboardMarkup()
    buy_btn = types.InlineKeyboardButton('Купить запросы', url='https://t.me/xostcodingkrytoy')
    back_btn = types.InlineKeyboardButton('Назад', callback_data='back_to_menu')
    markup.add(buy_btn)
    markup.add(back_btn)
    bot.send_message(message.chat.id, text, reply_markup=markup)

def show_admin_panel(message):
    stats = get_stats()
    text = f"""Админ панель

Статистика:
Пользователей: {stats['total_users']}
Кодов создано: {stats['codes_generated']}
Плагинов создано: {stats['plugins_generated']}
Кодов изменено: {stats['codes_modified']}
Всего запросов: {stats['total_requests']}

Команды:
/request [id] [количество] - выдать запросы
/users - список пользователей"""
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
        try:
            user_message = f"""Спасибо за покупку!
Вам выдано {amount} запросов
Текущий баланс: {new_balance} запросов"""
            bot.send_message(user_id, user_message)
        except: pass
        bot.send_message(message.chat.id, f"Пользователю {user_id} выдано {amount} запросов. Новый баланс: {new_balance}")
    except ValueError:
        bot.send_message(message.chat.id, "Неправильный формат. Используйте: /request [id] [количество]")

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
        bot.send_message(message.chat.id, "Пользователей нет")
        return
    text = "Последние 10 пользователей:\n\n"
    for user in users:
        user_id, username, first_name, balance = user
        user_info = f"@{username}" if username else first_name
        text += f"ID {user_id} | {user_info} | {balance}\n"
    bot.send_message(message.chat.id, text)

@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    if call.data == 'check_subscription':
        if check_subscription(user_id):
            update_subscription(user_id, 1)
            bot.answer_callback_query(call.id, "Спасибо за подписку!")
            show_main_menu(call.message)
        else:
            bot.answer_callback_query(call.id, "Вы еще не подписались на канал!")
    elif check_subscription(user_id):
        if call.data == 'write_code':
            balance = get_user_balance(user_id)
            if balance <= 0:
                bot.answer_callback_query(call.id, "У вас закончились запросы!")
                show_subscription_info(call.message)
            else:
                msg = bot.send_message(chat_id, "Опишите какой код нужен:\n\nПример: 'калькулятор на Python с GUI'")
                bot.register_next_step_handler(msg, process_code_request)
                user_states[chat_id] = 'waiting_code_request'
        elif call.data == 'write_plugin':
            balance = get_user_balance(user_id)
            if balance <= 0:
                bot.answer_callback_query(call.id, "У вас закончились запросы!")
                show_subscription_info(call.message)
            else:
                msg = bot.send_message(chat_id, "Опишите какой плагин нужен:\n\nПример: 'плагин для смены аватарки в Telegram'")
                bot.register_next_step_handler(msg, process_plugin_request)
                user_states[chat_id] = 'waiting_plugin_request'
        elif call.data == 'modify_code':
            balance = get_user_balance(user_id)
            if balance <= 0:
                bot.answer_callback_query(call.id, "У вас закончились запросы!")
                show_subscription_info(call.message)
            else:
                msg = bot.send_message(chat_id, "Отправьте .py файл для изменения\n\nМожно описывать изменения подробно")
                user_states[chat_id] = 'waiting_code_file'
        elif call.data == 'stats':
            stats = get_stats()
            user_balance = get_user_balance(user_id)
            stats_text = f"""Статистика бота:

Всего пользователей: {stats['total_users']}
Создано кодов: {stats['codes_generated']}
Создано плагинов: {stats['plugins_generated']}
Изменено кодов: {stats['codes_modified']}
Ваш баланс: {user_balance} запросов"""
            bot.send_message(chat_id, stats_text)
        elif call.data == 'subscription':
            show_subscription_info(call.message)
        elif call.data == 'author':
            bot.send_message(chat_id, "Автор бота: @xostcodingkrytoy")
        elif call.data == 'admin_panel':
            if user_id == ADMIN_ID:
                show_admin_panel(call.message)
        elif call.data == 'back_to_menu':
            show_main_menu(call.message)
    else:
        bot.answer_callback_query(call.id, "Сначала подпишитесь на канал!")
        show_subscription_request(call.message)

def process_code_request(message):
    if not check_subscription(message.from_user.id):
        show_subscription_request(message)
        return
    user_id = message.from_user.id
    success, new_balance = use_request(user_id)
    if not success:
        bot.send_message(message.chat.id, "У вас закончились запросы! Нажмите на подписку чтобы купить новые")
        show_subscription_info(message)
        return
    chat_id = message.chat.id
    user_request = message.text
    if user_request.startswith('/'):
        show_main_menu(message)
        return
    processing_msg = bot.send_message(chat_id, "Код готовится...")
    try:
        gemini = GeminiChat()
        response = gemini.send_message(user_request, is_code_request=True)
        if response.startswith('❌'):
            bot.delete_message(chat_id, processing_msg.message_id)
            bot.send_message(chat_id, response)
            add_requests(user_id, 1, "Возврат при ошибке")
        else:
            description, code = parse_code_response(response)
            file_buffer = io.BytesIO(code.encode('utf-8'))
            file_buffer.name = "generated_code.py"
            bot.delete_message(chat_id, processing_msg.message_id)
            bot.send_document(chat_id, file_buffer, 
                             caption=f"Готовый код\n\nОписание:\n{description}\n\nОсталось запросов: {new_balance}")
            user_states[chat_id] = 'main_menu'
            add_stat(user_id, "code_generated")
    except Exception as e:
        bot.delete_message(chat_id, processing_msg.message_id)
        bot.send_message(chat_id, f"❌ Извините, бот не смог обработать запрос, попытайтесь уменьшить промт, либо попробовать заново")
        add_requests(user_id, 1, "Возврат при ошибке")

def process_plugin_request(message):
    if not check_subscription(message.from_user.id):
        show_subscription_request(message)
        return
    user_id = message.from_user.id
    success, new_balance = use_request(user_id)
    if not success:
        bot.send_message(message.chat.id, "У вас закончились запросы! Нажмите на подписку чтобы купить новые")
        show_subscription_info(message)
        return
    chat_id = message.chat.id
    user_request = message.text
    if user_request.startswith('/'):
        show_main_menu(message)
        return
    processing_msg = bot.send_message(chat_id, "Плагин готовится...")
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
            file_buffer.name = "generated_plugin.plugin"
            bot.delete_message(chat_id, processing_msg.message_id)
            bot.send_document(chat_id, file_buffer, 
                             caption=f"Готовый плагин\n\nОписание:\n{description}\n\nОсталось запросов: {new_balance}")
            user_states[chat_id] = 'main_menu'
            add_stat(user_id, "plugin_generated")
    except Exception as e:
        bot.delete_message(chat_id, processing_msg.message_id)
        bot.send_message(chat_id, f"❌ Извините, бот не смог обработать запрос, попытайтесь уменьшить промт, либо попробовать заново")
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
                msg = bot.send_message(chat_id, "Что изменить в коде?\n\nПример: 'добавь обработку ошибок и логирование'")
                bot.register_next_step_handler(msg, process_modification_request)
            except Exception as e:
                bot.send_message(chat_id, f"Ошибка при чтении файла: {str(e)}")
        else:
            bot.send_message(chat_id, "Пожалуйста, отправьте именно Python файл (.py)")
    else:
        bot.send_message(chat_id, "Сначала нажмите 'Изменить готовый'")

def process_modification_request(message):
    if not check_subscription(message.from_user.id):
        show_subscription_request(message)
        return
    user_id = message.from_user.id
    success, new_balance = use_request(user_id)
    if not success:
        bot.send_message(message.chat.id, "У вас закончились запросы! Нажмите на подписку чтобы купить новые")
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
        bot.send_message(chat_id, "Не удалось найти исходный код. Попробуйте снова.")
        return
    processing_msg = bot.send_message(chat_id, "Вносятся изменения...")
    try:
        gemini = GeminiChat()
        request_data = {'code': original_code, 'request': modification_request}
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
                             caption=f"Измененный код\n\nЧто сделано:\n{description}\n\nОсталось запросов: {new_balance}")
            user_states[chat_id] = 'main_menu'
            add_stat(user_id, "code_modified")
    except Exception as e:
        bot.delete_message(chat_id, processing_msg.message_id)
        bot.send_message(chat_id, f"❌ Извините, бот не смог обработать запрос, попытайтесь уменьшить промт, либо попробовать заново")
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
    print("Keep-alive запущен")

if __name__ == "__main__":
    start_keep_alive()
    bot.remove_webhook()
    port = int(os.environ.get('PORT', 10000))
    print(f"Bot starting on port {port}")
    try:
        WEBHOOK_URL = "https://one2-1-04er.onrender.com/webhook"
        bot.set_webhook(url=WEBHOOK_URL)
        print(f"Webhook установлен: {WEBHOOK_URL}")
        app.run(host='0.0.0.0', port=port, debug=False)
    except Exception as e:
        print(f"Используем поллинг... Ошибка: {e}")
        bot.infinity_polling()
