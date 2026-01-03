import requests
import time
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Bot
import os

# === НАСТРОЙКИ ===
BOT_TOKEN = "2202515785:AAEMZYh_y8w7pVfMlkCupHBnx_Oe7EZ-Nu8/test"
CHANNEL_ID = "@PriceTonUpdate"
API_URL = "https://api.kucoin.com/api/v1/market/orderbook/level1?symbol=TON-USDT"

# Переменные
last_price = None
bot = None
running = True

# === HTTP сервер для порта ===
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b'OK')
    
    def log_message(self, format, *args):
        pass

def start_http_server():
    """Запускаем HTTP сервер для порта (обязательно для Web Service)"""
    port = int(os.environ.get('PORT', 10000))
    server = HTTPServer(('0.0.0.0', port), HealthHandler)
    print(f"HTTP сервер запущен на порту {port}")
    server.serve_forever()

def get_ton_price():
    """Получение цены TON"""
    try:
        response = requests.get(API_URL, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data.get('code') == '200000':
                return round(float(data['data']['price']), 4)
    except:
        pass
    return None

def send_price(price):
    """Отправка цены в канал"""
    global bot
    try:
        if bot is None:
            bot = Bot(token=BOT_TOKEN)
        
        message = f"{price}$"
        bot.send_message(chat_id=CHANNEL_ID, text=message)
        print(f"{price}$")
        return True
    except Exception as e:
        print(f"Ошибка: {e}")
        return False

def price_monitor():
    """Мониторинг цен в отдельном потоке"""
    global last_price, running
    
    while running:
        try:
            price = get_ton_price()
            
            if price:
                if last_price is None:
                    send_price(price)
                    last_price = price
                elif price != last_price:
                    send_price(price)
                    last_price = price
            
            time.sleep(1)
            
        except Exception as e:
            print(f"Ошибка мониторинга: {e}")
            time.sleep(2)

def main():
    global running
    
    # Запускаем мониторинг в отдельном потоке
    monitor_thread = threading.Thread(target=price_monitor, daemon=True)
    monitor_thread.start()
    
    # Запускаем HTTP сервер (основной поток)
    start_http_server()

if __name__ == "__main__":
    main()
