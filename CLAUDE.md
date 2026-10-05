# Broken Link Matcher

- Einrichtung des monatlichen Monitors: `.claude/skills/broken-link-monitor/EINRICHTUNG.md`. Lauf: `.claude/skills/broken-link-monitor/SKILL.md`.
- Schlüssel stehen nur in `.env` (aus `.env.example`). Nie ausgeben, nie in den Chat, nie auf die Kommandozeile.
- `monitor.config.json`, `.env` und `laeufe/` sind persönlich und stehen in `.gitignore`.
- Tests: `.venv/bin/pytest -q`, ohne Netzwerkzugriff.
- Oberfläche und Texte sind deutsch. Berichte enthalten keinen von einem Modell erfundenen Text.
- Im Monitor-Lauf Skripte immer als einzelnen Befehl `.venv/bin/python <skript>.py <angaben>` aufrufen, ohne cd, Pipes oder Verkettung. Nur so greift die Freigabeliste in `.claude/settings.json`.
