const DATA_URL = "../HafezFilebot.json";
const TABIR_URL = "../Hafez_Tabir.json";

const AUDIO_BASE_URL = "https://i.ganjoor.net/a/";

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
     * HafezFilebot.json به صورت object است
     * و کلید هر رکورد، شناسه فایل صوتی است.
     *
     * مثال:
     *
     * "2301": {
     *     "Poem": "...",
     *     "Title": "غزل شمارهٔ ۱۷۲",
     *     "Source": "/sh172/",
     *     "Audio": "..."
     * }
     *
     * بنابراین کلید را حفظ می‌کنیم.
     */

    if (Array.isArray(ghazalData)) {
        ghazals = ghazalData.map((record, index) => ({
            ...record,
            record_id:
                record.record_id ??
                record.RecordId ??
                record.id ??
                record.ID ??
                String(index + 1)
        }));
    } else {
        ghazals = Object.entries(ghazalData || {}).map(
            ([recordId, record]) => ({
                ...record,
                record_id: String(recordId)
            })
        );
    }


    if (Array.isArray(tabirData)) {
        interpretations = tabirData;
    } else {
        interpretations = Object.values(tabirData || {});
    }


    if (!ghazals.length) {
        throw new Error("بانک غزل‌ها خالی است");
    }
}


/* =========================
   شماره غزل
========================= */

function getGhazalNumber(record) {

    const source = String(
        record?.Source || ""
    ).trim();

    const sourceMatch =
        source.match(/\/sh(\d+)/i);

    if (sourceMatch) {
        return Number(sourceMatch[1]);
    }


    const title = String(
        record?.Title || ""
    ).trim();

    const titleMatch =
        title.match(/(\d+)/);

    if (titleMatch) {
        return Number(titleMatch[1]);
    }


    return null;
}


/* =========================
   پیدا کردن تعبیر
========================= */

function getInterpretationText(record) {

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


function findInterpretation(ghazalNumber) {

    if (!ghazalNumber) {
        return "";
    }


    /*
     * ابتدا فیلدهای شماره را بررسی می‌کنیم.
     */

    for (const record of interpretations) {

        const possibleNumbers = [
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


        for (const value of possibleNumbers) {

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
     * در صورت نبود شمارهٔ صریح،
     * ترتیب رکوردها برابر شماره غزل است.
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
   ساخت لینک صوت
========================= */

function getAudioUrl(record) {

    /*
     * مهم:
     *
     * کلید رکورد HafezFilebot.json
     * همان شناسه‌ای است که در آدرس فایل استفاده می‌شود.
     *
     * مثال:
     *
     * record_id = 2301
     *
     * نتیجه:
     *
     * https://i.ganjoor.net/a/2301-ff.mp3
     */

    const recordId = String(
        record?.record_id || ""
    ).trim();


    if (!recordId) {
        return "";
    }


    /*
     * فقط شناسه عددی را قبول می‌کنیم
     * تا URL اشتباه ساخته نشود.
     */

    if (!/^\d+$/.test(recordId)) {
        return "";
    }


    return `${AUDIO_BASE_URL}${recordId}-ff.mp3`;
}


/* =========================
   انتخاب تصادفی غزل
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


    /* ---------- عنوان ---------- */

    titleElement.textContent =
        record?.Title || "فال حافظ";


    /* ---------- شعر ---------- */

    poemElement.textContent =
        record?.Poem || "";


    /* ---------- منبع ---------- */

    const source =
        String(
            record?.Source || ""
        ).trim();


    if (source) {
        sourceElement.textContent =
            `منبع: ${source}`;
    } else {
        sourceElement.textContent = "";
    }


    /* ---------- تعبیر ---------- */

    const ghazalNumber =
        getGhazalNumber(record);


    const interpretation =
        findInterpretation(
            ghazalNumber
        );


    if (interpretation) {

        interpretationElement.textContent =
            interpretation;

    } else {

        interpretationElement.textContent =
            "تعبیر این فال در بانک موجود نیست.";
    }


    /* ---------- صوت ---------- */

    audioPlayer.pause();

    audioPlayer.removeAttribute("src");

    audioPlayer.load();


    const audioUrl =
        getAudioUrl(record);


    console.log(
        "[AUDIO]",
        {
            record_id: record.record_id,
            title: record.Title,
            ghazal: ghazalNumber,
            audio: audioUrl
        }
    );


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


    /* ---------- نمایش صفحه ---------- */

    showScreen(
        "fortuneScreen"
    );
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
                `[DATA] Loaded ${ghazals.length} ghazals.`
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
    }
);
