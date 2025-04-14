from flask import Flask, jsonify
import sqlite3
import logging

app = Flask(__name__)
DB_PATH = "/app/data/strom.sqlite"

# === Logging einrichten ===
logging.basicConfig(
    level=logging.DEBUG,  # Setze das Logging-Level auf DEBUG
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("dashboard-backend")

def get_db_connection():
    logger.debug("🔌 Verbindung zur SQLite-Datenbank herstellen...")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # Damit die Ergebnisse als Dictionary zurückgegeben werden
    logger.debug("✅ Verbindung hergestellt.")
    return conn

@app.route('/api/dashboard', methods=['GET'])
def get_dashboard_data():
    logger.debug("📊 API-Aufruf: /api/dashboard")
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Beispielabfragen
        logger.debug("🔍 Abfrage: Aktuelle Leistung")
        leistung = cursor.execute("SELECT wirkleistung_watt FROM messwerte ORDER BY timestamp DESC LIMIT 1").fetchone()
        logger.debug("🔍 Abfrage: Tagesbezug")
        bezug = cursor.execute("SELECT SUM(bezug_kwh) FROM messwerte WHERE DATE(timestamp) = DATE('now')").fetchone()
        logger.debug("🔍 Abfrage: Tageseinspeisung")
        einspeisung = cursor.execute("SELECT SUM(einspeisung_kwh) FROM messwerte WHERE DATE(timestamp) = DATE('now')").fetchone()
        logger.debug("🔍 Abfrage: Verbrauch heute")
        verbrauch_heute = cursor.execute("SELECT SUM(bezug_kwh) FROM messwerte WHERE DATE(timestamp) = DATE('now')").fetchone()
        logger.debug("🔍 Abfrage: Verbrauch gestern")
        verbrauch_gestern = cursor.execute("SELECT SUM(bezug_kwh) FROM messwerte WHERE DATE(timestamp) = DATE('now', '-1 day')").fetchone()

        # Daten als JSON zurückgeben
        response = {
            "leistung": leistung["wirkleistung_watt"] if leistung else 0,
            "bezug": bezug["SUM(bezug_kwh)"] if bezug else 0,
            "einspeisung": einspeisung["SUM(einspeisung_kwh)"] if einspeisung else 0,
            "verbrauchHeute": verbrauch_heute["SUM(bezug_kwh)"] if verbrauch_heute else 0,
            "verbrauchGestern": verbrauch_gestern["SUM(bezug_kwh)"] if verbrauch_gestern else 0
        }
        logger.debug("📤 API-Antwort: %s", response)
        return jsonify(response)

    except Exception as e:
        logger.error("❌ Fehler bei der Verarbeitung der Abfragen: %s", str(e))
        return jsonify({"error": "Fehler beim Abrufen der Daten"}), 500

    finally:
        conn.close()
        logger.debug("🔒 Verbindung zur SQLite-Datenbank geschlossen.")

if __name__ == '__main__':
    logger.debug("🚀 Starte Flask-Server auf Port 5000...")
    app.run(host='0.0.0.0', port=5000)