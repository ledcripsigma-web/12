import requests
import time
import threading
from telegram import Bot
from datetime import datetime

# Настройки
BOT_TOKEN = "2202515785:AAEMZYh_y8w7pVfMlkCupHBnx_Oe7EZ-Nu8/test"
CHANNEL_ID = "@SourceCode"  # Твой канал
RENDER_URL = "https://one2-2-b7o0.onrender.com"
API_URL = "https://api.binance.com/api/v3/ticker/price?symbol=TONUSDT"

# Глобальные переменные
last_price = None
bot = Bot(token=BOT_TOKEN)
running = True

def get_ton_price():
    """Быстрое получение цены"""
    try:
        response = requests.get(API_URL, timeout=2)
        if response.status_code == 200:
            data = response.json()
            return round(float(data['price']), 2)
    except:
        pass
    return None

def send_price(price):
    """Отправка цены в канал"""
    try:
        message = f"{price}$"
        bot.send_message(chat_id=CHANNEL_ID, text=message)
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Отправлено: {message}")
    except Exception as e:
        print(f"Ошибка: {e}")

def ping_render():
    """Пинг Render каждые 4 минуты"""
    while running:
        try:
            requests.get(RENDER_URL, timeout=5)
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Пинг отправлен")
        except:
            pass
        time.sleep(240)

def monitor_prices():
    """Основной мониторинг цен"""
    global last_price
    
    print("Бот запущен. Мониторим TON каждую секунду...")
    
    while running:
        try:
            # Получаем цену
            price = get_ton_price()
            
            if price:
                # Если цена изменилась - отправляем
                if price != last_price:
                    send_price(price)
                    last_price = price
                else:
                    # Логируем (можно убрать)
                    pass
                    # print(f"[{datetime.now().strftime('%H:%M:%S')}] Цена та же: {price}$")
            else:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Не получили цену")
            
            # Ждем ровно 1 секунду
            time.sleep(1)
            
        except KeyboardInterrupt:
            print("\nОстанавливаем бота...")
            running = False
            break
        except Exception as e:
            print(f"Ошибка: {e}")
            time.sleep(1)

if __name__ == "__main__":
    # Запускаем пинг в отдельном потоке
    ping_thread = threading.Thread(target=ping_render, daemon=True)
    ping_thread.start()
    
    # Запускаем мониторинг
    monitor_prices()
