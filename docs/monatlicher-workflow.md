# Monatlicher Broken-Link-Monitor

**Schnellstart:** Claude-Desktop-App öffnen, Bereich Code, eine neue Sitzung starten (welcher Ordner, ist egal) und diesen Satz eingeben:

```
Richte mir den Broken Link Monitor ein. Klone dazu https://github.com/DanielKremer91/broken-link-matcher nach ~/broken-link-matcher und folge der Anleitung für Claude in der README.
```

Claude führt dann durch alle Punkte unten.

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
5. **Bericht:** Eine kundenfreundliche Mail mit dem Betreff "Broken Link Chancen" und dem Kundennamen, zum Beispiel "Broken Link Chancen Fressnapf". Sie erklärt in einfachen Worten, worum es geht, und listet jeden Monat alle offenen Chancen: oben die neuen, darunter die weiterhin offenen mit dem Monat ihrer ersten Meldung. Pro Chance stehen verlinkende Website, Stärke, nicht mehr erreichbare Seite mit Linktext, passende eigene Seite mit zwei Alternativen, Passgenauigkeit, Grundlage und Status. Am Ende erklärt die Mail jede Angabe. Content-Gaps, also tote Seiten ohne passenden eigenen Inhalt, stehen weder in der Mail noch im Anhang. Wer sie als Ideen für neue Inhalte nutzen will, sieht sie in der Streamlit-App oder in einem CLI-Lauf ohne `--report`. Excel und Mail-Entwürfe an die verlinkenden Websites hängen an. Verschickt werden die Entwürfe nie automatisch.
6. **Versand:** per Resend, per Mail-Connector (Outlook oder Gmail) oder gar nicht. Dann liegt alles im Laufordner.

### Was "Fallback" bei der Wayback Machine heißt

Für jede tote URL holt das Tool den jüngsten Snapshot mit Status 200 aus der Wayback Machine und zieht daraus den Haupttext. Gibt es keinen Snapshot oder enthält er keinen lesbaren Text, baut das Tool einen Ersatztext. Er besteht nur aus dem, was Ahrefs schon liefert: Titel der linkgebenden Seite, Ankertext, Text links und rechts vom Link und den Wörtern aus dem URL-Pfad. Erfunden wird nichts. Das Matching auf dieser Grundlage ist unschärfer, deshalb zeigt der Bericht pro Zeile, woher der Text stammt.

## Voraussetzungen

