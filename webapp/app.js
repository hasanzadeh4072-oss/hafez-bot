const homeScreen = document.getElementById("homeScreen");
const fortuneScreen = document.getElementById("fortuneScreen");

const fortuneButton = document.getElementById("fortuneButton");
const newFortuneButton = document.getElementById("newFortuneButton");

const poemTitle = document.getElementById("poemTitle");
const poemText = document.getElementById("poemText");
const poemSource = document.getElementById("poemSource");
const interpretation = document.getElementById("interpretation");

const audioPlayer = document.getElementById("audioPlayer");


/* ==================================
   Data
================================== */

let hazals = [];
let interpretationMap = new Map();

let lastFortune = null;


/* ==================================
   Load Data
================================== */

async function loadData() {

    const [
        hafezResponse,
        tabirResponse
    ] = await Promise.all([

        fetch("../HafezFilebot.json"),

        fetch("../Hafez_Tabir.json")
    ]);


    if (!hafezResponse.ok) {
        throw new Error(
            "خطا در دریافت HafezFilebot.json"
        );
    }


    if (!tabirResponse.ok) {
        throw new Error(
            "خطا در دریافت Hafez_Tabir.json"
        );
    }


    const hafezData =
        await hafezResponse.json();

    const tabirData =
        await tabirResponse.json();


    hazals =
        normalizeHafezData(
            hafezData
        );


    interpretationMap =
        buildInterpretationMap(
            tabirData
        );


    if (hazals.length === 0) {
        throw new Error(
            "هیچ غزلی در HafezFilebot.json پیدا نشد."
        );
    }


    console.log(
        `[DATA] Loaded ${hazals.length} ghazals.`
    );


    console.log(
        `[TABIR] Loaded ${interpretationMap.size} interpretations.`
    );
}


/* ==================================
   Normalize Hafez Data
================================== */

function normalizeHafezData(data) {

    const result = [];


    /*
     * ساختار واقعی HafezFilebot.json:
     *
     * [
     *   {
     *      "2411": {
     *          "Audio": null,
     *          "Author": "حافظ",
     *          "Book": "غزلیات حافظ",
     *          "Poem": "...",
     *          "Source": "https://ganjoor.net/hafez/ghazal/sh282/",
     *          "Title": "غزل شمارهٔ ۲۸۲"
     *      }
     *   }
     * ]
     *
     * توجه:
     * کلید 2411 شماره غزل نیست.
     * شماره واقعی غزل از Source/Title استخراج می‌شود.
     */


    if (!Array.isArray(data)) {
        return result;
    }


    for (const item of data) {

        if (
            !item ||
            typeof item !== "object"
        ) {
            continue;
        }


        for (
            const [recordId, record]
            of Object.entries(item)
        ) {

            if (
                !record ||
                typeof record !== "object"
            ) {
                continue;
            }


            const poem =
                String(
                    record.Poem ?? ""
                ).trim();


            if (!poem) {
                continue;
            }


            result.push({

                record_id:
                    String(recordId),

                author:
                    String(
                        record.Author ??
                        "حافظ"
                    ).trim() || "حافظ",

                book:
                    String(
                        record.Book ??
                        "غزلیات حافظ"
                    ).trim() || "غزلیات حافظ",

                poem,

                source:
                    String(
                        record.Source ??
                        ""
                    ).trim(),

                title:
                    String(
                        record.Title ??
                        ""
                    ).trim(),

                audio:
                    String(
                        record.Audio ??
                        ""
                    ).trim()

            });
        }
    }


    return result;
}


/* ==================================
   Normalize Text
================================== */

