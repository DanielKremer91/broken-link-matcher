# Broken Link Matcher

Broken Link Building mit semantischem Matching. Das Tool nimmt die Broken Backlinks eines Wettbewerbers, holt den Inhalt der toten Seiten aus der Wayback Machine, embeddet ihn und findet per Kosinus-Ähnlichkeit die drei passendsten Seiten deiner Domain. Pro Treffer entsteht ein Mail-Entwurf an den Linkgeber. Tote Seiten ohne passendes Pendant werden als Content-Gap markiert.

Vorgestellt auf der SEOKomm 2026.

## Ablauf

Die App ist in fünf Abschnitte gegliedert, die du von oben nach unten durchgehst:

1. Eigene Domain: Screaming-Frog-Crawl mit Embeddings, Export hochladen, Dimensionscheck gegen das gewählte Modell.
2. Wettbewerber-Backlinks: Ahrefs-Export hochladen (CSV oder XLSX) oder per Ahrefs-API laden, filtern, nach Linkwert sortieren.
3. Wayback-Abruf: jüngster Snapshot mit Status 200 pro toter URL, Haupttext-Extraktion. Ohne Snapshot: Fallback aus Anker, Kontext, Titel und URL-Pfad, also ausschließlich aus Feldern, die Ahrefs bereits geliefert hat. Es wird nie Text generiert.
4. Matching: Embeddings mit demselben Modell wie im Frog, Top 3 pro URL, Content-Gap unter dem Schwellwert.
5. Verifikation und Outreach: Live-Check (Ziel noch 404? Link noch da?), Export als CSV oder Excel, Mail-Entwurf pro Treffer.

## Installation

Mit uv (empfohlen, holt Python 3.11 selbst):

```bash
uv python install 3.11
uv venv --python 3.11 .venv
source .venv/bin/activate
uv pip install -r requirements.txt
streamlit run app.py
```

Mit vorhandenem Python 3.11+:

```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

## Screaming Frog vorbereiten

- Richte im Screaming Frog einen Embeddings-Anbieter ein (OpenAI, Gemini oder Ollama) und wähle ein Embedding-Modell. In der aktuellen Frog-Version findest du das unter Configuration → API Access bzw. im Embeddings-Feature. Die genauen Menüpunkte unterscheiden sich je nach Version, maßgeblich ist die Frog-Dokumentation.
- Crawle deine Domain und exportiere die Embeddings als CSV.
- Erwartetes Layout (geprüft gegen Screaming Frog 24.3): eine Spalte `url`, danach `embedding_0 … embedding_N` mit je einem Wert pro Spalte. Zusätzlich akzeptiert das Tool eine Spalte `Address` als URL und eine einzelne Spalte mit einer Vektorliste wie `[0.1, 0.2, …]`. Eine Titelspalte (`title`) wird, falls vorhanden, für die Mail-Entwürfe genutzt.
- Merke dir Anbieter und Modellnamen. In der Seitenleiste musst du exakt dieselben wählen, sonst liegen die Vektoren in unterschiedlichen Räumen. Der Dimensionscheck fängt Abweichungen in der Vektorlänge ab, erkennt aber nicht jeden Modellwechsel mit gleicher Dimension.
- Das Tool normalisiert alle Vektoren vor dem Vergleich, die Kosinus-Ähnlichkeit hängt also nicht von der Vektorlänge ab.

## Ahrefs-Daten

- Export aus der Ahrefs-Oberfläche: Im Site Explorer den Bericht zu den Broken Backlinks der Wettbewerber-Domain öffnen (Bezeichnung und Menüpfad können je nach Ahrefs-Version abweichen), Filter Dofollow setzen, nach DR sortieren, als CSV exportieren.
- Der UI-Export kann UTF-16 kodiert sein. Das Tool liest UTF-8, UTF-16 (mit BOM) und Windows-1252 sowie Komma, Semikolon, Tab und Pipe als Trennzeichen automatisch.
- Alternativ Ahrefs-API v3 (planabhängig): Schlüssel in der Seitenleiste eintragen, Wettbewerber-Domain und maximale Zeilenzahl (Standard 100) angeben. Abgerufen werden Dofollow-Content-Links, ein Link pro verweisender Domain, absteigend nach Domain Rating. Jede Zeile kostet API-Units; Seitentraffic kostet 10 Units extra pro Zeile und ist deshalb optional.
- Andere Tools: Export (CSV oder XLSX) hochladen und die Spalten manuell zuordnen. Pflichtfelder sind verlinkende URL und tote Ziel-URL.
- Falls Spalten nicht erkannt werden, per Zuordnungsmaske zuweisen und gerne ein Issue mit den Spaltennamen eröffnen.
- Filter in der App: Nur Dofollow (Standard an), Nur Content-Links (Standard an), Mindest-DR, Sortierung nach Domain Rating, URL Rating oder Seitentraffic, Obergrenze (Standard 100).

## Schlüssel

Über die Seitenleiste, Umgebungsvariablen (`OPENAI_API_KEY`, `GEMINI_API_KEY`, `AHREFS_API_KEY`) oder `.streamlit/secrets.toml` (Vorlage: `.streamlit/secrets.example.toml`). Die Umgebungsvariable hat Vorrang vor der Secrets-Datei. Schlüssel werden nie auf Platte geschrieben. Ollama läuft lokal und braucht keinen Schlüssel, nur die URL (Standard `http://localhost:11434`).

