import os
import json
import random
import time
import threading
import re
import io

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

DATA_FILE = "HafezFilebot.json"

CHANNEL_URL = "https://splus.ir/@LIFE_M23"

HAFEZ_TOP_URL = "https://hafez.top/ghazal-{}.html"
HAFEZ_TOP_URL_ALT = "https://hafez.top/ghazal-{}/"

REQUEST_TIMEOUT = 20
AUDIO_TIMEOUT = 40

MAX_MESSAGE_LENGTH = 4096

# برای اینکه نزدیک سقف 4096 نرویم
SAFE_MESSAGE_LENGTH = 3900


# =========================================================
# Load Hafez data
# =========================================================

def load_hafez_data():
    if not os.path.exists(DATA_FILE):
        raise FileNotFoundError(
            f"{DATA_FILE} not found."
        )

    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    records = []

    if isinstance(data, list):
        source_items = data
    elif isinstance(data, dict):
        source_items = [data]
    else:
        raise ValueError("Invalid Hafez JSON structure.")

    for item in source_items:

        if not isinstance(item, dict):
            continue

        for record_id, record in item.items():

            if not isinstance(record, dict):
                continue

            title = str(record.get("Title") or "").strip()
            poem = str(record.get("Poem") or "").strip()
            source = str(record.get("Source") or "").strip()
            audio = record.get("Audio")

            if not title or not poem:
                continue

            ghazal_number = extract_ghazal_number(title)

            if ghazal_number is None:
                continue

            records.append({
                "record_id": str(record_id),
                "number": ghazal_number,
                "title": title,
                "poem": poem,
                "source": source,
                "audio": audio
            })

    if not records:
        raise ValueError("No valid Hafez ghazals found in JSON.")

    print(f"[DATA] Loaded {len(records)} ghazals.")

    return records


# =========================================================
# Extract ghazal number
# =========================================================

def extract_ghazal_number(title):

    if not title:
        return None

    # اعداد فارسی
    persian_digits = str.maketrans(
        "۰۱۲۳۴۵۶۷۸۹",
        "0123456789"
    )

    normalized = title.translate(persian_digits)

    match = re.search(r"(\d+)", normalized)

    if not match:
        return None

    try:
        return int(match.group(1))
    except Exception:
        return None


# =========================================================
# Global data
# =========================================================

HAFEZ_DATA = load_hafez_data()


# =========================================================
# HTTP helpers
# =========================================================

def post_api(method, data=None, files=None):

    url = f"{API}/{method}"

    try:
        if files:
            response = requests.post(
                url,
                data=data or {},
                files=files,
                timeout=REQUEST_TIMEOUT
            )
        else:
            response = requests.post(
                url,
                json=data or {},
                timeout=REQUEST_TIMEOUT
            )

        try:
            result = response.json()
        except Exception:
            result = {
                "ok": False,
                "description": response.text
            }

        print(
            f"[SPLUS] {method}: "
            f"{response.status_code} {result}"
        )

        return response, result

    except Exception as e:

        print(
            f"[SPLUS ERROR] {method}: {e}"
        )

        return None, {
            "ok": False,
            "description": str(e)
        }


# =========================================================
# Send message
# =========================================================

def send_message(chat_id, text, reply_markup=None):

    data = {
        "chat_id": chat_id,
        "text": text
    }

    if reply_markup is not None:
        data["reply_markup"] = reply_markup

    return post_api(
        "sendMessage",
        data=data
    )


# =========================================================
# Split long messages
# =========================================================

def split_message(text, max_length=SAFE_MESSAGE_LENGTH):

    if len(text) <= MAX_MESSAGE_LENGTH:
        return [text]

    chunks = []

    remaining = text.strip()

    while len(remaining) > max_length:

        # ترجیح می‌دهیم در خط خالی بشکنیم
        cut = remaining.rfind(
            "\n\n",
            0,
            max_length
        )

        # اگر پیدا نشد، در خط معمولی
        if cut < 0:
            cut = remaining.rfind(
                "\n",
                0,
                max_length
            )

        # اگر باز هم پیدا نشد، در فاصله
        if cut < 0:
            cut = remaining.rfind(
                " ",
                0,
                max_length
            )

        # آخرین حالت: برش مستقیم
        if cut <= 0:
            cut = max_length

        part = remaining[:cut].strip()

        if part:
            chunks.append(part)

        remaining = remaining[cut:].strip()

    if remaining:
        chunks.append(remaining)

    return chunks


def send_long_message(chat_id, text):

    chunks = split_message(text)

    print(
        f"[MESSAGE] length={len(text)} "
        f"chunks={len(chunks)}"
    )

    results = []

    for index, chunk in enumerate(chunks):

        result = send_message(
            chat_id,
            chunk
        )

        results.append(result)

        # فاصله بسیار کوتاه برای جلوگیری از فشار پشت سر هم
        if index < len(chunks) - 1:
            time.sleep(0.15)

    return results


