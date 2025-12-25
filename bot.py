import telebot
from telebot import types
import subprocess
import os
import threading
import signal

BOT_TOKEN = "7989206801:AAF5U9MvXnR2QNMB9uvc1o81-yWjIpFM1KM"
ADMIN_IDS = [8432356301, 7375893740]  # Список админов

WORK_DIR = "/root/checker"
NUMBERS_FILE = f"{WORK_DIR}/numbers.txt"
PROXIES_FILE = f"{WORK_DIR}/proxies.txt"
VALID_FILE = f"{WORK_DIR}/valid.txt"
INVALID_FILE = f"{WORK_DIR}/invalid.txt"

bot = telebot.TeleBot(BOT_TOKEN)

checker_process = None
is_running = False


def get_main_keyboard():
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.row("▶️ Запустить", "⏹ Остановить")
    keyboard.row("📊 Статус", "📁 Статистика")
    keyboard.row("📤 Загрузить базу", "📤 Загрузить прокси")
    keyboard.row("📥 Получить валид", "📥 Получить инвалид")
    return keyboard


def is_admin(message):
    return message.from_user.id in ADMIN_IDS


def count_lines(filepath):
    try:
        with open(filepath, 'r') as f:
            return sum(1 for line in f if line.strip())
    except:
        return 0


@bot.message_handler(commands=['start'])
def start(message):
    if not is_admin(message):
        return
    bot.send_message(
        message.chat.id,
        "🤖 *Mokka Checker Bot*\n\nВыберите действие:",
        parse_mode="Markdown",
        reply_markup=get_main_keyboard()
    )


@bot.message_handler(func=lambda m: m.text == "▶️ Запустить")
def start_checker(message):
    global checker_process, is_running
    if not is_admin(message):
        return

    if is_running:
        bot.send_message(message.chat.id, "⚠️ Чекер уже запущен!")
        return

    numbers_count = count_lines(NUMBERS_FILE)
    proxies_count = count_lines(PROXIES_FILE)

    if numbers_count == 0:
        bot.send_message(message.chat.id, "❌ Файл numbers.txt пуст!")
        return
    if proxies_count == 0:
        bot.send_message(message.chat.id, "❌ Файл proxies.txt пуст!")
        return

    def run_checker():
        global checker_process, is_running
        is_running = True
        checker_process = subprocess.Popen(
            ["python3", "main.py"],
            cwd=WORK_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT
        )
        checker_process.wait()
        is_running = False
        bot.send_message(message.chat.id, "✅ Чекер завершил работу!")

    thread = threading.Thread(target=run_checker)
    thread.start()

    bot.send_message(
        message.chat.id,
        f"✅ Чекер запущен!\n\n📱 Номеров: {numbers_count}\n🌐 Прокси: {proxies_count}"
    )


@bot.message_handler(func=lambda m: m.text == "⏹ Остановить")
def stop_checker(message):
    global checker_process, is_running
    if not is_admin(message):
        return

    if not is_running:
        bot.send_message(message.chat.id, "⚠️ Чекер не запущен!")
        return

    if checker_process:
        os.kill(checker_process.pid, signal.SIGTERM)
        is_running = False
        bot.send_message(message.chat.id, "⏹ Чекер остановлен!")


@bot.message_handler(func=lambda m: m.text == "📊 Статус")
def status(message):
    if not is_admin(message):
        return

    status_text = "🟢 Работает" if is_running else "🔴 Остановлен"
    bot.send_message(message.chat.id, f"📊 Статус: {status_text}")


@bot.message_handler(func=lambda m: m.text == "📁 Статистика")
def stats(message):
    if not is_admin(message):
        return

    numbers = count_lines(NUMBERS_FILE)
    proxies = count_lines(PROXIES_FILE)
    valid = count_lines(VALID_FILE)
    invalid = count_lines(INVALID_FILE)

    text = f"""📁 *Статистика*

📱 Номеров в базе: {numbers}
🌐 Прокси: {proxies}

✅ Валид: {valid}
❌ Инвалид: {invalid}
📊 Всего проверено: {valid + invalid}"""

    bot.send_message(message.chat.id, text, parse_mode="Markdown")


@bot.message_handler(func=lambda m: m.text == "📤 Загрузить базу")
def upload_numbers(message):
    if not is_admin(message):
        return
    bot.send_message(message.chat.id, "📤 Отправьте файл numbers.txt с номерами")
    bot.register_next_step_handler(message, process_numbers_file)


@bot.message_handler(func=lambda m: m.text == "📤 Загрузить прокси")
def upload_proxies(message):
    if not is_admin(message):
        return
    bot.send_message(message.chat.id, "📤 Отправьте файл proxies.txt с прокси")
    bot.register_next_step_handler(message, process_proxies_file)


def process_numbers_file(message):
    if not is_admin(message):
        return
    if not message.document:
        bot.send_message(message.chat.id, "❌ Отправьте файл!", reply_markup=get_main_keyboard())
        return

    try:
        file_info = bot.get_file(message.document.file_id)
        downloaded = bot.download_file(file_info.file_path)
        with open(NUMBERS_FILE, 'wb') as f:
            f.write(downloaded)
        count = count_lines(NUMBERS_FILE)
        bot.send_message(
            message.chat.id,
            f"✅ База загружена!\n📱 Номеров: {count}",
            reply_markup=get_main_keyboard()
        )
    except Exception as e:
        bot.send_message(
            message.chat.id,
            f"❌ Ошибка: {e}",
            reply_markup=get_main_keyboard()
        )


def process_proxies_file(message):
    if not is_admin(message):
        return
    if not message.document:
        bot.send_message(message.chat.id, "❌ Отправьте файл!", reply_markup=get_main_keyboard())
        return

    try:
        file_info = bot.get_file(message.document.file_id)
        downloaded = bot.download_file(file_info.file_path)
        with open(PROXIES_FILE, 'wb') as f:
            f.write(downloaded)
        count = count_lines(PROXIES_FILE)
        bot.send_message(
            message.chat.id,
            f"✅ Прокси загружены!\n🌐 Количество: {count}",
            reply_markup=get_main_keyboard()
        )
    except Exception as e:
        bot.send_message(
            message.chat.id,
            f"❌ Ошибка: {e}",
            reply_markup=get_main_keyboard()
        )


@bot.message_handler(func=lambda m: m.text == "📥 Получить валид")
def get_valid(message):
    if not is_admin(message):
        return

    if not os.path.exists(VALID_FILE) or count_lines(VALID_FILE) == 0:
        bot.send_message(message.chat.id, "❌ Файл valid.txt пуст!")
        return

    with open(VALID_FILE, 'rb') as f:
        bot.send_document(message.chat.id, f, caption="✅ Валидные номера")


@bot.message_handler(func=lambda m: m.text == "📥 Получить инвалид")
def get_invalid(message):
    if not is_admin(message):
        return

    if not os.path.exists(INVALID_FILE) or count_lines(INVALID_FILE) == 0:
        bot.send_message(message.chat.id, "❌ Файл invalid.txt пуст!")
        return

    with open(INVALID_FILE, 'rb') as f:
        bot.send_document(message.chat.id, f, caption="❌ Невалидные номера")


if __name__ == "__main__":
    print("🤖 Бот запущен...")
    bot.infinity_polling()