function normalizeText(text) {

    if (
        text === null ||
        text === undefined
    ) {
        return "";
    }


    return String(text)

        .replace(
            /\u200c/g,
            ""
        )

        .replace(
            /\r\n/g,
            "\n"
        )

        .replace(
            /\r/g,
            "\n"
        )

        .replace(
            /[\u064A]/g,
            "ی"
        )

        .replace(
            /[\u0643]/g,
            "ک"
        )

        .replace(
            /[\u0660-\u0669]/g,
            char =>
                String(
                    "۰۱۲۳۴۵۶۷۸۹".indexOf(char)
                )
        )

        .replace(
            /[\u06F0-\u06F9]/g,
            char =>
                String(
                    "۰۱۲۳۴۵۶۷۸۹".indexOf(char)
                )
        )

        .replace(
            /\s+/g,
            ""
        )

        .trim();
}


/* ==================================
   Valid Interpretation
================================== */

function isValidInterpretation(text) {

    if (
        text === null ||
        text === undefined
    ) {
        return false;
    }


    const value =
        String(text).trim();


    if (!value) {
        return false;
    }


    const normalized =
        value.replace(
            /\s/g,
            ""
        );


    const invalidPhrases = [

        "برایاینغزل هنوزتعبیریثبتنشده",

        "برایاینغزل هنوزتعبیری",

        "تعبیریثبتنشده",

        "تعبیرثبتنشده",

        "هنوزتعبیریثبتنشده"

    ];


    for (
        const phrase
        of invalidPhrases
    ) {

        if (
            normalized.includes(
                phrase
            )
        ) {
            return false;
        }
    }


    return true;
}


/* ==================================
   Build Interpretation Map
================================== */

function buildInterpretationMap(data) {

    const map = new Map();


    if (!Array.isArray(data)) {
        return map;
    }


    /*
     * Hafez_Tabir.json دارای poem + interpretation است.
     *
     * مهم:
     * ارتباط اصلی را با خود متن غزل انجام می‌دهیم.
     * شماره فایل رکورد HafezFilebot مبنا نیست.
     */


    data.forEach(
        (item, index) => {

            if (
                !item ||
                typeof item !== "object"
            ) {
                return;
            }


            const poem =
                String(
                    item.poem ??
                    item.Poem ??
                    ""
                ).trim();


            const text =
                String(
                    item.interpretation ??
                    item.Interpretation ??
                    ""
                ).trim();


            if (
                !poem ||
                !isValidInterpretation(text)
            ) {
                return;
            }


            const normalizedPoem =
                normalizeText(
                    poem
                );


            if (!normalizedPoem) {
                return;
            }


            map.set(
                normalizedPoem,
                {
                    interpretation: text,
                    index: index
                }
            );
        }
    );


    return map;
}


/* ==================================
   Get Ghazal Number
================================== */

function getGhazalNumber(record) {

    if (!record) {
        return null;
    }


    /*
     * اول Source
     *
     * مثال:
     * https://ganjoor.net/hafez/ghazal/sh282/
     */

    const source =
        String(
            record.source ?? ""
        );


    let match =
        source.match(
            /\/sh(\d+)/i
        );


    if (match) {
        return match[1];
    }


    /*
     * سپس Title
     *
     * مثال:
     * غزل شمارهٔ ۲۸۲
     */

    const title =
        String(
            record.title ?? ""
        );


    match =
        title.match(
            /[\d۰-۹]+/
        );


    if (match) {

        return convertPersianDigits(
            match[0]
        );
    }


    /*
     * در آخر فقط برای fallback
     * record_id بررسی می‌شود.
     *
     * اما record_id شماره غزل محسوب نمی‌شود.
     */

    return null;
}


/* ==================================
   Persian Digits
================================== */

function convertPersianDigits(value) {

    if (!value) {
        return "";
    }


    return String(value)

        .replace(
            /[۰-۹]/g,
            char =>
                String(
                    "۰۱۲۳۴۵۶۷۸۹".indexOf(char)
                )
        )

        .replace(
            /[٠-٩]/g,
            char =>
                String(
                    "٠١٢٣٤٥٦٧٨٩".indexOf(char)
                )
        );
}


