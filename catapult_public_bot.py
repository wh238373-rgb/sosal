import os
import logging
import telebot
import asyncio
import json
from datetime import datetime
from dotenv import load_dotenv
from catapult_analyzer import scan_catapult
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import threading
import time

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("TELEGRAM_TOKEN")
bot = telebot.TeleBot(TOKEN, parse_mode='Markdown', threaded=True)

latest_report = None
scanning = False


def update_report():
    """Оновлює звіт кожні 10 хвилин"""
    global latest_report, scanning

    while True:
        try:
            scanning = True
            logger.info("🔄 Запускаю сканування...")
            report = asyncio.run(scan_catapult())
            latest_report = report
            scanning = False
            logger.info("✅ Сканування завершено")
        except Exception as e:
            logger.error(f"❌ Помилка сканування: {e}")
            scanning = False

        time.sleep(600)  # 10 хвилин


@bot.message_handler(commands=['start'])
def start(message):
    logger.info(f"📩 Отримав /start від {message.chat.id}")
    text = """🤖 *Привіт! Я Catapult Analyzer*

Я сканую токени на catapult.trade

*Команди:*
/scan - Сканувати зараз
/report - Останній звіт
/patterns - Паттерни
/help - Допомога"""
    try:
        bot.reply_to(message, text)
        logger.info("✅ Повідомлення відправлено")
    except Exception as e:
        logger.error(f"❌ Помилка при відправці: {e}")


@bot.message_handler(commands=['scan'])
def scan_now(message):
    global latest_report, scanning

    logger.info(f"📩 Отримав /scan від {message.chat.id}")

    if scanning:
        bot.reply_to(message, "⏳ Сканування вже йде...")
        return

    msg = bot.reply_to(message, "🔄 Сканую...")

    try:
        scanning = True
        report = asyncio.run(scan_catapult())
        latest_report = report
        scanning = False

        # Формуємо основний звіт
        text = (f"✅ *СКАНУВАННЯ*\n\n"
                f"📊 Токенів: {report['total_tokens']}\n"
                f"📈 Паттернів: {report['total_patterns_found']}\n\n"
                f"🔥 *ТОП ПАТТЕРНИ:*\n")

        for pattern, count in report['top_patterns'][:5]:
            text += f"  {pattern}: *{count}*\n"

        # Додаємо кнопку для показу всіх токенів
        markup = InlineKeyboardMarkup()
        if report['total_tokens'] > 0:
            markup.add(InlineKeyboardButton("📋 Показити всі токени", callback_data="show_all_tokens"))

        bot.edit_message_text(
            text,
            message.chat.id,
            msg.message_id,
            reply_markup=markup if report['total_tokens'] > 0 else None,
            parse_mode="Markdown"
        )
        logger.info("✅ Звіт відправлено")

    except Exception as e:
        logger.error(f"❌ Помилка сканування: {e}")
        bot.reply_to(message, f"❌ Помилка: {str(e)[:100]}")
        scanning = False


@bot.callback_query_handler(func=lambda call: call.data == "show_all_tokens")
def show_all_tokens(call):
    """Виводить кожен токен окремо з паттернами"""
    global latest_report

    logger.info(f"📩 Натиснув кнопку показити токени: {call.from_user.id}")

    if not latest_report or not latest_report.get("tokens"):
        bot.answer_callback_query(call.id, "❌ Даних про токени нема", show_alert=True)
        return

    tokens = latest_report["tokens"]
    total = len(tokens)

    bot.answer_callback_query(call.id, f"📤 Відправляю {total} токенів...")
    logger.info(f"📤 Почало відправку {total} токенів")

    for idx, token in enumerate(tokens, 1):
        try:
            token_name = token.get("name", f"Token #{token.get('token_id', '?')}")
            token_url = token.get("url")
            patterns = token.get("patterns", [])

            # Формуємо текст про паттерни
            if not patterns:
                patterns_text = "❌ Паттернів немає"
            else:
                # Рахуємо скільки разів кожен паттерн з'явився в цьому токені
                pattern_counts = {}
                for pattern in patterns:
                    pattern_counts[pattern] = pattern_counts.get(pattern, 0) + 1

                patterns_text = "🔍 *Паттерни:*\n"
                for pattern, count in pattern_counts.items():
                    patterns_text += f"  {pattern}: `{count}`\n"

            # Формуємо повідомлення
            token_text = f"*#{idx}. {token_name}*\n\n{patterns_text}"

            # Додаємо кнопку посилання
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("🔗 Перейти до токену", url=token_url))

            bot.send_message(
                call.message.chat.id,
                token_text,
                reply_markup=markup,
                parse_mode="Markdown"
            )

            # Невеликий інтервал щоб не забанили за спам
            time.sleep(0.3)

        except Exception as e:
            logger.error(f"❌ Помилка при відправці токена #{idx}: {e}")
            continue

    logger.info(f"✅ Відправлено {total} токенів")


@bot.message_handler(commands=['report'])
def show_report(message):
    global latest_report

    logger.info(f"📩 Отримав /report від {message.chat.id}")

    if not latest_report:
        bot.reply_to(message, "❌ Даних немає. Запустіть /scan")
        return

    text = f"""📊 *ЗВІТ*

📌 Токенів: {latest_report['total_tokens']}
📌 Паттернів: {latest_report['total_patterns_found']}

🔥 *ТОП ПАТТЕРНИ:*
"""

    for pattern, count in latest_report['top_patterns'][:10]:
        text += f"  {pattern}: {count}\n"

    bot.reply_to(message, text)


@bot.message_handler(commands=['patterns'])
def show_patterns(message):
    global latest_report

    logger.info(f"📩 Отримав /patterns від {message.chat.id}")

    if not latest_report:
        bot.reply_to(message, "❌ Даних немає")
        return

    text = "🔍 *ПАТТЕРНИ*\n\n"

    for pattern, count in latest_report['top_patterns']:
        text += f"{pattern}: *{count}*\n"

    bot.reply_to(message, text)


@bot.message_handler(commands=['help'])
def help_cmd(message):
    logger.info(f"📩 Отримав /help від {message.chat.id}")
    text = """📖 *ДОПОМОГА*

/scan - Сканування
/report - Звіт
/patterns - Паттерни
/help - Допомога"""
    bot.reply_to(message, text)


@bot.message_handler(func=lambda m: True)
def default(message):
    logger.info(f"📩 Невідома команда від {message.chat.id}: {message.text}")
    bot.reply_to(message, "❓ /help")


if __name__ == "__main__":
    logger.info("🚀 Запускаю бота...")

    # Запускаємо фоновий сканер
    scanner_thread = threading.Thread(target=update_report, daemon=True)
    scanner_thread.start()
    logger.info("✅ Фоновий сканер запущений")

    logger.info("📱 Бот активний!")

    # Запускаємо бот з обробкою помилок
    while True:
        try:
            bot.infinity_polling(timeout=30, long_polling_timeout=30, skip_pending=True)
        except Exception as e:
            logger.error(f"⚠️ Помилка polling: {e}")
            time.sleep(5)  # Чекаємо 5 сек перед повторною спробою