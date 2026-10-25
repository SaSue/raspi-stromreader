# UTC-Speicherung und Bestandsmigration

## Zeitvertrag ab Schema 3

Messzeitpunkte in SQLite und neu geschriebenen JSON-Dateien sind ISO-8601 in
UTC mit sechs Nachkommastellen und `+00:00`, z. B.
`2026-10-25T01:02:00.000000+00:00`. Einheitliche Schreibweise ist erforderlich,
damit der vorhandene Textindex chronologisch sortiert. API-Zeitpunkte enthalten
diesen Offset. Container verwenden zusätzlich TZ=UTC. Die Zeitzone des Betriebssystems bleibt unverändert.

Berliner Kalendergrenzen bleiben fachlich erhalten: Tagesdateinamen,
Tages-/Wochen-/Monats-/Jahresstatistiken und Anzeige verwenden `Europe/Berlin`.
Tagesabfragen wandeln beide lokalen Mitternachtsgrenzen nach UTC um und nutzen
weiter den Timestamp-Index. Tage bei Zeitumstellung haben 23 bzw. 25 Stunden.
Kalendergruppen verwenden native SQLite-Zeitberechnung mit aus `zoneinfo`
kompilierten Berliner Offsetintervallen, unabhängig vom TZ des Containers. Die bestehende Verbrauchsdefinition MAX minus MIN bleibt erhalten.

OMD und Reader-Healthcheck nehmen den zuletzt eingefügten Datensatz (rowid),
rechnen auf UTC und lehnen Zeitangaben ohne Offset ab. Die bisherigen
Alarmschwellen bleiben bestehen. Der Reader blockiert gefüllte Datenbanken mit
Schema < 3; das Dashboard verlangt Schema 3. Kein automatischer Umbau beim
Containerstart: erst Datenmigration, dann gemeinsamer Versionswechsel.

## Werkzeug: Quelle bleibt unverändert

Voraussetzungen: Python >= 3.9, verfügbare IANA-Zeitzonendaten, genug freier
Speicher für Sicherung, Zielkopie, Audit-Tabelle und SQLite-Journal. Das Werkzeug
braucht keine Fremdpakete. Die Quelldatenbank wird ausschließlich mit `mode=ro`
geöffnet. Die SQLite-Backup-API erzeugt beim Konvertieren einen konsistenten
Snapshot, einschließlich schon bestätigter WAL-Daten. Niemals eine laufende
SQLite-Datei allein mit `cp` sichern.

Im Repository-Verzeichnis:

```sh
python3 tools/migrate_utc.py /pfad/strom.sqlite > audit.json
python3 tools/migrate_utc.py /pfad/strom.sqlite --folds folds.json > audit-resolved.json
python3 tools/migrate_utc.py /pfad/strom.sqlite --folds folds.json --output /pfad/strom-utc.sqlite > migration.json
```

Ohne `--output` ist der Lauf eine reine Vorschau. Exit 0 bedeutet vollständig
auflösbar; Exit 2 meldet ungeklärte Datensätze/ungenutzte Entscheidungen; Exit 1
bedeutet einen technischen Fehler. Zielpfad darf noch nicht existieren, auch
nicht als leere Datei. Bestehende Sicherungen werden nie überschrieben. Eine
fehlgeschlagene Zielkopie wird entfernt. Keine Löschung aus der Quelle.

Zeitstempel mit Offset oder `Z` werden direkt umgerechnet. Für Zeitstempel ohne
Offset gilt die explizite Herkunftsannahme `--source-timezone Europe/Berlin`.
Diese muss anhand der damaligen Writer-/Import-Konfiguration geprüft werden:
Der alte JSON-Importer entfernte `Z`; eventuell so entstandene naive UTC-Werte
sind durch bloßes Betrachten der Daten nicht von Berliner Zeiten unterscheidbar.
Für gemischte Herkunft unterstützt `--source-zones zones.json` dokumentierte
ID-Bereiche mit abweichender Quellzeitzone. Beispiel:
`[{"start_id": 1, "end_id": 123, "timezone": "UTC", "reason": "Writer ohne TZ; Archivvergleich"}]`.
Bereiche dürfen sich nicht überschneiden und verlangen eine Begründung. Sie
betreffen nur die Interpretation naiver Werte; vorhandene Offsets haben Vorrang.
Der Bericht enthält Herkunftsbereiche und Anzahlen, das Audit die tatsächlich
verwendete Quellzeitzone. Vorschau und finalen Lauf mit denselben geprüften
Herkunfts- und Fold-Dateien starten.

Die doppelte Herbststunde wird **nicht geraten**: `folds.json` ordnet IDs zu,
z. B. `{"123": 0, "124": 1}`. Fold 0 ist das erste Auftreten (Sommerzeit), Fold 1
das zweite (Winterzeit). Die Zuordnung muss durch Reihenfolge, tatsächlichen
Uhr-Rücksprung und nötigenfalls JSON-Archive mit Offset belegt sein. Eine einzelne
isolierte Messung ist nicht eindeutig. Nicht existente Frühlingszeiten und
ungültige Zeitstempel blockieren den Lauf ebenfalls; sie werden nicht verschoben
oder gelöscht. Unbenutzte Fold-IDs blockieren als Schutz gegen falsche Zuordnung.

