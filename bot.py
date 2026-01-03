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

def test_telegram_bot():
    """Тестируем подключение бота к Telegram"""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🔧 Тестирую Telegram бота...")
    
    # Тест 1: Проверка токена
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/getMe"
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ Бот: @{data['result']['username']}")
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ ID: {data['result']['id']}")
        else:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ Ошибка токена: {response.status_code}")
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Токен: {BOT_TOKEN[:20]}...")
            return False
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ Ошибка подключения: {e}")
        return False
    
    # Тест 2: Проверка отправки в канал
    try:
        test_msg = "🤖 Тест бота TON Price"
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        data = {
            "chat_id": CHANNEL_ID,
            "text": test_msg,
            "disable_notification": True
        }
        
        response = requests.post(url, json=data, timeout=10)
        
        if response.status_code == 200:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ Тест отправлен в канал {CHANNEL_ID}")
            return True
        else:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ Ошибка отправки: {response.status_code}")
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Ответ: {response.text[:200]}")
            
            # Проверяем конкретные ошибки
            error_data = response.json()
            if "description" in error_data:
                error_desc = error_data['description']
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Описание: {error_desc}")
                
                if "chat not found" in error_desc.lower():
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ Канал {CHANNEL_ID} не найден!")
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Проверь что канал существует и бот - администратор")
                elif "forbidden" in error_desc.lower():
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ У бота нет доступа к каналу!")
                elif "unauthorized" in error_desc.lower():
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ Неверный токен бота!")
            
            return False
            
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ Ошибка теста: {e}")
        return False

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
            return True
        else:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ Ошибка отправки цены: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ Ошибка сети: {e}")
        return False

def get_ton_price():
    """Получение цены TON"""
    try:
        response = requests.get(API_URL, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if data.get('code') == '200000':
                price = float(data['data']['price'])
                return round(price, 2)
    except:
        pass
    return None

def price_monitor():
    """Мониторинг цены"""
    global last_price
    
    # Сначала тестируем бота
    if not test_telegram_bot():
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ⚠️ Продолжаю без Telegram...")
    
    while True:
        try:
            price = get_ton_price()
            
            if price:
                if last_price is None:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🆕 Первая цена: {price}$")
                    if send_telegram_message(f"{price}$"):
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ Отправлено: {price}$")
                    last_price = price
                    
                elif price != last_price:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] 📈 Изменение: {last_price}$ → {price}$")
                    if send_telegram_message(f"{price}$"):
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ Отправлено: {price}$")
                    last_price = price
                else:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] ⏸️ Цена: {price}$", end='\r')
            
            time.sleep(1)
            
        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 🔥 Ошибка: {e}")
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
