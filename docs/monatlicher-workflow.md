# Monatlicher Broken-Link-Monitor

Einmal im Monat läuft der komplette Workflow automatisch: Claude holt die Broken Backlinks deiner Wettbewerber über das Ahrefs-MCP, crawlt deine eigene Seite mit Embeddings über das Screaming-Frog-MCP, matcht beides mit `cli.py` und schickt dir einen Bericht. Der Bericht enthält nur Paare aus linkgebender Seite und toter URL, die seit dem letzten Lauf neu dazugekommen sind.

Die Checkliste zum Abhaken steht in [checkliste.md](checkliste.md).

## Ablauf eines Laufs

1. **Eigene Seiten:** Screaming Frog crawlt die Start-URL mit deiner gespeicherten Konfiguration und exportiert die Embeddings.
2. **Wettbewerber:** Das Ahrefs-MCP liefert pro Wettbewerber bis zu 100 Broken Backlinks, eine Zeile pro linkgebender Domain, sortiert nach Domain Rating.
3. **Matching:** `cli.py` holt die toten Seiten aus der Wayback Machine, bettet sie ein, sucht die drei ähnlichsten eigenen Seiten und prüft live, ob der Link noch existiert.
4. **Abgleich mit dem Vormonat:** Eine Verlaufsdatei pro Wettbewerber merkt sich jedes gemeldete Paar aus linkgebender Seite und toter URL, zusammen mit dem Monat der Meldung. In den Bericht kommen nur neue Paare.
   - Unterschiede bei `https`, `www` oder Schrägstrich am Ende zählen nicht als neu.
   - Paare, die nicht im Bericht standen, bleiben offen und kommen beim nächsten Lauf wieder dran. Das betrifft Links, die die Live-Prüfung als erledigt eingestuft hat, und Zeilen ohne Treffer.
   - Ein Content-Gap, für den es später eine passende eigene Seite gibt, wird noch einmal als Chance gemeldet.
   - Ahrefs liefert pro linkgebender Domain nur einen Beispiel-Link. Wechselt dieser Beispiel-Link, taucht dieselbe Domain mit einer anderen Seite erneut auf.
5. **Bericht:** Betreff mit der Zahl neuer Chancen, Tabelle mit Linkgeber, toter URL, Anker, Vorschlag, Score und Live-Status, dazu Content-Gaps. Excel-Datei und Mail-Entwürfe hängen an.
6. **Versand:** per Resend, per Mail-Connector (Outlook oder Gmail) oder gar nicht. Dann liegt alles im Laufordner.

## Voraussetzungen

| Was | Wofür |
|---|---|
| Claude-Desktop-App mit Claude Code | Skill und geplante Aufgabe |
| Ahrefs-Abo mit MCP-Zugang | Broken Backlinks der Wettbewerber |
| Screaming Frog SEO Spider mit Lizenz und MCP-Erweiterung | Crawl mit Embeddings |
| OpenAI-Schlüssel (oder Gemini, oder lokal Ollama) | Embeddings im Frog und im Tool, Mail-Entwürfe |
| Optional: Resend-Konto mit verifizierter Domain | Versand des Berichts |
| Python 3.11 oder neuer und `uv` | `cli.py` |

## Einrichtung

### 1. Repo und Umgebung

```bash
git clone https://github.com/DanielKremer91/broken-link-matcher
```

```bash
cd broken-link-matcher && uv venv && uv pip install -r requirements.txt
```

### 2. Screaming-Frog-Konfiguration mit Embeddings

Das Frog-MCP kann Embeddings nicht selbst einschalten. Es startet den Crawl mit einer gespeicherten Konfigurationsdatei. Diese legst du einmal in der Frog-Oberfläche an:

