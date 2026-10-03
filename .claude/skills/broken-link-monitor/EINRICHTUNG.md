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

1. Gibt es noch kein Repo, schlag als Speicherort `~/broken-link-matcher` im Benutzerordner vor und frag kurz, ob das passt. Klone nicht einfach in den Ordner, in dem die Sitzung gerade läuft. Erstnutzer starten Claude oft in einem zufälligen Ordner, und der Monitor soll an einem festen, leicht auffindbaren Ort liegen. Fragt Claude dafür nach einer Berechtigung, erkläre in einem Satz, warum.
2. Klone das Repo dorthin: `git clone https://github.com/DanielKremer91/broken-link-matcher <ordner>`. Existiert der Ordner schon mit `cli.py`, nutze ihn und hole Neuerungen mit `git pull`.
3. Fehlt die Umgebung `.venv`, richte sie ein, im Repo-Ordner:
   - mit `uv`: `uv venv --python 3.11 .venv && uv pip install -r requirements.txt`
   - ohne `uv`, wenn `python3 --version` mindestens 3.11 zeigt: `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`
   - Fehlt beides, erkläre, wie man `uv` installiert (`brew install uv`, ohne Homebrew das Installationsskript von astral.sh), und warte.
4. Fehlt die Schlüsseldatei, lege sie an: `cp -n .env.example .env && chmod 600 .env`. Das `-n` verhindert, dass eine vorhandene `.env` mit eingetragenen Schlüsseln überschrieben wird.

## Schritt 2: Voraussetzungen prüfen

Prüfe selbst, welche Werkzeuge in dieser Sitzung verfügbar sind, und berichte das Ergebnis in einer kurzen Liste:

- **Ahrefs-MCP:** Es gibt ein Tool für `site-explorer-broken-backlinks`. Wenn nicht, erkläre: In der Claude-App unter Einstellungen, Connectors den Ahrefs-Connector hinzufügen und mit dem Ahrefs-Konto anmelden. Dafür braucht es ein Ahrefs-Abo mit MCP-Zugang. Danach eine neue Claude-Sitzung starten, damit die Tools erscheinen.
- **Screaming-Frog-MCP:** Es gibt Tools wie `sf_crawl` und `sf_list_allowed_base_directory`. Wenn nicht, erkläre Schritt für Schritt:
  1. Screaming Frog SEO Spider ab Version 24.1 mit Lizenz installieren, am Mac im Ordner Programme. Speichermodus ist die Datenbank, das ist der Standard.
  2. In Screaming Frog unter File, Settings, MCP Server die Node.js-Laufzeit akzeptieren und aktivieren.
  3. Die STDIO-MCP-Erweiterung `spider-mcp.mcpb` von Screaming Frog herunterladen. Link und Anleitung stehen im Benutzerhandbuch von Screaming Frog im Abschnitt zum MCP Server: https://www.screamingfrog.co.uk/seo-spider/user-guide/configuration/
  4. In der Claude-App unter Einstellungen, Erweiterungen auf "Install Extension" klicken und die Datei `spider-mcp.mcpb` wählen.
  5. Claude komplett beenden, neu öffnen und eine neue Sitzung starten.
  Bei der Fehlermeldung "Unexpected non-whitespace character": Erweiterung entfernen, Claude neu starten, Screaming Frog auf mindestens 24.1 aktualisieren und die Erweiterung neu installieren. Hilft das nicht, in Screaming Frog die Sprache auf eine feste Sprache statt "System" stellen.
- **Embedding-Anbieter:** Ein OpenAI-Schlüssel, alternativ Gemini oder ein lokales Ollama.

Fehlt ein MCP, erkläre, wie es verbunden wird, und mach mit den Schritten weiter, die ohne es gehen. Die Konfiguration kannst du trotzdem schreiben. Ist alles verbunden, reicht ein Satz dazu.

## Schritt 3: Fragen und Konfiguration

Gibt es schon eine `monitor.config.json`, frag nicht alles neu. Zeig die wichtigsten Werte als Liste und frag nur, ob sie noch stimmen oder was sich ändern soll. Ändere dann nur diese Werte.

Sonst frag in einer Nachricht, mit Beispielen und Standardwerten:

