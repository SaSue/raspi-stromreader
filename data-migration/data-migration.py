import json
import sqlite3
from datetime import datetime
from pathlib import Path
import logging
import glob

# === Konfiguration ===
DB_PATH = Path("/app/data/strom.sqlite")
HISTORY_PATH = Path("/app/data/history")
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

file_handler = logging.FileHandler(LOG_PATH)
file_handler.setLevel(logging.DEBUG)

console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)

logger = logging.getLogger("data-migration")
logger.setLevel(logging.DEBUG)
logger.addHandler(file_handler)
logger.addHandler(console_handler)

# === Verbindung zur SQLite-Datenbank herstellen ===
try:
    conn = sqlite3.connect(DB_PATH)
    conn.set_trace_callback(lambda stmt: logger.debug("🟢 SQL: %s", stmt))
    cursor = conn.cursor()
except Exception as e:
    logger.critical("❌ Fehler beim Verbinden mit der Datenbank: %s", str(e))
    raise SystemExit(1)

# === Alle JSON-Dateien im Ordner `history` abarbeiten ===
json_files = glob.glob(str(HISTORY_PATH / "*.json"))
logger.info("📂 Gefundene JSON-Dateien: %s", json_files)

gesamtanzahl = 0

for json_file in json_files:
    logger.info("📄 Verarbeite Datei: %s", json_file)
    try:
        # JSON-Datei laden
        with open(json_file, "r", encoding="utf-8") as f:
            daten = json.load(f)

        # Datensätze einfügen
        anzahl = 0
        for i, eintrag in enumerate(daten):
            try:
                timestamp = eintrag["timestamp"].replace("Z", "")
                bezug = float(eintrag["bezug"])
                einspeisung = float(eintrag["einspeisung"])
                leistung = int(eintrag["leistung"])

                logger.info("🔁 Eintrag [%d]: %s", i, timestamp)
                logger.debug("⚙️ Werte → Bezug: %.4f, Einspeisung: %.4f, Leistung: %d", bezug, einspeisung, leistung)

                cursor.execute("""
                    INSERT INTO messwerte (zaehler_id, timestamp, bezug_kwh, einspeisung_kwh, wirkleistung_watt)
                    VALUES (?, ?, ?, ?, ?)
                """, (ZAEHLER_ID, timestamp, bezug, einspeisung, leistung))

                anzahl += 1
                logger.info("✅ Gespeichert [%d]: %s", anzahl, timestamp)

            except Exception as e:
                logger.error("❌ Fehler beim Einfügen [%d] (%s): %s", i, timestamp, str(e))

        gesamtanzahl += anzahl
        logger.info("📄 Datei abgeschlossen: %s (%d Einträge)", json_file, anzahl)

    except Exception as e:
        logger.error("❌ Fehler beim Verarbeiten der Datei %s: %s", json_file, str(e))

# === Abschluss ===
try:
    conn.commit()
    logger.info("💾 Änderungen gespeichert (%d Einträge insgesamt)", gesamtanzahl)
except Exception as e:
    logger.error("❌ Commit-Fehler: %s", str(e))
finally:
    conn.close()
    logger.info("🔒 Verbindung zur Datenbank geschlossen.")

print(f"✅ Fertig. {gesamtanzahl} Messwerte erfolgreich in die Datenbank übernommen.")