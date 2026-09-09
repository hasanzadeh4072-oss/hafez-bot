import os
import json
import random
import time
import threading
import re
from collections import OrderedDict
from urllib.parse import urljoin

import requests
from flask import Flask, request


app = Flask(__name__)


# ==================================
# Configuration
# ==================================

TOKEN = os.environ.get("SOROUSH_TOKEN")

if not TOKEN:
    raise RuntimeError("SOROUSH_TOKEN environment variable is not set.")

API = f"https://api.splus.ir/bot{TOKEN}"

WEBHOOK_URL = "https://hafez-bot.onrender.com/webhook"
DATA_FILE = "HafezFilebot.json"
CHANNEL_URL = "https://splus.ir/@LIFE_M23"

MAX_MESSAGE_LENGTH = 4000

CONNECT_TIMEOUT = 5
READ_TIMEOUT = 15
REQUEST_TIMEOUT = (CONNECT_TIMEOUT, READ_TIMEOUT)


# ==================================
# Audio Cache
# ==================================

AUDIO_CACHE_MAX_ITEMS = 5
AUDIO_CACHE_MAX_BYTES = 50 * 1024 * 1024
AUDIO_NEGATIVE_CACHE_TTL = 10 * 60
AUDIO_URL_CACHE_TTL = 60 * 60

_AUDIO_CACHE = OrderedDict()
_AUDIO_CACHE_BYTES = 0
_AUDIO_CACHE_LOCK = threading.RLock()

_AUDIO_DOWNLOAD_LOCKS = {}
_AUDIO_DOWNLOAD_LOCKS_GUARD = threading.Lock()

_AUDIO_NEGATIVE_CACHE = {}
_AUDIO_NEGATIVE_LOCK = threading.Lock()

_AUDIO_URL_CACHE = {}
_AUDIO_URL_CACHE_LOCK = threading.Lock()

_AUDIO_RESOLVE_LOCKS = {}
_AUDIO_RESOLVE_LOCKS_GUARD = threading.Lock()

_THREAD_LOCAL = threading.local()


def get_session():
    session = getattr(_THREAD_LOCAL, "session", None)

    if session is None:
        session = requests.Session()

        session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 "
                "(compatible; HafezBot/1.0)"
            )
        })

        _THREAD_LOCAL.session = session

    return session


def get_audio_download_lock(audio_url):
    with _AUDIO_DOWNLOAD_LOCKS_GUARD:
        lock = _AUDIO_DOWNLOAD_LOCKS.get(audio_url)

        if lock is None:
            lock = threading.Lock()
            _AUDIO_DOWNLOAD_LOCKS[audio_url] = lock

        return lock


def get_audio_resolve_lock(source_url):
    with _AUDIO_RESOLVE_LOCKS_GUARD:
        lock = _AUDIO_RESOLVE_LOCKS.get(source_url)

        if lock is None:
            lock = threading.Lock()
            _AUDIO_RESOLVE_LOCKS[source_url] = lock

        return lock


def audio_cache_get(audio_url):
    global _AUDIO_CACHE_BYTES

    with _AUDIO_CACHE_LOCK:
        item = _AUDIO_CACHE.get(audio_url)

        if item is None:
            return None

        _AUDIO_CACHE.move_to_end(audio_url)

        return item


def audio_cache_put(audio_url, data):
    global _AUDIO_CACHE_BYTES

    if not data:
        return

    size = len(data)

    if size > AUDIO_CACHE_MAX_BYTES:
        return

    with _AUDIO_CACHE_LOCK:
        old = _AUDIO_CACHE.pop(audio_url, None)

        if old is not None:
            _AUDIO_CACHE_BYTES -= len(old)

        _AUDIO_CACHE[audio_url] = data
        _AUDIO_CACHE_BYTES += size

        while (
            len(_AUDIO_CACHE) > AUDIO_CACHE_MAX_ITEMS
            or _AUDIO_CACHE_BYTES > AUDIO_CACHE_MAX_BYTES
        ):
            _, removed = _AUDIO_CACHE.popitem(last=False)
            _AUDIO_CACHE_BYTES -= len(removed)


def negative_cache_get(audio_url):
    now = time.time()

    with _AUDIO_NEGATIVE_LOCK:
        expires_at = _AUDIO_NEGATIVE_CACHE.get(audio_url)

        if expires_at is None:
            return False

        if expires_at <= now:
            _AUDIO_NEGATIVE_CACHE.pop(audio_url, None)
            return False

        return True


