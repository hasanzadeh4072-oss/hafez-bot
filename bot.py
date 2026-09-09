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

# زمان اتصال و دریافت پاسخ جداگانه
CONNECT_TIMEOUT = 5
READ_TIMEOUT = 15

REQUEST_TIMEOUT = (CONNECT_TIMEOUT, READ_TIMEOUT)


# ----------------------------------
# Audio Cache
# ----------------------------------

AUDIO_CACHE_MAX_ITEMS = 5
AUDIO_CACHE_MAX_BYTES = 50 * 1024 * 1024

# مدت نگهداری خطاهای 404 صوت
AUDIO_NEGATIVE_CACHE_TTL = 10 * 60


# ==================================
# Logging
# ==================================

def log(message):
    """
    لاگ دقیق برای Render:
    PID + Thread + زمان نسبی + flush فوری
    """

    timestamp = time.strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    pid = os.getpid()

    thread_name = threading.current_thread().name

    print(
        f"{timestamp} "
        f"[PID={pid}] "
        f"[THREAD={thread_name}] "
        f"{message}",
        flush=True
    )


# ==================================
# Global Data
# ==================================

HAZALS = []


# ==================================
# Control Message State
# ==================================

# برای هر چت، پیام‌های کنترلی فعال را نگه می‌داریم.
#
# start_message_id:
#   پیام /start کاربر
#
# repeat_prompt_message_id:
#   پیام «دوباره نیت کنید...»
#
# fortune_message_id:
#   پیام «📜 فال حافظ» که کاربر برای درخواست فال فرستاده
#
# توجه:
# پیام شعر و صوت در این State ذخیره نمی‌شوند
# و هیچ‌وقت حذف نخواهند شد.

CHAT_CONTROL_MESSAGES = {}

CHAT_CONTROL_LOCK = threading.Lock()


def set_chat_control_message(
    chat_id,
    key,
    message_id
):

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


