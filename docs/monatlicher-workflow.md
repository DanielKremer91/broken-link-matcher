# Monatlicher Broken-Link-Monitor

Einmal im Monat läuft der komplette Workflow automatisch: Claude holt die Broken Backlinks deiner Wettbewerber über das Ahrefs-MCP, crawlt deine eigene Seite mit Embeddings über das Screaming-Frog-MCP, matcht beides mit `cli.py` und schickt dir einen Bericht. Der Bericht enthält jeden Monat alle offenen Chancen und zeigt, welche seit dem letzten Lauf neu dazugekommen sind.

Die Checkliste zum Abhaken steht in [checkliste.md](checkliste.md).

## Ablauf eines Laufs

1. **Eigene Seiten:** Screaming Frog crawlt die Start-URL mit deiner gespeicherten Konfiguration und exportiert die Embeddings.
2. **Wettbewerber:** Das Ahrefs-MCP liefert pro Wettbewerber bis zu 100 Broken Backlinks, eine Zeile pro linkgebender Domain, sortiert nach Domain Rating.
3. **Matching:** `cli.py` holt die toten Seiten aus der Wayback Machine, bettet sie ein, sucht die drei ähnlichsten eigenen Seiten und prüft live, ob der Link noch existiert.
4. **Abgleich mit dem Vormonat:** Eine Verlaufsdatei pro Wettbewerber merkt sich jedes gemeldete Paar aus linkgebender Seite und toter URL, zusammen mit dem Monat der ersten Meldung. Daran erkennt der Bericht, was neu ist.
   - Unterschiede bei `https`, `www` oder Schrägstrich am Ende zählen nicht als neu.
   - Links, die die Live-Prüfung als erledigt einstuft, fallen aus dem Bericht. Taucht so ein Link später wieder als offen auf, steht er wieder drin.
   - Ein Content-Gap, für den es später eine passende eigene Seite gibt, erscheint dann als neue Chance.
   - Ahrefs liefert pro linkgebender Domain nur einen Beispiel-Link. Wechselt dieser Beispiel-Link, taucht dieselbe Domain mit einer anderen Seite erneut auf.
5. **Bericht:** Jeden Monat die komplette Liste aller offenen Chancen. Oben stehen die neuen, darunter die bereits gemeldeten mit dem Monat ihrer ersten Meldung. Pro Linkgeber: tote URL, Anker, alle drei Vorschläge mit Score, Herkunft des Texts und Live-Status. Betreff zum Beispiel "42 Chancen, davon 5 neu". Content-Gaps stehen nur in der Excel-Datei. Excel und Mail-Entwürfe hängen an.
6. **Versand:** per Resend, per Mail-Connector (Outlook oder Gmail) oder gar nicht. Dann liegt alles im Laufordner.

### Was "Fallback" bei der Wayback Machine heißt

Für jede tote URL holt das Tool den jüngsten Snapshot mit Status 200 aus der Wayback Machine und zieht daraus den Haupttext. Gibt es keinen Snapshot oder enthält er keinen lesbaren Text, baut das Tool einen Ersatztext. Er besteht nur aus dem, was Ahrefs schon liefert: Titel der linkgebenden Seite, Ankertext, Text links und rechts vom Link und den Wörtern aus dem URL-Pfad. Erfunden wird nichts. Das Matching auf dieser Grundlage ist unschärfer, deshalb zeigt der Bericht pro Zeile, woher der Text stammt.

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

Das Frog-MCP kann Embeddings nicht selbst einschalten. Es startet den Crawl mit einer gespeicherten Konfigurationsdatei. Darin steckt alles: Crawl-Umfang, Rendering und das Embedding-Setup. Es gibt zwei Wege, die Embeddings zu erzeugen:

| Weg | Einstellung im Monitor | Hinweis |
|---|---|---|
| Custom JavaScript (Snippet ruft die OpenAI-API auf) | `frog.embeddings_source`: `custom_javascript` | braucht JavaScript-Rendering; der Schlüssel steht im Snippet und damit in der Konfigurationsdatei |
| Eingebaute KI-Anbindung von Frog | `frog.embeddings_source`: `ai` | Schlüssel wird in Frog hinterlegt |

So legst du die Datei an:

1. **Embeddings einrichten,** entweder als Custom-JavaScript-Snippet (Konfiguration, Benutzerdefiniert, Custom JavaScript) oder über die KI-Anbindung (Konfiguration, API-Zugang, KI).
2. **Rendering:** Beim Custom-JavaScript-Weg unter Konfiguration, Spider, Rendering auf JavaScript stellen. Ohne Rendering läuft das Snippet nicht.
3. **Umfang festlegen:** Nur HTML-Seiten, bei Bedarf auf relevante Verzeichnisse beschränken, Parameter-URLs ausschließen.
4. **Einmal testen:** Ein paar Seiten crawlen und prüfen, ob die Embedding-Spalte gefüllt ist.
5. **Speichern:** Datei, Konfiguration, Speichern unter. Lege die Datei in das Basisverzeichnis des Frog-MCP, bei dir `~/seo_spider_mcp_server/`. Auf dieses Verzeichnis hat das MCP sicher Zugriff.

Heißt die Custom-JavaScript-Spalte nicht nach dem Muster "Embeddings ...", trage ihren Namen in `frog.custom_js_field` ein, zum Beispiel `Embeddings Fressnapf 1`.

