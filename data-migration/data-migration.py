import json
import sqlite3
from datetime import datetime
from pathlib import Path
import logging

# === Konfiguration ===
DB_PATH = Path("/app/data/strom.sqlite")
JSON_PATH = Path("/app/data/history/2025-04-09.json")
LOG_PATH = Path("/app/data/sqlite_debug.log")
ZAEHLER_ID = 1

# === Verzeichnisse anlegen ===
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

# === Logging einrichten ===
logging.basicConfig(
    filename=LOG_PATH,
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

# === Verbindung zur SQLite-Datenbank herstellen ===
try:
    conn = sqlite3.connect(DB_PATH)
    conn.set_trace_callback(lambda stmt: logging.debug("🟢 SQL: %s", stmt))
    cursor = conn.cursor()
except Exception as e:
    logging.critical("❌ Fehler beim Verbinden mit der Datenbank: %s", str(e))
    raise SystemExit(1)

# === JSON-Datei laden ===
try:
    with JSON_PATH.open("r", encoding="utf-8") as f:
        daten = json.load(f)
except Exception as e:
    logging.critical("❌ Fehler beim Lesen der JSON-Datei: %s", str(e))
    conn.close()
    raise SystemExit(1)

# === Datensätze einfügen ===
anzahl = 0
for i, eintrag in enumerate(daten):
    try:
        timestamp = eintrag["timestamp"].replace("Z", "")
        bezug = float(eintrag["bezug"])
        einspeisung = float(eintrag["einspeisung"])
        leistung = int(eintrag["leistung"])

        logging.info("🔁 Eintrag [%d]: %s", i, timestamp)
        logging.debug("⚙️ Werte → Bezug: %.4f, Einspeisung: %.4f, Leistung: %d", bezug, einspeisung, leistung)

        cursor.execute("""
            INSERT INTO messwerte (zaehler_id, timestamp, bezug_kwh, einspeisung_kwh, wirkleistung_watt)
            VALUES (?, ?, ?, ?, ?)
        """, (ZAEHLER_ID, timestamp, bezug, einspeisung, leistung))

        anzahl += 1
        logging.info("✅ Gespeichert [%d]: %s", anzahl, timestamp)

    except Exception as e:
        logging.error("❌ Fehler beim Einfügen [%d] (%s): %s", i, timestamp, str(e))

# === Abschluss ===
try:
    conn.commit()
    logging.info("💾 Änderungen gespeichert (%d Einträge)", anzahl)
except Exception as e:
    logging.error("❌ Commit-Fehler: %s", str(e))
finally:
    conn.close()
    logging.info("🔒 Verbindung zur Datenbank geschlossen.")

print(f"✅ Fertig. {anzahl} Messwerte erfolgreich in die Datenbank übernommen.")