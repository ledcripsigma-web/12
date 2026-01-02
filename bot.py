import requests
import time
import threading
from telegram import Bot

# Настройки
BOT_TOKEN = "2202515785:AAEMZYh_y8w7pVfMlkCupHBnx_Oe7EZ-Nu8/test"
CHANNEL_ID = "@SourceCode"
RENDER_URL = "https://one2-2-b7o0.onrender.com"

# Глобальные переменные
last_price = None
bot = Bot(token=BOT_TOKEN)
running = True

def get_ton_price():
    """Получение цены TON с нескольких источников"""
    sources = [
        # Источник 1: Binance
        ("https://api.binance.com/api/v3/ticker/price?symbol=TONUSDT", lambda r: float(r.json()['price'])),
        # Источник 2: Bybit
        ("https://api.bybit.com/v5/market/tickers?category=spot&symbol=TONUSDT", lambda r: float(r.json()['result']['list'][0]['lastPrice'])),
        # Источник 3: Kucoin
        ("https://api.kucoin.com/api/v1/market/orderbook/level1?symbol=TON-USDT", lambda r: float(r.json()['data']['price'])),
        # Источник 4: MEXC
        ("https://api.mexc.com/api/v3/ticker/price?symbol=TONUSDT", lambda r: float(r.json()['price'])),
    ]
    
    for url, parser in sources:
        try:
            response = requests.get(url, timeout=3)
            if response.status_code == 200:
                price = parser(response)
                print(f"✅ Цена получена с {url.split('/')[2]}: {price}")
                return round(price, 2)
        except Exception as e:
            print(f"❌ Ошибка от {url.split('/')[2]}: {str(e)[:50]}")
            continue
    
    return None

def send_price(price):
    """Отправка цены в канал"""
    try:
        message = f"{price}$"
        bot.send_message(chat_id=CHANNEL_ID, text=message)
        print(f"📤 Отправлено в канал: {message}")
    except Exception as e:
        print(f"❌ Ошибка отправки: {e}")

def ping_render():
    """Пинг Render каждые 4 минуты"""
    while running:
        try:
            requests.get(RENDER_URL, timeout=5)
            print("🔄 Пинг отправлен на Render")
        except Exception as e:
            print(f"⚠️ Ошибка пинга: {e}")
        time.sleep(240)

def monitor_prices():
    """Основной мониторинг цен"""
    global last_price, running
    
    print("=" * 50)
    print("🚀 Бот TON Price Tracker запущен!")
    print(f"📢 Канал: {CHANNEL_ID}")
    print("⏱️  Проверка каждую секунду")
    print("=" * 50)
    
    while running:
        try:
            price = get_ton_price()
            
            if price is not None:
                if last_price is None:
                    print(f"🆕 Первая цена: {price}$")
                    send_price(price)
                    last_price = price
                elif price != last_price:
                    print(f"📈 Изменение цены: {last_price}$ → {price}$")
                    send_price(price)
                    last_price = price
                else:
                    # Цена не изменилась, тихо продолжаем
                    pass
            else:
                print("❌ Не удалось получить цену ни с одного источника")
            
            time.sleep(1)
            
        except KeyboardInterrupt:
            print("\n🛑 Останавливаем бота...")
            running = False
            break
        except Exception as e:
            print(f"🔥 Критическая ошибка: {e}")
            time.sleep(5)

if __name__ == "__main__":
    # Запускаем пинг в отдельном потоке
    ping_thread = threading.Thread(target=ping_render, daemon=True)
    ping_thread.start()
    
    # Запускаем мониторинг
    monitor_prices()
