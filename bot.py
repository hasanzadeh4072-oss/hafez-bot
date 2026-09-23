import os, random, time, threading, requests, uuid, io, cairosvg
from flask import Flask, request
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance

app = Flask(__name__)

TOKEN = os.environ.get("SOROUSH_TOKEN")

if not TOKEN:
    raise RuntimeError("SOROUSH_TOKEN environment variable is not set.")

API = f"https://api.splus.ir/bot{TOKEN}"
CHANNEL_URL = "https://splus.ir/life_m23"

W = H = 1080
S = 2
RW = RH = W * S

POEM_FONT = "Parastoo[wght].ttf"
TITLE_FONT = "BTitrBd.ttf"
SUB_FONT = FOOT_FONT = "Vazirmatn-Regular.ttf"

BG_URL = (
    "https://raw.githubusercontent.com/"
    "hasanzadeh4072-oss/Soroush-Poetry-Card-Bot/"
    "be5859ec92836a14ef0ef28d82ca6c161959cb26/"
    "tazhib-21-v1-t1-pub1-inkscape-plain.svg"
)

TIMEOUT = 120

LINE_SPACING = 32
BLANK_LINE_SPACING = 48

PENDING = {}
READY = {}
TIMERS = {}

LOCK = threading.RLock()
HTTP = threading.local()
FONT_CACHE = {}

BG = None
BACKGROUNDS = {}
TEXTURE = None
PANEL = None

PALETTES = [
    {
        "name":"بنفش سلطنتی","top":(55,25,82),"middle":(32,21,53),"bottom":(13,10,25),
        "glow1":(160,105,200,38),"glow2":(105,70,160,22),"glow3":(100,65,145,10),
        "frame":(173,137,82),"frame_inner":(205,172,105),"text":(255,255,255),
        "accent":(244,210,137),"subtitle":(205,191,168),"ornament":(145,112,68),
        "panel_outline":(205,172,105,38),"side_line":(205,172,105,75),"side_dot":(205,172,105,100)
    },
    {
        "name":"آبی شبانه","top":(18,39,76),"middle":(16,27,53),"bottom":(7,11,23),
        "glow1":(75,115,185,32),"glow2":(50,80,150,22),"glow3":(55,85,140,10),
        "frame":(165,140,83),"frame_inner":(200,170,103),"text":(255,255,255),
        "accent":(239,210,139),"subtitle":(195,204,211),"ornament":(140,125,82),
        "panel_outline":(190,170,110,38),"side_line":(200,175,110,75),"side_dot":(215,185,115,100)
    },
    {
        "name":"شرابی","top":(76,19,37),"middle":(45,14,26),"bottom":(20,6,13),
        "glow1":(175,70,90,35),"glow2":(135,45,65,20),"glow3":(130,45,60,10),
        "frame":(174,133,72),"frame_inner":(205,169,98),"text":(255,255,255),
        "accent":(241,210,139),"subtitle":(211,193,181),"ornament":(145,105,65),
        "panel_outline":(195,155,95,38),"side_line":(200,160,100,75),"side_dot":(215,175,105,100)
    },
    {
        "name":"فیروزه‌ای تیره","top":(10,61,67),"middle":(9,39,45),"bottom":(4,17,21),
        "glow1":(55,155,165,34),"glow2":(35,110,125,20),"glow3":(40,120,130,10),
        "frame":(172,145,91),"frame_inner":(205,177,112),"text":(255,255,255),
        "accent":(224,199,132),"subtitle":(188,209,208),"ornament":(130,137,91),
        "panel_outline":(185,170,110,38),"side_line":(185,175,110,75),"side_dot":(210,190,120,100)
    },
    {
        "name":"سبز زمردی","top":(12,59,51),"middle":(13,38,35),"bottom":(5,18,17),
        "glow1":(65,145,120,35),"glow2":(45,110,95,20),"glow3":(40,100,85,10),
        "frame":(168,139,78),"frame_inner":(200,169,99),"text":(255,255,255),
        "accent":(239,211,137),"subtitle":(194,207,197),"ornament":(140,118,70),
        "panel_outline":(190,165,100,38),"side_line":(190,170,105,75),"side_dot":(210,180,110,100)
    },
    {
        "name":"رزگلد","top":(72,35,48),"middle":(45,23,32),"bottom":(19,9,14),
        "glow1":(190,105,120,32),"glow2":(150,75,95,20),"glow3":(135,70,85,10),
        "frame":(181,125,119),"frame_inner":(218,165,154),"text":(255,255,255),
        "accent":(235,181,163),"subtitle":(216,194,187),"ornament":(164,112,106),
        "panel_outline":(215,160,150,38),"side_line":(210,155,145,75),"side_dot":(225,170,158,100)
    },
    {
        "name":"کرم","top":(250,239,210),"middle":(242,226,190),"bottom":(226,205,163),
        "glow1":(255,252,230,55),"glow2":(255,240,185,28),"glow3":(255,255,255,22),
        "frame":(91,67,39),"frame_inner":(126,96,58),"text":(49,40,31),
        "accent":(104,73,38),"subtitle":(77,61,43),"ornament":(113,80,42),
        "panel_outline":(105,78,43,55),"side_line":(105,78,43,85),"side_dot":(94,67,35,125)
    },
    {
        "name":"آبی روشن","top":(205,235,248),"middle":(180,220,238),"bottom":(153,201,225),
        "glow1":(235,249,255,58),"glow2":(145,205,235,28),"glow3":(255,255,255,24),
        "frame":(43,73,91),"frame_inner":(72,105,124),"text":(31,51,63),
        "accent":(48,82,101),"subtitle":(54,77,91),"ornament":(59,91,108),
        "panel_outline":(58,91,110,55),"side_line":(58,91,110,85),"side_dot":(46,79,99,125)
    },
    {
        "name":"مریم‌گلی","top":(218,231,205),"middle":(201,219,184),"bottom":(179,201,159),
        "glow1":(242,249,230,58),"glow2":(175,205,145,28),"glow3":(255,255,255,24),
        "frame":(60,76,52),"frame_inner":(91,108,78),"text":(39,54,35),
        "accent":(67,88,55),"subtitle":(67,82,59),"ornament":(75,96,62),
        "panel_outline":(73,96,62,55),"side_line":(73,96,62,85),"side_dot":(62,84,52,125)
    }
]


