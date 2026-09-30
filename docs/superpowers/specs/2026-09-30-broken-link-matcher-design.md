# Broken Link Matcher – Design Spec

Datum: 2026-09-30
Status: Entwurf zur Freigabe
Kontext: Workflow-Tool für einen SEOKomm-Vortrag. Das Tool wird als offenes GitHub-Repo an die Zuhörer weitergegeben.

## 1. Ziel

Broken Link Building mit semantischem Matching. Das Tool nimmt die Broken Backlinks eines Wettbewerbers, rekonstruiert den Inhalt der toten Ziel-URLs über die Wayback Machine, embeddet diesen Inhalt und findet per Kosinus-Ähnlichkeit die drei passendsten URLs der eigenen Domain. Pro Treffer entsteht ein Mail-Entwurf an den Linkgeber. Zeilen ohne passende eigene URL werden als Content-Gap markiert.

Nicht-Ziele:

- Kein Mailversand, keine Kontaktdatensuche.
- Kein eigener Crawler für die eigene Domain. Embeddings der eigenen Domain kommen aus dem Screaming Frog.
- Keine Verarbeitung von mehr als einigen hundert Backlinks pro Lauf.

## 2. Architektur

Ein Python-Paket `blm` (broken link matcher) mit klar getrennten Modulen und eine Streamlit-Datei `app.py`, die ausschließlich Eingaben einsammelt, Module aufruft und Ergebnisse anzeigt. Kein Modul in `blm` importiert Streamlit. Alle HTTP-Zugriffe laufen über `httpx`, damit Tests sie mocken können.

Python 3.11 oder neuer. Auf dem Entwicklungsrechner ist nur Python 3.9 systemweit installiert, deshalb wird die Umgebung mit `uv` verwaltet (`uv python install 3.11`, `uv venv`, `uv pip install -r requirements.txt`). Die README dokumentiert beide Wege, `uv` und klassisches `pip` mit vorhandenem Python 3.11.

### 2.1 Internes Datenmodell

`BrokenBacklink` (dataclass):

| Feld | Typ | Bedeutung |
|---|---|---|
| url_from | str | Linkgebende URL |
| url_to | str | Tote Ziel-URL beim Wettbewerber |
| anchor | str | Ankertext |
| snippet_left | str | Text vor dem Link, leer wenn unbekannt |
| snippet_right | str | Text nach dem Link, leer wenn unbekannt |
| title_from | str | Titel der linkgebenden Seite, leer wenn unbekannt |
| domain_rating | float oder None | DR der linkgebenden Domain |
| url_rating | float oder None | UR der linkgebenden Seite |
| page_traffic | int oder None | Organischer Traffic der linkgebenden Seite |
| is_dofollow | bool oder None | None wenn die Quelle das Flag nicht liefert |
| is_content | bool oder None | Link steht im Hauptinhalt |
| http_code_target | int oder None | Statuscode der Ziel-URL laut Quelle |

`OwnPage`: url, vector (numpy float32).

`RecoveredContent`: url_to, text, source (`wayback`, `fallback`), snapshot_timestamp (str oder None), error (str oder None).

`MatchResult`: backlink, recovered, top (Liste aus bis zu drei Paaren url plus score), is_content_gap (bool), verification (`confirmed`, `fixed`, `unknown`, `skipped`), errors (Liste str).

### 2.2 Module

`blm/ingest/backlinks_csv.py`
Liest eine CSV oder XLSX und erzeugt `BrokenBacklink`-Objekte. Automatische Spaltenerkennung über zwei Namensschemata: die Spaltennamen des Ahrefs-UI-Exports und die Feldnamen der Ahrefs-API (identisch mit dem Ahrefs-MCP-Output). Die Zuordnung ist eine Tabelle Zielfeld → Liste bekannter Quellnamen, case-insensitiv. Kann eine Pflichtspalte (url_from, url_to) nicht erkannt werden, gibt das Modul die Liste der gefundenen Spalten zurück und die UI zeigt eine manuelle Zuordnungsmaske. Boolesche Spalten aus dem UI-Export (z. B. Nofollow als Ja/Nein oder leer/gefüllt) werden robust geparst; unbekannte Werte ergeben None.

