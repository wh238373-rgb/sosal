import os
import logging
import telebot
import asyncio
import json
import sys
from datetime import datetime
from dotenv import load_dotenv
from catapult_analyzer import scan_catapult
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import threading
import time
import traceback

load_dotenv()

# 🔧 Налаштування логування
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),  # 📝 Логи у файл
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TOKEN:
    logger.error("❌ TELEGRAM_TOKEN не знайдений у .env!")
    sys.exit(1)

bot = telebot.TeleBot(TOKEN, parse_mode='Markdown', threaded=True)

# 🔄 Глобальні змінні
latest_report = None
scanning = False
scan_error_count = 0
last_scan_time = None


def update_report():
    """🔄 Оновлює звіт кожні 10 хвилин"""
    global latest_report, scanning, scan_error_count, last_scan_time

    while True:
        try:
            scanning = True
            logger.info("=" * 70)
            logger.info("🔄 ФОНОВИЙ СКАНЕР: Запускаю сканування...")
            logger.info("=" * 70)

            # 🆕 Правильна асинхронність для VPS
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            try:
                report = loop.run_until_complete(
                    scan_catapult(headless=True, use_virtual_display=True)
                )
                latest_report = report
                last_scan_time = datetime.now()
                scanning = False
                scan_error_count = 0
                
                logger.info("✅ ФОНОВИЙ СКАНЕР: Сканування завершено успішно")
                logger.info(f"   📊 Знайдено токенів: {report['total_tokens']}")
                logger.info(f"   📈 Паттернів: {report['total_patterns_found']}")
                
            finally:
                loop.close()

        except Exception as e:
            logger.error(f"❌ ФОНОВИЙ СКАНЕР: Помилка сканування")
            logger.error(f"   {str(e)}")
            logger.debug(traceback.format_exc())
            
            scan_error_count += 1
            scanning = False

            # 🚨 Якщо багато помилок поспіль - перезавантажити
            if scan_error_count > 5:
                logger.critical(f"🔴 КРИТИЧНО: {scan_error_count} помилок поспіль!")
                logger.critical("   Перезавантажу процес...")
                os._exit(1)

        # ⏰ Чекаємо 10 хвилин
        logger.info("⏳ Фоновий сканер спить 10 хвилин...")
        time.sleep(600)


@bot.message_handler(commands=['start'])
def start(message):
    """Команда /start"""
    logger.info(f"📩 /start від {message.chat.id} (@{message.from_user.username})")
    
    text = """🤖 *Привіт! Я Catapult Analyzer*

Я сканую нові токени на **catapult.trade** 🚀

*📋 Команди:*
/scan - Сканувати зараз
/report - Останній звіт
/patterns - Статистика паттернів
/status - Статус бота
/help - Допомога"""
    
    try:
        bot.reply_to(message, text)
        logger.info("✅ /start: повідомлення відправлено")
    except Exception as e:
        logger.error(f"❌ /start: помилка відправки: {e}")


@bot.message_handler(commands=['status'])
def status(message):
    """🔧 Статус бота"""
    logger.info(f"📩 /status від {message.chat.id}")
    
    status_text = "🤖 *СТАТУС БОТА*\n\n"
    
    if scanning:
        status_text += "🔄 *Сканування:* Йде прямо зараз\n"
    else:
        status_text += "✅ *Сканування:* Готово\n"
    
    status_text += f"❌ *Помилок:* {scan_error_count}/5\n"
    
    if latest_report:
        status_text += f"📊 *Токенів у звіті:* {latest_report['total_tokens']}\n"
        status_text += f"📈 *Паттернів:* {latest_report['total_patterns_found']}\n"
        if last_scan_time:
            status_text += f"⏰ *Останнє сканування:* {last_scan_time.strftime('%H:%M:%S')}\n"
    else:
        status_text += "📊 *Звіт:* Ще немає\n"
    
    bot.reply_to(message, status_text)


