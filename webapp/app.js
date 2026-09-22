const DATA_FILE = "../HafezFilebot.json";
const TABIR_FILE = "../Hafez_Tabir.json";

const fortuneButton = document.getElementById("fortuneButton");
const newFortuneButton = document.getElementById("newFortuneButton");

const homeScreen = document.getElementById("homeScreen");
const fortuneScreen = document.getElementById("fortuneScreen");

const poemTitle = document.getElementById("poemTitle");
const poemText = document.getElementById("poemText");
const poemSource = document.getElementById("poemSource");
const interpretation = document.getElementById("interpretation");
const audioPlayer = document.getElementById("audioPlayer");

let hazals = [];
let tabirMap = {};
let usedGhzalNumbers = new Set();

let dataReady = false;


/* -----------------------------
   تبدیل اعداد فارسی و عربی
----------------------------- */

function normalizeDigits(value) {

    if (value === null || value === undefined) {
        return "";
    }

    return String(value)
        .replace(/[۰-۹]/g, digit =>
            String("۰۱۲۳۴۵۶۷۸۹".indexOf(digit))
        )
        .replace(/[٠-٩]/g, digit =>
            String("٠١٢٣٤٥٦٧٨٩".indexOf(digit))
        );
}


/* -----------------------------
   استخراج شماره غزل
----------------------------- */

function getGhazalNumber(record) {

    const source =
        record.Source ||
        record.source ||
        "";

    const sourceMatch =
        String(source).match(/\/sh(\d+)/i);

    if (sourceMatch) {
        return normalizeDigits(sourceMatch[1]);
    }


    const title =
        record.Title ||
        record.title ||
        "";

    const titleNormalized =
        normalizeDigits(title);

    const titleMatch =
        titleNormalized.match(/(\d+)/);

    if (titleMatch) {
        return titleMatch[1];
    }


    const recordId =
        record.record_id ||
        record.RecordId ||
        record.id ||
        record.ID ||
        "";

    const idNormalized =
        normalizeDigits(recordId);

    const idMatch =
        idNormalized.match(/(\d+)/);

    if (idMatch) {
        return idMatch[1];
    }


    return recordId
        ? String(recordId)
        : "؟";
}


/* -----------------------------
   استخراج غزل‌ها
----------------------------- */

function normalizeHafezData(data) {

    const result = [];


    if (Array.isArray(data)) {

        data.forEach(item => {

            if (!item || typeof item !== "object") {
                return;
            }


            if (
                item.Poem ||
                item.poem ||
                item.Title ||
                item.title
            ) {

                result.push({
                    ...item
                });

                return;
            }


            Object.entries(item).forEach(
                ([recordId, value]) => {

                    if (
                        !value ||
                        typeof value !== "object"
                    ) {
                        return;
                    }

                    result.push({
                        ...value,
                        record_id: recordId
                    });

                }
            );

        });

        return result;
    }


    if (data && typeof data === "object") {

        Object.entries(data).forEach(
            ([recordId, value]) => {

                if (
                    !value ||
                    typeof value !== "object"
                ) {
                    return;
                }

                result.push({
                    ...value,
                    record_id: recordId
                });

            }
        );

    }


    return result;
}


/* -----------------------------
   اعتبارسنجی تعبیر
----------------------------- */

function isValidInterpretation(value) {

    return (
        typeof value === "string" &&
        value.trim().length > 0
    );
}


/* -----------------------------
   بارگذاری تعبیرها
   مطابق منطق بات قبلی
----------------------------- */

function loadInterpretations(data) {

    const map = {};


    if (!Array.isArray(data)) {
        return map;
    }


    data.forEach((item, index) => {

        if (!item || typeof item !== "object") {
            return;
        }


        let ghazalNumber = null;


        const possibleNumberFields = [
            "ghazal_number",
            "GhazalNumber",
            "ghazal",
            "number",
            "Number",
            "id",
            "ID"
        ];


        for (const field of possibleNumberFields) {

            if (
                item[field] !== undefined &&
                item[field] !== null &&
                String(item[field]).trim() !== ""
            ) {

                ghazalNumber =
                    normalizeDigits(item[field]);

                break;
            }

        }


        if (!ghazalNumber) {
            ghazalNumber =
                String(index + 1);
        }


        const text =
            item.interpretation ||
            item.Interpretation ||
            "";


        if (!isValidInterpretation(text)) {
            return;
        }


        map[String(ghazalNumber)] =
            text.trim();

    });


    return map;
}


/* -----------------------------
   دریافت تعبیر
----------------------------- */

function getInterpretation(record) {

    const ghazalNumber =
        getGhazalNumber(record);


    return (
        tabirMap[String(ghazalNumber)] ||
        "تعبیری برای این غزل ثبت نشده است."
    );
}


/* -----------------------------
   دریافت URL صوت
----------------------------- */