def negative_cache_put(audio_url):
    with _AUDIO_NEGATIVE_LOCK:
        _AUDIO_NEGATIVE_CACHE[audio_url] = (
            time.time() + AUDIO_NEGATIVE_CACHE_TTL
        )


def audio_url_cache_get(source_url):
    now = time.time()

    with _AUDIO_URL_CACHE_LOCK:
        item = _AUDIO_URL_CACHE.get(source_url)

        if item is None:
            return None

        audio_url, expires_at = item

        if expires_at <= now:
            _AUDIO_URL_CACHE.pop(source_url, None)
            return None

        return audio_url


def audio_url_cache_put(source_url, audio_url):
    with _AUDIO_URL_CACHE_LOCK:
        _AUDIO_URL_CACHE[source_url] = (
            audio_url,
            time.time() + AUDIO_URL_CACHE_TTL
        )


# ==================================
# Keyboards
# ==================================

MAIN_KEYBOARD = {
    "keyboard": [
        [
            {
                "text": "📜 فال حافظ"
            }
        ]
    ],
    "resize_keyboard": True,
    "one_time_keyboard": False,
    "is_persistent": True
}


REPEAT_FORTUNE_KEYBOARD = {
    "keyboard": [
        [
            {
                "text": "🌿 یک فال دیگر"
            }
        ]
    ],
    "resize_keyboard": True,
    "one_time_keyboard": False,
    "is_persistent": True
}


# ==================================
# Global Data
# ==================================

HAZALS = []


# ==================================
# Chat Control Message State
# ==================================

CHAT_CONTROL_MESSAGES = {}
CHAT_CONTROL_LOCK = threading.Lock()


def set_chat_control_message(chat_id, message_id):
    with CHAT_CONTROL_LOCK:
        CHAT_CONTROL_MESSAGES[chat_id] = message_id


def get_chat_control_message(chat_id):
    with CHAT_CONTROL_LOCK:
        return CHAT_CONTROL_MESSAGES.get(chat_id)


def remove_chat_control_message(chat_id):
    with CHAT_CONTROL_LOCK:
        return CHAT_CONTROL_MESSAGES.pop(chat_id, None)


def clear_chat_control_message(chat_id, message_id=None):
    with CHAT_CONTROL_LOCK:
        current = CHAT_CONTROL_MESSAGES.get(chat_id)

        if message_id is None or current == message_id:
            CHAT_CONTROL_MESSAGES.pop(chat_id, None)


# ==================================
# Data Loading
# ==================================

def load_data():
    global HAZALS

    if not os.path.exists(DATA_FILE):
        raise FileNotFoundError(
            f"Data file not found: {DATA_FILE}"
        )

    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError(
            "HafezFilebot.json must contain a top-level list."
        )

    loaded = []

    for item in data:
        if not isinstance(item, dict):
            continue

        for record_id, record in item.items():
            if not isinstance(record, dict):
                continue

            poem = record.get("Poem")

            if not isinstance(poem, str):
                continue

            poem = poem.strip()

            if not poem:
                continue

            title = record.get("Title")

            if not isinstance(title, str):
                title = ""

            source = record.get("Source")

            if not isinstance(source, str):
                source = ""

            audio = record.get("Audio")

            if not isinstance(audio, str):
                audio = None

            author = record.get("Author")

            if not isinstance(author, str) or not author.strip():
                author = "حافظ"

            book = record.get("Book")

            if not isinstance(book, str) or not book.strip():
                book = "غزلیات حافظ"

            loaded.append({
                "record_id": str(record_id),
                "author": author,
                "book": book,
                "poem": poem,
                "source": source,
                "title": title,
                "audio": audio,
            })

    HAZALS = loaded

    audio_count = sum(
        1
        for record in HAZALS
        if record.get("audio")
    )

    print(
        f"[DATA] Total ghazals: {len(HAZALS)} | "
        f"Audio present: {audio_count} | "
        f"Audio missing: {len(HAZALS) - audio_count}"
    )


# ==================================
# Soroush API
# ==================================

def splus_request(method, data=None, files=None):
    url = f"{API}/{method}"

    start = time.perf_counter()

    try:
        print(
            f"[API] START {method}"
        )

        response = get_session().post(
            url,
            data=data,
            files=files,
            timeout=REQUEST_TIMEOUT
        )

        elapsed = time.perf_counter() - start

        print(
            f"[API] END {method} "
            f"status={response.status_code} "
            f"time={elapsed:.3f}s"
        )

        try:
            return response.json()
        except Exception:
            return None

    except Exception as exc:
        elapsed = time.perf_counter() - start

        print(
            f"[API] ERROR {method} "
            f"time={elapsed:.3f}s "
            f"error={exc}"
        )

        return None