@bot.message_handler(commands=['scan'])
def scan_now(message):
    """Команда /scan - Сканувати одразу"""
    global latest_report, scanning

    logger.info(f"📩 /scan від {message.chat.id}")

    if scanning:
        bot.reply_to(message, "⏳ Сканування вже йде...\nСпробуйте через хвилину")
        return

    msg = bot.reply_to(message, "🔄 Сканую токени на catapult.trade...\n⏳ Зачекайте 2-3 хвилини...")

    try:
        scanning = True
        logger.info("   🔄 Початок ручного сканування...")
        
        # 🆕 Правильна асинхронність
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            report = loop.run_until_complete(
                scan_catapult(headless=True, use_virtual_display=True)
            )
            latest_report = report
            scanning = False
            
            logger.info(f"   ✅ Ручне сканування завершено")
            logger.info(f"      Токенів: {report['total_tokens']}")
            logger.info(f"      Паттернів: {report['total_patterns_found']}")

        finally:
            loop.close()

        # 📊 Формуємо звіт
        if report['total_tokens'] == 0:
            text = "⚠️ *СКАНУВАННЯ*\n\n❌ Токенів не знайдено"
        else:
            text = (f"✅ *СКАНУВАННЯ CATAPULT*\n\n"
                    f"📊 Токенів: `{report['total_tokens']}`\n"
                    f"📈 Паттернів: `{report['total_patterns_found']}`\n\n"
                    f"���� *ТОП ПАТТЕРНИ:*\n")

            for pattern, count in report['top_patterns'][:5]:
                text += f"  {pattern}: `{count}`\n"

        # 🔘 Кнопка для показу всіх токенів
        markup = None
        if report['total_tokens'] > 0:
            markup = InlineKeyboardMarkup()
            markup.add(
                InlineKeyboardButton(
                    f"📋 Показати {report['total_tokens']} токенів",
                    callback_data="show_all_tokens"
                )
            )

        bot.edit_message_text(
            text,
            message.chat.id,
            msg.message_id,
            reply_markup=markup,
            parse_mode="Markdown"
        )
        logger.info("   ✅ Звіт відправлено")

    except Exception as e:
        logger.error(f"❌ /scan: помилка: {e}")
        logger.debug(traceback.format_exc())
        
        try:
            bot.reply_to(
                message,
                f"❌ *Помилка сканування*\n\n`{str(e)[:100]}`"
            )
        except:
            pass
        
        scanning = False


@bot.callback_query_handler(func=lambda call: call.data == "show_all_tokens")
def show_all_tokens(call):
    """Показати всі токени один за одним"""
    global latest_report

    logger.info(f"📩 show_all_tokens від {call.from_user.id}")

    if not latest_report or not latest_report.get("tokens"):
        bot.answer_callback_query(call.id, "❌ Даних немає", show_alert=True)
        return

    tokens = latest_report["tokens"]
    total = len(tokens)

    bot.answer_callback_query(call.id, f"📤 Відправляю {total} токенів...")
    logger.info(f"   📤 Почало відправку {total} токенів")

    for idx, token in enumerate(tokens, 1):
        try:
            token_name = token.get("name", f"Token #{token.get('token_id', '?')}")
            token_url = token.get("url")
            patterns = token.get("patterns", [])

            # 📝 Формуємо текст
            if not patterns:
                patterns_text = "❌ Паттернів немає"
            else:
                pattern_counts = {}
                for pattern in patterns:
                    pattern_counts[pattern] = pattern_counts.get(pattern, 0) + 1

                patterns_text = "🔍 *Паттерни:*\n"
                for pattern, count in sorted(pattern_counts.items()):
                    patterns_text += f"  {pattern}: `{count}`\n"

            token_text = f"*#{idx}. {token_name}*\n\n{patterns_text}"

            # 🔘 Кнопка
            markup = InlineKeyboardMarkup()
            markup.add(
                InlineKeyboardButton("🔗 Перейти на Catapult", url=token_url)
            )

            bot.send_message(
                call.message.chat.id,
                token_text,
                reply_markup=markup,
                parse_mode="Markdown"
            )

            # ⏱️ Затримка щоб не спамити
            time.sleep(0.25)

        except Exception as e:
            logger.error(f"❌ show_all_tokens: помилка токена #{idx}: {e}")
            continue

    logger.info(f"   ✅ Відправлено {total} токенів")


