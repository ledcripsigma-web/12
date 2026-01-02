import requests
import time
import threading
from telegram import Bot

# Настройки
BOT_TOKEN = "2202515785:AAEMZYh_y8w7pVfMlkCupHBnx_Oe7EZ-Nu8/test"
CHANNEL_ID = "@SourceCode"
RENDER_URL = "https://one2-2-b7o0.onrender.com"

# Глобальные переменные
last_price = None
bot = Bot(token=BOT_TOKEN)
running = True

def get_ton_price():
    """Получение цены TON с 10 разных источников"""
    
    sources = [
        # 1. CoinGecko (самый надежный)
        {
            "name": "CoinGecko",
            "url": "https://api.coingecko.com/api/v3/simple/price",
            "params": {"ids": "toncoin", "vs_currencies": "usd"},
            "parser": lambda r: r.json()['toncoin']['usd']
        },
        
        # 2. Binance
        {
            "name": "Binance",
            "url": "https://api.binance.com/api/v3/ticker/price",
            "params": {"symbol": "TONUSDT"},
            "parser": lambda r: float(r.json()['price'])
        },
        
        # 3. Bybit
        {
            "name": "Bybit",
            "url": "https://api.bybit.com/v5/market/tickers",
            "params": {"category": "spot", "symbol": "TONUSDT"},
            "parser": lambda r: float(r.json()['result']['list'][0]['lastPrice'])
        },
        
        # 4. KuCoin
        {
            "name": "KuCoin",
            "url": "https://api.kucoin.com/api/v1/market/orderbook/level1",
            "params": {"symbol": "TON-USDT"},
            "parser": lambda r: float(r.json()['data']['price'])
        },
        
        # 5. MEXC
        {
            "name": "MEXC",
            "url": "https://api.mexc.com/api/v3/ticker/price",
            "params": {"symbol": "TONUSDT"},
            "parser": lambda r: float(r.json()['price'])
        },
        
        # 6. OKX
        {
            "name": "OKX",
            "url": "https://www.okx.com/api/v5/market/ticker",
            "params": {"instId": "TON-USDT"},
            "parser": lambda r: float(r.json()['data'][0]['last'])
        },
        
        # 7. Gate.io
        {
            "name": "Gate.io",
            "url": "https://api.gateio.ws/api/v4/spot/tickers",
            "params": {"currency_pair": "TON_USDT"},
            "parser": lambda r: float(r.json()[0]['last'])
        },
        
        # 8. Huobi
        {
            "name": "Huobi",
            "url": "https://api.huobi.pro/market/detail/merged",
            "params": {"symbol": "tonusdt"},
            "parser": lambda r: r.json()['tick']['close']
        },
        
        # 9. CoinMarketCap (через простой парсинг)
        {
            "name": "CoinMarketCap",
            "url": "https://api.coinmarketcap.com/data-api/v3/cryptocurrency/detail",
            "params": {"slug": "toncoin", "aux": "stats"},
            "parser": lambda r: r.json()['data']['stats']['price']
        },
        
        # 10. Bitget
        {
            "name": "Bitget",
            "url": "https://api.bitget.com/api/v2/spot/market/tickers",
            "params": {"symbol": "TONUSDT"},
            "parser": lambda r: float(r.json()['data'][0]['lastPr'])
        },
        
        # 11. BingX (бонус)
        {
            "name": "BingX",
            "url": "https://open-api.bingx.com/openApi/spot/v1/ticker/24hr",
            "params": {"symbol": "TON-USDT"},
            "parser": lambda r: float(r.json()['lastPrice'])
        },
        
        # 12. Poloniex
        {
            "name": "Poloniex",
            "url": "https://api.poloniex.com/markets/TON_USDT/price",
            "parser": lambda r: float(r.json()['price'])
        }
    ]
    
    for source in sources:
        try:
            print(f"🔍 Пробуем {source['name']}...", end=" ")
            
            if 'params' in source:
                response = requests.get(
                    source['url'], 
                    params=source['params'],
                    timeout=5,
                    headers={
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                    }
                )
            else:
                response = requests.get(
                    source['url'], 
                    timeout=5,
                    headers={
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                    }
                )
            
            if response.status_code == 200:
                price = source['parser'](response)
                if price and price > 0:
                    print(f"✅ {price}$")
                    return round(price, 2)
                else:
                    print("❌ Некорректная цена")
            else:
                print(f"❌ Код {response.status_code}")
                
        except Exception as e:
            print(f"❌ Ошибка: {str(e)[:30]}")
            continue
    
    print("😔 Все источники недоступны")
    return None

def send_price(price):
    """Отправка цены в канал"""
    try:
        message = f"{price}$"
        bot.send_message(chat_id=CHANNEL_ID, text=message)
        print(f"📤 Отправлено: {message}")
        return True
    except Exception as e:
        print(f"❌ Ошибка отправки: {e}")
        return False

def ping_render():
    """Пинг Render каждые 4 минуты"""
    while running:
        try:
            requests.get(RENDER_URL, timeout=5)
            print("🔄 Пинг Render")
        except:
            print("⚠️ Не удалось пинговать Render")
        time.sleep(240)

def monitor_prices():
    """Основной мониторинг цен"""
    global last_price, running
    
    print("=" * 60)
    print("🚀 TON Price Bot запущен!")
    print(f"📢 Канал: {CHANNEL_ID}")
    print("⏱️  Проверка: каждую секунду")
    print("📊 Источники: 12 бирж")
    print("=" * 60)
    
    # Тест подключения
    print("\n🔌 Тестируем подключение к интернету...")
    try:
        test = requests.get("https://google.com", timeout=5)
        print(f"✅ Интернет доступен (код: {test.status_code})")
    except:
        print("❌ Нет интернета!")
    
    # Запускаем пинг
    threading.Thread(target=ping_render, daemon=True).start()
    
    error_count = 0
    
    while running:
        try:
            price = get_ton_price()
            
            if price is not None:
                error_count = 0  # Сбрасываем счетчик ошибок
                
                if last_price is None:
                    print(f"\n🎯 Первая цена: {price}$")
                    if send_price(price):
                        last_price = price
                elif price != last_price:
                    change = price - last_price
                    change_pct = (change / last_price) * 100
                    arrow = "📈" if change > 0 else "📉"
                    
                    print(f"\n{arrow} Изменение: {last_price}$ → {price}$ ({change_pct:+.2f}%)")
                    if send_price(price):
                        last_price = price
                else:
                    # Цена не изменилась
                    print(".", end="", flush=True)
                    
            else:
                error_count += 1
                print(f"\n❌ Ошибка #{error_count}: цена не получена")
                
                if error_count > 10:
                    print("⚠️ Много ошибок подряд. Пауза 30 секунд...")
                    time.sleep(30)
                    error_count = 0
            
            time.sleep(1)
            
        except KeyboardInterrupt:
            print("\n\n🛑 Останавливаем бота...")
            running = False
            break
            
        except Exception as e:
            print(f"\n🔥 Критическая ошибка: {e}")
            time.sleep(5)

if __name__ == "__main__":
    monitor_prices()