def remove_chat_control_message(
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


def clear_chat_control_message(
    chat_id,
    key
):

    message_id = remove_chat_control_message(
        chat_id,
        key
    )

    return message_id


# ==================================
# HTTP Session
# ==================================

_thread_local = threading.local()


def get_session():
    """
    برای هر Thread یک requests.Session نگه می‌داریم
    تا Connection Pool قابل استفاده مجدد باشد.
    """

    session = getattr(
        _thread_local,
        "session",
        None
    )

    if session is None:

        session = requests.Session()

        session.headers.update({
            "User-Agent": "HafezBot/1.0"
        })

        _thread_local.session = session

        log(
            "[SESSION] New HTTP session created."
        )

    return session


# ==================================
# Audio Cache
# ==================================

_AUDIO_CACHE = OrderedDict()

_AUDIO_CACHE_BYTES = 0

_AUDIO_CACHE_LOCK = threading.Lock()

_AUDIO_DOWNLOAD_LOCKS = {}

_AUDIO_DOWNLOAD_LOCKS_GUARD = threading.Lock()

_AUDIO_NEGATIVE_CACHE = {}

_AUDIO_NEGATIVE_CACHE_LOCK = threading.Lock()


def get_audio_download_lock(audio_url):
    """
    برای هر URL یک Lock ایجاد می‌کند تا اگر
    چند درخواست همزمان برای یک فایل صوتی آمد،
    فایل چند بار دانلود نشود.
    """

    with _AUDIO_DOWNLOAD_LOCKS_GUARD:

        lock = _AUDIO_DOWNLOAD_LOCKS.get(
            audio_url
        )

        if lock is None:

            lock = threading.Lock()

            _AUDIO_DOWNLOAD_LOCKS[
                audio_url
            ] = lock

        return lock


def get_cached_audio(audio_url):

    if not audio_url:
        return None

    with _AUDIO_CACHE_LOCK:

        item = _AUDIO_CACHE.get(
            audio_url
        )

        if item is None:
            return None

        # LRU
        _AUDIO_CACHE.move_to_end(
            audio_url
        )

        return item


def cache_audio(
    audio_url,
    audio_data
):

    global _AUDIO_CACHE_BYTES

    if not audio_url or not audio_data:
        return

    data_size = len(audio_data)

    if data_size > AUDIO_CACHE_MAX_BYTES:

        log(
            f"[AUDIO CACHE] "
            f"File too large to cache: "
            f"{data_size} bytes"
        )

        return

    with _AUDIO_CACHE_LOCK:

        old_data = _AUDIO_CACHE.pop(
            audio_url,
            None
        )

        if old_data is not None:

            _AUDIO_CACHE_BYTES -= len(
                old_data
            )

        _AUDIO_CACHE[audio_url] = audio_data

        _AUDIO_CACHE_BYTES += data_size

        while (
            len(_AUDIO_CACHE)
            > AUDIO_CACHE_MAX_ITEMS
            or _AUDIO_CACHE_BYTES
            > AUDIO_CACHE_MAX_BYTES
        ):

            _, removed_data = (
                _AUDIO_CACHE.popitem(
                    last=False
                )
            )

            _AUDIO_CACHE_BYTES -= len(
                removed_data
            )

        log(
            f"[AUDIO CACHE] Stored: "
            f"{data_size} bytes | "
            f"items={len(_AUDIO_CACHE)} | "
            f"total={_AUDIO_CACHE_BYTES} bytes"
        )


def get_negative_audio_cache(
    audio_url
):

    if not audio_url:
        return False

    now = time.monotonic()

    with _AUDIO_NEGATIVE_CACHE_LOCK:

        expires_at = (
            _AUDIO_NEGATIVE_CACHE.get(
                audio_url
            )
        )

        if expires_at is None:
            return False

        if now >= expires_at:

            del _AUDIO_NEGATIVE_CACHE[
                audio_url
            ]

            return False

        return True


def set_negative_audio_cache(
    audio_url
):

    if not audio_url:
        return

    expires_at = (
        time.monotonic()
        + AUDIO_NEGATIVE_CACHE_TTL
    )

    with _AUDIO_NEGATIVE_CACHE_LOCK:

        _AUDIO_NEGATIVE_CACHE[
            audio_url
        ] = expires_at

    log(
        f"[AUDIO CACHE] "
        f"Negative cache stored "
        f"for {AUDIO_NEGATIVE_CACHE_TTL}s"
    )


# ==================================
# Keyboard
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


# ----------------------------------
# Repeat Fortune Keyboard
# ----------------------------------

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
# Data Loading
# ==================================

def load_data():

    global HAZALS

    log(
        f"[DATA] Loading data from "
        f"{DATA_FILE}"
    )

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

    loaded = []

    for item in raw_data:

        if not isinstance(item, dict):
            continue

        for record_id, record in item.items():

            if not isinstance(record, dict):
                continue

            poem = str(
                record.get("Poem") or ""
            ).strip()

            if not poem:
                continue

            title = str(
                record.get("Title") or ""
            ).strip()

            source = str(
                record.get("Source") or ""
            ).strip()

            audio = record.get("Audio")

            if isinstance(audio, str):

                audio = audio.strip()

                if not audio:
                    audio = None

            else:

                audio = None

            loaded.append({
                "record_id": str(record_id),

                "author": record.get(
                    "Author",
                    "حافظ"
                ),

                "book": record.get(
                    "Book",
                    "غزلیات حافظ"
                ),

                "poem": poem,

                "source": source,

                "title": title,

                "audio": audio,
            })

    HAZALS = loaded

    log(
        f"[DATA] Loaded "
        f"{len(HAZALS)} ghazals."
    )


# ==================================
# Soroush API Request
# ==================================

def splus_request(
    method,
    data=None,
    files=None
):

    url = f"{API}/{method}"

    started_at = time.perf_counter()

    log(
        f"[SPLUS START] "
        f"{method}"
    )

    try:

        session = get_session()

        response = session.post(
            url,
            data=data,
            files=files,
            timeout=REQUEST_TIMEOUT
        )

        elapsed = (
            time.perf_counter()
            - started_at
        )

        status_code = response.status_code

        if response.ok:

            log(
                f"[SPLUS END] "
                f"{method}: "
                f"{status_code} | "
                f"{elapsed:.3f}s"
            )

        else:

            preview = response.text[:300]

            log(
                f"[SPLUS ERROR] "
                f"{method}: "
                f"{status_code} | "
                f"{elapsed:.3f}s | "
                f"{preview}"
            )

        response.raise_for_status()

        try:

            result = response.json()

        except ValueError:

            log(
                f"[SPLUS ERROR] "
                f"{method}: "
                f"Invalid JSON response | "
                f"{elapsed:.3f}s"
            )

            return None

        return result

    except requests.Timeout as e:

        elapsed = (
            time.perf_counter()
            - started_at
        )

        log(
            f"[SPLUS TIMEOUT] "
            f"{method}: "
            f"{elapsed:.3f}s | "
            f"{e}"
        )

        return None

    except requests.RequestException as e:

        elapsed = (
            time.perf_counter()
            - started_at
        )

        log(
            f"[SPLUS ERROR] "
            f"{method}: "
            f"{elapsed:.3f}s | "
            f"{e}"
        )

        return None

    except Exception as e:

        elapsed = (
            time.perf_counter()
            - started_at
        )

        log(
            f"[SPLUS ERROR] "
            f"{method}: "
            f"{elapsed:.3f}s | "
            f"{e}"
        )

        return None


# ==================================
# Delete Message
# ==================================

def delete_message(
    chat_id,
    message_id
):

    if not chat_id or not message_id:
        return False

    log(
        f"[DELETE] "
        f"chat_id={chat_id} "
        f"message_id={message_id}"
    )

    result = splus_request(
        "deleteMessage",
        data={
            "chat_id": chat_id,
            "message_id": message_id
        }
    )

    if result and result.get("ok"):

        log(
            f"[DELETE] Success | "
            f"message_id={message_id}"
        )

        return True

    log(
        f"[DELETE] Failed | "
        f"message_id={message_id}"
    )

    return False


def delete_control_message(
    chat_id,
    key
):

    message_id = get_chat_control_message(
        chat_id,
        key
    )

    if not message_id:
        return

    success = delete_message(
        chat_id,
        message_id
    )

    if success:

        clear_chat_control_message(
            chat_id,
            key
        )


# ==================================
# Send Message
# ==================================

def send_message(
    chat_id,
    text,
    reply_markup=None
):

    if not text:
        return None

    data = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": "true"
    }

    if reply_markup is not None:

        data["reply_markup"] = json.dumps(
            reply_markup,
            ensure_ascii=False,
            separators=(",", ":")
        )

    return splus_request(
        "sendMessage",
        data=data
    )


