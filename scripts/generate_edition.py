main()import json
import os
import re
import time
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

DATA_DIR = "data"
INDEX_FILE = os.path.join(DATA_DIR, "index.json")


def get_warsaw_date() -> str:
    return datetime.now(ZoneInfo("Europe/Warsaw")).strftime("%Y-%m-%d")


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
            # Odrzucamy pliki wektorowe, dokumenty i bardzo wąskie paski
            if any(lower.endswith(ext) for ext in (".svg", ".pdf", ".tif", ".tiff", ".ogg", ".webm")):
                continue
            if width >= 600 and height >= 350:
                return thumb_url
    except Exception as exc:
        print(f"[WARN] Nie udało się pobrać zdjęcia dla '{query}': {exc}")
    return ""


def extract_json_payload(raw_text: str) -> dict:
    """Wyciąga czysty obiekt JSON z odpowiedzi modelu."""
    cleaned = raw_text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not match:
        raise ValueError("Nie znaleziono struktury JSON w odpowiedzi modelu.")
    return json.loads(match.group(0))


def extract_grounding_sources(response) -> list[dict]:
    """Pobiera prawdziwe linki źródłowe zwrócone przez Google Search Grounding."""
    sources = []
    seen = set()
    try:
        candidates = getattr(response, "candidates", []) or []
        for cand in candidates:
            meta = getattr(cand, "grounding_metadata", None)
            if not meta:
                continue
            chunks = getattr(meta, "grounding_chunks", []) or []
            for ch in chunks:
                web = getattr(ch, "web", None)
                if web and getattr(web, "uri", None):
                    uri = web.uri
                    title = getattr(web, "title", None) or uri
                    if uri not in seen:
                        seen.add(uri)
                        sources.append({"title": title, "url": uri})
    except Exception:
        pass
    return sources[:25]


def generate_newspaper_content(today_str: str) -> dict:
    client = genai.Client()
    interests_bullet = "\n".join(f"- {item}" for item in USER_INTERESTS)

    prompt = f"""
Dzisiejsza data: {today_str}.
Wciel się w rolę redaktora naczelnego prestiżowego, pogłębionego dziennika opiniotwórczego „Kurier Światowy”.
Użyj wyszukiwarki Google, aby zebrać najświeższe, zweryfikowane wydarzenia z ostatnich 24–48 godzin (do dnia {today_str}).

BEZWZGLĘDNE ZASADY REDAKCYJNE:
1. ZERO POLSKIEJ POLITYKI: Całkowicie pomiń bieżącą politykę krajową w Polsce (partie, sejm, rząd, wybory w Polsce). W sekcji Europa opisuj inne państwa europejskie lub zjawiska ogólnoeuropejskie (naukowe, gospodarcze, kulturalne, społeczne, geopolityczne poza polską sceną polityczną).
2. ZERO POWIELANIA TEMATÓW: Żadne wydarzenie z sekcji „top5” nie może powtórzyć się w sekcji „interests” ani w żadnym z 6 kontynentów. Każdy z 27 artykułów w wydaniu musi dotyczyć innego, odrębnego tematu.
3. POGŁĘBIONY STYL (ZERO PAPKI): Każdy artykuł ma mieć:
   - konkretny, dziennikarski tytuł (`title`),
   - kategorię (`category`, np. Geopolityka, Gospodarka, Nauka, Zegarmistrzostwo, Technologia, Kultura, Klimat, Infrastruktura),
   - 2-zdaniowy lead (`summary`) widoczny przed rozwinięciem,
   - 3 merytoryczne akapity rozwinięcia (`body`, oddzielone podwójnym znakiem nowej linii `\\n\\n`), wyjaśniające kontekst, przyczyny i konsekwencje,
   - krótkie angielskie zapytanie do wyszukiwarki zdjęć (`image_query`, 2–4 proste słowa po angielsku opisujące główny obiekt/miejsce, np. "mechanical watch movement", "tokyo bullet train", "solar farm desert"),
   - listę 1–2 konkretnych nazw mediów/instytucji źródłowych (`sources`, np. ["Reuters", "Financial Times"]).

STRUKTURA WYDANIA (łącznie 27 unikalnych artykułów):
- `top5`: dokładnie 5 najważniejszych i najistotniejszych wydarzeń ze świata (pierwszy z nich będzie artykułem głównym na pierwszej stronie).
- `interests`: dokładnie 4 pogłębione materiały dopasowane do poniższych zainteresowań czytelnika (wybierz najciekawsze aktualności z tych dziedzin):
{interests_bullet}
- `continents`: obiekt zawierający dokładnie 6 kluczy: "Europa", "Ameryka Północna", "Ameryka Południowa", "Azja", "Afryka", "Australia i Oceania". Pod każdym kontynentem umieść listę dokładnie 3 artykułów (nie skupiaj się wyłącznie na polityce — uwzględnij też gospodarkę, naukę, technologię, społeczeństwo i kulturę).

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
      "sources": ["Źródło 1", "Źródło 2"]
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
      "sources": ["Źródło 1"]
    }}
  ],
  "continents": {{
    "Europa": [ ... 3 artykuły ... ],
    "Ameryka Północna": [ ... 3 artykuły ... ],
    "Ameryka Południowa": [ ... 3 artykuły ... ],
    "Azja": [ ... 3 artykuły ... ],
    "Afryka": [ ... 3 artykuły ... ],
    "Australia i Oceania": [ ... 3 artykuły ... ]
  }}
}}
"""

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config={"tools": [{"google_search": {}}]},
    )

    edition = extract_json_payload(response.text)
    grounding_links = extract_grounding_sources(response)
    edition["grounding_links"] = grounding_links
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
        # Delikatny odstęp, aby nie przeciążać API Wikimedia
        time.sleep(0.25)

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
    edition = generate_newspaper_content(today_str)
    edition = enrich_with_images(edition)
    update_archive_index(today_str, edition)
    print(f"Sukces! Zapisano wydanie {edition_path} oraz zaktualizowano {INDEX_FILE}.")


if __name__ == "__main__":
    main()
