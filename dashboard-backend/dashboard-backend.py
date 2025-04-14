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
        bezug = round((cursor.execute("""
            SELECT bezug_kwh FROM messwerte 
            WHERE DATE(timestamp) = DATE('now') 
            ORDER BY timestamp DESC LIMIT 1
        """).fetchone())["bezug_kwh"],2)
        logger.debug("📊 Tagesbezug: %.2f kWh", bezug)

        logger.debug("🔍 Abfrage: Tageseinspeisung")

        einspeisung = round((cursor.execute("""
            SELECT einspeisung_kwh FROM messwerte 
            WHERE DATE(timestamp) = DATE('now') 
            ORDER BY timestamp DESC LIMIT 1
        """).fetchone())["einspeisung_kwh"],2)
        logger.debug("📊 Tageseinspeisung: %.2f kWh", einspeisung)

        logger.debug("🔍 Abfrage: Verbrauch heute")

        # Ersten und letzten Wert des heutigen Tages abrufen
        verbrauch_heute_start = cursor.execute("""
            SELECT bezug_kwh FROM messwerte 
            WHERE DATE(timestamp) = DATE('now') 
            ORDER BY timestamp ASC LIMIT 1
        """).fetchone()

        verbrauch_heute_end = cursor.execute("""
            SELECT bezug_kwh FROM messwerte 
            WHERE DATE(timestamp) = DATE('now') 
            ORDER BY timestamp DESC LIMIT 1
        """).fetchone()

        # Differenz berechnen, falls beide Werte vorhanden sind
        if verbrauch_heute_start and verbrauch_heute_end:
            verbrauch_heute = verbrauch_heute_end["bezug_kwh"] - verbrauch_heute_start["bezug_kwh"]
            logger.debug("📊 Verbrauch heute berechnet: Start = %.4f, Ende = %.4f, Differenz = %.4f",
                         verbrauch_heute_start["bezug_kwh"], verbrauch_heute_end["bezug_kwh"], verbrauch_heute)
        else:
            verbrauch_heute = 0
            logger.debug("⚠️ Kein Verbrauch heute berechnet, da nicht genügend Daten vorhanden sind.")

        logger.debug("🔍 Abfrage: Verbrauch gestern")

        # Ersten und letzten Wert des gestrigen Tages abrufen
        verbrauch_gestern_start = cursor.execute("""
            SELECT bezug_kwh FROM messwerte 
            WHERE DATE(timestamp) = DATE('now', '-1 day') 
            ORDER BY timestamp ASC LIMIT 1
        """).fetchone()

        verbrauch_gestern_end = cursor.execute("""
            SELECT bezug_kwh FROM messwerte 
            WHERE DATE(timestamp) = DATE('now', '-1 day') 
            ORDER BY timestamp DESC LIMIT 1
        """).fetchone()

        # Differenz berechnen, falls beide Werte vorhanden sind
        if verbrauch_gestern_start and verbrauch_gestern_end:
            verbrauch_gestern = verbrauch_gestern_end["bezug_kwh"] - verbrauch_gestern_start["bezug_kwh"]
            logger.debug("📊 Verbrauch gestern berechnet: Start = %.4f, Ende = %.4f, Differenz = %.4f",
                         verbrauch_gestern_start["bezug_kwh"], verbrauch_gestern_end["bezug_kwh"], verbrauch_gestern)
        else:
            verbrauch_gestern = 0
            logger.debug("⚠️ Kein Verbrauch gestern berechnet, da nicht genügend Daten vorhanden sind.")

        # Daten als JSON zurückgeben
        response = {
            "leistung": leistung["wirkleistung_watt"] if leistung else 0,
            "bezug": bezug,
            "einspeisung": einspeisung,
            "verbrauchHeute": verbrauch_heute,
            "verbrauchGestern": verbrauch_gestern
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