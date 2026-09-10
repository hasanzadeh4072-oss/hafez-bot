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


# ==================================
# HTTP Session
# ==================================

def get_session():
    session = getattr(_THREAD_LOCAL, "session", None)

    if session is None:
        session = requests.Session()
        session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 "
                "(compatible; HafezBot/1.0)"
            )
        )
        _THREAD_LOCAL.session = session

    return session


# ==================================
# Lock Helpers
# ==================================

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


# ==================================
# Audio Byte Cache
# ==================================

def audio_cache_get(audio_url):
    global _AUDIO_CACHE_BYTES

    with _AUDIO_CACHE_LOCK:
        data = _AUDIO_CACHE.get(audio_url)

        if data is None:
            return None

        _AUDIO_CACHE.move_to_end(audio_url)
        return data


def audio_cache_put(audio_url, data):
    global _AUDIO_CACHE_BYTES

    if not data:
        return

    data_size = len(data)

    if data_size > AUDIO_CACHE_MAX_BYTES:
        return

    with _AUDIO_CACHE_LOCK:

        old = _AUDIO_CACHE.pop(audio_url, None)

        if old is not None:
            _AUDIO_CACHE_BYTES -= len(old)

        _AUDIO_CACHE[audio_url] = data
        _AUDIO_CACHE_BYTES += data_size

        while (
            len(_AUDIO_CACHE) > AUDIO_CACHE_MAX_ITEMS
            or _AUDIO_CACHE_BYTES > AUDIO_CACHE_MAX_BYTES
        ):
            _, removed = _AUDIO_CACHE.popitem(last=False)
            _AUDIO_CACHE_BYTES -= len(removed)


# ==================================
# Negative Cache
# ==================================

def negative_cache_get(audio_url):
    now = time.time()

    with _AUDIO_NEGATIVE_LOCK:
        timestamp = _AUDIO_NEGATIVE_CACHE.get(audio_url)

        if timestamp is None:
            return False

        if now - timestamp < AUDIO_NEGATIVE_CACHE_TTL:
            return True

        _AUDIO_NEGATIVE_CACHE.pop(audio_url, None)
        return False


def negative_cache_put(audio_url):
    with _AUDIO_NEGATIVE_LOCK:
        _AUDIO_NEGATIVE_CACHE[audio_url] = time.time()


# ==================================
# Audio URL Cache
# ==================================

def audio_url_cache_get(source_url):
    now = time.time()

    with _AUDIO_URL_CACHE_LOCK:
        item = _AUDIO_URL_CACHE.get(source_url)

        if item is None:
            return None

        audio_url, timestamp = item

        if now - timestamp < AUDIO_URL_CACHE_TTL:
            return audio_url

        _AUDIO_URL_CACHE.pop(source_url, None)
        return None


def audio_url_cache_put(source_url, audio_url):
    with _AUDIO_URL_CACHE_LOCK:
        _AUDIO_URL_CACHE[source_url] = (
            audio_url,
            time.time()
        )


# ==================================
# Keyboards
# ==================================

MAIN_KEYBOARD = {
    "keyboard": [
        [
            {"text": "📜 فال حافظ"}
        ]
    ],
    "resize_keyboard": True,
    "one_time_keyboard": False
}


REPEAT_KEYBOARD = {
    "keyboard": [
        [
            {"text": "🌿 یک فال دیگر"}
        ]
    ],
    "resize_keyboard": True,
    "one_time_keyboard": False
}


# ==================================
# Data
# ==================================

HAZALS = []


def load_data():
    global HAZALS

    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError("HafezFilebot.json must contain a list.")

    records = []

    for record_id, item in enumerate(data, start=1):

        if not isinstance(item, dict):
            continue

        poem = str(item.get("Poem", "")).strip()

        if not poem:
            continue

        author = str(
            item.get("Author", "حافظ")
        ).strip() or "حافظ"

        book = str(
            item.get("Book", "غزلیات حافظ")
        ).strip() or "غزلیات حافظ"

        source = str(
            item.get("Source", "")
        ).strip()

        title = str(
            item.get("Title", "")
        ).strip()

        audio = str(
            item.get("Audio", "")
        ).strip()

        records.append({
            "record_id": str(record_id),
            "author": author,
            "book": book,
            "poem": poem,
            "source": source,
            "title": title,
            "audio": audio
        })

    HAZALS = records

    audio_count = sum(
        1 for item in HAZALS
        if item.get("audio") or item.get("source")
    )

    print(
        f"[DATA] Loaded {len(HAZALS)} ghazals "
        f"with {audio_count} audio entries."
    )


# ==================================
# Soroush Plus API
# ==================================