# ==================================
# Messages
# ==================================

def delete_message(chat_id, message_id):
    if not message_id:
        return

    splus_request(
        "deleteMessage",
        data={
            "chat_id": chat_id,
            "message_id": message_id
        }
    )


def delete_control_message(chat_id):
    message_id = remove_chat_control_message(chat_id)

    if message_id:
        delete_message(chat_id, message_id)


def send_message(chat_id, text, reply_markup=None):
    data = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": "true"
    }

    if reply_markup is not None:
        data["reply_markup"] = json.dumps(
            reply_markup,
            ensure_ascii=False
        )

    return splus_request(
        "sendMessage",
        data=data
    )


def split_message(text):
    if len(text) <= MAX_MESSAGE_LENGTH:
        return [text]

    chunks = []
    remaining = text

    while len(remaining) > MAX_MESSAGE_LENGTH:
        cut = remaining.rfind(
            "\n",
            0,
            MAX_MESSAGE_LENGTH
        )

        if cut <= 0:
            cut = remaining.rfind(
                " ",
                0,
                MAX_MESSAGE_LENGTH
            )

        if cut <= 0:
            cut = MAX_MESSAGE_LENGTH

        chunks.append(
            remaining[:cut].strip()
        )

        remaining = remaining[cut:].strip()

    if remaining:
        chunks.append(remaining)

    return chunks


# ==================================
# Ghazal Number
# ==================================

def get_ghazal_number(record):
    source = record.get("source", "")

    match = re.search(
        r"/sh(\d+)",
        source
    )

    if match:
        return match.group(1)

    title = record.get("title", "")

    match = re.search(
        r"\d+",
        title
    )

    if match:
        return match.group(0)

    return record.get("record_id", "")


# ==================================
# Poem Cleaning
# ==================================

def clean_poem(poem):
    poem = poem.replace("\r\n", "\n")
    poem = poem.replace("\r", "\n")

    return poem.strip()


# ==================================
# Fortune Formatting
# ==================================

def format_fortune(record):
    number = get_ghazal_number(record)
    poem = clean_poem(record["poem"])

    return (
        "فال حافظ\n"
        f"شماره غزل {number}\n\n"
        f"{poem}\n\n"
        "منبع گنجور\n"
        f"{record.get('source', '')}\n"
        f"{CHANNEL_URL} 🌱"
    )


def send_fortune(chat_id, record):
    text = format_fortune(record)
    chunks = split_message(text)

    result = None

    for index, chunk in enumerate(chunks):
        reply_markup = (
            REPEAT_FORTUNE_KEYBOARD
            if index == len(chunks) - 1
            else None
        )

        result = send_message(
            chat_id,
            chunk,
            reply_markup=reply_markup
        )

    return result


# ==================================
# Audio URL Extraction
# ==================================

def extract_audio_urls_from_page(html, source_url):
    urls = []

    absolute_pattern = re.compile(
        r'https?://[^"\']+\.(?:ogg|mp3)(?:\?[^"\']*)?',
        re.IGNORECASE
    )

    for match in absolute_pattern.findall(html):
        urls.append(match)

    relative_pattern = re.compile(
        r'["\']([^"\']+\.(?:ogg|mp3)(?:\?[^"\']*)?)["\']',
        re.IGNORECASE
    )

    for match in relative_pattern.findall(html):
        urls.append(
            urljoin(source_url, match)
        )

    preferred = [
        url
        for url in urls
        if "i.ganjoor.net" in url
    ]

    if preferred:
        return list(dict.fromkeys(preferred))

    return list(dict.fromkeys(urls))


def resolve_audio_from_source(source_url):
    if not source_url:
        return None

    cached = audio_url_cache_get(source_url)

    if cached:
        print(
            f"[AUDIO] Source cache HIT: {source_url}"
        )
        return cached

    lock = get_audio_resolve_lock(source_url)

    with lock:
        cached = audio_url_cache_get(source_url)

        if cached:
            return cached

        print(
            f"[AUDIO] Resolving from source: {source_url}"
        )

        try:
            response = get_session().get(
                source_url,
                timeout=REQUEST_TIMEOUT
            )

            response.raise_for_status()

            candidates = extract_audio_urls_from_page(
                response.text,
                source_url
            )

            if not candidates:
                print(
                    "[AUDIO] No audio candidate found."
                )
                return None

            ogg_candidates = [
                url
                for url in candidates
                if ".ogg" in url.lower()
            ]

            selected = (
                ogg_candidates[0]
                if ogg_candidates
                else candidates[0]
            )

            audio_url_cache_put(
                source_url,
                selected
            )

            print(
                f"[AUDIO] Resolved URL: {selected}"
            )

            return selected

        except Exception as exc:
            print(
                f"[AUDIO] Resolve error: {exc}"
            )
            return None