In der erfolgreichen Zielkopie stehen Schema 3 und der Timestamp-Index. Die
Tabelle `utc_migration_audit` bewahrt für jede Änderung Original, UTC-Wert,
Quellzeitzone und Auflösungsart. IDs, Zählerzuordnung und Messwerte bleiben
unverändert. Integrität und Fremdschlüssel werden geprüft; alle Änderungen an
der Kopie erfolgen in einer Transaktion. Erneute Prüfung einer fertigen Kopie
ohne Fold-Datei meldet `changed: 0`. Die ursprüngliche Fold-Datei ist für diese
bereits eindeutige Kopie nicht mehr erforderlich.

Alte JSON-Archive zunächst unverändert sichern und aufbewahren. Sie sind eine
wichtige zusätzliche Quelle zur Auflösung historischer Zeitpunkte. Neue Dateien
enthalten UTC-Zeitpunkte; der Tagesdateiname bleibt Berlin. Der JSON-Importer
akzeptiert nur Zeitpunkte mit Offset/Z und Schema 3, rechnet auf kanonisches UTC
um und bricht bei Fehlern den gesamten Import ab. Er dedupliziert nicht: alte
Archive nicht zusätzlich in eine bereits vollständig migrierte DB importieren.

## Geplanter produktiver Ablauf

1. Lesende Vorschau mit Herkunftsprüfung, Klärung aller gemeldeten IDs und
   gesicherter Fold-Datei. Neue Images lokal/CI bauen und zusammen mit dem neuen
   OMD-Plugin vorbereiten. Noch keine Aktualisierung der laufenden Container.
2. Probelauf auf konsistenter Kopie. Datensatzanzahl, IDs, Zählerstände und
   Fremdschlüssel mit Quelle vergleichen; UTC-Reihenfolge und Berliner Tages-,
   Monats- und Jahreswerte prüfen, besonders beide Herbststunden und Mitternacht.
   Laufzeit, Plattenbedarf und API-Antwortzeiten auf dem Pi messen. Vollständige Kalendergruppen verwenden native SQLite-Ausdrücke; deren
   Laufzeit prüfen.
3. **Explizite Freigabe für das Wartungsfenster einholen.** Reader und Dashboard
   müssen für den finalen Austausch gestoppt werden. Geprüfte Images bereithalten,
   vorhandene Tags/Digests, Compose, Mounts, Limits und altes OMD-Plugin sichern.
4. Nach dem Stopp eine finale konsistente Originalkopie per SQLite-Backup-API
   erstellen und unverändert behalten. Vorschaustand nicht einsetzen: Er enthält
   später eingegangene Messungen nicht. Finalen Snapshot migrieren und erneut
   prüfen. Aktive Datenbankverbindungen müssen vor dem Austausch geschlossen
   sein; WAL sauber checkpointen. DB und eventuelle WAL-/SHM-Dateien als Einheit
   behandeln, keine alten Sidecars mit einer neuen DB mischen. Dateirechte und
   Eigentümer erhalten. Genug freien Platz vorher prüfen.
5. Geprüfte Zielkopie am bisherigen Pfad aktivieren; neue Reader-/Backend-Images
   und Dashboard-JavaScript gemeinsam bereitstellen. Neues Plugin nach der
   Migration installieren. Alten Writer niemals gegen Schema 3 starten.
6. Mehrere neue Messungen abwarten: UTC-Offset und fortschreitende IDs prüfen,
   beide Container dauerhaft healthy, API und HTTPS erreichbar, Kalenderwerte
   plausibel. OMD-Site `demo` und frischen echten NCPA-Check aus dem OMD-Container
   prüfen sowie gespeicherten Service `Stromreader Datenalter` mit neuem
   Checkzeitpunkt und Zustand OK verifizieren. Erst dann Erfolg melden.

Rollback: neue Prozesse stoppen, seit Umschaltung entstandene UTC-Messungen
separat sichern; alte DB-Sicherung einschließlich korrekter Sidecar-Behandlung,
Images und Plugin zusammen zurücksetzen. Seit Sicherung aufgezeichnete Daten
nicht blind verwerfen oder doppelt importieren. Wartungsfenster verursacht eine
Aufzeichnungslücke; Stromzähler-Gesamtstände bleiben am Gerät bestehen, die
Leistungshistorie dieser Lücke ist nicht rekonstruierbar.

## Tests

```sh
python3 -m unittest discover -s tests -q
```

Getestet werden UTC-Schreibformat, Schema-Sperre, UTC-Alter trotz Rückstellung,
23-/25-Stunden-Grenzen, lokale Kalendergruppen an UTC-Mitternacht,
Offset-Erhalt, blockierte DST-Lücken/Mehrdeutigkeiten, explizite Fold-Auflösung,
unveränderte Quelle, unveränderte Messwerte, Audit, erneute Vorschau sowie
Abbruch und Entfernen ungültiger Zielkopien.
