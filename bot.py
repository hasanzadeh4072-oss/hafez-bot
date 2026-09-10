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
TABIR_FILE = "Hafez_Tabir.json"

CHANNEL_URL = "https://splus.ir/life_m23"

POETRY_CARD_BOT_URL = "http://splus.ir/PoetryCardBot"
ANONYMOUS_BOT_URL = "http://splus.ir/PayamNashenasBot"

MAX_MESSAGE_LENGTH = 4000

CONNECT_TIMEOUT = 5
READ_TIMEOUT = 15
REQUEST_TIMEOUT = (CONNECT_TIMEOUT, READ_TIMEOUT)


# ==================================
# About
# ==================================

ABOUT_TEXT = """🌿 درباره ما

از سال ۱۳۹۵ با کانال «شعرکده» در پیام‌رسان سروش پلاس همراه شما هستیم.

در «شعرکده» بخش‌های متنوعی از جمله:
📜 شعر
📖 برگی از کتاب
🎬 دیالوگ ماندگار
💬 بگو مگو
🪶 ضرب‌المثل
🎵 موزیک‌گردی
🇮🇷 ایران زیبا
را با شما به اشتراک می‌گذاریم.

خوشحال می‌شویم پذیرای شما در کانال <a href="https://splus.ir/life_m23">شعرکده</a> باشیم. 🌱

🔗 <a href="https://splus.ir/life_m23">لینک کانال شعرکده</a>"""


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


# ==================================
# Audio Cache Functions
# ==================================

def audio_cache_get(audio_url):
    global _AUDIO_CACHE_BYTES

    with _AUDIO_CACHE_LOCK:
        item = _AUDIO_CACHE.get(audio_url)

        if item is None:
            return None

        data, created_at = item

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
            _AUDIO_CACHE_BYTES -= len(old[0])

        _AUDIO_CACHE[audio_url] = (
            data,
            time.time()
        )

        _AUDIO_CACHE_BYTES += data_size

        while (
            len(_AUDIO_CACHE) > AUDIO_CACHE_MAX_ITEMS
            or _AUDIO_CACHE_BYTES > AUDIO_CACHE_MAX_BYTES
        ):
            _, old_item = _AUDIO_CACHE.popitem(last=False)
            _AUDIO_CACHE_BYTES -= len(old_item[0])


def negative_cache_get(audio_url):
    now = time.time()

    with _AUDIO_NEGATIVE_LOCK:
        timestamp = _AUDIO_NEGATIVE_CACHE.get(audio_url)

        if timestamp is None:
            return False

        if now - timestamp > AUDIO_NEGATIVE_CACHE_TTL:
            del _AUDIO_NEGATIVE_CACHE[audio_url]
            return False

        return True


def negative_cache_put(audio_url):
    with _AUDIO_NEGATIVE_LOCK:
        _AUDIO_NEGATIVE_CACHE[audio_url] = time.time()


def audio_url_cache_get(source_url):
    now = time.time()

    with _AUDIO_URL_CACHE_LOCK:
        item = _AUDIO_URL_CACHE.get(source_url)

        if item is None:
            return None

        audio_url, timestamp = item

        if now - timestamp > AUDIO_URL_CACHE_TTL:
            del _AUDIO_URL_CACHE[source_url]
            return None

        return audio_url


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
            {
                "text": "📜 فال حافظ"
            }
        ],
        [
            {
                "text": "🎨 ساختن کارت شعر"
            },
            {
                "text": "🌿 درباره ما"
            }
        ],
        [
            {
                "text": "💬 ارتباط با مدیر"
            },
            {
                "text": "📣 کانال شعرکده"
            }
        ]
    ],
    "resize_keyboard": True,
    "one_time_keyboard": False
}


# ==================================
# Data
# ==================================

HAZALS = []

TABIR_MAP = {}


# ==================================
# Interpretation Validation
# ==================================

