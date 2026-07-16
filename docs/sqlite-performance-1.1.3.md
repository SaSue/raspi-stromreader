# SQLite-Optimierung in Version 1.1.3

## Ausgangslage

Die produktive Datenbank auf `raspi-stromzaehler` war zum Messzeitpunkt 52 MB
groß und enthielt 549.072 Messwerte. Abfragen mit `DATE(timestamp)` konnten den
vorhandenen Index `idx_timestamp` nicht verwenden und führten einen vollständigen
Tabellenscan aus.

## Messergebnis

Gemessen wurde am 16. Juli 2026 direkt gegen die produktive Datenbank. Beide
Abfragen liefen ausschließlich lesend und ermittelten den Tagesverbrauch für
den 30. April 2026.

| Abfrage | Laufzeit |
| --- | ---: |
| Bisher: `DATE(timestamp) = ?` | 0,824 s |
| Neu: `timestamp >= ? AND timestamp < ?` | 0,002 s |
| Verbesserung | rund 419-mal schneller |

Der neue Abfrageplan enthält `SEARCH messwerte USING INDEX idx_timestamp`.
Der Test `test_day_range_query_uses_timestamp_index_with_large_table` prüft
diesen Plan zusätzlich mit 500.000 generierten Messwerten.

Die Messung kann mit `tools/benchmark_sqlite.py` auf einer schreibgeschützt
geöffneten Datenbank wiederholt werden.

## Migration und Rollback

Beim ersten Start des Readers aus Version 1.1.3 wird das SQLite-Schema
automatisch und idempotent auf `PRAGMA user_version = 2` migriert.

Vor jeder notwendigen Migration einer bereits vorhandenen Datenbank passiert
Folgendes:

1. Die Quelldatenbank muss `PRAGMA integrity_check` bestehen.
2. Über die SQLite-Backup-API wird eine konsistente Sicherung unter
   `strom.sqlite.backup-v1.1.3` angelegt.
3. Auch die Sicherung muss die Integritätsprüfung bestehen.
4. Tabellen und Zeitstempelindex werden mit `IF NOT EXISTS` abgesichert.
5. Nach der Transaktion wird die migrierte Datenbank erneut geprüft.

Bei einem Fehler bricht der Reader-Start ab. Eine beschädigte oder nicht
gesicherte Datenbank wird nicht stillschweigend weiterverwendet. Die Sicherung
wird bei späteren Containerstarts nicht überschrieben.

Für ein Rollback müssen Reader und Backend gestoppt sein. Danach kann die
aktuelle Datenbank separat gesichert und die Datei
`strom.sqlite.backup-v1.1.3` als `strom.sqlite` wiederhergestellt werden.
