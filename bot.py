import requests
import time
import threading
from telegram import Bot
from telegram.error import TelegramError

# Настройки
BOT_TOKEN = "2202515785:AAEMZYh_y8w7pVfMlkCupHBnx_Oe7EZ-Nu8/test"
CHANNEL_ID = "@SourceCode"  # Проверь что канал существует и бот админ
RENDER_URL = "https://one2-2-b7o0.onrender.com"

# Глобальные переменные
last_price = None
bot = None
running = True

def init_bot():
    """Инициализация бота с проверкой"""
    global bot
    try:
        bot = Bot(token=BOT_TOKEN)
        
        # Проверяем что бот работает
        bot_info = bot.get_me()
        print(f"✅ Бот: @{bot_info.username}")
        print(f"✅ ID: {bot_info.id}")
        print(f"✅ Имя: {bot_info.first_name}")
        
        # Пробуем отправить тестовое сообщение
        test_msg = "🤖 Бот TON Price запущен!"
        bot.send_message(chat_id=CHANNEL_ID, text=test_msg)
        print(f"✅ Тестовое сообщение отправлено в {CHANNEL_ID}")
        
        return True
        
    except TelegramError as e:
        print(f"❌ Ошибка Telegram: {e}")
        print(f"❌ Токен: {BOT_TOKEN[:20]}...")
        return False
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return False

def get_ton_price():
    """Получение цены только с KuCoin"""
    try:
        url = "https://api.kucoin.com/api/v1/market/orderbook/level1"
        params = {"symbol": "TON-USDT"}
        
        response = requests.get(url, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if data['code'] == '200000':  # KuCoin успешный код
                price = float(data['data']['price'])
                print(f"✅ KuCoin: {price}$")
                return round(price, 2)
    except Exception as e:
        print(f"❌ KuCoin ошибка: {str(e)[:50]}")
    
    return None

def send_to_channel(price):
    """Отправка цены в канал"""
    global bot
    
    if not bot:
        print("❌ Бот не инициализирован")
        return False
    
    try:
        message = f"{price}$"
        
        # Пробуем отправить
        sent_message = bot.send_message(
            chat_id=CHANNEL_ID,
            text=message,
            disable_notification=True  # Без звука
        )
        
        print(f"📤 Отправлено в канал: {message}")
        print(f"📝 ID сообщения: {sent_message.message_id}")
        return True
        
    except TelegramError as e:
        print(f"❌ Ошибка отправки: {e}")
        
        # Проверяем конкретные ошибки
        if "Chat not found" in str(e):
            print("❌ Канал не найден! Проверь:")
            print(f"   1. Канал: {CHANNEL_ID}")
            print(f"   2. Бот добавлен как администратор")
            print(f"   3. Канал публичный или бот имеет доступ")
        elif "Forbidden" in str(e):
            print("❌ Бот заблокирован в канале или нет прав")
        elif "Unauthorized" in str(e):
            print("❌ Неверный токен бота")
        
        return False
        
    except Exception as e:
        print(f"❌ Неизвестная ошибка: {e}")
        return False

def ping_render():
    """Пинг Render"""
    while running:
        try:
            requests.get(RENDER_URL, timeout=5)
            print("🔄 Пинг Render")
        except:
            pass
        time.sleep(240)

def main():
    global last_price, running
    
    print("=" * 60)
    print("🚀 Запуск TON Price Bot")
    print("=" * 60)
    
    # Инициализируем бота
    if not init_bot():
        print("❌ Не удалось инициализировать бота")
        print("Проверь:")
        print("1. Токен бота (получи новый у @BotFather)")
        print("2. Канал существует")
        print("3. Бот - администратор канала")
        return
    
    # Запускаем пинг
    threading.Thread(target=ping_render, daemon=True).start()
    
    print("\n🔍 Начинаем мониторинг цены TON...")
    print("Источник: KuCoin")
    print("=" * 60)
    
    while running:
        try:
            # Получаем цену
            price = get_ton_price()
            
            if price is not None:
                if last_price is None:
                    print(f"\n🎯 Первая цена: {price}$")
                    if send_to_channel(price):
                        last_price = price
                    else:
                        print("❌ Не удалось отправить первую цену")
                        
                elif price != last_price:
                    change = price - last_price
                    arrow = "📈" if change > 0 else "📉"
                    
                    print(f"\n{arrow} Изменение: {last_price}$ → {price}$ ({change:+.2f})")
                    
                    if send_to_channel(price):
                        last_price = price
                    else:
                        print("❌ Не удалось отправить изменение цены")
                        
                else:
                    # Цена не изменилась
                    print(".", end="", flush=True)
            else:
                print("⚠️ Цена не получена")
            
            time.sleep(1)
            
        except KeyboardInterrupt:
            print("\n\n🛑 Остановка...")
            running = False
            break
            
        except Exception as e:
            print(f"\n🔥 Ошибка: {e}")
            time.sleep(2)

if __name__ == "__main__":
    main()
