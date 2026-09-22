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
let interpretations = [];


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


interpretations =
    Array.isArray(tabirData)
        ? tabirData
        : [];


if (hazals.length === 0) {

    throw new Error(
        "هیچ غزلی در HafezFilebot.json پیدا نشد."
    );
}


console.log(
    `[DATA] Loaded ${hazals.length} ghazals.`
);


console.log(
    `[TABIR] Loaded ${interpretations.length} interpretations.`
);



}


/* ==================================
Normalize Hafez Data
دقیقاً متناسب با ساختار bot.py
================================== */


function normalizeHafezData(data) {


const result = [];


/*
 * ساختار HafezFilebot.json:
 *
 * [
 *   {
 *      "fxr49o": {
 *          "Audio": "...",
 *          "Author": "حافظ",
 *          "Book": "غزلیات حافظ",
 *          "Poem": "...",
 *          "Source": "...",
 *          "Title": "..."
 *      }
 *   }
 * ]
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
Random
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
Ghazal Number
همان منطق bot.py
================================== */


function getGhazalNumber(record) {


if (!record) {

    return null;
}


const source =
    String(
        record.source ?? ""
    );


/*
 * اول Source
 * مثال:
 * https://ganjoor.net/hafez/ghazal/sh63/
 */

const sourceMatch =
    source.match(
        /\/sh(\d+)/i
    );


if (sourceMatch) {

    return sourceMatch[1];
}


/*
 * سپس Title
 */

const title =
    String(
        record.title ?? ""
    );


const titleMatch =
    title.match(
        /\d+/
    );


if (titleMatch) {

    return titleMatch[0];
}


/*
 * سپس record_id
 */

const recordId =
    String(
        record.record_id ?? ""
    );


const idMatch =
    recordId.match(
        /\d+/
    );


if (idMatch) {

    return idMatch[0];
}


return recordId || null;



}


/* ==================================
Interpretation Validation
همان منطق bot.py
================================== */


function isValidInterpretation(
interpretation
) {


if (
    interpretation === null ||
    interpretation === undefined
) {

    return false;
}


const text =
    String(
        interpretation
    ).trim();


if (!text) {

    return false;
}


const normalized =
    text.replace(
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
Load Interpretation
همان منطق load_interpretations
در bot.py
================================== */


function getInterpretation(
record
) {


const number =
    getGhazalNumber(
        record
    );


if (!number) {

    return null;
}


/*
 * در bot.py:
 *
 * اگر رکورد شماره نداشته باشد،
 * شماره همان index رکورد است.
 *
 * بنابراین رکورد شماره 1
 * با اولین رکورد Hafez_Tabir
 * مرتبط است.
 */


const index =
    Number(number) - 1;


if (
    Number.isInteger(index) &&
    index >= 0 &&
    index < interpretations.length
) {

    const item =
        interpretations[index];


    if (
        item &&
        typeof item === "object"
    ) {

        const interpretation =
            String(
                item.interpretation ??
                ""
            ).trim();


        if (
            isValidInterpretation(
                interpretation
            )
        ) {

            return interpretation;
        }
    }
}


/*
 * اگر خود فایل تعبیر
 * شماره غزل داشته باشد،
 * آن شماره نیز بررسی می‌شود.
 */

for (
    const item
    of interpretations
) {

    if (
        !item ||
        typeof item !== "object"
    ) {

        continue;
    }


    const possibleFields = [

        "ghazal_number",

        "GhazalNumber",

        "ghazal",

        "number",

        "Number",

        "id",

        "ID"

    ];


    let itemNumber = null;


    for (
        const field
        of possibleFields
    ) {

        const value =
            item[field];


        if (
            value !== undefined &&
            value !== null
        ) {

            const match =
                String(value).match(
                    /\d+/
                );


            if (match) {

                itemNumber =
                    match[0];

                break;
            }
        }
    }


    if (
        itemNumber ===
        String(number)
    ) {

        const interpretation =
            String(
                item.interpretation ??
                ""
            ).trim();


        if (
            isValidInterpretation(
                interpretation
            )
        ) {

            return interpretation;
        }
    }
}


return null;



}


/* ==================================
Clean Poem
همان منطق bot.py
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
ابتدا Audio خود HafezFilebot
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
Check Audio
================================== */


async function checkAudioUrl(
audioUrl
) {


if (!audioUrl) {

    return false;
}


try {

    const response =
        await fetch(
            audioUrl,
            {
                method: "HEAD",
                mode: "cors"
            }
        );


    return response.ok;

} catch (error) {

    /*
     * بعضی سرورهای صوتی HEAD/CORS
     * را محدود می‌کنند.
     *
     * خود URL را همچنان قابل استفاده
     * در audio player در نظر می‌گیریم.
     */

    return true;
}



}


/* ==================================
Extract Audio URLs
همان منطق bot.py
================================== */


function extractAudioUrls(
html,
baseUrl
) {


const candidates = [];


const absoluteRegex =
    /https?:\/\/[^"'>\s]+?\.(?:ogg|mp3)(?:\?[^"'>\s]*)?/gi;


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
همان منطق bot.py
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
     * اول OGG
     * سپس سایر فرمت‌ها
     */

    const oggCandidates =
        candidates.filter(
            url =>
                url
                    .toLowerCase()
                    .includes(
                        ".ogg"
                    )
        );


    const ordered =
        [
            ...oggCandidates,

            ...candidates.filter(
                url =>
                    !oggCandidates.includes(
                        url
                    )
            )
        ];


    for (
        const candidate
        of ordered
    ) {

        const valid =
            await checkAudioUrl(
                candidate
            );


        if (valid) {

            return candidate;
        }
    }

} catch (error) {

    console.warn(
        "[AUDIO] Resolve source failed:",
        error
    );
}


return null;



}


/* ==================================
Resolve Final Audio
همان ترتیب bot.py
================================== */


async function resolveFinalAudioUrl(
record
) {


/*
 * اول Audio مستقیم رکورد
 */

const directAudio =
    getDirectAudio(
        record
    );


if (directAudio) {

    return directAudio;
}


/*
 * اگر Audio نداشت،
 * از Source برای پیدا کردن صوت
 * استفاده می‌کنیم.
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
Reset Audio Player
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


async function showAudio(
record
) {


resetAudioPlayer();


/*
 * صوت مستقیم HafezFilebot
 * بدون نیاز به دانلود یا سرور واسطه
 */

const audioUrl =
    await resolveFinalAudioUrl(
        record
    );


if (!audioUrl) {

    console.warn(
        "[AUDIO] No audio available."
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
    !hazals.length
) {

    alert(
        "غزلی برای فال حافظ پیدا نشد."
    );

    return;
}


let fortune;


/*
 * فال قبلی بلافاصله تکرار نشود.
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


const source =
    fortune.source;


const tabir =
    getInterpretation(
        fortune
    );


console.log(
    `[FORTUNE] Selected ghazal #${number}`
);


console.log(
    `[TABIR] ${
        tabir
            ? "Found"
            : "Not found"
    } for ghazal #${number}`
);


/*
 * نمایش اطلاعات
 */

poemTitle.textContent =
    title;


poemText.textContent =
    poem ||
    "متن غزل موجود نیست.";


if (source) {

    poemSource.textContent =
        `منبع: ${source}`;

} else {

    poemSource.textContent =
        "";
}


interpretation.textContent =
    tabir ||
    "تعبیری برای این غزل ثبت نشده است.";


/*
 * ابتدا صفحه نمایش داده شود
 */

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


/*
 * سپس صوت آماده شود.
 */

await showAudio(
    fortune
);



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



