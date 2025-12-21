import os
import sqlite3
import zipfile
import subprocess
import shutil
import asyncio
import aiohttp
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# ========== НАСТРОЙКИ ==========
TOKEN = "2202599086:AAH6oYmkqHVOiN5ieQwh0moaewQzMzkOMcI/test"  # 🔴 ЗАМЕНИ НА СВОЙ ТОКЕН!
ADMIN_ID = 2202291197
MAX_SIZE = 15 * 1024 * 1024  # 15MB
PING_URL = "https://one2-2-b7o0.onrender.com"  # 🎯 ТВОЙ ХОСТ ДЛЯ ПИНГА
PING_INTERVAL = 240  # Пинг каждые 4 минуты (в секундах)

# ========== АВТО-ПИНГ ==========
async def auto_ping():
    """Автоматический пинг хоста каждые 4 минуты"""
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(PING_URL) as response:
                    print(f"✅ [{datetime.now().strftime('%H:%M:%S')}] Пинг отправлен. Статус: {response.status}")
        except Exception as e:
            print(f"❌ [{datetime.now().strftime('%H:%M:%S')}] Ошибка пинга: {e}")
        
        await asyncio.sleep(PING_INTERVAL)

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
    conn.commit()
    conn.close()

init_db()

# ========== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ==========
active = {}  # Активные процессы {project_id: process}
bot_app = None  # Ссылка на приложение бота

# ========== КОМАНДЫ БОТА ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🚀 Python Host Bot + Auto-Ping\n\n"
        "✅ Авто-пинг активен для:\n"
        f"🔗 {PING_URL}\n\n"
        "📦 Отправь ZIP с Python проектом\n"
        "💻 Затем команду для запуска\n\n"
        "Команды:\n"
        "/myfiles - мои проекты\n"
        "/stop - остановить проект\n"
        "/status - статус проектов\n"
        "/ping - проверить пинг сейчас"
    )

async def ping_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ручная проверка пинга"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(PING_URL) as response:
                await update.message.reply_text(f"✅ Пинг отправлен! Статус: {response.status}")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.document:
        return
    
    file = update.message.document
    if not file.file_name.endswith('.zip'):
        await update.message.reply_text("❌ Только ZIP файлы")
        return
    
    if file.file_size > MAX_SIZE:
        await update.message.reply_text("❌ Максимум 15MB")
        return
    
    user = update.effective_user
    filename = f"{user.id}_{file.file_name}"
    
    # Скачиваем файл
    file_obj = await file.get_file()
    await file_obj.download_to_drive(filename)
    
    # Сохраняем в БД
    conn = sqlite3.connect('projects.db')
    c = conn.cursor()
    c.execute("INSERT INTO projects (user_id, username, filename, status) VALUES (?, ?, ?, ?)",
              (user.id, user.username, filename, 'uploaded'))
    conn.commit()
    conn.close()
    
    await update.message.reply_text(
        f"✅ {file.file_name} сохранен!\n\n"
        f"Теперь напиши команду для запуска.\n"
        f"Например: python main.py\n"
        f"Или: python bot.py"
    )

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    user = update.effective_user
    
    if not text.startswith('python'):
        await update.message.reply_text("❌ Только python команды (начинаются с python)")
        return
    
    # Ищем последний загруженный файл пользователя
    conn = sqlite3.connect('projects.db')
    c = conn.cursor()
    c.execute("SELECT id, filename FROM projects WHERE user_id=? AND status='uploaded' ORDER BY id DESC LIMIT 1", (user.id,))
    result = c.fetchone()
    
    if not result:
        await update.message.reply_text("❌ Сначала загрузи ZIP файл!")
        return
    
    proj_id, filename = result
    
    # Распаковываем
    extract_dir = f"project_{proj_id}"
    if os.path.exists(extract_dir):
        shutil.rmtree(extract_dir)
    os.makedirs(extract_dir)
    
    try:
        with zipfile.ZipFile(filename, 'r') as zip_ref:
            zip_ref.extractall(extract_dir)
        
        # Запускаем процесс
        process = subprocess.Popen(
            text,
            shell=True,
            cwd=extract_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )
        
        # Сохраняем процесс
        active[proj_id] = process
        
        # Обновляем БД
        c.execute("UPDATE projects SET command=?, status='running', pid=? WHERE id=?",
                  (text, process.pid, proj_id))
        conn.commit()
        
        await update.message.reply_text(
            f"🚀 Проект запущен!\n\n"
            f"📁 Файл: {filename}\n"
            f"⚡ Команда: {text}\n"
            f"🔢 PID: {process.pid}\n\n"
            f"Чтобы остановить: /stop_{proj_id}"
        )
        
        # Запускаем чтение логов в фоне
        asyncio.create_task(read_output(proj_id, process))
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка запуска: {e}")
    finally:
        conn.close()

async def read_output(proj_id, process):
    """Чтение вывода процесса"""
    try:
        while True:
            line = process.stdout.readline()
            if not line and process.poll() is not None:
                break
            # Можно добавить сохранение логов в БД
    except:
        pass
    finally:
        # Очистка при завершении процесса
        if proj_id in active:
            del active[proj_id]
        conn = sqlite3.connect('projects.db')
        c = conn.cursor()
        c.execute("UPDATE projects SET status='stopped' WHERE id=?", (proj_id,))
        conn.commit()
        conn.close()

