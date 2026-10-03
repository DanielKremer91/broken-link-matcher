# Broken Link Matcher

Broken Link Building mit semantischem Matching. Das Tool nimmt die Broken Backlinks eines Wettbewerbers, holt den Inhalt der toten Seiten aus der Wayback Machine, embeddet ihn und findet per Kosinus-Ähnlichkeit die drei passendsten Seiten deiner Domain. Pro Treffer entsteht ein Mail-Entwurf an den Linkgeber. Tote Seiten ohne passendes Pendant werden als Content-Gap markiert.

Vorgestellt auf der SEOKomm 2026.

## Schnellstart: monatlicher Monitor mit Claude

Öffne die Claude-Desktop-App, Bereich Code, in einem beliebigen Ordner und schreib:

```
Richte mir den Broken Link Monitor ein. Klone dazu https://github.com/DanielKremer91/broken-link-matcher und folge der Anleitung für Claude in der README.
```

Claude klont das Repo, stellt dir ein paar Fragen und führt dich Schritt für Schritt durch die Einrichtung bis zum ersten Lauf. Was du dafür brauchst, steht in der [Checkliste](docs/checkliste.md).

> **Anleitung für Claude:** Soll der Broken Link Monitor eingerichtet werden, folge `.claude/skills/broken-link-monitor/EINRICHTUNG.md` in diesem Repo. Für einen Lauf gilt `.claude/skills/broken-link-monitor/SKILL.md`.

## Ablauf

Die App ist in fünf Abschnitte gegliedert, die du von oben nach unten durchgehst:

1. Eigene Domain: Screaming-Frog-Crawl mit Embeddings, Export hochladen, Dimensionscheck gegen das gewählte Modell.
2. Wettbewerber-Backlinks: Ahrefs-Export hochladen (CSV oder XLSX) oder per Ahrefs-API laden, filtern, nach Linkwert sortieren.
3. Wayback-Abruf: jüngster Snapshot mit Status 200 pro toter URL, Haupttext-Extraktion. Ohne Snapshot: Fallback aus Anker, Kontext, Titel und URL-Pfad, also ausschließlich aus Feldern, die Ahrefs bereits geliefert hat. Es wird nie Text generiert.
4. Matching: Embeddings mit demselben Modell wie im Frog, Top 3 pro URL, Content-Gap unter dem Schwellwert.
5. Verifikation und Outreach: Live-Check (Ziel noch 404? Link noch da?), Export als CSV oder Excel, Mail-Entwurf pro Treffer.

Sind Frog-Export, Backlinks und API-Schlüssel da, führt "Los geht's" den Dimensionscheck aus Schritt 1 sowie die Schritte 3 und 4 in einem Durchlauf aus. Die einzelnen Buttons bleiben für erneute Läufe erhalten.

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

Unter Windows lautet die Aktivierung `.venv\Scripts\activate` statt `source .venv/bin/activate`.

`requirements.txt` enthält nur die Laufzeit-Abhängigkeiten. Für die Tests zusätzlich `requirements-dev.txt` installieren (siehe Abschnitt Tests).

## Screaming Frog vorbereiten