@bot.message_handler(commands=['report'])
def show_report(message):
    """Показати останній звіт"""
    global latest_report

    logger.info(f"📩 /report від {message.chat.id}")

    if not latest_report:
        bot.reply_to(message, "❌ Даних немає\n\nЗапустіть `/scan`", parse_mode="Markdown")
        return

    text = f"""📊 *ЗВІТ CATAPULT*

📌 Токенів: `{latest_report['total_tokens']}`
📌 Паттернів: `{latest_report['total_patterns_found']}`

🔥 *ТОП ПАТТЕРНИ (ТОП 10):*
"""

    for idx, (pattern, count) in enumerate(latest_report['top_patterns'][:10], 1):
        text += f"{idx}. {pattern}: `{count}`\n"

    bot.reply_to(message, text)


@bot.message_handler(commands=['patterns'])
def show_patterns(message):
    """Показати статистику всіх паттернів"""
    global latest_report

    logger.info(f"📩 /patterns від {message.chat.id}")

    if not latest_report or not latest_report['top_patterns']:
        bot.reply_to(message, "❌ Даних немає\n\nЗапустіть `/scan`", parse_mode="Markdown")
        return

    text = "🔍 *СТАТИСТИКА ПАТТЕРНІВ*\n\n"

    for pattern, count in latest_report['top_patterns']:
        bar = "▪" * min(count, 20)  # Візуальна шкала
        text += f"{pattern}: {bar} ({count})\n"

    bot.reply_to(message, text)


@bot.message_handler(commands=['help'])
def help_cmd(message):
    """Команда /help"""
    logger.info(f"📩 /help від {message.chat.id}")
    
    text = """📖 *ДОПОМОГА*

*Команди:*
/scan - 🔄 Сканування прямо зараз
/report - 📊 Останній звіт
/patterns - 🔍 Статистика паттернів
/status - 🤖 Статус бота
/help - 📖 Ця допомога

*Автоматичне сканування:* Кожні 10 хвилин ⏰

*Паттерни:*
⏰NEW - Новий токен
🚀PUMP - Зростання ціни
📈VOLUME - Обсяг торгів
🔒LOCK - Блокування ліквідності
📱SOCIAL - Соціальні мережі
👥HOLDERS - Кількість власників
🚨RUG - Ризик скама
📉DIP - Падіння ціни
💰MCAP - Капіталізація
💎HIGH_PRICE - Висока ціна"""
    
    bot.reply_to(message, text)


@bot.message_handler(func=lambda m: True)
def default(message):
    """Обробка невідомих команд"""
    logger.info(f"📩 Невідома команда від {message.chat.id}: {message.text}")
    bot.reply_to(message, "❓ Невідома команда\n\nВикористайте `/help`", parse_mode="Markdown")


def main():
    """🚀 Основна функція"""
    logger.info("=" * 70)
    logger.info("🚀 ЗАПУСК БОТА CATAPULT ANALYZER")
    logger.info("=" * 70)
    
    # 🔧 Перевіримо Telegram TOKEN
    if not TOKEN:
        logger.error("❌ TELEGRAM_TOKEN не знайдений!")
        return
    
    logger.info(f"✅ TOKEN завантажений: {TOKEN[:10]}...")
    
    # 🔄 Запускаємо фоновий сканер
    logger.info("\n🔄 Запускаю фоновий сканер...")
    scanner_thread = threading.Thread(target=update_report, daemon=True)
    scanner_thread.start()
    logger.info("✅ Фоновий сканер запущений (оновлення кожні 10 хвилин)")

    logger.info("\n📱 БОТ АКТИВНИЙ! Чекаю команди...\n")

    # 🔄 Запускаємо бот з обробкою помилок
    while True:
        try:
            bot.infinity_polling(
                timeout=30,
                long_polling_timeout=30,
                skip_pending=True
            )
        except Exception as e:
            logger.error(f"⚠️ Помилка polling: {e}")
            logger.debug(traceback.format_exc())
            logger.info("⏳ Перезавантаження за 5 сек...")
            time.sleep(5)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("\n🛑 БОТ ЗУПИНЕНИЙ (Ctrl+C)")
        sys.exit(0)
    except Exception as e:
        logger.critical(f"🔴 КРИТИЧНА ПОМИЛКА: {e}")
        logger.debug(traceback.format_exc())
        sys.exit(1)
