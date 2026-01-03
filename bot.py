import requests
import time
import threading
from telegram import Bot

# === НАСТРОЙКИ ===
BOT_TOKEN = "2202515785:AAEMZYh_y8w7pVfMlkCupHBnx_Oe7EZ-Nu8/test"
CHANNEL_ID = "@PriceTonUpdate"
API_URL = "https://api.kucoin.com/api/v1/market/orderbook/level1?symbol=TON-USDT"

# Глобальные переменные
last_price = None
bot = Bot(token=BOT_TOKEN)
running = True

def get_ton_price():
    """Получение цены TON с KuCoin"""
    try:
        response = requests.get(API_URL, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data.get('code') == '200000':
                return round(float(data['data']['price']), 4)
    except:
        pass
    return None

def send_price(price):
    """Отправка цены в канал"""
    try:
        message = f"{price}$"
        bot.send_message(chat_id=CHANNEL_ID, text=message)
        print(f"[{time.strftime('%H:%M:%S')}] {price}$")
        return True
    except Exception as e:
        print(f"[{time.strftime('%H:%M:%S')}] Ошибка отправки: {e}")
        return False

def main():
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
                # else: цена не изменилась, ничего не делаем
            else:
                print(f"[{time.strftime('%H:%M:%S')}] Не удалось получить цену")
            
            time.sleep(1)
            
        except KeyboardInterrupt:
            running = False
        except Exception as e:
            print(f"[{time.strftime('%H:%M:%S')}] Ошибка: {e}")
            time.sleep(2)

if __name__ == "__main__":
    main()