def session():
    s = getattr(HTTP, "s", None)

    if s is None:
        s = requests.Session()

        adapter = requests.adapters.HTTPAdapter(
            pool_connections=20,
            pool_maxsize=20,
            max_retries=0
        )

        s.mount("http://", adapter)
        s.mount("https://", adapter)

        HTTP.s = s

    return s


class D:
    def __init__(self, image):
        self.image = image
        self.draw = ImageDraw.Draw(image)

    def p(self, point):
        return tuple(int(round(v * S)) for v in point)

    def b(self, box):
        return tuple(int(round(v * S)) for v in box)

    def text(self, xy, text, font, **kwargs):
        return self.draw.text(
            self.p(xy),
            text,
            font=font,
            **kwargs
        )

    def bbox(self, xy, text, font, **kwargs):
        b = self.draw.textbbox(
            self.p(xy),
            text,
            font=font,
            **kwargs
        )

        return tuple(v / S for v in b)

    def line(self, xy, **kwargs):
        if "width" in kwargs:
            kwargs["width"] = max(
                1,
                int(round(kwargs["width"] * S))
            )

        return self.draw.line(
            [self.p(x) for x in xy],
            **kwargs
        )

    def rr(self, box, **kwargs):
        if "radius" in kwargs:
            kwargs["radius"] = int(
                round(kwargs["radius"] * S)
            )

        if "width" in kwargs:
            kwargs["width"] = max(
                1,
                int(round(kwargs["width"] * S))
            )

        return self.draw.rounded_rectangle(
            self.b(box),
            **kwargs
        )

    def ellipse(self, box, **kwargs):
        return self.draw.ellipse(
            self.b(box),
            **kwargs
        )

    def polygon(self, points, **kwargs):
        return self.draw.polygon(
            [self.p(x) for x in points],
            **kwargs
        )


