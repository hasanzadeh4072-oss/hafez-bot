const DATA_URL = "../HafezFilebot.json";
const TABIR_URL = "../Hafez_Tabir.json";

let ghazals = [];
let interpretations = [];

const homeScreen = document.getElementById("homeScreen");
const fortuneScreen = document.getElementById("fortuneScreen");

const fortuneButton = document.getElementById("fortuneButton");
const newFortuneButton = document.getElementById("newFortuneButton");

const poemTitle = document.getElementById("poemTitle");
const poemText = document.getElementById("poemText");
const poemSource = document.getElementById("poemSource");
const interpretation = document.getElementById("interpretation");
const audioPlayer = document.getElementById("audioPlayer");


// -----------------------------
// بارگذاری اطلاعات
// -----------------------------

async function loadData() {
    try {
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

        ghazals = [];

        /*
         * ساختار HafezFilebot.json:
         *
         * [
         *   {
         *     "2130": {
         *       "Audio": "...",
         *       "Poem": "...",
         *       "Source": "...",
         *       "Title": "..."
         *     }
         *   }
         * ]
         */

        if (Array.isArray(ghazalData)) {
            for (const group of ghazalData) {
                if (!group || typeof group !== "object") {
                    continue;
                }

                for (const [recordId, record] of Object.entries(group)) {
                    if (!record || typeof record !== "object") {
                        continue;
                    }

                    ghazals.push({
                        record_id: String(recordId),
                        ...record
                    });
                }
            }
        }

        /*
         * تعبیرها را بدون تغییر ساختار اصلی نگه می‌داریم.
         */
        interpretations = tabirData;

        console.log("تعداد غزل‌ها:", ghazals.length);

        if (!ghazals.length) {
            throw new Error("هیچ غزلی از HafezFilebot.json خوانده نشد.");
        }

    } catch (error) {
        console.error("خطا در بارگذاری اطلاعات:", error);

        alert("دریافت اطلاعات فال با مشکل مواجه شد.");
        throw error;
    }
}


// -----------------------------
// پیدا کردن تعبیر
// -----------------------------

function getInterpretation(record) {
    const title = String(record?.Title || "").trim();
    const recordId = String(record?.record_id || "").trim();

    if (!interpretations) {
        return "";
    }

    /*
     * حالت آرایه‌ای
     */
    if (Array.isArray(interpretations)) {
        for (const item of interpretations) {
            if (!item || typeof item !== "object") {
                continue;
            }

            const itemId = String(
                item.id ??
                item.ID ??
                item.شناسه ??
                item.record_id ??
                ""
            ).trim();

            const itemTitle = String(
                item.Title ??
                item.title ??
                item.عنوان ??
                ""
            ).trim();

            if (
                (recordId && itemId === recordId) ||
                (title && itemTitle === title)
            ) {
                return String(
                    item.Tabir ??
                    item.تعبیر ??
                    item.Interpretation ??
                    item.interpretation ??
                    item.Text ??
                    item.text ??
                    ""
                ).trim();
            }
        }
    }

    /*
     * حالت آبجکت با کلید شناسه
     */
    if (
        typeof interpretations === "object" &&
        !Array.isArray(interpretations)
    ) {
        if (recordId && interpretations[recordId]) {
            const item = interpretations[recordId];

            if (typeof item === "string") {
                return item.trim();
            }

            if (item && typeof item === "object") {
                return String(
                    item.Tabir ??
                    item.تعبیر ??
                    item.Interpretation ??
                    item.interpretation ??
                    item.Text ??
                    item.text ??
                    ""
                ).trim();
            }
        }
    }

    return "";
}


// -----------------------------
// ساخت لینک صوت
// -----------------------------

function getAudioUrl(record) {
    const audio = String(record?.Audio || "").trim();

    if (!audio) {
        return "";
    }

    /*
     * مثال:
     *
     * https://i.ganjoor.net/a/2237.ogg
     *
     * تبدیل می‌شود به:
     *
     * https://i.ganjoor.net/a/2237-ff.mp3
     */

    const match = audio.match(
        /\/a\/(\d+)(?:\.[^/?#]+)?(?:[?#].*)?$/i
    );

    if (!match) {
        console.warn("فرمت Audio قابل تشخیص نیست:", audio);
        return "";
    }

    const audioId = match[1];

    return `https://i.ganjoor.net/a/${audioId}-ff.mp3`;
}


// -----------------------------
// نمایش فال
// -----------------------------

function showFortune() {
    if (!ghazals.length) {
        return;
    }

    const record =
        ghazals[Math.floor(Math.random() * ghazals.length)];

    const title = String(record?.Title || "فال حافظ").trim();
    const poem = String(record?.Poem || "").trim();
    const source = String(record?.Source || "").trim();

    const tabir = getInterpretation(record);
    const audioUrl = getAudioUrl(record);

    poemTitle.textContent = title;
    poemText.textContent = poem;

    if (source) {
        poemSource.textContent = source;
    } else {
        poemSource.textContent = "";
    }

    interpretation.textContent =
        tabir || "تعبیر این فال در دسترس نیست.";

    /*
     * کنترل صدا همیشه نمایش داده شود.
     */
    audioPlayer.style.display = "block";

    /*
     * ابتدا صوت قبلی کاملاً پاک شود.
     */
    audioPlayer.pause();
    audioPlayer.removeAttribute("src");
    audioPlayer.load();

    if (audioUrl) {
        console.log("Audio:", record.Audio);
        console.log("Audio MP3:", audioUrl);

        audioPlayer.src = audioUrl;
        audioPlayer.load();
    } else {
        console.warn(
            "برای این غزل Audio معتبر پیدا نشد:",
            record
        );
    }

    homeScreen.classList.remove("active");
    fortuneScreen.classList.add("active");

    window.scrollTo({
        top: 0,
        behavior: "smooth"
    });
}


// -----------------------------
// دکمه‌ها
// -----------------------------

fortuneButton.addEventListener("click", async () => {
    fortuneButton.disabled = true;

    try {
        if (!ghazals.length) {
            await loadData();
        }

        showFortune();

    } catch (error) {
        console.error(error);
    } finally {
        fortuneButton.disabled = false;
    }
});


newFortuneButton.addEventListener("click", () => {
    showFortune();
});


// -----------------------------
// خطای پخش صوت
// -----------------------------

audioPlayer.addEventListener("error", () => {
    console.warn(
        "پخش صوت با خطا مواجه شد:",
        audioPlayer.src
    );
});


// -----------------------------
// شروع
// -----------------------------

loadData().catch(error => {
    console.error("خطا در شروع برنامه:", error);
});
