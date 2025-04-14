import json
import sqlite3
from datetime import datetime

# Datei-Pfade
JSON_DATEI = "/app/data/history/2025-04-09.json"
DB_DATEI = "/app/data/strom.sqlite"

# Datenbankverbindung und Tabelle vorbereiten
conn = sqlite3.connect(DB_DATEI)
cursor = conn.cursor()

zaehler_id = 1  # Hier die ID des Zählers angeben

# JSON-Datei einlesen
with open(JSON_DATEI, "r", encoding="utf-8") as f:
    daten = json.load(f)
i = 0
# Daten einfügen
for eintrag in daten:

    # Messwert einfügen
    cursor.execute("""
        INSERT INTO messwerte (zaehler_id, timestamp, bezug_kwh, einspeisung_kwh, wirkleistung_watt)
        VALUES (?, ?, ?, ?, ?)
    """, (
        zaehler_id,
        eintrag["timestamp"][i],
        eintrag["bezug"][i],
        eintrag["einspeisung"][i],
        eintrag["leistung"][i]
    ))
    i = i + 1
    print(f"📊 Messwert in SQLite gespeichert: {eintrag}")

# Änderungen speichern und Verbindung schließen
conn.commit()
conn.close()

print("Daten erfolgreich in SQLite übertragen.")