- Richte im Screaming Frog einen Embeddings-Anbieter ein (OpenAI, Gemini oder Ollama) und wähle ein Embedding-Modell. In der aktuellen Frog-Version findest du das unter Configuration → API Access bzw. im Embeddings-Feature. Die genauen Menüpunkte unterscheiden sich je nach Version, maßgeblich ist die Frog-Dokumentation.
- Crawle deine Domain und exportiere die Embeddings als CSV.
- Akzeptierte Formate: CSV, TSV oder TXT (UTF-8, UTF-16 (mit BOM) oder Windows-1252, Trennzeichen Komma, Semikolon, Tab oder Pipe) sowie XLSX. Öffne den Export nicht in Excel, um ihn wieder als CSV zu speichern: Excel kürzt Zellen mit mehr als 32767 Zeichen, solche Zeilen werden übersprungen. Erkennt das Tool die Spalten nicht, kannst du URL- und Embedding-Spalte in der App selbst zuordnen.
- Erwartetes Layout (geprüft gegen Screaming Frog 24.3): eine Spalte `url`, danach `embedding_0 … embedding_N` mit je einem Wert pro Spalte. Zusätzlich akzeptiert das Tool eine Spalte `Address` als URL und eine einzelne Spalte mit einer Vektorliste wie `[0.1, 0.2, …]`. Eine Titelspalte (`title`) wird, falls vorhanden, für die Mail-Entwürfe genutzt.
- Merke dir Anbieter und Modellnamen (Hilfe im Abschnitt 1 der App: "Welches Modell habe ich im Frog?"). In der Seitenleiste musst du exakt dieselben wählen, sonst liegen die Vektoren in unterschiedlichen Räumen. Der Dimensionscheck fängt Abweichungen in der Vektorlänge ab, erkennt aber nicht jeden Modellwechsel mit gleicher Dimension.
- Das Tool normalisiert alle Vektoren vor dem Vergleich, die Kosinus-Ähnlichkeit hängt also nicht von der Vektorlänge ab.

## Ahrefs-Daten

- Export aus der Ahrefs-Oberfläche: Im Site Explorer den Bericht zu den Broken Backlinks der Wettbewerber-Domain öffnen (Bezeichnung und Menüpfad können je nach Ahrefs-Version abweichen), Filter Dofollow setzen, nach DR sortieren, als CSV exportieren.
- Der UI-Export kann UTF-16 kodiert sein. Das Tool liest CSV, TSV und TXT in UTF-8, UTF-16 (mit BOM) und Windows-1252 sowie Komma, Semikolon, Tab und Pipe als Trennzeichen automatisch, außerdem XLSX (erstes Blatt).
- Speichere den Export nicht mit Excel als CSV: Excel macht aus Dezimalwerten wie 4.6 Datumsangaben wie "04. Jun". Das Tool rechnet solche Werte zurück und zeigt an, wie viele es waren.
- Alternativ Ahrefs-API v3 (planabhängig): Schlüssel in der Seitenleiste eintragen, Wettbewerber-Domain und maximale Zeilenzahl (Standard 100) angeben. Abgerufen werden Dofollow-Content-Links, ein Link pro verweisender Domain, absteigend nach Domain Rating. Jede Zeile kostet API-Units; Seitentraffic kostet 10 Units extra pro Zeile und ist deshalb optional. Im Tab "Ahrefs-API" lassen sich die serverseitigen Filter einzeln setzen (Dofollow, Content-Links, Spam ausschließen, nur 404/410, Mindest-DR); Units fallen pro zurückgegebener Zeile an.
- Andere Tools: Export (CSV oder XLSX) hochladen und die Spalten manuell zuordnen. Pflichtfelder sind verlinkende URL und tote Ziel-URL.
- Falls Spalten nicht erkannt werden, per Zuordnungsmaske zuweisen und gerne ein Issue mit den Spaltennamen eröffnen.
- Filter in der App: Nur Dofollow (Standard an), Nur Content-Links (Standard an), Mindest-DR, Sortierung nach Domain Rating, URL Rating oder Seitentraffic, Obergrenze (Standard 100).

## Schlüssel

Über die Seitenleiste, Umgebungsvariablen (`OPENAI_API_KEY`, `GEMINI_API_KEY`, `AHREFS_API_KEY`) oder `.streamlit/secrets.toml` (Vorlage: `.streamlit/secrets.example.toml`). Die Umgebungsvariable hat Vorrang vor der Secrets-Datei. Schlüssel werden nie auf Platte geschrieben. Ollama läuft lokal und braucht keinen Schlüssel, nur die URL (Standard `http://localhost:11434`).

Schlüssel aus Secrets oder Umgebung werden nie in die Eingabefelder übernommen; die Seitenleiste zeigt dann "Schlüssel aus Secrets/Umgebung aktiv". Ein eingetippter Schlüssel hat Vorrang. Ohne Schlüssel (OpenAI, Gemini) sind Dimensionscheck und Mail-Entwürfe gesperrt.

