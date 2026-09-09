import os
import json
import random
import time
import threading
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
# Global data
# ============================================================

HAZALS = []


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

    with open(DATA_FILE, "r", encoding="utf-8") as f:
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

        response = requests.post(
            url,
            data=data,
            files=files,
            timeout=REQUEST_TIMEOUT
        )

        print(
            f"[SPLUS] {method}: "
            f"{response.status_code} "
            f"{response.text[:1000]}"
        )

        response.raise_for_status()

        return response.json()

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
            ensure_ascii=False
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
        return

    splus_request(
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

        import re

        match = re.search(
            r"/sh(\d+)/?",
            source
        )

        if match:
            return match.group(1)

    import re

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

    poem = poem.replace(
        "\r\n",
        "\n"
    )

    poem = poem.replace(
        "\r",
        "\n"
    )

    return poem.strip()


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

    print(
        f"[FORTUNE] "
        f"Ghazal #{get_ghazal_number(record)} "
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

    for chunk in chunks:

        send_message(
            chat_id,
            chunk
        )

        if len(chunks) > 1:
            time.sleep(0.15)


# ============================================================
# Download user's own audio
# ============================================================

def download_audio(
    audio_url
):

    if not audio_url:
        return None

    print(
        f"[AUDIO] Downloading ONLY user's source: "
        f"{audio_url}"
    )

    try:

        response = requests.get(
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

        return content

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

    print(
        f"[AUDIO] Ghazal #{get_ghazal_number(record)} "
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
        f"{get_ghazal_number(record)}"
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
            f"{get_ghazal_number(record)}"
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
            f"for ghazal #{get_ghazal_number(record)}"
        )

    else:

        print(
            f"[AUDIO] Failed to send "
            f"ghazal #{get_ghazal_number(record)}"
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

    print(
        f"[FORTUNE] Selected "
        f"ghazal #{get_ghazal_number(record)} "
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

        except Exception:

            temporary_message_id = None

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

        # ====================================================
        # /start
        # ====================================================

        if text.strip() == "/start":

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

        if text.strip() in (
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



