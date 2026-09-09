import os
import json
import random
import time
import threading
import re
from collections import OrderedDict

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

REQUEST_TIMEOUT = 30


# ==================================
# Thread Local Session
# ==================================

_thread_local = threading.local()


def get_session():
    session = getattr(_thread_local, "session", None)

    if session is None:
        session = requests.Session()
        _thread_local.session = session

    return session


# ==================================
# Audio Cache
# ==================================

AUDIO_CACHE_MAX_ITEMS = 5
AUDIO_CACHE_MAX_BYTES = 50 * 1024 * 1024

audio_cache = OrderedDict()
audio_cache_size = 0

AUDIO_CACHE_LOCK = threading.Lock()

AUDIO_DOWNLOAD_LOCKS = {}
AUDIO_DOWNLOAD_LOCKS_LOCK = threading.Lock()


# ==================================
# Negative Audio Cache
# ==================================

NEGATIVE_AUDIO_CACHE_TTL = 10 * 60

negative_audio_cache = {}

NEGATIVE_AUDIO_CACHE_LOCK = threading.Lock()


# ==================================
# Control Message State
# ==================================

CHAT_CONTROL_MESSAGES = {}

CHAT_CONTROL_LOCK = threading.Lock()


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
    "resize_keyboard": True
}


REPEAT_FORTUNE_KEYBOARD = {
    "keyboard": [
        [
            {
                "text": "🌿 یک فال دیگر"
            }
        ]
    ],
    "resize_keyboard": True
}


# ==================================
# Data
# ==================================

def load_data():
    if not os.path.exists(DATA_FILE):
        raise FileNotFoundError(
            f"Data file not found: {DATA_FILE}"
        )

    with open(
        DATA_FILE,
        "r",
        encoding="utf-8"
    ) as f:
        raw_data = json.load(f)

    records = []

    if isinstance(raw_data, dict):
        items = raw_data.items()

    elif isinstance(raw_data, list):
        items = enumerate(raw_data)

    else:
        raise ValueError(
            "Unsupported JSON structure."
        )

    for record_id, record in items:

        if not isinstance(record, dict):
            continue

        poem = str(
            record.get("Poem", "")
        ).strip()

        if not poem:
            continue

        normalized = {
            "record_id": str(record_id),

            "Poem": poem,

            "Title": str(
                record.get("Title", "")
            ).strip(),

            "Source": str(
                record.get("Source", "")
            ).strip(),

            "Audio": record.get("Audio"),

            "Author": str(
                record.get("Author", "حافظ")
            ).strip(),

            "Book": str(
                record.get("Book", "غزلیات حافظ")
            ).strip()
        }

        records.append(normalized)

    if not records:
        raise ValueError(
            "No valid Hafez records found."
        )

    print(
        f"[DATA] HAZALS loaded: {len(records)}"
    )

    return records


HAZALS = load_data()


# ==================================
# HTTP API
# ==================================

def splus_request(
    method,
    data=None,
    files=None,
    timeout=REQUEST_TIMEOUT
):
    url = f"{API}/{method}"

    session = get_session()

    try:

        if files:
            response = session.post(
                url,
                data=data,
                files=files,
                timeout=timeout
            )

        else:
            response = session.post(
                url,
                data=data,
                timeout=timeout
            )

    except requests.RequestException as exc:

        print(
            f"[REQUEST ERROR] "
            f"method={method} "
            f"error={exc}"
        )

        return None

    try:
        result = response.json()

    except Exception:

        print(
            f"[API ERROR] "
            f"method={method} "
            f"status={response.status_code} "
            f"response={response.text[:1000]}"
        )

        return None

    if not response.ok:

        print(
            f"[HTTP ERROR] "
            f"method={method} "
            f"status={response.status_code} "
            f"response={result}"
        )

        return result

    if (
        isinstance(result, dict)
        and result.get("ok") is False
    ):

        print(
            f"[API ERROR] "
            f"method={method} "
            f"response={result}"
        )

    return result


# ==================================
# Send Message
# ==================================

