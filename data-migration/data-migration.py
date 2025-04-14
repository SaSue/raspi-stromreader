import json
import sqlite3
from datetime import datetime
from pathlib import Path

# Datei-Pfade
JSON_DATEI = "/app/data/history/2025-04-09.json"
DB_DATEI = "/app/data/strom.sqlite"

# Datenbankverbindung und Cursor erstellen
conn = sqlite3.connect(DB_DATEI)
cursor = conn.cursor()

# JSON-Datei laden
with open(JSON_DATEI, "r", encoding="utf-8") as f:
    daten = json.load(f)

zaehler_id = 1  # Zähler-ID (anpassen falls mehrere Zähler vorhanden)

# Zähler für erfolgreiche Inserts
anzahl_erfolgreich = 0

# Alle Einträge einfügen
for i, eintrag in enumerate(daten):
    try:
        print(f"🔁 Durchlauf {i} - Eintrag: {eintrag}")

        cursor.execute("""
            INSERT INTO messwerte (zaehler_id, timestamp, bezug_kwh, einspeisung_kwh, wirkleistung_watt)
            VALUES (?, ?, ?, ?, ?)
        """, (
            zaehler_id,
            eintrag["timestamp"],
            eintrag["bezug"],
            eintrag["einspeisung"],
            eintrag["leistung"]
        ))

        anzahl_erfolgreich += 1
        print(f"✅ Gespeichert [{anzahl_erfolgreich}]: {eintrag['timestamp']}")

    except Exception as e:
        print(f"❌ Fehler bei Eintrag {i}: {e}")

# Änderungen speichern und Verbindung schließen
conn.commit()
conn.close()

print(f"✅ Fertig. {anzahl_erfolgreich} Messwerte erfolgreich in die Datenbank übernommen.")