async def myfiles(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    conn = sqlite3.connect('projects.db')
    c = conn.cursor()
    c.execute("SELECT id, filename, command, status, pid FROM projects WHERE user_id=? ORDER BY id DESC LIMIT 5", (user.id,))
    projects = c.fetchall()
    conn.close()
    
    if not projects:
        await update.message.reply_text("📭 У тебя пока нет проектов")
        return
    
    text = "📁 Твои проекты:\n\n"
    for p in projects:
        text += f"🆔 ID: {p[0]}\n"
        text += f"📄 Файл: {p[1]}\n"
        text += f"⚡ Команда: {p[2] or 'нет'}\n"
        text += f"📊 Статус: {p[3]}\n"
        if p[4]:
            text += f"🔢 PID: {p[4]}\n"
        text += "─" * 20 + "\n"
    
    await update.message.reply_text(text)

async def stop_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    user = update.effective_user
    
    if not args:
        # Показываем запущенные проекты
        conn = sqlite3.connect('projects.db')
        c = conn.cursor()
        c.execute("SELECT id, filename FROM projects WHERE user_id=? AND status='running'", (user.id,))
        running = c.fetchall()
        conn.close()
        
        if not running:
            await update.message.reply_text("✅ Нет запущенных проектов")
            return
        
        text = "🛑 Выбери проект для остановки:\n\n"
        for proj_id, filename in running:
            text += f"/stop_{proj_id} - {filename}\n"
        await update.message.reply_text(text)
        return
    
    # Останавливаем конкретный проект
    try:
        proj_id = int(args[0])
        
        # Проверяем владельца
        conn = sqlite3.connect('projects.db')
        c = conn.cursor()
        c.execute("SELECT user_id FROM projects WHERE id=?", (proj_id,))
        result = c.fetchone()
        
        if not result or result[0] != user.id:
            await update.message.reply_text("❌ Это не твой проект!")
            return
        
        # Останавливаем процесс
        if proj_id in active:
            process = active[proj_id]
            process.terminate()
            try:
                process.wait(timeout=3)
            except:
                process.kill()
            del active[proj_id]
        
        c.execute("UPDATE projects SET status='stopped' WHERE id=?", (proj_id,))
        conn.commit()
        conn.close()
        
        await update.message.reply_text(f"✅ Проект {proj_id} остановлен")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    running = []
    
    for proj_id, process in active.items():
        # Проверяем владельца в БД
        conn = sqlite3.connect('projects.db')
        c = conn.cursor()
        c.execute("SELECT user_id FROM projects WHERE id=?", (proj_id,))
        result = c.fetchone()
        conn.close()
        
        if result and result[0] == user.id:
            running.append(f"• Проект {proj_id} - PID: {process.pid}")
    
    if running:
        await update.message.reply_text("🚀 Запущенные проекты:\n" + "\n".join(running))
    else:
        await update.message.reply_text("📭 Нет запущенных проектов")

async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    
    conn = sqlite3.connect('projects.db')
    c = conn.cursor()
    
    # Статистика
    c.execute("SELECT COUNT(*), COUNT(DISTINCT user_id) FROM projects")
    total, users = c.fetchone()
    
    c.execute("SELECT COUNT(*) FROM projects WHERE status='running'")
    running = c.fetchone()[0]
    
    # Последние проекты
    c.execute("SELECT id, user_id, username, filename, command, status FROM projects ORDER BY id DESC LIMIT 10")
    projects = c.fetchall()
    
    conn.close()
    
    text = f"👑 АДМИН ПАНЕЛЬ\n\n"
    text += f"📊 Всего проектов: {total}\n"
    text += f"🚀 Запущено сейчас: {running}\n"
    text += f"👤 Уникальных пользователей: {users}\n"
    text += f"✅ Авто-пинг активен: {PING_URL}\n\n"
    
    text += "📁 Последние проекты:\n"
    for p in projects:
        text += f"\n🆔 ID:{p[0]} 👤 @{p[2]}({p[1]})\n"
        text += f"📄 {p[3]}\n"
        text += f"⚡ {p[4] or 'нет'}\n"
        text += f"📊 Статус: {p[5]}\n"
        if p[0] in active:
            text += f"🔢 PID: {active[p[0]].pid}\n"
        text += "─\n"
    
    await update.message.reply_text(text)

# ========== ЗАПУСК БОТА ==========
async def main():
    global bot_app
    
    # Создаем приложение бота
    bot_app = Application.builder().token(TOKEN).build()
    
    # Регистрируем обработчики команд
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(CommandHandler("ping", ping_now))
    bot_app.add_handler(CommandHandler("myfiles", myfiles))
    bot_app.add_handler(CommandHandler("stop", stop_cmd))
    bot_app.add_handler(CommandHandler("status", status))
    bot_app.add_handler(CommandHandler("admin", admin))
    
    # Обработчики сообщений
    bot_app.add_handler(MessageHandler(filters.Document.ALL, handle_file))
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    # Запускаем авто-пинг в фоне
    asyncio.create_task(auto_ping())
    
    print("=" * 50)
    print("🤖 Бот запущен!")
    print(f"👑 Админ ID: {ADMIN_ID}")
    print(f"✅ Авто-пинг активен для: {PING_URL}")
    print("=" * 50)
    
    # Запускаем бота
    await bot_app.run_polling()

if __name__ == "__main__":
    # Настраиваем логирование
    logging.basicConfig(level=logging.INFO)
    
    # Запускаем основную функцию
    asyncio.run(main())
