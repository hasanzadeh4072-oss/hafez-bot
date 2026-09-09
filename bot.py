import os
import json
import random
import re
import threading
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
# Global State
# ==================================

DATA = []

PENDING_INTENT = {}

STATE_LOCK = threading.Lock()


# ==================================
# Reply Keyboard
# ==================================

FORTUNE_KEYBOARD = {
    "keyboard": [
        [
            {
                "text": "📜 گرفتن فال"
            }
        ]
    ],
    "resize_keyboard": True,
    "one_time_keyboard": True
}


REMOVE_KEYBOARD = {
    "remove_keyboard": True
}


# ==================================
# Load JSON Data
# ==================================

def load_data():
    global DATA

    with open(DATA_FILE, "r", encoding="utf-8") as f:
        raw_data = json.load(f)

    normalized = []

    if not isinstance(raw_data, list):
        raise ValueError("JSON root must be a list.")

    for item in raw_data:

        if not isinstance(item, dict):
            continue

        for ghazal_id, record in item.items():

            if not isinstance(record, dict):
                continue

            audio = record.get("Audio")

            if not isinstance(audio, str) or not audio.strip():
                audio = None

            normalized.append(
                {
                    "id": str(ghazal_id),
                    "Audio": audio,
                    "Author": record.get("Author", ""),
                    "Book": record.get("Book", ""),
                    "Poem": record.get("Poem", ""),
                    "Source": record.get("Source", ""),
                    "Title": record.get("Title", "")
                }
            )

    DATA = normalized

    print(f"Loaded {len(DATA)} ghazals.")


# ==================================
# HTTP Helpers
# ==================================

def api_post(method, data=None, files=None):
    url = f"{API}/{method}"

    try:
        response = requests.post(
            url,
            data=data,
            files=files,
            timeout=REQUEST_TIMEOUT
        )

        try:
            result = response.json()
        except Exception:
            result = {
                "ok": False,
                "description": response.text
            }

        print(f"{method}: {response.status_code} {result}")

        return result

    except Exception as e:
        print(f"{method} ERROR: {e}")

        return {
            "ok": False,
            "description": str(e)
        }


# ==================================
# Send Message
# ==================================

def send_message(chat_id, text, reply_markup=None):

    data = {
        "chat_id": chat_id,
        "text": text
    }

    if reply_markup is not None:
        data["reply_markup"] = json.dumps(
            reply_markup,
            ensure_ascii=False
        )

    return api_post(
        "sendMessage",
        data=data
    )


# ==================================
# Delete Message
# ==================================

def delete_message(chat_id, message_id):

    if not message_id:
        return None

    return api_post(
        "deleteMessage",
        data={
            "chat_id": chat_id,
            "message_id": message_id
        }
    )


# ==================================
# Hide Reply Keyboard
# ==================================

def hide_keyboard(chat_id):

    return send_message(
        chat_id,
        " ",
        reply_markup=REMOVE_KEYBOARD
    )


# ==================================
# Extract Ghazal Number
# ==================================

def get_ghazal_number(record):

    source = record.get("Source", "")

    if isinstance(source, str):

        match = re.search(
            r"/sh(\d+)/?",
            source
        )

        if match:
            return match.group(1)

    title = record.get("Title", "")

    if isinstance(title, str):

        match = re.search(
            r"(\d+)",
            title
        )

        if match:
            return match.group(1)

    return record.get("id", "")


# ==================================
# Build Fortune Text
# ==================================

def build_fortune(record):

    ghazal_number = get_ghazal_number(record)

    poem = record.get("Poem", "")

    source = record.get("Source", "")

    text = (
        "فال حافظ\n"
        f"شماره غزل {ghazal_number}\n\n"
        f"{poem}\n\n"
        "منبع گنجور\n"
        f"{source}\n"
        "@LIFE_M23 🌱"
    )

    return text


# ==================================
# Send Long Message Safely
# ==================================

def send_long_message(chat_id, text):

    if len(text) <= MAX_MESSAGE_LENGTH:

        return send_message(
            chat_id,
            text
        )

    results = []

    start = 0

    while start < len(text):

        chunk = text[
            start:start + MAX_MESSAGE_LENGTH
        ]

        result = send_message(
            chat_id,
            chunk
        )

        results.append(result)

        start += MAX_MESSAGE_LENGTH

    return results


# ==================================
# Download Audio
# ==================================

