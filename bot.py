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


# =========================================================
# Configuration
# =========================================================

TOKEN = os.environ.get("SOROUSH_TOKEN")

if not TOKEN:
    raise RuntimeError("SOROUSH_TOKEN environment variable is not set.")

API = f"https://api.splus.ir/bot{TOKEN}"

WEBHOOK_URL = "https://hafez-bot.onrender.com/webhook"

DATA_FILE = "HafezFilebot.json"
TABIR_FILE = "Hafez_Tabir.json"

CHANNEL_URL = "https://splus.ir/life_m23"
POETRY_CARD_BOT_URL = "https://splus.ir/PoetryCardBot"
ANONYMOUS_BOT_URL = "https://splus.ir/PayamNashenasBot"

CONNECT_TIMEOUT = 5
READ_TIMEOUT = 15

REQUEST_TIMEOUT = (CONNECT_TIMEOUT, READ_TIMEOUT)


# =========================================================
# Audio cache configuration
# =========================================================

AUDIO_CACHE_MAX_ITEMS = 5
AUDIO_CACHE_MAX_BYTES = 50 * 1024 * 1024

AUDIO_NEGATIVE_TTL = 10 * 60
AUDIO_URL_CACHE_TTL = 60 * 60

_AUDIO_CACHE = OrderedDict()
_AUDIO_CACHE_BYTES = 0

_AUDIO_NEGATIVE_CACHE = {}
_AUDIO_URL_CACHE = {}

_AUDIO_DOWNLOAD_LOCKS = {}
_AUDIO_DOWNLOAD_LOCKS_GUARD = threading.Lock()

_AUDIO_RESOLVE_LOCKS = {}
_AUDIO_RESOLVE_LOCKS_GUARD = threading.Lock()


# =========================================================
# Thread local HTTP session
# =========================================================

_THREAD_LOCAL = threading.local()


def get_session():
    session = getattr(_THREAD_LOCAL, "session", None)

    if session is None:
        session = requests.Session()

        session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 "
                    "(Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 "
                    "(KHTML, like Gecko) "
                    "Chrome/124.0 Safari/537.36"
                )
            }
        )

        _THREAD_LOCAL.session = session

    return session


# =========================================================
# Global data
# =========================================================

HAZALS = []
TABIR_MAP = {}

DATA_LOCK = threading.RLock()

CHAT_CONTROL_MESSAGES = {}
CHAT_CONTROL_LOCK = threading.RLock()


# =========================================================
# Keyboards
# =========================================================

MAIN_KEYBOARD = {
    "keyboard": [
        [
            {"text": "📜 فال حافظ"},
            {"text": "🎨 ساختن کارت شعر"},
        ],
        [
            {"text": "🌿 درباره ما"},
            {"text": "💬 ارتباط با مدیر"},
        ],
        [
            {"text": "📣 کانال شعرکده"},
        ],
    ],
    "resize_keyboard": True,
}


FORTUNE_KEYBOARD = {
    "keyboard": [
        [
            {"text": "🌿 یک فال دیگر"},
            {"text": "🎨 ساختن کارت شعر"},
        ],
        [
            {"text": "🌿 درباره ما"},
            {"text": "💬 ارتباط با مدیر"},
        ],
        [
            {"text": "📣 کانال شعرکده"},
        ],
    ],
    "resize_keyboard": True,
}


# =========================================================
# About text
# =========================================================

ABOUT_TEXT = (
    "<b>🌿 درباره بات فال حافظ</b>\n\n"
    "با این بات می‌توانید به صورت تصادفی فال حافظ بگیرید "
    "و غزل و تعبیر مربوط به آن را دریافت کنید.\n\n"
    "🎨 برای ساخت کارت شعر می‌توانید از بات "
    f'<a href="{POETRY_CARD_BOT_URL}">کارت شعر</a> استفاده کنید.\n\n'
    "📣 کانال شعرکده:\n"
    f'<a href="{CHANNEL_URL}">{CHANNEL_URL}</a>'
)


# =========================================================
# General helpers
# =========================================================

def normalize_text(value):
    if value is None:
        return ""

    return str(value).strip()


