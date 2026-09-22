const homeScreen = document.getElementById("homeScreen");
const fortuneScreen = document.getElementById("fortuneScreen");

const fortuneButton = document.getElementById("fortuneButton");
const newFortuneButton = document.getElementById("newFortuneButton");

const poemTitle = document.getElementById("poemTitle");
const poemText = document.getElementById("poemText");
const poemSource = document.getElementById("poemSource");
const interpretation = document.getElementById("interpretation");

const audioPlayer = document.getElementById("audioPlayer");

let fortunes = [];
let interpretations = [];
let mainHafezData = [];

let lastFortune = null;


async function loadData() {
    const [falResponse, tabirResponse, hafezResponse] =
        await Promise.all([
            fetch("../fal.json"),
            fetch("../Hafez_Tabir.json"),
            fetch("../HafezFilebot.json")
        ]);

    if (!falResponse.ok) {
        throw new Error("خطا در دریافت fal.json");
    }

    if (!tabirResponse.ok) {
        throw new Error("خطا در دریافت Hafez_Tabir.json");
    }

    if (!hafezResponse.ok) {
        throw new Error("خطا در دریافت HafezFilebot.json");
    }

    const falData = await falResponse.json();
    const tabirData = await tabirResponse.json();
    const hafezData = await hafezResponse.json();

    fortunes = normalizeRecords(falData);
    interpretations = normalizeRecords(tabirData);
    mainHafezData = normalizeRecords(hafezData);

    if (fortunes.length === 0) {
        throw new Error("هیچ فالی در fal.json پیدا نشد.");
    }
}


function normalizeRecords(data) {
    if (Array.isArray(data)) {
        return data.filter(Boolean);
    }

    if (data && typeof data === "object") {
        return Object.entries(data)
            .map(([key, value]) => {
                if (value && typeof value === "object") {
                    return {
                        ...value,
                        __recordId: key
                    };
                }

                return null;
            })
            .filter(Boolean);
    }

    return [];
}


function randomItem(array) {
    if (!Array.isArray(array) || array.length === 0) {
        return null;
    }

    return array[Math.floor(Math.random() * array.length)];
}


function getValue(object, keys) {
    if (!object) {
        return "";
    }

    for (const key of keys) {
        if (
            object[key] !== undefined &&
            object[key] !== null &&
            object[key] !== ""
        ) {
            return object[key];
        }
    }

    return "";
}


function normalizeText(text) {
    return String(text || "")
        .replace(/\r\n/g, "\n")
        .replace(/\r/g, "\n")
        .replace(/\u200c/g, "")
        .replace(/[ًٌٍَُِّْـ]/g, "")
        .replace(/[يى]/g, "ی")
        .replace(/[ك]/g, "ک")
        .replace(/\s+/g, " ")
        .trim();
}


function getPoem(record) {
    return getValue(record, [
        "Poem",
        "poem",
        "شعر",
        "غزل"
    ]);
}


function getGhazalNumber(record) {
    const source = getValue(record, [
        "Source",
        "source",
        "منبع"
    ]);

    const title = getValue(record, [
        "Title",
        "title",
        "عنوان"
    ]);

    const recordId = getValue(record, [
        "__recordId",
        "ID",
        "Id",
        "id",
        "شناسه"
    ]);

    const sourceMatch = String(source).match(/\/sh(\d+)/i);

    if (sourceMatch) {
        return Number(sourceMatch[1]);
    }

    const titleMatch = String(title).match(/(\d+)/);

    if (titleMatch) {
        return Number(titleMatch[1]);
    }

    const idMatch = String(recordId).match(/(\d+)/);

    if (idMatch) {
        return Number(idMatch[1]);
    }

    return null;
}


function getInterpretationText(record) {
    return getValue(record, [
        "interpretation",
        "Interpretation",
        "interpretation_text",
        "Tabir",
        "tabir",
        "تعبیر",
        "متن"
    ]);
}


