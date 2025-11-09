import requests
import json
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters
import io
import os
import threading
import time

# Конфигурация
API_KEY = "AIzaSyARZYE8kSTBVlGF_A1jxFdEQdVi5-9MN38"
BOT_TOKEN = "2201149182:AAG5kZQcl8AqMgbqqCGu4eiyik8AIFQA03Q"

# Используем правильную модель
SELECTED_MODEL = "gemini-2.5-flash"

# Хранилище состояний пользователей
user_states = {}

# Keep-alive функция
def keep_alive():
    """Функция для поддержания бота активным"""
    while True:
        try:
            # Отправляем запрос к самому себе
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/getMe"
            response = requests.get(url, timeout=10)
            print(f"✅ Keep-alive запрос отправлен: {response.status_code}")
        except Exception as e:
            print(f"❌ Ошибка keep-alive: {e}")
        
        # Ждем 4 минуты (240 секунд)
        time.sleep(240)

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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    
    await update.message.reply_text(welcome_text, reply_markup=reply_markup)
    user_states[update.effective_chat.id] = 'main_menu'

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id
    
    if query.data == 'write_code':
        await query.edit_message_text("💡 Опишите, какой код вам нужен:")
        user_states[chat_id] = 'waiting_code_request'
        
    elif query.data == 'modify_code':
        await query.edit_message_text("📎 Отправьте ваш .py файл, который нужно изменить")
        user_states[chat_id] = 'waiting_code_file'
        
    elif query.data == 'author':
        await query.edit_message_text("👨‍💻 Автор бота: @xostcodingkrytoy")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_text = update.message.text
    
    if user_states.get(chat_id) == 'waiting_code_request':
        await process_code_request(update, context, user_text)
    elif user_states.get(chat_id, {}).get('state') == 'waiting_modification_request':
        await process_modification_request(update, context, user_text)
    else:
        # Показываем меню
        keyboard = [
            [InlineKeyboardButton("📝 Написать код", callback_data="write_code")],
            [InlineKeyboardButton("🔧 Изменить готовый", callback_data="modify_code")],
            [InlineKeyboardButton("👨‍💻 Автор бота", callback_data="author")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("🤖 Выберите действие:", reply_markup=reply_markup)

async def process_code_request(update: Update, context: ContextTypes.DEFAULT_TYPE, user_request: str):
    chat_id = update.effective_chat.id
    
    if user_request.startswith('/'):
        await start(update, context)
        return
    
    processing_msg = await update.message.reply_text("⚙️ Код готовится... Это может занять несколько секунд")
    
    try:
        gemini = GeminiChat()
        response = gemini.send_message(user_request, is_code_request=True)
        
        if response.startswith('❌'):
            await context.bot.delete_message(chat_id, processing_msg.message_id)
            await update.message.reply_text(response)
        else:
            description, code = parse_code_response(response)
            
            file_buffer = io.BytesIO(code.encode('utf-8'))
            file_buffer.name = "generated_code.py"
            
            await context.bot.delete_message(chat_id, processing_msg.message_id)
            await update.message.reply_document(
                document=InputFile(file_buffer, filename="generated_code.py"),
                caption=f"📁 Готовый код\n\n📝 Описание:\n{description}\n\n✅ Файл готов к использованию!"
            )
            user_states[chat_id] = 'main_menu'
        
    except Exception as e:
        await context.bot.delete_message(chat_id, processing_msg.message_id)
        await update.message.reply_text(f"❌ Произошла ошибка при генерации кода: {str(e)}")

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    
    if user_states.get(chat_id) == 'waiting_code_file':
        document = update.message.document
        if document.file_name.endswith('.py'):
            try:
                file = await context.bot.get_file(document.file_id)
                file_content = await file.download_as_bytearray()
                code_content = file_content.decode('utf-8')
                
                user_states[chat_id] = {'state': 'waiting_modification_request', 'code': code_content}
                await update.message.reply_text("✏️ Что вы хотите изменить в коде?")
                
            except Exception as e:
                await update.message.reply_text(f"❌ Ошибка при чтении файла: {str(e)}")
        else:
            await update.message.reply_text("❌ Пожалуйста, отправьте именно Python файл (.py)")
    else:
        await update.message.reply_text("❌ Сначала нажмите 'Изменить готовый'")

async def process_modification_request(update: Update, context: ContextTypes.DEFAULT_TYPE, modification_request: str):
    chat_id = update.effective_chat.id
    
    if modification_request.startswith('/'):
        await start(update, context)
        return
    
    user_data = user_states.get(chat_id, {})
    original_code = user_data.get('code', '')
    
    if not original_code:
        await update.message.reply_text("❌ Не удалось найти исходный код. Попробуйте снова.")
        return
    
    processing_msg = await update.message.reply_text("⚙️ Вносятся изменения в код...")
    
    try:
        gemini = GeminiChat()
        request_data = {
            'code': original_code,
            'request': modification_request
        }
        response = gemini.send_message(request_data, is_code_request=False)
        
        if response.startswith('❌'):
            await context.bot.delete_message(chat_id, processing_msg.message_id)
            await update.message.reply_text(response)
        else:
            description, modified_code = parse_code_response(response)
            
            file_buffer = io.BytesIO(modified_code.encode('utf-8'))
            file_buffer.name = "modified_code.py"
            
            await context.bot.delete_message(chat_id, processing_msg.message_id)
            await update.message.reply_document(
                document=InputFile(file_buffer, filename="modified_code.py"),
                caption=f"📁 Измененный код\n\n📝 Что было сделано:\n{description}\n\n✅ Файл готов к использованию!"
            )
            
            user_states[chat_id] = 'main_menu'
        
    except Exception as e:
        await context.bot.delete_message(chat_id, processing_msg.message_id)
        await update.message.reply_text(f"❌ Произошла ошибка при изменении кода: {str(e)}")

def start_keep_alive():
    """Запускает keep-alive в отдельном потоке"""
    keep_alive_thread = threading.Thread(target=keep_alive, daemon=True)
    keep_alive_thread.start()
    print("🔄 Keep-alive запущен (запросы каждые 4 минуты)")

def main():
    # Запускаем keep-alive
    start_keep_alive()
    
    # Создаем приложение
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Добавляем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    
    print(f"🤖 Бот запущен... Используется модель: {SELECTED_MODEL}")
    print("🔗 Бот работает на хостинге за пределами РФ")
    print("🔄 Keep-alive активен - бот не будет выключаться")
    
    # Запускаем бота
    application.run_polling()

if __name__ == "__main__":
    main()