def is_valid_interpretation(interpretation):

    if interpretation is None:
        return False

    interpretation = str(
        interpretation
    ).strip()

    if not interpretation:
        return False

    normalized = interpretation.replace(
        " ",
        ""
    )

    invalid_phrases = [
        "برایاینغزل هنوزتعبیریثبتنشده",
        "برایاینغزل هنوزتعبیری",
        "تعبیریثبتنشده",
        "تعبیرثبتنشده",
        "هنوزتعبیریثبتنشده",
    ]

    for phrase in invalid_phrases:

        if phrase in normalized:
            return False

    return True


# ==================================
# Load Interpretations
# ==================================

def load_interpretations():

    global TABIR_MAP

    TABIR_MAP = {}

    if not os.path.exists(TABIR_FILE):

        print(
            f"[TABIR] File not found: {TABIR_FILE}"
        )

        return

    try:

        with open(
            TABIR_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            data = json.load(f)

    except Exception as e:

        print(
            "[TABIR] JSON load error:",
            e
        )

        return

    if not isinstance(data, list):

        print(
            "[TABIR] JSON root must be a list."
        )

        return

    total_records = len(data)
    valid_records = 0
    skipped_records = 0

    print(
        f"[TABIR] Total records: {total_records}"
    )

    for index, item in enumerate(
        data,
        start=1
    ):

        ghazal_number = str(index)

        if not isinstance(item, dict):

            skipped_records += 1

            print(
                f"[TABIR] Skipped record #{ghazal_number}: "
                f"invalid record structure"
            )

            continue

        interpretation = item.get(
            "interpretation",
            ""
        )

        interpretation = str(
            interpretation
        ).strip()

        if not is_valid_interpretation(
            interpretation
        ):

            skipped_records += 1

            print(
                f"[TABIR] Skipped interpretation "
                f"for ghazal #{ghazal_number}"
            )

            continue

        TABIR_MAP[ghazal_number] = interpretation

        valid_records += 1

    print(
        f"[TABIR] Valid interpretations: "
        f"{valid_records}"
    )

    print(
        f"[TABIR] Skipped records: "
        f"{skipped_records}"
    )

    print(
        f"[TABIR] Map size: "
        f"{len(TABIR_MAP)}"
    )


def get_interpretation(record):

    number = get_ghazal_number(
        record
    )

    if not number:
        return None

    number = str(
        number
    ).strip()

    interpretation = TABIR_MAP.get(
        number
    )

    if is_valid_interpretation(
        interpretation
    ):

        return interpretation

    return None


# ==================================
# Load Hafez Data
# ==================================

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

        data = json.load(f)

    if not isinstance(data, list):

        raise ValueError(
            "HafezFilebot.json must contain a list."
        )

    result = []

    for item in data:

        if not isinstance(item, dict):
            continue

        for record_id, record in item.items():

            if not isinstance(record, dict):
                continue

            poem = str(
                record.get(
                    "Poem",
                    ""
                )
            ).strip()

            if not poem:
                continue

            title = str(
                record.get(
                    "Title",
                    ""
                )
            ).strip()

            source = str(
                record.get(
                    "Source",
                    ""
                )
            ).strip()

            audio = str(
                record.get(
                    "Audio",
                    ""
                )
            ).strip()

            author = str(
                record.get(
                    "Author",
                    "حافظ"
                )
            ).strip() or "حافظ"

            book = str(
                record.get(
                    "Book",
                    "غزلیات حافظ"
                )
            ).strip() or "غزلیات حافظ"

            result.append({
                "record_id": str(record_id),
                "author": author,
                "book": book,
                "poem": poem,
                "source": source,
                "title": title,
                "audio": audio
            })

    HAZALS = result

    audio_count = sum(
        1
        for item in HAZALS
        if item.get("audio")
    )

    print(
        f"[DATA] Loaded {len(HAZALS)} ghazals "
        f"with {audio_count} audio entries."
    )


# ==================================
# Soroush API
# ==================================

def splus_request(
    method,
    data=None,
    files=None
):

    url = f"{API}/{method}"

    start_time = time.time()

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


def delete_message(
    chat_id,
    message_id
):

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
        "disable_web_page_preview": "true",
        "parse_mode": "HTML"
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
# Message Helpers
# ==================================

def split_message(
    text,
    max_length=MAX_MESSAGE_LENGTH
):

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

        if cut < 0:

            cut = remaining.rfind(
                " ",
                0,
                max_length
            )

        if cut < 0:

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


# ==================================
# Ghazal Number
# ==================================

def get_ghazal_number(record):

    source = str(
        record.get(
            "source",
            ""
        )
    )

    match = re.search(
        r"/sh(\d+)",
        source,
        re.IGNORECASE
    )

    if match:
        return match.group(1)

    title = str(
        record.get(
            "title",
            ""
        )
    )

    match = re.search(
        r"\d+",
        title
    )

    if match:
        return match.group(0)

    record_id = str(
        record.get(
            "record_id",
            ""
        )
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

    if not poem:
        return ""

    poem = str(poem)

    poem = poem.replace(
        "\r\n",
        "\n"
    )

    poem = poem.replace(
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

    number = get_ghazal_number(
        record
    )

    poem = clean_poem(
        record.get(
            "poem",
            ""
        )
    )

    interpretation = get_interpretation(
        record
    )

    text = (
        "فال حافظ\n"
        f"شماره غزل {number}\n\n"
        f"{poem}\n\n"
        "────────────\n\n"
        "🌌 تعبیر\n\n"
    )

    if interpretation:

        text += (
            f"{interpretation}\n\n"
        )

    else:

        text += (
            "بات تعبیری برای این غزل ندارد.\n\n"
        )

    text += (
        f"{CHANNEL_URL} 🌱"
    )

    return text


def send_fortune(
    chat_id,
    record
):

    text = format_fortune(
        record
    )

    chunks = split_message(
        text
    )

    results = []

    for chunk in chunks:

        result = send_message(
            chat_id,
            chunk,
            reply_markup=MAIN_KEYBOARD
        )

        results.append(
            result
        )

    if not all(
        result is not None
        for result in results
    ):
        return False

    result = send_message(
        chat_id,
        "🌿 نیت کنید و روی «📜 فال حافظ» بزنید.",
        reply_markup=MAIN_KEYBOARD
    )

    return result is not None


# ==================================
# Audio URL Extraction
# ==================================

def extract_audio_urls(
    html,
    base_url
):

    candidates = []

    absolute_urls = re.findall(
        r'https?://[^"\'>\s]+?\.(?:ogg|mp3)(?:\?[^"\'>\s]*)?',
        html,
        re.IGNORECASE
    )

    for url in absolute_urls:

        url = url.replace(
            "&amp;",
            "&"
        )

        candidates.append(
            url
        )

    relative_urls = re.findall(
        r'["\']([^"\']+\.(?:ogg|mp3)(?:\?[^"\']*)?)["\']',
        html,
        re.IGNORECASE
    )

    for relative in relative_urls:

        full_url = urljoin(
            base_url,
            relative
        )

        candidates.append(
            full_url
        )

    unique = []

    seen = set()

    for url in candidates:

        if url not in seen:

            seen.add(url)
            unique.append(url)

    ganjoor = [
        url
        for url in unique
        if "i.ganjoor.net" in url.lower()
    ]

    if ganjoor:
        return ganjoor

    return unique


# ==================================
# Resolve Audio From Source
# ==================================

def resolve_audio_from_source(
    source_url
):

    if not source_url:
        return None

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

        try:

            print(
                f"[AUDIO] Resolving source: "
                f"{source_url}"
            )

            response = get_session().get(
                source_url,
                timeout=REQUEST_TIMEOUT
            )

            if response.status_code != 200:

                print(
                    "[AUDIO] Source page status:",
                    response.status_code
                )

                return None

            candidates = extract_audio_urls(
                response.text,
                source_url
            )

            if not candidates:

                print(
                    "[AUDIO] No audio URL found."
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
                f"[AUDIO] Resolved: {selected}"
            )

            return selected

        except Exception as e:

            print(
                "[AUDIO] Resolve error:",
                e
            )

            return None


# ==================================
# Check Audio URL
# ==================================

def check_audio_url(audio_url):

    if not audio_url:
        return False

    try:

        response = get_session().get(
            audio_url,
            stream=True,
            timeout=REQUEST_TIMEOUT
        )

        return response.status_code == 200

    except Exception as e:

        print(
            "[AUDIO] Check error:",
            e
        )

        return False


# ==================================
# Resolve Final Audio
# ==================================

def resolve_final_audio_url(record):

    audio_url = str(
        record.get(
            "audio",
            ""
        )
    ).strip()

    if audio_url:

        if not negative_cache_get(
            audio_url
        ):

            if check_audio_url(
                audio_url
            ):

                return audio_url

            negative_cache_put(
                audio_url
            )

    source_url = str(
        record.get(
            "source",
            ""
        )
    ).strip()

    if source_url:

        return resolve_audio_from_source(
            source_url
        )

    return None


# ==================================
# Download Audio
# ==================================

def download_audio(audio_url):

    if not audio_url:
        return None

    cached = audio_cache_get(
        audio_url
    )

    if cached is not None:

        print(
            "[AUDIO] Cache HIT"
        )

        return cached

    if negative_cache_get(
        audio_url
    ):

        print(
            "[AUDIO] Negative cache HIT"
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

            print(
                "[AUDIO] Cache HIT after lock"
            )

            return cached

        try:

            print(
                f"[AUDIO] Downloading: "
                f"{audio_url}"
            )

            response = get_session().get(
                audio_url,
                timeout=REQUEST_TIMEOUT
            )

            if response.status_code == 404:

                print(
                    "[AUDIO] 404"
                )

                negative_cache_put(
                    audio_url
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

                print(
                    "[AUDIO] Empty audio response."
                )

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

    number = get_ghazal_number(
        record
    )

    return f"غزل شمارهٔ {number}"


def get_audio_performer(record):

    return "شعرکده سروش پلاس"


# ==================================
# Send Audio
# ==================================

def send_audio(
    chat_id,
    record
):

    audio_url = resolve_final_audio_url(
        record
    )

    if not audio_url:

        print(
            "[AUDIO] No audio URL available."
        )

        return None

    audio_data = download_audio(
        audio_url
    )

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

    number = get_ghazal_number(
        record
    )

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
        f"[AUDIO] Sending Audio | "
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
# Chat Control State
# ==================================

CHAT_CONTROL_MESSAGES = {}

CHAT_CONTROL_LOCK = threading.RLock()


def set_control_message(
    chat_id,
    message_id
):

    with CHAT_CONTROL_LOCK:

        CHAT_CONTROL_MESSAGES[
            str(chat_id)
        ] = message_id


def get_control_message(
    chat_id
):

    with CHAT_CONTROL_LOCK:

        return CHAT_CONTROL_MESSAGES.get(
            str(chat_id)
        )


def remove_control_message(
    chat_id
):

    with CHAT_CONTROL_LOCK:

        return CHAT_CONTROL_MESSAGES.pop(
            str(chat_id),
            None
        )


def clear_control_message(
    chat_id
):

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

        number = get_ghazal_number(
            record
        )

        print(
            f"[FORTUNE] Selected ghazal #{number}"
        )

        interpretation = get_interpretation(
            record
        )

        if interpretation:

            print(
                f"[TABIR] Found interpretation "
                f"for ghazal #{number}"
            )

        else:

            print(
                f"[TABIR] No interpretation "
                f"for ghazal #{number}"
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

        message = update.get(
            "message"
        ) or update.get(
            "edited_message"
        )

        if not message:
            return "ok"

        chat = message.get(
            "chat"
        ) or {}

        chat_id = chat.get(
            "id"
        )

        if chat_id is None:
            return "ok"

        text = str(
            message.get(
                "text",
                ""
            )
        ).strip()

        message_id = message.get(
            "message_id"
        )

        # ------------------------------
        # /start
        # ------------------------------

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

            if result:

                sent_message_id = None

                if isinstance(
                    result,
                    dict
                ):

                    result_data = result.get(
                        "result"
                    )

                    if isinstance(
                        result_data,
                        dict
                    ):

                        sent_message_id = result_data.get(
                            "message_id"
                        )

                if sent_message_id:

                    set_control_message(
                        chat_id,
                        sent_message_id
                    )

            if message_id:

                delete_message(
                    chat_id,
                    message_id
                )

            return "ok"

        # ------------------------------
        # Fortune
        # ------------------------------

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

        # ------------------------------
        # Poetry Card Bot
        # ------------------------------

        if text == "🎨 ساختن کارت شعر":

            if message_id:

                delete_message(
                    chat_id,
                    message_id
                )

            send_message(
                chat_id,
                (
                    "🎨 <a href=\"http://splus.ir/PoetryCardBot\">کارت شعر</a>\n\n"
                    "شعر مورد علاقه‌تان را به یک کارت شعر زیبا و اختصاصی تبدیل کنید. ✨\n\n"
                    "برای ساخت کارت، وارد بات "
                    "<a href=\"http://splus.ir/PoetryCardBot\">کارت شعر</a> شوید.\n\n"
                    "🔗 <a href=\"http://splus.ir/PoetryCardBot\">http://splus.ir/PoetryCardBot</a>"
                ),
                reply_markup=MAIN_KEYBOARD
            )

            return "ok"

        # ------------------------------
        # About
        # ------------------------------

        if text == "🌿 درباره ما":

            if message_id:

                delete_message(
                    chat_id,
                    message_id
                )

            send_message(
                chat_id,
                ABOUT_TEXT,
                reply_markup=MAIN_KEYBOARD
            )

            return "ok"

        # ------------------------------
        # Contact Admin
        # ------------------------------

        if text == "💬 ارتباط با مدیر":

            if message_id:

                delete_message(
                    chat_id,
                    message_id
                )

            send_message(
                chat_id,
                (
                    "💬 <a href=\"http://splus.ir/PayamNashenasBot\">پیام ناشناس شعرکده</a>\n\n"
                    "اگر پیشنهاد، انتقاد یا پیامی برای مدیر بات دارید، "
                    "می‌توانید از طریق "
                    "<a href=\"http://splus.ir/PayamNashenasBot\">پیام ناشناس شعرکده</a> "
                    "با ما در ارتباط باشید.\n\n"
                    "🔗 <a href=\"http://splus.ir/PayamNashenasBot\">http://splus.ir/PayamNashenasBot</a>"
                ),
                reply_markup=MAIN_KEYBOARD
            )

            return "ok"

        # ------------------------------
        # Poetry Channel
        # ------------------------------

        if text == "📣 کانال شعرکده":

            if message_id:

                delete_message(
                    chat_id,
                    message_id
                )

            send_message(
                chat_id,
                (
                    "📣 <a href=\"https://splus.ir/life_m23\">کانال شعرکده</a>\n\n"
                    "برای ورود مستقیم به <a href=\"https://splus.ir/life_m23\">کانال شعرکده</a> "
                    "از لینک زیر استفاده کنید.\n\n"
                    "🔗 <a href=\"https://splus.ir/life_m23\">https://splus.ir/life_m23</a>"
                ),
                reply_markup=MAIN_KEYBOARD
            )

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


try:

    load_interpretations()

except Exception as e:

    print(
        "[STARTUP] TABIR ERROR:",
        e
    )

    TABIR_MAP = {}


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