function findInterpretation(fortune) {
    if (!fortune || interpretations.length === 0) {
        return null;
    }

    const fortunePoem = normalizeText(getPoem(fortune));

    /*
     * Hafez_Tabir.json دارای متن کامل غزل و تعبیر متناظر است.
     * ابتدا خود غزل را تطبیق می‌دهیم تا تعبیر اشتباه نمایش داده نشود.
     */
    if (fortunePoem) {
        const poemMatch = interpretations.find(item => {
            const tabirPoem = getPoem(item);

            return (
                tabirPoem &&
                normalizeText(tabirPoem) === fortunePoem
            );
        });

        if (poemMatch) {
            return poemMatch;
        }
    }

    /*
     * اگر تطبیق متن غزل ممکن نبود، شماره غزل بررسی می‌شود.
     */
    const fortuneNumber = getGhazalNumber(fortune);

    if (fortuneNumber !== null) {
        const numberMatch = interpretations.find(item => {
            return getGhazalNumber(item) === fortuneNumber;
        });

        if (numberMatch) {
            return numberMatch;
        }
    }

    return null;
}


function findMainHafezRecord(fortune) {
    const fortunePoem = normalizeText(getPoem(fortune));

    if (fortunePoem) {
        const poemMatch = mainHafezData.find(item => {
            const poem = getPoem(item);

            return (
                poem &&
                normalizeText(poem) === fortunePoem
            );
        });

        if (poemMatch) {
            return poemMatch;
        }
    }

    const fortuneNumber = getGhazalNumber(fortune);

    if (fortuneNumber !== null) {
        const numberMatch = mainHafezData.find(item => {
            return getGhazalNumber(item) === fortuneNumber;
        });

        if (numberMatch) {
            return numberMatch;
        }
    }

    return null;
}


function getAudio(record) {
    return getValue(record, [
        "Audio",
        "audio",
        "صوت"
    ]);
}


function prepareAudio(fortune) {
    let audio = getAudio(fortune);

    if (!audio) {
        const mainRecord = findMainHafezRecord(fortune);

        if (mainRecord) {
            audio = getAudio(mainRecord);
        }
    }

    return audio;
}


function showFortune() {
    if (!fortunes.length) {
        alert("فال حافظی پیدا نشد.");
        return;
    }

    let fortune;

    /*
     * در صورت امکان فال قبلی دوباره انتخاب نشود.
     */
    if (fortunes.length > 1) {
        do {
            fortune = randomItem(fortunes);
        } while (fortune === lastFortune);
    } else {
        fortune = fortunes[0];
    }

    lastFortune = fortune;

    const title = getValue(fortune, [
        "Title",
        "title",
        "عنوان"
    ]);

    const poem = getPoem(fortune);

    const source = getValue(fortune, [
        "Source",
        "source",
        "منبع"
    ]);

    const tabir = findInterpretation(fortune);
    const tabirText = getInterpretationText(tabir);

    const audio = prepareAudio(fortune);

    poemTitle.textContent = title || "غزل حافظ";

    poemText.textContent =
        poem || "متن غزل موجود نیست.";

    if (source) {
        poemSource.textContent = `منبع: ${source}`;
    } else {
        poemSource.textContent = "";
    }

    interpretation.textContent =
        tabirText ||
        "تعبیری برای این غزل ثبت نشده است.";

    audioPlayer.pause();
    audioPlayer.removeAttribute("src");
    audioPlayer.load();
    audioPlayer.style.display = "none";

    if (audio) {
        audioPlayer.src = audio;
        audioPlayer.style.display = "block";
        audioPlayer.load();
    }

    homeScreen.classList.remove("active");
    fortuneScreen.classList.add("active");

    window.scrollTo({
        top: 0,
        behavior: "smooth"
    });
}


fortuneButton.addEventListener(
    "click",
    showFortune
);

newFortuneButton.addEventListener(
    "click",
    showFortune
);


loadData()
    .then(() => {
        fortuneButton.disabled = false;
    })
    .catch(error => {
        console.error(error);

        fortuneButton.disabled = true;
        fortuneButton.textContent =
            "خطا در بارگذاری اطلاعات فال";
    });
