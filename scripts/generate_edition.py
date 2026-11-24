import html
import json
import os
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from zoneinfo import ZoneInfo
import requests
from google import genai

# ==============================================================================
# KONFIGURACJA TEMATÓW OSOBISTYCH (możesz dowolnie edytować)
# ==============================================================================
USER_INTERESTS = [
    "Zegarmistrzostwo mechaniczne i kwarcowe, nowe modele, microbrandy, limitowane edycje i design zegarków",
    "Nauka, fizyka kwantowa, astronomia i przełomowe odkrycia badawcze",
    "Cyberbezpieczeństwo, architektura systemów, AI i zaawansowane technologie",
    "Kolej dużych prędkości, nowoczesny transport szynowy i wielkie projekty infrastrukturalne na świecie",
    "Kultura, muzyka alternatywna i klasyczna, architektura oraz wzornictwo przemysłowe",
]

CONTINENTS = [
    "Europa",
    "Ameryka Północna",
    "Ameryka Południowa",
    "Azja",
    "Afryka",
    "Australia i Oceania",
]

RSS_FEEDS = {
    "Świat (przegląd główny)": [
        ("BBC World", "https://feeds.bbci.co.uk/news/world/rss.xml"),
        ("Al Jazeera", "https://www.aljazeera.com/xml/rss/all.xml"),
    ],
    "Europa (bez polskiej polityki)": [
        ("BBC Europe", "https://feeds.bbci.co.uk/news/world/europe/rss.xml"),
        ("France 24 Europe", "https://www.france24.com/en/europe/rss"),
        ("Deutsche Welle Europe", "https://rss.dw.com/xml/rss-en-eu"),
    ],
    "Ameryka Północna": [
        ("BBC US & Canada", "https://feeds.bbci.co.uk/news/world/us_and_canada/rss.xml"),
        ("NPR News", "https://feeds.npr.org/1001/rss.xml"),
    ],
    "Ameryka Południowa": [
        ("BBC Latin America", "https://feeds.bbci.co.uk/news/world/latin_america/rss.xml"),
        ("MercoPress", "https://en.mercopress.com/rss/"),
    ],
    "Azja": [
        ("BBC Asia", "https://feeds.bbci.co.uk/news/world/asia/rss.xml"),
        ("Deutsche Welle Asia", "https://rss.dw.com/xml/rss-en-asia"),
    ],
    "Afryka": [
        ("BBC Africa", "https://feeds.bbci.co.uk/news/world/africa/rss.xml"),
        ("Africanews", "https://www.africanews.com/feed/"),
    ],
    "Australia i Oceania": [
        ("ABC News Australia", "https://www.abc.net.au/news/feed/51120/rss.xml"),
        ("Radio New Zealand", "https://www.rnz.co.nz/rss/national.xml"),
    ],
    "Zegarmistrzostwo i design": [
        ("Monochrome Watches", "https://monochrome-watches.com/feed/"),
        ("Dezeen Design & Architecture", "https://www.dezeen.com/feed/"),
    ],
    "Nauka, technologia i kolej": [
        ("ScienceDaily Top Science", "https://www.sciencedaily.com/rss/top/science.xml"),
        ("Ars Technica", "https://feeds.arstechnica.com/arstechnica/index"),
        ("International Railway Journal", "https://www.railjournal.com/feed/"),
    ],
}

DATA_DIR = "data"
INDEX_FILE = os.path.join(DATA_DIR, "index.json")


def get_warsaw_date() -> str:
    return datetime.now(ZoneInfo("Europe/Warsaw")).strftime("%Y-%m-%d")


def clean_html_text(raw: str, max_len: int = 260) -> str:
    if not raw:
        return ""
    text = html.unescape(raw)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > max_len:
        text = text[:max_len].rsplit(" ", 1)[0] + "..."
    return text


