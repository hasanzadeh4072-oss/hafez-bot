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


# ============================================================
# Configuration
# ============================================================

TOKEN = os.environ.get("SOROUSH_TOKEN")

if not TOKEN:
    raise RuntimeError("SOROUSH_TOKEN environment variable is not set.")

API = f"https://api.splus.ir/bot{TOKEN}"

WEBHOOK_URL = "https://hafez-bot.onrender.com/webhook"

DATA_FILE = "HafezFilebot.json"

CHANNEL_URL = "https://splus.ir/@LIFE_M23"

MAX_MESSAGE_LENGTH = 4000

REQUEST_TIMEOUT = 30


# ============================================================
# Audio Cache Configuration
# ============================================================

# حداکثر تعداد فایل صوتی که در RAM نگهداری می‌شود.
# مقدار کم انتخاب شده تا مصرف RAM کنترل شود.
AUDIO_CACHE_MAX_ITEMS = 5

# حداکثر حجم کل کش صوتی در RAM
# 50 MB
AUDIO_CACHE_MAX_BYTES = 50 * 1024 * 1024


# ============================================================
# Global data
# ============================================================

HAZALS = []


# ============================================================
# HTTP Session
# ============================================================

# requests.Session در بین Threadهای مختلف مستقیماً share نمی‌شود.
# برای هر Thread یک Session مستقل ساخته می‌شود.
_thread_local = threading.local()


