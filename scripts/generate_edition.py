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

PRIMARY_MODELS = [
    "gemini-3.8-flash",
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


def clean_html_text(raw: str, max_len: int = 340) -> str:
    if not raw:
        return ""
    text = html.unescape(raw)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > max_len:
        text = text[:max_len].rsplit(" ", 1)[0] + "..."
    return text


def fetch_rss_digest() -> str:
    """Pobiera najnowsze nagłówki i streszczenia z kanałów RSS."""
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; KurierSwiatowyBot/1.0; +https://github.com)"
    }
    sections_output = []
    total_items = 0

    for group_name, feeds in RSS_FEEDS.items():
        group_lines = [f"### SEKCJA ŹRÓDŁOWA: {group_name}"]
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
                    if count >= 5:
                        break
                    title = ""
                    link = ""
                    summary = ""
                    for child in entry:
                        tag = child.tag.split("}")[-1].lower()
                        if tag == "title" and child.text:
                            title = clean_html_text(child.text, 180)
                        elif tag == "link":
                            if child.text and child.text.strip().startswith("http"):
                                link = child.text.strip()
                            elif child.attrib.get("href"):
                                link = child.attrib["href"].strip()
                        elif tag in ("description", "summary", "content") and child.text and not summary:
                            summary = clean_html_text(child.text, 320)
                    if title and link:
                        group_lines.append(
                            f"- [{source_name}] {title} | Opis: {summary} | URL: {link}"
                        )
                        count += 1
                        total_items += 1
            except Exception as exc:
                print(f"[WARN] Pominięto kanał {source_name}: {exc}")
        if len(group_lines) > 1:
            sections_output.append("\n".join(group_lines))

    print(f"Pobrano łącznie {total_items} aktualnych depesz z kanałów RSS.")
    if total_items < 15:
        raise RuntimeError("Zbyt mało depesz pobranych z kanałów RSS — sprawdź połączenie sieciowe.")
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
    """Wyciąga i parsuje strukturę JSON z odpowiedzi modelu."""
    if not raw_text:
        raise ValueError("Model zwrócił pustą odpowiedź (brak tekstu).")
    cleaned = raw_text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not match:
        raise ValueError("Nie znaleziono obiektu JSON w odpowiedzi modelu.")
    return json.loads(match.group(0), strict=False)


def build_grounding_links(edition: dict) -> list[dict]:
    """Tworzy listę klikalnych źródeł na dole wydania na podstawie artykułów."""
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


def discover_candidate_models(client) -> list[str]:
    """Buduje listę modeli zaczynając od gemini-3.8-flash oraz wykrytych modeli zapasowych."""
    models = list(PRIMARY_MODELS)
    excluded_tokens = ("embedding", "imagen", "veo", "aqa", "tts", "audio", "robotics", "computer-use")
    try:
        for m in client.models.list():
            name = getattr(m, "name", "") or ""
            if name.startswith("models/"):
                name = name[len("models/"):]
            lower = name.lower()
            if "gemini" in lower and ("flash" in lower or "pro" in lower):
                if not any(tok in lower for tok in excluded_tokens) and name not in models:
                    models.append(name)
    except Exception as exc:
        print(f"[WARN] Nie udało się pobrać listy modeli zapasowych: {exc}")
    return models[:4]


