import requests
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters
import io
import os
from flask import Flask, request

# Конфигурация
API_KEY = "AIzaSyARZYE8kSTBVlGF_A1jxFdEQdVi5-9MN38"
BOT_TOKEN = "2201149182:AAG5kZQcl8AqMgbqqCGu4eiyik8AIFQA03Q/test"
SELECTED_MODEL = "gemini-2.5-flash"

user_states = {}
app = Flask(__name__)

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
                description = parts[0].strip() if parts[0].strip() else "📝 Сгенерированный Python код"
                return description, code
        
        return "📝 Сгенерированный Python код", response
        
    except Exception as e:
        return f"❌ Ошибка при разборе ответа", response

# Инициализация приложения
application = Application.builder().token(BOT_TOKEN).build()

@app.route('/')
def home():
    return "🤖 GeniAi Bot is running!"

@app.route('/webhook', methods=['POST'])
def webhook():
    """Обработчик веб-хука от Telegram"""
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = Update.de_json(json.loads(json_string), application.bot)
        application.update_queue.put(update)
        return 'OK'
    return 'Error'

def start(update: Update, context):
    keyboard = [
        [InlineKeyboardButton("📝 Написать код", callback_data="write_code")],
        [InlineKeyboardButton("🔧 Изменить готовый", callback_data="modify_code")],
        [InlineKeyboardButton("👨‍💻 Автор бота", callback_data="author")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    welcome_text = f"""🤖 Привет, я GeniAi!
Ваш помощник для создания Python кодов
✨ Используется модель: {SELECTED_MODEL}

Просто выберите, с чего начнём:"""
    
    update.message.reply_text(welcome_text, reply_markup=reply_markup)
    user_states[update.effective_chat.id] = 'main_menu'

def button_handler(update: Update, context):
    query = update.callback_query
    query.answer()
    chat_id = query.message.chat_id
    
    if query.data == 'write_code':
        query.edit_message_text("💡 Опишите, какой код вам нужен:")
        user_states[chat_id] = 'waiting_code_request'
        
    elif query.data == 'modify_code':
        query.edit_message_text("📎 Отправьте ваш .py файл, который нужно изменить")
        user_states[chat_id] = 'waiting_code_file'
        
    elif query.data == 'author':
        query.edit_message_text("👨‍💻 Автор бота: @xostcodingkrytoy")

def handle_message(update: Update, context):
    chat_id = update.effective_chat.id
    user_text = update.message.text
    
    if user_states.get(chat_id) == 'waiting_code_request':
        process_code_request(update, context, user_text)
    elif user_states.get(chat_id, {}).get('state') == 'waiting_modification_request':
        process_modification_request(update, context, user_text)
    else:
        keyboard = [
            [InlineKeyboardButton("📝 Написать код", callback_data="write_code")],
            [InlineKeyboardButton("🔧 Изменить готовый", callback_data="modify_code")],
            [InlineKeyboardButton("👨‍💻 Автор бота", callback_data="author")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        update.message.reply_text("🤖 Выберите действие:", reply_markup=reply_markup)

def process_code_request(update: Update, context, user_request: str):
    chat_id = update.effective_chat.id
    
    if user_request.startswith('/'):
        start(update, context)
        return
    
    processing_msg = update.message.reply_text("⚙️ Код готовится... Это может занять несколько секунд")
    
    try:
        gemini = GeminiChat()
        response = gemini.send_message(user_request, is_code_request=True)
        
        if response.startswith('❌'):
            context.bot.delete_message(chat_id, processing_msg.message_id)
            update.message.reply_text(response)
        else:
            description, code = parse_code_response(response)
            
            file_buffer = io.BytesIO(code.encode('utf-8'))
            file_buffer.name = "generated_code.py"
            
            context.bot.delete_message(chat_id, processing_msg.message_id)
            update.message.reply_document(
                document=InputFile(file_buffer, filename="generated_code.py"),
                caption=f"📁 Готовый код\n\n📝 Описание:\n{description}\n\n✅ Файл готов к использованию!"
            )
            user_states[chat_id] = 'main_menu'
        
    except Exception as e:
        context.bot.delete_message(chat_id, processing_msg.message_id)
        update.message.reply_text(f"❌ Произошла ошибка при генерации кода: {str(e)}")

def handle_document(update: Update, context):
    chat_id = update.effective_chat.id
    
    if user_states.get(chat_id) == 'waiting_code_file':
        document = update.message.document
        if document.file_name and document.file_name.endswith('.py'):
            try:
                file = context.bot.get_file(document.file_id)
                file_content = file.download_as_bytearray()
                code_content = file_content.decode('utf-8')
                
                user_states[chat_id] = {'state': 'waiting_modification_request', 'code': code_content}
                update.message.reply_text("✏️ Что вы хотите изменить в коде?")
                
            except Exception as e:
                update.message.reply_text(f"❌ Ошибка при чтении файла: {str(e)}")
        else:
            update.message.reply_text("❌ Пожалуйста, отправьте именно Python файл (.py)")
    else:
        update.message.reply_text("❌ Сначала нажмите 'Изменить готовый'")

def process_modification_request(update: Update, context, modification_request: str):
    chat_id = update.effective_chat.id
    
    if modification_request.startswith('/'):
        start(update, context)
        return
    
    user_data = user_states.get(chat_id, {})
    original_code = user_data.get('code', '')
    
    if not original_code:
        update.message.reply_text("❌ Не удалось найти исходный код. Попробуйте снова.")
        return
    
    processing_msg = update.message.reply_text("⚙️ Вносятся изменения в код...")
    
    try:
        gemini = GeminiChat()
        request_data = {
            'code': original_code,
            'request': modification_request
        }
        response = gemini.send_message(request_data, is_code_request=False)
        
        if response.startswith('❌'):
            context.bot.delete_message(chat_id, processing_msg.message_id)
            update.message.reply_text(response)
        else:
            description, modified_code = parse_code_response(response)
            
            file_buffer = io.BytesIO(modified_code.encode('utf-8'))
            file_buffer.name = "modified_code.py"
            
            context.bot.delete_message(chat_id, processing_msg.message_id)
            update.message.reply_document(
                document=InputFile(file_buffer, filename="modified_code.py"),
                caption=f"📁 Измененный код\n\n📝 Что было сделано:\n{description}\n\n✅ Файл готов к использованию!"
            )
            
            user_states[chat_id] = 'main_menu'
        
    except Exception as e:
        context.bot.delete_message(chat_id, processing_msg.message_id)
        update.message.reply_text(f"❌ Произошла ошибка при изменении кода: {str(e)}")

# Добавляем обработчики
application.add_handler(CommandHandler("start", start))
application.add_handler(CallbackQueryHandler(button_handler))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
application.add_handler(MessageHandler(filters.Document.ALL, handle_document))

if __name__ == "__main__":
    # Устанавливаем веб-хук
    WEBHOOK_URL = "https://one2-1-04er.onrender.com/webhook"
    application.bot.set_webhook(WEBHOOK_URL)
    print(f"✅ Webhook установлен: {WEBHOOK_URL}")
    
    # Запускаем сервер
    port = int(os.environ.get('PORT', 10000))
    print(f"🚀 Bot starting on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False)
