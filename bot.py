import requests
import json
import telebot
from telebot import types
import io
import os

# Конфигурация
API_KEY = "AIzaSyARZYE8kSTBVlGF_A1jxFdEQdVi5-9MN38"
BOT_TOKEN = "2201149182:AAG5kZQcl8AqMgbqqCGu4eiyik8AIFQA03Q/test"

# Настройка прокси для Telegram
PROXY = {
    'https': 'https://138.68.161.14:3128',  # Рабочий прокси сервер
}

# Создаем бота с прокси
bot = telebot.TeleBot(BOT_TOKEN)

# Используем правильную модель
SELECTED_MODEL = "gemini-2.5-flash"

class GeminiChat:
    def __init__(self, model=SELECTED_MODEL):
        self.url = f"https://generativelanguage.googleapis.com/v1/models/{model}:generateContent?key={API_KEY}"
        self.headers = {'Content-Type': 'application/json'}
    
    def send_message(self, message, is_code_request=True):
        if is_code_request:
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

            Если запрос не связан с программированием, всё равно создай соответствующий Python код.
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
            # Для Gemini API не используем прокси (он доступен в России)
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
        # Пробуем разные форматы ответа
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
                description = parts[0].strip() if parts[0].strip() else "📝 Сгенерированный Python код"
                return description, code
        
        # Если не нашли структурированный ответ, возвращаем весь текст как код
        return "📝 Сгенерированный Python код", response
        
    except Exception as e:
        return f"❌ Ошибка при разборе ответа", response

user_states = {}

@bot.message_handler(commands=['start'])
def send_welcome(message):
    markup = types.InlineKeyboardMarkup(row_width=1)
    btn1 = types.InlineKeyboardButton('📝 Написать код', callback_data='write_code')
    btn2 = types.InlineKeyboardButton('🔧 Изменить готовый', callback_data='modify_code')
    btn3 = types.InlineKeyboardButton('👨‍💻 Автор бота', callback_data='author')
    markup.add(btn1, btn2, btn3)
    
    welcome_text = f"""🤖 Привет, я GeniAi!
Ваш помощник для создания Python кодов
✨ Используется модель: {SELECTED_MODEL}

Просто выберите, с чего начнём:"""
    
    bot.send_message(message.chat.id, welcome_text, reply_markup=markup)
    user_states[message.chat.id] = 'main_menu'

@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    chat_id = call.message.chat.id
    
    if call.data == 'write_code':
        msg = bot.send_message(chat_id, "💡 Опишите, какой код вам нужен:")
        bot.register_next_step_handler(msg, process_code_request)
        user_states[chat_id] = 'waiting_code_request'
        
    elif call.data == 'modify_code':
        msg = bot.send_message(chat_id, "📎 Отправьте ваш .py файл, который нужно изменить")
        user_states[chat_id] = 'waiting_code_file'
        
    elif call.data == 'author':
        bot.send_message(chat_id, "👨‍💻 Автор бота: @xostcodingkrytoy")

def process_code_request(message):
    chat_id = message.chat.id
    user_request = message.text
    
    if user_request.startswith('/'):
        send_welcome(message)
        return
    
    processing_msg = bot.send_message(chat_id, "⚙️ Код готовится... Это может занять несколько секунд")
    
    try:
        gemini = GeminiChat()
        response = gemini.send_message(user_request, is_code_request=True)
        
        if response.startswith('❌'):
            bot.delete_message(chat_id, processing_msg.message_id)
            bot.send_message(chat_id, response)
        else:
            description, code = parse_code_response(response)
            
            file_buffer = io.BytesIO(code.encode('utf-8'))
            file_buffer.name = f"generated_code.py"
            
            bot.delete_message(chat_id, processing_msg.message_id)
            bot.send_document(chat_id, file_buffer, 
                             caption=f"📁 Готовый код\n\n📝 Описание:\n{description}\n\n✅ Файл готов к использованию!")
        
    except Exception as e:
        bot.delete_message(chat_id, processing_msg.message_id)
        bot.send_message(chat_id, f"❌ Произошла ошибка при генерации кода: {str(e)}")

@bot.message_handler(content_types=['document'])
def handle_document(message):
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
    chat_id = message.chat.id
    modification_request = message.text
    
    if modification_request.startswith('/'):
        send_welcome(message)
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
        else:
            description, modified_code = parse_code_response(response)
            
            file_buffer = io.BytesIO(modified_code.encode('utf-8'))
            file_buffer.name = f"modified_code.py"
            
            bot.delete_message(chat_id, processing_msg.message_id)
            bot.send_document(chat_id, file_buffer,
                             caption=f"📁 Измененный код\n\n📝 Что было сделано:\n{description}\n\n✅ Файл готов к использованию!")
            
            user_states[chat_id] = 'main_menu'
        
    except Exception as e:
        bot.delete_message(chat_id, processing_msg.message_id)
        bot.send_message(chat_id, f"❌ Произошла ошибка при изменении кода: {str(e)}")

@bot.message_handler(func=lambda message: True)
def handle_other_messages(message):
    chat_id = message.chat.id
    
    if user_states.get(chat_id) not in ['waiting_code_request', 'waiting_code_file', 'waiting_modification_request']:
        markup = types.InlineKeyboardMarkup(row_width=1)
        btn1 = types.InlineKeyboardButton('📝 Написать код', callback_data='write_code')
        btn2 = types.InlineKeyboardButton('🔧 Изменить готовый', callback_data='modify_code')
        btn3 = types.InlineKeyboardButton('👨‍💻 Автор бота', callback_data='author')
        markup.add(btn1, btn2, btn3)
        
        bot.send_message(chat_id, "🤖 Выберите действие:", reply_markup=markup)

if __name__ == "__main__":
    print(f"🤖 Бот запущен... Используется модель: {SELECTED_MODEL}")
    
    # Пробуем разные способы обхода блокировки
    try:
        # Способ 1: Обычный запуск
        bot.infinity_polling()
    except Exception as e:
        print(f"❌ Ошибка подключения: {e}")
        print("🔄 Пробуем использовать прокси...")
        
        # Способ 2: С прокси
        try:
            from telebot import apihelper
            # Устанавливаем прокси для Telegram API
            apihelper.proxy = PROXY
            bot.infinity_polling()
        except Exception as e2:
            print(f"❌ Ошибка с прокси: {e2}")
            print("💡 Рекомендации:")
            print("1. Используйте VPN")
            print("2. Или запустите бота на хостинге за пределами РФ")
            print("3. Или используйте Telegram Web версию")