def check_audio_url(audio_url):
    if not audio_url:
        return False

    try:
        response = get_session().get(
            audio_url,
            stream=True,
            timeout=REQUEST_TIMEOUT
        )

        status = response.status_code

        response.close()

        return status == 200

    except Exception as exc:
        print(
            f"[AUDIO] URL check error: {exc}"
        )
        return False


def resolve_final_audio_url(record):
    audio_url = record.get("audio")

    if isinstance(audio_url, str) and audio_url.strip():
        audio_url = audio_url.strip()

        print(
            f"[AUDIO] JSON Audio found: {audio_url}"
        )

        if audio_cache_get(audio_url) is not None:
            return audio_url

        if negative_cache_get(audio_url):
            print(
                "[AUDIO] JSON audio is negative-cached."
            )
        else:
            if check_audio_url(audio_url):
                return audio_url

            negative_cache_put(audio_url)

            print(
                "[AUDIO] JSON audio invalid; "
                "falling back to source."
            )

    source_url = record.get("source")

    if not source_url:
        return None

    return resolve_audio_from_source(source_url)


def download_audio(audio_url):
    cached = audio_cache_get(audio_url)

    if cached is not None:
        print(
            "[AUDIO] Download cache HIT."
        )
        return cached

    if negative_cache_get(audio_url):
        print(
            "[AUDIO] Negative cache HIT."
        )
        return None

    lock = get_audio_download_lock(audio_url)

    with lock:
        cached = audio_cache_get(audio_url)

        if cached is not None:
            return cached

        if negative_cache_get(audio_url):
            return None

        print(
            f"[AUDIO] Downloading: {audio_url}"
        )

        try:
            response = get_session().get(
                audio_url,
                timeout=REQUEST_TIMEOUT
            )

            if response.status_code == 404:
                negative_cache_put(audio_url)

                print(
                    "[AUDIO] 404; negative cache stored."
                )

                return None

            response.raise_for_status()

            data = response.content

            if not data:
                return None

            audio_cache_put(
                audio_url,
                data
            )

            print(
                f"[AUDIO] Downloaded {len(data)} bytes."
            )

            return data

        except Exception as exc:
            print(
                f"[AUDIO] Download error: {exc}"
            )
            return None


# ==================================
# Audio Metadata
# ==================================

def get_audio_title(record):
    number = get_ghazal_number(record)

    return f"غزل شمارهٔ {number}"


def get_audio_performer(record):
    return "حافظ"


def send_audio(chat_id, record):
    audio_url = resolve_final_audio_url(record)

    if not audio_url:
        print(
            "[AUDIO] No audio URL available."
        )
        return None

    audio_data = download_audio(audio_url)

    if not audio_data:
        print(
            "[AUDIO] Audio download failed."
        )
        return None

    lower_url = audio_url.lower()

    if ".mp3" in lower_url:
        extension = "mp3"
        mime_type = "audio/mpeg"
    else:
        extension = "ogg"
        mime_type = "audio/ogg"

    ghazal_number = get_ghazal_number(record)

    # ==================================
    # Official file name
    # ==================================

    filename = (
        f"غزل {ghazal_number} - حافظ - گنجور."
        f"{extension}"
    )

    # ==================================
    # Audio metadata
    # ==================================

    audio_title = get_audio_title(record)
    audio_performer = get_audio_performer(record)

    print(
        f"[AUDIO] Filename: {filename}"
    )

    print(
        f"[AUDIO] Title: {audio_title}"
    )

    print(
        f"[AUDIO] Performer: {audio_performer}"
    )

    files = {
        "voice": (
            filename,
            audio_data,
            mime_type
        )
    }

    return splus_request(
        "sendVoice",
        data={
            "chat_id": chat_id,
            "performer": audio_performer,
            "title": audio_title,
        },
        files=files
    )


# ==================================
# Fortune Processing
# ==================================

