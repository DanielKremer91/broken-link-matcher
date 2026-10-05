# Broken Backlinks per Ahrefs-MCP holen

Der Ahrefs-MCP ersetzt den Export-Klick in der Ahrefs-Oberfläche, nicht den Workflow. Claude ruft den Endpunkt `site-explorer-broken-backlinks` auf, bekommt eine CSV zurück, und diese CSV lädst du in Schritt 2 des Tools hoch. Der Parser erkennt die API-Spaltennamen automatisch.

Voraussetzung: Claude Desktop oder Claude Code mit verbundenem Ahrefs-MCP (Einrichtung siehe Ahrefs-Dokumentation).

## Prompt

```
Hol mir über den Ahrefs-MCP die Broken Backlinks von konkurrent.de:
mode subdomains, aggregation 1_per_domain, nur is_dofollow=true und is_content=true,
sortiert nach domain_rating_source absteigend, limit 100, output csv,
select: url_from,url_to,anchor,snippet_left,snippet_right,title,domain_rating_source,url_rating_source,http_code_target,is_dofollow,is_content
Speichere die CSV als broken-backlinks-konkurrent.csv.
```

## Parameter im Detail

| Parameter | Wert | Warum |
|---|---|---|
| target | Wettbewerber-Domain | ohne Protokoll |
| mode | subdomains | Hauptdomain und alle Subdomains |
| aggregation | 1_per_domain | eine Zeile pro linkgebender Domain |
| where | is_dofollow = true und is_content = true | nur Links, die zählen |
| order_by | domain_rating_source:desc | wertvollste Linkgeber zuerst |
| select | siehe Prompt | genau die Felder, die das Tool braucht |
| limit | 100 | reicht für einen Durchlauf |
| output | csv | direkt hochladbar |

Optional: `traffic` im select ergänzen, wenn du den organischen Traffic der linkgebenden Seite sehen willst. Das kostet 10 API-Units zusätzlich pro Zeile.

## Kosten

Jede Zeile kostet API-Units, mit der Auswahl oben etwa 11 bis 12 Units pro Zeile, je nach Filtern. Abfragen auf `ahrefs.com` als Ziel sind kostenlos und eignen sich zum Üben.

## Beispieldatei

`examples/broken-backlinks-ahrefs-com.csv` ist eine echte Antwort des MCP für das Ziel `ahrefs.com` (15 Zeilen, Stand September 2026). Du kannst sie direkt in Schritt 2 hochladen, um den Parser und das Ranking auszuprobieren. Die Flag-Spalten `is_dofollow` und `is_content` fehlen darin, deshalb zeigt das Tool dafür "unbekannt"; das Where-Filter hat sie bereits auf Dofollow und Content-Links eingeschränkt.
