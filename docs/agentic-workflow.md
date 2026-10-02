# Agentischer Weg: Claude Code steuert den Workflow

Dieselbe Pipeline wie in der Streamlit-App, aber ohne Oberfläche. Claude Code holt die Eingaben über die MCP-Server von Screaming Frog und Ahrefs, ruft `cli.py` auf, liest die Zusammenfassung und wertet die Ergebnisdatei aus. `cli.py` nutzt dieselben Module wie die App (Ingest, Ranking, Wayback, Embeddings, Matching, Verifikation, Mail-Entwürfe) und teilt sich den Cache-Ordner `.cache/` mit ihr.

## Voraussetzungen

- Claude Code läuft im Ordner dieses Repos, die virtuelle Umgebung ist installiert (`.venv`, siehe README).
- Screaming Frog MCP und Ahrefs MCP sind verbunden (zum Ahrefs-MCP siehe [ahrefs-mcp.md](ahrefs-mcp.md)).
- Eine Screaming-Frog-Konfigurationsdatei (`.seospiderconfig`) mit aktivierten Embeddings existiert. Speichere sie einmal in der Frog-Oberfläche (Embeddings-Anbieter und Modell einrichten, dann Configuration → Save As). Der MCP kann Embeddings nicht selbst konfigurieren, er nutzt die gespeicherte Datei.
- Der Schlüssel für den Embedding-Anbieter ist in der Shell exportiert, die Claude Code startet, zum Beispiel `export OPENAI_API_KEY=...` (oder `GEMINI_API_KEY`; Ollama braucht nur optional `OLLAMA_URL`).

## Der Prompt

```
Führe den Broken-Link-Workflow für meine Domain meine-domain.de gegen den Wettbewerber konkurrent.de aus:

1. Screaming Frog MCP: lade den letzten Crawl von meine-domain.de (oder starte einen Crawl mit der Konfiguration /Pfad/zu/embeddings.seospiderconfig) und exportiere die Embeddings als CSV nach frog-embeddings.csv.
2. Ahrefs MCP: hol die Broken Backlinks von konkurrent.de (mode subdomains, aggregation 1_per_domain, nur is_dofollow=true und is_content=true, sortiert nach domain_rating_source absteigend, limit 100, output csv, select url_from,url_to,anchor,snippet_left,snippet_right,title,domain_rating_source,url_rating_source,http_code_target,is_dofollow,is_content) und speichere sie als broken-backlinks-konkurrent.csv.
3. Führe aus: .venv/bin/python cli.py --frog <Pfad aus Schritt 1> --backlinks broken-backlinks-konkurrent.csv --provider openai --model text-embedding-3-small --out ergebnis.xlsx --verify --json
4. Lies die JSON-Zusammenfassung und die ersten Zeilen der Excel-Datei und sag mir, welche fünf Linkgeber ich zuerst anschreiben sollte und warum. Content-Gaps bitte separat auflisten.
```

Anbieter und Modell müssen exakt zu der Frog-Konfiguration passen, sonst bricht der Dimensionscheck ab oder die Vektoren liegen in unterschiedlichen Räumen.

## Wohin der Frog-MCP schreibt

Der Screaming-Frog-MCP schreibt Exporte nur in sein erlaubtes Basisverzeichnis. Den Pfad meldet der MCP selbst (Tool zum Auflisten des erlaubten Verzeichnisses). `cli.py` akzeptiert absolute Pfade, deshalb reicht es, wenn Claude den vom MCP gemeldeten Pfad der Embeddings-CSV als `--frog` übergibt. Die Ahrefs-CSV liegt dagegen im Arbeitsordner und wird relativ angegeben.

## Mit Mail-Entwürfen

Hänge diese Optionen an den Aufruf aus Schritt 3 an:

```
--drafts --sender "Name" --domain meine-domain.de --drafts-out entwuerfe.md
```

Die Entwürfe landen als Markdown in `entwuerfe.md` (pro Backlink ein Abschnitt mit toter URL und Text). Es gibt keinen Entwurf für Content-Gap-Zeilen. Der Chat-Anbieter ist derselbe wie beim Embedding; das Modell lässt sich mit `--chat-model` ändern. Die Entwürfe gehören vor dem Versand geprüft. Ohne `--drafts-out` schreibt `cli.py` die Entwürfe nach `<Name von --out>-entwuerfe.md` neben die Ergebnisdatei (bei `--out ergebnis.xlsx` also `ergebnis-entwuerfe.md`).

## Was Claude danach tun soll

Lies die JSON-Zusammenfassung auf stdout, öffne die XLSX-Datei und liste die fünf wichtigsten Linkgeber (hoher Domain Rating, starker Treffer, Verifikation "confirmed", also Ziel noch tot und Link noch vorhanden; "fixed" heißt, die tote URL antwortet wieder oder die verlinkende Seite verlinkt nicht mehr darauf; beides lohnt keinen Outreach mehr) mit je einem Satz Begründung. Führe die Content-Gaps in einer eigenen Liste auf: das sind tote URLs, zu denen deine Seite thematisch nichts Passendes hat. Dort lohnt neuer Content statt einer Umleitung.

## CLI-Referenz

Ausgabe von `.venv/bin/python cli.py --help`:

```text
usage: cli.py [-h] --frog FROG --backlinks BACKLINKS [--provider {openai,gemini,ollama}]
              [--model MODEL] --out OUT [--limit LIMIT] [--min-dr MIN_DR]
              [--sort {domain_rating,url_rating,page_traffic}] [--all-links]
              [--threshold THRESHOLD] [--no-fallback] [--max-chars MAX_CHARS] [--pause PAUSE]
              [--contact CONTACT] [--verify] [--drafts] [--sender SENDER] [--domain DOMAIN]
              [--chat-model CHAT_MODEL] [--drafts-out DRAFTS_OUT] [--cache-dir CACHE_DIR]
              [--seen-file SEEN_FILE] [--report REPORT] [--competitor COMPETITOR]
              [--env-file ENV_FILE] [--json] [--quiet]

Broken Link Matcher: tote Wettbewerber-URLs mit eigenen Seiten matchen (ohne Oberfläche).

options:
  -h, --help            show this help message and exit
  --frog FROG           Screaming-Frog-Embeddings-Export (CSV/TSV/TXT/XLSX)
  --backlinks BACKLINKS
                        Broken-Backlinks-Export (CSV/TSV/TXT/XLSX)
  --provider {openai,gemini,ollama}
                        Embedding-Anbieter wie im Frog
  --model MODEL         Embedding-Modell wie im Frog (Standard je Anbieter)
  --out OUT             Ergebnisdatei .xlsx oder .csv
  --limit LIMIT
  --min-dr MIN_DR
  --sort {domain_rating,url_rating,page_traffic}
  --all-links           auch Nofollow- und Nicht-Content-Links
  --threshold THRESHOLD
                        Content-Gap unterhalb dieses Scores
  --no-fallback         Zeilen ohne Snapshot nicht matchen
  --max-chars MAX_CHARS
  --pause PAUSE         Sekunden Pause nach jedem Wayback-Abruf
  --contact CONTACT     Kontakt (Mail oder URL) für den User-Agent
  --verify              Live prüfen: Ziel noch 404, Link noch vorhanden
  --drafts              Mail-Entwürfe erzeugen (braucht --sender und --domain)
  --sender SENDER       Absender-Name für Mail-Entwürfe
  --domain DOMAIN       eigene Domain für Mail-Entwürfe
  --chat-model CHAT_MODEL
                        Chat-Modell für Entwürfe (Standard je Anbieter)
  --drafts-out DRAFTS_OUT
                        Markdown-Datei für die Mail-Entwürfe (Standard: <Name von
                        --out>-entwuerfe.md neben --out)
  --cache-dir CACHE_DIR
  --seen-file SEEN_FILE
                        Verlaufsdatei (JSON): markiert neue Zeilen und merkt sich alle gemeldeten
  --report REPORT       Bericht als .md oder .txt, dazu eine .html-Datei daneben
  --competitor COMPETITOR
                        Name des Wettbewerbers im Bericht (Standard: häufigster Host der toten
                        URLs)
  --env-file ENV_FILE   Datei mit KEY=Wert-Zeilen für Schlüssel (Standard: .env im Repo)
  --json                Zusammenfassung als JSON auf stdout
  --quiet               keinen Fortschritt auf stderr

Schlüssel nur über Umgebungsvariablen oder .env: OPENAI_API_KEY, GEMINI_API_KEY, OLLAMA_URL.
```

### Exit-Codes

| Code | Bedeutung |
|---|---|
| 0 | Lauf erfolgreich, Ergebnisdatei geschrieben |
| 1 | Laufzeitfehler: fehlender Schlüssel, Ausgabepfad ist ein Verzeichnis oder nicht beschreibbar, nicht lesbare oder unpassende Eingabedatei, Dimensionskonflikt, Anbieter nicht erreichbar, fehlende `--sender`/`--domain` bei `--drafts` |
| 2 | Ungültige Argumente (argparse), zum Beispiel unbekannte Option, negative `--pause`, `--limit` unter 1, `--max-chars` unter 1000, `--min-dr` außerhalb 0 bis 100 oder `--out` ohne Endung `.xlsx` oder `.csv` |

Fehlermeldungen stehen auf stderr, die Zusammenfassung (Text oder mit `--json` als JSON) auf stdout. Der Fortschritt läuft auf stderr und lässt sich mit `--quiet` abschalten.

### Schlüssel

Schlüssel gehören nie auf die Kommandozeile. Es gibt dafür bewusst keine Option, denn Argumente landen in der Shell-History und in der Prozessliste. `cli.py` liest ausschließlich `OPENAI_API_KEY`, `GEMINI_API_KEY` und `OLLAMA_URL` (Standard `http://localhost:11434`) aus der Umgebung und gibt sie nie aus. Fehlen sie in der Shell, nimmt `cli.py` sie aus `.env` im Repo (oder aus der Datei hinter `--env-file`). Werte aus der Shell haben Vorrang.

### Monatlicher Lauf

`--seen-file` merkt sich alle gemeldeten Paare aus Linkgeber und toter URL. Die Ergebnisdatei bekommt dann eine Spalte "Neu". `--report bericht.md` schreibt einen kurzen Bericht der neuen Chancen und daneben `bericht.html` für den Mailversand. Mit `--json` stehen zusätzlich `new_rows`, `new_opportunities`, `report`, `report_html` und `report_subject` in der Ausgabe. Den kompletten monatlichen Ablauf beschreibt [monatlicher-workflow.md](monatlicher-workflow.md).