1. **KI-Anbieter verbinden:** Konfiguration, API-Zugang, KI, OpenAI. Schlüssel eintragen und verbinden.
2. **Embedding-Prompt anlegen:** Im selben Fenster unter Prompt-Konfiguration einen Eintrag aus der Bibliothek hinzufügen, der Embeddings aus dem Seiteninhalt erzeugt. Modell zum Beispiel `text-embedding-3-small`.
3. **Umfang festlegen:** Nur HTML-Seiten, bei Bedarf auf relevante Verzeichnisse beschränken, Parameter-URLs ausschließen.
4. **Speichern:** Datei, Konfiguration, Speichern unter. Lege die Datei in das Basisverzeichnis des Frog-MCP, zum Beispiel `~/seo_spider_mcp_server/broken-link-monitor.seospiderconfig`.

Das Modell im Frog muss exakt zu `embedding.model` in der Monitor-Konfiguration passen. Sonst bricht der Dimensionscheck ab.

Gib die Konfigurationsdatei nicht weiter. Je nach Frog-Version können darin Zugangsdaten stecken.

### 3. Schlüssel in `.env`

```bash
cp .env.example .env && chmod 600 .env
```

Trage danach in `.env` deinen OpenAI-Schlüssel ein, bei Resend auch `RESEND_API_KEY` und `RESEND_FROM`. Kommentare hinter einem Wert sind erlaubt, wenn vor dem `#` ein Leerzeichen steht. Die Datei steht in `.gitignore`. Schlüssel gehören nie in den Chat, nie auf die Kommandozeile und nie in die Monitor-Konfiguration.

### 4. Resend einrichten (optional)

1. Konto bei resend.com anlegen.
2. Unter Domains die Absender-Domain hinzufügen und die angezeigten DNS-Einträge setzen. Nach der Verifizierung darf Resend in ihrem Namen senden.
3. Unter API Keys einen Schlüssel mit Sendeberechtigung erzeugen und als `RESEND_API_KEY` in `.env` eintragen.
4. `RESEND_FROM` auf eine Adresse dieser Domain setzen, zum Beispiel `Broken Link Monitor <monitor@deine-domain.de>`.

Ohne verifizierte Domain gibt es nur den Testabsender `onboarding@resend.dev`. Der darf ausschließlich an die Adresse des Resend-Kontos senden.

Lieber per Outlook oder Gmail? Verbinde den Connector in den Claude-Einstellungen und setze `mail.method` auf `connector`. Ganz ohne Versand: `file`.

### 5. Monitor-Konfiguration

```bash
cp .claude/skills/broken-link-monitor/config.example.json monitor.config.json
```

| Feld | Bedeutung |
|---|---|
| `repo_path` | absoluter Pfad zu diesem Repo |
| `own_domain` | deine Domain, erscheint in den Mail-Entwürfen |
| `start_url` | Start-URL des Crawls, zum Beispiel dein Ratgeber-Verzeichnis |
| `frog.crawl` | `true` crawlt jeden Monat neu, `false` nimmt `frog.embeddings_file` |
| `frog.config_file` | die gespeicherte Frog-Konfiguration aus Schritt 2 |
| `competitors` | Liste der Wettbewerber-Domains ohne Protokoll |
| `embedding` | Anbieter und Modell, identisch zum Frog |
| `ahrefs.limit`, `ahrefs.min_dr` | Zeilen pro Wettbewerber und Mindest-Domain-Rating |
| `verify` | Live-Prüfung, ob Ziel noch tot und Link noch vorhanden |
| `drafts` | Mail-Entwürfe an Linkgeber erzeugen, nur als Entwurf |
| `contact` | optional: Mail oder URL im User-Agent für Wayback und Live-Prüfung |
| `mail.method`, `mail.to` | `resend`, `connector` oder `file`, dazu die Empfänger |
| `output_dir` | Ordner für Laufergebnisse und Verlaufsdateien |

`monitor.config.json` steht in `.gitignore`.

### 6. Einrichtung prüfen

```bash
.venv/bin/python check_setup.py
```

Das Skript zeigt pro Punkt einen Haken oder ein Kreuz und nennt nie Schlüsselwerte.

### 7. Erster Lauf von Hand

Öffne Claude Code im Repo-Ordner und schreibe:

```
/broken-link-monitor
```