# =========================================================
# Reply keyboard
# =========================================================

def main_keyboard():

    return {
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


# =========================================================
# Fetch Hafez page
# =========================================================

def fetch_hafez_page(number):

    urls = [
        HAFEZ_TOP_URL.format(number),
        HAFEZ_TOP_URL_ALT.format(number)
    ]

    headers = {
        "User-Agent": (
            "Mozilla/5.0 "
            "(Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/131.0 Safari/537.36"
        )
    }

    for url in urls:

        try:

            print(
                f"[HAFEZ.TOP] Fetching: {url}"
            )

            response = requests.get(
                url,
                headers=headers,
                timeout=REQUEST_TIMEOUT
            )

            if response.status_code != 200:
                print(
                    f"[HAFEZ.TOP] HTTP "
                    f"{response.status_code}"
                )
                continue

            response.encoding = response.apparent_encoding or "utf-8"

            html = response.text

            if len(html) < 1000:
                continue

            print(
                f"[HAFEZ.TOP] OK "
                f"length={len(html)}"
            )

            return html

        except Exception as e:

            print(
                f"[HAFEZ.TOP ERROR] {e}"
            )

    return None


# =========================================================
# Clean HTML
# =========================================================

def html_to_text(html):

    if not html:
        return ""

    text = html

    # حذف script و style
    text = re.sub(
        r"<script\b[^>]*>.*?</script>",
        " ",
        text,
        flags=re.I | re.S
    )

    text = re.sub(
        r"<style\b[^>]*>.*?</style>",
        " ",
        text,
        flags=re.I | re.S
    )

    # تبدیل br و block tags به newline
    text = re.sub(
        r"<br\s*/?>",
        "\n",
        text,
        flags=re.I
    )

    text = re.sub(
        r"</(?:p|div|li|h1|h2|h3|h4|h5|h6|section|article)>",
        "\n",
        text,
        flags=re.I
    )

    # حذف باقی تگ‌ها
    text = re.sub(
        r"<[^>]+>",
        " ",
        text
    )

    # HTML entities
    replacements = {
        "&nbsp;": " ",
        "&amp;": "&",
        "&quot;": '"',
        "&#039;": "'",
        "&lt;": "<",
        "&gt;": ">"
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    # فاصله‌ها
    text = re.sub(
        r"[ \t]+",
        " ",
        text
    )

    # خطوط خالی اضافی
    text = re.sub(
        r"\n\s*\n\s*\n+",
        "\n\n",
        text
    )

    return text.strip()


# =========================================================
# Extract fortune interpretation
# =========================================================

def extract_interpretation(html, number):

    if not html:
        return None

    # -----------------------------------------------------
    # روش اول:
    # مستقیماً از بخش "نتیجه تفال شما..."
    # -----------------------------------------------------

    marker_pattern = (
        rf"نتیجه\s+تفال\s+شما\s+به\s+غزل\s+"
        rf"{number}\s+حافظ"
    )

    match = re.search(
        marker_pattern,
        html,
        flags=re.I
    )

    if match:

        section = html[match.end():]

        # پایان بخش تعبیر
        end_patterns = [
            r"تفسیر\s+کامل\s+غزل",
            r"تفسیر\s+غزل",
            r"معنی\s+و\s+تفسیر",
            r"غزل‌های\s+مشابه",
            r"دیدگاهتان\s+را\s+بنویسید",
            r"دیدگاه"
        ]

        end_positions = []

        for pattern in end_patterns:

            end_match = re.search(
                pattern,
                section,
                flags=re.I
            )

            if end_match:
                end_positions.append(
                    end_match.start()
                )

        if end_positions:
            section = section[
                :min(end_positions)
            ]

        # استخراج li ها
        li_items = re.findall(
            r"<li\b[^>]*>(.*?)</li>",
            section,
            flags=re.I | re.S
        )

        if li_items:

            cleaned_items = []

            for item in li_items:

                item_text = html_to_text(item)

                item_text = re.sub(
                    r"^\s*[*•\-]\s*",
                    "",
                    item_text
                ).strip()

                if item_text:
                    cleaned_items.append(
                        item_text
                    )

            if cleaned_items:

                return "\n".join(
                    f"• {item}"
                    for item in cleaned_items
                )

        # اگر li پیدا نشد، متن خام بخش
        clean_section = html_to_text(section)

        lines = []

        for line in clean_section.splitlines():

            line = line.strip()

            if not line:
                continue

            if len(line) < 3:
                continue

            line = re.sub(
                r"^[*•\-]\s*",
                "",
                line
            )

            lines.append(line)

        if lines:

            return "\n".join(
                f"• {line}"
                for line in lines
            )

    # -----------------------------------------------------
    # روش دوم:
    # در صورت تغییر HTML سایت، از بخش معنی و تفسیر
    # استفاده می‌کنیم.
    # -----------------------------------------------------

    text = html_to_text(html)

    marker = f"معنی و تفسیر غزل {number} حافظ"

    start = text.find(marker)

    if start >= 0:

        section = text[start + len(marker):]

        end_markers = [
            f"نتیجه تفال شما به غزل {number} حافظ",
            "تفسیر کامل غزل",
            "غزل‌های مشابه",
            "دیدگاهتان را بنویسید"
        ]

        positions = []

        for end_marker in end_markers:

            pos = section.find(end_marker)

            if pos >= 0:
                positions.append(pos)

        if positions:
            section = section[:min(positions)]

        section = section.strip()

        if section:
            return section

    return None


# =========================================================
# Extract MP3 URL from Hafez.top
# =========================================================

def extract_mp3_url(html, number):

    if not html:
        return None

    # ابتدا دنبال لینک مستقیم mp3 غزل می‌گردیم
    patterns = [
        rf'https?://[^"\']+ghazal[-_]{number}\.mp3',
        rf'https?://[^"\']+/ghazal-{number}\.mp3',
        rf'https?://[^"\']+/ghazal_{number}\.mp3'
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            html,
            flags=re.I
        )

        if match:
            return match.group(0)

    # حالت عمومی‌تر
    all_mp3 = re.findall(
        r'https?://[^"\']+\.mp3',
        html,
        flags=re.I
    )

    for url in all_mp3:

        normalized = url.lower()

        if (
            f"ghazal-{number}" in normalized
            or
            f"ghazal_{number}" in normalized
            or
            f"ghazal{number}" in normalized
        ):
            return url

    return None


# =========================================================
# Download audio
# =========================================================

def download_audio(url):

    if not url:
        return None

    try:

        print(
            f"[AUDIO] Downloading: {url}"
        )

        headers = {
            "User-Agent": (
                "Mozilla/5.0 "
                "(Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/131.0 Safari/537.36"
            )
        }

        response = requests.get(
            url,
            headers=headers,
            timeout=AUDIO_TIMEOUT
        )

        response.raise_for_status()

        content = response.content

        if not content:
            print("[AUDIO] Empty file.")
            return None

        # جلوگیری از ارسال HTML به جای فایل صوتی
        content_type = (
            response.headers.get(
                "Content-Type",
                ""
            ).lower()
        )

        if (
            "text/html" in content_type
            and not url.lower().endswith(".mp3")
        ):
            print(
                "[AUDIO] Response appears to be HTML."
            )
            return None

        print(
            f"[AUDIO] Downloaded "
            f"{len(content)} bytes."
        )

        return content

    except Exception as e:

        print(
            f"[AUDIO ERROR] {e}"
        )

        return None


# =========================================================
# Send audio
# =========================================================

def send_audio(chat_id, audio_bytes, number):

    if not audio_bytes:
        return False

    filename = f"hafez_{number}.mp3"

    files = {
        "audio": (
            filename,
            io.BytesIO(audio_bytes),
            "audio/mpeg"
        )
    }

    data = {
        "chat_id": str(chat_id)
    }

    response, result = post_api(
        "sendAudio",
        data=data,
        files=files
    )

    if (
        result
        and result.get("ok") is True
    ):
        print(
            f"[AUDIO] Sent successfully "
            f"for ghazal #{number}"
        )
        return True

    print(
        f"[AUDIO] Failed for ghazal #{number}"
    )

    return False


# =========================================================
# Get interpretation + audio from same page
# =========================================================

def get_hafez_extras(number):

    html = fetch_hafez_page(number)

    if not html:
        return {
            "interpretation": None,
            "audio_url": None
        }

    interpretation = extract_interpretation(
        html,
        number
    )

    audio_url = extract_mp3_url(
        html,
        number
    )

    print(
        f"[EXTRAS] ghazal #{number} "
        f"interpretation="
        f"{bool(interpretation)} "
        f"audio="
        f"{audio_url}"
    )

    return {
        "interpretation": interpretation,
        "audio_url": audio_url
    }


# =========================================================
# Build fortune text
# =========================================================

def build_fortune_text(record, interpretation):

    number = record["number"]
    poem = record["poem"].strip()
    source = record["source"].strip()

    if not interpretation:
        interpretation = (
            "تعبیر این غزل در حال حاضر "
            "در دسترس نیست."
        )

    text = (
        "فال حافظ\n"
        f"شماره غزل {number}\n\n"
        f"{poem}\n\n"
        "منبع گنجور\n"
        f"{source}\n"
        "@LIFE_M23 🌱\n\n"
        "──────────────\n\n"
        "🌌 تعبیر\n\n"
        f"{interpretation.strip()}\n\n"
        "@LIFE_M23 🌱"
    )

    return text


# =========================================================
# Send fortune
# =========================================================

def send_fortune(chat_id):

    record = random.choice(HAFEZ_DATA)

    number = record["number"]

    print(
        f"[FORTUNE] Selected ghazal "
        f"#{number} "
        f"record={record['record_id']}"
    )

    # -----------------------------------------------------
    # پیام انتظار
    # -----------------------------------------------------

    send_message(
        chat_id,
        "🌿 نیت کنید...\n\n"
        "در حال گرفتن فال حافظ"
    )

    # -----------------------------------------------------
    # دریافت تعبیر و صوت از صفحه همان غزل
    # -----------------------------------------------------

    extras = get_hafez_extras(number)

    interpretation = extras.get(
        "interpretation"
    )

    audio_url = extras.get(
        "audio_url"
    )

    # -----------------------------------------------------
    # ساخت متن
    # -----------------------------------------------------

    fortune_text = build_fortune_text(
        record,
        interpretation
    )

    print(
        f"[FORTUNE] Final text length="
        f"{len(fortune_text)}"
    )

    # -----------------------------------------------------
    # ارسال متن
    # -----------------------------------------------------

    send_long_message(
        chat_id,
        fortune_text
    )

    # -----------------------------------------------------
    # صوت کاملاً جدا از متن
    # -----------------------------------------------------

    if audio_url:

        print(
            f"[AUDIO] Ghazal #{number} "
            f"source={audio_url}"
        )

        audio_bytes = download_audio(
            audio_url
        )

        if audio_bytes:

            send_audio(
                chat_id,
                audio_bytes,
                number
            )

        else:

            print(
                f"[AUDIO] Download failed "
                f"for ghazal #{number}"
            )

    else:

        print(
            f"[AUDIO] No audio available "
            f"for ghazal #{number}"
        )


# =========================================================
# /start
# =========================================================

def handle_start(chat_id):

    text = (
        "به فال حافظ خوش آمدید 🌿\n\n"
        "برای گرفتن فال، دکمه زیر را بزنید."
    )

    send_message(
        chat_id,
        text,
        reply_markup=main_keyboard()
    )


# =========================================================
# Process update
# =========================================================

def process_update(update):

    try:

        print(
            f"[UPDATE] {json.dumps(update, ensure_ascii=False)}"
        )

        message = update.get("message")

        if not message:
            return

        chat = message.get("chat")

        if not chat:
            return

        chat_id = chat.get("id")

        if chat_id is None:
            return

        text = message.get("text")

        print(
            f"[MESSAGE] chat_id={chat_id} "
            f"text='{text}'"
        )

        if text == "/start":

            handle_start(chat_id)
            return

        if text == "📜 فال حافظ":

            send_fortune(chat_id)
            return

    except Exception as e:

        print(
            f"[PROCESS ERROR] {e}"
        )


# =========================================================
# Webhook
# =========================================================

@app.route(
    "/webhook",
    methods=["POST"]
)
def webhook():

    try:

        update = request.get_json(
            silent=True
        )

        if not update:
            return "OK", 200

        # پردازش در thread تا سروش سریع 200 بگیرد
        thread = threading.Thread(
            target=process_update,
            args=(update,),
            daemon=True
        )

        thread.start()

        return "OK", 200

    except Exception as e:

        print(
            f"[WEBHOOK ERROR] {e}"
        )

        return "OK", 200


# =========================================================
# Health check
# =========================================================

@app.route("/")
def index():

    return (
        "Hafez Bot is running.",
        200
    )


@app.route("/health")
def health():

    return {
        "status": "ok",
        "ghazals": len(HAFEZ_DATA)
    }, 200


# =========================================================
# Set webhook
# =========================================================

def setup_webhook():

    time.sleep(2)

    webhook_url = os.environ.get(
        "WEBHOOK_URL"
    )

    if not webhook_url:

        render_url = os.environ.get(
            "RENDER_EXTERNAL_URL"
        )

        if render_url:

            webhook_url = (
                render_url.rstrip("/")
                + "/webhook"
            )

    if not webhook_url:

        print(
            "[WEBHOOK] WEBHOOK_URL / "
            "RENDER_EXTERNAL_URL not found."
        )

        return

    print(
        f"[WEBHOOK] Setting webhook: "
        f"{webhook_url}"
    )

    response, result = post_api(
        "setWebhook",
        data={
            "url": webhook_url
        }
    )

    print(
        f"[WEBHOOK] Result: {result}"
    )


# =========================================================
# Start
# =========================================================

if __name__ == "__main__":

    threading.Thread(
        target=setup_webhook,
        daemon=True
    ).start()

    port = int(
        os.environ.get(
            "PORT",
            "10000"
        )
    )

    app.run(
        host="0.0.0.0",
        port=port
    )