def process_fortune(chat_id, fortune_message_id):
    start = time.perf_counter()

    print(
        f"[FORTUNE] START chat={chat_id}"
    )

    try:
        if not HAZALS:
            print(
                "[FORTUNE] HAZALS is empty."
            )

            send_message(
                chat_id,
                "متأسفانه مجموعه غزل‌های حافظ در دسترس نیست.",
                reply_markup=MAIN_KEYBOARD
            )

            return

        record = random.choice(HAZALS)

        print(
            f"[FORTUNE] Selected "
            f"record_id={record.get('record_id')} "
            f"number={get_ghazal_number(record)}"
        )

        result = send_fortune(
            chat_id,
            record
        )

        if result:
            old_control = get_chat_control_message(chat_id)

            if old_control:
                delete_message(
                    chat_id,
                    old_control
                )

            delete_message(
                chat_id,
                fortune_message_id
            )

            clear_chat_control_message(
                chat_id
            )

        send_audio(
            chat_id,
            record
        )

    except Exception as exc:
        print(
            f"[FORTUNE] ERROR: {exc}"
        )

    finally:
        elapsed = time.perf_counter() - start

        print(
            f"[FORTUNE] END "
            f"chat={chat_id} "
            f"time={elapsed:.3f}s"
        )


# ==================================
# Webhook
# ==================================

@app.route("/webhook", methods=["POST"])
def webhook():
    update = request.get_json(
        silent=True
    ) or {}

    message = update.get("message") or {}

    chat = message.get("chat") or {}
    chat_id = chat.get("id")

    if chat_id is None:
        return "OK"

    text = message.get("text")

    message_id = message.get("message_id")

    if not isinstance(text, str):
        return "OK"

    text = text.strip()

    print(
        f"[WEBHOOK] chat={chat_id} "
        f"message_id={message_id} "
        f"text={text!r}"
    )

    # ------------------------------
    # /start
    # ------------------------------

    if text == "/start":
        sent = send_message(
            chat_id,
            (
                "🌿 به بات فال حافظ خوش آمدید.\n\n"
                "✨ ابتدا نیت کنید و سپس دکمه "
                "«📜 فال حافظ» را بزنید."
            ),
            reply_markup=MAIN_KEYBOARD
        )

        delete_message(
            chat_id,
            message_id
        )

        if isinstance(sent, dict):
            sent_message = sent.get("result")

            if isinstance(sent_message, dict):
                sent_message_id = sent_message.get(
                    "message_id"
                )

                if sent_message_id:
                    set_chat_control_message(
                        chat_id,
                        sent_message_id
                    )

        return "OK"

    # ------------------------------
    # Repeat fortune
    # ------------------------------

    if text in (
        "یک فال دیگر",
        "🌿 یک فال دیگر"
    ):
        delete_message(
            chat_id,
            message_id
        )

        sent = send_message(
            chat_id,
            (
                "✨ دوباره نیت کنید و سپس دکمه "
                "«📜 فال حافظ» را بزنید."
            ),
            reply_markup=MAIN_KEYBOARD
        )

        if isinstance(sent, dict):
            sent_message = sent.get("result")

            if isinstance(sent_message, dict):
                sent_message_id = sent_message.get(
                    "message_id"
                )

                if sent_message_id:
                    set_chat_control_message(
                        chat_id,
                        sent_message_id
                    )

        return "OK"

    # ------------------------------
    # Fortune
    # ------------------------------

    if text in (
        "فال حافظ",
        "📜 فال حافظ"
    ):
        fortune_message_id = message_id

        thread = threading.Thread(
            target=process_fortune,
            args=(
                chat_id,
                fortune_message_id
            ),
            daemon=True,
            name=f"fortune-{chat_id}"
        )

        thread.start()

        return "OK"

    return "OK"


# ==================================
# Health
# ==================================

@app.route("/", methods=["GET", "HEAD"])
def home():
    return "Hafez Bot is running."


# ==================================
# Webhook Setup
# ==================================

def set_webhook():
    result = splus_request(
        "setWebhook",
        data={
            "url": WEBHOOK_URL
        }
    )

    print(
        f"[WEBHOOK] setWebhook result: {result}"
    )


# ==================================
# Startup
# ==================================

print("[STARTUP] Starting Hafez Bot...")

try:
    load_data()

except Exception as exc:
    print(
        f"[STARTUP] Data load error: {exc}"
    )

print("[STARTUP] Initialization complete.")


if __name__ == "__main__":
    set_webhook()

    port = int(
        os.environ.get(
            "PORT",
            10000
        )
    )

    app.run(
        host="0.0.0.0",
        port=port
    )