def download_audio(audio_url):

    if not audio_url:
        return None

    try:

        response = requests.get(
            audio_url,
            timeout=REQUEST_TIMEOUT
        )

        if response.status_code != 200:

            print(
                f"Audio download failed: "
                f"{response.status_code}"
            )

            return None

        content = response.content

        if not content:
            return None

        return content

    except Exception as e:

        print(f"Audio download ERROR: {e}")

        return None


# ==================================
# Send Audio
# ==================================

def send_audio(chat_id, record):

    audio_url = record.get("Audio")

    # Audio MUST come only from JSON
    if not audio_url:
        print(
            f"No audio available for ghazal "
            f"{record.get('id')}"
        )
        return None

    audio_bytes = download_audio(
        audio_url
    )

    if not audio_bytes:
        print(
            f"Could not download audio for "
            f"ghazal {record.get('id')}"
        )
        return None

    ghazal_number = get_ghazal_number(
        record
    )

    filename = (
        f"hafez_{ghazal_number}.mp3"
    )

    files = {
        "audio": (
            filename,
            audio_bytes,
            "audio/mpeg"
        )
    }

    data = {
        "chat_id": chat_id,
        "title": f"حافظ - غزل {ghazal_number}",
        "performer": "حافظ"
    }

    return api_post(
        "sendAudio",
        data=data,
        files=files
    )


# ==================================
# Process Fortune
# ==================================

def process_fortune(chat_id):

    if not DATA:

        send_message(
            chat_id,
            "متأسفانه اطلاعات فال حافظ در دسترس نیست."
        )

        return

    record = random.choice(DATA)

    print(
        f"Fortune selected: "
        f"{get_ghazal_number(record)}"
    )

    fortune_text = build_fortune(
        record
    )

    send_long_message(
        chat_id,
        fortune_text
    )

    # Audio only from JSON Audio field
    send_audio(
        chat_id,
        record
    )


# ==================================
# Fortune Button Handler
# ==================================

def handle_fortune_button(chat_id):

    with STATE_LOCK:

        # ----------------------------------
        # First press:
        # Show intention + reply keyboard
        # ----------------------------------

        if chat_id not in PENDING_INTENT:

            result = send_message(
                chat_id,
                "🌿 نیت کنید...\n\n"
                "نیت خود را در دل کنید و سپس "
                "دکمه «📜 گرفتن فال» را بزنید.",
                reply_markup=FORTUNE_KEYBOARD
            )

            message_id = None

            if result and result.get("ok"):

                try:
                    message_id = (
                        result["result"]["message_id"]
                    )

                except Exception:
                    message_id = None

            PENDING_INTENT[chat_id] = message_id

            return

        # ----------------------------------
        # Second press:
        # Take fortune
        # ----------------------------------

        pending_message_id = PENDING_INTENT.pop(
            chat_id,
            None
        )

    # Delete intention message
    if pending_message_id:

        delete_message(
            chat_id,
            pending_message_id
        )

    # Hide reply keyboard
    hide_keyboard(
        chat_id
    )

    # Generate fortune
    process_fortune(
        chat_id
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
        )

        if not update:

            return "OK"

        print(
            "Incoming update:",
            update
        )

        message = update.get(
            "message"
        )

        if not message:

            return "OK"

        chat = message.get(
            "chat"
        )

        if not chat:

            return "OK"

        chat_id = chat.get(
            "id"
        )

        text = message.get(
            "text"
        )

        if not text:

            return "OK"

        text = text.strip()

        # ==================================
        # Main Fortune Button
        # ==================================

        if text == "📜 فال حافظ":

            thread = threading.Thread(
                target=handle_fortune_button,
                args=(chat_id,),
                daemon=True
            )

            thread.start()

            return "OK"

        # ==================================
        # Reply Keyboard Fortune Button
        # ==================================

        if text == "📜 گرفتن فال":

            with STATE_LOCK:

                is_pending = (
                    chat_id in PENDING_INTENT
                )

            if is_pending:

                thread = threading.Thread(
                    target=handle_fortune_button,
                    args=(chat_id,),
                    daemon=True
                )

                thread.start()

            return "OK"

        return "OK"

    except Exception as e:

        print(
            f"Webhook ERROR: {e}"
        )

        return "OK"


# ==================================
# Home / Health Check
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

    result = api_post(
        "setWebhook",
        data={
            "url": WEBHOOK_URL
        }
    )

    print(
        "Webhook result:",
        result
    )

    return result


# ==================================
# Startup
# ==================================

load_data()


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