1. **Kundenname** für den Betreff der Mail, zum Beispiel "Fressnapf".
2. **Eigene Domain**, zum Beispiel `fressnapf.de`.
3. **Start-URL des Crawls**, zum Beispiel `https://www.fressnapf.de/magazin/`. Tipp: Ein Ratgeber- oder Magazinbereich passt meist am besten.
4. **Wettbewerber**, eine oder mehrere Domains, zum Beispiel `zooroyal.de`.
5. **Wohin soll der Bericht gehen, und wie?** Dazu die Empfängeradresse. Erkläre die drei Wege in je einem Satz:
   - **Outlook oder Gmail** über einen in Claude verbundenen Mail-Connector. Am einfachsten, wenn der Connector schon verbunden ist.
   - **Resend**, ein Versanddienst für automatische Mails. Braucht ein eigenes, kostenloses Konto und eine bestätigte Domain. Lohnt sich, wenn die Mail regelmäßig von einer festen Absenderadresse kommen soll. Ich helfe beim Einrichten.
   - **Nur als Datei** im Ordner `laeufe`. Kein Versand, sofort startklar. Später jederzeit umstellbar.
   Wer unsicher ist: mit "nur als Datei" starten.
6. **Unterschrift für die Mail-Entwürfe:** Das Tool schreibt zu jeder Chance einen Entwurf für eine kurze Mail an die verlinkende Website, mit dem Vorschlag, den toten Link durch die eigene Seite zu ersetzen. Mit welchem Namen sollen diese Entwürfe unterschrieben sein? Zum Beispiel "Daniel Kremer". Verschickt werden die Entwürfe nie automatisch.

Nur wenn die Bestandsaufnahme schon eine Frog-Konfiguration gefunden hat, frag zusätzlich:

7. **Wie entstehen die Embeddings in dieser Frog-Konfiguration:** per Custom-JavaScript-Snippet oder über die eingebaute KI-Anbindung? Mit welchem Modell? Standard: OpenAI `text-embedding-3-small`.

Ohne Frog-Konfiguration frag das nicht hier. Es wird in Schritt 4 gemeinsam festgelegt. Trag vorläufig `custom_javascript` und `text-embedding-3-small` ein und passe es in Schritt 4 an.

Erwähne die Ahrefs-Standardfilter in einem Satz: 100 Links pro Wettbewerber, nur Dofollow-Links aus dem Inhaltsbereich, ohne Spam, nur Ziele mit 404 oder 410, sortiert nach Domain Rating. Etwa 12 Ahrefs-Units pro Link. Frag, ob das passt.

Schreibe dann `monitor.config.json` im Repo-Ordner nach dem Muster von `config.example.json` in diesem Skill-Ordner:

- `repo_path` ist der absolute Repo-Pfad.
- `frog.config_file` ist `<Basisverzeichnis des Frog-MCP>/broken-link-monitor.seospiderconfig`. Das Basisverzeichnis liefert das Frog-Tool für das erlaubte Verzeichnis. Ohne Frog-MCP nimm vorläufig `~/seo_spider_mcp_server` und prüfe später.
- Wettbewerber klein, ohne `https://` und ohne Schrägstrich.
- `output_dir` ist `laeufe`.

Zeig die wichtigsten Werte in einer kurzen Liste und frag, ob alles stimmt.

## Schritt 4: Screaming Frog vorbereiten

Liegt die Frog-Konfiguration laut Bestandsaufnahme schon am richtigen Ort, frag nur: "Enthält sie das Embedding-Setup und JavaScript-Rendering?" Bei Ja überspringe diesen Schritt.

Sonst erkläre, dass Screaming Frog die eigenen Seiten crawlt und dabei für jede Seite ein Embedding erzeugt, eine Zahlenfolge, die den Inhalt beschreibt. So kann das Tool später Seiten mit ähnlichem Inhalt finden. Das richtet die Person einmal in Frog ein und speichert es als Konfigurationsdatei.

Gibt es noch kein Embedding-Setup, stell die beiden Wege kurz vor und lass die Person wählen:

- **Eingebaute KI-Anbindung:** einfacher einzurichten, kein JavaScript-Rendering nötig, der Schlüssel wird in Frog hinterlegt. Gut für den Einstieg.
- **Custom-JavaScript-Snippet:** flexibler, braucht aber JavaScript-Rendering, und der Schlüssel steht im Snippet und damit in der Konfigurationsdatei.

Trag die Wahl als `frog.embeddings_source` (`ai` oder `custom_javascript`) und das Modell als `embedding.model` in `monitor.config.json` ein.

**Wichtig in beiden Fällen: nur der Hauptinhalt.** Erkläre: Das Embedding soll nur den eigentlichen Inhalt einer Seite beschreiben. Kommen Navigation, Footer, Cookie-Banner oder Teaserlisten mit hinein, sehen sich alle Seiten ähnlicher, als sie sind, und die Vorschläge werden schlechter. Jede Website ist anders gebaut, deshalb lohnt sich ein kurzer Blick.