Beim ersten Lauf fragt Claude nach Berechtigungen für die MCP-Tools und für Shell-Befehle. Erlaube sie, damit der automatische Lauf später ohne Rückfrage durchkommt. Prüfe danach Bericht, Excel und Mail.

Weitere Läufe im selben Monat sind unkritisch. Sie liefern denselben Bericht noch einmal, weil sich die Verlaufsdatei den Monat jeder Meldung merkt. Das hilft auch, wenn ein Versand gescheitert ist: Lauf wiederholen, Bericht kommt erneut.

### 8. Monatlich automatisch

Bitte Claude in der Desktop-App:

```
Lege eine geplante Aufgabe an, die am 1. jedes Monats um 7 Uhr läuft.
Prompt: Arbeite im Ordner /Pfad/zu/broken-link-matcher. Lies .claude/skills/broken-link-monitor/SKILL.md und führe den Broken-Link-Monitor mit monitor.config.json aus.
```

Geplante Aufgaben laufen nur, wenn die Desktop-App geöffnet ist. Verpasste Läufe holt die App beim nächsten Start nach. Der Mac sollte zur geplanten Zeit wach sein, weil der Crawl je nach Seitengröße eine Weile dauert.

## Skill herauslösen

Der Skill liegt in `.claude/skills/broken-link-monitor/` und funktioniert in Claude Code automatisch, sobald du im Repo arbeitest. Für die Nutzung in jedem Ordner kopierst du ihn in deine persönlichen Skills:

```bash
cp -R .claude/skills/broken-link-monitor ~/.claude/skills/
```

Der Skill findet das Repo über `repo_path` in `monitor.config.json`. Fehlt das Repo, klont er es selbst.

## Was ein Lauf kostet

| Posten | Größenordnung |
|---|---|
| Ahrefs | etwa 11 Units pro Zeile, also rund 1.100 Units pro Wettbewerber bei 100 Zeilen |
| Embeddings im Frog | abhängig von der Seitenzahl, bei `text-embedding-3-small` wenige Cent pro tausend Seiten |
| Embeddings und Mail-Entwürfe im Tool | wenige Cent pro Lauf |
| Resend | im kostenlosen Kontingent enthalten |

## Dateien eines Laufs

```
laeufe/
  verlauf-zooroyal.de.json         bereits gemeldete Paare mit Monat, nie löschen
  2026-11/
    zooroyal.de/
      broken-backlinks.csv         Antwort des Ahrefs-MCP
      ergebnis.xlsx                alle Zeilen, Spalte "Neu" markiert neue
      ergebnis-entwuerfe.md        Mail-Entwürfe
      bericht.md, bericht.html     Bericht, so wie er verschickt wird
    fehler.md                      nur wenn etwas schiefging
```

`laeufe/` steht in `.gitignore`. Ein `git clean -fdx` oder ein frischer Klon löscht deshalb auch die Verlaufsdateien. Sichere sie, wenn du das Repo neu aufsetzt. Ohne Verlauf gilt beim nächsten Lauf wieder alles als neu.

## Fehlerbehebung

| Meldung | Ursache und Lösung |
|---|---|
| Frog-Export ohne Embedding-Spalten | Die Frog-Konfiguration enthält keinen Embedding-Prompt. Schritt 2 wiederholen und neu speichern. |
| Dimension passt nicht | Modell im Frog und `embedding.model` unterscheiden sich. |
| `OPENAI_API_KEY ist nicht gesetzt` | `.env` fehlt oder ist leer. |
| Resend lehnt ab, Domain nicht verifiziert | DNS-Einträge in Resend prüfen, `RESEND_FROM` muss auf der verifizierten Domain liegen. |
| Verlaufsdatei nicht lesbar | Datei wurde von Hand beschädigt. Aus einem Backup zurückholen oder löschen; dann gilt beim nächsten Lauf wieder alles als neu. |
| Lauf ist nicht gestartet | Die Desktop-App war geschlossen. Er läuft beim nächsten Öffnen. |
| Bericht kam nicht an | `fehler.md` im Laufordner lesen. Nach der Behebung den Lauf im selben Monat wiederholen, der Bericht kommt dann vollständig. |