def get_font(name, size):
    key = (
        name,
        int(round(size * S))
    )

    if key in FONT_CACHE:
        return FONT_CACHE[key]

    f = ImageFont.truetype(
        name,
        key[1]
    )

    if name == POEM_FONT:
        try:
            axes = f.get_variation_axes()

            for i, axis in enumerate(axes):
                if axis.get("name", "").lower() == "weight":

                    values = [
                        a.get(
                            "default",
                            a.get("min", 400)
                        )
                        for a in axes
                    ]

                    values[i] = 400
                    f.set_variation_by_axes(values)

                    break

        except Exception:
            pass

    FONT_CACHE[key] = f

    return f


def load_background():
    global BG

    try:
        response = session().get(
            BG_URL,
            timeout=30
        )

        response.raise_for_status()

        png = cairosvg.svg2png(
            bytestring=response.content,
            output_width=4320
        )

        image = Image.open(
            io.BytesIO(png)
        ).convert("RGBA")

        ratio = image.width / image.height
        target = RW / RH

        if ratio > target:
            nh = RH
            nw = int(
                image.width * RH / image.height
            )
        else:
            nw = RW
            nh = int(
                image.height * RW / image.width
            )

        image = image.resize(
            (nw, nh),
            Image.Resampling.LANCZOS
        )

        x = (nw - RW) // 2
        y = (nh - RH) // 2

        image = image.crop(
            (
                x,
                y,
                x + RW,
                y + RH
            )
        )

        image = ImageEnhance.Brightness(
            image
        ).enhance(.48)

        image = image.filter(
            ImageFilter.GaussianBlur(4 * S)
        )

        image.putalpha(42)

        BG = image

    except Exception as error:
        print(
            "Background error:",
            error
        )


def build_texture():
    global TEXTURE

    if TEXTURE is not None:
        return TEXTURE

    with LOCK:

        if TEXTURE is not None:
            return TEXTURE

        image = Image.new(
            "RGBA",
            (RW, RH),
            (0, 0, 0, 0)
        )

        pixels = image.load()

        rng = random.Random(8)

        for _ in range(56000):

            pixels[
                rng.randrange(RW),
                rng.randrange(RH)
            ] = rng.choice(
                [
                    (255,255,255,3),
                    (0,0,0,4)
                ]
            )

        TEXTURE = image

        return image


def make_background(p):
    image = Image.new(
        "RGB",
        (1, RH)
    )

    pixels = image.load()

    for y in range(RH):

        ratio = y / (RH - 1)

        if ratio < .52:
            a = p["top"]
            b = p["middle"]
            t = ratio / .52
        else:
            a = p["middle"]
            b = p["bottom"]
            t = (ratio - .52) / .48

        pixels[0, y] = tuple(
            int(
                a[i] * (1 - t) +
                b[i] * t
            )
            for i in range(3)
        )

    image = image.resize(
        (RW, RH),
        Image.Resampling.NEAREST
    ).convert("RGBA")

    if BG is not None:
        image = Image.alpha_composite(
            image,
            BG
        )

    glow = Image.new(
        "RGBA",
        (RW, RH),
        (0, 0, 0, 0)
    )

    d = ImageDraw.Draw(glow)

    d.ellipse(
        (-260*S, -180*S, 650*S, 560*S),
        fill=p["glow1"]
    )

    d.ellipse(
        (690*S, 690*S, 1250*S, 1250*S),
        fill=p["glow2"]
    )

    d.ellipse(
        (250*S, 350*S, 850*S, 950*S),
        fill=p["glow3"]
    )

    glow = glow.filter(
        ImageFilter.GaussianBlur(110 * S)
    )

    image = Image.alpha_composite(
        image,
        glow
    )

    return Image.alpha_composite(
        image,
        build_texture()
    ).convert("RGB")