Hilf dabei so: Hol dir mit `curl -sL` das HTML von zwei, drei Seiten unterhalb der Start-URL und schau, ob es `main` oder `article` gibt und ob Navigation und Footer als `nav` und `footer` ausgezeichnet sind. Schlag daraus konkrete Selektoren vor, zum Beispiel `.article-body` für den Inhalt oder `.teaser-list, .author-box` für Ausschlüsse.

**Gleiches Modell:** Das Modell in Frog muss exakt dem Modell in `monitor.config.json` entsprechen. Damit bettet das Tool auch die toten Wettbewerberseiten ein. In der `.env` steht nur der Schlüssel, nicht das Modell. Passen die Modelle nicht zusammen, bricht der Lauf beim Dimensionscheck ab. Standard ist `text-embedding-3-small`.

Führe dann je nach Wahl:

- **Custom JavaScript:** Die Vorlage liegt im Repo unter `frog/main-content-embedding.js`. Sie findet den Hauptinhalt auf vielen Seiten von selbst, teilt lange Texte in Abschnitte und mittelt die Embeddings. Die Person öffnet in Frog Konfiguration, Benutzerdefiniert, Custom JavaScript, fügt ein Snippet vom Typ "Extraction" hinzu und kopiert den Inhalt der Datei hinein. Öffne ihr die Datei dazu mit `open -e <repo>/frog/main-content-embedding.js`, nur zum Kopieren. Den OpenAI-Schlüssel trägt sie erst im Editor von Frog ein, nie in der Datei im Repo. Dort prüft sie auch, dass `MODEL` zur Konfiguration passt. Deine Selektoren gehören in `CONTENT_ROOT_SELECTOR` und `EXTRA_EXCLUDE_SELECTOR`. Unter Konfiguration, Spider, Rendering muss JavaScript eingestellt sein. Tipp: Mit `PREVIEW_TEXT = true` zeigt Frog nach einem Testcrawl von ein paar Seiten den Text, der eingebettet würde, ohne OpenAI-Kosten. Danach wieder auf `false` stellen.
- **KI-Anbindung:** Unter Konfiguration, API-Zugang, KI den Anbieter verbinden und in der Prompt-Konfiguration einen Eintrag mit der Kategorie "Embeddings" und dem Inhalt "Page Text" anlegen, mit dem Modell aus der Konfiguration. "Page Text" richtet sich nach Konfiguration, Content, Content Area. Dort sind Navigation und Footer schon ausgeschlossen. Deine Selektoren für weitere Ausschlüsse trägt die Person dort ein. Hinweis: Bei sehr langen Seiten kann die KI-Anbindung den Text kürzen, das Snippet teilt ihn dagegen auf.

**Pflicht-Rückfrage beim Snippet-Weg:** Frag ausdrücklich: "Steht unter Konfiguration, Spider, Rendering jetzt JavaScript?" Erklär dazu in einem Satz: Ohne JavaScript-Rendering führt Screaming Frog das Snippet gar nicht aus, und es entstehen keine Embeddings. Mach erst nach einem klaren Ja weiter. Empfiehl als Beweis einen Testcrawl über wenige Seiten mit `PREVIEW_TEXT = true`: Erscheint in der Custom-JavaScript-Spalte Text, läuft das Snippet. Danach `PREVIEW_TEXT` wieder auf `false` stellen. Zusätzlich prüft der Monitor bei jedem Lauf nach den ersten 50 Seiten eine Stichprobe und hält den Crawl an, wenn keine Embeddings entstehen.

Dann in beiden Fällen:

1. Umfang festlegen: nur HTML-Seiten, bei Bedarf auf den Bereich der Start-URL beschränken.
2. Optional ein paar Seiten testweise crawlen und prüfen, ob die Embedding-Spalte gefüllt ist.
3. Speichern über Datei, Konfiguration, Speichern unter. Wichtig: Im Dialog zuerst den Ordner `<Basisverzeichnis>` auswählen und dann nur den Dateinamen `broken-link-monitor.seospiderconfig` eintippen. Wird der ganze Pfad ins Namensfeld getippt, landet die Datei mit einem Doppelpunkt im Namen im Benutzerordner.
4. Hinweis: Beim Custom-JavaScript-Weg steht der API-Schlüssel in dieser Datei. Sie darf nie weitergegeben werden.

Wenn die Person "gespeichert" sagt, prüfe, ob die Datei an der richtigen Stelle liegt. Liegt sie mit Doppelpunkt im Namen im Benutzerordner (zum Beispiel `~/seo_spider_mcp_server:broken-link-monitor.seospiderconfig`), sag das und verschiebe sie an den richtigen Ort.

Lies die Datei nicht aus und zeig keine Inhalte daraus.

## Schritt 5: Mailversand

