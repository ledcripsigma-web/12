import requests
import time
import telegram
import warnings
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
import os

# Игнорируем warnings
warnings.filterwarnings("ignore")

# Настройки
BOT_TOKEN = "2202515785:AAEMZYh_y8w7pVfMlkCupHBnx_Oe7EZ-Nu8/test"
CHANNEL_ID = "@PriceTonUpdate"
API_URL = "https://api.kucoin.com/api/v1/market/orderbook/level1?symbol=TON-USDT"

last_price = None
bot = telegram.Bot(token=BOT_TOKEN)

# HTTP сервер для порта
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b'TON Bot OK')
    
    def log_message(self, format, *args):
        pass  # Отключаем логи

def start_http_server():
    """Запуск HTTP сервера для порта"""
    port = int(os.environ.get('PORT', 10000))
    server = HTTPServer(('0.0.0.0', port), HealthHandler)
    print(f"HTTP сервер запущен на порту {port}")
    server.serve_forever()

def price_monitor():
    """Мониторинг цены"""
    global last_price
    
    print("Мониторинг цены TON запущен")
    
    while True:
        try:
            # Получаем цену
            response = requests.get(API_URL, timeout=5)
            data = response.json()
            price = round(float(data['data']['price']), 4)
            
            # Если цена изменилась - отправляем
            if last_price is None:
                bot.send_message(chat_id=CHANNEL_ID, text=f"{price}$")
                print(f"{price}$")
                last_price = price
            elif price != last_price:
                bot.send_message(chat_id=CHANNEL_ID, text=f"{price}$")
                print(f"{price}$")
                last_price = price
            
            time.sleep(1)
            
        except Exception as e:
            print(f"Ошибка: {e}")
            time.sleep(2)

def main():
    # Запускаем мониторинг в отдельном потоке
    monitor_thread = threading.Thread(target=price_monitor, daemon=True)
    monitor_thread.start()
    
    # Запускаем HTTP сервер в основном потоке
    start_http_server()

if __name__ == "__main__":
    main()
