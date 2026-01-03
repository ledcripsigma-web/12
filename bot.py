import requests
import time
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import os
from datetime import datetime

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
        
        if response.status_code == 200:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ Отправлено: {text}")
            return True
        else:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ Ошибка {response.status_code}: {response.text[:100]}")
            return False
            
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ Ошибка сети: {e}")
        return False

def get_ton_price():
    """Получение цены TON"""
    try:
        response = requests.get(API_URL, timeout=10)
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 📡 Запрос к KuCoin...")
        
        if response.status_code == 200:
            data = response.json()
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 📊 Ответ KuCoin получен")
            
            if data.get('code') == '200000':
                price = float(data['data']['price'])
                rounded = round(price, 2)
                print(f"[{datetime.now().strftime('%H:%M:%S')}] 💰 Цена: {price:.4f}$ → {rounded}$")
                return rounded
            else:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ KuCoin код ошибки: {data.get('code')}")
        else:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ HTTP ошибка: {response.status_code}")
            
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ Исключение: {e}")
    
    return None

def price_monitor():
    """Мониторинг цены"""
    global last_price
    
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🚀 Мониторинг запущен")
    
    while True:
        try:
            price = get_ton_price()
            
            if price:
                if last_price is None:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🆕 Первая цена: {price}$")
                    send_telegram_message(f"{price}$")
                    last_price = price
                    
                elif price != last_price:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] 📈 Изменение: {last_price}$ → {price}$")
                    send_telegram_message(f"{price}$")
                    last_price = price
                else:
                    # Цена не изменилась
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] ⏸️ Цена: {price}$ (без изменений)", end='\r')
            else:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] ⚠️ Не удалось получить цену")
            
            time.sleep(1)
            
        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 🔥 Ошибка в цикле: {e}")
            time.sleep(2)

def start_http_server():
    """HTTP сервер для порта"""
    port = int(os.environ.get('PORT', 10000))
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🌐 HTTP сервер на порту {port}")
    server = HTTPServer(('0.0.0.0', port), HealthHandler)
    server.serve_forever()

def main():
    print("=" * 50)
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🏁 ЗАПУСК БОТА")
    print("=" * 50)
    
    # Запускаем мониторинг в отдельном потоке
    monitor_thread = threading.Thread(target=price_monitor, daemon=True)
    monitor_thread.start()
    
    # Запускаем HTTP сервер
    start_http_server()

if __name__ == "__main__":
    main()