/* ==================================
   Find Interpretation
   بر اساس خود متن غزل
================================== */

function getInterpretation(record) {

    if (!record) {
        return null;
    }


    const poem =
        normalizeText(
            record.poem
        );


    if (!poem) {
        return null;
    }


    /*
     * تطبیق مستقیم متن غزل
     */

    const direct =
        interpretationMap.get(
            poem
        );


    if (direct) {
        return direct.interpretation;
    }


    /*
     * اگر به دلیل تفاوت جزئی در
     * فاصله/نیم‌فاصله تطبیق مستقیم نشد،
     * تطبیق دقیق‌تری با خطوط انجام می‌دهیم.
     */

    for (
        const [
            tabirPoem,
            data
        ]
        of interpretationMap.entries()
    ) {

        if (
            tabirPoem === poem
        ) {
            return data.interpretation;
        }
    }


    return null;
}


/* ==================================
   Clean Poem
================================== */

function cleanPoem(poem) {

    if (!poem) {
        return "";
    }


    let text =
        String(poem);


    text =
        text.replace(
            /\r\n/g,
            "\n"
        );


    text =
        text.replace(
            /\r/g,
            "\n"
        );


    text =
        text.replace(
            /\n{3,}/g,
            "\n\n"
        );


    return text.trim();
}


/* ==================================
   Audio
================================== */

function getDirectAudio(record) {

    if (!record) {
        return "";
    }


    return String(
        record.audio ?? ""
    ).trim();
}


/* ==================================
   Extract Audio URLs
================================== */