def fetch_rss_digest(max_per_feed: int = 3) -> str:
    """Pobiera najnowsze nagłówki i streszczenia z kanałów RSS."""
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; KurierSwiatowyBot/1.0; +https://github.com)"
    }
    sections_output = []
    total_items = 0

    for group_name, feeds in RSS_FEEDS.items():
        group_lines = [f"### SEKCJA: {group_name}"]
        for source_name, feed_url in feeds:
            try:
                resp = requests.get(feed_url, headers=headers, timeout=8)
                if resp.status_code != 200:
                    continue
                root = ET.fromstring(resp.content)
                entries = [
                    el for el in root.iter()
                    if el.tag.endswith("item") or el.tag.endswith("entry")
                ]
                count = 0
                for entry in entries:
                    if count >= max_per_feed:
                        break
                    title = ""
                    link = ""
                    summary = ""
                    for child in entry:
                        tag = child.tag.split("}")[-1].lower()
                        if tag == "title" and child.text:
                            title = clean_html_text(child.text, 160)
                        elif tag == "link":
                            if child.text and child.text.strip().startswith("http"):
                                link = child.text.strip()
                            elif child.attrib.get("href"):
                                link = child.attrib["href"].strip()
                        elif tag in ("description", "summary", "content") and child.text and not summary:
                            summary = clean_html_text(child.text, 240)
                    if title and link:
                        group_lines.append(
                            f"- [{source_name}] {title} | {summary} | URL: {link}"
                        )
                        count += 1
                        total_items += 1
            except Exception as exc:
                print(f"[WARN] Pominięto kanał {source_name}: {exc}")
        if len(group_lines) > 1:
            sections_output.append("\n".join(group_lines))

    print(f"Pobrano łącznie {total_items} aktualnych depesz z kanałów RSS.")
    if total_items < 15:
        raise RuntimeError("Zbyt mało depesz pobranych z kanałów RSS.")
    return "\n\n".join(sections_output)


def fetch_wikimedia_image(query: str) -> str:
    """Pobiera dopasowane zdjęcie z Wikimedia Commons o szerokości 900px."""
    if not query:
        return ""
    url = "https://commons.wikimedia.org/w/api.php"
    params = {
        "action": "query",
        "format": "json",
        "generator": "search",
        "gsrsearch": f"filetype:bitmap {query}",
        "gsrnamespace": 6,
        "gsrlimit": 5,
        "prop": "imageinfo",
        "iiprop": "url|size",
        "iiurlwidth": 900,
    }
    headers = {
        "User-Agent": "KurierSwiatowyBot/1.0 (https://github.com; automated daily newspaper)"
    }
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        if resp.status_code != 200:
            return ""
        data = resp.json()
        pages = data.get("query", {}).get("pages", {})
        for page in pages.values():
            info_list = page.get("imageinfo", [])
            if not info_list:
                continue
            info = info_list[0]
            thumb_url = info.get("thumburl") or info.get("url", "")
            width = info.get("width", 0)
            height = info.get("height", 0)
            lower = thumb_url.lower()
            if any(lower.endswith(ext) for ext in (".svg", ".pdf", ".tif", ".tiff", ".ogg", ".webm")):
                continue
            if width >= 600 and height >= 350:
                return thumb_url
    except Exception as exc:
        print(f"[WARN] Nie udało się pobrać zdjęcia dla '{query}': {exc}")
    return ""


def extract_json_payload(raw_text: str) -> dict:
    if not raw_text:
        raise ValueError("Model zwrócił pustą odpowiedź.")
    cleaned = raw_text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not match:
        raise ValueError("Nie znaleziono obiektu JSON w odpowiedzi modelu.")
    return json.loads(match.group(0), strict=False)


def discover_groq_models(api_key: str) -> list[str]:
    """Pobiera aktualną listę aktywnych modeli czatowych z konta Groq."""
    url = "https://api.groq.com/openai/v1/models"
    headers = {"Authorization": f"Bearer {api_key}"}
    excluded = ("whisper", "guard", "tts", "playai", "orpheus", "safeguard", "embed")
    resp = requests.get(url, headers=headers, timeout=15)
    if resp.status_code != 200:
        raise RuntimeError(f"Groq models API błąd {resp.status_code}: {resp.text[:300]}")
    models_data = resp.json().get("data", [])
    candidates = []
    for item in models_data:
        mid = item.get("id", "")
        lower = mid.lower()
        if mid and not any(tok in lower for tok in excluded):
            candidates.append(mid)

    def model_priority(mid: str) -> int:
        low = mid.lower()
        if "llama-4" in low or "70b" in low or "120b" in low:
            return 0
        if "qwen" in low or "gpt-oss" in low or "32b" in low or "deepseek" in low:
            return 1
        if "llama" in low or "mixtral" in low or "gemma" in low:
            return 2
        return 3

    candidates.sort(key=model_priority)
    return candidates


