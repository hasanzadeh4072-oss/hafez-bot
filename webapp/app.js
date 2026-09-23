const DATA_URL = "../HafezFilebot.json";
const TABIR_URL = "../Hafez_Tabir.json";

let ghazals = [];
let interpretations = [];


/* =========================
   بارگذاری اطلاعات
========================= */

async function loadData() {
    const [ghazalResponse, tabirResponse] = await Promise.all([
        fetch(DATA_URL, { cache: "no-store" }),
        fetch(TABIR_URL, { cache: "no-store" })
    ]);

    if (!ghazalResponse.ok) {
        throw new Error("خطا در دریافت HafezFilebot.json");
    }

    if (!tabirResponse.ok) {
        throw new Error("خطا در دریافت Hafez_Tabir.json");
    }

    const ghazalData = await ghazalResponse.json();
    const tabirData = await tabirResponse.json();


    /*
     * HafezFilebot.json معمولاً به صورت:
     *
     * {
     *   "2301": {
     *      "Poem": "...",
     *      "Title": "غزل شمارهٔ ۱۷۲",
     *      "Audio": "https://i.ganjoor.net/a/2301.ogg"
     *   }
     * }
     *
     * است.
     */

    if (Array.isArray(ghazalData)) {
        ghazals = ghazalData;
    } else {
        ghazals = Object.values(ghazalData || {});
    }


    if (Array.isArray(tabirData)) {
        interpretations = tabirData;
    } else {
        interpretations = Object.values(tabirData || {});
    }


    if (!ghazals.length) {
        throw new Error("بانک اشعار خالی است");
    }
}


/* =========================
   شماره غزل
========================= */

function getGhazalNumber(record) {

    const source =
        String(record?.Source || "").trim();

    const sourceMatch =
        source.match(/\/sh(\d+)/i);

    if (sourceMatch) {
        return Number(sourceMatch[1]);
    }


    const title =
        String(record?.Title || "").trim();

    const titleMatch =
        title.match(/(\d+)/);

    if (titleMatch) {
        return Number(titleMatch[1]);
    }


    return null;
}


/* =========================
   متن تعبیر
========================= */

function getInterpretationText(record) {

    if (!record) {
        return "";
    }

    return (
        record.Interpretation ??
        record.interpretation ??
        record.Tabir ??
        record.tabir ??
        record["تعبیر"] ??
        record["متن"] ??
        ""
    );
}


/* =========================
   پیدا کردن تعبیر
========================= */

function findInterpretation(ghazalNumber) {

    if (!ghazalNumber) {
        return "";
    }


    /*
     * اول فیلد شمارهٔ صریح را بررسی می‌کنیم.
     */

    for (const record of interpretations) {

        const fields = [
            record.Number,
            record.number,
            record.No,
            record.no,
            record.ID,
            record.Id,
            record.id,
            record["غزل"],
            record["شماره"]
        ];


        for (const value of fields) {

            if (
                value !== undefined &&
                value !== null &&
                String(value).trim() !== ""
            ) {

                const number = Number(value);

                if (
                    Number.isInteger(number) &&
                    number === ghazalNumber
                ) {
                    return getInterpretationText(record);
                }
            }
        }
    }


    /*
     * اگر شمارهٔ غزل داخل رکورد تعبیر نباشد،
     * ترتیب رکوردها را به عنوان شمارهٔ غزل در نظر می‌گیریم.
     */

    const index = ghazalNumber - 1;

    if (
        index >= 0 &&
        index < interpretations.length
    ) {
        return getInterpretationText(
            interpretations[index]
        );
    }


    return "";
}


/* =========================
   ساخت لینک صوت فریدون فرح‌اندوز
========================= */

function getAudioUrl(record) {

    /*
     * فقط و فقط مقدار Audio از بانک اصلی خوانده می‌شود.
     *
     * مثال:
     *
     * Audio:
     * https://i.ganjoor.net/a/2237.ogg
     *
     * تبدیل:
     * https://i.ganjoor.net/a/2237-ff.mp3
     */


    const audio =
        String(record?.Audio || "").trim();


    if (!audio) {
        return "";
    }


    /*
     * شناسه فایل را از انتهای URL استخراج می‌کنیم.
     */

    const match =
        audio.match(
            /\/a\/(\d+)(?:\.[^/?#]+)?(?:[?#].*)?$/i
        );


    if (!match) {
        console.warn(
            "[AUDIO] Cannot extract audio ID:",
            audio
        );

        return "";
    }


    const audioId = match[1];


    const finalUrl =
        `https://i.ganjoor.net/a/${audioId}-ff.mp3`;


    console.log(
        "[AUDIO]",
        audio,
        "=>",
        finalUrl
    );


    return finalUrl;
}


/* =========================
   انتخاب غزل تصادفی
========================= */

function getRandomGhazal() {

    if (!ghazals.length) {
        return null;
    }


    const index =
        Math.floor(
            Math.random() * ghazals.length
        );


    return ghazals[index];
}


/* =========================
   تغییر صفحه
========================= */

function showScreen(screenId) {

    document
        .querySelectorAll(".screen")
        .forEach(screen => {
            screen.classList.remove("active");
        });


    const screen =
        document.getElementById(screenId);


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

    const record =
        getRandomGhazal();


    if (!record) {
        alert("امکان دریافت فال وجود ندارد.");
        return;
    }


    const titleElement =
        document.getElementById("poemTitle");

    const poemElement =
        document.getElementById("poemText");

    const sourceElement =
        document.getElementById("poemSource");

    const interpretationElement =
        document.getElementById("interpretation");

    const audioPlayer =
        document.getElementById("audioPlayer");


    /* عنوان */

    titleElement.textContent =
        record.Title || "فال حافظ";


    /* شعر */

    poemElement.textContent =
        record.Poem || "";


    /* منبع */

    const source =
        String(record.Source || "").trim();


    sourceElement.textContent =
        source
            ? `منبع: ${source}`
            : "";


    /* تعبیر */

    const ghazalNumber =
        getGhazalNumber(record);


    const interpretation =
        findInterpretation(
            ghazalNumber
        );


    interpretationElement.textContent =
        interpretation ||
        "تعبیر این فال در بانک موجود نیست.";


    /* صوت */

    audioPlayer.pause();

    audioPlayer.removeAttribute("src");

    audioPlayer.load();


    const audioUrl =
        getAudioUrl(record);


    if (audioUrl) {

        audioPlayer.src =
            audioUrl;

        audioPlayer.load();

        audioPlayer.style.display =
            "block";

    } else {

        audioPlayer.style.display =
            "none";
    }


    /* نمایش فال */

    showScreen("fortuneScreen");
}


/* =========================
   شروع برنامه
========================= */

document.addEventListener(
    "DOMContentLoaded",
    async () => {

        const fortuneButton =
            document.getElementById(
                "fortuneButton"
            );

        const newFortuneButton =
            document.getElementById(
                "newFortuneButton"
            );


        fortuneButton.disabled = true;


        try {

            await loadData();

            fortuneButton.disabled =
                false;


            console.log(
                `[DATA] Loaded ${ghazals.length} ghazals`
            );

        } catch (error) {

            console.error(
                "[DATA ERROR]",
                error
            );


            alert(
                "بارگذاری اطلاعات فال با مشکل مواجه شد."
            );


            return;
        }


        fortuneButton.addEventListener(
            "click",
            showFortune
        );


        newFortuneButton.addEventListener(
            "click",
            showFortune
        );
    }
);
