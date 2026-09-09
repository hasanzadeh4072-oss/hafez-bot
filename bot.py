import os
import json
import random
import re
import time
import threading
import requests

from flask import Flask, request, jsonify


# ============================================================
# Configuration
# ============================================================

TOKEN = os.environ.get("SOROUSH_TOKEN")

if not TOKEN:
    raise RuntimeError("SOROUSH_TOKEN environment variable is not set.")

API = f"https://api.splus.ir/bot{TOKEN}"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, "HafezFilebot.json")

CHANNEL_TAG = "@LIFE_M23 🌱"

BUTTON_TEXT = "📜 فال حافظ"

# Render automatically provides this variable.
# You can also manually set WEBHOOK_URL if needed.
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")

if not WEBHOOK_URL:
    render_url = os.environ.get("RENDER_EXTERNAL_URL")
    if render_url:
        WEBHOOK_URL = render_url.rstrip("/") + "/webhook"


# ============================================================
# Flask
# ============================================================

app = Flask(__name__)


# ============================================================
# Load Hafez data
# ============================================================

def load_hafez_data():
    if not os.path.exists(DATA_FILE):
        raise FileNotFoundError(
            f"Required file not found: {DATA_FILE}"
        )

    with open(DATA_FILE, "r", encoding="utf-8") as f:
        raw = json.load(f)

    records = []

    if not isinstance(raw, list):
        raise ValueError("HafezFilebot.json must contain a JSON array.")

    for item in raw:
        if not isinstance(item, dict):
            continue

        for record_id, data in item.items():
            if not isinstance(data, dict):
                continue

            title = str(data.get("Title", "")).strip()

            # Extract ghazal number from title:
            # غزل شمارهٔ ۱
            # غزل شماره ۱
            # غزل ۱
            match = re.search(r"(\d+)", title)

            if not match:
                continue

            ghazal_number = int(match.group(1))

            poem = str(data.get("Poem", "")).strip()
            source = str(data.get("Source", "")).strip()
            audio = str(data.get("Audio", "")).strip()

            if not poem:
                continue

            records.append(
                {
                    "id": str(record_id),
                    "number": ghazal_number,
                    "title": title,
                    "poem": poem,
                    "source": source,
                    "audio": audio,
                }
            )

    if not records:
        raise ValueError("No valid Hafez ghazals found.")

    return records


HAFEZ_DATA = load_hafez_data()


# ============================================================
# HTTP helpers
# ============================================================

SESSION = requests.Session()

SESSION.headers.update(
    {
        "User-Agent": (
            "Mozilla/5.0 "
            "(Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "Chrome/131.0 Safari/537.36"
        )
    }
)


def api_call(method, payload=None, files=None, timeout=30):
    """
    Call Soroush Plus Bot API.
    """
    url = f"{API}/{method}"

    try:
        if files:
            response = SESSION.post(
                url,
                data=payload or {},
                files=files,
                timeout=timeout,
            )
        else:
            response = SESSION.post(
                url,
                json=payload or {},
                timeout=timeout,
            )

        try:
            result = response.json()
        except Exception:
            result = {
                "ok": False,
                "description": response.text[:500],
            }

        print(
            f"[SPLUS] {method}: "
            f"{response.status_code} "
            f"{result}"
        )

        return result

    except Exception as e:
        print(f"[SPLUS ERROR] {method}: {e}")
        return {
            "ok": False,
            "description": str(e),
        }


# ============================================================
# Keyboard
# ============================================================

def main_keyboard():
    return {
        "keyboard": [
            [
                {
                    "text": BUTTON_TEXT
                }
            ]
        ],
        "resize_keyboard": True,
        "one_time_keyboard": False,
    }


# ============================================================
# Send message
# ============================================================

def send_message(chat_id, text, reply_markup=None):
    payload = {
        "chat_id": chat_id,
        "text": text,
    }

    if reply_markup is not None:
        payload["reply_markup"] = reply_markup

    return api_call("sendMessage", payload)


# ============================================================
# Send voice
# ============================================================

def send_voice(chat_id, audio_url):
    """
    Ganjoor audio in HafezFilebot.json is normally OGG.
    Soroush Plus supports OGG/Opus through sendVoice.

    First try the remote URL directly.
    If that fails, download the file and upload it.
    """

    if not audio_url:
        return None

    # --------------------------------------------------------
    # First attempt: send URL directly
    # --------------------------------------------------------

    result = api_call(
        "sendVoice",
        {
            "chat_id": chat_id,
            "voice": audio_url,
        },
        timeout=30,
    )

    if result.get("ok"):
        return result

    print("[VOICE] Direct URL failed. Trying download/upload...")

    # --------------------------------------------------------
    # Second attempt: download and upload
    # --------------------------------------------------------

    try:
        response = SESSION.get(
            audio_url,
            timeout=30,
            stream=True,
        )

        response.raise_for_status()

        audio_bytes = response.content

        if not audio_bytes:
            print("[VOICE] Empty audio file.")
            return result

        filename = os.path.basename(
            audio_url.split("?")[0]
        ) or "hafez.ogg"

        upload_payload = {
            "chat_id": str(chat_id),
        }

        upload_files = {
            "voice": (
                filename,
                audio_bytes,
                "audio/ogg",
            )
        }

        return api_call(
            "sendVoice",
            upload_payload,
            files=upload_files,
            timeout=60,
        )

    except Exception as e:
        print(f"[VOICE ERROR] {e}")
        return result


