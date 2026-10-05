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

1. Gibt es noch kein Repo, schlag als Speicherort `~/broken-link-matcher` im Benutzerordner vor und frag kurz, ob das passt. Gibt es schon eine Einrichtung für einen anderen Kunden, schlag einen eigenen Ordner vor, zum Beispiel `~/broken-link-matcher-<kunde>`. Eine Einrichtung gehört immer zu genau einem Kunden. Klone nicht einfach in den Ordner, in dem die Sitzung gerade läuft. Erstnutzer starten Claude oft in einem zufälligen Ordner, und der Monitor soll an einem festen, leicht auffindbaren Ort liegen. Fragt Claude dafür nach einer Berechtigung, erkläre in einem Satz, warum.
2. Hast du das Repo schon woanders geklont, zum Beispiel in den Sitzungsordner, um die Anleitung zu lesen, und liegt dort noch keine Einrichtung (keine `.env`, keine `monitor.config.json`, kein Ordner `laeufe`): Verschiebe diesen Klon mit `mv` an den Zielort, statt ein zweites Mal zu klonen. Sag der Person in einem Satz, dass du den Ordner verschoben hast. Eine dort schon angelegte `.venv` löschst du nach dem Verschieben und legst sie neu an, weil sie feste Pfade enthält.
3. Sonst klone das Repo dorthin: `git clone https://github.com/DanielKremer91/broken-link-matcher <ordner>`. Existiert der Ordner schon mit `cli.py`, nutze ihn und hole Neuerungen mit `git pull`.
4. Fehlt die Umgebung `.venv`, richte sie ein, im Repo-Ordner:
   - mit `uv`: `uv venv --python 3.11 .venv && uv pip install -r requirements.txt`
   - ohne `uv`, wenn `python3 --version` mindestens 3.11 zeigt: `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`
   - Fehlt beides, erkläre, wie man `uv` installiert (`brew install uv`, ohne Homebrew das Installationsskript von astral.sh), und warte.
5. Fehlt die Schlüsseldatei, lege sie an: `cp -n .env.example .env && chmod 600 .env`. Das `-n` verhindert, dass eine vorhandene `.env` mit eingetragenen Schlüsseln überschrieben wird.

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
- `frog.config_file` ist `<Basisverzeichnis des Frog-MCP>/broken-link-monitor-<kunde>.seospiderconfig`. `<kunde>` ist der Kundenname klein geschrieben, Leerzeichen als Bindestrich, Umlaute als ae, oe, ue, zum Beispiel `broken-link-monitor-fressnapf.seospiderconfig`. So bekommt jeder Kunde seine eigene Frog-Konfiguration. Das Basisverzeichnis liefert das Frog-Tool für das erlaubte Verzeichnis. Ohne Frog-MCP nimm vorläufig `~/seo_spider_mcp_server` und prüfe später.
- Wettbewerber klein, ohne `https://` und ohne Schrägstrich.
- `output_dir` ist `laeufe`.

Zeig die wichtigsten Werte in einer kurzen Liste und frag, ob alles stimmt.

## Schritt 4: Screaming Frog vorbereiten

Das ist der einzige Schritt, bei dem die Person länger selbst in einem anderen Programm arbeitet. Hier gehen Erstnutzer am ehesten verloren. Führe deshalb besonders kleinschrittig.

### Vorab: Gibt es schon eine passende Konfiguration?

Liegen im Basisverzeichnis schon Frog-Konfigurationen (`broken-link-monitor*.seospiderconfig`), nenne sie und frag, ob eine davon für genau diese Website angelegt wurde und Embedding-Setup und JavaScript-Rendering enthält. Nur dann trag ihren Pfad als `frog.config_file` ein und spring direkt zum Probe-Crawl (4.6). Übernimm nie die Konfiguration einer anderen Website: Snippet und Ausschlüsse sind auf deren Seitenaufbau zugeschnitten und liefern bei einer fremden Website schlechte Embeddings.

### So führst du durch diesen Schritt