Das Modell im Snippet oder in der KI-Anbindung muss exakt zu `embedding.model` in der Monitor-Konfiguration passen. Sonst bricht der Dimensionscheck ab.

Gib die Konfigurationsdatei nie weiter und lege sie nie ins Repo. Beim Custom-JavaScript-Weg steht dein API-Schlüssel darin.

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
| `frog.embeddings_source` | `custom_javascript` oder `ai`, siehe Schritt 2 |
| `frog.custom_js_field` | optional: Name der Custom-JavaScript-Spalte mit den Embeddings |
| `competitors` | Liste der Wettbewerber-Domains ohne Protokoll |
| `embedding` | Anbieter und Modell, identisch zum Frog |
| `ahrefs` | Filter für den Ahrefs-Abruf, siehe unten |
| `verify` | Live-Prüfung, ob Ziel noch tot und Link noch vorhanden |
| `drafts` | Mail-Entwürfe an Linkgeber erzeugen, nur als Entwurf |
| `contact` | optional: Mail oder URL im User-Agent für Wayback und Live-Prüfung |
| `mail.method`, `mail.to` | `resend`, `connector` oder `file`, dazu die Empfänger |
| `output_dir` | Ordner für Laufergebnisse und Verlaufsdateien |

`monitor.config.json` steht in `.gitignore`.

#### Ahrefs-Filter

| Feld | Standard | Bedeutung |
|---|---|---|
| `limit` | 100 | Zeilen pro Wettbewerber, 1 bis 1000 |
| `min_dr` | 0 | Mindest-Domain-Rating der linkgebenden Domain |
| `dofollow_only` | true | nur Dofollow-Links |
| `content_only` | true | nur Links aus dem Inhaltsbereich, keine Navigation oder Footer |
| `exclude_spam` | true | Links, die Ahrefs als Spam einstuft, auslassen |
| `dead_only` | true | nur Ziele mit Status 404 oder 410 |
| `mode` | subdomains | `subdomains`, `domain`, `prefix` oder `exact` |
| `aggregation` | 1_per_domain | `1_per_domain` (eine Zeile pro Domain), `similar` oder `all` |
| `order_by` | domain_rating_source | Sortierung: `domain_rating_source`, `url_rating_source` oder `traffic` |
| `include_traffic` | false | organischen Traffic der linkgebenden Seite mitholen, kostet 10 Units extra pro Zeile |

`ahrefs_params.py` macht daraus die exakten Parameter für das Ahrefs-MCP. So siehst du vorab, was abgefragt wird:

```bash
.venv/bin/python ahrefs_params.py --target zooroyal.de
```

#### Mehrere Wettbewerber

Trage einfach mehrere Domains in `competitors` ein. Der Crawl der eigenen Seite läuft einmal, Ahrefs-Abruf, Matching, Verlauf und Mail gibt es pro Wettbewerber.

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

Weitere Läufe im selben Monat sind unkritisch. Sie melden dieselben Paare noch einmal, weil sich die Verlaufsdatei den Monat jeder Meldung merkt. Das hilft auch, wenn ein Versand gescheitert ist: Lauf wiederholen, Bericht kommt erneut.

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
| Ahrefs | etwa 12 Units pro Zeile mit den Standardfiltern, also rund 1.200 Units pro Wettbewerber bei 100 Zeilen |
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
      ergebnis.xlsx                alle Zeilen, mit den Spalten "Neu" und "Erstmals erfasst"
      ergebnis-entwuerfe.md        Mail-Entwürfe
      bericht.md, bericht.html     Bericht, so wie er verschickt wird
    fehler.md                      nur wenn etwas schiefging
```

`laeufe/` steht in `.gitignore`. Ein `git clean -fdx` oder ein frischer Klon löscht deshalb auch die Verlaufsdateien. Sichere sie, wenn du das Repo neu aufsetzt. Ohne Verlauf gilt beim nächsten Lauf wieder alles als neu.

## Fehlerbehebung

| Meldung | Ursache und Lösung |
|---|---|
| Frog-Export ohne Embeddings | Die Konfiguration enthält kein Embedding-Setup, beim Custom-JavaScript-Weg fehlt das JavaScript-Rendering, oder `frog.embeddings_source` passt nicht zum Weg. |
| Mehrere oder keine Embedding-Spalten | `frog.custom_js_field` auf den genauen Spaltennamen setzen. |
| Dimension passt nicht | Modell im Frog und `embedding.model` unterscheiden sich. |
| `OPENAI_API_KEY ist nicht gesetzt` | `.env` fehlt oder ist leer. |
| Resend lehnt ab, Domain nicht verifiziert | DNS-Einträge in Resend prüfen, `RESEND_FROM` muss auf der verifizierten Domain liegen. |
| Verlaufsdatei nicht lesbar | Datei wurde von Hand beschädigt. Aus einem Backup zurückholen oder löschen; dann gilt beim nächsten Lauf wieder alles als neu. |
| Lauf ist nicht gestartet | Die Desktop-App war geschlossen. Er läuft beim nächsten Öffnen. |
| Bericht kam nicht an | `fehler.md` im Laufordner lesen. Nach der Behebung den Lauf wiederholen. Im selben Monat genügt `/broken-link-monitor`. Ist der Monat schon vorbei, nenne die Lauf-Kennung: `/broken-link-monitor mit Lauf-Kennung 2026-11`. |