def build_panel():
    global PANEL

    panel = Image.new(
        "RGBA",
        (RW, RH),
        (0, 0, 0, 0)
    )

    d = D(panel)

    d.rr(
        (100,164,980,896),
        radius=45,
        fill=(0,0,0,45)
    )

    d.rr(
        (100,160,980,890),
        radius=45,
        fill=(255,255,255,24)
    )

    d.rr(
        (110,170,970,880),
        radius=37,
        outline=(255,255,255,12),
        width=1
    )

    PANEL = panel.filter(
        ImageFilter.GaussianBlur(.35 * S)
    )


def initialize():
    global BACKGROUNDS

    load_background()
    build_texture()

    BACKGROUNDS = {
        p["name"]: make_background(p)
        for p in PALETTES
    }

    build_panel()


initialize()


def wrap_text(d, text, font_, max_width):
    words = text.split()

    if not words:
        return []

    lines = []

    current = words[0]

    for word in words[1:]:

        candidate = current + " " + word

        bbox = d.bbox(
            (0,0),
            candidate,
            font_
        )

        if bbox[2] - bbox[0] <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word

    lines.append(current)

    return lines


def prepare_lines(d, text, font_, max_width):
    result = []

    for raw in text.replace("…", "...").splitlines():

        if not raw.strip():
            result.append(None)
            continue

        result.extend(
            wrap_text(
                d,
                raw.strip(),
                font_,
                max_width
            )
        )

    return result


def calculate_height(
    d,
    lines,
    font_,
    line_spacing=LINE_SPACING,
    blank_spacing=BLANK_LINE_SPACING
):
    total = 0

    for line in lines:

        if line is None:
            total += blank_spacing
            continue

        bbox = d.bbox(
            (0,0),
            line,
            font_
        )

        total += (
            bbox[3] - bbox[1] +
            line_spacing
        )

    if lines and lines[-1] is not None:
        total -= line_spacing

    return total


def api(
    method,
    data=None,
    files=None,
    timeout=20
):
    try:
        return session().post(
            f"{API}/{method}",
            json=data if files is None else None,
            data=data if files is not None else None,
            files=files,
            timeout=timeout
        )

    except Exception as error:
        print(
            f"{method} error:",
            error
        )

        return None


def send_message(
    chat_id,
    text,
    markup=None
):
    data = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML"
    }

    if markup is not None:
        data["reply_markup"] = markup

    return api(
        "sendMessage",
        data
    )


def delete_message(
    chat_id,
    message_id
):
    return api(
        "deleteMessage",
        {
            "chat_id": chat_id,
            "message_id": message_id
        }
    )


def send_photo(
    chat_id,
    filename
):
    try:
        with open(
            filename,
            "rb"
        ) as photo:

            return api(
                "sendPhoto",
                {
                    "chat_id": chat_id
                },
                {
                    "photo": (
                        "poetry_card.png",
                        photo,
                        "image/png"
                    )
                },
                60
            )

    except Exception as error:
        print(
            "sendPhoto error:",
            error
        )

        return None


def answer_callback(callback_id):
    return api(
        "answerCallbackQuery",
        {
            "callback_query_id": callback_id
        }
    )


def expire_pending(
    chat_id,
    created_at
):
    with LOCK:

        pending = PENDING.get(chat_id)

        if not pending:
            TIMERS.pop(
                chat_id,
                None
            )
            return

        if pending.get("created_at") != created_at:
            return

        if time.time() - created_at >= TIMEOUT:

            PENDING.pop(
                chat_id,
                None
            )

            TIMERS.pop(
                chat_id,
                None
            )


