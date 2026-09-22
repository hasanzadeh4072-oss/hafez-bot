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
================================== */

function normalizeHafezData(data) {

    const result = [];


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


    const sourceMatch =
        source.match(
            /\/sh(\d+)/i
        );


    if (sourceMatch) {

        return sourceMatch[1];
    }


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
فقط از Audio موجود در HafezFilebot
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

function showAudio(record) {

    resetAudioPlayer();


    const audioUrl =
        getDirectAudio(
            record
        );


    if (!audioUrl) {

        console.warn(
            "[AUDIO] No direct audio available."
        );

        return;
    }


    /*
     * URL صوت مستقیماً از
     * HafezFilebot.json استفاده می‌شود.
     *
     * هیچ HEAD یا fetch روی فایل صوتی
     * انجام نمی‌شود.
     */

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


    showAudio(
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
