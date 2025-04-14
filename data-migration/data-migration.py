import json
import sqlite3
from datetime import datetime

# Datei-Pfade
JSON_DATEI = "/app/data/history/2025-04-09.json"
DB_DATEI = "/app/data/strom.sqlite"

# Verbindung zur Datenbank
conn = sqlite3.connect(DB_DATEI)
cursor = conn.cursor()

# JSON-Datei laden
with open(JSON_DATEI, "r", encoding="utf-8") as f:
    daten = json.load(f)

zaehler_id = 1
anzahl_erfolgreich = 0
anzahl_fehler = 0

for i, eintrag in enumerate(daten):
    try:

        # Prüfung auf fehlende Felder
        for key in ("timestamp", "bezug", "einspeisung", "leistung"):
            if key not in eintrag or eintrag[key] is None:
                raise ValueError(f"Feld '{key}' fehlt oder ist None")

        print(f"🔁 Durchlauf {i} - Eintrag: {eintrag}")
        print("⚙️ Einfügedaten:", eintrag["timestamp"], eintrag["bezug"], eintrag["einspeisung"], eintrag["leistung"])
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
        conn.commit()
    except Exception as e:
        conn.commit()
    
        anzahl_fehler += 1
        print(f"❌ Fehler bei Eintrag {i}: {e}")
        continue

# Abschluss
print(f"✅ Fertig. {anzahl_erfolgreich} Messwerte erfolgreich in die Datenbank übernommen.")
if anzahl_fehler > 0:
    print(f"⚠️  {anzahl_fehler} Einträge konnten nicht gespeichert werden.")

conn.close()