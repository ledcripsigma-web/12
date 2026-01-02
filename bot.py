import requests
import time
import threading
import socket
from telegram import Bot

# Настройки
BOT_TOKEN = "2202515785:AAEMZYh_y8w7pVfMlkCupHBnx_Oe7EZ-Nu8/test"
CHANNEL_ID = "@SourceCode"
RENDER_URL = "https://one2-2-b7o0.onrender.com"

# Переменные
last_price = None
bot = Bot(token=BOT_TOKEN)
running = True

def check_internet():
    """Проверка доступности интернета"""
    hosts = ['8.8.8.8', '1.1.1.1', 'google.com', 'api.coingecko.com']
    
    for host in hosts:
        try:
            socket.create_connection((host, 80), timeout=5)
            print(f"✅ Интернет доступен через {host}")
            return True
        except OSError:
            print(f"❌ {host} недоступен")
    
    return False

def get_price_simple():
    """Самый простой способ получить цену"""
    # Пробуем прямо через IP адрес
    try:
        # Прямой запрос без сложных параметров
        url = "https://api.coingecko.com/api/v3/simple/price?ids=toncoin&vs_currencies=usd"
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            return round(data['toncoin']['usd'], 2)
    except:
        pass
    
    # Если не получилось, пробуем локальный парсинг
    try:
        url = "https://www.binance.com/api/v3/ticker/price?symbol=TONUSDT"
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            return round(float(data['price']), 2)
    except:
        pass
    
    return None

def send_message(price):
    """Отправка сообщения"""
    try:
        bot.send_message(chat_id=CHANNEL_ID, text=f"{price}$")
        print(f"📤 Отправлено: {price}$")
        return True
    except Exception as e:
        print(f"❌ Ошибка отправки: {e}")
        return False

def ping_render():
    """Пинг для поддержания активности"""
    while running:
        try:
            requests.get(RENDER_URL, timeout=5)
            print("🔄 Пинг")
        except:
            pass
        time.sleep(240)

def main():
    global last_price, running
    
    print("=" * 50)
    print("🔧 Проверка соединения...")
    
    if not check_internet():
        print("❌ НЕТ ИНТЕРНЕТА НА RENDER!")
        print("Попробуй другой сервис вместо Render:")
        print("1. PythonAnywhere")
        print("2. Replit")
        print("3. Heroku")
        print("4. Запусти на своем сервере/VPS")
        return
    
    print("✅ Интернет работает")
    
    # Тест бота
    try:
        bot_info = bot.get_me()
        print(f"✅ Бот: @{bot_info.username}")
    except Exception as e:
        print(f"❌ Ошибка бота: {e}")
        return
    
    # Запускаем пинг
    threading.Thread(target=ping_render, daemon=True).start()
    
    print("\n🚀 Начинаем мониторинг...\n")
    
    while running:
        try:
            price = get_price_simple()
            
            if price:
                if last_price != price:
                    if send_message(price):
                        last_price = price
                else:
                    # Цена не изменилась
                    pass
            else:
                print("⚠️ Не получили цену")
            
            time.sleep(1)
            
        except KeyboardInterrupt:
            running = False
        except Exception as e:
            print(f"Ошибка: {e}")
            time.sleep(2)

if __name__ == "__main__":
    main()