def clean_poem(poem):
    poem = normalize_text(poem)

    poem = poem.replace("\r\n", "\n")
    poem = poem.replace("\r", "\n")

    poem = re.sub(r"\n{3,}", "\n\n", poem)

    return poem.strip()


def api_success(result):
    """
    تنها معیار موفقیت API:
    پاسخ باید dict باشد و مقدار ok دقیقاً True باشد.
    """

    return (
        isinstance(result, dict)
        and result.get("ok") is True
    )


# =========================================================
# Soroush API
# =========================================================

def splus_request(method, data=None, files=None):
    url = f"{API}/{method}"

    started = time.time()

    try:
        response = get_session().post(
            url,
            data=data,
            files=files,
            timeout=REQUEST_TIMEOUT,
        )

        elapsed = time.time() - started

        print(
            f"[API] {method} "
            f"status={response.status_code} "
            f"time={elapsed:.2f}s"
        )

        try:
            result = response.json()

        except ValueError:
            result = {
                "ok": bool(response.ok),
                "status_code": response.status_code,
                "text": response.text[:1000],
            }

        if not api_success(result):
            print(
                f"[API-FAIL] {method}: "
                f"{result}"
            )

        return result

    except Exception as e:
        elapsed = time.time() - started

        print(
            f"[API-ERROR] {method} "
            f"time={elapsed:.2f}s "
            f"error={e}"
        )

        return None


def send_message(chat_id, text, keyboard=None):
    data = {
        "chat_id": str(chat_id),
        "text": text,
        "parse_mode": "HTML",
    }

    if keyboard is not None:
        data["reply_markup"] = json.dumps(
            keyboard,
            ensure_ascii=False,
        )

    return splus_request(
        "sendMessage",
        data=data,
    )


def delete_message(chat_id, message_id):
    if not chat_id or not message_id:
        return None

    return splus_request(
        "deleteMessage",
        data={
            "chat_id": str(chat_id),
            "message_id": str(message_id),
        },
    )


# =========================================================
# Data loading
# =========================================================

def get_record_number(record):
    """
    شماره معتبر غزل را فقط با اولویت Source پیدا می‌کند.

    مثال:
        /sh265
        -> 265

    عنوان و record_id فقط به عنوان fallback استفاده می‌شوند
    تا در صورت خراب بودن Source بات از کار نیفتد.
    """

    source = normalize_text(record.get("source"))

    match = re.search(
        r"/sh(\d+)(?:\D|$)",
        source,
        flags=re.IGNORECASE,
    )

    if match:
        return match.group(1)

    title = normalize_text(record.get("title"))

    match = re.search(
        r"(?<!\d)(\d{1,4})(?!\d)",
        title,
    )

    if match:
        return match.group(1)

    record_id = normalize_text(record.get("record_id"))

    match = re.search(
        r"(?<!\d)(\d{1,4})(?!\d)",
        record_id,
    )

    if match:
        return match.group(1)

    return ""


def load_data():
    global HAZALS

    print(f"[DATA] Loading {DATA_FILE}")

    with open(
        DATA_FILE,
        "r",
        encoding="utf-8",
    ) as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError(
            f"{DATA_FILE} must contain a list."
        )

    loaded = []

    for item in data:

        if not isinstance(item, dict):
            continue

        for record_id, record in item.items():

            if not isinstance(record, dict):
                continue

            poem = clean_poem(
                record.get("Poem", "")
            )

            if not poem:
                continue

            normalized = {
                "record_id": normalize_text(record_id),
                "author": normalize_text(
                    record.get("Author")
                ),
                "book": normalize_text(
                    record.get("Book")
                ),
                "poem": poem,
                "source": normalize_text(
                    record.get("Source")
                ),
                "title": normalize_text(
                    record.get("Title")
                ),
                "audio": normalize_text(
                    record.get("Audio")
                ),
            }

            normalized["ghazal_number"] = get_record_number(
                normalized
            )

            loaded.append(normalized)

    with DATA_LOCK:
        HAZALS = loaded

    audio_count = sum(
        1
        for record in loaded
        if record.get("audio")
    )

    print(
        f"[DATA] Loaded {len(loaded)} ghazals "
        f"and {audio_count} direct audio entries."
    )


# =========================================================
# Interpretation loading
# =========================================================

