---
name: broken-link-monitor
description: Monatlicher Broken-Link-Monitor. Holt die Broken Backlinks von Wettbewerbern über das Ahrefs-MCP, crawlt die eigene Domain mit Embeddings über das Screaming-Frog-MCP, matcht tote Wettbewerber-URLs mit eigenen Seiten (broken-link-matcher, cli.py), meldet nur neue Chancen seit dem letzten Lauf und verschickt den Bericht per Resend, Mail-Connector oder als Datei. Verwende diesen Skill bei "Broken-Link-Monitor", "monatlicher Broken-Link-Lauf", "/broken-link-monitor" oder wenn eine geplante Aufgabe ihn aufruft.
---

# Broken-Link-Monitor

Dieser Skill läuft oft unbeaufsichtigt als geplante Aufgabe. Stelle deshalb keine Rückfragen. Wenn etwas fehlt oder scheitert, brich sauber ab und melde den Fehler über denselben Weg wie den Bericht (Schritt 6).

## Feste Regeln

- Schlüssel (OpenAI, Gemini, Resend) nie ausgeben, nie auf die Kommandozeile schreiben, nie in Dateien außer `.env` ablegen. `cli.py` und `send_report.py` lesen sie selbst aus der Umgebung oder aus `<repo>/.env`.
- Verschicke ausschließlich den Bericht an die Empfänger aus `mail.to`. Schicke niemals Mails an Linkgeber. Die Mail-Entwürfe sind nur Entwürfe.
- Erfinde keine Inhalte. Alle Zahlen und URLs im Bericht stammen aus der Ausgabe von `cli.py`.

## Schritt 0: Konfiguration finden

1. Suche `monitor.config.json` in dieser Reihenfolge: im aktuellen Arbeitsordner, in dem Ordner, den die aufrufende Aufgabe nennt, in `~/broken-link-matcher/`.
2. `repo_path` ist der Ordner mit `cli.py`. Alle relativen Pfade beziehen sich auf ihn. Fehlt das Repo, klone es mit `git clone https://github.com/DanielKremer91/broken-link-matcher <repo_path>` und richte die Umgebung ein: `cd <repo_path> && uv venv && uv pip install -r requirements.txt`.
3. Lege den Laufordner an: `<repo_path>/<output_dir>/<JJJJ-MM>/`. Alle Dateien dieses Laufs landen dort.
4. Prüfe die Einrichtung mit `<repo_path>/.venv/bin/python <repo_path>/check_setup.py --config <pfad zur config>`. Bei Exit-Code ungleich 0: Abbruch mit der ausgegebenen Meldung (Schritt 6).

## Schritt 1: Eigene Seiten mit Embeddings (Screaming-Frog-MCP)

Wenn `frog.crawl` true ist:

1. Starte den Crawl: Frog-MCP-Tool zum Crawlen mit `crawl_url` = `start_url` und `config_path` = `frog.config_file`.
2. Prüfe den Fortschritt etwa einmal pro Minute mit dem Fortschritts-Tool, bis 100 Prozent erreicht sind. Brich nach drei Stunden ab.
3. Exportiere die Embeddings mit dem Export-Tool nach `broken-link-monitor/<own_domain>-<JJJJ-MM>.csv`. Der Pfad ist relativ zum erlaubten Basisverzeichnis des Frog-MCP. Hol dir dieses Verzeichnis mit dem Tool, das es auflistet, und bilde daraus den absoluten Pfad.
4. Prüfe die Kopfzeile der CSV. Sie muss `url` und Spalten `embedding_0`, `embedding_1` und so weiter enthalten. Fehlen die Embedding-Spalten, enthält die Frog-Konfiguration keine Embeddings: Abbruch mit genau diesem Hinweis.

Wenn `frog.crawl` false ist, nimm `frog.embeddings_file` als fertigen Export.

## Schritt 2: Broken Backlinks pro Wettbewerber (Ahrefs-MCP)

Für jeden Eintrag in `competitors`:

1. Lies einmal die Doku des Ahrefs-Endpunkts für Broken Backlinks (Ahrefs-MCP-Tool `doc`).
2. Rufe den Endpunkt `site-explorer-broken-backlinks` auf mit: target = Wettbewerber, mode `subdomains`, aggregation `1_per_domain`, where `is_dofollow = true` und `is_content = true` (bei `ahrefs.min_dr` größer 0 zusätzlich `domain_rating_source >= min_dr`), order_by `domain_rating_source:desc`, limit `ahrefs.limit`, output `csv`, select `url_from,url_to,anchor,snippet_left,snippet_right,title,domain_rating_source,url_rating_source,http_code_target,is_dofollow,is_content`.
3. Speichere die CSV unverändert als `<laufordner>/<wettbewerber>/broken-backlinks.csv`.

## Schritt 3: Matching (cli.py)

Für jeden Wettbewerber im Repo-Ordner:

```
.venv/bin/python cli.py \
  --frog <absoluter Pfad aus Schritt 1> \
  --backlinks <laufordner>/<wettbewerber>/broken-backlinks.csv \
  --provider <embedding.provider> --model <embedding.model> \
  --out <laufordner>/<wettbewerber>/ergebnis.xlsx \
  --seen-file <output_dir>/verlauf-<wettbewerber>.json \
  --report <laufordner>/<wettbewerber>/bericht.md \
  --competitor <wettbewerber> \
  --json --quiet
```

Hänge `--verify` an, wenn `verify` true ist. Hänge `--drafts --sender "<drafts.sender>" --domain <own_domain>` an, wenn `drafts.enabled` true ist. Hänge `--contact "<contact>"` an, wenn `contact` nicht leer ist.

Lies die JSON-Ausgabe. Wichtig sind `report_subject`, `report`, `report_html`, `output`, `drafts_output`, `new_opportunities` und `errors`. Exit-Code 1 heißt Abbruch für diesen Wettbewerber: Nimm die Meldung von stderr in den Fehlerbericht auf und mach mit dem nächsten weiter.

Die Verlaufsdatei sorgt dafür, dass jeder Linkgeber nur einmal als neu gemeldet wird. Lösche sie nie.

## Schritt 4: Kurze Einordnung

Lies `bericht.md` und die ersten Zeilen von `ergebnis.xlsx`. Schreibe höchstens fünf Sätze Einordnung: welche neuen Linkgeber zuerst angeschrieben werden sollten und warum (hoher DR, Score, Live-Prüfung bestätigt). Erfinde nichts, was nicht in den Dateien steht. Hänge die Einordnung oben in `bericht.md` an und als Absatz `<p>` direkt nach der Überschrift in `bericht.html`.

## Schritt 5: Versand

Je Wettbewerber eine Mail, je nach `mail.method`:

- **resend**: im Repo-Ordner
  ```
  .venv/bin/python send_report.py --to <empfänger> [--to <weitere>] \
    --subject "<report_subject>" --html <report_html> --text <report> \
    --attach <output> [--attach <drafts_output>]
  ```
  `send_report.py` liest `RESEND_API_KEY` und `RESEND_FROM` aus der Umgebung oder `.env`.
- **connector**: Nutze den verbundenen Mail-Connector (Outlook oder Gmail) und schicke an die Empfänger aus `mail.to`: Betreff `report_subject`, Text aus `bericht.md`. Hänge die Excel-Datei an, wenn der Connector Anhänge kann, sonst nenne den Dateipfad.
- **file**: Kein Versand. Die Dateien liegen im Laufordner.

## Schritt 6: Fehlerfall

Scheitert ein Schritt vor dem Bericht, schreibe `<laufordner>/fehler.md` mit Schritt, Meldung und Hinweis zur Behebung. Verschicke ihn auf dem Weg aus `mail.method` mit dem Betreff `Broken Link Monitor: Lauf fehlgeschlagen (<JJJJ-MM>)`. Bei `resend` geht das mit `send_report.py --text <laufordner>/fehler.md`.

## Schritt 7: Abschluss

Antworte mit einer kurzen Zusammenfassung: pro Wettbewerber neue Chancen, Versandstatus und Pfad zum Laufordner.