def send_message(
    chat_id,
    text,
    reply_markup=None
):

    data = {
        "chat_id": chat_id,
        "text": text
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


# ==================================
# DELETE MESSAGE
# ==================================

def delete_message(chat_id, message_id):

    if not chat_id or message_id is None:

        print(
            f"[DELETE] SKIPPED | "
            f"chat_id={chat_id} | "
            f"message_id={message_id}"
        )

        return False

    print(
        f"[DELETE] TRY | "
        f"chat_id={chat_id} | "
        f"message_id={message_id}"
    )

    result = splus_request(
        "deleteMessage",
        data={
            "chat_id": chat_id,
            "message_id": message_id
        }
    )

    print(
        f"[DELETE] RESULT | "
        f"chat_id={chat_id} | "
        f"message_id={message_id} | "
        f"result={result}"
    )

    if (
        isinstance(result, dict)
        and result.get("ok") is True
    ):

        print(
            f"[DELETE] SUCCESS | "
            f"chat_id={chat_id} | "
            f"message_id={message_id}"
        )

        return True

    print(
        f"[DELETE] FAILED | "
        f"chat_id={chat_id} | "
        f"message_id={message_id}"
    )

    return False


# ==================================
# Control Message State
# ==================================

def set_chat_control_message(
    chat_id,
    key,
    message_id
):

    if chat_id is None or message_id is None:
        return

    with CHAT_CONTROL_LOCK:

        state = CHAT_CONTROL_MESSAGES.setdefault(
            str(chat_id),
            {}
        )

        state[key] = message_id


def get_chat_control_message(
    chat_id,
    key
):

    with CHAT_CONTROL_LOCK:

        state = CHAT_CONTROL_MESSAGES.get(
            str(chat_id),
            {}
        )

        return state.get(key)


def clear_chat_control_message(
    chat_id,
    key
):

    with CHAT_CONTROL_LOCK:

        state = CHAT_CONTROL_MESSAGES.get(
            str(chat_id)
        )

        if not state:
            return None

        message_id = state.pop(
            key,
            None
        )

        if not state:
            CHAT_CONTROL_MESSAGES.pop(
                str(chat_id),
                None
            )

        return message_id


# ==================================
# Split Message
# ==================================

def split_message(text):

    if len(text) <= MAX_MESSAGE_LENGTH:
        return [text]

    chunks = []

    current = ""

    for line in text.split("\n"):

        if not current:

            if len(line) <= MAX_MESSAGE_LENGTH:
                current = line

            else:

                while len(line) > MAX_MESSAGE_LENGTH:
                    chunks.append(
                        line[:MAX_MESSAGE_LENGTH]
                    )

                    line = line[
                        MAX_MESSAGE_LENGTH:
                    ]

                current = line

            continue

        candidate = (
            current
            + "\n"
            + line
        )

        if len(candidate) <= MAX_MESSAGE_LENGTH:

            current = candidate

        else:

            chunks.append(current)

            if len(line) <= MAX_MESSAGE_LENGTH:

                current = line

            else:

                while len(line) > MAX_MESSAGE_LENGTH:

                    chunks.append(
                        line[:MAX_MESSAGE_LENGTH]
                    )

                    line = line[
                        MAX_MESSAGE_LENGTH:
                    ]

                current = line

    if current:
        chunks.append(current)

    return chunks


# ==================================
# Ghazal Number
# ==================================

def get_ghazal_number(record):

    source = str(
        record.get("Source", "")
    )

    match = re.search(
        r"/sh(\d+)/",
        source
    )

    if match:
        return match.group(1)

    title = str(
        record.get("Title", "")
    )

    match = re.search(
        r"(\d+)",
        title
    )

    if match:
        return match.group(1)

    return str(
        record.get("record_id", "")
    )


# ==================================
# Clean Poem
# ==================================

def clean_poem(poem):

    if not poem:
        return ""

    poem = str(poem).strip()

    poem = re.sub(
        r"\n{3,}",
        "\n\n",
        poem
    )

    return poem


# ==================================
# Build Fortune
# ==================================

def build_fortune(record):

    number = get_ghazal_number(
        record
    )

    poem = clean_poem(
        record.get("Poem", "")
    )

    return (
        f"فال حافظ\n"
        f"شماره غزل {number}\n\n"
        f"{poem}\n\n"
        f"منبع گنجور\n"
        f"{record.get('Source', '')}\n"
        f"@LIFE_M23 🌱"
    )


# ==================================
# Send Fortune
# ==================================

def send_fortune(
    chat_id,
    record,
    reply_markup=None
):

    text = build_fortune(record)

    chunks = split_message(text)

    for index, chunk in enumerate(chunks):

        result = send_message(
            chat_id,
            chunk,
            reply_markup=(
                reply_markup
                if index == len(chunks) - 1
                else None
            )
        )

        if not result:
            print(
                "[FORTUNE] "
                "send_message returned None"
            )

        if len(chunks) > 1:
            time.sleep(0.15)

    return True


# ==================================
# Audio Cache Helpers
# ==================================

def get_audio_download_lock(url):

    with AUDIO_DOWNLOAD_LOCKS_LOCK:

        lock = AUDIO_DOWNLOAD_LOCKS.get(url)

        if lock is None:

            lock = threading.Lock()

            AUDIO_DOWNLOAD_LOCKS[url] = lock

        return lock


def get_cached_audio(url):

    global audio_cache_size

    with AUDIO_CACHE_LOCK:

        item = audio_cache.get(url)

        if item is None:
            return None

        audio_cache.move_to_end(url)

        return item


def set_cached_audio(url, content):

    global audio_cache_size

    content_size = len(content)

    if content_size > AUDIO_CACHE_MAX_BYTES:
        return

    with AUDIO_CACHE_LOCK:

        old = audio_cache.pop(
            url,
            None
        )

        if old is not None:
            audio_cache_size -= len(old)

        audio_cache[url] = content

        audio_cache_size += content_size

        while (
            len(audio_cache)
            > AUDIO_CACHE_MAX_ITEMS
            or audio_cache_size
            > AUDIO_CACHE_MAX_BYTES
        ):

            _, removed = audio_cache.popitem(
                last=False
            )

            audio_cache_size -= len(
                removed
            )


# ==================================
# Negative Audio Cache
# ==================================

def is_negative_audio_cached(url):

    now = time.time()

    with NEGATIVE_AUDIO_CACHE_LOCK:

        timestamp = negative_audio_cache.get(
            url
        )

        if timestamp is None:
            return False

        if now - timestamp >= NEGATIVE_AUDIO_CACHE_TTL:

            negative_audio_cache.pop(
                url,
                None
            )

            return False

        return True


def set_negative_audio_cache(url):

    with NEGATIVE_AUDIO_CACHE_LOCK:

        negative_audio_cache[url] = time.time()


# ==================================
# Download Audio
# ==================================

def download_audio(url):

    if not url:
        return None

    if is_negative_audio_cached(url):

        print(
            f"[AUDIO] negative cache hit: {url}"
        )

        return None

    cached = get_cached_audio(url)

    if cached is not None:

        print(
            f"[AUDIO] cache hit: {url}"
        )

        return cached

    lock = get_audio_download_lock(url)

    with lock:

        cached = get_cached_audio(url)

        if cached is not None:
            return cached

        if is_negative_audio_cached(url):
            return None

        print(
            f"[AUDIO] downloading: {url}"
        )

        try:

            response = get_session().get(
                url,
                timeout=REQUEST_TIMEOUT
            )

        except requests.RequestException as exc:

            print(
                f"[AUDIO] download error: "
                f"{url} | {exc}"
            )

            return None

        if response.status_code == 404:

            print(
                f"[AUDIO] 404: {url}"
            )

            set_negative_audio_cache(url)

            return None

        if response.status_code != 200:

            print(
                f"[AUDIO] HTTP "
                f"{response.status_code}: "
                f"{url}"
            )

            return None

        content = response.content

        if not content:

            print(
                f"[AUDIO] empty response: "
                f"{url}"
            )

            return None

        if len(content) > AUDIO_CACHE_MAX_BYTES:

            print(
                f"[AUDIO] file too large: "
                f"{len(content)} bytes"
            )

            return content

        set_cached_audio(
            url,
            content
        )

        return content


# ==================================
# Send Audio
# ==================================

def send_audio(
    chat_id,
    record
):

    audio_url = record.get(
        "Audio"
    )

    if not audio_url:
        return False

    audio_url = str(
        audio_url
    ).strip()

    if not audio_url:
        return False

    audio_content = download_audio(
        audio_url
    )

    if audio_content is None:

        print(
            f"[AUDIO] unavailable: "
            f"{audio_url}"
        )

        return False

    filename = "hafez.ogg"

    source_match = re.search(
        r"/([^/]+)$",
        audio_url
    )

    if source_match:
        filename = source_match.group(1)

    files = {
        "audio": (
            filename,
            audio_content,
            "audio/ogg"
        )
    }

    data = {
        "chat_id": chat_id
    }

    title = record.get(
        "Title"
    )

    if title:
        data["title"] = title

    data["performer"] = "حافظ"

    result = splus_request(
        "sendAudio",
        data=data,
        files=files
    )

    if (
        isinstance(result, dict)
        and result.get("ok") is True
    ):

        print(
            f"[AUDIO] sent: "
            f"{audio_url}"
        )

        return True

    print(
        f"[AUDIO] send failed: "
        f"{audio_url} | "
        f"{result}"
    )

    return False


# ==================================
# Fortune Processing
# ==================================

def process_fortune(
    chat_id,
    fortune_message_id
):

    try:

        record = random.choice(
            HAZALS
        )

        # ----------------------------------
        # Send poem
        # ----------------------------------

        send_fortune(
            chat_id,
            record,
            reply_markup=REPEAT_FORTUNE_KEYBOARD
        )

        # ----------------------------------
        # Delete user's "📜 فال حافظ"
        # AFTER poem is sent
        # ----------------------------------

        if fortune_message_id is not None:

            delete_message(
                chat_id,
                fortune_message_id
            )

        # ----------------------------------
        # Delete repeat prompt if exists
        # ----------------------------------

        repeat_prompt_id = (
            get_chat_control_message(
                chat_id,
                "repeat_prompt_message_id"
            )
        )

        if repeat_prompt_id is not None:

            delete_message(
                chat_id,
                repeat_prompt_id
            )

            clear_chat_control_message(
                chat_id,
                "repeat_prompt_message_id"
            )

        clear_chat_control_message(
            chat_id,
            "fortune_message_id"
        )

        # ----------------------------------
        # Send audio
        # ----------------------------------

        send_audio(
            chat_id,
            record
        )

    except Exception as exc:

        print(
            f"[FORTUNE ERROR] "
            f"chat_id={chat_id} | "
            f"error={exc}"
        )


# ==================================
# Extract Message
# ==================================

def extract_message(update):

    if not isinstance(update, dict):
        return None

    message = update.get(
        "message"
    )

    if isinstance(message, dict):
        return message

    return None


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
        )

    except Exception:

        update = None

    if not isinstance(update, dict):

        return "OK"

    print(
        f"[UPDATE] {update}"
    )

    message = extract_message(
        update
    )

    if not message:
        return "OK"

    message_id = message.get(
        "message_id"
    )

    chat = message.get(
        "chat"
    )

    if not isinstance(chat, dict):
        return "OK"

    chat_id = chat.get(
        "id"
    )

    if chat_id is None:
        return "OK"

    text = message.get(
        "text",
        ""
    )

    if not isinstance(text, str):
        text = str(text)

    text = text.strip()

    # ==================================
    # /start
    # ==================================

    if text == "/start":

        send_message(
            chat_id,
            "سلام 🌿\n\n"
            "به ربات فال حافظ خوش آمدید.\n\n"
            "برای گرفتن فال، نیت کنید و "
            "دکمه «📜 فال حافظ» را بزنید.",
            reply_markup=MAIN_KEYBOARD
        )

        # حذف پیام /start کاربر
        if message_id is not None:

            delete_message(
                chat_id,
                message_id
            )

        return "OK"

    # ==================================
    # Repeat Fortune
    # ==================================

    if text in (
        "یک فال دیگر",
        "🌿 یک فال دیگر"
    ):

        # ----------------------------------
        # حذف فوری پیام «🌿 یک فال دیگر»
        # ----------------------------------

        if message_id is not None:

            delete_message(
                chat_id,
                message_id
            )

        # ----------------------------------
        # ارسال پیام نیت مجدد
        # ----------------------------------

        prompt_result = send_message(
            chat_id,
            "✨ دوباره نیت کنید و سپس دکمه «📜 فال حافظ» را بزنید.",
            reply_markup=MAIN_KEYBOARD
        )

        # ----------------------------------
        # ذخیره message_id پیام نیت
        # ----------------------------------

        if (
            isinstance(prompt_result, dict)
            and prompt_result.get("ok") is True
        ):

            prompt_message = (
                prompt_result.get("result")
            )

            if isinstance(
                prompt_message,
                dict
            ):

                prompt_message_id = (
                    prompt_message.get(
                        "message_id"
                    )
                )

                if prompt_message_id is not None:

                    set_chat_control_message(
                        chat_id,
                        "repeat_prompt_message_id",
                        prompt_message_id
                    )

        return "OK"

    # ==================================
    # Fortune
    # ==================================

    if text in (
        "فال حافظ",
        "📜 فال حافظ"
    ):

        # ----------------------------------
        # ذخیره message_id پیام کاربر
        # ----------------------------------

        if message_id is not None:

            set_chat_control_message(
                chat_id,
                "fortune_message_id",
                message_id
            )

        # ----------------------------------
        # Process in background
        # ----------------------------------

        thread = threading.Thread(
            target=process_fortune,
            args=(
                chat_id,
                message_id
            ),
            daemon=True,
            name=f"fortune-{chat_id}"
        )

        thread.start()

        return "OK"

    return "OK"


# ==================================
# Home
# ==================================

@app.route(
    "/",
    methods=["GET"]
)
def home():

    return "Hafez Bot is running."


# ==================================
# Set Webhook
# ==================================

def set_webhook():

    result = splus_request(
        "setWebhook",
        data={
            "url": WEBHOOK_URL
        }
    )

    print(
        f"[WEBHOOK] setWebhook result: "
        f"{result}"
    )

    return result


# ==================================
# Startup
# ==================================

try:

    set_webhook()

except Exception as exc:

    print(
        f"[STARTUP ERROR] "
        f"{exc}"
    )


# ==================================
# Local Run
# ==================================

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=int(
            os.environ.get(
                "PORT",
                "5000"
            )
        )
        )