Sind `RESEND_API_KEY` und `RESEND_FROM` laut Bestandsaufnahme schon eingetragen, oder ist der gewählte Connector schon verbunden, überspringe diesen Schritt.

- **Resend:** Hat die Person noch kein Konto, führe sie durch:
  1. Auf resend.com ein Konto anlegen. Der kostenlose Tarif reicht für einen monatlichen Bericht.
  2. Unter Domains auf "Add domain" klicken. Empfiehl eine Subdomain wie `mail.firma.de`, dann bleibt das normale Mail-Setup der Firma unberührt.
  3. Resend zeigt einige DNS-Einträge an. Die trägt die Person oder die zuständige IT beim Domain-Anbieter ein. Das kann einige Minuten bis Stunden dauern, bis Resend die Domain als "Verified" zeigt.
  4. Bis dahin kann der Monitor mit "nur als Datei" laufen. Stell `mail.method` vorübergehend auf `file` und später zurück auf `resend`.
  Hat die Person schon ein Konto, meldet sie sich selbst an. Unter Domains muss eine Domain den Status "Verified" haben. Absender wird eine Adresse auf dieser Domain. Trag `RESEND_FROM=Broken Link Monitor <monitor@domain>` selbst in `.env` ein, bevor die Person die Datei öffnet. Den Schlüssel legt die Person unter API keys an: Name "Broken Link Monitor", Berechtigung "Sending access", nur diese Domain. Rate von bestehenden Schlüsseln mit vollem Zugriff ab.
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
- Danach Wayback-Abruf, Matching, Live-Prüfung und Mail-Entwürfe, etwa 10 bis 30 Minuten.
- Der Rechner muss die ganze Zeit wach und online bleiben. Gegen das Einschlafen bei Untätigkeit startet der Lauf einen Schlafschutz. Den Laptop bitte nicht zuklappen und nicht das WLAN wechseln, sonst bricht dem Crawl die Verbindung ab. Der Lauf prüft danach, ob der Crawl vollständig war, und startet ihn bei Bedarf einmal neu.
- Am Ende geht die Mail an die eingetragenen Empfänger.

Erkläre auch: Der Crawl läuft über das MCP in einer eigenen Screaming-Frog-Instanz im Hintergrund, ohne Fenster. Im geöffneten Frog-Fenster ist er deshalb nicht zu sehen. Den Fortschritt meldest du. Nach dem Ende erscheint der Crawl in Frog unter File, Crawls.

Starte erst nach einem ausdrücklichen "Go". Führe dann den Lauf nach `SKILL.md` aus, Schritt 0 bis 7. Halte die Person bei langen Schritten mit kurzen Zwischenständen auf dem Laufenden, zum Beispiel alle 15 Minuten mit der Zahl gecrawlter URLs.

## Schritt 9: Monatlich automatisch

Gibt es schon eine geplante Aufgabe für den Broken-Link-Monitor, zeig ihren Zeitplan und frag nur, ob er so bleiben soll. Leg keine zweite an.

Sonst frag, ob der Lauf monatlich automatisch kommen soll, zum Beispiel am 1. um 7 Uhr. Wenn ja und ein Werkzeug für geplante Aufgaben verfügbar ist, lege die Aufgabe an:

- Zeitplan als Cron: `0 7 1 * *`
- Prompt: `Geplanter Lauf ohne Rückfragen: Arbeite im Ordner <repo_path>. Lies .claude/skills/broken-link-monitor/SKILL.md und führe den Broken-Link-Monitor mit monitor.config.json aus.`

Erkläre dazu: Die Aufgabe läuft nur, wenn die Claude-App geöffnet ist. Verpasste Läufe holt sie beim nächsten Start nach. Der Rechner sollte zur geplanten Zeit wach sein.

Ohne Werkzeug für geplante Aufgaben erkläre, wie die Person die Aufgabe in der Claude-App selbst anlegt, mit genau diesem Prompt.

## Zum Schluss

Fasse in wenigen Sätzen zusammen, was eingerichtet ist, wo die Dateien liegen und wie man einen Lauf jederzeit von Hand startet. Nenne dabei den Repo-Ordner mit vollem Pfad und erkläre den Begriff: Das ist der Ordner, in den alles heruntergeladen wurde und in dem Konfiguration und Schlüssel liegen. Für einen Lauf von Hand startet die Person in der Claude-App im Bereich Code eine neue Sitzung, wählt diesen Ordner und gibt `/broken-link-monitor` ein. Erwähne, dass sich Einstellungen jederzeit ändern lassen, zum Beispiel mit "Nimm zooplus.de als weiteren Wettbewerber in den Broken Link Monitor auf", und dass Änderungen ab dem nächsten Lauf gelten. Verweise auf `docs/checkliste.md` zum Abhaken.