Dieselben Anbieter erzeugen auch die Mail-Entwürfe (Chat-Modell in der Seitenleiste einstellbar). Dafür müssen Name und Domain in der Seitenleiste eingetragen sein; für Content-Gap-Zeilen gibt es keinen Entwurf. Die Entwürfe sind der einzige generierte Text im Tool, sie sind editierbar und gehören vor dem Versand geprüft.

## Kosten und Etikette

- Wayback Machine: pro tote URL zwei Anfragen (CDX-Abfrage nach dem jüngsten Snapshot mit Status 200, danach der Rohdaten-Abruf über das `id_`-Flag, also ohne Wayback-Toolbar), mit einer Sekunde Pause zwischen den beiden Anfragen und einer Sekunde Pause zwischen den URLs. Bei Fehlern, Status 429 und 5xx wird mit Backoff (2, 4, 8 Sekunden) wiederholt. Bitte nicht parallelisieren. Bereits geholte Seiten kommen aus dem Cache und kosten keine Pause.
- User-Agent: Wayback-Abruf und Live-Check senden `broken-link-matcher/0.1 (…)`. Trag in der Seitenleiste unter "Kontakt für User-Agent" eine E-Mail-Adresse oder URL ein, dann wird sie mitgeschickt und Betreiber können dich erreichen.
- Embeddings: pro toter URL ein Text von maximal 12000 Zeichen (in Abschnitt 3 einstellbar, 1000 bis 50000). Gleiche Texte werden nur einmal eingebettet. Bei Status 429, 5xx und Zeitüberschreitungen wird bis zu dreimal wiederholt (2, 4, 8 Sekunden, ein numerischer Retry-After-Header wird bis 30 Sekunden beachtet). Fertige Batches landen sofort im Cache, ein Abbruch verliert also nur den laufenden Batch.
- Cache: Wayback-Texte (bis 50000 Zeichen, gekürzt auf die eingestellte Länge) und Embeddings werden in `.cache/` neben `app.py` gespeichert; "Cache leeren" in der Seitenleiste löscht die gespeicherten Einträge.
- Live-Check: "confirmed" heißt, das Ziel antwortet noch mit 404 oder 410 und die verlinkende Seite enthält den Link noch. Leitet das Ziel inzwischen auf eine erreichbare Seite weiter oder ist der Link entfernt, gilt die Zeile als "fixed". Nicht eindeutige Antworten (Netzwerkfehler, 403, 429, 5xx, fehlerhafte URLs) ergeben "unknown".
- Schwellwert: 0,5 ist ein Startwert. Die Score-Verteilung hängt vom Modell ab; an eigenen Daten kalibrieren.
- Export: Die CSV nutzt Semikolon als Trennzeichen und Dezimalkomma, damit sie in deutschem Excel direkt sauber öffnet. Die Excel-Datei enthält dieselben Spalten im Blatt "Treffer".

## Deployment auf Streamlit Community Cloud

Repo verbinden, `app.py` als Einstieg, Schlüssel unter App Settings → Secrets im TOML-Format hinterlegen (gleiche Namen wie in `.streamlit/secrets.example.toml`). Streamlit Cloud installiert `requirements.txt`, also nur die Laufzeit-Abhängigkeiten; `requirements-dev.txt` wird dort nicht gebraucht. Der Cache ist dort flüchtig.

### Öffentliches Deployment

Schlüssel aus Secrets oder Umgebungsvariablen werden nie in die Eingabefelder vorbefüllt und gelangen so nicht in den Browser; die Seitenleiste zeigt nur "Schlüssel aus Secrets/Umgebung aktiv". Trotzdem gilt: Eine öffentliche Cloud-App mit Schlüsseln in den Secrets lässt jeden Besucher das Kontingent des Betreibers verbrauchen (Embeddings, Mail-Entwürfe, Ahrefs-Units). Deploye die App deshalb privat (Zugriff nur für eingeladene Nutzer) oder lass die Secrets leer, damit jeder Nutzer seinen eigenen Schlüssel einträgt. Der Cache (`.cache/`) wird von allen Besuchern geteilt, und "Cache leeren" löscht ihn für alle. Das Feld Ollama-URL ist für lokale Installationen gedacht und sollte auf einem öffentlichen Deployment nicht genutzt werden, weil der Server dann Anfragen an beliebige vom Besucher eingetragene Adressen schickt.

