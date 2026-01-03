import requests
import time
import telegram
import warnings
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
import os
import sys

# Включаем все принты
print("=== ЗАПУСК БОТА ===")

# Настройки
BOT_TOKEN = "2202515785:AAEMZYh_y8w7pVfMlkCupHBnx_Oe7EZ-Nu8/test"
CHANNEL_ID = "@PriceTonUpdate"
API_URL = "https://api.kucoin.com/api/v1/market/orderbook/level1?symbol=TON-USDT"

print(f"Токен: {BOT_TOKEN[:20]}...")
print(f"Канал: {CHANNEL_ID}")
print(f"API: {API_URL}")

last_price = None
bot = None

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b'TON Bot OK')
    
    def log_message(self, format, *args):
        pass

def start_http_server():
    port = int(os.environ.get('PORT', 10000))
    print(f"Запускаю HTTP сервер на порту {port}")
    server = HTTPServer(('0.0.0.0', port), HealthHandler)
    print("✅ HTTP сервер запущен")
    server.serve_forever()

def price_monitor():
    global last_price, bot
    
    print("=== НАЧИНАЮ МОНИТОРИНГ ===")
    
    # 1. Тест интернета
    print("1. Проверяю интернет...")
    try:
        requests.get("https://google.com", timeout=5)
        print("✅ Интернет есть")
    except Exception as e:
        print(f"❌ Нет интернета: {e}")
        return
    
    # 2. Тест KuCoin API
    print("2. Тестирую KuCoin API...")
    try:
        response = requests.get(API_URL, timeout=10)
        print(f"✅ KuCoin ответил: статус {response.status_code}")
        data = response.json()
        price = float(data['data']['price'])
        print(f"✅ Цена TON: {price}$")
    except Exception as e:
        print(f"❌ KuCoin ошибка: {e}")
        return
    
    # 3. Тест Telegram бота
    print("3. Тестирую Telegram бота...")
    try:
        bot = telegram.Bot(token=BOT_TOKEN)
        bot_info = bot.get_me()
        print(f"✅ Бот: @{bot_info.username}")
        print(f"✅ ID: {bot_info.id}")
        print(f"✅ Имя: {bot_info.first_name}")
    except Exception as e:
        print(f"❌ Ошибка бота: {e}")
        print("Проблема с токеном или сетью Telegram")
        return
    
    # 4. Тест отправки в канал
    print("4. Тест отправки в канал...")
    try:
        test_msg = f"🤖 Бот запущен! Тест: {time.strftime('%H:%M:%S')}"
        bot.send_message(chat_id=CHANNEL_ID, text=test_msg)
        print(f"✅ Тестовое сообщение отправлено в {CHANNEL_ID}")
    except Exception as e:
        print(f"❌ Не могу отправить в канал: {e}")
        print("Проверь:")
        print(f"1. Канал {CHANNEL_ID} существует")
        print("2. Бот - администратор канала")
        print("3. Канал публичный или бот имеет доступ")
        return
    
    print("=== МОНИТОРИНГ НАЧАТ ===")
    
    while True:
        try:
            # Получаем цену
            response = requests.get(API_URL, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                price = round(float(data['data']['price']), 4)
                
                # Если цена изменилась - отправляем
                if last_price is None:
                    print(f"🆕 Первая цена: {price}$")
                    bot.send_message(chat_id=CHANNEL_ID, text=f"{price}$")
                    last_price = price
                    print(f"✅ Отправлено: {price}$")
                    
                elif price != last_price:
                    change = price - last_price
                    arrow = "📈" if change > 0 else "📉"
                    print(f"{arrow} Изменение: {last_price}$ → {price}$")
                    bot.send_message(chat_id=CHANNEL_ID, text=f"{price}$")
                    last_price = price
                    print(f"✅ Отправлено: {price}$")
                else:
                    # Цена не изменилась
                    print(f"⏸️ Цена: {price}$ (без изменений)", end='\r')
            
            time.sleep(1)
            
        except Exception as e:
            print(f"🔥 Ошибка в цикле: {e}")
            time.sleep(2)

def main():
    print("=== ОСНОВНОЙ ЗАПУСК ===")
    
    # Запускаем мониторинг в отдельном потоке
    monitor_thread = threading.Thread(target=price_monitor, daemon=True)
    monitor_thread.start()
    
    # Запускаем HTTP сервер
    start_http_server()

if __name__ == "__main__":
    # Отключаем warnings
    import warnings
    warnings.filterwarnings("ignore")
    
    main()
