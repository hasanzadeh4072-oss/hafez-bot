import os
import json
import random
import time
import threading
import re
import unicodedata
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

    session = getattr(
        _THREAD_LOCAL,
        "session",
        None
    )

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


# ==================================
# Audio Locks
# ==================================

def get_audio_download_lock(audio_url):

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


def get_audio_resolve_lock(source_url):

    with _AUDIO_RESOLVE_LOCKS_GUARD:

        lock = _AUDIO_RESOLVE_LOCKS.get(
            source_url
        )

        if lock is None:

            lock = threading.Lock()

            _AUDIO_RESOLVE_LOCKS[
                source_url
            ] = lock

        return lock


# ==================================
# Audio Cache Functions
# ==================================

def audio_cache_get(audio_url):

    global _AUDIO_CACHE_BYTES

    with _AUDIO_CACHE_LOCK:

        item = _AUDIO_CACHE.get(
            audio_url
        )

        if item is None:
            return None

        data, created_at = item

        _AUDIO_CACHE.move_to_end(
            audio_url
        )

        return data


def audio_cache_put(
    audio_url,
    data
):

    global _AUDIO_CACHE_BYTES

    if not data:
        return

    data_size = len(data)

    if data_size > AUDIO_CACHE_MAX_BYTES:
        return

    with _AUDIO_CACHE_LOCK:

        old = _AUDIO_CACHE.pop(
            audio_url,
            None
        )

        if old is not None:

            _AUDIO_CACHE_BYTES -= len(
                old[0]
            )

        _AUDIO_CACHE[audio_url] = (
            data,
            time.time()
        )

        _AUDIO_CACHE_BYTES += data_size

        while (
            len(_AUDIO_CACHE) > AUDIO_CACHE_MAX_ITEMS
            or
            _AUDIO_CACHE_BYTES > AUDIO_CACHE_MAX_BYTES
        ):

            _, old_item = (
                _AUDIO_CACHE.popitem(
                    last=False
                )
            )

            _AUDIO_CACHE_BYTES -= len(
                old_item[0]
            )


def negative_cache_get(audio_url):

    now = time.time()

    with _AUDIO_NEGATIVE_LOCK:

        timestamp = _AUDIO_NEGATIVE_CACHE.get(
            audio_url
        )

        if timestamp is None:
            return False

        if (
            now - timestamp
            >
            AUDIO_NEGATIVE_CACHE_TTL
        ):

            del _AUDIO_NEGATIVE_CACHE[
                audio_url
            ]

            return False

        return True


def negative_cache_put(audio_url):

    with _AUDIO_NEGATIVE_LOCK:

        _AUDIO_NEGATIVE_CACHE[
            audio_url
        ] = time.time()


def audio_url_cache_get(source_url):

    now = time.time()

    with _AUDIO_URL_CACHE_LOCK:

        item = _AUDIO_URL_CACHE.get(
            source_url
        )

        if item is None:
            return None

        audio_url, timestamp = item

        if (
            now - timestamp
            >
            AUDIO_URL_CACHE_TTL
        ):

            del _AUDIO_URL_CACHE[
                source_url
            ]

            return None

        return audio_url


def audio_url_cache_put(
    source_url,
    audio_url
):

    with _AUDIO_URL_CACHE_LOCK:

        _AUDIO_URL_CACHE[
            source_url
        ] = (
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
        ]
    ],
    "resize_keyboard": True,
    "one_time_keyboard": False
}