`blm/ingest/ahrefs_api.py`
Optionaler Client für `GET https://api.ahrefs.com/v3/site-explorer/broken-backlinks`. Parameter: target, mode=subdomains, aggregation=1_per_domain, where mit is_dofollow=true und is_content=true, order_by=domain_rating_source:desc, limit aus der UI, select minimal: url_from, url_to, anchor, snippet_left, snippet_right, title, domain_rating_source, url_rating_source, http_code_target. Das Feld traffic (10 Units pro Zeile) wird nur bei aktivierter Option mit angefordert. Authentifizierung per Bearer-Token. Fehler der API (401, 403, 429, Unit-Limit) werden als lesbare Meldung nach oben gereicht.

`blm/ingest/frog_csv.py`
Liest den Embeddings-Export des Screaming Frog (CSV mit URL-Spalte und Vektor-Spalte, Vektor als Zahlenliste in einem Feld). Liefert eine Liste `OwnPage` und die Vektordimension. Zeilen mit leerem oder nicht parsebarem Vektor werden gezählt und übersprungen, nicht abgebrochen.

`blm/ranking.py`
Filtert und sortiert Backlinks. Filter (jeweils abschaltbar): nur Dofollow, nur Content-Links. Zeilen, deren Flag None ist, bleiben erhalten. Sortierung: domain_rating absteigend, dann page_traffic absteigend, None ans Ende. Danach Kappung auf die Obergrenze (Standard 100). Dedupliziert identische url_to mehrfach vorkommende Ziel-URLs nicht, denn jede linkgebende URL ist ein eigener Outreach-Kandidat; der Wayback-Abruf dedupliziert intern per Cache.

`blm/wayback.py`
Für eine url_to:
1. CDX-Abfrage: `https://web.archive.org/cdx/search/cdx?url=<url_to>&output=json&filter=statuscode:200&fl=timestamp,original&limit=-1`. Ergebnis ist der jüngste Snapshot mit Status 200. Es wird immer dieser jüngste Snapshot genommen, keine Wahl älterer Snapshots.
2. Abruf des Rohinhalts: `https://web.archive.org/web/<timestamp>id_/<original>`. Das Suffix `id_` liefert das Original-HTML ohne Wayback-Toolbar und ohne umgeschriebene Links.
3. Haupttext-Extraktion mit `trafilatura`. Liefert trafilatura nichts, Fallback auf den sichtbaren Text des body per BeautifulSoup. Text wird auf eine konfigurierbare Zeichenzahl gekürzt (Standard 12000 Zeichen), um Token-Limits der Embedding-Modelle einzuhalten.
4. Fallback ohne Snapshot oder ohne Text: Ersatztext aus title_from, anchor, snippet_left, snippet_right und dem lesbar gemachten URL-Pfad (Bindestriche und Slashes zu Leerzeichen). source=`fallback`.

Rate-Limit: sequentielle Abrufe mit einer Pause von 1 Sekunde zwischen Anfragen. Bei HTTP 429 oder 5xx bis zu drei Wiederholungen mit Pausen von 2, 4, 8 Sekunden. Danach Fallback mit error-Text. Ein einstellbarer User-Agent mit Kontakt-Hinweis wird gesendet.

`blm/embeddings/base.py`, `openai.py`, `gemini.py`, `ollama.py`
Gemeinsame Schnittstelle `EmbeddingProvider.embed(texts: list[str]) -> np.ndarray` mit Batching. Anbieter: OpenAI (Embeddings-API, Modellname frei wählbar, Vorgaben text-embedding-3-small, text-embedding-3-large), Gemini (Embeddings-API, Vorgaben gemini-embedding-001, text-embedding-004), Ollama (lokale HTTP-API, Modellname frei). Dimensionscheck: `provider.probe_dimension()` embeddet einen kurzen Probestring und gibt die Länge zurück. Stimmt sie nicht mit der Dimension der Frog-CSV überein, blockiert die UI das Matching und nennt beide Werte. Ein Tabellen-Hinweis in der UI erklärt, welches Frog-Setting welchem Anbieter entspricht.

`blm/matcher.py`
Normalisiert Eigen- und Wettbewerber-Vektoren auf Länge 1, berechnet die Ähnlichkeitsmatrix per Matrixprodukt, wählt pro Zeile die drei höchsten Scores. `is_content_gap` ist wahr, wenn der beste Score unter dem Schwellwert liegt. Schwellwert kommt aus der UI (Schieberegler 0.0 bis 1.0, Standard 0.5). Reine numpy-Funktion, keine IO.