def is_valid_interpretation(value):
    if not isinstance(value, str):
        return False

    value = value.strip()

    if not value:
        return False

    invalid_phrases = [
        "برای این غزل هنوز تعبیری ثبت نشده",
        "برای این غزل تعبیری ثبت نشده",
        "تعبیری برای این غزل ثبت نشده",
    ]

    for phrase in invalid_phrases:
        if phrase in value:
            return False

    return True


def extract_explicit_ghazal_number(item):
    """
    اگر در آینده فایل تعبیر دارای شماره صریح شد،
    این تابع آن را تشخیص می‌دهد.

    ترتیب اولویت:
    number
    ghazal_number
    ghazal
    شماره
    شماره غزل
    """

    possible_keys = [
        "number",
        "ghazal_number",
        "ghazal",
        "شماره",
        "شماره غزل",
    ]

    for key in possible_keys:

        value = item.get(key)

        if value is None:
            continue

        match = re.search(
            r"(?<!\d)(\d{1,4})(?!\d)",
            str(value),
        )

        if match:
            return match.group(1)

    return ""


def load_interpretations():
    global TABIR_MAP

    print(f"[TABIR] Loading {TABIR_FILE}")

    with open(
        TABIR_FILE,
        "r",
        encoding="utf-8",
    ) as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError(
            f"{TABIR_FILE} must contain a list."
        )

    mapping = {}

    explicit_numbers_found = 0
    sequential_numbers_used = 0

    for index, item in enumerate(
        data,
        start=1,
    ):

        if not isinstance(item, dict):
            continue

        interpretation = item.get(
            "interpretation",
            "",
        )

        if not is_valid_interpretation(
            interpretation
        ):
            continue

        explicit_number = extract_explicit_ghazal_number(
            item
        )

        if explicit_number:
            ghazal_number = explicit_number
            explicit_numbers_found += 1

        else:
            # فایل فعلی شماره صریح ندارد.
            # در این حالت ترتیب فایل = شماره غزل
            ghazal_number = str(index)
            sequential_numbers_used += 1

        if ghazal_number in mapping:
            print(
                f"[TABIR-WARNING] Duplicate interpretation "
                f"for ghazal {ghazal_number}; "
                f"keeping the first one."
            )
            continue

        mapping[ghazal_number] = interpretation.strip()

    with DATA_LOCK:
        TABIR_MAP = mapping

    print(
        f"[TABIR] Loaded {len(mapping)} interpretations."
    )

    print(
        f"[TABIR] Explicit numbers: "
        f"{explicit_numbers_found}"
    )

    print(
        f"[TABIR] Sequential numbers: "
        f"{sequential_numbers_used}"
    )

    # -----------------------------------------------------
    # Basic consistency validation
    # -----------------------------------------------------

    with DATA_LOCK:
        data_numbers = {
            record.get("ghazal_number")
            for record in HAZALS
            if record.get("ghazal_number")
        }

    if data_numbers:

        matched = len(
            data_numbers.intersection(
                mapping.keys()
            )
        )

        print(
            f"[TABIR] Ghazal number coverage: "
            f"{matched}/{len(data_numbers)}"
        )

        missing = sorted(
            data_numbers - mapping.keys(),
            key=lambda x: int(x)
            if str(x).isdigit()
            else 999999,
        )

        if missing:
            print(
                f"[TABIR-WARNING] "
                f"No interpretation for "
                f"{len(missing)} ghazal(s)."
            )


def get_interpretation(record):
    number = normalize_text(
        record.get("ghazal_number")
    )

    if not number:
        number = get_record_number(record)

    if not number:
        return None

    with DATA_LOCK:
        return TABIR_MAP.get(number)


# =========================================================
# Fortune formatting
# =========================================================