def call_groq_json(api_key: str, models: list[str], prompt: str, required_key: str) -> dict:
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    last_err = None

    for model_id in models:
        use_json_format = True
        for attempt in range(1, 3):
            payload = {
                "model": model_id,
                "messages": [
                    {
                        "role": "system",
                        "content": "Jesteś redaktorem naczelnym polskiego dziennika opiniotwórczego. Zwracasz wyłącznie poprawny obiekt JSON bez żadnego tekstu przed ani po nim.",
                    },
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.3,
                "max_tokens": 8000,
            }
            if use_json_format:
                payload["response_format"] = {"type": "json_object"}

            try:
                print(f"Groq: próba z modelem {model_id} (próba {attempt})...")
                resp = requests.post(url, headers=headers, json=payload, timeout=90)
                if resp.status_code == 200:
                    content = resp.json()["choices"][0]["message"]["content"]
                    parsed = extract_json_payload(content)
                    if parsed.get(required_key):
                        print(f"Groq: sukces modelem {model_id}.")
                        return parsed
                    raise ValueError(f"Brak oczekiwanego klucza '{required_key}' w JSON.")
                err_text = resp.text[:400]
                last_err = f"{model_id} -> HTTP {resp.status_code}: {err_text}"
                print(f"[WARN] {last_err}")
                if resp.status_code == 400 and use_json_format and "json" in err_text.lower():
                    use_json_format = False
                    continue
                if resp.status_code == 429 and attempt == 1:
                    time.sleep(20)
                    continue
                break
            except Exception as exc:
                last_err = f"{model_id} -> {exc}"
                print(f"[WARN] {last_err}")
                break

    raise RuntimeError(f"Żaden model Groq nie zwrócił poprawnego wydania. Ostatni błąd: {last_err}")


def generate_via_groq(today_str: str, rss_digest: str, groq_key: str) -> dict:
    models = discover_groq_models(groq_key)
    if not models:
        raise RuntimeError("Lista modeli Groq jest pusta.")
    print(f"Wykryte aktywne modele Groq: {models}")

    interests_bullet = "\n".join(f"- {item}" for item in USER_INTERESTS)

    prompt_part1 = f"""
Dzisiejsza data: {today_str}.
Na podstawie poniższych aktualnych depesz RSS przygotuj po polsku PIERWSZĄ CZĘŚĆ wydania gazety „Kurier Światowy”.

ZASADY:
- ZERO polskiej polityki krajowej.
- ZERO powielania tematów (każdy z 9 artykułów poniżej ma dotyczyć innego wydarzenia).
- Każdy artykuł musi zawierać: `title` (po polsku), `category`, `region`, `summary` (2 zdania), `body` (3 pogłębione akapity oddzielone `\\n\\n`), `image_query` (2-4 słowa po angielsku do wyszukiwarki zdjęć), `sources` (lista z nazwą źródła) oraz `source_url` (dokładny link URL z depeszy).

WYMAGANE SEKCJE W TYM KROKU:
1. `editorial_lead`: 2-zdaniowe wprowadzenie redakcyjne podsumowujące dzisiejszy dzień na świecie.
2. `top5`: dokładnie 5 najważniejszych wydarzeń ze świata.
3. `interests`: dokładnie 4 pogłębione artykuły dopasowane do zainteresowań czytelnika:
{interests_bullet}

DEPESZE RSS:
{rss_digest}

Zwróć wyłącznie obiekt JSON o kluczach: `editorial_lead`, `top5`, `interests`.
"""
    print("Groq (1/2): Generowanie sekcji Najważniejsze 5 oraz Wybrane tematy...")
    part1 = call_groq_json(groq_key, models, prompt_part1, "top5")

    used_titles = [
        art.get("title", "")
        for art in (part1.get("top5", []) + part1.get("interests", []))
        if art.get("title")
    ]
    used_list_str = "\n".join(f"- {t}" for t in used_titles)

    print("Oczekiwanie 15 sekund (ochrona darmowego limitu tokenów na minutę)...")
    time.sleep(15)

    prompt_part2 = f"""
Dzisiejsza data: {today_str}.
Na podstawie poniższych depesz RSS przygotuj po polsku DRUGĄ CZĘŚĆ wydania gazety „Kurier Światowy”: przegląd 6 kontynentów.

ZASADY:
- ZERO polskiej polityki krajowej (w Europie opisuj inne państwa lub zjawiska ogólnoeuropejskie).
- NIE POWTARZAJ ŻADNEGO Z PONIŻSZYCH TEMATÓW UŻYTYCH JUŻ NA PIERWSZEJ STRONIE:
{used_list_str}
- Dla każdego z 6 kontynentów przygotuj dokładnie 3 odrębne artykuły (nie tylko polityka — uwzględnij też gospodarkę, naukę, technologię, infrastrukturę, społeczeństwo i kulturę).
- Każdy artykuł musi zawierać: `title` (po polsku), `category`, `region` (nazwa kontynentu), `summary` (2 zdania), `body` (3 pogłębione akapity oddzielone `\\n\\n`), `image_query` (2-4 słowa po angielsku do wyszukiwarki zdjęć), `sources` (lista z nazwą źródła) oraz `source_url` (dokładny link URL z depeszy).

DEPESZE RSS:
{rss_digest}

Zwróć wyłącznie obiekt JSON o strukturze:
{{
  "continents": {{
    "Europa": [3 artykuły],
    "Ameryka Północna": [3 artykuły],
    "Ameryka Południowa": [3 artykuły],
    "Azja": [3 artykuły],
    "Afryka": [3 artykuły],
    "Australia i Oceania": [3 artykuły]
  }}
}}
"""
    print("Groq (2/2): Generowanie przeglądu 6 kontynentów...")
    part2 = call_groq_json(groq_key, models, prompt_part2, "continents")

    return {
        "date": today_str,
        "editorial_lead": part1.get("editorial_lead", ""),
        "top5": part1.get("top5", []),
        "interests": part1.get("interests", []),
        "continents": part2.get("continents", {}),
    }


def discover_gemini_models(client) -> list[str]:
    models = ["gemini-3.8-flash"]
    excluded = ("embedding", "imagen", "veo", "aqa", "tts", "audio", "robotics", "computer-use")
    try:
        for m in client.models.list():
            name = getattr(m, "name", "") or ""
            if name.startswith("models/"):
                name = name[len("models/"):]
            low = name.lower()
            if "gemini" in low and ("flash" in low or "pro" in low):
                if not any(tok in low for tok in excluded) and name not in models:
                    models.append(name)
    except Exception:
        pass
    return models[:4]


def generate_via_gemini(today_str: str, rss_digest: str, gemini_key: str) -> dict:
    client = genai.Client(api_key=gemini_key)
    interests_bullet = "\n".join(f"- {item}" for item in USER_INTERESTS)
    prompt = f"""
Dzisiejsza data: {today_str}.
Na podstawie poniższych depesz RSS przygotuj pełne wydanie dziennika „Kurier Światowy” po polsku (27 unikalnych artykułów: 5 w `top5`, 4 w `interests`, oraz po 3 w każdym z 6 kluczy obiektu `continents`: "Europa", "Ameryka Północna", "Ameryka Południowa", "Azja", "Afryka", "Australia i Oceania").
Zasady: zero polskiej polityki, zero duplikatów między sekcjami, 3 pogłębione akapity w `body` oddzielone `\\n\\n`, pola `title`, `category`, `region`, `summary`, `body`, `image_query` (po angielsku), `sources`, `source_url`.
Zainteresowania czytelnika:
{interests_bullet}

DEPESZE RSS:
{rss_digest}

Zwróć wyłącznie JSON o kluczach: `date`, `editorial_lead`, `top5`, `interests`, `continents`.
"""
    models = discover_gemini_models(client)
    last_err = None
    for model_name in models:
        for attempt in range(1, 4):
            try:
                print(f"Gemini: próba z modelem {model_name} (próba {attempt}/3)...")
                resp = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config={
                        "response_mime_type": "application/json",
                        "max_output_tokens": 32768,
                        "temperature": 0.3,
                    },
                )
                if resp and resp.text:
                    return extract_json_payload(resp.text)
            except Exception as exc:
                last_err = exc
                err_str = str(exc)
                print(f"[WARN] Gemini {model_name} błąd: {err_str}")
                if any(c in err_str for c in ("503", "UNAVAILABLE", "429")) and attempt < 3:
                    time.sleep(25 * attempt)
                else:
                    break
    raise RuntimeError(f"Brak działającego modelu Gemini. Ostatni błąd: {last_err}")


