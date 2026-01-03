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
RENDER_URL = "https://one2-2-b7o0.onrender.com"  # Твой Render URL

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
        pass

def start_http_server():
    """HTTP сервер для порта (чтобы Render не убивал)"""
    port = int(os.environ.get('PORT', 10000))
    server = HTTPServer(('0.0.0.0', port), HealthHandler)
    print(f"✅ HTTP сервер запущен на порту {port}")
    server.serve_forever()

def ping_render():
    """Автопинг Render каждые 4 минуты"""
    while True:
        try:
            requests.get(RENDER_URL, timeout=5)
            print(f"[{time.strftime('%H:%M:%S')}] 🟢 Пинг")
        except:
            print(f"[{time.strftime('%H:%M:%S')}] 🔴 Ошибка пинга")
        time.sleep(240)  # 4 минуты

def get_price():
    """Получить цену TON"""
    try:
        response = requests.get(API_URL, timeout=5)
        data = response.json()
        price = float(data['data']['price'])
        return round(price, 2)  # Округление до центов
    except:
        return None

def send_price(price):
    """Отправить цену в канал"""
    try:
        bot.send_message(chat_id=CHANNEL_ID, text=f"{price}$")
        print(f"{price}$")
        return True
    except:
        return False

def main():
    global last_price
    
    print("🚀 TON Price Bot запущен")
    
    # Запускаем автопинг в отдельном потоке
    ping_thread = threading.Thread(target=ping_render, daemon=True)
    ping_thread.start()
    
    # Основной цикл мониторинга
    while True:
        price = get_price()
        
        if price:
            if last_price is None:
                send_price(price)
                last_price = price
            elif price != last_price:
                send_price(price)
                last_price = price
            # else: цена не изменилась
        
        time.sleep(1)

if __name__ == "__main__":
    # Запускаем HTTP сервер в отдельном потоке
    http_thread = threading.Thread(target=start_http_server, daemon=True)
    http_thread.start()
    
    # Запускаем основной код
    main()