def format_fortune(record):
    number = normalize_text(
        record.get("ghazal_number")
    )

    if not number:
        number = "؟"

    poem = clean_poem(
        record.get("poem", "")
    )

    interpretation = get_interpretation(
        record
    )

    if not interpretation:
        interpretation = (
            "بات تعبیری برای این غزل ندارد."
        )

    return (
        f"<b>📜 فال حافظ</b>\n"
        f"<b>شماره غزل {number}</b>\n\n"
        f"{poem}\n\n"
        f"━━━━━━━━━━━━━━\n"
        f"<b>🌌 تعبیر</b>\n\n"
        f"{interpretation}\n\n"
        f"<b>⚠️ توجه:</b> فال و طالع‌بینی جنبه سرگرمی دارد "
        f"و پیشنهاد نمی‌شود بر اساس آن تصمیمی گرفته شود.\n\n"
        f"📣 <a href=\"{CHANNEL_URL}\">شعرکده</a>"
    )


# =========================================================
# Fortune sending
# =========================================================

def split_text(text, max_length=4000):
    if len(text) <= max_length:
        return [text]

    parts = []

    remaining = text

    while len(remaining) > max_length:

        cut = remaining.rfind(
            "\n",
            0,
            max_length,
        )

        if cut <= 0:
            cut = max_length

        parts.append(
            remaining[:cut]
        )

        remaining = remaining[cut:].lstrip()

    if remaining:
        parts.append(remaining)

    return parts


def send_fortune(chat_id, record):
    text = format_fortune(record)

    parts = split_text(
        text,
        max_length=4000,
    )

    results = []

    for part in parts:

        result = send_message(
            chat_id,
            part,
            FORTUNE_KEYBOARD,
        )

        results.append(result)

        # اگر حتی یک بخش شکست خورد،
        # فال کامل را موفق در نظر نمی‌گیریم.
        if not api_success(result):
            print(
                "[FORTUNE] Message send failed."
            )
            return False

    return True


# =========================================================
# Audio helpers
# =========================================================

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


def is_negative_cached(url):
    timestamp = _AUDIO_NEGATIVE_CACHE.get(
        url
    )

    if timestamp is None:
        return False

    if time.time() - timestamp > AUDIO_NEGATIVE_TTL:
        _AUDIO_NEGATIVE_CACHE.pop(
            url,
            None,
        )
        return False

    return True


def set_negative_cache(url):
    _AUDIO_NEGATIVE_CACHE[url] = time.time()


def get_cached_audio_url(source_url):
    item = _AUDIO_URL_CACHE.get(
        source_url
    )

    if not item:
        return None

    audio_url, created_at = item

    if time.time() - created_at > AUDIO_URL_CACHE_TTL:
        _AUDIO_URL_CACHE.pop(
            source_url,
            None,
        )
        return None

    return audio_url


def set_cached_audio_url(
    source_url,
    audio_url,
):
    _AUDIO_URL_CACHE[source_url] = (
        audio_url,
        time.time(),
    )


def get_cached_audio(audio_url):
    global _AUDIO_CACHE_BYTES

    item = _AUDIO_CACHE.get(
        audio_url
    )

    if not item:
        return None

    data, created_at = item

    _AUDIO_CACHE.move_to_end(
        audio_url
    )

    return data


def cache_audio(audio_url, data):
    global _AUDIO_CACHE_BYTES

    if not data:
        return

    size = len(data)

    if size > AUDIO_CACHE_MAX_BYTES:
        print(
            f"[AUDIO-CACHE] File too large: "
            f"{size / 1024 / 1024:.2f} MB"
        )
        return

    old = _AUDIO_CACHE.pop(
        audio_url,
        None,
    )

    if old:
        _AUDIO_CACHE_BYTES -= len(
            old[0]
        )

    _AUDIO_CACHE[
        audio_url
    ] = (
        data,
        time.time(),
    )

    _AUDIO_CACHE_BYTES += size

    while (
        len(_AUDIO_CACHE)
        > AUDIO_CACHE_MAX_ITEMS
        or _AUDIO_CACHE_BYTES
        > AUDIO_CACHE_MAX_BYTES
    ):

        _, (old_data, _) = (
            _AUDIO_CACHE.popitem(
                last=False
            )
        )

        _AUDIO_CACHE_BYTES -= len(
            old_data
        )


# =========================================================
# Audio URL validation
# =========================================================