def build_grounding_links(edition: dict) -> list[dict]:
    links = []
    seen = set()
    all_articles = []
    all_articles.extend(edition.get("top5", []))
    all_articles.extend(edition.get("interests", []))
    for cont in CONTINENTS:
        all_articles.extend(edition.get("continents", {}).get(cont, []))

    for art in all_articles:
        url = (art.get("source_url") or "").strip()
        src_names = art.get("sources") or []
        label = src_names[0] if src_names else "Źródło"
        title = f"{label}: {art.get('title', '')[:65]}"
        if url.startswith("http") and url not in seen:
            seen.add(url)
            links.append({"title": title, "url": url})
    return links[:27]


def enrich_with_images(edition: dict) -> dict:
    all_articles = []
    all_articles.extend(edition.get("top5", []))
    all_articles.extend(edition.get("interests", []))
    for cont in CONTINENTS:
        all_articles.extend(edition.get("continents", {}).get(cont, []))

    for idx, art in enumerate(all_articles):
        query = art.get("image_query", "")
        art["image_url"] = fetch_wikimedia_image(query)
        art["id"] = f"art-{idx + 1}"
        time.sleep(0.2)
    return edition


def update_archive_index(today_str: str, edition: dict) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    index_data = {"editions": []}
    if os.path.exists(INDEX_FILE):
        with open(INDEX_FILE, "r", encoding="utf-8") as f:
            try:
                index_data = json.load(f)
            except json.JSONDecodeError:
                index_data = {"editions": []}

    existing = {item["date"]: item for item in index_data.get("editions", [])}
    issue_num = (
        existing[today_str]["issue_number"]
        if today_str in existing
        else len(existing) + 1
    )
    edition["issue_number"] = issue_num

    edition_path = os.path.join(DATA_DIR, f"{today_str}.json")
    with open(edition_path, "w", encoding="utf-8") as f:
        json.dump(edition, f, ensure_ascii=False, indent=2)

    top_title = edition["top5"][0].get("title", "") if edition.get("top5") else ""
    existing[today_str] = {
        "date": today_str,
        "issue_number": issue_num,
        "headline": top_title,
    }

    sorted_editions = sorted(existing.values(), key=lambda x: x["date"], reverse=True)
    with open(INDEX_FILE, "w", encoding="utf-8") as f:
        json.dump({"editions": sorted_editions}, f, ensure_ascii=False, indent=2)


