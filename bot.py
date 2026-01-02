import requests
import time
import threading
import telegram  # Используем telegram вместо python-telegram-bot

# Настройки
BOT_TOKEN = "2202515785:AAEMZYh_y8w7pVfMlkCupHBnx_Oe7EZ-Nu8/test"
CHANNEL_ID = "@SourceCode"
RENDER_URL = "https://one2-2-b7o0.onrender.com"

# Переменные
last_price = None
running = True

def init_bot():
    """Инициализация бота"""
    try:
        # Простая проверка - отправляем тестовое сообщение
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/getMe"
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Бот: @{data['result']['username']}")
            return True
        else:
            print(f"❌ Ошибка бота: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return False

def send_message_to_channel(text):
    """Отправка сообщения в канал через Telegram API"""
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        data = {
            "chat_id": CHANNEL_ID,
            "text": text,
            "disable_notification": True
        }
        
        response = requests.post(url, json=data, timeout=10)
        
        if response.status_code == 200:
            print(f"✅ Отправлено: {text}")
            return True
        else:
            print(f"❌ Ошибка отправки: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Ошибка сети: {e}")
        return False

def get_ton_price():
    """Получение цены TON"""
    try:
        # KuCoin - самый надежный
        url = "https://api.kucoin.com/api/v1/market/orderbook/level1"
        params = {"symbol": "TON-USDT"}
        
        response = requests.get(url, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if data.get('code') == '200000':
                price = float(data['data']['price'])
                return round(price, 2)
    except Exception as e:
        print(f"KuCoin error: {str(e)[:50]}")
    
    # Запасной вариант
    try:
        url = "https://api.coingecko.com/api/v3/simple/price"
        params = {"ids": "toncoin", "vs_currencies": "usd"}
        
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            return round(data['toncoin']['usd'], 2)
    except:
        pass
    
    return None

def ping_render():
    """Пинг для поддержания активности"""
    while running:
        try:
            requests.get(RENDER_URL, timeout=5)
            print("🔄 Ping Render")
        except:
            pass
        time.sleep(240)

def main():
    global last_price, running
    
    print("=" * 50)
    print("🚀 TON Price Bot - Simplified Version")
    print("=" * 50)
    
    # Проверяем бота
    if not init_bot():
        print("❌ Не удалось проверить бота")
        return
    
    # Отправляем стартовое сообщение
    send_message_to_channel("🤖 Бот TON Price запущен!")
    
    # Запускаем пинг
    threading.Thread(target=ping_render, daemon=True).start()
    
    print("\n🔍 Начинаем мониторинг...")
    
    error_count = 0
    success_count = 0
    
    while running:
        try:
            # Получаем цену
            price = get_ton_price()
            
            if price:
                success_count += 1
                error_count = 0
                
                if last_price is None:
                    print(f"\n🎯 Первая цена: {price}$")
                    if send_message_to_channel(f"{price}$"):
                        last_price = price
                        
                elif price != last_price:
                    print(f"\n📊 Изменение: {last_price}$ → {price}$")
                    if send_message_to_channel(f"{price}$"):
                        last_price = price
                else:
                    # Цена не изменилась
                    if success_count % 60 == 0:  # Каждые 60 успехов
                        print(f"⏱️ Цена стабильна: {price}$ (секунд: {success_count})")
                        
            else:
                error_count += 1
                print(f"⚠️ Ошибка #{error_count}: цена не получена")
                
                if error_count > 10:
                    print("😴 Пауза 30 секунд...")
                    time.sleep(30)
                    error_count = 0
            
            time.sleep(1)
            
        except KeyboardInterrupt:
            print("\n🛑 Остановка...")
            running = False
            break
            
        except Exception as e:
            print(f"\n🔥 Ошибка: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()