def check_audio_url(audio_url):
    if not audio_url:
        return False

    if is_negative_cached(audio_url):
        return False

    try:
        with get_session().get(
            audio_url,
            stream=True,
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True,
        ) as response:

            if response.status_code != 200:
                print(
                    f"[AUDIO-CHECK] "
                    f"status={response.status_code} "
                    f"url={audio_url}"
                )

                return False

            content_type = (
                response.headers
                .get("Content-Type", "")
                .lower()
            )

            # بعضی سرورها Content-Type صحیح نمی‌دهند،
            # بنابراین فقط در صورت وجود نوع مشخص و
            # کاملاً نامرتبط آن را رد می‌کنیم.
            if content_type:
                bad_types = [
                    "text/html",
                    "text/plain",
                    "application/json",
                ]

                if any(
                    bad in content_type
                    for bad in bad_types
                ):
                    print(
                        f"[AUDIO-CHECK] "
                        f"Invalid content type: "
                        f"{content_type}"
                    )

                    return False

            return True

    except Exception as e:
        print(
            f"[AUDIO-CHECK] ERROR "
            f"{audio_url}: {e}"
        )

        return False


# =========================================================
# Extract audio URLs from source page
# =========================================================

def extract_audio_urls(
    html,
    base_url,
):
    if not html:
        return []

    candidates = []

    # Absolute URLs
    absolute_pattern = re.compile(
        r'https?://[^\s"\'<>]+?\.(?:ogg|mp3)(?:\?[^\s"\'<>]*)?',
        re.IGNORECASE,
    )

    for match in absolute_pattern.finditer(
        html
    ):
        candidates.append(
            match.group(0)
        )

    # Relative URLs
    relative_pattern = re.compile(
        r'(?:"|\')([^"\']+\.(?:ogg|mp3)(?:\?[^"\']*)?)(?:"|\')',
        re.IGNORECASE,
    )

    for match in relative_pattern.finditer(
        html
    ):
        relative_url = match.group(1)

        candidates.append(
            urljoin(
                base_url,
                relative_url,
            )
        )

    # Clean + deduplicate
    result = []

    seen = set()

    for url in candidates:

        url = url.strip()

        if not url:
            continue

        url = url.rstrip(
            ".,);"
        )

        if url in seen:
            continue

        seen.add(url)

        result.append(url)

    # Prefer Ganjoor audio
    ganjoor = [
        url
        for url in result
        if "i.ganjoor.net" in url.lower()
    ]

    if ganjoor:
        others = [
            url
            for url in result
            if url not in ganjoor
        ]

        result = ganjoor + others

    return result


# =========================================================
# Resolve audio from source
# =========================================================

def resolve_audio_from_source(source_url):
    if not source_url:
        return None

    cached = get_cached_audio_url(
        source_url
    )

    if cached:

        # مهم:
        # URL cache شده را دوباره قبل از استفاده
        # اعتبارسنجی نمی‌کنیم؛ اما اگر download شکست
        # بخورد، cache حذف خواهد شد.
        return cached

    lock = get_audio_resolve_lock(
        source_url
    )

    with lock:

        cached = get_cached_audio_url(
            source_url
        )

        if cached:
            return cached

        try:
            response = get_session().get(
                source_url,
                timeout=REQUEST_TIMEOUT,
            )

            if response.status_code != 200:
                print(
                    f"[AUDIO-RESOLVE] "
                    f"Source status={response.status_code}"
                )
                return None

            candidates = extract_audio_urls(
                response.text,
                source_url,
            )

            if not candidates:
                print(
                    "[AUDIO-RESOLVE] "
                    "No audio candidates found."
                )
                return None

            # مهم:
            # همه candidateها را به ترتیب بررسی می‌کنیم
            # و اولین URL واقعاً سالم را انتخاب می‌کنیم.
            for candidate in candidates:

                if check_audio_url(
                    candidate
                ):
                    set_cached_audio_url(
                        source_url,
                        candidate,
                    )

                    print(
                        f"[AUDIO-RESOLVE] "
                        f"Selected: {candidate}"
                    )

                    return candidate

                print(
                    f"[AUDIO-RESOLVE] "
                    f"Invalid candidate: {candidate}"
                )

            return None

        except Exception as e:
            print(
                f"[AUDIO-RESOLVE] ERROR "
                f"{source_url}: {e}"
            )

            return None


# =========================================================
# Final audio URL
# =========================================================

