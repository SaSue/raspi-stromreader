from flask import Flask, jsonify, request
from datetime import datetime, date, timedelta

import sqlite3
import logging
import os

app = Flask(__name__)
DB_PATH = os.getenv("DB_PATH", "/app/data/strom.sqlite")
SQLITE_TIMEOUT_SECONDS = float(os.getenv("SQLITE_TIMEOUT_SECONDS", "10"))

# === Logging einrichten ===
logging.basicConfig(
    level=logging.INFO,  # Setze das Logging-Level auf DEBUG
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("dashboard-backend")

def get_day_range(d: date):
    """Return index-friendly ISO date bounds for one local calendar day."""
    return d.isoformat(), (d + timedelta(days=1)).isoformat()


def parse_date(value: str):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None

def get_db_connection():
    logger.debug("🔌 Verbindung zur SQLite-Datenbank herstellen...")
    conn = sqlite3.connect(DB_PATH, timeout=SQLITE_TIMEOUT_SECONDS)
    conn.row_factory = sqlite3.Row  # Damit die Ergebnisse als Dictionary zurückgegeben werden
    conn.execute("PRAGMA busy_timeout = 10000")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA query_only = ON")
    logger.debug("✅ Verbindung erfolgreich hergestellt.")
    return conn

@app.route('/api/dashboard', methods=['GET'])
def get_dashboard_data():
    logger.debug("📊 API-Aufruf: /api/dashboard")
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        
        # Momentanverbrauch
        logger.debug("🔍 Abfrage: Momentanverbrauch")
        leistung_row = cursor.execute("""
            SELECT wirkleistung_watt, timestamp
            FROM messwerte
            ORDER BY timestamp DESC
            LIMIT 1
        """).fetchone()
        leistung = leistung_row["wirkleistung_watt"] if leistung_row else 0
        letzter_timestamp = leistung_row["timestamp"] if leistung_row else None

        # Gesamtzaehlerstaende in einem Tabellendurchlauf bestimmen
        logger.debug("🔍 Abfrage: Bezug und Einspeisung gesamt")
        gesamt_row = cursor.execute("""
            SELECT MAX(bezug_kwh) AS bezug,
                   MAX(einspeisung_kwh) AS einspeisung
            FROM messwerte
        """).fetchone()
        bezug = gesamt_row["bezug"] if gesamt_row and gesamt_row["bezug"] is not None else 0
        einspeisung = gesamt_row["einspeisung"] if gesamt_row and gesamt_row["einspeisung"] is not None else 0
        
        heute = date.today()
        start, end = get_day_range(heute)
        # Verbrauch und Leistungsstatistik heute gemeinsam berechnen
        logger.debug("🔍 Abfrage: Tagesstatistik heute")
        heute_stats = cursor.execute("""
            SELECT MAX(bezug_kwh) - MIN(bezug_kwh) AS verbrauch,
                   MAX(wirkleistung_watt) AS max_watt,
                   MIN(wirkleistung_watt) AS min_watt,
                   AVG(wirkleistung_watt) AS avg_watt
            FROM messwerte
            WHERE timestamp >= ? AND timestamp < ?
        """, (start, end)).fetchone()
        verbrauch_heute = heute_stats["verbrauch"] if heute_stats and heute_stats["verbrauch"] is not None else 0

        gestern = date.today() - timedelta(days=1)
        start, end = get_day_range(gestern)
        # Verbrauch und Leistungsstatistik gestern gemeinsam berechnen
        logger.debug("🔍 Abfrage: Tagesstatistik gestern")
        gestern_stats = cursor.execute("""
            SELECT MAX(bezug_kwh) - MIN(bezug_kwh) AS verbrauch,
                   MAX(wirkleistung_watt) AS max_watt,
                   MIN(wirkleistung_watt) AS min_watt,
                   AVG(wirkleistung_watt) AS avg_watt
            FROM messwerte
            WHERE timestamp >= ? AND timestamp < ?
        """, (start,end)).fetchone()
        verbrauch_gestern = gestern_stats["verbrauch"] if gestern_stats and gestern_stats["verbrauch"] is not None else 0

        # Tendenz berechnen
        logger.debug("🔍 Abfrage: Tendenz")
        
        # Aktuelle Zeit
        jetzt = datetime.now()  
        aktuelle_stunde = jetzt.hour
        aktuelle_minute = jetzt.minute

        # Prozentualer Anteil des Tages
        anteil_tag = (aktuelle_stunde * 60 + aktuelle_minute) / (24 * 60) * 100
        logger.debug("🔍 Abfrage: Prozentualer Anteil des Tages: %.2f%%", anteil_tag)

        # Berechnung der Tendenz
        verbrauch_gestern_anteil = verbrauch_gestern * (anteil_tag / 100)

        if abs(verbrauch_heute - verbrauch_gestern_anteil) <= verbrauch_gestern_anteil * 0.01:
            tendenz = "gleich"
        elif verbrauch_heute > verbrauch_gestern_anteil * 1.01 and verbrauch_heute <= verbrauch_gestern_anteil * 1.10:
            tendenz = "mehr"
        elif verbrauch_heute > verbrauch_gestern_anteil * 1.10:
            tendenz = "viel mehr"
        elif verbrauch_heute < verbrauch_gestern_anteil * 0.99 and verbrauch_heute >= verbrauch_gestern_anteil * 0.90:
            tendenz = "weniger"
        elif verbrauch_heute < verbrauch_gestern_anteil * 0.90:
            tendenz = "viel weniger"
        else:
            tendenz = "unbekannt"  # Fallback für unerwartete Fälle

        logger.debug("🔍 Tendenz: %s", tendenz)
        
        max_heute = heute_stats["max_watt"] if heute_stats and heute_stats["max_watt"] is not None else 0
        min_heute = heute_stats["min_watt"] if heute_stats and heute_stats["min_watt"] is not None else 0
        avg_heute = round(heute_stats["avg_watt"], 2) if heute_stats and heute_stats["avg_watt"] is not None else 0

        max_gestern = gestern_stats["max_watt"] if gestern_stats and gestern_stats["max_watt"] is not None else 0
        min_gestern = gestern_stats["min_watt"] if gestern_stats and gestern_stats["min_watt"] is not None else 0
        avg_gestern = round(gestern_stats["avg_watt"], 2) if gestern_stats and gestern_stats["avg_watt"] is not None else 0

        # Daten als JSON zurückgeben
        response = {
            "leistung": leistung,
            "timestamp": letzter_timestamp,
            "bezug": bezug,
            "einspeisung": einspeisung,
            "verbrauchHeute": verbrauch_heute,
            "tendenz" : tendenz,
            "verbrauchGestern": verbrauch_gestern,
            "maxHeute": max_heute,
            "minHeute": min_heute,
            "avgHeute": avg_heute,
            "maxGestern": max_gestern,
            "minGestern": min_gestern,
            "avgGestern": avg_gestern
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
        heute = date.today()
        start, end = get_day_range(heute)
        # Tagesverlauf-Daten abrufen
        verlauf = cursor.execute("""
            SELECT timestamp, wirkleistung_watt 
            FROM messwerte 
            WHERE timestamp >= ? AND timestamp < ?
            ORDER BY timestamp ASC
        """,(start,end)).fetchall()

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
    start_date = parse_date(datum)
    if not start_date:
        logger.error("❌ Kein Datum angegeben.")
        return jsonify({"error": "Kein Datum angegeben"}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Wochenstatistik-Daten abrufen (Startdatum + 6 Tage)
        logger.debug("🔍 Abfrage: Wochenstatistik ab %s", datum)
        start = start_date.isoformat()
        end = (start_date + timedelta(days=7)).isoformat()
        statistik = cursor.execute("""
            SELECT substr(timestamp, 1, 10) AS datum,
                   MAX(bezug_kwh) - MIN(bezug_kwh) as tagesverbrauch
            FROM messwerte
            WHERE timestamp >= ? AND timestamp < ?
            GROUP BY substr(timestamp, 1, 10)
            ORDER BY datum ASC
        """, (start, end)).fetchall()

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
    selected_date = parse_date(datum)
    if not selected_date:
        logger.error("❌ Kein Datum angegeben.")
        return jsonify({"error": "Kein Datum angegeben"}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        start, end = get_day_range(selected_date)
        # Tagesverbrauch und Endstand in einem Durchlauf berechnen
        logger.debug("🔍 Abfrage: Tageswerte für %s", datum)
        werte_row = cursor.execute("""
            SELECT MAX(bezug_kwh) - MIN(bezug_kwh) AS verbrauch,
                   MAX(bezug_kwh) AS endstand
            FROM messwerte
            WHERE timestamp >= ? AND timestamp < ?
        """, (start, end)).fetchone()
        verbrauch = werte_row["verbrauch"] if werte_row and werte_row["verbrauch"] is not None else 0
        endstand = werte_row["endstand"] if werte_row and werte_row["endstand"] is not None else 0

        # Tagesverlauf abrufen (Leistung über den Tag)
        logger.debug("🔍 Abfrage: Tagesverlauf für %s", datum)
        verlauf = cursor.execute("""
            SELECT timestamp, wirkleistung_watt
            FROM messwerte
            WHERE timestamp >= ? AND timestamp < ?
            ORDER BY timestamp ASC
        """, (start, end)).fetchall()

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
        
@app.route('/api/verfuegbare-tage', methods=['GET'])
def get_verfuegbare_tage():
    logger.debug("📊 API-Aufruf: /api/verfuegbare-tage")
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Abrufen der Tage, für die Messwerte vorhanden sind
        logger.debug("🔍 Abfrage: Verfügbare Tage mit Messwerten")
        tage = cursor.execute("""
            SELECT DISTINCT DATE(timestamp) as datum
            FROM messwerte
            ORDER BY datum ASC
        """).fetchall()

        # Daten in ein JSON-kompatibles Format umwandeln
        tage_data = [row["datum"] for row in tage]
        logger.debug("📊 Verfügbare Tage: %s", tage_data)
        return jsonify(tage_data)

    except Exception as e:
        logger.error("❌ Fehler beim Abrufen der verfügbaren Tage: %s", str(e))
        return jsonify({"error": "Fehler beim Abrufen der verfügbaren Tage"}), 500

    finally:
        conn.close()
        logger.debug("🔒 Verbindung zur SQLite-Datenbank geschlossen.")

@app.route('/api/statistik', methods=['GET'])
def get_statistik():
    logger.debug("📊 API-Aufruf: /api/statistik")
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Jede Aggregationsebene nur einmal aus der Datenbank lesen.
        today_start = date.today().isoformat()
        logger.debug("🔍 Abfrage: Tages- und Monatsstatistik")
        daily_rows = cursor.execute("""
            SELECT substr(timestamp, 1, 10) AS periode,
                   MAX(bezug_kwh) - MIN(bezug_kwh) AS verbrauch
            FROM messwerte
            WHERE timestamp < ?
            GROUP BY substr(timestamp, 1, 10)
        """, (today_start,)).fetchall()
        monthly_rows = cursor.execute("""
            SELECT substr(timestamp, 1, 7) AS periode,
                   MAX(bezug_kwh) - MIN(bezug_kwh) AS verbrauch
            FROM messwerte
            GROUP BY substr(timestamp, 1, 7)
        """).fetchall()

        def summarize(rows, key):
            values = [row for row in rows if row["verbrauch"] is not None]
            if not values:
                return None, None, 0
            highest = max(values, key=lambda row: row["verbrauch"])
            lowest = min(values, key=lambda row: row["verbrauch"])
            average = sum(row["verbrauch"] for row in values) / len(values)
            return (
                {key: highest["periode"], "verbrauch": highest["verbrauch"]},
                {key: lowest["periode"], "verbrauch": lowest["verbrauch"]},
                average,
            )

        max_tag, min_tag, avg_tag = summarize(daily_rows, "datum")
        max_monat, min_monat, avg_monat = summarize(monthly_rows, "monat")

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
