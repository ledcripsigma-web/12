import requests
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
import os

# Настройки
BOT_TOKEN = "2202515785:AAEMZYh_y8w7pVfMlkCupHBnx_Oe7EZ-Nu8/test"
CHANNEL_ID = "@PriceTonUpdate"
API_URL = "https://api.kucoin.com/api/v1/market/orderbook/level1?symbol=TON-USDT"

last_price = None

# Простейший HTTP сервер
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'OK')

def log(msg):
    """Логирование с timestamp"""
    timestamp = time.strftime("%H:%M:%S")
    print(f"[{timestamp}] {msg}")

def get_price():
    """Получить цену TON"""
    try:
        response = requests.get(API_URL, timeout=5)
        data = response.json()
        price = float(data['data']['price'])
        rounded = round(price, 2)
        log(f"Цена: {price:.4f} -> {rounded}")
        return rounded
    except Exception as e:
        log(f"Ошибка цены: {e}")
        return None

def send_to_channel(price):
    """Отправить в канал"""
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        data = {"chat_id": CHANNEL_ID, "text": f"{price}$"}
        response = requests.post(url, json=data, timeout=5)
        
        if response.status_code == 200:
            log(f"Отправлено: {price}$")
            return True
        else:
            log(f"Ошибка Telegram: {response.status_code}")
            return False
    except Exception as e:
        log(f"Ошибка отправки: {e}")
        return False

def main():
    global last_price
    
    log("Бот запущен")
    
    # Тест подключения
    log("Тестирую подключения...")
    
    # Тест интернета
    try:
        requests.get("https://google.com", timeout=3)
        log("Интернет: OK")
    except:
        log("Интернет: НЕТ")
    
    # Тест KuCoin
    price = get_price()
    if price:
        log(f"KuCoin: OK ({price}$)")
    else:
        log("KuCoin: ОШИБКА")
    
    # Тест Telegram
    try:
        test_url = f"https://api.telegram.org/bot{BOT_TOKEN}/getMe"
        response = requests.get(test_url, timeout=5)
        if response.status_code == 200:
            log("Telegram бот: OK")
        else:
            log(f"Telegram бот: ОШИБКА {response.status_code}")
    except Exception as e:
        log(f"Telegram тест: {e}")
    
    # Основной цикл
    log("Начинаю мониторинг...")
    
    while True:
        price = get_price()
        
        if price:
            if last_price is None:
                # Первая цена
                send_to_channel(price)
                last_price = price
            elif price != last_price:
                # Цена изменилась
                send_to_channel(price)
                last_price = price
            else:
                # Цена не изменилась
                pass
        
        time.sleep(1)

if __name__ == "__main__":
    # Запускаем HTTP сервер в отдельном потоке
    import threading
    
    def run_server():
        port = int(os.environ.get('PORT', 10000))
        server = HTTPServer(('0.0.0.0', port), HealthHandler)
        server.serve_forever()
    
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    
    # Запускаем основной код
    main()