def resolve_final_audio_url(record):
    direct_audio = normalize_text(
        record.get("audio")
    )

    # -----------------------------------------------------
    # 1. Direct audio from HafezFilebot.json
    # -----------------------------------------------------

    if direct_audio:

        if not is_negative_cached(
            direct_audio
        ):

            if check_audio_url(
                direct_audio
            ):
                return direct_audio

            print(
                f"[AUDIO] Direct audio invalid: "
                f"{direct_audio}"
            )

            set_negative_cache(
                direct_audio
            )

    # -----------------------------------------------------
    # 2. Fallback to Source page
    # -----------------------------------------------------

    source_url = normalize_text(
        record.get("source")
    )

    if source_url:

        resolved = resolve_audio_from_source(
            source_url
        )

        if resolved:
            return resolved

    return None


# =========================================================
# Download audio
# =========================================================

def download_audio(audio_url):
    if not audio_url:
        return None

    cached = get_cached_audio(
        audio_url
    )

    if cached is not None:
        print(
            "[AUDIO] Memory cache hit."
        )
        return cached

    if is_negative_cached(
        audio_url
    ):
        print(
            "[AUDIO] Negative cache hit."
        )
        return None

    lock = get_audio_download_lock(
        audio_url
    )

    with lock:

        cached = get_cached_audio(
            audio_url
        )

        if cached is not None:
            return cached

        try:
            print(
                f"[AUDIO] Downloading: "
                f"{audio_url}"
            )

            response = get_session().get(
                audio_url,
                timeout=REQUEST_TIMEOUT,
            )

            if response.status_code == 404:
                set_negative_cache(
                    audio_url
                )

                print(
                    "[AUDIO] 404 -> negative cache"
                )

                return None

            if response.status_code != 200:
                print(
                    f"[AUDIO] "
                    f"status={response.status_code}"
                )

                return None

            data = response.content

            if not data:
                print(
                    "[AUDIO] Empty response."
                )
                return None

            if len(data) > AUDIO_CACHE_MAX_BYTES:
                print(
                    f"[AUDIO] File exceeds "
                    f"50 MB limit: "
                    f"{len(data) / 1024 / 1024:.2f} MB"
                )

                return None

            cache_audio(
                audio_url,
                data,
            )

            print(
                f"[AUDIO] Downloaded "
                f"{len(data) / 1024:.1f} KB"
            )

            return data

        except Exception as e:
            print(
                f"[AUDIO] Download error: "
                f"{e}"
            )

            return None


# =========================================================
# Send audio
# =========================================================

def send_audio(chat_id, record):
    audio_url = resolve_final_audio_url(
        record
    )

    if not audio_url:
        print(
            "[AUDIO] No valid audio URL."
        )
        return False

    data = download_audio(
        audio_url
    )

    if not data:
        print(
            "[AUDIO] Audio download failed."
        )
        return False

    number = normalize_text(
        record.get("ghazal_number")
    )

    if not number:
        number = "؟"

    lower_url = audio_url.lower()

    if ".ogg" in lower_url:
        extension = "ogg"
        mime_type = "audio/ogg"

    else:
        extension = "mp3"
        mime_type = "audio/mpeg"

    filename = (
        f"غزل {number} - حافظ - گنجور."
        f"{extension}"
    )

    files = {
        "audio": (
            filename,
            data,
            mime_type,
        )
    }

    result = splus_request(
        "sendAudio",
        data={
            "chat_id": str(chat_id),
            "title": f"غزل شمارهٔ {number}",
            "performer": "شعرکده سروش پلاس",
        },
        files=files,
    )

    return api_success(result)


# =========================================================
# Chat control state
# =========================================================

def set_control_message(
    chat_id,
    message_id,
):
    with CHAT_CONTROL_LOCK:
        CHAT_CONTROL_MESSAGES[
            str(chat_id)
        ] = message_id


def get_control_message(chat_id):
    with CHAT_CONTROL_LOCK:
        return CHAT_CONTROL_MESSAGES.get(
            str(chat_id)
        )


def clear_control_message(chat_id):
    with CHAT_CONTROL_LOCK:
        CHAT_CONTROL_MESSAGES.pop(
            str(chat_id),
            None,
        )


# =========================================================
# Fortune processing
# =========================================================

