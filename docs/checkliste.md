# Checkliste: Broken-Link-Monitor einrichten

Zum Abhaken. Details zu jedem Punkt stehen in [monatlicher-workflow.md](monatlicher-workflow.md).

## Zugänge

- [ ] Claude-Desktop-App installiert, Claude Code nutzbar
- [ ] Ahrefs-Abo mit MCP-Zugang, Ahrefs-MCP in Claude verbunden
- [ ] Screaming Frog mit Lizenz, MCP-Erweiterung in Claude verbunden
- [ ] OpenAI-Schlüssel (oder Gemini oder Ollama)
- [ ] Optional: Resend-Konto, oder Outlook- bzw. Gmail-Connector in Claude

## Einrichtung

- [ ] Repo geklont und `uv venv && uv pip install -r requirements.txt` ausgeführt
- [ ] Frog: KI-Anbieter verbunden und Embedding-Prompt angelegt
- [ ] Frog: Modell notiert, zum Beispiel `text-embedding-3-small`
- [ ] Frog: Konfiguration im MCP-Basisverzeichnis gespeichert
- [ ] `.env` aus `.env.example` angelegt, Schlüssel eingetragen, `chmod 600 .env`
- [ ] Resend: Domain verifiziert, Schlüssel und Absender in `.env`
- [ ] `monitor.config.json` aus der Vorlage angelegt und ausgefüllt
- [ ] Gleiches Embedding-Modell in Frog und `monitor.config.json`
- [ ] Wettbewerber als Domain ohne `https://` eingetragen
- [ ] `.venv/bin/python check_setup.py` zeigt nur Haken

## Erster Lauf

- [ ] In Claude Code im Repo `/broken-link-monitor` ausgeführt
- [ ] Berechtigungen für MCP-Tools und Shell-Befehle erlaubt
- [ ] Bericht angekommen, Excel und Entwürfe geprüft
- [ ] Stichprobe: drei Vorschläge von Hand angesehen, passen sie thematisch?

## Automatisierung

- [ ] Geplante Aufgabe angelegt, zum Beispiel am 1. des Monats um 7 Uhr
- [ ] Einmal "Jetzt ausführen" getestet (ein zweiter Lauf im selben Monat liefert denselben Bericht)
- [ ] Desktop-App bleibt geöffnet, Mac zur Laufzeit wach
- [ ] Ordner `laeufe/` mit den Verlaufsdateien ist im Backup

## Vor jedem Outreach

- [ ] Nur Zeilen mit Live-Prüfung "bestätigt" anschreiben
- [ ] Vorschlagsseite öffnen: Ersetzt sie den toten Inhalt wirklich?
- [ ] Mail-Entwurf lesen und persönlich anpassen, nie ungeprüft verschicken
- [ ] Content-Gaps als Ideen für neue Inhalte notieren
