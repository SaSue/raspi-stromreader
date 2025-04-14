import json
import sqlite3
import logging
from datetime import datetime

# Datei-Pfade
JSON_DATEI = "/app/data/history/2025-04-09.json"
DB_DATEI = "strom.sqlite"

# Datenbankverbindung und Tabelle vorbereiten
conn = sqlite3.connect(DB_DATEI)
cursor = conn.cursor()

# JSON-Datei einlesen
with open(JSON_DATEI, "r", encoding="utf-8") as f:
    daten = json.load(f)

# Daten einfügen
for eintrag in daten:
     # Zähler-ID abrufen oder einfügen
    c.execute("SELECT id FROM zaehler WHERE seriennummer = ?", (eintrag["seriennummer"]))
    row = c.fetchone()
    if row:
        zaehler_id = row[0]
        print("🔍 Zähler-ID gefunden: %s", zaehler_id)
    else:
        c.execute("INSERT INTO zaehler (seriennummer, hersteller) VALUES (?, ?)", (eintrag["seriennummer"],eintrag["hersteller"]))
        zaehler_id = c.lastrowid
        print("💾 Neuer Zähler in SQLite gespeichert: %s", (seriennummer, hersteller))

    # Messwert einfügen
    timestamp = datetime.now().isoformat()
    c.execute("""
        INSERT INTO messwerte (zaehler_id, timestamp, bezug_kwh, einspeisung_kwh, wirkleistung_watt)
        VALUES (?, ?, ?, ?, ?)
    """, (
        zaehler_id,
        eintrag["timestamp"],
        eintrag["bezug"],
        eintrag["einspeisung"],
        eintrag["leistung"]
    ))
    print("📊 Messwert in SQLite gespeichert: %s", eintrag)


# Änderungen speichern und Verbindung schließen
conn.commit()
conn.close()

print("Daten erfolgreich in SQLite übertragen.")