`blm/verify.py`
Optional. Pro Zeile zwei Live-Prüfungen mit Timeout 10 Sekunden: GET auf url_to, Status 404 oder 410 gilt als weiterhin kaputt; GET auf url_from, prüft ob ein `<a href>` auf url_to (exakt oder ohne Protokoll und Trailing Slash) vorhanden ist. Ergebnis `confirmed` (kaputt und Link vorhanden), `fixed` (Ziel antwortet 2xx/3xx oder Link fehlt), `unknown` (Timeout oder Fehler). Pause 0.5 Sekunden zwischen Domains.

`blm/outreach.py`
Erzeugt einen Mail-Entwurf per Chat-Modell des gewählten Anbieters (OpenAI, Gemini oder Ollama, jeweils ein frei wählbarer Chat-Modellname mit Vorgabe). Prompt enthält: Sprache Deutsch, Länge maximal 120 Wörter, Absender-Name und eigene Domain aus der UI, url_from, anchor, snippet_left und snippet_right, url_to, Vorschlags-URL (Top 1) und deren Titel, wenn aus der Frog-CSV vorhanden, sonst URL-Slug. Tonalität: freundlich, konkret, keine Floskeln. Ausgabe ist reiner Text, editierbar im UI.

`blm/cache.py`
Datei-Cache im Projektordner `.cache/`, JSON pro Eintrag. Schlüssel für Wayback: SHA-256 der url_to. Schlüssel für Embeddings: SHA-256 aus Anbieter, Modellname und Text. Cache lässt sich in der UI leeren.

### 2.3 Streamlit-Oberfläche (`app.py`)

Sprache Deutsch. Seitenleiste: Embedding-Anbieter (Auswahl), Embedding-Modellname (Textfeld mit Vorgabe je Anbieter), API-Schlüssel oder Ollama-URL, Chat-Modellname für Outreach, optional Ahrefs-API-Schlüssel, Absender-Name und eigene Domain für den Mail-Entwurf, Knopf Cache leeren. Schlüssel werden nur im Session-State gehalten, nie auf Platte geschrieben; alternativ Übernahme aus Umgebungsvariablen und `st.secrets`.

Hauptbereich, fünf Abschnitte, jeder aktiviert sich erst, wenn der vorherige Ergebnisse hat:

1. Eigene Domain: Upload Frog-CSV. Anzeige: Anzahl URLs, Vektordimension, übersprungene Zeilen. Knopf Dimensionscheck, Ergebnis grün oder roter Blocker.
2. Wettbewerber-Backlinks: Tab CSV-Upload oder Tab Ahrefs-API (Domain, Limit, Traffic mitladen). Danach Spaltenzuordnung (nur sichtbar, wenn automatisch unvollständig), Filter-Schalter, Obergrenze, sortierte Vorschautabelle.
3. Wayback-Abruf: Startknopf, Fortschrittsbalken, danach Kennzahlen: Snapshots gefunden, Fallbacks, Fehler. Aufklappbare Vorschau des extrahierten Texts pro URL.
4. Matching: Schwellwert-Regler, Startknopf, Ergebnistabelle mit url_from, DR, url_to, Snapshot-Datum oder Fallback, Top 1 bis 3 mit Score, Content-Gap-Markierung. Content-Gap-Zeilen farblich hervorgehoben und als eigener Filter wählbar.
5. Verifikation und Outreach: Schalter Live-Check, Startknopf, Spalte Verifikation in der Tabelle. Export als CSV und XLSX. Pro Zeile ein Aufklapper mit Knopf Mail-Entwurf erzeugen, Ergebnis in einem editierbaren Textfeld.

Lange Läufe (Wayback, Embedding, Verifikation) zeigen Fortschritt und schreiben Zwischenergebnisse in den Session-State, damit ein Rerun von Streamlit nicht alles verwirft.

## 3. Ahrefs-Datenwege

Drei Wege, ein Zielformat:

1. CSV-Export aus der Ahrefs-Oberfläche (Site Explorer → Broken Backlinks → Export). Standardweg für Zuhörer.
2. Direkter API-Abruf im Tool mit eigenem Schlüssel (siehe `ahrefs_api.py`). Bonus, nicht Voraussetzung, weil API-Zugang planabhängig ist.
3. Im Vortrag: Claude ruft über den Ahrefs-MCP denselben Endpunkt auf und schreibt das Ergebnis als CSV; diese wird über Weg 1 hochgeladen. Die Spaltennamen entsprechen dem API-Schema, das der Parser kennt.

## 4. Fehlerbehandlung