- **Ein Teilschritt pro Nachricht.** Jede Nachricht enthält genau eine Aktion, den Klickpfad und am Ende den Satz: "Schreib 'weiter', wenn das erledigt ist." Dann wartest du. Schick nie mehrere Teilschritte auf einmal.
- **Klickpfade immer in beiden Sprachen,** so wie unten angegeben, zuerst Deutsch, dann Englisch. Frag nicht nach der Sprache der Oberfläche.
- Sieht bei der Person etwas anders aus, hilf zuerst dort weiter, bevor du zum nächsten Teilschritt gehst. Menüs können je nach Frog-Version leicht abweichen.
- Lies die Konfigurationsdatei nie aus und zeig keine Inhalte daraus. Beim Snippet-Weg steht ein API-Schlüssel darin.

### Einstieg (eine Nachricht, noch ohne Aktion)

Erkläre in drei, vier Sätzen: Screaming Frog crawlt die eigenen Seiten und erzeugt für jede Seite ein Embedding, eine Zahlenfolge, die den Inhalt beschreibt. So findet das Tool später Seiten mit ähnlichem Inhalt. Das wird einmal in Frog eingestellt und als Datei gespeichert. Es sind fünf kurze Handgriffe, danach prüfst du mit einem kleinen Probe-Crawl, ob alles funktioniert.

Gibt es noch kein Embedding-Setup, nenne die zwei Wege und empfiehl den ersten:

- **Snippet-Weg (empfohlen, erprobt):** Ein fertiges JavaScript-Snippet aus diesem Repo zieht den Hauptinhalt jeder Seite heraus und erzeugt das Embedding. Braucht JavaScript-Rendering. Der OpenAI-Schlüssel steht dann im Snippet und damit in der Konfigurationsdatei.
- **KI-Anbindung von Frog:** Frog erzeugt die Embeddings selbst aus dem Seitentext. Der Schlüssel wird in Frog hinterlegt. In diesem Ablauf weniger erprobt.

Trag die Wahl als `frog.embeddings_source` (`custom_javascript` oder `ai`) und das Modell als `embedding.model` in `monitor.config.json` ein.

Bereite dann im Hintergrund vor, ohne die Person damit aufzuhalten:

- **Hauptinhalt:** Das Embedding soll nur den eigentlichen Inhalt beschreiben. Kommen Navigation, Footer, Cookie-Banner oder Teaserlisten mit hinein, sehen sich alle Seiten ähnlicher, als sie sind. Hol dir mit `curl -sL` das HTML von zwei, drei Seiten unterhalb der Start-URL. Schau, ob es `main` oder `article` gibt und welche Bereiche zusätzlich auszuschließen sind, zum Beispiel Bildnachweise, Autorenboxen oder Teaserlisten. Leite daraus konkrete Selektoren ab. Die Vorlage kommt oft ohne aus; dann sag das.
- **Dateiname:** der Name aus `frog.config_file`, zum Beispiel `broken-link-monitor-fressnapf.seospiderconfig`.
- **Gleiches Modell:** Das Modell in Frog muss exakt `embedding.model` entsprechen. Damit bettet das Tool auch die toten Wettbewerberseiten ein. In der `.env` steht nur der Schlüssel, nicht das Modell.

### Teilschritte beim Snippet-Weg

**4.1 Rendering auf JavaScript stellen.**
Klickpfad: `Konfiguration > Spider`, Reiter `Rendering`, Auswahl `JavaScript` statt `Nur Text`. Englisch: `Configuration > Spider`, Tab `Rendering`, `JavaScript` statt `Text Only`. Mit OK bestätigen.
Ein Satz dazu: Ohne JavaScript-Rendering führt Frog das Snippet gar nicht aus.

**4.2 Snippet anlegen.**
Klickpfad: `Konfiguration > Eigene > Eigenes JavaScript`, dann `Hinzufügen`. Englisch: `Configuration > Custom > Custom JavaScript`, dann `Add`.
In der neuen Zeile: Typ `Extraktion` (`Extraction`) und als Name `Embeddings <Kunde>`, zum Beispiel `Embeddings Fressnapf`. Der Name muss mit "Embeddings" beginnen, daran erkennt der Monitor später die Spalte.

