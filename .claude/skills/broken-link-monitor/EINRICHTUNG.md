# Einrichtung des Broken-Link-Monitors

Diese Anleitung ist für Claude. Sie gilt, wenn jemand den Monitor zum ersten Mal einrichten will, zum Beispiel mit "Richte mir den Broken Link Monitor ein" oder "/broken-link-monitor einrichten". Die Person war vermutlich im Vortrag und kennt sich mit Terminal und Konfigurationsdateien nicht unbedingt aus.

## Haltung

- Führe Schritt für Schritt. Sag am Anfang in drei Sätzen, was passiert und wie lange es ungefähr dauert: etwa 20 bis 30 Minuten Einrichtung, dann der erste Lauf.
- Erkläre in einfachen Worten. Kein Fachjargon ohne Erklärung, keine Codeblöcke ohne Satz davor, was sie tun.
- Stelle Fragen gebündelt und mit Beispielen. Biete sinnvolle Standardwerte an, damit die Person mit "passt" antworten kann.
- Alles, was du selbst erledigen kannst, erledigst du selbst. Die Person macht nur, was du nicht darfst oder nicht kannst.
- Schlüssel und Passwörter gehören nie in den Chat. Wenn jemand einen Schlüssel in den Chat schreibt, verwende ihn nicht, sag freundlich, dass er in die Datei `.env` gehört, und empfiehl, ihn beim Anbieter neu zu erzeugen.
- Melde dich nirgends mit Zugangsdaten an und lege keine Konten an. Das macht die Person selbst.
- Ändere die Datei `.env` nicht, solange sie in einem Editor geöffnet ist. Trage Werte ohne Geheimnis vorher ein und öffne die Datei erst dann für die Person. Sonst überschreibt der Editor deine Änderung beim Speichern.

## Grundsatz: Erledigtes überspringen

Vieles ist bei der Person vielleicht schon da: das Repo, die Umgebung, Schlüssel, die Frog-Konfiguration, ein verbundenes MCP oder eine verifizierte Resend-Domain. Prüfe jeden Schritt zuerst und überspringe, was schon erledigt ist. Sag das kurz, zum Beispiel: "Die Frog-Konfiguration liegt schon am richtigen Ort, diesen Schritt überspringen wir." Frag nie nach Dingen, die du selbst nachsehen kannst. Überschreibe nie vorhandene Dateien der Person, insbesondere nicht `.env`, `monitor.config.json` und die Verlaufsdateien.

## Schritt 0: Bestandsaufnahme

1. Suche ein vorhandenes Repo: `~/broken-link-matcher`, den aktuellen Arbeitsordner und auf dem Mac zusätzlich mit `mdfind -name monitor.config.json` nach einer bestehenden Einrichtung. Findest du eine, nenne den Ordner und frag kurz, ob sie genutzt oder bewusst eine neue angelegt werden soll.
2. Ist ein Repo da, führe dort `.venv/bin/python check_setup.py --inventory` aus. Ohne `.venv` geht das mit `python3 check_setup.py --inventory` nicht, dann gilt die Umgebung als fehlend. Die Ausgabe zeigt, was vorhanden ist, ohne Werte zu verraten.
3. Prüfe die Werkzeuge dieser Sitzung (Ahrefs-MCP, Frog-MCP, geplante Aufgaben), wie in Schritt 2 beschrieben. Gibt es geplante Aufgaben, sieh nach, ob schon eine für den Broken-Link-Monitor existiert.
4. Zeig der Person eine kurze Liste: "Schon erledigt" und "Noch zu tun". Mach dann nur mit den offenen Punkten weiter, in der Reihenfolge der Schritte unten.

## Schritt 1: Repo und Umgebung

1. Gibt es noch kein Repo, frage, wo der Monitor liegen soll. Standard: `~/broken-link-matcher`.
2. Klone das Repo dorthin: `git clone https://github.com/DanielKremer91/broken-link-matcher <ordner>`. Existiert der Ordner schon mit `cli.py`, nutze ihn und hole Neuerungen mit `git pull`.
3. Fehlt die Umgebung `.venv`, richte sie ein, im Repo-Ordner:
   - mit `uv`: `uv venv --python 3.11 .venv && uv pip install -r requirements.txt`
   - ohne `uv`, wenn `python3 --version` mindestens 3.11 zeigt: `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`
   - Fehlt beides, erkläre, wie man `uv` installiert (`brew install uv`, ohne Homebrew das Installationsskript von astral.sh), und warte.
4. Fehlt die Schlüsseldatei, lege sie an: `cp -n .env.example .env && chmod 600 .env`. Das `-n` verhindert, dass eine vorhandene `.env` mit eingetragenen Schlüsseln überschrieben wird.

## Schritt 2: Voraussetzungen prüfen

Prüfe selbst, welche Werkzeuge in dieser Sitzung verfügbar sind, und berichte das Ergebnis in einer kurzen Liste:

- **Ahrefs-MCP:** Es gibt ein Tool für `site-explorer-broken-backlinks`. Wenn nicht: Die Person verbindet Ahrefs in Claude unter Einstellungen, Connectors. Sie braucht dafür ein Ahrefs-Abo mit MCP-Zugang.
- **Screaming-Frog-MCP:** Es gibt Tools wie `sf_crawl` und `sf_list_allowed_base_directory`. Wenn nicht: Die Person installiert die MCP-Erweiterung von Screaming Frog für Claude nach der Anleitung von Screaming Frog. Screaming Frog braucht eine Lizenz.
- **Embedding-Anbieter:** Ein OpenAI-Schlüssel, alternativ Gemini oder ein lokales Ollama.

Fehlt ein MCP, erkläre, wie es verbunden wird, und mach mit den Schritten weiter, die ohne es gehen. Die Konfiguration kannst du trotzdem schreiben. Ist alles verbunden, reicht ein Satz dazu.

## Schritt 3: Fragen und Konfiguration

Gibt es schon eine `monitor.config.json`, frag nicht alles neu. Zeig die wichtigsten Werte als Liste und frag nur, ob sie noch stimmen oder was sich ändern soll. Ändere dann nur diese Werte.

Sonst frag in einer Nachricht, mit Beispielen und Standardwerten:

1. **Kundenname** für den Betreff der Mail, zum Beispiel "Fressnapf".
2. **Eigene Domain**, zum Beispiel `fressnapf.de`.
3. **Start-URL des Crawls**, zum Beispiel `https://www.fressnapf.de/magazin/`. Tipp: Ein Ratgeber- oder Magazinbereich passt meist am besten.
4. **Wettbewerber**, eine oder mehrere Domains, zum Beispiel `zooroyal.de`.
5. **Mailversand:** Resend, ein verbundener Mail-Connector (Outlook oder Gmail) oder nur als Datei. Dazu die Empfängeradresse.
6. **Name für die Textvorschläge** an die Websites, zum Beispiel "Vorname Nachname".
7. **Wie entstehen die Embeddings im Frog:** per Custom-JavaScript-Snippet oder über die eingebaute KI-Anbindung? Welches Modell? Standard: OpenAI `text-embedding-3-small`.

Erwähne die Ahrefs-Standardfilter in einem Satz: 100 Links pro Wettbewerber, nur Dofollow-Links aus dem Inhaltsbereich, ohne Spam, nur Ziele mit 404 oder 410, sortiert nach Domain Rating. Etwa 12 Ahrefs-Units pro Link. Frag, ob das passt.

Schreibe dann `monitor.config.json` im Repo-Ordner nach dem Muster von `config.example.json` in diesem Skill-Ordner:

- `repo_path` ist der absolute Repo-Pfad.
- `frog.config_file` ist `<Basisverzeichnis des Frog-MCP>/broken-link-monitor.seospiderconfig`. Das Basisverzeichnis liefert das Frog-Tool für das erlaubte Verzeichnis. Ohne Frog-MCP nimm vorläufig `~/seo_spider_mcp_server` und prüfe später.
- Wettbewerber klein, ohne `https://` und ohne Schrägstrich.
- `output_dir` ist `laeufe`.

Zeig die wichtigsten Werte in einer kurzen Liste und frag, ob alles stimmt.

## Schritt 4: Screaming Frog vorbereiten

Liegt die Frog-Konfiguration laut Bestandsaufnahme schon am richtigen Ort, frag nur: "Enthält sie das Embedding-Setup und JavaScript-Rendering?" Bei Ja überspringe diesen Schritt.

Sonst erkläre, dass Screaming Frog die eigenen Seiten crawlt und dabei für jede Seite ein Embedding erzeugt, eine Zahlenfolge, die den Inhalt beschreibt. Das richtet die Person einmal in Frog ein und speichert es als Konfigurationsdatei. Führe sie je nach Antwort aus Schritt 3:

- **Custom JavaScript:** Konfiguration, Benutzerdefiniert, Custom JavaScript, Snippet hinzufügen. Die Snippet-Bibliothek von Frog bietet Vorlagen, darunter für OpenAI-Embeddings. Den eigenen OpenAI-Schlüssel trägt die Person im Snippet ein, dasselbe Modell wie in der Konfiguration. Dann unter Konfiguration, Spider, Rendering auf JavaScript stellen. Das Snippet läuft nur mit JavaScript-Rendering.
- **KI-Anbindung:** Konfiguration, API-Zugang, KI, Anbieter verbinden und einen Embedding-Prompt für den Seiteninhalt anlegen.

Dann in beiden Fällen:

1. Umfang festlegen: nur HTML-Seiten, bei Bedarf auf den Bereich der Start-URL beschränken.
2. Optional ein paar Seiten testweise crawlen und prüfen, ob die Embedding-Spalte gefüllt ist.
3. Speichern über Datei, Konfiguration, Speichern unter. Wichtig: Im Dialog zuerst den Ordner `<Basisverzeichnis>` auswählen und dann nur den Dateinamen `broken-link-monitor.seospiderconfig` eintippen. Wird der ganze Pfad ins Namensfeld getippt, landet die Datei mit einem Doppelpunkt im Namen im Benutzerordner.
4. Hinweis: Beim Custom-JavaScript-Weg steht der API-Schlüssel in dieser Datei. Sie darf nie weitergegeben werden.

