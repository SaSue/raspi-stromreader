from flask import Flask, jsonify, request
import sqlite3
import logging

app = Flask(__name__)
DB_PATH = "/app/data/strom.sqlite"

# === Logging einrichten ===
logging.basicConfig(
    level=logging.INFO,  # Setze das Logging-Level auf DEBUG
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
            verbrauch_heute = round(verbrauch_heute_end["bezug_kwh"] - verbrauch_heute_start["bezug_kwh"],2)
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
            verbrauch_gestern = round(verbrauch_gestern_end["bezug_kwh"] - verbrauch_gestern_start["bezug_kwh"],2)
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

@app.route('/api/tagesverlauf', methods=['GET'])
def get_tagesverlauf():
    logger.debug("📊 API-Aufruf: /api/tagesverlauf")
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Tagesverlauf-Daten abrufen
        verlauf = cursor.execute("""
            SELECT timestamp, wirkleistung_watt 
            FROM messwerte 
            WHERE DATE(timestamp) = DATE('now')
            ORDER BY timestamp ASC
        """).fetchall()

        # Daten in ein JSON-kompatibles Format umwandeln
        verlauf_data = [{"timestamp": row["timestamp"], "leistung": row["wirkleistung_watt"]} for row in verlauf]
        logger.debug("📊 Tagesverlauf-Daten in Watt: %s", verlauf_data)
        return jsonify(verlauf_data)

    except Exception as e:
        logger.error("❌ Fehler beim Abrufen des Tagesverlaufs: %s", str(e))
        return jsonify({"error": "Fehler beim Abrufen des Tagesverlaufs"}), 500

    finally:
        conn.close()
        logger.debug("🔒 Verbindung zur SQLite-Datenbank geschlossen.")

@app.route('/api/wochenstatistik', methods=['GET'])
def get_wochenstatistik():
    logger.debug("📊 API-Aufruf: /api/wochenstatistik")
    datum = request.args.get('datum')  # Startdatum aus den Query-Parametern abrufen
    if not datum:
        logger.error("❌ Kein Datum angegeben.")
        return jsonify({"error": "Kein Datum angegeben"}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Wochenstatistik-Daten abrufen (Startdatum + 6 Tage)
        logger.debug("🔍 Abfrage: Wochenstatistik ab %s", datum)
        statistik = cursor.execute("""
            SELECT DATE(timestamp) as datum, 
                   MAX(bezug_kwh) - MIN(bezug_kwh) as tagesverbrauch
            FROM messwerte
            WHERE DATE(timestamp) BETWEEN DATE(?) AND DATE(?, '+6 days')
            GROUP BY DATE(timestamp)
            ORDER BY datum ASC
        """, (datum, datum)).fetchall()

        # Daten in ein JSON-kompatibles Format umwandeln
        statistik_data = [{"datum": row["datum"], "verbrauch": row["tagesverbrauch"]} for row in statistik]
        logger.debug("📊 Wochenstatistik-Daten: %s", statistik_data)
        return jsonify(statistik_data)

    except Exception as e:
        logger.error("❌ Fehler beim Abrufen der Wochenstatistik: %s", str(e))
        return jsonify({"error": "Fehler beim Abrufen der Wochenstatistik"}), 500

    finally:
        conn.close()
        logger.debug("🔒 Verbindung zur SQLite-Datenbank geschlossen.")

@app.route('/api/tagesdaten', methods=['GET'])
def get_tagesdaten():
    logger.debug("📊 API-Aufruf: /api/tagesdaten")
    datum = request.args.get('datum')  # Datum aus den Query-Parametern abrufen
    if not datum:
        logger.error("❌ Kein Datum angegeben.")
        return jsonify({"error": "Kein Datum angegeben"}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Tagesverbrauch berechnen (max - min Bezug)
        logger.debug("🔍 Abfrage: Tagesverbrauch für %s", datum)
        verbrauch_row = cursor.execute("""
            SELECT MAX(bezug_kwh) - MIN(bezug_kwh) AS verbrauch
            FROM messwerte
            WHERE DATE(timestamp) = ?
        """, (datum,)).fetchone()
        verbrauch = verbrauch_row["verbrauch"] if verbrauch_row and verbrauch_row["verbrauch"] is not None else 0

        # Tagesendstand abrufen (max Bezug)
        logger.debug("🔍 Abfrage: Tagesendstand für %s", datum)
        endstand_row = cursor.execute("""
            SELECT MAX(bezug_kwh) AS endstand
            FROM messwerte
            WHERE DATE(timestamp) = ?
        """, (datum,)).fetchone()
        endstand = endstand_row["endstand"] if endstand_row and endstand_row["endstand"] is not None else 0

        # Tagesverlauf abrufen (Leistung über den Tag)
        logger.debug("🔍 Abfrage: Tagesverlauf für %s", datum)
        verlauf = cursor.execute("""
            SELECT timestamp, wirkleistung_watt
            FROM messwerte
            WHERE DATE(timestamp) = ?
            ORDER BY timestamp ASC
        """, (datum,)).fetchall()

        verlauf_data = [{"timestamp": row["timestamp"], "leistung": row["wirkleistung_watt"]} for row in verlauf]

        # API-Antwort erstellen
        response = {
            "verbrauch": verbrauch,
            "endstand": endstand,
            "verlauf": verlauf_data
        }
        logger.debug("📤 API-Antwort: %s", response)
        return jsonify(response)

    except Exception as e:
        logger.error("❌ Fehler bei der Verarbeitung der Tagesdaten: %s", str(e))
        return jsonify({"error": "Fehler beim Abrufen der Tagesdaten"}), 500

    finally:
        conn.close()
        logger.debug("🔒 Verbindung zur SQLite-Datenbank geschlossen.")

@app.route('/api/monatsstatistik', methods=['GET'])
def get_monatsstatistik():
    logger.debug("📊 API-Aufruf: /api/monatsstatistik")
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Verbrauchsdaten der letzten 12 Monate berechnen
        logger.debug("🔍 Abfrage: Monatsstatistik der letzten 12 Monate")
        statistik = cursor.execute("""
            SELECT strftime('%Y-%m', timestamp) as monat,
                   MAX(bezug_kwh) - MIN(bezug_kwh) as verbrauch
            FROM messwerte
            WHERE timestamp >= DATE('now', '-12 months')
            GROUP BY strftime('%Y-%m', timestamp)
            ORDER BY monat ASC
        """).fetchall()

        # Daten in ein JSON-kompatibles Format umwandeln
        statistik_data = [{"monat": row["monat"], "verbrauch": row["verbrauch"]} for row in statistik]
        logger.debug("📊 Monatsstatistik-Daten: %s", statistik_data)
        return jsonify(statistik_data)

    except Exception as e:
        logger.error("❌ Fehler beim Abrufen der Monatsstatistik: %s", str(e))
        return jsonify({"error": "Fehler beim Abrufen der Monatsstatistik"}), 500

    finally:
        conn.close()
        logger.debug("🔒 Verbindung zur SQLite-Datenbank geschlossen.")

@app.route('/api/jahresstatistik', methods=['GET'])
def get_jahresstatistik():
    logger.debug("📊 API-Aufruf: /api/jahresstatistik")
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Verbrauchsdaten der letzten 5 Jahre berechnen
        logger.debug("🔍 Abfrage: Jahresstatistik der letzten 5 Jahre")
        statistik = cursor.execute("""
            SELECT strftime('%Y', timestamp) as jahr,
                   MAX(bezug_kwh) - MIN(bezug_kwh) as verbrauch
            FROM messwerte
            WHERE timestamp >= DATE('now', '-5 years')
            GROUP BY strftime('%Y', timestamp)
            ORDER BY jahr ASC
        """).fetchall()

        # Daten in ein JSON-kompatibles Format umwandeln
        statistik_data = [{"jahr": row["jahr"], "verbrauch": row["verbrauch"]} for row in statistik]
        logger.debug("📊 Jahresstatistik-Daten: %s", statistik_data)
        return jsonify(statistik_data)

    except Exception as e:
        logger.error("❌ Fehler beim Abrufen der Jahresstatistik: %s", str(e))
        return jsonify({"error": "Fehler beim Abrufen der Jahresstatistik"}), 500

    finally:
        conn.close()
        logger.debug("🔒 Verbindung zur SQLite-Datenbank geschlossen.")

@app.route('/api/statistik', methods=['GET'])
def get_statistik():
    logger.debug("📊 API-Aufruf: /api/statistik")
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Tag mit höchstem Verbrauch
        logger.debug("🔍 Abfrage: Tag mit höchstem Verbrauch")
        max_tag_row = cursor.execute("""
            SELECT DATE(timestamp) as datum, 
                   MAX(bezug_kwh) - MIN(bezug_kwh) as verbrauch
            FROM messwerte
            GROUP BY DATE(timestamp)
            ORDER BY verbrauch DESC
            LIMIT 1
        """).fetchone()
        max_tag = {"datum": max_tag_row["datum"], "verbrauch": max_tag_row["verbrauch"]} if max_tag_row else None

        # Tag mit niedrigstem Verbrauch
        logger.debug("🔍 Abfrage: Tag mit niedrigstem Verbrauch")
        min_tag_row = cursor.execute("""
            SELECT DATE(timestamp) as datum, 
                   MAX(bezug_kwh) - MIN(bezug_kwh) as verbrauch
            FROM messwerte
            GROUP BY DATE(timestamp)
            ORDER BY verbrauch ASC
            LIMIT 1
        """).fetchone()
        min_tag = {"datum": min_tag_row["datum"], "verbrauch": min_tag_row["verbrauch"]} if min_tag_row else None

        # Durchschnittlicher täglicher Verbrauch
        logger.debug("🔍 Abfrage: Durchschnittlicher täglicher Verbrauch")
        avg_tag_row = cursor.execute("""
            SELECT AVG(tagesverbrauch) as avg_verbrauch
            FROM (
                SELECT MAX(bezug_kwh) - MIN(bezug_kwh) as tagesverbrauch
                FROM messwerte
                GROUP BY DATE(timestamp)
            )
        """).fetchone()
        avg_tag = avg_tag_row["avg_verbrauch"] if avg_tag_row else 0

        # Monat mit höchstem Verbrauch
        logger.debug("🔍 Abfrage: Monat mit höchstem Verbrauch")
        max_monat_row = cursor.execute("""
            SELECT strftime('%Y-%m', timestamp) as monat, 
                   MAX(bezug_kwh) - MIN(bezug_kwh) as verbrauch
            FROM messwerte
            GROUP BY strftime('%Y-%m', timestamp)
            ORDER BY verbrauch DESC
            LIMIT 1
        """).fetchone()
        max_monat = {"monat": max_monat_row["monat"], "verbrauch": max_monat_row["verbrauch"]} if max_monat_row else None

        # Monat mit niedrigstem Verbrauch
        logger.debug("🔍 Abfrage: Monat mit niedrigstem Verbrauch")
        min_monat_row = cursor.execute("""
            SELECT strftime('%Y-%m', timestamp) as monat, 
                   MAX(bezug_kwh) - MIN(bezug_kwh) as verbrauch
            FROM messwerte
            GROUP BY strftime('%Y-%m', timestamp)
            ORDER BY verbrauch ASC
            LIMIT 1
        """).fetchone()
        min_monat = {"monat": min_monat_row["monat"], "verbrauch": min_monat_row["verbrauch"]} if min_monat_row else None

        # Durchschnittlicher monatlicher Verbrauch
        logger.debug("🔍 Abfrage: Durchschnittlicher monatlicher Verbrauch")
        avg_monat_row = cursor.execute("""
            SELECT AVG(monatsverbrauch) as avg_verbrauch
            FROM (
                SELECT MAX(bezug_kwh) - MIN(bezug_kwh) as monatsverbrauch
                FROM messwerte
                GROUP BY strftime('%Y-%m', timestamp)
            )
        """).fetchone()
        avg_monat = avg_monat_row["avg_verbrauch"] if avg_monat_row else 0

        # API-Antwort erstellen
        response = {
            "maxTag": max_tag,
            "minTag": min_tag,
            "avgTag": avg_tag,
            "maxMonat": max_monat,
            "minMonat": min_monat,
            "avgMonat": avg_monat
        }
        logger.debug("📤 API-Antwort: %s", response)
        return jsonify(response)

    except Exception as e:
        logger.error("❌ Fehler beim Abrufen der Statistik: %s", str(e))
        return jsonify({"error": "Fehler beim Abrufen der Statistik"}), 500

    finally:
        conn.close()
        logger.debug("🔒 Verbindung zur SQLite-Datenbank geschlossen.")

if __name__ == '__main__':
    logger.debug("🚀 Starte Flask-Server auf Port 5000...")
    app.run(host='0.0.0.0', port=5000)