def splus_request(method, data=None, files=None):

    url = f"{API}/{method}"
    start_time = time.time()

    try:
        print(f"[API] START {method}")

        response = get_session().post(
            url,
            data=data,
            files=files,
            timeout=REQUEST_TIMEOUT
        )

        elapsed = time.time() - start_time

        print(
            f"[API] END {method} "
            f"status={response.status_code} "
            f"time={elapsed:.3f}s"
        )

        try:
            return response.json()

        except Exception:
            print(
                "[API] Non-JSON response:",
                response.text[:500]
            )

            return {
                "ok": response.ok,
                "status_code": response.status_code,
                "text": response.text
            }

    except Exception as e:

        elapsed = time.time() - start_time

        print(
            f"[API] ERROR {method} "
            f"time={elapsed:.3f}s "
            f"error={e}"
        )

        return None


# ==================================
# Message Helpers
# ==================================

def delete_message(chat_id, message_id):

    if not message_id:
        return None

    return splus_request(
        "deleteMessage",
        data={
            "chat_id": chat_id,
            "message_id": message_id
        }
    )


def send_message(
    chat_id,
    text,
    reply_markup=None
):

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


def split_message(text, max_length=MAX_MESSAGE_LENGTH):

    if len(text) <= max_length:
        return [text]

    chunks = []
    remaining = text

    while len(remaining) > max_length:

        cut = remaining.rfind(
            "\n",
            0,
            max_length
        )

        if cut < max_length // 2:
            cut = remaining.rfind(
                " ",
                0,
                max_length
            )

        if cut < max_length // 2:
            cut = max_length

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

    source = str(
        record.get("source", "")
    )

    match = re.search(
        r"/sh(\d+)",
        source,
        re.IGNORECASE
    )

    if match:
        return match.group(1)

    title = str(
        record.get("title", "")
    )

    match = re.search(
        r"\d+",
        title
    )

    if match:
        return match.group(0)

    record_id = str(
        record.get("record_id", "")
    )

    match = re.search(
        r"\d+",
        record_id
    )

    if match:
        return match.group(0)

    return record_id or "؟"


# ==================================
# Poem Formatting
# ==================================

def clean_poem(poem):

    poem = str(poem)

    poem = poem.replace(
        "\r\n",
        "\n"
    ).replace(
        "\r",
        "\n"
    )

    poem = re.sub(
        r"\n{3,}",
        "\n\n",
        poem
    )

    return poem.strip()


def format_fortune(record):

    number = get_ghazal_number(record)
    poem = clean_poem(
        record.get("poem", "")
    )
    source = str(
        record.get("source", "")
    ).strip()

    text = (
        "فال حافظ\n"
        f"شماره غزل {number}\n\n"
        f"{poem}\n\n"
        "منبع گنجور\n"
        f"{source}\n"
        f"{CHANNEL_URL} 🌱"
    )

    return text


def send_fortune(chat_id, record):

    text = format_fortune(record)
    chunks = split_message(text)

    success = True

    for index, chunk in enumerate(chunks):

        is_last = index == len(chunks) - 1

        result = send_message(
            chat_id,
            chunk,
            reply_markup=(
                REPEAT_KEYBOARD
                if is_last
                else None
            )
        )

        if result is None:
            success = False

    return success


# ==================================
# Audio URL Extraction
# ==================================

def extract_audio_urls(html, base_url):

    candidates = []

    absolute_urls = re.findall(
        r'https?://[^"\']+\.(?:ogg|mp3)(?:\?[^"\']*)?',
        html,
        flags=re.IGNORECASE
    )

    candidates.extend(
        absolute_urls
    )

    relative_urls = re.findall(
        r'(?:"|\')([^"\']+\.(?:ogg|mp3)(?:\?[^"\']*)?)(?:"|\')',
        html,
        flags=re.IGNORECASE
    )

    for relative_url in relative_urls:

        absolute_url = urljoin(
            base_url,
            relative_url
        )

        candidates.append(
            absolute_url
        )

    unique = []

    seen = set()

    for url in candidates:

        url = url.strip()

        if not url:
            continue

        if url in seen:
            continue

        seen.add(url)
        unique.append(url)

    preferred = [
        url for url in unique
        if "i.ganjoor.net" in url.lower()
    ]

    if preferred:
        return preferred + [
            url for url in unique
            if url not in preferred
        ]

    return unique


# ==================================
# Resolve Audio From Ganjoor
# ==================================