Wenn die Person "gespeichert" sagt, prüfe, ob die Datei an der richtigen Stelle liegt. Liegt sie mit Doppelpunkt im Namen im Benutzerordner (zum Beispiel `~/seo_spider_mcp_server:broken-link-monitor.seospiderconfig`), sag das und verschiebe sie an den richtigen Ort.

Lies die Datei nicht aus und zeig keine Inhalte daraus.

## Schritt 5: Mailversand

Sind `RESEND_API_KEY` und `RESEND_FROM` laut Bestandsaufnahme schon eingetragen, oder ist der gewählte Connector schon verbunden, überspringe diesen Schritt.

- **Resend:** Die Person meldet sich selbst bei resend.com an. Unter Domains muss eine Domain den Status "Verified" haben. Wenn nicht, erklär, dass Resend dafür DNS-Einträge anzeigt, die die Person oder die zuständige IT einträgt. Absender wird eine Adresse auf dieser Domain. Trag `RESEND_FROM=Broken Link Monitor <monitor@domain>` selbst in `.env` ein, bevor die Person die Datei öffnet. Den Schlüssel legt die Person unter API keys an: Name "Broken Link Monitor", Berechtigung "Sending access", nur diese Domain. Rate von bestehenden Schlüsseln mit vollem Zugriff ab.
- **Connector:** Die Person verbindet Outlook oder Gmail unter Einstellungen, Connectors. Dann ist nichts weiter nötig.
- **Datei:** Nichts zu tun. Der Bericht liegt nach jedem Lauf im Ordner `laeufe`.

## Schritt 6: Schlüssel eintragen

Sind alle nötigen Schlüssel laut Bestandsaufnahme eingetragen, überspringe diesen Schritt. Sonst nenne nur die fehlenden.

1. Öffne die Datei für die Person: `open -e <repo>/.env` (auf dem Mac in TextEdit).
2. Erkläre: Den OpenAI-Schlüssel direkt hinter `OPENAI_API_KEY=` einfügen, bei Resend den Schlüssel hinter `RESEND_API_KEY=`. Keine Leerzeichen, keine Anführungszeichen. Speichern mit Cmd+S und das Fenster schließen.
3. Warte, bis die Person "fertig" sagt.

## Schritt 7: Prüfen

Führe `.venv/bin/python check_setup.py` im Repo-Ordner aus. Zu jedem Kreuz steht eine Lösung. Erklär offene Punkte in eigenen, einfachen Worten, behebe, was du selbst beheben darfst, und prüfe erneut, bis "Alles bereit." erscheint.

## Schritt 8: Erster Lauf

Sag vorher, was passiert und was es kostet:

- Screaming Frog crawlt die Start-URL mit JavaScript-Rendering. Das kann je nach Größe eine bis mehrere Stunden dauern und kostet beim Embedding-Anbieter einige Cent pro tausend Seiten.
- Ahrefs liefert die Broken Backlinks, etwa 12 Units pro Link.
- Danach Wayback-Abruf, Matching und Live-Prüfung, etwa 5 bis 10 Minuten.
- Am Ende geht die Mail an die eingetragenen Empfänger.

Starte erst nach einem ausdrücklichen "Go". Führe dann den Lauf nach `SKILL.md` aus, Schritt 0 bis 7. Halte die Person bei langen Schritten mit kurzen Zwischenständen auf dem Laufenden.

## Schritt 9: Monatlich automatisch

Gibt es schon eine geplante Aufgabe für den Broken-Link-Monitor, zeig ihren Zeitplan und frag nur, ob er so bleiben soll. Leg keine zweite an.

Sonst frag, ob der Lauf monatlich automatisch kommen soll, zum Beispiel am 1. um 7 Uhr. Wenn ja und ein Werkzeug für geplante Aufgaben verfügbar ist, lege die Aufgabe an:

- Zeitplan als Cron: `0 7 1 * *`
- Prompt: `Geplanter Lauf ohne Rückfragen: Arbeite im Ordner <repo_path>. Lies .claude/skills/broken-link-monitor/SKILL.md und führe den Broken-Link-Monitor mit monitor.config.json aus.`

Erkläre dazu: Die Aufgabe läuft nur, wenn die Claude-App geöffnet ist. Verpasste Läufe holt sie beim nächsten Start nach. Der Rechner sollte zur geplanten Zeit wach sein.

Ohne Werkzeug für geplante Aufgaben erkläre, wie die Person die Aufgabe in der Claude-App selbst anlegt, mit genau diesem Prompt.

## Zum Schluss

Fasse in wenigen Sätzen zusammen, was eingerichtet ist, wo die Dateien liegen und wie man einen Lauf jederzeit von Hand startet: Claude im Repo-Ordner öffnen und `/broken-link-monitor` eingeben. Verweise auf `docs/checkliste.md` zum Abhaken.
