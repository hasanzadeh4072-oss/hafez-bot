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


async function loadData() {
    const [falResponse, tabirResponse] = await Promise.all([
        fetch("../fal.json"),
        fetch("../Hafez_Tabir.json")
    ]);

    if (!falResponse.ok) {
        throw new Error("خطا در دریافت fal.json");
    }

    if (!tabirResponse.ok) {
        throw new Error("خطا در دریافت Hafez_Tabir.json");
    }

    fortunes = await falResponse.json();
    interpretations = await tabirResponse.json();
}


function randomItem(array) {
    if (!Array.isArray(array) || array.length === 0) {
        return null;
    }

    return array[Math.floor(Math.random() * array.length)];
}


function findInterpretation(fortune) {
    if (!Array.isArray(interpretations)) {
        return null;
    }

    const id =
        fortune?.ID ??
        fortune?.Id ??
        fortune?.id ??
        fortune?.شناسه;

    if (id !== undefined) {
        const match = interpretations.find(item => {
            const itemId =
                item?.ID ??
                item?.Id ??
                item?.id ??
                item?.شناسه;

            return String(itemId) === String(id);
        });

        if (match) {
            return match;
        }
    }

    return randomItem(interpretations);
}


function getValue(object, keys) {
    for (const key of keys) {
        if (
            object &&
            object[key] !== undefined &&
            object[key] !== null &&
            object[key] !== ""
        ) {
            return object[key];
        }
    }

    return "";
}


function showFortune() {
    const fortune = randomItem(fortunes);

    if (!fortune) {
        alert("فال حافظی پیدا نشد.");
        return;
    }

    const title = getValue(fortune, [
        "Title",
        "title",
        "عنوان"
    ]);

    const poem = getValue(fortune, [
        "Poem",
        "poem",
        "شعر",
        "غزل"
    ]);

    const source = getValue(fortune, [
        "Source",
        "source",
        "منبع"
    ]);

    const audio = getValue(fortune, [
        "Audio",
        "audio",
        "صوت"
    ]);

    const tabir = findInterpretation(fortune);

    const tabirText = getValue(tabir, [
        "Tabir",
        "tabir",
        "Interpretation",
        "interpretation",
        "تعبیر",
        "متن"
    ]);

    poemTitle.textContent = title || "غزل حافظ";
    poemText.textContent = poem || "متن غزل موجود نیست.";
    poemSource.textContent = source ? `منبع: ${source}` : "";
    interpretation.textContent =
        tabirText || "تعبیری برای این فال ثبت نشده است.";

    audioPlayer.pause();
    audioPlayer.removeAttribute("src");
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


fortuneButton.addEventListener("click", showFortune);
newFortuneButton.addEventListener("click", showFortune);


loadData().catch(error => {
    console.error(error);

    fortuneButton.disabled = true;
    fortuneButton.textContent = "خطا در بارگذاری اطلاعات فال";
});
