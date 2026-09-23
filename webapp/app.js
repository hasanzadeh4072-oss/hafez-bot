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
Reset Audio
================================== */

function resetAudioPlayer() {

    audioPlayer.pause();

    audioPlayer.removeAttribute(
        "src"
    );

    audioPlayer.removeAttribute(
        "type"
    );

    audioPlayer.style.display =
        "none";

    audioPlayer.load();
}


/* ==================================
Test Audio URL
================================== */

function testAudioUrl(url) {

    return new Promise(
        resolve => {

            if (!url) {
                resolve(false);
                return;
            }

            const testAudio =
                document.createElement(
                    "audio"
                );

            let finished = false;

            const finish =
                result => {

                    if (finished) {
                        return;
                    }

                    finished = true;

                    testAudio.removeAttribute(
                        "src"
                    );

                    testAudio.load();

                    resolve(result);
                };


            testAudio.preload =
                "metadata";


            testAudio.onloadedmetadata =
                () => {

                    console.log(
                        "[AUDIO TEST] OK:",
                        url
                    );

                    finish(true);
                };


            testAudio.onerror =
                () => {

                    console.warn(
                        "[AUDIO TEST] FAILED:",
                        url
                    );

                    finish(false);
                };


            testAudio.src =
                url;


            testAudio.load();


            setTimeout(
                () => finish(false),
                8000
            );
        }
    );
}


/* ==================================
Extract Audio URLs
================================== */

function extractAudioUrls(
    html,
    baseUrl
) {

    const candidates = [];

    const absoluteUrls =
        html.match(
            /https?:\/\/[^"'<>\\s]+?\.(?:ogg|mp3)(?:\?[^"'<>\\s]*)?/gi
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
            relativeRegex.exec(html)) !==
        null
    ) {

        try {

            candidates.push(
                new URL(
                    match[1],
                    baseUrl
                ).href
            );

        } catch (error) {

            console.warn(
                "[AUDIO] Invalid URL:",
                match[1]
            );
        }
    }


    const unique =
        [...new Set(candidates)];


    const ogg =
        unique.filter(
            url =>
                /\.ogg(?:\?|$)/i.test(
                    url
                )
        );


    const ganjoor =
        unique.filter(
            url =>
                url
                    .toLowerCase()
                    .includes(
                        "i.ganjoor.net"
                    )
        );


    const rest =
        unique.filter(
            url =>
                !ogg.includes(url) &&
                !ganjoor.includes(url)
        );


    return [
        ...ganjoor,
        ...ogg,
        ...rest
    ];
}


/* ==================================
Find Audio From Source
================================== */

async function findAudioFromSource(
    sourceUrl
) {

    if (!sourceUrl) {
        return "";
    }


    try {

        console.log(
            "[AUDIO] Trying Source:",
            sourceUrl
        );


        const response =
            await fetch(
                sourceUrl
            );


        if (!response.ok) {

            console.warn(
                "[AUDIO] Source HTTP:",
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


        console.log(
            "[AUDIO] Candidates:",
            candidates
        );


        for (
            const url
            of candidates
        ) {

            const valid =
                await testAudioUrl(
                    url
                );


            if (valid) {

                return url;
            }
        }

    } catch (error) {

        console.error(
            "[AUDIO] Source error:",
            error
        );
    }


    return "";
}


/* ==================================
Resolve Audio
================================== */

async function resolveAudio(
    record
) {

    const directAudio =
        getDirectAudio(
            record
        );


    /*
     * اول Audio داخل JSON را تست می‌کنیم.
     */

    if (directAudio) {

        console.log(
            "[AUDIO] Testing JSON Audio:",
            directAudio
        );


        const directWorks =
            await testAudioUrl(
                directAudio
            );


        if (directWorks) {

            return directAudio;
        }


        console.warn(
            "[AUDIO] JSON Audio failed."
        );
    }


    /*
     * اگر لینک مستقیم کار نکرد،
     * Source را بررسی می‌کنیم.
     */

    const source =
        String(
            record.source ?? ""
        ).trim();


    if (source) {

        const resolved =
            await findAudioFromSource(
                source
            );


        if (resolved) {

            return resolved;
        }
    }


    return "";
}


/* ==================================
Show Audio
================================== */

async function showAudio(record) {

    resetAudioPlayer();


    const audioUrl =
        await resolveAudio(
            record
        );


    if (!audioUrl) {

        console.warn(
            "[AUDIO] No playable audio found."
        );

        return;
    }


    console.log(
        "[AUDIO] PLAYABLE URL:",
        audioUrl
    );


    audioPlayer.src =
        audioUrl;


    audioPlayer.style.display =
        "block";


    audioPlayer.load();


    audioPlayer.onerror =
        event => {

            console.error(
                "[AUDIO] Playback error:",
                event
            );

            console.error(
                "[AUDIO] URL:",
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


    poemSource.textContent =
        source
            ? `منبع: ${source}`
            : "";


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
     * آماده‌سازی صوت
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



