from flask import Flask, jsonify, request
from datetime import datetime, date, timedelta, timezone
from zoneinfo import ZoneInfo

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

LOCAL_TIMEZONE = ZoneInfo("Europe/Berlin")


def calendar_expression(conn):
    """Compile Berlin offset intervals into native SQLite date arithmetic.

    ZoneInfo supplies historical/DST rules once per connection, rather than
    invoking Python separately for every measurement in each aggregation.
    """
    first = conn.execute("SELECT timestamp FROM messwerte ORDER BY timestamp LIMIT 1").fetchone()
    last = conn.execute("SELECT timestamp FROM messwerte ORDER BY timestamp DESC LIMIT 1").fetchone()
    if not first:
        return "datetime(timestamp)"
    start_year = datetime.fromisoformat(first[0]).year
    end_year = datetime.fromisoformat(last[0]).year + 1
    current = datetime(start_year, 1, 1, tzinfo=timezone.utc)
    end = datetime(end_year, 1, 1, tzinfo=timezone.utc)

    def offset(moment):
        return int(moment.astimezone(LOCAL_TIMEZONE).utcoffset().total_seconds())

    previous_offset = offset(current)
    cases = []
    while current < end:
        following = min(current + timedelta(days=1), end)
        following_offset = offset(following)
        if following_offset != previous_offset:
            low, high = int(current.timestamp()), int(following.timestamp())
            while high - low > 1:
                middle = (low + high) // 2
                if offset(datetime.fromtimestamp(middle, timezone.utc)) == previous_offset:
                    low = middle
                else:
                    high = middle
            boundary = datetime.fromtimestamp(high, timezone.utc).isoformat(timespec="microseconds")
            cases.append(f"WHEN timestamp < '{boundary}' THEN datetime(timestamp, '{previous_offset:+d} seconds')")
            previous_offset = following_offset
        current = following
    if not cases:
        return f"datetime(timestamp, '{previous_offset:+d} seconds')"
    return "CASE " + " ".join(cases) + f" ELSE datetime(timestamp, '{previous_offset:+d} seconds') END"


def utc_midnight(d):
    return datetime.combine(d, datetime.min.time(), LOCAL_TIMEZONE).astimezone(
        timezone.utc
    ).isoformat(timespec="microseconds")


def get_day_range(d: date):
    """Index-friendly UTC bounds for a Berlin day (23, 24 or 25 hours)."""
    return utc_midnight(d), utc_midnight(d + timedelta(days=1))


def rolling_start(months):
    today = datetime.now(LOCAL_TIMEZONE).date()
    year, month_index = divmod(today.year * 12 + today.month - 1 - months, 12)
    # Match SQLite's overflow semantics for e.g. February 29 minus one year.
    cutoff = date(year, month_index + 1, 1) + timedelta(days=today.day - 1)
    return utc_midnight(cutoff)


def parse_date(value: str):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None

