import requests
import time
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import os

# Настройки
BOT_TOKEN = "2202515785:AAEMZYh_y8w7pVfMlkCupHBnx_Oe7EZ-Nu8/test"
CHANNEL_ID = "@PriceTonUpdate"
API_URL = "https://api.kucoin.com/api/v1/market/orderbook/level1?symbol=TON-USDT"
RENDER_URL = "https://one-p66h.onrender.com"

last_price = None

# HTTP сервер для порта
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b'TON Bot OK')
    
    def log_message(self, format, *args):
        pass

def start_http_server():
    """HTTP сервер для порта"""
    port = int(os.environ.get('PORT', 10000))
    server = HTTPServer(('0.0.0.0', port), HealthHandler)
    print(f"✅ HTTP сервер запущен на порту {port}")
    server.serve_forever()

def ping_render():
    """Автопинг Render"""
    while True:
        try:
            requests.get(RENDER_URL, timeout=5)
            print(f"[{time.strftime('%H:%M:%S')}] 🟢 Пинг")
        except:
            print(f"[{time.strftime('%H:%M:%S')}] 🔴 Ошибка пинга")
        time.sleep(240)

def get_price():
    """Получить цену TON"""
    try:
        response = requests.get(API_URL, timeout=5)
        data = response.json()
        price = float(data['data']['price'])
        return round(price, 2)
    except:
        return None

def send_telegram_message(price):
    """Отправка через Telegram Bot API"""
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        data = {
            "chat_id": CHANNEL_ID,
            "text": f"{price}$",
            "disable_notification": True
        }
        
        response = requests.post(url, json=data, timeout=10)
        if response.status_code == 200:
            print(f"{price}$")
            return True
        else:
            print(f"Ошибка: {response.status_code}")
            return False
    except Exception as e:
        print(f"Ошибка отправки: {e}")
        return False

def price_monitor():
    """Мониторинг цен"""
    global last_price
    
    print("🚀 TON Price Bot запущен")
    
    while True:
        try:
            price = get_price()
            
            if price:
                if last_price is None:
                    send_telegram_message(price)
                    last_price = price
                elif price != last_price:
                    send_telegram_message(price)
                    last_price = price
            
            time.sleep(1)
            
        except Exception as e:
            print(f"Ошибка: {e}")
            time.sleep(2)

def main():
    # Запускаем автопинг
    ping_thread = threading.Thread(target=ping_render, daemon=True)
    ping_thread.start()
    
    # Запускаем мониторинг
    monitor_thread = threading.Thread(target=price_monitor, daemon=True)
    monitor_thread.start()
    
    # Запускаем HTTP сервер
    start_http_server()

if __name__ == "__main__":
    main()