- Wayback 429/5xx: drei Wiederholungen mit Backoff, dann Fallback-Text mit error.
- Kein Snapshot mit Status 200: Fallback-Text, source=`fallback`.
- Leere Extraktion: Fallback-Text.
- Dimensionsabweichung: Matching blockiert, Meldung mit beiden Werten und Hinweis auf Frog-Einstellung.
- Fehlender Schlüssel: betroffener Abschnitt deaktiviert mit Hinweis.
- Ahrefs-API-Fehler: Meldung mit Statuscode und Antworttext, Hinweis auf CSV-Weg.
- Live-Check Timeout oder Ausnahme: verification=`unknown`.
- Embedding-API-Fehler für einen Batch: Batch wird in kleinere Teile zerlegt und wiederholt; bleibt ein Text fehlerhaft, bekommt die Zeile einen error und kein Matching.
- Jede Zeile trägt ihre Fehler in `errors`; die Exporttabelle enthält eine Spalte Fehler. Nichts geht stumm verloren.

## 5. Tests

Pytest, kein Netzwerkzugriff in Tests, HTTP über `respx` gemockt.

- `tests/fixtures/`: Ahrefs-UI-Export (klein, anonymisiert), Ahrefs-API-Export im MCP-Format, Frog-Embeddings-CSV mit drei URLs und Dimension 8, CDX-JSON-Antwort, archiviertes Beispiel-HTML, Beispiel-HTML einer linkgebenden Seite mit und ohne Link.
- `backlinks_csv`: beide Namensschemata, fehlende Pflichtspalte liefert Zuordnungsbedarf, boolesche Werte in allen Schreibweisen.
- `frog_csv`: Dimension korrekt erkannt, defekte Zeile wird übersprungen und gezählt.
- `ranking`: Filter- und Sortierlogik inklusive None-Werte und Kappung.
- `wayback`: jüngster 200er-Snapshot wird gewählt, `id_`-URL korrekt gebaut, Retry bei 429, Fallback-Text bei leerem CDX-Ergebnis, Textkürzung.
- `embeddings`: jeder Anbieter parst seine gemockte Antwort korrekt, Batching, probe_dimension.
- `matcher`: synthetische Vektoren mit bekanntem Ergebnis, Top 3 Reihenfolge, Content-Gap-Schwelle, Normalisierung.
- `verify`: alle drei Ergebniszustände.
- `outreach`: Prompt enthält alle Pflichtfelder, gemockte Antwort wird durchgereicht.
- `cache`: Schreiben, Lesen, Leeren, Schlüsselunterschied bei anderem Modell.
- `app.py`: ein Rauchtest mit `streamlit.testing.v1.AppTest`, der die App lädt und prüft, dass die fünf Abschnitte gerendert werden.

## 6. Repo-Struktur

```
broken-link-matcher/
  app.py
  blm/
    __init__.py
    models.py
    ranking.py
    wayback.py
    matcher.py
    verify.py
    outreach.py
    cache.py
    ingest/
      __init__.py
      backlinks_csv.py
      ahrefs_api.py
      frog_csv.py
    embeddings/
      __init__.py
      base.py
      openai.py
      gemini.py
      ollama.py
  tests/
    fixtures/
    test_*.py
  docs/superpowers/specs/
  .streamlit/config.toml
  requirements.txt
  README.md
  .gitignore   (.cache/, .venv/, secrets)
```

Abhängigkeiten: streamlit, httpx, respx (nur Tests), pandas, numpy, trafilatura, beautifulsoup4, openpyxl, pytest. Anbieter-SDKs werden nicht verwendet; alle drei Embedding- und Chat-Anbieter werden über ihre HTTP-APIs mit httpx angesprochen, damit die Abhängigkeitsliste klein bleibt und Tests einheitlich mocken.

README auf Deutsch mit englischer Kurzfassung: Zweck, Installation mit uv und pip, Frog-Einstellungen für den Embeddings-Export, Ahrefs-Exportweg, Schlüssel, Ablauf der fünf Schritte, Hinweise zu API-Kosten und Wayback-Etikette, Deployment auf Streamlit Community Cloud mit `st.secrets`.

## 7. Offene Annahmen

- Die exakten Spaltennamen des Ahrefs-UI-Exports und des Frog-Embeddings-Exports werden beim Implementieren an echten Exportdateien verifiziert; die Zuordnungstabelle ist bewusst erweiterbar.
- Die Score-Verteilung unterscheidet sich je Modell; der Standard-Schwellwert 0.5 ist ein Startwert, den die README zur Kalibrierung an eigenen Daten empfiehlt.
