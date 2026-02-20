import os
import logging
import telebot
import asyncio
from datetime import datetime
from dotenv import load_dotenv
from catapult_analyzer import scan_catapult
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import threading
import time
import sys

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TOKEN:
    logger.error("❌ TELEGRAM_TOKEN не знайдений!")
    sys.exit(1)

bot = telebot.TeleBot(TOKEN, parse_mode='HTML', threaded=True)

latest_report = None
scanning = False


def update_report():
    """Оновлює звіт кожні 10 хвилин"""
    global latest_report, scanning

    while True:
        try:
            scanning = True
            logger.info("🔄 Фоновий сканер: Запускаю...")
            
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            report = loop.run_until_complete(scan_catapult())
            loop.close()
            
            latest_report = report
            scanning = False
            logger.info(f"✅ Фоновий сканер: Завершено ({report['total_tokens']} токенів)")
        except Exception as e:
            logger.error(f"❌ Фоновий сканер: {e}")
            scanning = False

        time.sleep(600)


@bot.message_handler(commands=['start'])
def start(message):
    logger.info(f"📩 /start від {message.chat.id}")
    text = """🤖 <b>Catapult Analyzer</b>

Сканую нові токени на <b>catapult.trade</b>

<b>Команди:</b>
/scan - Сканувати зараз
/report - Звіт
/patterns - Паттерни
/help - Допомога"""
    bot.reply_to(message, text)


@bot.message_handler(commands=['scan'])
def scan_now(message):
    global latest_report, scanning

    logger.info(f"📩 /scan від {message.chat.id}")

    if scanning:
        bot.reply_to(message, "⏳ Сканування вже йде...")
        return

    msg = bot.reply_to(message, "🔄 Сканую...")

    try:
        scanning = True
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        report = loop.run_until_complete(scan_catapult())
        loop.close()
        
        latest_report = report
        scanning = False

        if report['total_tokens'] == 0:
            text = "<b>СКАНУВАННЯ</b>\n\n❌ Токенів не знайдено"
        else:
            text = (f"<b>СКАНУВАННЯ</b>\n\n"
                    f"Токенів: <code>{report['total_tokens']}</code>\n"
                    f"Паттернів: <code>{report['total_patterns_found']}</code>\n\n"
                    f"<b>ТОП ПАТТЕРНИ:</b>\n")

            for pattern, count in report['top_patterns'][:5]:
                text += f"{pattern}: <code>{count}</code>\n"

        markup = InlineKeyboardMarkup()
        if report['total_tokens'] > 0:
            markup.add(InlineKeyboardButton(
                f"📋 {report['total_tokens']} токенів",
                callback_data="show_all_tokens"
            ))

        bot.edit_message_text(
            text,
            message.chat.id,
            msg.message_id,
            reply_markup=markup if report['total_tokens'] > 0 else None
        )
        logger.info("✅ /scan: Звіт відправлено")

    except Exception as e:
        logger.error(f"❌ /scan: {e}")
        bot.reply_to(message, f"❌ {str(e)[:100]}")
        scanning = False


@bot.callback_query_handler(func=lambda call: call.data == "show_all_tokens")
def show_all_tokens(call):
    global latest_report

    logger.info(f"📩 show_all_tokens від {call.from_user.id}")

    if not latest_report or not latest_report.get("tokens"):
        bot.answer_callback_query(call.id, "❌ Даних немає", show_alert=True)
        return

    tokens = latest_report["tokens"]
    bot.answer_callback_query(call.id, f"📤 {len(tokens)} токенів...")

    for idx, token in enumerate(tokens, 1):
        try:
            patterns_text = "❌ Паттернів немає"
            if token.get("patterns"):
                patterns_text = "<b>Паттерни:</b>\n" + "\n".join([f"{p}" for p in token["patterns"]])
            
            text = f"<b>#{idx}. {token.get('name', 'Token')}</b>\n\n{patterns_text}"
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("🔗 Catapult", url=token['url']))
            
            bot.send_message(call.message.chat.id, text, reply_markup=markup)
            time.sleep(0.2)
        except Exception as e:
            logger.error(f"❌ Токен #{idx}: {e}")


@bot.message_handler(commands=['report'])
def show_report(message):
    global latest_report

    logger.info(f"📩 /report від {message.chat.id}")

    if not latest_report:
        bot.reply_to(message, "❌ Даних немає. /scan спочатку")
        return

    text = f"""<b>ЗВІТ</b>

Токенів: <code>{latest_report['total_tokens']}</code>
Паттернів: <code>{latest_report['total_patterns_found']}</code>

<b>ТОП ПАТТЕРНИ:</b>
"""

    for idx, (pattern, count) in enumerate(latest_report['top_patterns'][:10], 1):
        text += f"{idx}. {pattern}: <code>{count}</code>\n"

    bot.reply_to(message, text)


@bot.message_handler(commands=['patterns'])
def show_patterns(message):
    global latest_report

    logger.info(f"📩 /patterns від {message.chat.id}")

    if not latest_report:
        bot.reply_to(message, "❌ Даних немає")
        return

    text = "<b>ПАТТЕРНИ</b>\n\n"

    for pattern, count in latest_report['top_patterns']:
        bar = "▪" * min(count, 15)
        text += f"{pattern}: {bar} ({count})\n"

    bot.reply_to(message, text)


@bot.message_handler(commands=['help'])
def help_cmd(message):
    logger.info(f"📩 /help від {message.chat.id}")
    text = """<b>ДОПОМОГА</b>

/scan - Сканувати
/report - Звіт
/patterns - Паттерни
/help - Допомога"""
    bot.reply_to(message, text)


@bot.message_handler(func=lambda m: True)
def default(message):
    bot.reply_to(message, "❓ /help")


if __name__ == "__main__":
    logger.info("🚀 Запускаю бота...")

    scanner_thread = threading.Thread(target=update_report, daemon=True)
    scanner_thread.start()
    logger.info("✅ Фоновий сканер запущений")
    logger.info("📱 Бот активний!")

    while True:
        try:
            bot.infinity_polling(timeout=30, long_polling_timeout=30, skip_pending=True)
        except Exception as e:
            logger.error(f"⚠️ {e}")
            time.sleep(5)