def process_fortune(
    chat_id,
    message_id,
):
    try:

        with DATA_LOCK:

            if not HAZALS:
                send_message(
                    chat_id,
                    "❌ در حال حاضر اطلاعات غزل‌ها در دسترس نیست.",
                    MAIN_KEYBOARD,
                )
                return

            record = random.choice(
                HAZALS
            )

        print(
            f"[FORTUNE] Selected "
            f"ghazal={record.get('ghazal_number')} "
            f"record={record.get('record_id')}"
        )

        # -------------------------------------------------
        # Send fortune FIRST
        # -------------------------------------------------

        fortune_success = send_fortune(
            chat_id,
            record,
        )

        if not fortune_success:

            print(
                "[FORTUNE] Fortune send failed; "
                "audio will NOT be sent."
            )

            send_message(
                chat_id,
                "⚠️ ارسال فال با مشکل مواجه شد. لطفاً دوباره تلاش کنید.",
                MAIN_KEYBOARD,
            )

            return

        # -------------------------------------------------
        # Only after successful fortune
        # -------------------------------------------------

        old_control_message = get_control_message(
            chat_id
        )

        if old_control_message:
            delete_message(
                chat_id,
                old_control_message,
            )

            clear_control_message(
                chat_id
            )

        # Delete original button message
        if message_id:
            delete_message(
                chat_id,
                message_id,
            )

        # -------------------------------------------------
        # Audio is OPTIONAL
        # -------------------------------------------------

        audio_success = send_audio(
            chat_id,
            record,
        )

        if not audio_success:
            print(
                "[FORTUNE] Audio unavailable; "
                "fortune remains successfully delivered."
            )

    except Exception as e:

        print(
            f"[FORTUNE] ERROR: {e}"
        )


# =========================================================
# Webhook helpers
# =========================================================

def extract_message_id(result):
    if not api_success(result):
        return None

    result_data = result.get(
        "result"
    )

    if not isinstance(
        result_data,
        dict,
    ):
        return None

    message_id = result_data.get(
        "message_id"
    )

    if message_id is None:
        message_id = result_data.get(
            "messageId"
        )

    return message_id


def get_message_text(message):
    if not isinstance(
        message,
        dict,
    ):
        return ""

    text = message.get(
        "text"
    )

    if text is None:
        text = message.get(
            "caption"
        )

    return normalize_text(
        text
    )


def get_chat_id(message):
    if not isinstance(
        message,
        dict,
    ):
        return None

    chat = message.get(
        "chat"
    )

    if isinstance(
        chat,
        dict,
    ):
        return (
            chat.get("id")
            or chat.get("chat_id")
        )

    return (
        message.get("chat_id")
        or message.get("chatId")
    )


def get_message_id(message):
    if not isinstance(
        message,
        dict,
    ):
        return None

    return (
        message.get("message_id")
        or message.get("messageId")
        or message.get("id")
    )


# =========================================================
# Webhook
# =========================================================