REPEAT_KEYBOARD = {
    "keyboard": [
        [
            {
                "text": "🌿 یک فال دیگر"
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
# Text Normalization
# ==================================

def normalize_text(text):

    if text is None:
        return ""

    text = str(text)

    # Unicode normalization
    text = unicodedata.normalize(
        "NFKC",
        text
    )

    # یکسان‌سازی حروف عربی و فارسی
    replacements = {
        "ي": "ی",
        "ى": "ی",
        "ك": "ک",
        "ۀ": "ه",
        "ة": "ه",
        "ؤ": "و",
        "إ": "ا",
        "أ": "ا",
        "ٱ": "ا",
    }

    for old, new in replacements.items():
        text = text.replace(
            old,
            new
        )

    # حذف کشیده
    text = text.replace(
        "ـ",
        ""
    )

    # حذف کاراکترهای نامرئی
    text = text.replace(
        "\ufeff",
        ""
    )

    text = text.replace(
        "\u200b",
        ""
    )

    text = text.replace(
        "\u200d",
        ""
    )

    # نیم‌فاصله برای تطبیق مانند فاصله معمولی باشد
    text = text.replace(
        "\u200c",
        " "
    )

    # یکسان‌سازی خط جدید
    text = text.replace(
        "\r\n",
        "\n"
    )

    text = text.replace(
        "\r",
        "\n"
    )

    # حذف حرکات عربی
    text = "".join(
        char
        for char in text
        if unicodedata.category(char) != "Mn"
    )

    # حذف علائم نگارشی
    text = re.sub(
        r"[^\w\s\u0600-\u06FF]",
        " ",
        text,
        flags=re.UNICODE
    )

    # یکسان‌سازی فاصله‌ها
    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


def normalize_poem_for_match(text):

    text = normalize_text(
        text
    )

    if not text:
        return ""

    # برای تطبیق شعر:
    # فاصله، نیم‌فاصله و خط جدید اهمیتی نداشته باشد.
    text = re.sub(
        r"\s+",
        "",
        text
    )

    return text


# ==================================
# Interpretation Helpers
# ==================================

def is_valid_interpretation(
    interpretation
):

    if interpretation is None:
        return False

    interpretation = normalize_text(
        interpretation
    )

    if not interpretation:
        return False

    lowered = interpretation.replace(
        " ",
        ""
    )

    invalid_phrases = [
        "برایاینغزل هنوزتعبیریثبتنشده",
        "برایاینغزل هنوزتعبیری ثبتنشده",
        "برایاینغزل هنوزتعبیری",
        "تعبیریثبتنشده",
        "تعبیرثبتنشده",
        "هنوزتعبیریثبتنشده",
    ]

    for phrase in invalid_phrases:

        if phrase in lowered:
            return False

    return True


def load_interpretations():

    global TABIR_MAP

    TABIR_MAP = {}

    if not os.path.exists(
        TABIR_FILE
    ):

        print(
            f"[TABIR] File not found: "
            f"{TABIR_FILE}"
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

    if not isinstance(
        data,
        list
    ):

        print(
            "[TABIR] JSON root must be a list."
        )

        return

    total_records = 0
    valid_records = 0
    skipped_records = 0

    for item in data:

        # ساختار واقعی Hafez_Tabir.json:
        #
        # {
        #     "poem": "...",
        #     "interpretation": "..."
        # }
        #
        # بنابراین نباید item.items() را
        # دوباره به عنوان رکورد پیمایش کنیم.

        if not isinstance(
            item,
            dict
        ):

            skipped_records += 1
            continue

        poem = item.get(
            "poem",
            ""
        )

        interpretation = item.get(
            "interpretation",
            ""
        )

        total_records += 1

        poem_key = normalize_poem_for_match(
            poem
        )

        interpretation = normalize_text(
            interpretation
        )

        if not poem_key:

            skipped_records += 1
            continue

        if not is_valid_interpretation(
            interpretation
        ):

            skipped_records += 1
            continue

        TABIR_MAP[
            poem_key
        ] = interpretation

        valid_records += 1

    print(
        f"[TABIR] Total records: "
        f"{total_records}"
    )

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

    poem = normalize_poem_for_match(
        record.get(
            "poem",
            ""
        )
    )

    if not poem:
        return None

    interpretation = TABIR_MAP.get(
        poem
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

    if not os.path.exists(
        DATA_FILE
    ):

        raise FileNotFoundError(
            f"Data file not found: "
            f"{DATA_FILE}"
        )

    with open(
        DATA_FILE,
        "r",
        encoding="utf-8"
    ) as f:

        data = json.load(f)

    if not isinstance(
        data,
        list
    ):

        raise ValueError(
            "HafezFilebot.json "
            "must contain a list."
        )

    result = []

    for item in data:

        if not isinstance(
            item,
            dict
        ):
            continue

        for record_id, record in item.items():

            if not isinstance(
                record,
                dict
            ):
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
                "record_id": str(
                    record_id
                ),
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

        remaining = remaining[
            cut:
        ].strip()

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


# ==================================
# Fortune Text
# ==================================

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

    for index, chunk in enumerate(
        chunks
    ):

        is_last = (
            index == len(chunks) - 1
        )

        markup = (
            REPEAT_KEYBOARD
            if is_last
            else None
        )

        result = send_message(
            chat_id,
            chunk,
            reply_markup=markup
        )

        results.append(
            result
        )

    return all(
        result is not None
        for result in results
    )


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

    # Remove duplicates
    unique = []

    seen = set()

    for url in candidates:

        if url not in seen:

            seen.add(
                url
            )

            unique.append(
                url
            )

    # Prefer Ganjoor audio
    ganjoor = [
        url
        for url in unique
        if "i.ganjoor.net"
        in url.lower()
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

            # Prefer OGG
            ogg_candidates = [
                url
                for url in candidates
                if ".ogg"
                in url.lower()
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
                f"[AUDIO] Resolved: "
                f"{selected}"
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

def check_audio_url(
    audio_url
):

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

def resolve_final_audio_url(
    record
):

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

def download_audio(
    audio_url
):

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

    return (
        f"غزل شمارهٔ {number}"
    )


def get_audio_performer(record):

    return "شعرکده