| Was | Wofür |
|---|---|
| Claude-Desktop-App mit Claude Code, auf macOS oder Windows | Skill und geplante Aufgabe. Die Skripte werden auf beiden Systemen automatisch getestet. Die Einrichtung im Gespräch und das Zusammenspiel mit Screaming Frog sind bisher nur auf macOS praktisch erprobt |
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
cd broken-link-matcher && uv venv --python 3.11 .venv && uv pip install -r requirements.txt
```

### 2. Screaming-Frog-Konfiguration mit Embeddings

Das Frog-MCP kann Embeddings nicht selbst einschalten. Es startet den Crawl mit einer gespeicherten Konfigurationsdatei. Darin steckt alles: Crawl-Umfang, Rendering und das Embedding-Setup. Es gibt zwei Wege, die Embeddings zu erzeugen:

| Weg | Einstellung im Monitor | Hinweis |
|---|---|---|
| Custom JavaScript mit der Vorlage `frog/main-content-embedding.js` | `frog.embeddings_source`: `custom_javascript` | extrahiert den Hauptinhalt, teilt lange Texte auf; braucht JavaScript-Rendering; der Schlüssel steht im Snippet und damit in der Konfigurationsdatei |
| Eingebaute KI-Anbindung von Frog mit Seitentext | `frog.embeddings_source`: `ai` | Hauptinhalt über `Konfiguration > Inhalt > Bereich`; Navigation und Footer sind dort standardmäßig ausgeschlossen; Schlüssel wird in Frog hinterlegt |

**Nur der Hauptinhalt zählt.** Kommen Navigation, Footer, Cookie-Banner oder Teaserlisten ins Embedding, sehen sich alle Seiten ähnlicher, als sie sind. Die Vorlage findet den Hauptinhalt auf vielen Seiten von selbst. Für eine bestimmte Website trägst du oben eigene Selektoren ein: `CONTENT_ROOT_SELECTOR` für den Inhaltsbereich, `EXTRA_EXCLUDE_SELECTOR` für Bereiche wie Bildnachweise oder Autorenboxen. Mit `PREVIEW_TEXT = true` zeigt Frog nach einem kurzen Testcrawl den Text, der eingebettet würde, ohne OpenAI-Kosten. Beim Weg über die KI-Anbindung trägst du dieselben Ausschlüsse unter `Konfiguration > Inhalt > Bereich` ein.

So legst du die Datei an. Die Einrichtung mit Claude führt dich Schritt für Schritt durch dieselben Handgriffe. Die Menünamen stehen hier auf Deutsch und in Klammern auf Englisch.

Beim Snippet-Weg:

1. **Rendering:** `Konfiguration > Spider`, Reiter `Rendering`, Auswahl `JavaScript` statt `Nur Text` (`Configuration > Spider > Rendering > JavaScript`).
2. **Snippet anlegen:** `Konfiguration > Eigene > Eigenes JavaScript`, `Hinzufügen` (`Configuration > Custom > Custom JavaScript`, `Add`). Typ `Extraktion` (`Extraction`), Name `Embeddings <Kunde>`. Der Name muss mit "Embeddings" beginnen.
3. **Vorlage einfügen:** Den Inhalt von `frog/main-content-embedding.js` kopieren und über den Knopf `JS` in den Editor einfügen.
4. **Anpassen, nur im Frog-Editor:** eigenen OpenAI-Schlüssel eintragen, `MODEL` prüfen, bei Bedarf Selektoren für Inhaltsbereich und Ausschlüsse setzen.
5. **Speichern:** `Konfiguration > Profile > Speichern unter...` (`Configuration > Profiles > Save As...`), in älteren Versionen `Datei > Konfiguration > Speichern unter...`. Speichere einfach im Ordner **Downloads**, mit dem Kundennamen im Dateinamen, zum Beispiel `broken-link-monitor-fressnapf.seospiderconfig`.
6. **An den richtigen Ort:** Claude verschiebt die Datei in den Ordner des Frog-MCP. Von Hand geht es mit `.venv/bin/python place_frog_config.py --target <Pfad aus frog.config_file>`. Das Skript findet die Datei in Downloads, auf dem Schreibtisch, in Dokumente und im Benutzerordner. Den Schreibtisch besser meiden: Er wird auf vielen Macs mit iCloud abgeglichen, und die Datei kann deinen Schlüssel enthalten.

Bei der KI-Anbindung: Anbieter unter `Konfiguration > API-Zugang > KI` verbinden, in der `Prompt-Konfiguration` einen Embedding-Prompt für den `Seitentext` anlegen, unter `Konfiguration > Inhalt > Einbettungen` einschalten und unter `Konfiguration > Inhalt > Bereich` die Ausschlüsse prüfen. Dann speichern wie oben.

Jeder Kunde bekommt seine eigene Konfiguration, weil Snippet und Ausschlüsse auf den Seitenaufbau der jeweiligen Website zugeschnitten sind.

**Probe-Crawl:** Nach dem Speichern crawlt Claude zur Probe etwa 60 Seiten und prüft, ob Embeddings ankommen und die Dimension zum Modell passt. Das dauert zwei bis drei Minuten und kostet weniger als einen Cent. So zeigt sich ein Fehler sofort und nicht erst im ersten Lauf.

Heißt die Custom-JavaScript-Spalte nicht nach dem Muster "Embeddings ...", trage ihren Namen in `frog.custom_js_field` ein, zum Beispiel `Embeddings Fressnapf 1`.

Das Modell im Snippet oder in der KI-Anbindung muss exakt zu `embedding.model` in der Monitor-Konfiguration passen. Mit diesem Modell bettet das Tool auch die toten Wettbewerberseiten ein. In der `.env` steht nur der Schlüssel, nicht das Modell. Passen die Modelle nicht, bricht der Dimensionscheck ab.

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
| `customer` | Kundenname für Betreff und Text der Mail, zum Beispiel `Fressnapf` |
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
| `contact` | optional: Mail oder URL im User-Agent für Wayback Machine und Live-Prüfung |
| `mail.method`, `mail.to` | `resend`, `connector` oder `file`, dazu die Empfänger |
| `output_dir` | Ordner für Laufergebnisse und Verlaufsdateien |

`monitor.config.json` steht in `.gitignore`.

#### Ahrefs-Filter

| Feld | Standard | Bedeutung |
|---|---|---|
| `limit` | 100 | Zeilen pro Wettbewerber, 1 bis 200. Mehr geht über das Ahrefs-MCP nicht zuverlässig, weil Claude die Zeilen selbst in eine Datei überträgt |
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

### Mehrere Kunden

Eine Einrichtung gehört zu genau einem Kunden: eine eigene Domain, eine Frog-Konfiguration, beliebig viele Wettbewerber. Für einen weiteren Kunden richtest du den Monitor ein zweites Mal ein, mit demselben Startsatz. Als Speicherort wählst du dann einen eigenen Ordner, zum Beispiel `~/broken-link-matcher-bora`. Jede Einrichtung hat ihre eigene Konfiguration, ihren Verlauf und auf Wunsch ihre eigene geplante Aufgabe.

Alle Einrichtungen teilen sich einen Screaming Frog, und der crawlt immer nur eine Website gleichzeitig. Lege die Aufgaben deshalb auf verschiedene Tage, zum Beispiel den 1., 2. und 3. des Monats. Zusätzlich reserviert jeder Lauf den Frog über eine kleine Sperrdatei, solange er crawlt und exportiert. Ein zweiter Lauf wartet dann bis zu sechs Stunden, statt abzubrechen oder dem ersten den Crawl wegzunehmen. Nach dem Crawl prüft der Monitor außerdem, ob die gecrawlten Seiten wirklich zur eigenen Domain gehören.

### Später etwas ändern

Alle Einstellungen stehen in `monitor.config.json` im Repo-Ordner. Der Monitor liest sie bei jedem Lauf neu. Eine Änderung gilt deshalb ab dem nächsten Lauf, auch für die geplante Aufgabe, ohne dass du diese anfassen musst.

Der **Repo-Ordner** ist der Ordner, in den Claude bei der Einrichtung alles heruntergeladen hat, standardmäßig `~/broken-link-matcher` in deinem Benutzerordner. Darin liegen auch `monitor.config.json` und `.env`. Um mit Claude dort zu arbeiten, startest du in der Claude-App im Bereich Code eine neue Sitzung und wählst diesen Ordner aus.

Am einfachsten sagst du es Claude, in einer Sitzung im Repo-Ordner:

```
Nimm zooplus.de als weiteren Wettbewerber in den Broken Link Monitor auf.
```

Claude trägt die Domain ein, prüft die Einrichtung und bietet an, den neuen Wettbewerber sofort einmal laufen zu lassen. Gibt es diesen Monat schon einen vollständigen Crawl deiner Seite, wird er wiederverwendet. Genauso kannst du Empfänger, Kundennamen oder Ahrefs-Filter ändern oder einen Wettbewerber entfernen.

Von Hand geht es auch: `monitor.config.json` in einem Texteditor öffnen, die Domain in die Liste bei `competitors` eintragen, zum Beispiel `["zooroyal.de", "zooplus.de"]`, speichern und `.venv/bin/python check_setup.py` ausführen.

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

Weitere Läufe im selben Monat sind unkritisch:

- Der Bericht enthält dieselben Paare noch einmal, weil sich die Verlaufsdatei den Monat jeder Meldung merkt.
- Die Mail geht nicht doppelt raus. Nach dem Versand legt der Monitor einen Versandmerker im Laufordner ab (`versendet.json`). Soll sie bewusst noch einmal kommen, sag "erneut senden".
- Wettbewerber, deren Bericht schon verschickt ist, werden komplett übersprungen. Das spart die Ahrefs-Units, und die verschickten Dateien bleiben unverändert.
- Ein vollständiger Crawl deiner Seite aus demselben Monat wird wiederverwendet, solange Start-URL, Frog-Konfiguration und Modell unverändert sind. Ist der Versand gescheitert, reicht also ein kurzer zweiter Lauf.
- Ändert sich mitten im Monat der Empfänger, kommt der Bericht dort erst mit "erneut senden" an.

### 8. Monatlich automatisch

Drei Dinge müssen stimmen, damit der Monitor wirklich ohne dich läuft. Sie sind an echten geplanten Läufen getestet.

**1. Die Aufgabe aus dem Repo-Ordner anlegen.** Eine geplante Aufgabe läuft in dem Ordner, aus dem sie angelegt wurde. Starte in der Claude-App eine Sitzung mit dem Repo-Ordner und schreib dort:

```
Lege den monatlichen Termin für den Broken Link Monitor an.
```

Von Hand geht es auch: eine Aufgabe für den 1. jedes Monats um 7 Uhr mit dem Prompt `Geplanter Lauf ohne Rückfragen: Lies .claude/skills/broken-link-monitor/SKILL.md und führe den Broken-Link-Monitor mit monitor.config.json aus.`

**2. Die Freigabeliste des Repos.** Die Datei `.claude/settings.json` erlaubt Claude in diesem Ordner zwei Dinge ohne Rückfrage:

- die neun Skripte des Monitors auszuführen: `monitor_match.py`, `send_report.py`, `check_setup.py`, `ahrefs_params.py`, `backlinks_check.py`, `frog_state.py`, `frog_probe.py`, `frog_crawl_check.py` und `oshelp.py`
- Dateien im Ordner `laeufe` zu schreiben

Mehr steht nicht drin. Diese Skripte nehmen keine freien Empfänger, Anhänge oder Ausgabepfade an: Wer die Mail bekommt und wohin geschrieben wird, bestimmt allein deine `monitor.config.json`. Beim ersten Öffnen des Ordners fragt die Claude-App, ob du ihm vertraust. Erst mit deinem Ja gilt die Liste. Ohne sie würde der Lauf jeden Monat an Abfragen hängen bleiben, weil die App Erlaubnisse für wechselnde Befehle und für das Schreiben von Dateien nicht dauerhaft speichert.

**3. Der erste Lauf über die Aufgabe, mit dir am Rechner.** Screaming Frog, Ahrefs und ein Mail-Connector stehen bewusst nicht auf der Liste. Für sie fragt die App beim ersten Mal je Werkzeug einmal. Wähle "Immer erlauben", dann merkt sie es sich für alle späteren Läufe. Starte den ersten Lauf deshalb bei der Aufgabe über "Jetzt ausführen", öffne die neue Sitzung und erlaube die Abfragen. Es sind etwa zehn bis zwölf, einige gleich zu Beginn, einige nach dem Crawl.

Geplante Aufgaben laufen nur, wenn die Desktop-App geöffnet ist. Verpasste Läufe holt die App beim nächsten Start nach. Der Rechner muss zur geplanten Zeit wach und online sein, weil der Crawl je nach Seitengröße eine Weile dauert. Bleibt die Mail an einem Termin aus, sieh zuerst in der Sitzung der Aufgabe nach, ob dort eine Abfrage wartet.

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
      ergebnis.xlsx                Mailanhang, ohne Content-Gaps
      ergebnis-entwuerfe.md        Mail-Entwürfe
      bericht.md, bericht.html     Bericht, so wie er verschickt wird
    fehler.md                      nur wenn etwas schiefging
```