function extractAudioUrls(
    html,
    baseUrl
) {

    const candidates = [];


    /*
     * لینک‌های مستقیم
     */

    const absoluteRegex =
        /https?:\/\/[^"'<>\\\s]+?\.(?:ogg|mp3)(?:\?[^"'<>\\\s]*)?/gi;


    const absoluteUrls =
        html.match(
            absoluteRegex
        ) || [];


    for (
        let url
        of absoluteUrls
    ) {

        url =
            url.replace(
                /&amp;/g,
                "&"
            );


        candidates.push(
            url
        );
    }


    /*
     * لینک‌های نسبی
     */

    const relativeRegex =
        /["']([^"']+\.(?:ogg|mp3)(?:\?[^"]*)?)["']/gi;


    let match;


    while (
        (match =
            relativeRegex.exec(
                html
            )) !== null
    ) {

        try {

            candidates.push(
                new URL(
                    match[1],
                    baseUrl
                ).href
            );

        } catch (error) {
            // نادیده گرفته می‌شود.
        }
    }


    /*
     * حذف تکراری‌ها
     */

    const unique = [];

    const seen =
        new Set();


    for (
        const url
        of candidates
    ) {

        if (!seen.has(url)) {

            seen.add(url);

            unique.push(url);
        }
    }


    /*
     * اول i.ganjoor.net
     */

    const ganjoor =
        unique.filter(
            url =>
                url
                    .toLowerCase()
                    .includes(
                        "i.ganjoor.net"
                    )
        );


    if (
        ganjoor.length > 0
    ) {

        return ganjoor;
    }


    return unique;
}


/* ==================================
   Resolve Audio From Source
================================== */

async function resolveAudioFromSource(
    sourceUrl
) {

    if (!sourceUrl) {
        return null;
    }


    try {

        const response =
            await fetch(
                sourceUrl
            );


        if (!response.ok) {
            return null;
        }


        const html =
            await response.text();


        const candidates =
            extractAudioUrls(
                html,
                sourceUrl
            );


        if (
            candidates.length === 0
        ) {
            return null;
        }


        /*
         * OGG اولویت دارد.
         */

        const oggCandidates =
            candidates.filter(
                url =>
                    /\.ogg(?:\?|$)/i.test(
                        url
                    )
            );


        const ordered = [

            ...oggCandidates,

            ...candidates.filter(
                url =>
                    !oggCandidates.includes(
                        url
                    )
            )

        ];


        return ordered[0] || null;

    } catch (error) {

        console.warn(
            "[AUDIO] Source audio lookup failed:",
            error
        );


        return null;
    }
}


/* ==================================
   Resolve Final Audio
================================== */

async function resolveFinalAudioUrl(
    record
) {

    /*
     * مرحله اول:
     * Audio مستقیم HafezFilebot
     */

    const directAudio =
        getDirectAudio(
            record
        );


    if (directAudio) {

        return directAudio;
    }


    /*
     * مرحله دوم:
     * اگر Audio خالی بود،
     * از Source همان غزل استفاده می‌کنیم.
     */

    const source =
        String(
            record.source ?? ""
        ).trim();


    if (source) {

        return await resolveAudioFromSource(
            source
        );
    }


    return null;
}


/* ==================================
   Reset Audio
================================== */

function resetAudioPlayer() {

    audioPlayer.pause();

    audioPlayer.removeAttribute(
        "src"
    );

    audioPlayer.load();

    audioPlayer.style.display =
        "none";
}


/* ==================================
   Show Audio
================================== */

async function showAudio(record) {

    resetAudioPlayer();


    const audioUrl =
        await resolveFinalAudioUrl(
            record
        );


    if (!audioUrl) {

        console.warn(
            "[AUDIO] No audio found."
        );

        return;
    }


    audioPlayer.src =
        audioUrl;


    audioPlayer.style.display =
        "block";


    audioPlayer.load();


    console.log(
        "[AUDIO] Ready:",
        audioUrl
    );
}


/* ==================================
   Show Fortune
================================== */

async function showFortune() {

    if (
        hazals.length === 0
    ) {

        alert(
            "غزلی برای فال حافظ پیدا نشد."
        );

        return;
    }


    let fortune;


    /*
     * غزل قبلی بلافاصله تکرار نشود.
     */

    if (
        hazals.length > 1
    ) {

        do {

            fortune =
                randomItem(
                    hazals
                );

        } while (
            fortune === lastFortune
        );

    } else {

        fortune =
            hazals[0];
    }


    lastFortune =
        fortune;


    const number =
        getGhazalNumber(
            fortune
        );


    const title =
        fortune.title ||
        (
            number
                ? `غزل شمارهٔ ${number}`
                : "غزل حافظ"
        );


    const poem =
        cleanPoem(
            fortune.poem
        );


    const tabir =
        getInterpretation(
            fortune
        );


    poemTitle.textContent =
        title;


    poemText.textContent =
        poem ||
        "متن غزل موجود نیست.";


    if (number) {

        poemSource.textContent =
            `غزل شمارهٔ ${number}`;

    } else {

        poemSource.textContent =
            "";
    }


    interpretation.textContent =
        tabir ||
        "تعبیری برای این غزل ثبت نشده است.";


    homeScreen.classList.remove(
        "active"
    );


    fortuneScreen.classList.add(
        "active"
    );


    window.scrollTo({

        top: 0,

        behavior: "smooth"

    });


    await showAudio(
        fortune
    );
}


/* ==================================
   Random Item
================================== */

function randomItem(array) {

    if (
        !Array.isArray(array) ||
        array.length === 0
    ) {
        return null;
    }


    return array[
        Math.floor(
            Math.random() * array.length
        )
    ];
}


/* ==================================
   Buttons
================================== */

fortuneButton.addEventListener(
    "click",
    showFortune
);


newFortuneButton.addEventListener(
    "click",
    showFortune
);


/* ==================================
   Startup
================================== */

fortuneButton.disabled =
    true;


loadData()

    .then(() => {

        fortuneButton.disabled =
            false;

    })

    .catch(error => {

        console.error(
            "[STARTUP]",
            error
        );


        fortuneButton.disabled =
            true;


        fortuneButton.textContent =
            "خطا در بارگذاری اطلاعات فال";
    });