def resolve_audio_from_source(source_url):

    cached = audio_url_cache_get(
        source_url
    )

    if cached:
        return cached

    lock = get_audio_resolve_lock(
        source_url
    )

    with lock:

        cached = audio_url_cache_get(
            source_url
        )

        if cached:
            return cached

        print(
            f"[AUDIO] Resolving source: {source_url}"
        )

        try:

            response = get_session().get(
                source_url,
                timeout=REQUEST_TIMEOUT
            )

            if response.status_code != 200:
                print(
                    "[AUDIO] Source status:",
                    response.status_code
                )
                return None

            candidates = extract_audio_urls(
                response.text,
                source_url
            )

            if not candidates:
                print(
                    "[AUDIO] No audio candidates found."
                )
                return None

            ogg_candidates = [
                url for url in candidates
                if ".ogg" in url.lower()
            ]

            ordered = (
                ogg_candidates + [
                    url for url in candidates
                    if url not in ogg_candidates
                ]
            )

            for audio_url in ordered:

                if check_audio_url(audio_url):

                    audio_url_cache_put(
                        source_url,
                        audio_url
                    )

                    print(
                        f"[AUDIO] Resolved: {audio_url}"
                    )

                    return audio_url

        except Exception as e:

            print(
                "[AUDIO] Resolve error:",
                e
            )

        return None


def check_audio_url(audio_url):

    try:

        response = get_session().get(
            audio_url,
            stream=True,
            timeout=REQUEST_TIMEOUT
        )

        status = response.status_code

        response.close()

        return status == 200

    except Exception as e:

        print(
            "[AUDIO] URL check error:",
            e
        )

        return False


def resolve_final_audio_url(record):

    direct_audio = str(
        record.get("audio", "")
    ).strip()

    if direct_audio:

        if not negative_cache_get(
            direct_audio
        ):

            if check_audio_url(
                direct_audio
            ):
                return direct_audio

    source_url = str(
        record.get("source", "")
    ).strip()

    if not source_url:
        return None

    return resolve_audio_from_source(
        source_url
    )


# ==================================
# Download Audio
# ==================================

def download_audio(audio_url):

    cached = audio_cache_get(
        audio_url
    )

    if cached is not None:

        print(
            f"[AUDIO] Cache hit: {audio_url}"
        )

        return cached

    if negative_cache_get(
        audio_url
    ):

        print(
            f"[AUDIO] Negative cache hit: {audio_url}"
        )

        return None

    lock = get_audio_download_lock(
        audio_url
    )

    with lock:

        cached = audio_cache_get(
            audio_url
        )

        if cached is not None:
            return cached

        print(
            f"[AUDIO] Downloading: {audio_url}"
        )

        try:

            response = get_session().get(
                audio_url,
                timeout=REQUEST_TIMEOUT
            )

            if response.status_code == 404:

                negative_cache_put(
                    audio_url
                )

                print(
                    "[AUDIO] Download 404."
                )

                return None

            if response.status_code != 200:

                print(
                    "[AUDIO] Download status:",
                    response.status_code
                )

                return None

            data = response.content

            if not data:
                return None

            audio_cache_put(
                audio_url,
                data
            )

            print(
                f"[AUDIO] Downloaded "
                f"{len(data) / 1024:.1f} KB"
            )

            return data

        except Exception as e:

            print(
                "[AUDIO] Download error:",
                e
            )

            return None


# ==================================
# Audio Metadata
# ==================================

def get_audio_title(record):

    return "شعرکده سروش پلاس"


def get_audio_performer(record):

    return "شعرکده سروش پلاس"


# ==================================
# Send Audio
# ==================================

def send_audio(chat_id, record):

    audio_url = resolve_final_audio_url(
        record
    )

    if not audio_url:

        print(
            "[AUDIO] No final audio URL."
        )

        return None

    audio_data = download_audio(
        audio_url
    )

    if not audio_data:

        print(
            "[AUDIO] No audio data."
        )

        return None

    number = get_ghazal_number(
        record
    )

    if ".mp3" in audio_url.lower():

        extension = "mp3"
        mime_type = "audio/mpeg"

    else:

        extension = "ogg"
        mime_type = "audio/ogg"

    filename = (
        f"غزل {number} - حافظ - گنجور."
        f"{extension}"
    )

    audio_title = get_audio_title(
        record
    )

    audio_performer = get_audio_performer(
        record
    )

    print(
        "[AUDIO] Sending Audio | "
        f"filename={filename} | "
        f"title={audio_title} | "
        f"performer={audio_performer}"
    )

    files = {
        "audio": (
            filename,
            audio_data,
            mime_type
        )
    }

    return splus_request(
        "sendAudio",
        data={
            "chat_id": chat_id,
            "performer": audio_performer,
            "title": audio_title,
        },
        files=files
    )


# ==================================
# Chat Control
# ==================================

CHAT_CONTROL_MESSAGES = {}
CHAT_CONTROL_LOCK = threading.RLock()