# ============================================================
# Interpretation
# ============================================================

def extract_interpretation(html, ghazal_number):
    """
    Extract the 'نتیجه تفال' section from hafez.top.

    Example page structure:

    نتیجه تفال شما به غزل 1 حافظ
    ...
    ...
    تفسیر کامل غزل 1 حافظ
    """

    # Normalize HTML a little
    html = html.replace("\r", "\n")

    # Remove scripts/styles
    html = re.sub(
        r"<script\b[^>]*>.*?</script>",
        " ",
        html,
        flags=re.I | re.S,
    )

    html = re.sub(
        r"<style\b[^>]*>.*?</style>",
        " ",
        html,
        flags=re.I | re.S,
    )

    # Convert common block tags to newlines
    html = re.sub(
        r"</(?:p|div|li|h1|h2|h3|h4|h5|h6|br|section)>",
        "\n",
        html,
        flags=re.I,
    )

    # Remove remaining tags
    text = re.sub(r"<[^>]+>", " ", html)

    # Decode common HTML entities
    import html as html_module

    text = html_module.unescape(text)

    # Normalize whitespace
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)

    # --------------------------------------------------------
    # Find the interpretation/result section
    # --------------------------------------------------------

    patterns = [
        rf"نتیجه\s+تفال\s+شما\s+به\s+غزل\s*{ghazal_number}\s*حافظ",
        rf"نتیجه\s+تفال\s+شما\s+به\s+غزل\s*{ghazal_number}",
        r"نتیجه\s+تفال\s+شما\s+به\s+غزل",
    ]

    start = -1

    for pattern in patterns:
        match = re.search(
            pattern,
            text,
            flags=re.I,
        )

        if match:
            start = match.end()
            break

    if start == -1:
        return None

    # Stop before the long literary interpretation section
    stop_patterns = [
        r"تفسیر\s+کامل\s+غزل",
        r"تفسیر\s+غزل",
        r"معنی\s+و\s+تفسیر\s+غزل",
        r"غزل‌های\s+مشابه",
        r"دیدگاه",
    ]

    end = len(text)

    for pattern in stop_patterns:
        match = re.search(
            pattern,
            text[start:],
            flags=re.I,
        )

        if match:
            candidate_end = start + match.start()

            if candidate_end < end:
                end = candidate_end

    interpretation = text[start:end].strip()

    # Remove navigation/noise
    interpretation = re.sub(
        r"\s*[\r\n]+\s*",
        "\n",
        interpretation,
    )

    interpretation = re.sub(
        r"\n{3,}",
        "\n\n",
        interpretation,
    )

    # Remove leading/trailing punctuation/noise
    interpretation = interpretation.strip(
        " \n\r\t:|-"
    )

    # If extraction accidentally became too short,
    # return None so fallback can be used.
    if len(interpretation) < 30:
        return None

    return interpretation


def fetch_interpretation(ghazal_number):
    """
    Fetch the interpretation for the exact selected ghazal.
    """

    url = f"https://hafez.top/ghazal-{ghazal_number}/"

    try:
        response = SESSION.get(
            url,
            timeout=15,
        )

        response.raise_for_status()

        response.encoding = response.apparent_encoding or "utf-8"

        interpretation = extract_interpretation(
            response.text,
            ghazal_number,
        )

        if interpretation:
            return interpretation

        print(
            f"[INTERPRETATION] "
            f"Could not extract ghazal {ghazal_number}"
        )

    except Exception as e:
        print(
            f"[INTERPRETATION ERROR] "
            f"Ghazal {ghazal_number}: {e}"
        )

    return (
        "تعبیر این غزل در حال حاضر در دسترس نیست.\n"
        "لطفاً چند لحظه بعد دوباره تلاش کنید."
    )


# ============================================================
# Format poem
# ============================================================

def clean_poem(poem):
    """
    Keep the original poem as much as possible,
    while normalizing excessive blank lines.
    """

    poem = poem.replace("\r\n", "\n")
    poem = poem.replace("\r", "\n")

    poem = re.sub(
        r"\n{3,}",
        "\n\n",
        poem,
    )

    return poem.strip()


# ============================================================
# Build fortune
# ============================================================

def build_fortune(record):
    number = record["number"]

    poem = clean_poem(record["poem"])

    source = record["source"]

    interpretation = fetch_interpretation(number)

    text = (
        "فال حافظ\n"
        f"شماره غزل {number}\n\n"
        f"{poem}\n\n"
        "منبع گنجور\n"
        f"{source}\n"
        f"{CHANNEL_TAG}\n\n"
        "──────────────\n\n"
        "🌌 تعبیر\n\n"
        f"{interpretation}\n\n"
        f"{CHANNEL_TAG}"
    )

    return text