function getAudioUrl(record) {

    const audio =
        record.Audio ||
        record.audio ||
        "";

    if (
        typeof audio === "string" &&
        audio.trim()
    ) {
        return audio.trim();
    }


    return "";
}


/* -----------------------------
   نمایش صفحه فال
----------------------------- */

function showFortuneScreen() {

    homeScreen.classList.remove("active");
    fortuneScreen.classList.add("active");

    window.scrollTo({
        top: 0,
        behavior: "smooth"
    });
}


/* -----------------------------
   انتخاب غزل تصادفی
----------------------------- */

function getRandomHazal() {

    if (!hazals.length) {
        return null;
    }


    if (usedGhzalNumbers.size >= hazals.length) {
        usedGhzalNumbers.clear();
    }


    const available =
        hazals.filter(record => {

            const number =
                getGhazalNumber(record);

            return !usedGhzalNumbers.has(number);

        });


    const list =
        available.length
            ? available
            : hazals;


    const record =
        list[
            Math.floor(
                Math.random() * list.length
            )
        ];


    usedGhzalNumbers.add(
        getGhazalNumber(record)
    );


    return record;
}


/* -----------------------------
   آماده‌سازی صوت
----------------------------- */

function setupAudio(audioUrl) {

    audioPlayer.pause();

    audioPlayer.removeAttribute("src");

    audioPlayer.load();


    if (!audioUrl) {

        audioPlayer.style.display = "none";

        return;

    }


    audioPlayer.src = audioUrl;

    audioPlayer.style.display = "block";

    audioPlayer.load();


    /*
       فقط وقتی کاربر روی کنترل صوت
       کلیک می‌کند، مرورگر اجازه پخش می‌دهد.
    */

    audioPlayer.onerror = () => {

        console.error(
            "خطا در بارگذاری صوت:",
            audioUrl
        );

    };

}


/* -----------------------------
   نمایش فال
----------------------------- */

function displayFortune(record) {

    if (!record) {

        poemTitle.textContent = "خطا";

        poemText.textContent =
            "غزلی برای نمایش پیدا نشد.";

        poemSource.textContent = "";

        interpretation.textContent = "";

        setupAudio("");

        return;
    }


    const title =
        record.Title ||
        record.title ||
        `غزل شمارهٔ ${getGhazalNumber(record)}`;


    const poem =
        record.Poem ||
        record.poem ||
        "متن غزل موجود نیست.";


    const ghazalNumber =
        getGhazalNumber(record);


    poemTitle.textContent = title;

    poemText.textContent = poem;


    poemSource.textContent =
        `غزل شمارهٔ ${ghazalNumber}`;


    interpretation.textContent =
        getInterpretation(record);


    const audioUrl =
        getAudioUrl(record);


    setupAudio(audioUrl);

}


/* -----------------------------
   گرفتن فال
----------------------------- */

function getFortune() {

    if (!dataReady) {
        return;
    }


    const record =
        getRandomHazal();


    displayFortune(record);

    showFortuneScreen();

}


/* -----------------------------
   بارگذاری فایل‌ها
----------------------------- */

async function loadData() {

    try {

        fortuneButton.disabled = true;
        newFortuneButton.disabled = true;


        const [
            hafezResponse,
            tabirResponse
        ] = await Promise.all([

            fetch(DATA_FILE, {
                cache: "no-store"
            }),

            fetch(TABIR_FILE, {
                cache: "no-store"
            })

        ]);


        if (!hafezResponse.ok) {

            throw new Error(
                `HafezFilebot.json: ${hafezResponse.status}`
            );

        }


        if (!tabirResponse.ok) {

            throw new Error(
                `Hafez_Tabir.json: ${tabirResponse.status}`
            );

        }


        const [
            hafezData,
            tabirData
        ] = await Promise.all([

            hafezResponse.json(),

            tabirResponse.json()

        ]);


        hazals =
            normalizeHafezData(hafezData);


        tabirMap =
            loadInterpretations(tabirData);


        if (!hazals.length) {

            throw new Error(
                "هیچ غزلی از HafezFilebot.json پیدا نشد."
            );

        }


        dataReady = true;

        fortuneButton.disabled = false;
        newFortuneButton.disabled = false;


    } catch (error) {

        console.error(
            "خطا در بارگذاری اطلاعات:",
            error
        );


        fortuneButton.disabled = true;
        newFortuneButton.disabled = true;


        poemTitle.textContent =
            "خطا در بارگذاری";

        poemText.textContent =
            "اطلاعات فال حافظ در دسترس نیست.";

        poemSource.textContent = "";

        interpretation.textContent =
            "لطفاً دوباره برنامه را باز کنید.";

        setupAudio("");

    }

}


/* -----------------------------
   رویدادها
----------------------------- */

fortuneButton.addEventListener(
    "click",
    getFortune
);


newFortuneButton.addEventListener(
    "click",
    getFortune
);


/* -----------------------------
   شروع برنامه
----------------------------- */

loadData();