def store_pending(
    chat_id,
    poem
):
    created_at = time.time()

    with LOCK:

        old = TIMERS.pop(
            chat_id,
            None
        )

        if old:
            old.cancel()

        PENDING[chat_id] = {
            "poem": poem,
            "branded": True,
            "created_at": created_at
        }

        timer = threading.Timer(
            TIMEOUT,
            expire_pending,
            (
                chat_id,
                created_at
            )
        )

        timer.daemon = True

        TIMERS[chat_id] = timer

        timer.start()


def refresh_timeout(chat_id):
    with LOCK:

        pending = PENDING.get(chat_id)

        if not pending:
            return

        old = TIMERS.pop(
            chat_id,
            None
        )

        if old:
            old.cancel()

        created_at = time.time()

        pending["created_at"] = created_at

        timer = threading.Timer(
            TIMEOUT,
            expire_pending,
            (
                chat_id,
                created_at
            )
        )

        timer.daemon = True

        TIMERS[chat_id] = timer

        timer.start()


def remove_previous_ready(chat_id):
    with LOCK:
        message_id = READY.get(chat_id)

    if not message_id:
        return

    response = delete_message(
        chat_id,
        message_id
    )

    if response is not None and response.ok:

        with LOCK:

            if READY.get(chat_id) == message_id:
                READY.pop(
                    chat_id,
                    None
                )


def draw_ornament(
    d,
    p,
    y
):
    center = W // 2
    width = 150

    d.line(
        (
            (center-width, y),
            (center-12, y)
        ),
        fill=p["ornament"],
        width=2
    )

    d.line(
        (
            (center+12, y),
            (center+width, y)
        ),
        fill=p["ornament"],
        width=2
    )

    d.polygon(
        [
            (center, y-5),
            (center+5, y),
            (center, y+5),
            (center-5, y)
        ],
        fill=p["accent"]
    )


