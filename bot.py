import telebot
from telebot import types
import subprocess
import os
import threading
import signal
import time

BOT_TOKEN = "7989206801:AAF5U9MvXnR2QNMB9uvc1o81-yWjIpFM1KM"
ADMIN_IDS = [8432356301, 7375893740]

WORK_DIR = "/root/checker"
NUMBERS_FILE = f"{WORK_DIR}/numbers.txt"
PROXIES_FILE = f"{WORK_DIR}/proxies.txt"
VALID_FILE = f"{WORK_DIR}/valid.txt"
INVALID_FILE = f"{WORK_DIR}/invalid.txt"

bot = telebot.TeleBot(BOT_TOKEN)

checker_process = None
is_running = False

# Кэш для быстрой статистики
stats_cache = {
    'numbers': 0,
    'proxies': 0,
    'valid': 0,
    'invalid': 0,
    'last_update': 0
}


def get_main_keyboard():
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.row("▶️ Запустить", "⏹ Остановить")
    keyboard.row("📊 Статус", "📁 Статистика")
    keyboard.row("📤 Загрузить базу", "📤 Загрузить прокси")
    keyboard.row("📥 Получить валид", "📥 Получить инвалид")
    return keyboard


def is_admin(message):
    return message.from_user.id in ADMIN_IDS


def count_lines_fast(filepath):
    """Быстрый подсчёт через wc -l"""
    try:
        result = subprocess.run(['wc', '-l', filepath], capture_output=True, text=True, timeout=5)
        return int(result.stdout.split()[0])
    except:
        return 0


def update_stats_cache():
    """Обновляет кэш статистики в фоне"""
    global stats_cache
    stats_cache['numbers'] = count_lines_fast(NUMBERS_FILE)
    stats_cache['proxies'] = count_lines_fast(PROXIES_FILE)
    stats_cache['valid'] = count_lines_fast(VALID_FILE)
    stats_cache['invalid'] = count_lines_fast(INVALID_FILE)
    stats_cache['last_update'] = time.time()


def get_stats_async(callback):
    """Получает статистику асинхронно"""
    def worker():
        update_stats_cache()
        callback(stats_cache)
    thread = threading.Thread(target=worker)
    thread.start()


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

    # Быстрая проверка наличия файлов
    if not os.path.exists(NUMBERS_FILE) or os.path.getsize(NUMBERS_FILE) == 0:
        bot.send_message(message.chat.id, "❌ Файл numbers.txt пуст!")
        return
    if not os.path.exists(PROXIES_FILE) or os.path.getsize(PROXIES_FILE) == 0:
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

    bot.send_message(message.chat.id, "✅ Чекер запущен!")


@bot.message_handler(func=lambda m: m.text == "⏹ Остановить")
def stop_checker(message):
    global checker_process, is_running
    if not is_admin(message):
        return

    if not is_running:
        bot.send_message(message.chat.id, "⚠️ Чекер не запущен!")
        return

    try:
        # Убиваем main.py и все дочерние процессы
        subprocess.run(['pkill', '-f', 'python3 main.py'], timeout=5)
        subprocess.run(['pkill', '-f', 'camoufox'], timeout=5)
    except:
        pass

    if checker_process:
        try:
            os.kill(checker_process.pid, signal.SIGTERM)
        except:
            pass

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

    # Отправляем сообщение сразу
    msg = bot.send_message(message.chat.id, "⏳ Загрузка статистики...")

    def send_stats(s):
        text = f"""📁 *Статистика*

📱 Номеров в базе: {s['numbers']:,}
🌐 Прокси: {s['proxies']:,}

✅ Валид: {s['valid']:,}
❌ Инвалид: {s['invalid']:,}
📊 Всего проверено: {s['valid'] + s['invalid']:,}"""

        bot.edit_message_text(text, message.chat.id, msg.message_id, parse_mode="Markdown")

    get_stats_async(send_stats)


@bot.message_handler(func=lambda m: m.text == "📤 Загрузить базу")
def upload_numbers(message):
    if not is_admin(message):
        return
    bot.send_message(message.chat.id, "📤 Отправьте файл с номерами")
    bot.register_next_step_handler(message, process_numbers_file)


@bot.message_handler(func=lambda m: m.text == "📤 Загрузить прокси")
def upload_proxies(message):
    if not is_admin(message):
        return
    bot.send_message(message.chat.id, "📤 Отправьте файл с прокси")
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
        count = count_lines_fast(NUMBERS_FILE)
        bot.send_message(
            message.chat.id,
            f"✅ База загружена!\n📱 Номеров: {count:,}",
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
        count = count_lines_fast(PROXIES_FILE)
        bot.send_message(
            message.chat.id,
            f"✅ Прокси загружены!\n🌐 Количество: {count:,}",
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

    if not os.path.exists(VALID_FILE) or os.path.getsize(VALID_FILE) == 0:
        bot.send_message(message.chat.id, "❌ Файл valid.txt пуст!")
        return

    with open(VALID_FILE, 'rb') as f:
        bot.send_document(message.chat.id, f, caption="✅ Валидные номера")


@bot.message_handler(func=lambda m: m.text == "📥 Получить инвалид")
def get_invalid(message):
    if not is_admin(message):
        return

    if not os.path.exists(INVALID_FILE) or os.path.getsize(INVALID_FILE) == 0:
        bot.send_message(message.chat.id, "❌ Файл invalid.txt пуст!")
        return

    with open(INVALID_FILE, 'rb') as f:
        bot.send_document(message.chat.id, f, caption="❌ Невалидные номера")


if __name__ == "__main__":
    print("🤖 Бот запущен...")
    bot.infinity_polling()