**4.3 Vorlage einfügen.**
Öffne der Person die Vorlage mit `open -e <repo>/frog/main-content-embedding.js`. Sie markiert alles (Cmd+A), kopiert (Cmd+C), klickt in Frog in der Snippet-Zeile auf den Knopf `JS`, um den Editor zu öffnen, und fügt dort alles ein (Cmd+V). Die Datei im Repo bleibt unverändert und wird wieder geschlossen.

**4.4 Drei Zeilen im Frog-Editor anpassen.**
Nenne die Zeilen wörtlich, so wie sie nach der Änderung aussehen sollen:
- `const OPENAI_API_KEY = '...';` mit dem eigenen OpenAI-Schlüssel zwischen den Anführungszeichen. Der Schlüssel gehört nur hierher, nie in den Chat und nie in die Datei im Repo.
- `const MODEL = '<embedding.model>';` nur prüfen, ob es stimmt.
- Falls du Selektoren ermittelt hast: `const CONTENT_ROOT_SELECTOR = '...';` und `const EXTRA_EXCLUDE_SELECTOR = '...';` mit deinen Werten. Sonst bleiben beide leer.
Danach den Editor und das Fenster mit OK schließen.

**4.5 Konfiguration auf dem Schreibtisch speichern.**
Klickpfad: `Konfiguration > Profile > Speichern unter...`. Englisch: `Configuration > Profiles > Save As...`. In älteren Versionen: `Datei > Konfiguration > Speichern unter...` (`File > Configuration > Save As...`).
Im Speichern-Dialog links **Schreibtisch** wählen und als Namen genau den Dateinamen aus der Vorbereitung eintippen. Gib den Namen zum Kopieren an.
Hinweis in einem Satz: Diese Datei enthält den Schlüssel. Sie wird nie weitergegeben.

Schreibt die Person "weiter", verschiebst du die Datei selbst an den richtigen Ort:
`.venv/bin/python place_frog_config.py --target "<frog.config_file>"`
- Exit-Code 0: Sag, dass die Datei jetzt am richtigen Ort liegt. Die Person muss nichts weiter tun.
- Exit-Code 1: nichts gefunden. Bitte die Person, noch einmal zu speichern, und nenne Ort und Namen erneut.
- Exit-Code 2: mehrere Kandidaten. Zeig die Liste, frag, welche es ist, und ruf das Skript mit `--source "<Datei>"` erneut auf.

### Teilschritte bei der KI-Anbindung

**4.1 Anbieter verbinden.** `Konfiguration > API-Zugang > KI`, Anbieter wählen, Schlüssel eintragen, verbinden. Englisch: `Configuration > API Access > AI`.
**4.2 Embedding-Prompt anlegen.** Im selben Fenster unter `Prompt-Konfiguration` (`Prompt Configuration`) einen Prompt hinzufügen: Kategorie Embeddings, Inhalt `Seitentext` (`Page Text`), Modell wie `embedding.model`. In der Bibliothek gibt es dafür die Vorlage "Extract embeddings from page content".
**4.3 Einbettungen einschalten.** `Konfiguration > Inhalt > Einbettungen` (`Configuration > Content > Embeddings`): aktivieren und den Prompt aus 4.2 auswählen.
**4.4 Inhaltsbereich prüfen.** `Konfiguration > Inhalt > Bereich` (`Configuration > Content > Area`): Navigation und Footer sind schon ausgeschlossen. Deine zusätzlichen Ausschlüsse trägt die Person hier ein. Der Seitentext richtet sich nach dieser Einstellung.
**4.5 Speichern** wie beim Snippet-Weg, danach verschiebst du die Datei mit `place_frog_config.py`.

### 4.6 Probe-Crawl: funktioniert die Konfiguration?

Sag der Person, was jetzt passiert: Du crawlst zur Probe etwa 60 Seiten, das dauert zwei bis drei Minuten und kostet beim Embedding-Anbieter weniger als einen Cent. Der Crawl läuft unsichtbar im Hintergrund. Die Person muss nichts tun.

