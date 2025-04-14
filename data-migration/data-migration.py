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
for eintrag in daten:
    # Zähler-ID abrufen oder einfügen
    cursor.execute("SELECT id FROM zaehler WHERE seriennummer = ?", (eintrag["seriennummer"],))
    row = cursor.fetchone()
    if row:
        zaehler_id = row[0]
        print(f"🔍 Zähler-ID gefunden: {zaehler_id}")
    else:
        cursor.execute(
            "INSERT INTO zaehler (seriennummer, hersteller) VALUES (?, ?)",
            (eintrag["seriennummer"], eintrag["zaehlername"])
        )
        zaehler_id = cursor.lastrowid
        print(f"💾 Neuer Zähler in SQLite gespeichert: {eintrag['seriennummer']}, {eintrag['zaehlername']}")

    # Messwert einfügen
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
    print(f"📊 Messwert in SQLite gespeichert: {eintrag}")

# Änderungen speichern und Verbindung schließen
conn.commit()
conn.close()

print("Daten erfolgreich in SQLite übertragen.")