def get_db_connection():
    logger.debug("🔌 Verbindung zur SQLite-Datenbank herstellen...")
    conn = sqlite3.connect(DB_PATH, timeout=SQLITE_TIMEOUT_SECONDS)
    if conn.execute("PRAGMA user_version").fetchone()[0] != 3:
        conn.close()
        raise sqlite3.DatabaseError("UTC schema 3 required; migrate database first")
    expression = calendar_expression(conn)
    conn.execute(f"""CREATE TEMP VIEW calendar_messwerte AS SELECT *,
        substr(({expression}), 1, 10) AS local_day,
        substr(({expression}), 1, 7) AS local_month,
        substr(({expression}), 1, 4) AS local_year FROM messwerte""")
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
            FROM calendar_messwerte
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
            FROM calendar_messwerte
        """).fetchone()
        bezug = gesamt_row["bezug"] if gesamt_row and gesamt_row["bezug"] is not None else 0
        einspeisung = gesamt_row["einspeisung"] if gesamt_row and gesamt_row["einspeisung"] is not None else 0
        
        heute = datetime.now(LOCAL_TIMEZONE).date()
        start, end = get_day_range(heute)
        # Verbrauch und Leistungsstatistik heute gemeinsam berechnen
        logger.debug("🔍 Abfrage: Tagesstatistik heute")
        heute_stats = cursor.execute("""
            SELECT MAX(bezug_kwh) - MIN(bezug_kwh) AS verbrauch,
                   MAX(wirkleistung_watt) AS max_watt,
                   MIN(wirkleistung_watt) AS min_watt,
                   AVG(wirkleistung_watt) AS avg_watt
            FROM calendar_messwerte
            WHERE timestamp >= ? AND timestamp < ?
        """, (start, end)).fetchone()
        verbrauch_heute = heute_stats["verbrauch"] if heute_stats and heute_stats["verbrauch"] is not None else 0

        gestern = heute - timedelta(days=1)
        start, end = get_day_range(gestern)
        # Verbrauch und Leistungsstatistik gestern gemeinsam berechnen
        logger.debug("🔍 Abfrage: Tagesstatistik gestern")
        gestern_stats = cursor.execute("""
            SELECT MAX(bezug_kwh) - MIN(bezug_kwh) AS verbrauch,
                   MAX(wirkleistung_watt) AS max_watt,
                   MIN(wirkleistung_watt) AS min_watt,
                   AVG(wirkleistung_watt) AS avg_watt
            FROM calendar_messwerte
            WHERE timestamp >= ? AND timestamp < ?
        """, (start,end)).fetchone()
        verbrauch_gestern = gestern_stats["verbrauch"] if gestern_stats and gestern_stats["verbrauch"] is not None else 0

        # Tendenz berechnen
        logger.debug("🔍 Abfrage: Tendenz")
        
        # Aktuelle Zeit
        jetzt = datetime.now(LOCAL_TIMEZONE)

        # Prozentualer Anteil des Tages
        day_start, day_end = map(datetime.fromisoformat, get_day_range(heute))
        anteil_tag = ((jetzt.astimezone(timezone.utc) - day_start).total_seconds()
                      / (day_end - day_start).total_seconds() * 100)
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
        heute = datetime.now(LOCAL_TIMEZONE).date()
        start, end = get_day_range(heute)
        # Tagesverlauf-Daten abrufen
        verlauf = cursor.execute("""
            SELECT timestamp, wirkleistung_watt 
            FROM calendar_messwerte
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
        start = utc_midnight(start_date)
        end = utc_midnight(start_date + timedelta(days=7))
        statistik = cursor.execute("""
            SELECT local_day AS datum,
                   MAX(bezug_kwh) - MIN(bezug_kwh) as tagesverbrauch
            FROM calendar_messwerte
            WHERE timestamp >= ? AND timestamp < ?
            GROUP BY local_day
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
            FROM calendar_messwerte
            WHERE timestamp >= ? AND timestamp < ?
        """, (start, end)).fetchone()
        verbrauch = werte_row["verbrauch"] if werte_row and werte_row["verbrauch"] is not None else 0
        endstand = werte_row["endstand"] if werte_row and werte_row["endstand"] is not None else 0

        # Tagesverlauf abrufen (Leistung über den Tag)
        logger.debug("🔍 Abfrage: Tagesverlauf für %s", datum)
        verlauf = cursor.execute("""
            SELECT timestamp, wirkleistung_watt
            FROM calendar_messwerte
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
            SELECT local_month as monat,
                   MAX(bezug_kwh) - MIN(bezug_kwh) as verbrauch
            FROM calendar_messwerte
            WHERE timestamp >= ?
            GROUP BY local_month
            ORDER BY monat ASC
        """, (rolling_start(12),)).fetchall()

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
            SELECT local_year as jahr,
                   MAX(bezug_kwh) - MIN(bezug_kwh) as verbrauch
            FROM calendar_messwerte
            WHERE timestamp >= ?
            GROUP BY local_year
            ORDER BY jahr ASC
        """, (rolling_start(60),)).fetchall()

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
            SELECT DISTINCT local_day as datum
            FROM calendar_messwerte
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
        today_start = utc_midnight(datetime.now(LOCAL_TIMEZONE).date())
        logger.debug("🔍 Abfrage: Tages- und Monatsstatistik")
        daily_rows = cursor.execute("""
            SELECT local_day AS periode,
                   MAX(bezug_kwh) - MIN(bezug_kwh) AS verbrauch
            FROM calendar_messwerte
            WHERE timestamp < ?
            GROUP BY local_day
        """, (today_start,)).fetchall()
        monthly_rows = cursor.execute("""
            SELECT local_month AS periode,
                   MAX(bezug_kwh) - MIN(bezug_kwh) AS verbrauch
            FROM calendar_messwerte
            GROUP BY local_month
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
