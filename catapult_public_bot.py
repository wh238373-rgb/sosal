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
bot = telebot.TeleBot(TOKEN, parse_mode='HTML', threaded=True)  # 🔧 Змінив на HTML замість Markdown

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
    text = """🤖 <b>Привіт! Я Catapult Analyzer</b>

Я сканую токени на catapult.trade

<b>Команди:</b>
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
        bot.reply_to(message, "⏳ Сканування вже йде...", parse_mode='HTML')
        return

    msg = bot.reply_to(message, "🔄 Сканую...", parse_mode='HTML')

    try:
        scanning = True
        report = asyncio.run(scan_catapult())
        latest_report = report
        scanning = False

        # 🔧 Формуємо звіт БЕЗ емодзи в Markdown
        if report['total_tokens'] == 0:
            text = "<b>СКАНУВАННЯ</b>\n\n❌ Токенів не знайдено"
        else:
            text = (f"<b>СКАНУВАННЯ</b>\n\n"
                    f"Токенів: <code>{report['total_tokens']}</code>\n"
                    f"Паттернів: <code>{report['total_patterns_found']}</code>\n\n"
                    f"<b>ТОП ПАТТЕРНИ:</b>\n")

            for pattern, count in report['top_patterns'][:5]:
                # 🔧 Очищуємо емодзи з назви паттерну для безпеки
                clean_pattern = str(pattern).strip()
                text += f"{clean_pattern}: <code>{count}</code>\n"

        # Додаємо кнопку для показу всіх токенів
        markup = InlineKeyboardMarkup()
        if report['total_tokens'] > 0:
            markup.add(InlineKeyboardButton(
                f"📋 Показати {report['total_tokens']} токенів",
                callback_data="show_all_tokens"
            ))

        bot.edit_message_text(
            text,
            message.chat.id,
            msg.message_id,
            reply_markup=markup if report['total_tokens'] > 0 else None,
            parse_mode='HTML'
        )
        logger.info("✅ Звіт відправлено")

    except Exception as e:
        logger.error(f"❌ Помилка сканування: {e}")
        try:
            bot.reply_to(message, f"❌ Помилка: {str(e)[:100]}", parse_mode='HTML')
        except:
            pass
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

    bot.answer_callback_query(call.id, f"📤 Відправляю {total} токенів...", show_alert=False)
    logger.info(f"📤 Почало відправку {total} токенів")

    for idx, token in enumerate(tokens, 1):
        try:
            token_name = token.get("name", f"Token #{token.get('token_id', '?')}")
            token_url = token.get("url")
            patterns = token.get("patterns", [])

            # 🔧 Формуємо текст про паттерни БЕЗ Markdown конфліктів
            if not patterns:
                patterns_text = "❌ Паттернів немає"
            else:
                pattern_counts = {}
                for pattern in patterns:
                    pattern_counts[pattern] = pattern_counts.get(pattern, 0) + 1

                patterns_text = "<b>Паттерни:</b>\n"
                for pattern, count in pattern_counts.items():
                    clean_pattern = str(pattern).strip()
                    patterns_text += f"{clean_pattern}: <code>{count}</code>\n"

            token_text = f"<b>#{idx}. {token_name}</b>\n\n{patterns_text}"

            # Додаємо кнопку посилання
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("🔗 Перейти до токену", url=token_url))

            bot.send_message(
                call.message.chat.id,
                token_text,
                reply_markup=markup,
                parse_mode='HTML'
            )

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
        bot.reply_to(message, "❌ Даних немає. Запустіть /scan", parse_mode='HTML')
        return

    text = f"""<b>ЗВІТ</b>

Токенів: <code>{latest_report['total_tokens']}</code>
Паттернів: <code>{latest_report['total_patterns_found']}</code>

<b>ТОП ПАТТЕРНИ (ТОП 10):</b>
"""

    for idx, (pattern, count) in enumerate(latest_report['top_patterns'][:10], 1):
        clean_pattern = str(pattern).strip()
        text += f"{idx}. {clean_pattern}: <code>{count}</code>\n"

    bot.reply_to(message, text, parse_mode='HTML')


@bot.message_handler(commands=['patterns'])
def show_patterns(message):
    global latest_report

    logger.info(f"📩 Отримав /patterns від {message.chat.id}")

    if not latest_report:
        bot.reply_to(message, "❌ Даних немає", parse_mode='HTML')
        return

    text = "<b>СТАТИСТИКА ПАТТЕРНІВ</b>\n\n"

    for pattern, count in latest_report['top_patterns']:
        clean_pattern = str(pattern).strip()
        bar = "▪" * min(count, 15)
        text += f"{clean_pattern}: {bar} ({count})\n"

    bot.reply_to(message, text, parse_mode='HTML')


@bot.message_handler(commands=['help'])
def help_cmd(message):
    logger.info(f"📩 Отримав /help від {message.chat.id}")
    text = """<b>ДОПОМОГА</b>

/scan - Сканування
/report - Звіт
/patterns - Паттерни
/help - Допомога"""
    bot.reply_to(message, text, parse_mode='HTML')


@bot.message_handler(func=lambda m: True)
def default(message):
    logger.info(f"📩 Невідома команда від {message.chat.id}: {message.text}")
    bot.reply_to(message, "❓ Невідома команда. Введіть /help", parse_mode='HTML')


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
            time.sleep(5)
