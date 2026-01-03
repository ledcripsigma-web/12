import requests
import time
from telegram import Bot
import os

# Настройки
BOT_TOKEN = "2202515785:AAEMZYh_y8w7pVfMlkCupHBnx_Oe7EZ-Nu8/test"
CHANNEL_ID = "@PriceTonUpdate"
API_URL = "https://api.kucoin.com/api/v1/market/orderbook/level1?symbol=TON-USDT"

last_price = None
bot = Bot(token=BOT_TOKEN)

def get_price():
    try:
        response = requests.get(API_URL, timeout=5)
        data = response.json()
        return round(float(data['data']['price']), 4)
    except:
        return None

def send_price(price):
    try:
        bot.send_message(chat_id=CHANNEL_ID, text=f"{price}$")
        print(f"{price}$")
        return True
    except:
        return False

def main():
    global last_price
    
    print("Бот запущен")
    
    while True:
        price = get_price()
        
        if price:
            if last_price is None:
                send_price(price)
                last_price = price
            elif price != last_price:
                send_price(price)
                last_price = price
        
        time.sleep(1)

if __name__ == "__main__":
    # Игнорим warnings
    import warnings
    warnings.filterwarnings("ignore")
    
    main()
