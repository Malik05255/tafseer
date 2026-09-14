import html
import logging
import re
from urllib.parse import quote

import httpx


logger = logging.getLogger("tafseer.scripture")

_ARABIC_DIACRITICS = re.compile(r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED]")
_WORDS = re.compile(r"[\u0621-\u063A\u0641-\u064A]{3,}")
_TAGS = re.compile(r"<[^>]+>")
_STOPWORDS = {
    "كان", "كانت", "كنت", "فيه", "فيها", "هذا", "هذه", "ذلك", "الذي", "التي",
    "علي", "الى", "عن", "من", "ثم", "بعد", "بعدين", "بس", "معه", "معها",
    "انا", "هو", "هي", "هم", "احنا", "نحن", "رايت", "شفت", "حلمت", "رؤيا",
    "رؤيه", "منام", "المنام", "شيء", "شي", "مره", "جدا", "كانه", "صار", "جاء", "راح",
}


def _normalize_arabic(text: str) -> str:
    text = _ARABIC_DIACRITICS.sub("", text)
    return text.translate(str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ى": "ي", "ة": "ه"}))


def _keywords(text: str, limit: int = 5) -> list[str]:
    normalized = _normalize_arabic(text.lower())
    result: list[str] = []
    for raw_word in _WORDS.findall(normalized):
        word = raw_word
        if len(word) > 4 and word.startswith("و"):
            candidate = word[1:]
            if candidate not in _STOPWORDS:
                word = candidate
        if word in _STOPWORDS or word in result:
            continue
        result.append(word)
        if len(result) >= limit:
            break
    return result


def _grade_class(grade: str) -> str:
    value = _normalize_arabic(grade.lower())
    weak_markers = (
        "ضعيف", "موضوع", "منكر", "باطل", "لا يصح", "لا يثبت", "كذاب", "متروك",
        "اسناده واه", "حديث واه", "انقطاع", "منقطع", "مجهول", "اضطراب",
    )
    if any(marker in value for marker in weak_markers):
        return "weak"
    strong_markers = (
        "صحيح", "حسن", "ثابت", "اسناده صحيح", "اسناده حسن", "رجاله ثقات",
    )
    if any(marker in value for marker in strong_markers):
        return "accepted"
    return "unclassified"


class ScriptureRetriever:
    """Retrieve Quran and hadith evidence from live, source-aware corpora.

    Quran search covers the full quran-uthmani corpus served by AlQuran Cloud,
    whose Arabic text is sourced from Tanzil. Hadith search uses Dorar's public
    Hadith Encyclopedia API and preserves the muhaddith's grading.
    """

    def __init__(self) -> None:
        self.timeout = httpx.Timeout(14.0, connect=6.0)

    async def retrieve(self, dream: str, answers: list[dict], limit: int = 10) -> list[dict]:
        answer_text = " ".join(str(item.get("value", "")) for item in answers)
        terms = _keywords(dream + " " + answer_text, limit=5)
        if not terms:
            return []

        quran_limit = max(3, min(6, limit // 2 + 1))
        hadith_limit = max(3, min(6, limit // 2 + 1))

        quran = await self._search_quran(terms, quran_limit)
        hadith = await self._search_hadith(terms, hadith_limit)
        return quran + hadith

    async def _search_quran(self, terms: list[str], limit: int) -> list[dict]:
        results: list[dict] = []
        seen: set[str] = set()
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for term in terms[:4]:
                url = f"https://api.alquran.cloud/v1/search/{quote(term)}/all/quran-uthmani"
                try:
                    response = await client.get(url, headers={"Accept": "application/json"})
                    response.raise_for_status()
                    payload = response.json()
                except Exception as exc:
                    logger.warning("quran_search_failed term=%s type=%s", term, type(exc).__name__)
                    continue

                data = payload.get("data", {}) if isinstance(payload, dict) else {}
                matches = data.get("matches", []) if isinstance(data, dict) else []
                if not isinstance(matches, list):
                    continue
                for item in matches:
                    if not isinstance(item, dict):
                        continue
                    surah = item.get("surah", {}) if isinstance(item.get("surah"), dict) else {}
                    surah_no = surah.get("number")
                    ayah_no = item.get("numberInSurah")
                    text = str(item.get("text", "")).strip()
                    if not surah_no or not ayah_no or not text:
                        continue
                    ref = f"القرآن {surah_no}:{ayah_no}"
                    if ref in seen:
                        continue
                    seen.add(ref)
                    results.append(
                        {
                            "kind": "source",
                            "source_title": "القرآن الكريم",
                            "source_ref": ref,
                            "source_type": "quran",
                            "text": text,
                            "notes": (
                                "نتيجة بحث من كامل القرآن بإصدار quran-uthmani عبر AlQuran Cloud؛ "
                                "النص العربي مصدره Tanzil. لا يعني تطابق كلمة أن الآية تفسير مباشر للرمز."
                            ),
                            "verified": True,
                            "grade": "قرآن",
                            "grade_class": "quran",
                        }
                    )
                    if len(results) >= limit:
                        return results
        return results

    async def _search_hadith(self, terms: list[str], limit: int) -> list[dict]:
        queries = [" ".join(terms[:3])]
        queries.extend(terms[:2])
        results: list[dict] = []
        seen: set[tuple[str, str]] = set()
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for query in queries:
                if not query.strip():
                    continue
                try:
                    response = await client.get(
                        "https://dorar.net/dorar_api.json",
                        params={"skey": query},
                        headers={"Accept": "application/json", "User-Agent": "Tafseer-HAI/1.0"},
                    )
                    response.raise_for_status()
                    payload = response.json()
                except Exception as exc:
                    logger.warning("dorar_search_failed type=%s", type(exc).__name__)
                    continue

                raw = ""
                if isinstance(payload, dict):
                    ahadith = payload.get("ahadith", {})
                    if isinstance(ahadith, dict):
                        raw = str(ahadith.get("result", ""))
                if not raw:
                    continue

                for item in self._parse_dorar(raw):
                    key = (item["source_ref"], item["text"][:80])
                    if key in seen:
                        continue
                    seen.add(key)
                    results.append(item)
                    if len(results) >= limit:
                        return results
        return results

    @staticmethod
    def _parse_dorar(raw: str) -> list[dict]:
        text = html.unescape(raw)
        text = _TAGS.sub(" ", text)
        text = text.replace("\u200f", " ").replace("\xa0", " ")
        chunks = re.split(r"-{6,}", text)
        parsed: list[dict] = []
        pattern = re.compile(
            r"\s*\d+\s*-\s*(.*?)\s+الراوي:\s*(.*?)\s+المحدث:\s*(.*?)\s+المصدر:\s*(.*?)\s+"
            r"الصفحة أو الرقم:\s*(.*?)\s+خلاصة حكم المحدث:\s*(.*?)(?=$|التخريج:)",
            re.S,
        )
        for chunk in chunks:
            compact = re.sub(r"\s+", " ", chunk).strip()
            match = pattern.search(compact)
            if not match:
                continue
            hadith, narrator, scholar, source, page, grade = [x.strip(" .") for x in match.groups()]
            if not hadith or not source:
                continue
            klass = _grade_class(grade)
            parsed.append(
                {
                    "kind": "source",
                    "source_title": source,
                    "source_ref": f"{source} — {page}",
                    "source_type": "hadith_accepted" if klass == "accepted" else (
                        "hadith_weak" if klass == "weak" else "hadith_unclassified"
                    ),
                    "text": hadith,
                    "notes": f"الراوي: {narrator}؛ المحدث: {scholar}؛ حكم المحدث: {grade}",
                    "verified": True,
                    "grade": grade,
                    "grade_class": klass,
                }
            )
        return parsed
