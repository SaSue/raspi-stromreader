import json
import sqlite3
from datetime import datetime

# Datei-Pfade
JSON_DATEI = "/app/data/history/2025-04-09.json"
DB_DATEI = "/app/data/strom.sqlite"

# Datenbankverbindung und Tabelle vorbereiten
conn = sqlite3.connect(DB_DATEI)
cursor = conn.cursor()

# JSON-Datei einlesen
with open(JSON_DATEI, "r", encoding="utf-8") as f:
    daten = json.load(f)

# Daten einfügen
for i, eintrag in enumerate(daten):  # Verwende enumerate, um den Index automatisch zu zählen
    # Messwert einfügen
    print(f"Schleifendurchlauf {i} Messwert: {eintrag}")
    cursor.execute("""
            INSERT INTO messwerte (zaehler_id, timestamp, bezug_kwh, einspeisung_kwh, wirkleistung_watt)
            VALUES (?, ?, ?, ?, ?)
        """, (
            zaehler_id,
            timestamps[i],
            bezug[i],
            einspeisung[i],
            leistung[i]
        ))
    print(f"📊 Messwert in SQLite gespeichert: {timestamps[i]}")

# Änderungen speichern und Verbindung schließen
conn.commit()
conn.close()

print("Daten erfolgreich in SQLite übertragen.")