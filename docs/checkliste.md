# Checkliste: Broken-Link-Monitor einrichten

**Schnellstart:** Claude-Desktop-App öffnen, Bereich Code, eine neue Sitzung starten (welcher Ordner, ist egal) und diesen Satz eingeben:

```
Richte mir den Broken Link Monitor ein. Klone dazu https://github.com/DanielKremer91/broken-link-matcher und folge der Anleitung für Claude in der README.
```

Claude führt dann durch alle Punkte unten.

Zum Abhaken. Details zu jedem Punkt stehen in [monatlicher-workflow.md](monatlicher-workflow.md).

## Zugänge

- [ ] Claude-Desktop-App installiert, Claude Code nutzbar
- [ ] Ahrefs-Abo mit MCP-Zugang, Ahrefs-MCP in Claude verbunden
- [ ] Screaming Frog mit Lizenz, MCP-Erweiterung in Claude verbunden
- [ ] OpenAI-Schlüssel (oder Gemini oder Ollama)
- [ ] Optional: Resend-Konto, oder Outlook- bzw. Gmail-Connector in Claude

## Einrichtung

- [ ] Repo geklont und `uv venv && uv pip install -r requirements.txt` ausgeführt
- [ ] Frog: Embeddings eingerichtet, per Vorlage `frog/main-content-embedding.js` oder KI-Anbindung mit "Page Text"
- [ ] Frog: Nur der Hauptinhalt wird eingebettet (Vorschau mit `PREVIEW_TEXT = true` oder Content Area geprüft)
- [ ] Frog: dasselbe Modell wie `embedding.model` in `monitor.config.json`
- [ ] Frog: bei Custom JavaScript das Rendering auf JavaScript gestellt und mit `PREVIEW_TEXT = true` an wenigen Seiten getestet
- [ ] Frog: ein Testcrawl zeigt gefüllte Embedding-Spalten
- [ ] Frog: Modell notiert, zum Beispiel `text-embedding-3-small`
- [ ] Frog: Konfiguration im MCP-Basisverzeichnis gespeichert, nie weitergegeben
- [ ] `.env` aus `.env.example` angelegt, Schlüssel eingetragen, `chmod 600 .env`
- [ ] Resend: Domain verifiziert, Schlüssel und Absender in `.env`
- [ ] `monitor.config.json` aus der Vorlage angelegt und ausgefüllt, inklusive Kundenname in `customer`
- [ ] Gleiches Embedding-Modell in Frog und `monitor.config.json`
- [ ] `frog.embeddings_source` passt zum Weg: `custom_javascript` oder `ai`
- [ ] Wettbewerber als Domain ohne `https://` eingetragen
- [ ] Ahrefs-Filter eingestellt und mit `ahrefs_params.py` angesehen
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
- [ ] Zeilen mit Ersatztext statt Snapshot aus der Wayback Machine besonders kritisch prüfen
- [ ] Optional: Content-Gaps als Ideen für neue Inhalte ansehen. Mail und Anhang enthalten sie nicht, die Streamlit-App zeigt sie