# ==================================
# Split Message
# ==================================

def split_message(
    text,
    max_length=MAX_MESSAGE_LENGTH
):

    if len(text) <= max_length:
        return [text]

    chunks = []

    remaining = text.strip()

    while len(remaining) > max_length:

        cut = remaining.rfind(
            "\n",
            0,
            max_length
        )

        if cut < 1000:

            cut = remaining.rfind(
                " ",
                0,
                max_length
            )

        if cut < 1:

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

    title = record.get(
        "title",
        ""
    )

    source = record.get(
        "source",
        ""
    )

    if source:

        match = re.search(
            r"/sh(\d+)/?",
            source
        )

        if match:

            return match.group(1)

    match = re.search(
        r"(\d+)",
        title
    )

    if match:

        return match.group(1)

    return record.get(
        "record_id",
        "نامشخص"
    )


# ==================================
# Clean Poem
# ==================================

def clean_poem(poem):

    if not poem:
        return ""

    poem = poem.replace(
        "\r\n",
        "\n"
    )

    poem = poem.replace(
        "\r",
        "\n"
    )

    return poem.strip()


# ==================================
# Build Fortune
# ==================================

def build_fortune(record):

    number = get_ghazal_number(
        record
    )

    poem = clean_poem(
        record.get(
            "poem",
            ""
        )
    )

    return (
        f"فال حافظ\n"
        f"شماره غزل {number}\n\n"
        f"{poem}\n\n"
        f"منبع گنجور\n"
        f"{record.get('source', '')}\n"
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

    fortune_text = build_fortune(
        record
    )

    log(
        f"[FORTUNE] Ghazal "
        f"#{get_ghazal_number(record)} "
        f"record={record.get('record_id')}"
    )

    log(
        f"[FORTUNE] Final text length="
        f"{len(fortune_text)}"
    )

    chunks = split_message(
        fortune_text
    )

    log(
        f"[MESSAGE] length="
        f"{len(fortune_text)} "
        f"chunks={len(chunks)}"
    )

    for index, chunk in enumerate(chunks):

        # دکمه فال دیگر فقط روی آخرین پیام شعر قرار می‌گیرد
        if index == len(chunks) - 1:

            result = send_message(
                chat_id,
                chunk,
                reply_markup=reply_markup
            )

        else:

            result = send_message(
                chat_id,
                chunk
            )

        if len(chunks) > 1:

            time.sleep(0.15)


# ==================================
# Download Audio
# ==================================

def download_audio(audio_url):

    if not audio_url:
        return None

    # ------------------------------
    # Positive Cache
    # ------------------------------

    cached = get_cached_audio(
        audio_url
    )

    if cached is not None:

        log(
            f"[AUDIO CACHE] HIT: "
            f"{audio_url}"
        )

        return cached

    log(
        f"[AUDIO CACHE] MISS: "
        f"{audio_url}"
    )

    # ------------------------------
    # Negative Cache
    # ------------------------------

    if get_negative_audio_cache(
        audio_url
    ):

        log(
            f"[AUDIO CACHE] "
            f"NEGATIVE HIT: "
            f"{audio_url}"
        )

        return None

    # ------------------------------
    # Download Lock
    # ------------------------------

    download_lock = get_audio_download_lock(
        audio_url
    )

    with download_lock:

        cached = get_cached_audio(
            audio_url
        )

        if cached is not None:

            log(
                f"[AUDIO CACHE] "
                f"HIT AFTER LOCK: "
                f"{audio_url}"
            )

            return cached

        if get_negative_audio_cache(
            audio_url
        ):

            log(
                f"[AUDIO CACHE] "
                f"NEGATIVE HIT AFTER LOCK: "
                f"{audio_url}"
            )

            return None

        log(
            f"[AUDIO] Downloading ONLY "
            f"user's source: {audio_url}"
        )

        started_at = time.perf_counter()

        try:

            session = get_session()

            response = session.get(
                audio_url,
                timeout=REQUEST_TIMEOUT
            )

            elapsed = (
                time.perf_counter()
                - started_at
            )

            if response.status_code == 404:

                log(
                    f"[AUDIO] HTTP 404 | "
                    f"{elapsed:.3f}s"
                )

                set_negative_audio_cache(
                    audio_url
                )

                return None

            response.raise_for_status()

            content = response.content

            if not content:

                log(
                    f"[AUDIO] "
                    f"Empty audio response | "
                    f"{elapsed:.3f}s"
                )

                return None

            log(
                f"[AUDIO] Downloaded "
                f"{len(content)} bytes | "
                f"{elapsed:.3f}s"
            )

            cache_audio(
                audio_url,
                content
            )

            return content

        except requests.Timeout as e:

            elapsed = (
                time.perf_counter()
                - started_at
            )

            log(
                f"[AUDIO TIMEOUT] "
                f"{elapsed:.3f}s | "
                f"{e}"
            )

            return None

        except requests.RequestException as e:

            elapsed = (
                time.perf_counter()
                - started_at
            )

            log(
                f"[AUDIO ERROR] "
                f"{elapsed:.3f}s | "
                f"{e}"
            )

            return None

        except Exception as e:

            elapsed = (
                time.perf_counter()
                - started_at
            )

            log(
                f"[AUDIO ERROR] "
                f"{elapsed:.3f}s | "
                f"{e}"
            )

            return None


# ==================================
# Send Audio
# ==================================

def send_audio(
    chat_id,
    record
):

    audio_url = record.get(
        "audio"
    )

    if not audio_url:

        log(
            f"[AUDIO] No audio in "
            f"user's source for ghazal "
            f"#{get_ghazal_number(record)}"
        )

        return

    log(
        f"[AUDIO] Ghazal "
        f"#{get_ghazal_number(record)} "
        f"source={audio_url}"
    )

    audio_data = download_audio(
        audio_url
    )

    if not audio_data:

        log(
            "[AUDIO] Audio unavailable. "
            "Nothing will be sent."
        )

        return

    filename = (
        f"hafez_"
        f"{get_ghazal_number(record)}"
        f".ogg"
    )

    files = {
        "voice": (
            filename,
            audio_data,
            "audio/ogg"
        )
    }

    data = {
        "chat_id": chat_id
    }

    result = splus_request(
        "sendVoice",
        data=data,
        files=files
    )

    if result and result.get("ok"):

        log(
            f"[AUDIO] Sent successfully "
            f"for ghazal "
            f"#{get_ghazal_number(record)}"
        )

    else:

        log(
            f"[AUDIO] Failed to send "
            f"ghazal "
            f"#{get_ghazal_number(record)}"
        )


# ==================================
# Process Fortune
# ==================================

def process_fortune(
    chat_id,
    fortune_message_id
):

    process_started_at = time.perf_counter()

    log(
        f"[FORTUNE START] "
        f"chat_id={chat_id}"
    )

    try:

        if not HAZALS:

            log(
                "[FORTUNE] HAZALS is empty."
            )

            send_message(
                chat_id,
                "متأسفانه مجموعه غزل‌های حافظ در دسترس نیست.",
                reply_markup=MAIN_KEYBOARD
            )

            return

        record = random.choice(
            HAZALS
        )

        log(
            f"[FORTUNE] Selected ghazal "
            f"#{get_ghazal_number(record)} "
            f"record={record.get('record_id')}"
        )

        # ------------------------------
        # Fortune Text
        # ------------------------------

        log(
            "[FORTUNE] "
            "Sending fortune text..."
        )

        send_fortune(
            chat_id,
            record,
            reply_markup=REPEAT_FORTUNE_KEYBOARD
        )

        log(
            "[FORTUNE] "
            "Fortune text completed."
        )

        # ------------------------------
        # Delete control messages
        # ------------------------------

        # پیام «📜 فال حافظ» کاربر
        if fortune_message_id:

            delete_message(
                chat_id,
                fortune_message_id
            )

        # پیام «دوباره نیت کنید...»
        repeat_prompt_id = (
            get_chat_control_message(
                chat_id,
                "repeat_prompt_message_id"
            )
        )

        if repeat_prompt_id:

            delete_message(
                chat_id,
                repeat_prompt_id
            )

            clear_chat_control_message(
                chat_id,
                "repeat_prompt_message_id"
            )

        # پیام کنترلی فال حافظ دیگر دیگر لازم نیست
        clear_chat_control_message(
            chat_id,
            "fortune_message_id"
        )

        # ------------------------------
        # Audio
        # ------------------------------

        log(
            "[FORTUNE] "
            "Starting audio..."
        )

        send_audio(
            chat_id,
            record
        )

        log(
            "[FORTUNE] "
            "Audio stage completed."
        )

    except Exception as e:

        log(
            f"[FORTUNE ERROR] {e}"
        )

    finally:

        total_elapsed = (
            time.perf_counter()
            - process_started_at
        )

        log(
            f"[FORTUNE END] "
            f"Total process time: "
            f"{total_elapsed:.3f}s"
        )


# ==================================
# Webhook
# ==================================

@app.route(
    "/webhook",
    methods=["POST"]
)
def webhook():

    webhook_started_at = time.perf_counter()

    log(
        "[WEBHOOK START]"
    )

    try:

        update = request.get_json(
            silent=True
        )

        log(
            f"[UPDATE] {update}"
        )

        if not update:

            log(
                "[WEBHOOK END] Empty update."
            )

            return "OK"

        message = update.get(
            "message"
        )

        if not message:

            log(
                "[WEBHOOK END] "
                "No message in update."
            )

            return "OK"

        chat = message.get(
            "chat",
            {}
        )

        chat_id = chat.get(
            "id"
        )

        text = message.get(
            "text",
            ""
        )

        message_id = message.get(
            "message_id"
        )

        if not chat_id:

            log(
                "[WEBHOOK END] "
                "No chat_id."
            )

            return "OK"

        log(
            f"[MESSAGE] "
            f"chat_id={chat_id} "
            f"message_id={message_id} "
            f"text={text!r}"
        )

        # ------------------------------
        # /start
        # ------------------------------

        if text.strip() == "/start":

            log(
                "[WEBHOOK] "
                "Processing /start..."
            )

            result = send_message(
                chat_id,
                "🌿 به بات فال حافظ خوش آمدید.\n\n"
                "✨ ابتدا نیت کنید و سپس دکمه "
                "«📜 فال حافظ» را بزنید.",
                reply_markup=MAIN_KEYBOARD
            )

            # بعد از ارسال خوش‌آمدگویی،
            # پیام /start کاربر حذف می‌شود.
            if message_id:

                delete_message(
                    chat_id,
                    message_id
                )

            elapsed = (
                time.perf_counter()
                - webhook_started_at
            )

            log(
                f"[WEBHOOK END] "
                f"/start completed in "
                f"{elapsed:.3f}s"
            )

            return "OK"

        # ------------------------------
        # Repeat Fortune
        # ------------------------------

        if text.strip() in (
            "یک فال دیگر",
            "🌿 یک فال دیگر"
        ):

            log(
                "[WEBHOOK] "
                "Repeat fortune request received."
            )

            # --------------------------------
            # اول خود پیام «یک فال دیگر»
            # حذف می‌شود.
            # --------------------------------

            if message_id:

                delete_message(
                    chat_id,
                    message_id
                )

            # --------------------------------
            # سپس پیام «دوباره نیت کنید...»
            # نمایش داده می‌شود.
            # --------------------------------

            prompt_result = send_message(
                chat_id,
                "✨ دوباره نیت کنید و سپس دکمه "
                "«📜 فال حافظ» را بزنید.",
                reply_markup=MAIN_KEYBOARD
            )

            if (
                prompt_result
                and prompt_result.get("ok")
            ):

                prompt_message = (
                    prompt_result.get(
                        "result"
                    )
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

                    if prompt_message_id:

                        set_chat_control_message(
                            chat_id,
                            "repeat_prompt_message_id",
                            prompt_message_id
                        )

                        log(
                            f"[CONTROL] "
                            f"repeat_prompt_message_id="
                            f"{prompt_message_id}"
                        )

            elapsed = (
                time.perf_counter()
                - webhook_started_at
            )

            log(
                f"[WEBHOOK END] "
                f"Repeat fortune prompt "
                f"completed in "
                f"{elapsed:.3f}s"
            )

            return "OK"

        # ------------------------------
        # Fortune
        # ------------------------------

        if text.strip() in (
            "فال حافظ",
            "📜 فال حافظ"
        ):

            log(
                "[WEBHOOK] "
                "Fortune request received."
            )

            # پیام فعلی «📜 فال حافظ»
            # پیام کنترلی همین مرحله است.
            #
            # بعد از ارسال شعر حذف خواهد شد.
            if message_id:

                set_chat_control_message(
                    chat_id,
                    "fortune_message_id",
                    message_id
                )

            thread = threading.Thread(
                target=process_fortune,
                args=(
                    chat_id,
                    message_id
                ),
                daemon=True,
                name=f"fortune-{chat_id}"
            )

            log(
                f"[WEBHOOK] "
                f"Starting fortune thread "
                f"name={thread.name}"
            )

            thread.start()

            log(
                f"[WEBHOOK] "
                f"Fortune thread started | "
                f"alive={thread.is_alive()}"
            )

        elapsed = (
            time.perf_counter()
            - webhook_started_at
        )

        log(
            f"[WEBHOOK END] "
            f"completed in "
            f"{elapsed:.3f}s"
        )

        return "OK"

    except Exception as e:

        log(
            f"[WEBHOOK ERROR] {e}"
        )

        elapsed = (
            time.perf_counter()
            - webhook_started_at
        )

        log(
            f"[WEBHOOK END] "
            f"with error after "
            f"{elapsed:.3f}s"
        )

        return "OK"


# ==================================
# Home / Health Check
# ==================================

@app.route(
    "/",
    methods=["GET", "HEAD"]
)
def home():

    log(
        "[HEALTH] Home/Health request received."
    )

    return "Hafez Bot is running."


# ==================================
# Set Webhook
# ==================================

def set_webhook():

    log(
        f"[WEBHOOK] Setting webhook: "
        f"{WEBHOOK_URL}"
    )

    result = splus_request(
        "setWebhook",
        data={
            "url": WEBHOOK_URL
        }
    )

    log(
        f"[WEBHOOK RESULT] {result}"
    )


# ==================================
# Startup
# ==================================

log(
    "[STARTUP] Bot process starting..."
)

try:

    load_data()

except Exception as e:

    log(
        f"[DATA ERROR] {e}"
    )


log(
    "[STARTUP] Bot initialization completed."
)


# ==================================
# Local Run
# ==================================

if __name__ == "__main__":

    log(
        "[LOCAL RUN] Starting local application..."
    )

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
