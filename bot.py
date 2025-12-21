import os
import sqlite3
import zipfile
import subprocess
import shutil
import requests
import threading
import time
import logging
from datetime import datetime
from collections import defaultdict
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ========== НАСТРОЙКИ ==========
TOKEN = "2202599086:AAH6oYmkqHVOiN5ieQwh0moaewQzMzkOMcI/test"
ADMIN_ID = 2202291197
CHANNEL_USERNAME = "@SourceCode"
MAX_SIZE = 15 * 1024 * 1024
PING_URL = "https://one2-2-b7o0.onrender.com"
PING_INTERVAL = 240

# ========== АНТИ-ФЛУД СИСТЕМА (ВАШ ВАРИАНТ) ==========
FLOOD_SETTINGS = {
    'MAX_MESSAGES': 5,  # 5 сообщений
    'TIME_WINDOW': 5,   # за 5 секунд
    'BAN_DURATION': 999999999  # перманентный бан (очень большое число)
}

user_messages = defaultdict(list)
banned_users = {}

def is_flooding(user_id):
    """Проверяет флуд и банит если нужно"""
    current_time = time.time()
    
    # Проверяем не забанен ли уже
    if user_id in banned_users:
        if current_time < banned_users[user_id]:
            return True
        else:
            del banned_users[user_id]
            del user_messages[user_id]
    
    # Добавляем текущее сообщение
    user_messages[user_id].append(current_time)
    
    # Очищаем старые сообщения
    user_messages[user_id] = [t for t in user_messages[user_id] 
                              if current_time - t <= FLOOD_SETTINGS['TIME_WINDOW']]
    
    # Если превышен лимит - бан
    if len(user_messages[user_id]) > FLOOD_SETTINGS['MAX_MESSAGES']:
        banned_users[user_id] = current_time + FLOOD_SETTINGS['BAN_DURATION']
        print(f"🚫 Пользователь {user_id} забанен за флуд")
        return True
    
    return False

def anti_flood(func):
    """Декоратор для защиты от флуда"""
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        # Получаем user_id
        if update.message:
            user_id = update.message.from_user.id
        elif update.callback_query:
            user_id = update.callback_query.from_user.id
        else:
            return
        
        # Пропускаем админа
        if user_id == ADMIN_ID:
            await func(update, context)
            return
        
        # Проверяем флуд
        if is_flooding(user_id):
            return  # Просто игнорируем, ничего не делаем
        
        # Выполняем функцию
        await func(update, context)
    
    return wrapper

# ========== АВТО-ПИНГ ==========
def auto_ping_background():
    print(f"🚀 Авто-пинг запущен для {PING_URL}")
    while True:
        try:
            response = requests.get(PING_URL, timeout=10)
            print(f"✅ [{datetime.now().strftime('%H:%M:%S')}] Пинг. Статус: {response.status_code}")
        except Exception as e:
            print(f"❌ [{datetime.now().strftime('%H:%M:%S')}] Ошибка: {e}")
        time.sleep(PING_INTERVAL)

ping_thread = threading.Thread(target=auto_ping_background, daemon=True)
ping_thread.start()

# ========== БАЗА ДАННЫХ ==========
def init_db():
    conn = sqlite3.connect('projects.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS projects
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  username TEXT,
                  filename TEXT,
                  command TEXT,
                  status TEXT DEFAULT 'stopped',
                  pid INTEGER,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id INTEGER PRIMARY KEY,
                  username TEXT,
                  subscribed INTEGER DEFAULT 0,
                  joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    conn.close()

init_db()

# ========== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ==========
active = {}

# ========== ПРОВЕРКА ПОДПИСКИ ==========
async def check_subscription(user_id: int, app) -> bool:
    try:
        member = await app.bot.get_chat_member(CHANNEL_USERNAME, user_id)
        if member.status in ['member', 'administrator', 'creator']:
            conn = sqlite3.connect('projects.db')
            c = conn.cursor()
            c.execute("INSERT OR REPLACE INTO users (user_id, subscribed) VALUES (?, ?)",
                     (user_id, 1))
            conn.commit()
            conn.close()
            return True
    except Exception as e:
        logging.error(f"Ошибка проверки подписки: {e}")
    
    conn = sqlite3.connect('projects.db')
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO users (user_id, subscribed) VALUES (?, ?)",
             (user_id, 0))
    conn.commit()
    conn.close()
    return False

