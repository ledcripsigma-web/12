import requests
import time
import threading
from telegram import Bot

# Настройки
BOT_TOKEN = "2202515785:AAEMZYh_y8w7pVfMlkCupHBnx_Oe7EZ-Nu8/test"
CHANNEL_ID = "@SourceCode"
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
    except Exception as e:
        print(f"Ошибка получения цены: {e}")
    return None

def send_price(price):
    """Отправка цены в канал"""
    try:
        message = f"{price}$"
        bot.send_message(chat_id=CHANNEL_ID, text=message)
        print(f"Отправлено: {message}")
    except Exception as e:
        print(f"Ошибка отправки: {e}")

def ping_render():
    """Пинг Render каждые 4 минуты"""
    while running:
        try:
            requests.get(RENDER_URL, timeout=5)
            print("Пинг отправлен на Render")
        except Exception as e:
            print(f"Ошибка пинга: {e}")
        time.sleep(240)

def monitor_prices():
    """Основной мониторинг цен"""
    global last_price, running
    
    print("🚀 Бот запущен. Мониторим TON каждую секунду...")
    
    while running:
        try:
            price = get_ton_price()
            
            if price is not None:
                if last_price is None:
                    send_price(price)
                    last_price = price
                elif price != last_price:
                    send_price(price)
                    last_price = price
            else:
                print("Не удалось получить цену")
            
            time.sleep(1)
            
        except KeyboardInterrupt:
            print("\n🛑 Останавливаем бота...")
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