def create_card(
    text,
    p,
    branded=True
):
    image = BACKGROUNDS[
        p["name"]
    ].copy().convert("RGBA")

    d = D(image)

    d.rr(
        (40,40,1040,1040),
        radius=42,
        outline=p["frame"],
        width=3
    )

    d.rr(
        (49,49,1031,1031),
        radius=35,
        outline=p["frame_inner"],
        width=2
    )

    title_font = get_font(
        TITLE_FONT,
        50
    )

    subtitle_font = get_font(
        SUB_FONT,
        23
    )

    footer_font = get_font(
        FOOT_FONT,
        23
    )

    title = "شعرکده"
    subtitle = "( سروش پلاس )"
    footer = "کارت شعر"

    def size(value, f):
        b = d.bbox(
            (0,0),
            value,
            f
        )

        return (
            b[2]-b[0],
            b[3]-b[1]
        )

    tw, th = size(
        title,
        title_font
    )

    sw, sh = size(
        subtitle,
        subtitle_font
    )

    fw, fh = size(
        footer,
        footer_font
    )

    center = W // 2

    footer_y = 78

    footer_x = (
        W - fw
    ) // 2

    title_y = (
        H - 78 - th
    )

    title_x = center + 10

    subtitle_x = (
        title_x - sw - 20
    )

    subtitle_y = (
        title_y +
        (th-sh)//2 -
        3
    )

    d.text(
        (footer_x+1, footer_y+2),
        footer,
        font=footer_font,
        fill=(0,0,0,60)
    )

    d.text(
        (footer_x, footer_y),
        footer,
        font=footer_font,
        fill=p["accent"]
    )

    draw_ornament(
        d,
        p,
        footer_y + fh + 25
    )

    if branded:

        d.text(
            (title_x+2, title_y+3),
            title,
            font=title_font,
            fill=(0,0,0,80)
        )

        d.text(
            (title_x, title_y),
            title,
            font=title_font,
            fill=p["accent"]
        )

        d.text(
            (subtitle_x, subtitle_y),
            subtitle,
            font=subtitle_font,
            fill=p["subtitle"]
        )

        draw_ornament(
            d,
            p,
            title_y - 25
        )

    else:

        draw_ornament(
            d,
            p,
            H - 112
        )

    panel = PANEL.copy()

    pd = D(panel)

    pd.rr(
        (100,160,980,890),
        radius=45,
        outline=p["panel_outline"],
        width=2
    )

    image = Image.alpha_composite(
        image,
        panel
    )

    d = D(image)

    left = 145
    right = 935

    top = 205
    bottom = 845

    max_width = right - left
    available_height = bottom - top

    font_size = 66

    lines = []

    line_spacing = LINE_SPACING
    blank_spacing = BLANK_LINE_SPACING

    while font_size >= 28:

        poem_font = get_font(
            POEM_FONT,
            font_size
        )

        lines = prepare_lines(
            d,
            text,
            poem_font,
            max_width
        )

        line_count = sum(
            1
            for line in lines
            if line is not None
        )

        # فاصلهٔ خطوط بر اساس تعداد خطوط واقعی شعر
        if line_count <= 2:
            current_line_spacing = 32
            current_blank_spacing = 48

        elif line_count == 3:
            current_line_spacing = 26
            current_blank_spacing = 40

        elif line_count == 4:
            current_line_spacing = 20
            current_blank_spacing = 32

        elif line_count == 5:
            current_line_spacing = 17
            current_blank_spacing = 28

        else:
            current_line_spacing = 14
            current_blank_spacing = 24

        height = calculate_height(
            d,
            lines,
            poem_font,
            current_line_spacing,
            current_blank_spacing
        )

        if height <= available_height:
            line_spacing = current_line_spacing
            blank_spacing = current_blank_spacing
            break

        font_size -= 2

    if not lines:

        poem_font = get_font(
            POEM_FONT,
            46
        )

        lines = [
            "متن خالی است"
        ]

        line_spacing = 20
        blank_spacing = 30

    items = []

    total_height = 0

    for index, line in enumerate(lines):

        if line is None:

            items.append(
                (
                    None,
                    None,
                    blank_spacing
                )
            )

            total_height += blank_spacing

            continue

        bbox = d.bbox(
            (0,0),
            line,
            poem_font
        )

        height = (
            bbox[3] -
            bbox[1]
        )

        items.append(
            (
                line,
                bbox,
                height
            )
        )

        total_height += height

        if index != len(lines)-1:
            total_height += line_spacing

    y = (
        top +
        (available_height - total_height) / 2
    )

    y = max(
        top,
        y
    )

    if y + total_height > bottom:
        y = bottom - total_height

    for line, bbox, height in items:

        if line is None:

            y += blank_spacing

            continue

        width = (
            bbox[2] -
            bbox[0]
        )

        x = (
            left +
            (max_width - width) / 2
        )

        d.text(
            (x, y - bbox[1]),
            line,
            font=poem_font,
            fill=p["text"]
        )

        y += (
            height +
            line_spacing
        )

    center_y = (
        top +
        (available_height // 2)
    )

    for x in (65, 1015):

        d.line(
            (
                (x, center_y-30),
                (x, center_y+30)
            ),
            fill=p["side_line"],
            width=2
        )

        d.ellipse(
            (
                x-3,
                center_y-3,
                x+3,
                center_y+3
            ),
            fill=p["side_dot"]
        )

    filename = (
        "/tmp/poetry_card_" +
        uuid.uuid4().hex +
        ".png"
    )

    image.resize(
        (W,H),
        Image.Resampling.LANCZOS
    ).convert("RGB").save(
        filename,
        "PNG",
        compress_level=2,
        optimize=False
    )

    return filename


def type_keyboard():
    return {
        "inline_keyboard": [
            [
                {
                    "text": "🖋️ با امضای شعرکده",
                    "callback_data": "type_branded"
                }
            ],
            [
                {
                    "text": "◻️ کارت عمومی، بدون امضا",
                    "callback_data": "type_public"
                }
            ]
        ]
    }


def color_keyboard():
    labels = [
        "🟣 سلطنتی",
        "🔵 آبی شبانه",
        "🔴 شرابی",
        "🩵 فیروزه‌ای تیره",
        "🟢 سبز زمردی",
        "🩷 رزگلد",
        "🟡 کرم",
        "🔵 آبی روشن",
        "🌿 مریم‌گلی"
    ]

    return {
        "inline_keyboard": [
            [
                {
                    "text": labels[i],
                    "callback_data": f"color_{i}"
                }
                for i in range(
                    row,
                    min(row+3, 9)
                )
            ]
            for row in range(0, 9, 3)
        ]
    }


def worker(
    chat_id,
    poem,
    p,
    branded
):
    filename = None
    building_id = None

    try:

        response = send_message(
            chat_id,
            "⏳ <b>کارت شعر در حال ساخت است...</b>"
        )

        if response is not None and response.ok:

            try:
                building_id = (
                    response.json()
                    .get("result", {})
                    .get("message_id")
                )

            except Exception:
                pass

        filename = create_card(
            poem,
            p,
            branded
        )

        response = send_photo(
            chat_id,
            filename
        )

        if response is not None and response.ok:

            if building_id:
                delete_message(
                    chat_id,
                    building_id
                )

            response = send_message(
                chat_id,
                "✨ کارت شعر شما آماده شد.\n\n"
                "اگر باز هم شعری دارید، همین‌جا ارسال کنید "
                "تا آن را هم به کارت شعر تبدیل کنیم. 🖼️\n\n"
                "📖 برای شعرهای بیشتر، سری به "
                f'<a href="{CHANNEL_URL}">«شعرکده»</a> '
                "در سروش پلاس بزنید."
            )

            if response is not None and response.ok:

                try:

                    ready_id = (
                        response.json()
                        .get("result", {})
                        .get("message_id")
                    )

                    if ready_id:

                        with LOCK:
                            READY[chat_id] = ready_id

                except Exception:
                    pass

        else:

            if building_id:
                delete_message(
                    chat_id,
                    building_id
                )

            send_message(
                chat_id,
                "✅ کارت ساخته شد، اما ارسال تصویر موفق نشد."
            )

    except Exception as error:

        print(
            "Card worker error:",
            error
        )

        if building_id:
            delete_message(
                chat_id,
                building_id
            )

        send_message(
            chat_id,
            "❌ هنگام ساخت کارت مشکلی پیش آمد."
        )

    finally:

        if filename and os.path.exists(filename):

            try:
                os.remove(filename)

            except Exception:
                pass


def process_type(update):
    q = update.get(
        "callback_query"
    ) or {}

    if q.get("id"):
        answer_callback(
            q["id"]
        )

    data = q.get("data")

    if data not in (
        "type_branded",
        "type_public"
    ):
        return "OK", 200

    message = q.get(
        "message"
    ) or {}

    chat = message.get(
        "chat"
    ) or {}

    chat_id = chat.get("id")
    message_id = message.get("message_id")

    if chat_id and message_id:
        delete_message(
            chat_id,
            message_id
        )

    if not chat_id:
        return "OK", 200

    with LOCK:
        pending = PENDING.get(
            chat_id
        )

    if not pending:

        send_message(
            chat_id,
            "⚠️ شعر در انتظار انتخاب پیدا نشد.\n\n"
            "لطفاً دوباره شعرت را ارسال کن."
        )

        return "OK", 200

    with LOCK:

        if chat_id in PENDING:

            PENDING[chat_id]["branded"] = (
                data == "type_branded"
            )

    refresh_timeout(
        chat_id
    )

    send_message(
        chat_id,
        "🎨 <b>حالا رنگ کارت شعر را انتخاب کن:</b>",
        color_keyboard()
    )

    return "OK", 200


def process_color(update):
    q = update.get(
        "callback_query"
    ) or {}

    if q.get("id"):
        answer_callback(
            q["id"]
        )

    data = q.get(
        "data",
        ""
    )

    if not data.startswith("color_"):
        return "OK", 200

    message = q.get(
        "message"
    ) or {}

    chat = message.get(
        "chat"
    ) or {}

    chat_id = chat.get("id")
    message_id = message.get("message_id")

    if chat_id and message_id:
        delete_message(
            chat_id,
            message_id
        )

    if not chat_id:
        return "OK", 200

    try:
        index = int(
            data[6:]
        )

    except ValueError:

        send_message(
            chat_id,
            "❌ رنگ انتخاب‌شده معتبر نیست."
        )

        return "OK", 200

    if not 0 <= index < len(PALETTES):

        send_message(
            chat_id,
            "❌ رنگ انتخاب‌شده معتبر نیست."
        )

        return "OK", 200

    with LOCK:

        pending = PENDING.pop(
            chat_id,
            None
        )

        timer = TIMERS.pop(
            chat_id,
            None
        )

    if timer:

        try:
            timer.cancel()

        except Exception:
            pass

    if not pending:

        send_message(
            chat_id,
            "⚠️ شعر در انتظار انتخاب پیدا نشد.\n\n"
            "لطفاً دوباره شعرت را ارسال کن."
        )

        return "OK", 200

    poem = pending.get(
        "poem"
    )

    if not poem:

        send_message(
            chat_id,
            "⚠️ متن شعر پیدا نشد.\n\n"
            "لطفاً دوباره شعرت را ارسال کن."
        )

        return "OK", 200

    threading.Thread(
        target=worker,
        args=(
            chat_id,
            poem,
            PALETTES[index],
            pending.get(
                "branded",
                True
            )
        ),
        daemon=True
    ).start()

    return "OK", 200


@app.route("/")
def home():
    return (
        "Poetry Card Bot is running",
        200
    )


@app.route(
    "/webhook",
    methods=["POST"]
)
def webhook():

    try:

        update = (
            request.get_json(
                silent=True
            ) or {}
        )

        if update.get(
            "callback_query"
        ):

            data = (
                update["callback_query"]
                .get("data", "")
            )

            if data in (
                "type_branded",
                "type_public"
            ):
                return process_type(
                    update
                )

            if data.startswith(
                "color_"
            ):
                return process_color(
                    update
                )

            return "OK", 200

        message = update.get(
            "message"
        ) or {}

        text = message.get(
            "text"
        )

        chat = message.get(
            "chat"
        ) or {}

        chat_id = chat.get(
            "id"
        )

        if not chat_id or not text:
            return "OK", 200

        if text == "/start":

            with LOCK:

                timer = TIMERS.pop(
                    chat_id,
                    None
                )

                PENDING.pop(
                    chat_id,
                    None
                )

                READY.pop(
                    chat_id,
                    None
                )

            if timer:

                try:
                    timer.cancel()

                except Exception:
                    pass

            send_message(
                chat_id,
                "سلام 👋\n\n"
                "🖼️ به بات کارت شعر خوش آمدی.\n\n"
                "شعرت را همین‌جا بفرست تا برایت کارت شعر بسازم. ✨\n\n"
                "📖 برای دیدن شعرهای بیشتر، "
                f'<a href="{CHANNEL_URL}">شعرکده</a> '
                "در سروش پلاس را دنبال کن."
            )

            return "OK", 200

        remove_previous_ready(
            chat_id
        )

        store_pending(
            chat_id,
            text
        )

        send_message(
            chat_id,
            "🖼️ <b>نوع کارت شعر را انتخاب کن:</b>\n\n"
            "🖋️ با امضای شعرکده\n"
            "کارت با عنوان و امضای شعرکده ساخته می‌شود.\n\n"
            "◻️ کارت عمومی\n"
            "کارت بدون نام و امضای شعرکده ساخته می‌شود.",
            type_keyboard()
        )

        return "OK", 200

    except Exception as error:

        print(
            "Webhook error:",
            error
        )

        raise


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(
            os.environ.get(
                "PORT",
                10000
            )
        ),
        threaded=True
             )