async def require_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE, func):
    user = update.effective_user
    
    conn = sqlite3.connect('projects.db')
    c = conn.cursor()
    c.execute("SELECT subscribed FROM users WHERE user_id=?", (user.id,))
    result = c.fetchone()
    
    if not result or result[0] == 0:
        is_subscribed = await check_subscription(user.id, context.application)
        if not is_subscribed:
            keyboard = [
                [InlineKeyboardButton("📢 Подписаться на канал", url=f"https://t.me/{CHANNEL_USERNAME[1:]}")],
                [InlineKeyboardButton("✅ Я подписался", callback_data="check_sub")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                f"📢 Для использования бота необходимо подписаться на канал {CHANNEL_USERNAME}\n"
                "После подписки нажмите кнопку ниже:",
                reply_markup=reply_markup
            )
            return
    
    await func(update, context)

# ========== ОСНОВНЫЕ ОБРАБОТЧИКИ С ДЕКОРАТОРОМ ==========
@anti_flood
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await require_subscription(update, context, start_handler)

async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🚀 Python Host Bot\n"
        f"👤 Владелец: @wpwpwe\n\n"
        "📦 Отправь ZIP -> напиши команду python ...\n\n"
        "Команды:\n"
        "/myfiles - мои проекты\n"
        "/stop - остановить проект\n"
        "/ping - проверить пинг"
    )

@anti_flood
async def ping_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await require_subscription(update, context, ping_now_handler)

async def ping_now_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        response = requests.get(PING_URL, timeout=10)
        await update.message.reply_text(f"✅ Пинг! Статус: {response.status_code}")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