1. Frag den Zustand mit dem Fortschritts-Tool ab. Läuft gerade ein Crawl (`SpiderActiveState`), warte nicht darauf und brich ihn nicht ab: Sag es der Person und frag, wie es weitergehen soll. Ist ein alter Crawl geladen (Zustand ist nicht `SpiderNoDataIdleState`), räume ihn mit dem Tool zum Verwerfen (`sf_clear_crawl`). Gespeicherte Crawls bleiben dabei erhalten. Ohne dieses Räumen bleibt der erste Start ohne Aktivität.
2. Starte den Crawl: `crawl_url` = `start_url`, `config_path` = `frog.config_file`, `crawl_name` = `blm-probe-<kunde>`.
3. Frag den Fortschritt etwa alle 30 Sekunden ab, bis mindestens 60 URLs abgeschlossen sind. Zum Warten nutzt du das verfügbare Warte-Werkzeug. Sind nach zwei Minuten noch keine URLs abgeschlossen, starte einmal neu. Nach fünf Minuten nimmst du, was da ist.
4. Halte den Crawl an (`sf_pause_crawl`). Solange er läuft, verweigert Frog jeden Export.
5. Exportiere die Stichprobe:
   - **custom_javascript:** Liste die Datenfelder des Elements `Custom JavaScript`, Filter `All`. Das Embedding-Feld beginnt mit "Embeddings". Exportiere mit dem Tool für SEO-Element-URLs die Felder `Address`, `Content Type`, `Status Code` und das Embedding-Feld nach `broken-link-monitor/probe-<kunde>.ndjson`, höchstens 300 Zeilen. Die Antwort des Tools enthält eine sehr lange Beispielzeile mit Zahlen. Lies sie nicht aus.
   - **ai:** Exportiere mit dem Embedding-Export-Tool nach `broken-link-monitor/probe-<kunde>.csv`.
6. Prüfe: `.venv/bin/python frog_probe.py "<absoluter Pfad>"`, beim Snippet-Weg mit `--field "<Embedding-Feld>"`.
7. Verwirf den Probe-Crawl (`sf_clear_crawl`) und lösche die Probe-Datei.
8. Sag das Ergebnis in einfachen Worten:
   - `ok`: "Die Konfiguration funktioniert: N von M Seiten haben ein Embedding." Vergleiche `dimension` mit dem Modell: `text-embedding-3-small` hat 1536, `text-embedding-3-large` 3072, `text-embedding-ada-002` 1536, Gemini `text-embedding-004` 768. Passt es nicht, stimmt das Modell im Snippet nicht mit `embedding.model` überein. Dann zurück zu 4.4.
   - `keine_embeddings`: Nenne die häufigsten Ursachen und geh mit der Person zum passenden Teilschritt zurück: Rendering steht nicht auf JavaScript (4.1), Schlüssel im Snippet fehlt oder ist falsch (4.4), `PREVIEW_TEXT` steht auf `true` (4.4), bei der KI-Anbindung sind die Einbettungen nicht eingeschaltet (4.3). Danach neu speichern (4.5) und den Probe-Crawl wiederholen.
   - `zu_wenig_daten`: Die Start-URL liefert zu wenige HTML-Seiten. Prüfe mit der Person die Start-URL.
9. Erwähne: Der Probe-Crawl steht in Frog unter `Datei > Crawls` (`File > Crawls`) mit dem Namen `blm-probe-<kunde>` und kann dort gelöscht werden.

Scheitert der Probe-Crawl an etwas anderem, zum Beispiel weil das Frog-MCP nicht verbunden ist, sag das offen. Dann zeigt sich erst im ersten Lauf, ob die Konfiguration funktioniert; die Frühwarnung prüft dort nach den ersten Seiten.

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
- Danach Abruf aus der Wayback Machine, Matching, Live-Prüfung und Mail-Entwürfe, etwa 10 bis 30 Minuten.
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