`laeufe/` steht in `.gitignore`. Ein `git clean -fdx` oder ein frischer Klon löscht deshalb auch die Verlaufsdateien. Sichere sie, wenn du das Repo neu aufsetzt. Ohne Verlauf gilt beim nächsten Lauf wieder alles als neu.

## Fehlerbehebung

| Meldung | Ursache und Lösung |
|---|---|
| Crawl nach wenigen Minuten angehalten: "Snippet liefert keine Embeddings" | Die Frühwarnung hat nach den ersten 60 Seiten keine Embeddings gefunden. Rendering auf JavaScript stellen, Schlüssel im Snippet prüfen, `PREVIEW_TEXT` auf false, Konfiguration neu speichern und den Lauf neu starten. |
| Hinweis "Crawl nicht vollständig" im Bericht | Während des Crawls ist die Verbindung abgerissen, zum Beispiel durch Schlafmodus oder WLAN-Wechsel. Der Lauf hat einmal neu gecrawlt. Rechner wach und online halten und den Lauf wiederholen. |
| Frog-Export ohne Embeddings | Die Konfiguration enthält kein Embedding-Setup, beim Custom-JavaScript-Weg fehlt das JavaScript-Rendering, oder `frog.embeddings_source` passt nicht zum Weg. |
| Mehrere oder keine Embedding-Spalten | `frog.custom_js_field` auf den genauen Spaltennamen setzen. |
| Dimension passt nicht | Modell im Frog und `embedding.model` unterscheiden sich. |
| `OPENAI_API_KEY ist nicht gesetzt` | `.env` fehlt oder ist leer. |
| Resend lehnt ab, Domain nicht verifiziert | DNS-Einträge in Resend prüfen, `RESEND_FROM` muss auf der verifizierten Domain liegen. |
| Verlaufsdatei nicht lesbar | Datei wurde von Hand beschädigt. Aus einem Backup zurückholen oder löschen; dann gilt beim nächsten Lauf wieder alles als neu. |
| Erster Crawl-Start bleibt ohne Aktivität | Im Frog-MCP war noch ein alter Crawl geladen. Der Lauf räumt das inzwischen selbst und startet neu. |
| Lauf ist nicht gestartet | Die Desktop-App war geschlossen. Er läuft beim nächsten Öffnen. |
| Lauf steht, keine Mail | In der Sitzung der geplanten Aufgabe wartet eine Berechtigungsabfrage. Dauerhaft erlauben, der Lauf geht weiter. |
| Jeden Monat neue Abfragen für Befehle oder Dateien | Die Aufgabe wurde nicht aus dem Repo-Ordner angelegt, oder dem Ordner wurde nicht vertraut. Dann gilt die Freigabeliste nicht. Aufgabe löschen und in einer Sitzung im Repo-Ordner neu anlegen. |
| "Bereits versendet", keine neue Mail | Der Bericht dieses Monats ging schon raus. Für eine bewusste Wiederholung "erneut senden" sagen. |
| "Ahrefs lieferte keine Broken Backlinks" | Null Zeilen gelten als Fehler: Units aufgebraucht, Filter zu streng oder eine Störung. Es geht bewusst keine Kundenmail raus. Units und Filter prüfen, Lauf wiederholen. |
| "Screaming Frog war belegt" oder "lief ein anderer Crawl" | Ein anderer Monitor oder ein eigener Crawl hat Frog über sechs Stunden belegt. Aufgaben auf verschiedene Tage legen. |
| "Der Crawl gehört nicht zu <Domain>" | Zwei Läufe sind sich in die Quere gekommen. Es wurde bewusst nichts verschickt. Lauf wiederholen. |
| Bericht kam nicht an | `fehler.md` im Laufordner lesen. Ist der Versand gescheitert, den Lauf wiederholen: Crawl und fertige Wettbewerber werden übersprungen. Hat Resend die Mail angenommen und sie ist trotzdem nicht da, zum Beispiel im Spam, sag "Broken Link Monitor erneut senden". Ist der Monat schon vorbei, nenne die Lauf-Kennung: `/broken-link-monitor mit Lauf-Kennung 2026-11`. |