## Agentischer Weg (Claude Code / Terminal)

`cli.py` führt denselben Workflow ohne Oberfläche aus. Claude Code kann so die Eingaben über den Screaming-Frog-MCP und den Ahrefs-MCP holen, das Tool aufrufen und die Ergebnisse auswerten.

```bash
export OPENAI_API_KEY=...   # Schlüssel nur über die Umgebung, nie als Argument
.venv/bin/python cli.py --frog frog-embeddings.csv --backlinks broken-backlinks-konkurrent.csv \
  --provider openai --model text-embedding-3-small --out ergebnis.xlsx --verify --json
```

Mit `--drafts` landen die Mail-Entwürfe standardmäßig in `<Name von --out>-entwuerfe.md` neben der Ergebnisdatei (änderbar mit `--drafts-out`). Exit-Code 0 bei Erfolg, 1 bei Laufzeitfehlern, 2 bei ungültigen Argumenten. App und CLI teilen sich den Cache-Ordner `.cache/`. Prompt, Voraussetzungen und die vollständige Optionsliste stehen in [docs/agentic-workflow.md](docs/agentic-workflow.md).

## Monatlicher Monitor (Claude-Skill)

Der Skill `broken-link-monitor` in `.claude/skills/` macht aus dem agentischen Weg einen monatlichen Lauf: Frog-Crawl mit Embeddings und Ahrefs-Abfrage über die MCPs, Matching mit `cli.py`, Abgleich mit dem Vormonat und Bericht per Resend, Mail-Connector oder als Datei. Der Bericht listet jeden Monat alle offenen Chancen, neue zuerst, bereits gemeldete mit dem Monat ihrer ersten Meldung.

- Anleitung: [docs/monatlicher-workflow.md](docs/monatlicher-workflow.md)
- Checkliste zum Abhaken: [docs/checkliste.md](docs/checkliste.md)
- Einrichtung prüfen: `.venv/bin/python check_setup.py`
- Ahrefs-Parameter ansehen: `.venv/bin/python ahrefs_params.py --target konkurrent.de`
- Später etwas ändern, zum Beispiel einen Wettbewerber aufnehmen: in der Claude-App eine Sitzung im Repo-Ordner starten, also dem Ordner, in den die Einrichtung alles geklont hat (Standard `~/broken-link-matcher`), und sagen "Nimm zooplus.de als weiteren Wettbewerber in den Broken Link Monitor auf". Details in der [Anleitung](docs/monatlicher-workflow.md#später-etwas-ändern).
- Vorlage für das Frog-Snippet (Hauptinhalt plus Embedding): [frog/main-content-embedding.js](frog/main-content-embedding.js)

## Tests

```bash
pip install -r requirements-dev.txt   # bzw. uv pip install -r requirements-dev.txt
pytest -q
```

Alle Tests laufen ohne Netzwerkzugriff; HTTP wird mit respx gemockt.

## English summary

Broken link building with semantic matching: pull a competitor's broken backlinks (Ahrefs export or API), recover the dead pages from the Wayback Machine (newest 200 snapshot via the CDX API, raw HTML via `id_`), embed with the same model your Screaming Frog used for your own site, rank your top 3 matching URLs by cosine similarity, flag content gaps, verify live, export (semicolon CSV with decimal comma, or XLSX), and draft outreach mails. Pages without a snapshot fall back to a plain concatenation of Ahrefs fields; nothing is generated except the editable mail drafts. The Ahrefs UI export may be UTF-16; the reader handles UTF-8, UTF-16 with BOM and Windows-1252. If columns are not recognised, map them in the UI and feel free to open an issue with the column names. Python 3.11+, Streamlit, no provider SDKs; install `requirements-dev.txt` to run the tests, which are fully mocked. A command-line entry point, `cli.py`, runs the same pipeline headlessly so an agent such as Claude Code can drive it. Keys are read from environment variables only; see `docs/agentic-workflow.md`.