Dieselben Anbieter erzeugen auch die Mail-Entwürfe (Chat-Modell in der Seitenleiste einstellbar). Die Entwürfe sind der einzige generierte Text im Tool, sie sind editierbar und gehören vor dem Versand geprüft.

## Kosten und Etikette

- Wayback Machine: pro tote URL zwei Anfragen (CDX-Abfrage nach dem jüngsten Snapshot mit Status 200, danach der Rohdaten-Abruf über das `id_`-Flag, also ohne Wayback-Toolbar), mit einer Sekunde Pause zwischen den URLs. Bei Fehlern, Status 429 und 5xx wird mit Backoff (2, 4, 8 Sekunden) wiederholt. Bitte nicht parallelisieren. Bereits geholte Seiten kommen aus dem Cache und kosten keine Pause.
- Embeddings: pro toter URL ein Text von maximal 12000 Zeichen (in Abschnitt 3 einstellbar, 1000 bis 50000). Wayback-Texte und Embeddings werden in `.cache/` neben `app.py` gespeichert; in der Seitenleiste leert "Cache leeren" das Verzeichnis.
- Schwellwert: 0,5 ist ein Startwert. Die Score-Verteilung hängt vom Modell ab; an eigenen Daten kalibrieren.
- Export: Die CSV nutzt Semikolon als Trennzeichen und Dezimalkomma, damit sie in deutschem Excel direkt sauber öffnet. Die Excel-Datei enthält dieselben Spalten im Blatt "Treffer".

## Deployment auf Streamlit Community Cloud

Repo verbinden, `app.py` als Einstieg, Schlüssel unter App Settings → Secrets im TOML-Format hinterlegen (gleiche Namen wie in `.streamlit/secrets.example.toml`). Der Cache ist dort flüchtig.

## Tests

```bash
pytest -q
```

Die Suite umfasst 190 Tests und läuft ohne Netzwerkzugriff; HTTP wird mit respx gemockt.

## English summary

Broken link building with semantic matching: pull a competitor's broken backlinks (Ahrefs export or API), recover the dead pages from the Wayback Machine (newest 200 snapshot via the CDX API, raw HTML via `id_`), embed with the same model your Screaming Frog used for your own site, rank your top 3 matching URLs by cosine similarity, flag content gaps, verify live, export (semicolon CSV with decimal comma, or XLSX), and draft outreach mails. Pages without a snapshot fall back to a plain concatenation of Ahrefs fields; nothing is generated except the editable mail drafts. The Ahrefs UI export may be UTF-16; the reader handles UTF-8, UTF-16 with BOM and Windows-1252. If columns are not recognised, map them in the UI and feel free to open an issue with the column names. Python 3.11+, Streamlit, no provider SDKs, 190 tests, all mocked.