def generate_newspaper_content(today_str: str, rss_digest: str) -> dict:
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "BRAK KLUCZA API: Zmienna GEMINI_API_KEY jest pusta. "
            "Dodaj ją w Settings -> Secrets and variables -> Actions -> Repository secrets."
        )

    client = genai.Client(api_key=api_key)
    interests_bullet = "\n".join(f"- {item}" for item in USER_INTERESTS)

    prompt = f"""
Dzisiejsza data: {today_str}.
Wciel się w rolę redaktora naczelnego prestiżowego, pogłębionego dziennika opiniotwórczego „Kurier Światowy”.
Poniżej znajduje się zestaw aktualnych depesz pobranych dzisiaj z międzynarodowych i branżowych redakcji. Na ich podstawie przygotuj kompletne wydanie gazety po polsku.

BEZWZGLĘDNE ZASADY REDAKCYJNE:
1. ZERO POLSKIEJ POLITYKI: Całkowicie pomiń bieżącą politykę krajową w Polsce (partie, sejm, rząd, wybory w Polsce). W sekcji Europa opisuj inne państwa europejskie lub zjawiska ogólnoeuropejskie.
2. ZERO POWIELANIA TEMATÓW: Żadne wydarzenie z sekcji „top5” nie może powtórzyć się w sekcji „interests” ani w żadnym z 6 kontynentów. Każdy z 27 artykułów w wydaniu musi dotyczyć innego, odrębnego tematu.
3. OPARCIE NA FAKTACH Z DEPESZ: Opieraj się wyłącznie na faktach zawartych w poniższych depeszach oraz swojej zweryfikowanej wiedzy kontekstowej — nie zmyślaj nieistniejących wydarzeń. Do każdego artykułu przypisz dokładny adres `source_url` z odpowiadającej mu depeszy.
4. POGŁĘBIONY STYL (ZERO PAPKI): Każdy artykuł ma mieć:
   - konkretny, dziennikarski tytuł po polsku (`title`),
   - kategorię (`category`, np. Geopolityka, Gospodarka, Nauka, Zegarmistrzostwo, Technologia, Kultura, Klimat, Infrastruktura),
   - 2-zdaniowy lead (`summary`) widoczny przed rozwinięciem,
   - 3 merytoryczne akapity rozwinięcia (`body`, oddzielone podwójnym znakiem nowej linii `\\n\\n`), wyjaśniające kontekst, przyczyny i konsekwencje,
   - krótkie angielskie zapytanie do wyszukiwarki zdjęć (`image_query`, 2–4 proste słowa po angielsku opisujące główny obiekt/miejsce, np. "mechanical watch movement", "tokyo bullet train", "european parliament brussels"),
   - nazwę redakcji źródłowej w liście `sources` (np. `["BBC World"]`) oraz dokładny link `source_url` z listy depesz.

STRUKTURA WYDANIA (łącznie 27 unikalnych artykułów):
- `top5`: dokładnie 5 najważniejszych i najistotniejszych wydarzeń ze świata (pierwszy będzie artykułem głównym na pierwszej stronie).
- `interests`: dokładnie 4 pogłębione materiały dopasowane do poniższych zainteresowań czytelnika:
{interests_bullet}
- `continents`: obiekt zawierający dokładnie 6 kluczy: "Europa", "Ameryka Północna", "Ameryka Południowa", "Azja", "Afryka", "Australia i Oceania". Pod każdym kontynentem umieść listę dokładnie 3 artykułów (nie skupiaj się wyłącznie na polityce — uwzględnij też gospodarkę, naukę, technologię, społeczeństwo i kulturę).

AKTUALNE DEPESZE ŹRÓDŁOWE:
{rss_digest}

Zwróć WYŁĄCZNIE poprawny obiekt JSON o dokładnie takiej strukturze:
{{
  "date": "{today_str}",
  "editorial_lead": "Krótkie, 2-zdaniowe wprowadzenie redakcyjne podsumowujące główny motyw dzisiejszego wydania.",
  "top5": [
    {{
      "title": "...",
      "category": "...",
      "region": "Świat",
      "summary": "...",
      "body": "Akapit 1...\\n\\nAkapit 2...\\n\\nAkapit 3...",
      "image_query": "...",
      "sources": ["Nazwa źródła"],
      "source_url": "https://..."
    }}
  ],
  "interests": [
    {{
      "title": "...",
      "category": "...",
      "region": "Wybrane tematy",
      "summary": "...",
      "body": "Akapit 1...\\n\\nAkapit 2...\\n\\nAkapit 3...",
      "image_query": "...",
      "sources": ["Nazwa źródła"],
      "source_url": "https://..."
    }}
  ],
  "continents": {{
    "Europa": [],
    "Ameryka Północna": [],
    "Ameryka Południowa": [],
    "Azja": [],
    "Afryka": [],
    "Australia i Oceania": []
  }}
}}
"""

    candidate_models = discover_candidate_models(client)
    print(f"Wykryta kolejność modeli: {candidate_models}")

    last_error = None
    response = None
    retry_delays = [25, 45, 60]

    for model_name in candidate_models:
        for attempt in range(1, 5):
            try:
                print(f"Próba generowania wydania modelem {model_name} (próba {attempt}/4)...")
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config={
                        "response_mime_type": "application/json",
                        "max_output_tokens": 32768,
                        "temperature": 0.3,
                    },
                )
                if response and response.text:
                    print(f"Sukces! Otrzymano pełne wydanie z modelu: {model_name}")
                    break
            except Exception as exc:
                last_error = exc
                err_str = str(exc)
                print(f"[WARN] Model {model_name} (próba {attempt}) zgłosił: {err_str}")
                is_transient = any(code in err_str for code in ("503", "UNAVAILABLE", "429", "overloaded"))
                if is_transient and attempt <= len(retry_delays):
                    wait_sec = retry_delays[attempt - 1]
                    print(f"Serwer chwilowo obciążony — odczekuję {wait_sec} s przed ponowieniem...")
                    time.sleep(wait_sec)
                else:
                    break
        if response and getattr(response, "text", None):
            break

    if response is None or not getattr(response, "text", None):
        raise RuntimeError(f"Nie udało się wygenerować treści. Ostatni błąd: {last_error}")

    edition = extract_json_payload(response.text)
    edition["grounding_links"] = build_grounding_links(edition)
    return edition


def enrich_with_images(edition: dict) -> dict:
    """Dopisuje dopasowane zdjęcia z Wikimedia Commons do każdego artykułu."""
    all_articles = []
    all_articles.extend(edition.get("top5", []))
    all_articles.extend(edition.get("interests", []))
    for cont in CONTINENTS:
        all_articles.extend(edition.get("continents", {}).get(cont, []))

    for idx, art in enumerate(all_articles):
        query = art.get("image_query", "")
        img_url = fetch_wikimedia_image(query)
        art["image_url"] = img_url
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

    top_title = ""
    if edition.get("top5"):
        top_title = edition["top5"][0].get("title", "")

    existing[today_str] = {
        "date": today_str,
        "issue_number": issue_num,
        "headline": top_title,
    }

    sorted_editions = sorted(
        existing.values(), key=lambda x: x["date"], reverse=True
    )
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
    rss_digest = fetch_rss_digest()
    edition = generate_newspaper_content(today_str, rss_digest)
    edition = enrich_with_images(edition)
    update_archive_index(today_str, edition)
    print(f"Sukces! Zapisano wydanie {edition_path} oraz zaktualizowano {INDEX_FILE}.")


if __name__ == "__main__":
    main()
