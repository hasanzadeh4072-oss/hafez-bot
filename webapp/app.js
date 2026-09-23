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

function getInterpretation(record) {

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
Audio URL
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
Audio URL Extraction
همان منطق بات
================================== */

function extractAudioUrls(
    html,
    baseUrl
) {

    const candidates = [];

    const absoluteUrls =
        html.match(
            /https?:\/\/[^"'>\s]+?\.(?:ogg|mp3)(?:\?[^"'>\s]*)?/gi
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


    const relativeUrls =
        html.match(
            /["']([^"']+\.(?:ogg|mp3)(?:\?[^"]*)?)["']/gi
        ) || [];


    for (
        const match
        of relativeUrls
    ) {

        const extracted =
            match.substring(
                1,
                match.length - 1
            );

        try {

            candidates.push(
                new URL(
                    extracted,
                    baseUrl
                ).href
            );

        } catch (error) {

            console.warn(
                "[AUDIO] Invalid relative URL:",
                extracted
            );
        }
    }


    const unique = [];

    const seen = new Set();

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


    if (ganjoor.length) {
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
        return "";
    }

    try {

        console.log(
            "[AUDIO] Resolving source:",
            sourceUrl
        );


        const response =
            await fetch(
                sourceUrl
            );


        if (!response.ok) {

            console.warn(
                "[AUDIO] Source page status:",
                response.status
            );

            return "";
        }


        const html =
            await response.text();


        const candidates =
            extractAudioUrls(
                html,
                sourceUrl
            );


        if (!candidates.length) {

            console.warn(
                "[AUDIO] No audio URL found."
            );

            return "";
        }


        const oggCandidates =
            candidates.filter(
                url =>
                    url
                        .toLowerCase()
                        .includes(".ogg")
            );


        const orderedCandidates = [

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
            of orderedCandidates
        ) {

            console.log(
                "[AUDIO] Candidate:",
                candidate
            );


            /*
             * برخلاف بات، اینجا فایل را دانلود نمی‌کنیم.
             *
             * فقط URL مناسب را برای
             * HTML5 Audio برمی‌گردانیم.
             */

            return candidate;
        }


    } catch (error) {

        console.error(
            "[AUDIO] Resolve error:",
            error
        );
    }


    return "";
}


/* ==================================
Resolve Final Audio
================================== */

async function resolveFinalAudioUrl(
    record
) {

    if (!record) {
        return "";
    }


    /*
     * اول Audio موجود در
     * HafezFilebot.json
     */

    const directAudio =
        getDirectAudio(
            record
        );


    if (directAudio) {

        console.log(
            "[AUDIO] Using Audio field:",
            directAudio
        );

        return directAudio;
    }


    /*
     * اگر Audio خالی بود،
     * از Source غزل استفاده می‌کنیم.
     *
     * این همان fallback اصلی
     * بات است.
     */

    const source =
        String(
            record.source ?? ""
        ).trim();


    if (source) {

        const resolved =
            await resolveAudioFromSource(
                source
            );

        if (resolved) {

            console.log(
                "[AUDIO] Resolved from Source:",
                resolved
            );

            return resolved;
        }
    }


    return "";
}


/* ==================================
Reset Audio Player
================================== */

function resetAudioPlayer() {

    try {
        audioPlayer.pause();
    } catch (error) {
        console.warn(
            "[AUDIO] Pause error:",
            error
        );
    }

    audioPlayer.removeAttribute(
        "src"
    );

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
            "[AUDIO] No audio URL available."
        );

        return;
    }


    console.log(
        "[AUDIO] Final URL:",
        audioUrl
    );


    audioPlayer.src =
        audioUrl;


    audioPlayer.style.display =
        "block";


    /*
     * اینجا عمداً play() نمی‌کنیم.
     * پخش خودکار ممکن است توسط WebView
     * مسدود شود.
     */

    audioPlayer.load();


    audioPlayer.onerror =
        function () {

            console.error(
                "[AUDIO] Browser could not load:",
                audioUrl
            );
        };
}


/* ==================================
Show Fortune
================================== */

async function showFortune() {

    if (!hazals.length) {

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


    /*
     * صوت را بعد از نمایش فال
     * به صورت مستقل آماده می‌کنیم.
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