@app.route(
    "/webhook",
    methods=["POST"],
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

        chat_id = get_chat_id(
            message
        )

        if chat_id is None:
            return "ok"

        message_id = get_message_id(
            message
        )

        text = get_message_text(
            message
        )

        print(
            f"[WEBHOOK] "
            f"chat={chat_id} "
            f"message={message_id} "
            f"text={text[:100]}"
        )

        # -------------------------------------------------
        # /start
        # -------------------------------------------------

        if text.startswith(
            "/start"
        ):

            send_message(
                chat_id,
                (
                    "<b>🌿 به فال حافظ خوش آمدید</b>\n\n"
                    "نیت کنید و روی «📜 فال حافظ» بزنید."
                ),
                MAIN_KEYBOARD,
            )

            if message_id:
                delete_message(
                    chat_id,
                    message_id,
                )

            return "ok"

        # -------------------------------------------------
        # New fortune
        # -------------------------------------------------

        if text == "🌿 یک فال دیگر":

            if message_id:
                delete_message(
                    chat_id,
                    message_id,
                )

            result = send_message(
                chat_id,
                (
                    "<b>🌿 نیت کنید...</b>\n\n"
                    "پس از نیت، روی «📜 فال حافظ» بزنید."
                ),
                MAIN_KEYBOARD,
            )

            control_message_id = (
                extract_message_id(
                    result
                )
            )

            if control_message_id:
                set_control_message(
                    chat_id,
                    control_message_id,
                )

            return "ok"

        # -------------------------------------------------
        # Fortune
        # -------------------------------------------------

        if text == "📜 فال حافظ":

            worker = threading.Thread(
                target=process_fortune,
                args=(
                    chat_id,
                    message_id,
                ),
                daemon=True,
            )

            worker.start()

            return "ok"

        # -------------------------------------------------
        # Poetry card bot
        # -------------------------------------------------

        if text == "🎨 ساختن کارت شعر":

            if message_id:
                delete_message(
                    chat_id,
                    message_id,
                )

            send_message(
                chat_id,
                (
                    "🎨 <b>ساخت کارت شعر</b>\n\n"
                    "برای ساخت کارت شعر از بات زیر استفاده کنید:\n\n"
                    f'<a href="{POETRY_CARD_BOT_URL}">'
                    "کارت شعر</a>"
                ),
                MAIN_KEYBOARD,
            )

            return "ok"

        # -------------------------------------------------
        # About
        # -------------------------------------------------

        if text == "🌿 درباره ما":

            if message_id:
                delete_message(
                    chat_id,
                    message_id,
                )

            send_message(
                chat_id,
                ABOUT_TEXT,
                MAIN_KEYBOARD,
            )

            return "ok"

        # -------------------------------------------------
        # Admin contact
        # -------------------------------------------------

        if text == "💬 ارتباط با مدیر":

            if message_id:
                delete_message(
                    chat_id,
                    message_id,
                )

            send_message(
                chat_id,
                (
                    "💬 <b>ارتباط با مدیر</b>\n\n"
                    "برای ارسال پیام ناشناس می‌توانید "
                    "از بات زیر استفاده کنید:\n\n"
                    f'<a href="{ANONYMOUS_BOT_URL}">'
                    "پیام ناشناس</a>"
                ),
                MAIN_KEYBOARD,
            )

            return "ok"

        # -------------------------------------------------
        # Channel
        # -------------------------------------------------

        if text == "📣 کانال شعرکده":

            if message_id:
                delete_message(
                    chat_id,
                    message_id,
                )

            send_message(
                chat_id,
                (
                    "📣 <b>کانال شعرکده</b>\n\n"
                    f'<a href="{CHANNEL_URL}">'
                    "ورود به کانال شعرکده</a>"
                ),
                MAIN_KEYBOARD,
            )

            return "ok"

        return "ok"

    except Exception as e:

        print(
            f"[WEBHOOK] ERROR: {e}"
        )

        # Webhook باید سریع پاسخ دهد
        # حتی در صورت خطای داخلی.
        return "ok"


# =========================================================
# Webhook setup
# =========================================================

def set_webhook():
    result = splus_request(
        "setWebhook",
        data={
            "url": WEBHOOK_URL,
        },
    )

    if api_success(result):
        print(
            f"[WEBHOOK] Successfully set: "
            f"{WEBHOOK_URL}"
        )

    else:
        print(
            "[WEBHOOK] Failed to set webhook."
        )

    return result


# =========================================================
# Startup validation
# =========================================================

def startup():
    print(
        "========================================"
    )
    print(
        "        HAFEZ BOT STARTING"
    )
    print(
        "========================================"
    )

    try:
        load_data()

    except Exception as e:
        print(
            f"[STARTUP] DATA ERROR: {e}"
        )

    try:
        load_interpretations()

    except Exception as e:
        print(
            f"[STARTUP] TABIR ERROR: {e}"
        )

    print(
        f"[STARTUP] HAZALS={len(HAZALS)} "
        f"TABIRS={len(TABIR_MAP)}"
    )

    print(
        "========================================"
    )


startup()


# =========================================================
# Local development
# =========================================================

if __name__ == "__main__":

    # فقط در اجرای مستقیم فایل اجرا می‌شود.
    # در Gunicorn این بخش اجرا نمی‌شود.
    set_webhook()

    port = int(
        os.environ.get(
            "PORT",
            "5000",
        )
    )

    app.run(
        host="0.0.0.0",
        port=port,
    )
