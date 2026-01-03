import requests
import time
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import os

# === НАСТРОЙКИ ===
BOT_TOKEN = "2202515785:AAEMZYh_y8w7pVfMlkCupHBnx_Oe7EZ-Nu8/test"
CHANNEL_ID = "@PriceTonUpdate"
API_URL = "https://api.kucoin.com/api/v1/market/orderbook/level1?symbol=TON-USDT"

last_price = None

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b'OK')
    
    def log_message(self, format, *args):
        pass

def send_telegram_message(text):
    """Отправка сообщения через Telegram Bot API"""
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        data = {
            "chat_id": CHANNEL_ID,
            "text": text,
            "disable_notification": True
        }
        
        response = requests.post(url, json=data, timeout=10)
        return response.status_code == 200
            
    except:
        return False

def get_ton_price():
    """Получение цены TON (округление до 2 знаков)"""
    try:
        response = requests.get(API_URL, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data.get('code') == '200000':
                price = float(data['data']['price'])
                # Обычное математическое округление
                return round(price, 2)
    except:
        pass
    return None

def price_monitor():
    """Мониторинг цены"""
    global last_price
    
    while True:
        try:
            price = get_ton_price()
            
            if price:
                if last_price is None:
                    # Первая цена
                    if send_telegram_message(f"{price}$"):
                        print(f"{price}$")
                        last_price = price
                    
                elif price != last_price:
                    # Цена изменилась
                    if send_telegram_message(f"{price}$"):
                        print(f"{price}$")
                        last_price = price
                else:
                    # Цена не изменилась
                    print(f"{price}$", end='\r')
            
            time.sleep(1)
            
        except Exception as e:
            print(f"Ошибка: {e}")
            time.sleep(2)

def start_http_server():
    """HTTP сервер для порта"""
    port = int(os.environ.get('PORT', 10000))
    server = HTTPServer(('0.0.0.0', port), HealthHandler)
    server.serve_forever()

def main():
    # Запускаем мониторинг в отдельном потоке
    monitor_thread = threading.Thread(target=price_monitor, daemon=True)
    monitor_thread.start()
    
    # Запускаем HTTP сервер
    start_http_server()

if __name__ == "__main__":
    main()
