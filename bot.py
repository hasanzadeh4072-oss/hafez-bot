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

# ------------------------------------------------------------
# وضعیت نیت کاربران
#
# اگر chat_id داخل این دیکشنری باشد یعنی کاربر یک بار
# روی «📜 فال حافظ» زده و منتظر زدن دوباره دکمه است.
#
# مقدار ذخیره‌شده = message_id پیام نیت
# ------------------------------------------------------------

PENDING_INTENT = {}

STATE_LOCK = threading.Lock()


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

    # --------------------------------------------------------
    # The user's JSON is an array of objects.
    # Each object contains one record such as:
    #
    # {
    #     "2130": {
    #         "Audio": "...",
    #         "Author": "حافظ",
    #         "Book": "غزلیات حافظ",
    #         "Poem": "...",
    #         "Source": "...",
    #         "Title": "غزل شمارهٔ ۱"
    #     }
    # }
    # --------------------------------------------------------

    for item in raw_data:

        if not isinstance(item, dict):
            continue

        for record_id, record in item.items():

            if not isinstance(record, dict):
                continue

            poem = str(record.get("Poem") or "").strip()

            if not poem:
                continue

            title = str(record.get("Title") or "").strip()

            source = str(record.get("Source") or "").strip()

            # IMPORTANT:
            # Audio is taken ONLY from the user's JSON.
            # No fallback URL is generated.
            audio = record.get("Audio")

            if isinstance(audio, str):
                audio = audio.strip()

                if not audio:
                    audio = None
            else:
                audio = None

            loaded.append({
                "record_id": str(record_id),
                "author": record.get("Author", "حافظ"),
                "book": record.get("Book", "غزلیات حافظ"),
                "poem": poem,
                "source": source,
                "title": title,
                "audio": audio,
            })

    HAZALS = loaded

    print(f"[DATA] Loaded {len(HAZALS)} ghazals.")


# ============================================================
# Soroush API helper
# ============================================================

def splus_request(method, data=None, files=None):

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

def send_message(chat_id, text):

    if not text:
        return None

    data = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": "true"
    }

    return splus_request(
        "sendMessage",
        data=data
    )


# ============================================================
# Delete message
# ============================================================

def delete_message(chat_id, message_id):

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

def split_message(text, max_length=MAX_MESSAGE_LENGTH):

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

    title = record.get("title", "")

    # Example:
    # غزل شمارهٔ 349
    # غزل شمارهٔ ۱
    #
    # We prefer Source because it contains sh349,
    # but Title is also kept as fallback.

    source = record.get("source", "")

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

    return record.get("record_id", "نامشخص")


# ============================================================
# Clean poem
# ============================================================

def clean_poem(poem):

    if not poem:
        return ""

    # Normalize line endings
    poem = poem.replace("\r\n", "\n")
    poem = poem.replace("\r", "\n")

    # Remove excessive blank lines at beginning/end
    poem = poem.strip()

    return poem


# ============================================================
# Build fortune text
# ============================================================

def build_fortune(record):

    number = get_ghazal_number(record)

    poem = clean_poem(
        record.get("poem", "")
    )

    # --------------------------------------------------------
    # VERY IMPORTANT:
    #
    # Only the poem is returned here.
    #
    # No:
    # - hafez.top
    # - interpretation
    # - extra explanation
    # - menu
    # - previous/next ghazal
    # - support message
    # - duplicated poem
    # --------------------------------------------------------

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

def send_fortune(chat_id, record):

    fortune_text = build_fortune(record)

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

        # Small delay to preserve order
        if len(chunks) > 1:
            time.sleep(0.15)


# ============================================================
# Download user's own audio
# ============================================================

def download_audio(audio_url):

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
            f"[AUDIO ERROR] "
            f"{e}"
        )

        return None


# ============================================================
# Send audio
# ============================================================

def send_audio(chat_id, record):

    # ========================================================
    # CRITICAL RULE:
    #
    # Audio MUST come directly from Audio field
    # in HafezFilebot.json.
    #
    # There is NO fallback.
    # ========================================================

    audio_url = record.get("audio")

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

    # --------------------------------------------------------
    # Soroush sendAudio requires an upload.
    #
    # Even if source is .ogg, we DO NOT invent another
    # source or use hafez.top.
    #
    # We simply attempt to send the bytes from the user's
    # Audio URL.
    # --------------------------------------------------------

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

def process_fortune(chat_id):

    if not HAZALS:

        send_message(
            chat_id,
            "متأسفانه مجموعه غزل‌های حافظ در دسترس نیست."
        )

        return

    # --------------------------------------------------------
    # Select one ghazal randomly
    # --------------------------------------------------------

    record = random.choice(
        HAZALS
    )

    print(
        f"[FORTUNE] Selected "
        f"ghazal #{get_ghazal_number(record)} "
        f"record={record.get('record_id')}"
    )

    # --------------------------------------------------------
    # Send ONLY the ghazal
    # --------------------------------------------------------

    send_fortune(
        chat_id,
        record
    )

    # --------------------------------------------------------
    # Send audio ONLY if Audio exists in JSON
    # --------------------------------------------------------

    send_audio(
        chat_id,
        record
    )


# ============================================================
# Fortune button handler
# ============================================================

def handle_fortune_button(chat_id):

    # --------------------------------------------------------
    # First press:
    # Show intention message and WAIT.
    #
    # Second press:
    # Remove intention message and generate fortune.
    # --------------------------------------------------------

    with STATE_LOCK:

        pending_message_id = PENDING_INTENT.get(
            chat_id
        )

        # ====================================================
        # FIRST PRESS
        # ====================================================

        if pending_message_id is None:

            result = send_message(
                chat_id,
                "🌿 نیت کنید...\n\n"
                "نیت خود را در دل کنید و سپس دوباره "
                "روی «📜 فال حافظ» بزنید."
            )

            message_id = None

            if result and result.get("ok"):

                try:

                    message_id = (
                        result["result"]["message_id"]
                    )

                except Exception:

                    message_id = None

            # Even if message_id could not be obtained,
            # keep the state so the next press generates
            # the fortune.

            PENDING_INTENT[chat_id] = message_id

            print(
                f"[INTENT] First press for chat "
                f"{chat_id}. Waiting for second press."
            )

            return

        # ====================================================
        # SECOND PRESS
        # ====================================================

        PENDING_INTENT.pop(
            chat_id,
            None
        )

        print(
            f"[INTENT] Second press for chat "
            f"{chat_id}. Generating fortune."
        )

    # --------------------------------------------------------
    # Delete the intention message before sending the result
    # --------------------------------------------------------

    if pending_message_id:

        delete_message(
            chat_id,
            pending_message_id
        )

    # --------------------------------------------------------
    # Generate fortune in background
    # --------------------------------------------------------

    process_fortune(
        chat_id
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

        # ----------------------------------------------------
        # Fortune command
        # ----------------------------------------------------

        if text.strip() == "📜 فال حافظ":

            # ------------------------------------------------
            # Handle first/second press.
            #
            # The state decision happens immediately so
            # duplicate webhook requests cannot accidentally
            # generate multiple fortunes.
            # ------------------------------------------------

            thread = threading.Thread(
                target=handle_fortune_button,
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