def get_session():
    """
    Return one requests.Session per worker thread.

    این کار باعث می‌شود connectionها تا حد امکان reuse شوند
    و برای هر درخواست یک connection جدید ساخته نشود.
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

    return session


# ============================================================
# Audio Cache
# ============================================================

_AUDIO_CACHE = OrderedDict()

_AUDIO_CACHE_BYTES = 0

_AUDIO_CACHE_LOCK = threading.Lock()

# برای جلوگیری از دانلود هم‌زمان یک URL یکسان
_AUDIO_DOWNLOAD_LOCKS = {}

_AUDIO_DOWNLOAD_LOCKS_GUARD = threading.Lock()


def get_audio_download_lock(audio_url):
    """
    Return a lock dedicated to one audio URL.
    """

    with _AUDIO_DOWNLOAD_LOCKS_GUARD:

        lock = _AUDIO_DOWNLOAD_LOCKS.get(
            audio_url
        )

        if lock is None:

            lock = threading.Lock()

            _AUDIO_DOWNLOAD_LOCKS[audio_url] = lock

        return lock


def get_cached_audio(audio_url):
    """
    Get audio bytes from cache.

    LRU behavior:
    هر فایلی که استفاده شود به انتهای cache منتقل می‌شود.
    """

    if not audio_url:
        return None

    with _AUDIO_CACHE_LOCK:

        item = _AUDIO_CACHE.get(
            audio_url
        )

        if item is None:
            return None

        # Move to end = most recently used
        _AUDIO_CACHE.move_to_end(
            audio_url
        )

        return item


def cache_audio(audio_url, audio_data):
    """
    Store audio in bounded LRU cache.
    """

    global _AUDIO_CACHE_BYTES

    if not audio_url or not audio_data:
        return

    data_size = len(audio_data)

    # فایل خیلی بزرگ را اصلاً وارد RAM نکن.
    if data_size > AUDIO_CACHE_MAX_BYTES:
        print(
            f"[AUDIO CACHE] File too large to cache: "
            f"{data_size} bytes"
        )
        return

    with _AUDIO_CACHE_LOCK:

        # اگر قبلاً وجود داشته، ابتدا حجم قبلی کم شود.
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

        # حذف قدیمی‌ترین فایل‌ها تا محدودیت حجم رعایت شود.
        while (
            len(_AUDIO_CACHE) > AUDIO_CACHE_MAX_ITEMS
            or _AUDIO_CACHE_BYTES > AUDIO_CACHE_MAX_BYTES
        ):

            _, removed_data = _AUDIO_CACHE.popitem(
                last=False
            )

            _AUDIO_CACHE_BYTES -= len(
                removed_data
            )

        print(
            f"[AUDIO CACHE] Stored: "
            f"{data_size} bytes | "
            f"items={len(_AUDIO_CACHE)} | "
            f"total={_AUDIO_CACHE_BYTES} bytes"
        )


# ============================================================
# Reply Keyboard
# ============================================================

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


# ============================================================
# Load Hafez JSON
# ============================================================

def load_data():

    global HAZALS

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

    print(
        f"[DATA] Loaded {len(HAZALS)} ghazals."
    )


# ============================================================
# Soroush API helper
# ============================================================

def splus_request(
    method,
    data=None,
    files=None
):

    url = f"{API}/{method}"

    try:

        session = get_session()

        response = session.post(
            url,
            data=data,
            files=files,
            timeout=REQUEST_TIMEOUT
        )

        status_code = response.status_code

        # فقط بخش کوتاه پاسخ در لاگ موفقیت
        # برای جلوگیری از لاگ‌های حجیم
        response_preview = response.text[:300]

        if response.ok:

            print(
                f"[SPLUS] {method}: "
                f"{status_code} "
                f"{response_preview}"
            )

        else:

            print(
                f"[SPLUS ERROR] {method}: "
                f"{status_code} "
                f"{response_preview}"
            )

        response.raise_for_status()

        try:

            return response.json()

        except ValueError:

            print(
                f"[SPLUS ERROR] {method}: "
                "Invalid JSON response."
            )

            return None

    except requests.RequestException as e:

        print(
            f"[SPLUS ERROR] {method}: {e}"
        )

        return None

    except Exception as e:

        print(
            f"[SPLUS ERROR] {method}: {e}"
        )

        return None


# ============================================================
# Send text message
# ============================================================

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


# ============================================================
# Delete message
# ============================================================

def delete_message(
    chat_id,
    message_id
):

    if not message_id:
        return None

    return splus_request(
        "deleteMessage",
        data={
            "chat_id": chat_id,
            "message_id": message_id
        }
    )


# ============================================================
# Split long messages
# ============================================================

def split_message(
    text,
    max_length=MAX_MESSAGE_LENGTH
):

    if not text:
        return []

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
        chunks.append(
            remaining
        )

    return chunks


# ============================================================
# Extract ghazal number
# ============================================================

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


# ============================================================
# Clean poem
# ============================================================

def clean_poem(poem):

    if not poem:
        return ""

    return poem.replace(
        "\r\n",
        "\n"
    ).replace(
        "\r",
        "\n"
    ).strip()


# ============================================================
# Build fortune text
# ============================================================

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

    text = (
        f"فال حافظ\n"
        f"شماره غزل {number}\n\n"
        f"{poem}\n\n"
        f"منبع گنجور\n"
        f"{record.get('source', '')}\n"
        f"@LIFE_M23 🌱"
    )

    return text


# ============================================================
# Send ghazal
# ============================================================

def send_fortune(
    chat_id,
    record
):

    fortune_text = build_fortune(
        record
    )

    ghazal_number = get_ghazal_number(
        record
    )

    print(
        f"[FORTUNE] "
        f"Ghazal #{ghazal_number} "
        f"record={record.get('record_id')}"
    )

    print(
        f"[FORTUNE] Final text length="
        f"{len(fortune_text)}"
    )

    chunks = split_message(
        fortune_text
    )

    print(
        f"[MESSAGE] "
        f"length={len(fortune_text)} "
        f"chunks={len(chunks)}"
    )

    for index, chunk in enumerate(chunks):

        send_message(
            chat_id,
            chunk
        )

        # همان رفتار نسخه اولیه حفظ شده.
        if index < len(chunks) - 1:
            time.sleep(0.15)


# ============================================================
# Download user's own audio
# ============================================================

def download_audio(
    audio_url
):

    if not audio_url:
        return None

    # ========================================================
    # Cache lookup
    # ========================================================

    cached_audio = get_cached_audio(
        audio_url
    )

    if cached_audio is not None:

        print(
            f"[AUDIO CACHE] HIT: "
            f"{audio_url}"
        )

        return cached_audio

    print(
        f"[AUDIO CACHE] MISS: "
        f"{audio_url}"
    )

    # ========================================================
    # Prevent duplicate simultaneous downloads
    # ========================================================

    download_lock = get_audio_download_lock(
        audio_url
    )

    with download_lock:

        # ممکن است Thread دیگری قبل از گرفتن lock
        # فایل را دانلود و cache کرده باشد.
        cached_audio = get_cached_audio(
            audio_url
        )

        if cached_audio is not None:

            print(
                f"[AUDIO CACHE] HIT after lock: "
                f"{audio_url}"
            )

            return cached_audio

        print(
            f"[AUDIO] Downloading ONLY user's source: "
            f"{audio_url}"
        )

        try:

            session = get_session()

            response = session.get(
                audio_url,
                timeout=REQUEST_TIMEOUT
            )

            response.raise_for_status()

            content = response.content

            if not content:

                print(
                    "[AUDIO] Empty audio response."
                )

                return None

            print(
                f"[AUDIO] Downloaded "
                f"{len(content)} bytes."
            )

            # ذخیره در کش با محدودیت RAM
            cache_audio(
                audio_url,
                content
            )

            return content

        except requests.RequestException as e:

            print(
                f"[AUDIO ERROR] Download failed: {e}"
            )

            return None

        except Exception as e:

            print(
                f"[AUDIO ERROR] {e}"
            )

            return None


# ============================================================
# Send audio
# ============================================================

def send_audio(
    chat_id,
    record
):

    audio_url = record.get(
        "audio"
    )

    if not audio_url:

        print(
            f"[AUDIO] No audio in user's source "
            f"for ghazal #{get_ghazal_number(record)}"
        )

        return

    ghazal_number = get_ghazal_number(
        record
    )

    print(
        f"[AUDIO] Ghazal #{ghazal_number} "
        f"source={audio_url}"
    )

    audio_data = download_audio(
        audio_url
    )

    if not audio_data:

        print(
            "[AUDIO] Audio unavailable. "
            "Nothing will be sent."
        )

        return

    filename = (
        f"hafez_"
        f"{ghazal_number}"
        f".mp3"
    )

    files = {
        "audio": (
            filename,
            audio_data,
            "audio/mpeg"
        )
    }

    data = {
        "chat_id": chat_id,
        "title": (
            f"حافظ - غزل "
            f"{ghazal_number}"
        ),
        "performer": "حافظ",
    }

    result = splus_request(
        "sendAudio",
        data=data,
        files=files
    )

    if result and result.get("ok"):

        print(
            f"[AUDIO] Sent successfully "
            f"for ghazal #{ghazal_number}"
        )

    else:

        print(
            f"[AUDIO] Failed to send "
            f"ghazal #{ghazal_number}"
        )


# ============================================================
# Fortune process
# ============================================================

def process_fortune(
    chat_id
):

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

    ghazal_number = get_ghazal_number(
        record
    )

    print(
        f"[FORTUNE] Selected "
        f"ghazal #{ghazal_number} "
        f"record={record.get('record_id')}"
    )

    result = send_message(
        chat_id,
        "🌿 نیت کنید...\n\n"
        "در حال گرفتن فال حافظ",
        reply_markup=MAIN_KEYBOARD
    )

    temporary_message_id = None

    if result and result.get("ok"):

        try:

            temporary_message_id = (
                result["result"]["message_id"]
            )

        except (
            KeyError,
            TypeError
        ):

            temporary_message_id = None

    # این زمان عمداً حفظ شده.
    time.sleep(0.4)

    if temporary_message_id:

        delete_message(
            chat_id,
            temporary_message_id
        )

    send_fortune(
        chat_id,
        record
    )

    send_audio(
        chat_id,
        record
    )


# ============================================================
# Webhook
# ============================================================

@app.route(
    "/webhook",
    methods=["POST"]
)
def webhook():

    try:

        update = request.get_json(
            silent=True
        )

        print(
            f"[UPDATE] {update}"
        )

        if not update:
            return "OK"

        message = update.get(
            "message"
        )

        if not message:
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

        if not chat_id:
            return "OK"

        print(
            f"[MESSAGE] "
            f"chat_id={chat_id} "
            f"text={text!r}"
        )

        normalized_text = text.strip()

        # ====================================================
        # /start
        # ====================================================

        if normalized_text == "/start":

            send_message(
                chat_id,
                "🌿 به فال حافظ خوش آمدید.\n\n"
                "برای گرفتن فال، دکمه «📜 فال حافظ» را بزنید.",
                reply_markup=MAIN_KEYBOARD
            )

            return "OK"

        # ====================================================
        # Fortune command
        # ====================================================

        if normalized_text in (
            "فال حافظ",
            "📜 فال حافظ"
        ):

            thread = threading.Thread(
                target=process_fortune,
                args=(chat_id,),
                daemon=True
            )

            thread.start()

        return "OK"

    except Exception as e:

        print(
            f"[WEBHOOK ERROR] {e}"
        )

        return "OK"


# ============================================================
# Home
# ============================================================

@app.route(
    "/",
    methods=["GET", "HEAD"]
)
def home():

    return "Hafez Bot is running."


# ============================================================
# Set webhook
# ============================================================

def set_webhook():

    print(
        f"[WEBHOOK] Setting webhook: "
        f"{WEBHOOK_URL}"
    )

    result = splus_request(
        "setWebhook",
        data={
            "url": WEBHOOK_URL
        }
    )

    print(
        f"[WEBHOOK RESULT] {result}"
    )


# ============================================================
# Startup
# ============================================================

try:

    load_data()

except Exception as e:

    print(
        f"[DATA ERROR] {e}"
    )


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