def set_control_message(
    chat_id,
    message_id
):

    if not message_id:
        return

    with CHAT_CONTROL_LOCK:
        CHAT_CONTROL_MESSAGES[
            str(chat_id)
        ] = message_id


def get_control_message(chat_id):

    with CHAT_CONTROL_LOCK:
        return CHAT_CONTROL_MESSAGES.get(
            str(chat_id)
        )


def remove_control_message(chat_id):

    with CHAT_CONTROL_LOCK:
        return CHAT_CONTROL_MESSAGES.pop(
            str(chat_id),
            None
        )


def clear_control_message(chat_id):

    with CHAT_CONTROL_LOCK:
        CHAT_CONTROL_MESSAGES.pop(
            str(chat_id),
            None
        )


# ==================================
# Fortune Processing
# ==================================

def process_fortune(
    chat_id,
    fortune_message_id
):

    try:

        if not HAZALS:

            send_message(
                chat_id,
                "متأسفانه مجموعه غزل‌های حافظ در دسترس نیست.",
                reply_markup=MAIN_KEYBOARD
            )

            return

        record = random.choice(
            HAZALS
        )

        success = send_fortune(
            chat_id,
            record
        )

        if success:

            old_control = get_control_message(
                chat_id
            )

            if old_control:

                delete_message(
                    chat_id,
                    old_control
                )

            if fortune_message_id:

                delete_message(
                    chat_id,
                    fortune_message_id
                )

            clear_control_message(
                chat_id
            )

        send_audio(
            chat_id,
            record
        )

    except Exception as e:

        print(
            "[FORTUNE] ERROR:",
            e
        )


# ==================================
# Webhook
# ==================================

@app.route(
    "/webhook",
    methods=["POST"]
)
def webhook():

    try:

        update = request.get_json(
            silent=True
        ) or {}

        message = (
            update.get("message")
            or update.get("edited_message")
        )

        if not message:
            return "ok"

        chat = message.get("chat") or {}

        chat_id = chat.get("id")

        if chat_id is None:
            return "ok"

        text = str(
            message.get("text", "")
        ).strip()

        message_id = message.get(
            "message_id"
        )

        # ----------------------------------
        # /start
        # ----------------------------------

        if text == "/start":

            welcome_text = (
                "🌿 به فال حافظ خوش آمدید.\n\n"
                "برای گرفتن فال، روی دکمه "
                "«📜 فال حافظ» بزنید.\n\n"
                "هر بار یک غزل تصادفی از "
                "غزلیات حافظ برای شما انتخاب می‌شود."
            )

            result = send_message(
                chat_id,
                welcome_text,
                reply_markup=MAIN_KEYBOARD
            )

            if (
                isinstance(result, dict)
                and result.get("result")
            ):

                sent_message = result[
                    "result"
                ]

                sent_message_id = (
                    sent_message.get(
                        "message_id"
                    )
                )

                if sent_message_id:

                    set_control_message(
                        chat_id,
                        sent_message_id
                    )

            delete_message(
                chat_id,
                message_id
            )

            return "ok"

        # ----------------------------------
        # Repeat
        # ----------------------------------

        if text == "🌿 یک فال دیگر":

            delete_message(
                chat_id,
                message_id
            )

            result = send_message(
                chat_id,
                "🌿 دوباره نیت کنید و روی "
                "«📜 فال حافظ» بزنید.",
                reply_markup=MAIN_KEYBOARD
            )

            if (
                isinstance(result, dict)
                and result.get("result")
            ):

                sent_message = result[
                    "result"
                ]

                sent_message_id = (
                    sent_message.get(
                        "message_id"
                    )
                )

                if sent_message_id:

                    set_control_message(
                        chat_id,
                        sent_message_id
                    )

            return "ok"

        # ----------------------------------
        # Fortune
        # ----------------------------------

        if text == "📜 فال حافظ":

            thread = threading.Thread(
                target=process_fortune,
                args=(
                    chat_id,
                    message_id
                ),
                daemon=True
            )

            thread.start()

            return "ok"

        return "ok"

    except Exception as e:

        print(
            "[WEBHOOK] ERROR:",
            e
        )

        return "ok"


# ==================================
# Health Check
# ==================================

@app.route(
    "/",
    methods=["GET"]
)
def health():

    return "Hafez Bot is running."


# ==================================
# Webhook Setup
# ==================================

def set_webhook():

    print(
        "[WEBHOOK] Setting webhook..."
    )

    result = splus_request(
        "setWebhook",
        data={
            "url": WEBHOOK_URL
        }
    )

    print(
        "[WEBHOOK] Result:",
        result
    )

    return result


# ==================================
# Startup
# ==================================

try:

    load_data()

except Exception as e:

    print(
        "[STARTUP] DATA ERROR:",
        e
    )

    HAZALS = []


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



