const DATA_URL = "../HafezFilebot.json";
const TABIR_URL = "../Hafez_Tabir.json";

let ghazals = [];
let interpretations = [];


/* =========================
   ابزارهای کمکی
========================= */

function normalizeText(value) {
    return String(value ?? "")
        .replace(/\u200c/g, " ")
        .replace(/\s+/g, " ")
        .trim();
}


function getGhazalNumber(record) {
    const source = String(record?.Source || "").trim();

    const sourceMatch = source.match(/\/sh(\d+)/i);
    if (sourceMatch) {
        return Number(sourceMatch[1]);
    }

    const title = String(record?.Title || "").trim();

    const titleMatch = title.match(/(\d+)/);
    if (titleMatch) {
        return Number(titleMatch[1]);
    }

    return null;
}


function getInterpretationNumber(record, index) {
    const possibleFields = [
        record?.Number,
        record?.number,
        record?.No,
        record?.no,
        record?.ID,
        record?.Id,
        record?.id,
        record?.غزل,
        record?.شماره
    ];

    for (const value of possibleFields) {
        const number = Number(value);

        if (Number.isInteger(number) && number > 0) {
            return number;
        }
    }

    // در Hafez_Tabir.json شمارهٔ غزل بر اساس ترتیب رکوردهاست
    return index + 1;
}


/* =========================
   لینک صوت
========================= */

function getAudioUrl(record) {
    const audio = String(record?.Audio || "").trim();

    if (!audio) {
        return "";
    }

    /*
     * لینک جدید خوانش فریدون فرح‌اندوز
     *
     * نمونه:
     * https://i.ganjoor.net/a/2301.ogg
     *
     * تبدیل می‌شود به:
     * https://i.ganjoor.net/a/2301-ff.mp3
     */

    const match = audio.match(
        /^(https?:\/\/i\.ganjoor\.net\/a\/)(\d+)(?:\.(?:ogg|mp3))$/i
    );

    if (match) {
        return `${match[1]}${match[2]}-ff.mp3`;
    }

    /*
     * اگر لینک از قبل به شکل -ff.mp3 باشد،
     * همان لینک استفاده می‌شود.
     */

    if (/-ff\.mp3$/i.test(audio)) {
        return audio;
    }

    return audio;
}


/* =========================
   دریافت اطلاعات
========================= */

async function loadData() {
    const [ghazalResponse, tabirResponse] = await Promise.all([
        fetch(DATA_URL, { cache: "no-store" }),
        fetch(TABIR_URL, { cache: "no-store" })
    ]);

    if (!ghazalResponse.ok) {
        throw new Error("خطا در دریافت بانک اشعار");
    }

    if (!tabirResponse.ok) {
        throw new Error("خطا در دریافت بانک تعبیر");
    }

    const ghazalData = await ghazalResponse.json();
    const tabirData = await tabirResponse.json();

    ghazals = Array.isArray(ghazalData)
        ? ghazalData
        : Object.values(ghazalData || {});

    interpretations = Array.isArray(tabirData)
        ? tabirData
        : Object.values(tabirData || {});

    if (!ghazals.length) {
        throw new Error("بانک اشعار خالی است");
    }
}


/* =========================
   پیدا کردن تعبیر
========================= */

function findInterpretation(ghazalNumber) {
    if (!ghazalNumber) {
        return "";
    }

    for (let index = 0; index < interpretations.length; index++) {
        const record = interpretations[index];

        const number = getInterpretationNumber(record, index);

        if (number === ghazalNumber) {
            return (
                record?.Interpretation ??
                record?.interpretation ??
                record?.Tabir ??
                record?.tabir ??
                record?.تعبیر ??
                record?.متن ??
                ""
            );
        }
    }

    return "";
}


/* =========================
   انتخاب فال
========================= */

function getRandomGhazal() {
    if (!ghazals.length) {
        return null;
    }

    const index = Math.floor(Math.random() * ghazals.length);

    return ghazals[index];
}


/* =========================
   نمایش صفحه
========================= */

function showScreen(screenId) {
    document.querySelectorAll(".screen").forEach(screen => {
        screen.classList.remove("active");
    });

    const screen = document.getElementById(screenId);

    if (screen) {
        screen.classList.add("active");
    }

    window.scrollTo({
        top: 0,
        behavior: "smooth"
    });
}


/* =========================
   نمایش فال
========================= */

function showFortune() {
    const record = getRandomGhazal();

    if (!record) {
        alert("امکان دریافت فال وجود ندارد.");
        return;
    }

    const titleElement = document.getElementById("poemTitle");
    const poemElement = document.getElementById("poemText");
    const sourceElement = document.getElementById("poemSource");
    const interpretationElement =
        document.getElementById("interpretation");
    const audioPlayer =
        document.getElementById("audioPlayer");

    const title =
        record?.Title ||
        "";

    const poem =
        record?.Poem ||
        "";

    const source =
        record?.Source ||
        "";

    const ghazalNumber =
        getGhazalNumber(record);

    const interpretation =
        findInterpretation(ghazalNumber);

    const audioUrl =
        getAudioUrl(record);


    /* عنوان */

    titleElement.textContent = title;


    /* شعر */

    poemElement.textContent = poem;


    /* منبع */

    if (source) {
        sourceElement.textContent = `منبع: ${source}`;
    } else {
        sourceElement.textContent = "";
    }


    /* تعبیر */

    if (interpretation) {
        interpretationElement.textContent =
            interpretation;
    } else {
        interpretationElement.textContent =
            "تعبیر این فال در بانک موجود نیست.";
    }


    /* صوت */

    audioPlayer.pause();

    audioPlayer.removeAttribute("src");

    if (audioUrl) {
        audioPlayer.src = audioUrl;
        audioPlayer.load();
    }


    showScreen("fortuneScreen");
}


/* =========================
   رویدادها
========================= */

document.addEventListener("DOMContentLoaded", async () => {

    const fortuneButton =
        document.getElementById("fortuneButton");

    const newFortuneButton =
        document.getElementById("newFortuneButton");


    fortuneButton.disabled = true;

    try {
        await loadData();

        fortuneButton.disabled = false;

    } catch (error) {
        console.error(
            "خطا در بارگذاری اطلاعات:",
            error
        );

        alert(
            "بارگذاری اطلاعات فال با مشکل مواجه شد."
        );

        return;
    }


    fortuneButton.addEventListener(
        "click",
        () => {
            showFortune();
        }
    );


    newFortuneButton.addEventListener(
        "click",
        () => {
            showFortune();
        }
    );
});