# ============================================================
# Process Hafez fortune
# ============================================================

def send_fortune(chat_id):
    """
    Select ONE random ghazal.

    Everything afterwards uses that same record:
      - number
      - poem
      - source
      - audio
      - interpretation
    """

    record = random.choice(HAFEZ_DATA)

    print(
        f"[FORTUNE] "
        f"Selected ghazal #{record['number']} "
        f"record={record['id']}"
    )

    # --------------------------------------------------------
    # Main text
    # --------------------------------------------------------

    text = build_fortune(record)

    send_message(
        chat_id,
        text,
        reply_markup=main_keyboard(),
    )

    # --------------------------------------------------------
    # Audio - ALWAYS separate message
    # --------------------------------------------------------

    audio_url = record.get("audio")

    if audio_url:
        print(
            f"[AUDIO] "
            f"Ghazal #{record['number']} -> {audio_url}"
        )

        send_voice(
            chat_id,
            audio_url,
        )

    return True


# ============================================================
# Handle incoming message
# ============================================================

def handle_message(message):
    if not isinstance(message, dict):
        return

    chat = message.get("chat") or {}

    chat_id = chat.get("id")

    if chat_id is None:
        print("[MESSAGE] No chat_id.")
        return

    text = message.get("text") or ""
    text = text.strip()

    print(
        f"[MESSAGE] "
        f"chat_id={chat_id} "
        f"text={text!r}"
    )

    # --------------------------------------------------------
    # Start
    # --------------------------------------------------------

    if text in (
        "/start",
        "/start@hafez_bot",
        "شروع",
    ):
        send_message(
            chat_id,
            "به فال حافظ خوش آمدید 🌿\n\n"
            "برای گرفتن فال، دکمه زیر را بزنید.",
            reply_markup=main_keyboard(),
        )
        return

    # --------------------------------------------------------
    # Hafez button
    # --------------------------------------------------------

    if text == BUTTON_TEXT:
        send_message(
            chat_id,
            "🌿 نیت کنید...\n\n"
            "در حال گرفتن فال حافظ",
        )

        try:
            send_fortune(chat_id)

        except Exception as e:
            print(f"[FORTUNE ERROR] {e}")

            send_message(
                chat_id,
                "متأسفانه هنگام گرفتن فال مشکلی پیش آمد.\n"
                "لطفاً دوباره تلاش کنید.",
                reply_markup=main_keyboard(),
            )

        return

    # --------------------------------------------------------
    # Any other message
    # --------------------------------------------------------

    send_message(
        chat_id,
        "برای گرفتن فال حافظ، دکمه زیر را بزنید.",
        reply_markup=main_keyboard(),
    )


# ============================================================
# Webhook
# ============================================================

@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        update = request.get_json(
            silent=True
        )

        if not update:
            return jsonify(
                {
                    "ok": True
                }
            )

        print(
            "[UPDATE]",
            json.dumps(
                update,
                ensure_ascii=False,
            )[:3000],
        )

        message = update.get("message")

        if message:
            # Process immediately.
            # Soroush webhook receives a successful HTTP response
            # only after this handler returns, so do the work in
            # a background thread.
            thread = threading.Thread(
                target=handle_message,
                args=(message,),
                daemon=True,
            )
            thread.start()

        return jsonify(
            {
                "ok": True
            }
        )

    except Exception as e:
        print(f"[WEBHOOK ERROR] {e}")

        # Still return 200 to avoid repeated webhook delivery
        # for malformed/non-critical updates.
        return jsonify(
            {
                "ok": True
            }
        )


# ============================================================
# Health check
# ============================================================

@app.route("/", methods=["GET"])
def health():
    return jsonify(
        {
            "ok": True,
            "bot": "hafez-bot",
            "ghazals": len(HAFEZ_DATA),
        }
    )


@app.route("/health", methods=["GET"])
def health_check():
    return jsonify(
        {
            "ok": True,
            "service": "hafez-bot",
            "ghazals": len(HAFEZ_DATA),
        }
    )


# ============================================================
# Set webhook
# ============================================================

def setup_webhook():
    if not WEBHOOK_URL:
        print(
            "[WEBHOOK] WEBHOOK_URL / "
            "RENDER_EXTERNAL_URL not available."
        )
        return

    print(
        f"[WEBHOOK] Setting webhook: {WEBHOOK_URL}"
    )

    result = api_call(
        "setWebhook",
        {
            "url": WEBHOOK_URL,
            "allowed_updates": ["message"],
            "drop_pending_updates": True,
        },
        timeout=30,
    )

    print(
        "[WEBHOOK RESULT]",
        result,
    )


# ============================================================
# Start webhook setup
# ============================================================

def start_webhook_setup():
    # Small delay gives Gunicorn/Render time to finish startup.
    time.sleep(2)
    setup_webhook()


threading.Thread(
    target=start_webhook_setup,
    daemon=True,
).start()


# ============================================================
# Local execution
# ============================================================

if __name__ == "__main__":
    port = int(
        os.environ.get(
            "PORT",
            "10000",
        )
    )

    app.run(
        host="0.0.0.0",
        port=port,
        )