def main():
    today_str = get_warsaw_date()
    force = os.getenv("FORCE_REGENERATE", "false").lower() == "true"
    edition_path = os.path.join(DATA_DIR, f"{today_str}.json")

    if os.path.exists(edition_path) and not force:
        print(f"Wydanie z dnia {today_str} już istnieje. Pomijam generowanie.")
        return

    print(f"Generowanie wydania Kuriera Światowego na dzień {today_str}...")
    rss_digest = fetch_rss_digest(max_per_feed=3)

    groq_key = os.environ.get("GROQ_API_KEY", "").strip()
    gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()
    edition = None

    if groq_key:
        try:
            edition = generate_via_groq(today_str, rss_digest, groq_key)
        except Exception as groq_exc:
            print(f"[WARN] Groq zakończył się błędem ({groq_exc}).")
            if gemini_key:
                print("Przełączam awaryjnie na Gemini API...")
            else:
                raise

    if edition is None:
        if gemini_key:
            edition = generate_via_gemini(today_str, rss_digest, gemini_key)
        else:
            raise RuntimeError("Brak klucza GROQ_API_KEY ani GEMINI_API_KEY w GitHub Secrets.")

    edition["grounding_links"] = build_grounding_links(edition)
    edition = enrich_with_images(edition)
    update_archive_index(today_str, edition)
    print(f"Sukces! Zapisano wydanie {edition_path} oraz zaktualizowano {INDEX_FILE}.")


if __name__ == "__main__":
    main()