@anti_flood
async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    if not await check_subscription(user.id, context.application):
        keyboard = [
            [InlineKeyboardButton("📢 Подписаться на канал", url=f"https://t.me/{CHANNEL_USERNAME[1:]}")],
            [InlineKeyboardButton("✅ Я подписался", callback_data="check_sub")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            f"❌ Для загрузки файлов нужно подписаться на {CHANNEL_USERNAME}",
            reply_markup=reply_markup
        )
        return
    
    if not update.message.document:
        return
    
    file = update.message.document
    if not file.file_name.endswith('.zip'):
        await update.message.reply_text("❌ Только ZIP")
        return
    
    if file.file_size > MAX_SIZE:
        await update.message.reply_text("❌ Макс 15MB")
        return
    
    filename = f"{user.id}_{file.file_name}"
    
    file_obj = await file.get_file()
    await file_obj.download_to_drive(filename)
    
    conn = sqlite3.connect('projects.db')
    c = conn.cursor()
    c.execute("INSERT INTO projects (user_id, username, filename, status) VALUES (?, ?, ?, ?)",
              (user.id, user.username, filename, 'uploaded'))
    conn.commit()
    conn.close()
    
    await update.message.reply_text(f"✅ {file.file_name} сохранен\nНапиши команду python ...")

@anti_flood
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    if not await check_subscription(user.id, context.application):
        return
    
    text = update.message.text.strip()
    
    if not text.startswith('python'):
        await update.message.reply_text("❌ Только python команды")
        return
    
    conn = sqlite3.connect('projects.db')
    c = conn.cursor()
    c.execute("SELECT id, filename FROM projects WHERE user_id=? AND status='uploaded' ORDER BY id DESC LIMIT 1", (user.id,))
    result = c.fetchone()
    
    if not result:
        await update.message.reply_text("❌ Сначала загрузи ZIP")
        return
    
    proj_id, filename = result
    
    extract_dir = f"project_{proj_id}"
    if os.path.exists(extract_dir):
        shutil.rmtree(extract_dir)
    os.makedirs(extract_dir)
    
    try:
        with zipfile.ZipFile(filename, 'r') as zip_ref:
            zip_ref.extractall(extract_dir)
        
        process = subprocess.Popen(
            text.split(),
            cwd=extract_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )
        
        active[proj_id] = process
        
        c.execute("UPDATE projects SET command=?, status='running', pid=? WHERE id=?",
                  (text, process.pid, proj_id))
        conn.commit()
        
        await update.message.reply_text(
            f"🚀 Запущено!\n"
            f"ID проекта: {proj_id}\n"
            f"PID: {process.pid}\n"
            f"Остановить: /stop_{proj_id}"
        )
        
        def monitor():
            try:
                while True:
                    line = process.stdout.readline()
                    if not line and process.poll() is not None:
                        break
            except:
                pass
            finally:
                if proj_id in active:
                    del active[proj_id]
                conn = sqlite3.connect('projects.db')
                c = conn.cursor()
                c.execute("UPDATE projects SET status='stopped' WHERE id=?", (proj_id,))
                conn.commit()
                conn.close()
        
        threading.Thread(target=monitor, daemon=True).start()
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")
    finally:
        conn.close()

@anti_flood
async def myfiles(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await require_subscription(update, context, myfiles_handler)

async def myfiles_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    conn = sqlite3.connect('projects.db')
    c = conn.cursor()
    c.execute("SELECT id, filename, command, status, pid FROM projects WHERE user_id=? ORDER BY id DESC LIMIT 5", (user.id,))
    projects = c.fetchall()
    conn.close()
    
    if not projects:
        await update.message.reply_text("📭 Нет проектов")
        return
    
    text = "📁 Твои проекты:\n\n"
    for p in projects:
        text += f"ID: {p[0]}\nФайл: {p[1]}\nКоманда: {p[2] or 'нет'}\nСтатус: {p[3]}\n"
        if p[4]:
            text += f"PID: {p[4]}\n"
        text += f"Остановить: /stop_{p[0]}\n"
        text += "─" * 20 + "\n"
    
    await update.message.reply_text(text)

@anti_flood
async def stop_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await require_subscription(update, context, stop_cmd_handler)

async def stop_cmd_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    conn = sqlite3.connect('projects.db')
    c = conn.cursor()
    c.execute("SELECT id, filename FROM projects WHERE user_id=? AND status='running'", (user.id,))
    running = c.fetchall()
    conn.close()
    
    if not running:
        await update.message.reply_text("✅ Нет запущенных проектов")
        return
    
    text = "🛑 Остановить проект:\n\n"
    for proj_id, filename in running:
        text += f"ID: {proj_id}\nФайл: {filename}\nОстановить: /stop_{proj_id}\n\n"
    
    await update.message.reply_text(text)

@anti_flood
async def stop_specific(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    if not await check_subscription(user.id, context.application):
        return
    
    command = update.message.text
    
    try:
        proj_id = int(command.split('_')[1])
        
        # Проверяем владельца
        conn = sqlite3.connect('projects.db')
        c = conn.cursor()
        c.execute("SELECT user_id, pid FROM projects WHERE id=?", (proj_id,))
        result = c.fetchone()
        
        if not result or result[0] != user.id:
            await update.message.reply_text("❌ Не ваш проект")
            conn.close()
            return
        
        pid = result[1]
        
        # Останавливаем процесс
        if proj_id in active:
            try:
                process = active[proj_id]
                process.terminate()
                try:
                    process.wait(timeout=2)
                except:
                    pass
                if process.poll() is None:
                    process.kill()
                del active[proj_id]
            except Exception as e:
                print(f"Ошибка остановки процесса: {e}")
        
        # Убиваем через PID
        if pid:
            try:
                os.system(f"pkill -P {pid} 2>/dev/null")
                os.system(f"kill -9 {pid} 2>/dev/null")
            except:
                pass
        
        # Обновляем статус
        c.execute("UPDATE projects SET status='stopped' WHERE id=?", (proj_id,))
        conn.commit()
        conn.close()
        
        await update.message.reply_text(f"✅ Проект {proj_id} остановлен!")
        
    except:
        await update.message.reply_text("❌ Используй: /stop_123")

@anti_flood
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "check_sub":
        user_id = query.from_user.id
        is_subscribed = await check_subscription(user_id, context.application)
        
        if is_subscribed:
            await query.edit_message_text(
                "✅ Отлично! Теперь вы можете использовать бота.\n"
                "Введите /start для начала работы."
            )
        else:
            keyboard = [
                [InlineKeyboardButton("📢 Подписаться на канал", url=f"https://t.me/{CHANNEL_USERNAME[1:]}")],
                [InlineKeyboardButton("🔄 Проверить подписку", callback_data="check_sub")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                f"❌ Вы еще не подписались на канал {CHANNEL_USERNAME}\n"
                "Пожалуйста, подпишитесь и нажмите кнопку проверки:",
                reply_markup=reply_markup
            )

# Админа не проверяем на флуд
async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    
    conn = sqlite3.connect('projects.db')
    c = conn.cursor()
    
    c.execute("SELECT COUNT(*), COUNT(DISTINCT user_id) FROM projects")
    total, users = c.fetchone()
    
    c.execute("SELECT COUNT(*) FROM projects WHERE status='running'")
    running = c.fetchone()[0]
    
    c.execute("SELECT id, user_id, username, filename, command, status FROM projects ORDER BY id DESC LIMIT 10")
    projects = c.fetchall()
    
    conn.close()
    
    text = f"👑 АДМИН\n\nВсего проектов: {total}\nЗапущено: {running}\nУникальных пользователей: {users}\n\n"
    text += f"🚫 ЗАБАНЕНО за флуд: {len(banned_users)} пользователей\n\n"
    
    if banned_users:
        text += "Забаненные ID (последние 20):\n"
        # Берем последние 20 забаненных
        banned_list = sorted(banned_users.items(), key=lambda x: x[1], reverse=True)[:20]
        for user_id, ban_until in banned_list:
            ban_time = datetime.fromtimestamp(ban_until).strftime('%Y-%m-%d %H:%M:%S') if ban_until < time.time() + 1000000 else "НАВСЕГДА"
            text += f"ID: {user_id} (бан до: {ban_time})\n"
        text += "\n"
    
    for p in projects:
        is_banned = p[1] in banned_users
        text += f"ID:{p[0]} @{p[2]} "
        if is_banned:
            text += "🚫\n"
        else:
            text += "\n"
        text += f"Файл: {p[3]}\n"
        text += f"Команда: {p[4] or 'нет'}\n"
        text += f"Статус: {p[5]}\n"
        if p[0] in active:
            text += f"PID: {active[p[0]].pid}\n"
        text += "─\n"
    
    await update.message.reply_text(text)

# ========== ЗАПУСК БОТА ==========
def main():
    app = Application.builder().token(TOKEN).build()
    
    from telegram.ext import CallbackQueryHandler
    app.add_handler(CallbackQueryHandler(button_callback))
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ping", ping_now))
    app.add_handler(CommandHandler("myfiles", myfiles))
    app.add_handler(CommandHandler("stop", stop_cmd))
    app.add_handler(CommandHandler("admin", admin))
    
    app.add_handler(MessageHandler(filters.Regex(r'^/stop_\d+$'), stop_specific))
    
    app.add_handler(MessageHandler(filters.Document.ALL, handle_file))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    print("=" * 50)
    print("🤖 Бот запущен!")
    print(f"✅ Авто-пинг: {PING_URL}")
    print(f"👤 Владелец: @wpwpwe")
    print(f"📢 Канал: {CHANNEL_USERNAME}")
    print(f"🚫 Анти-флуд: {FLOOD_SETTINGS['MAX_MESSAGES']} сообщений за {FLOOD_SETTINGS['TIME_WINDOW']} сек -> ПЕРМАНЕНТНЫЙ ИГНОР")
    print("=" * 50)
    
    app.run_polling()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
