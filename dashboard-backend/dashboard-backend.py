from flask import Flask, jsonify
import sqlite3

app = Flask(__name__)
DB_PATH = "/app/data/strom.sqlite"

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # Damit die Ergebnisse als Dictionary zurückgegeben werden
    return conn

@app.route('/api/dashboard', methods=['GET'])
def get_dashboard_data():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Beispielabfragen
    leistung = cursor.execute("SELECT wirkleistung_watt FROM messwerte ORDER BY timestamp DESC LIMIT 1").fetchone()
    bezug = cursor.execute("SELECT SUM(bezug_kwh) FROM messwerte WHERE DATE(timestamp) = DATE('now')").fetchone()
    einspeisung = cursor.execute("SELECT SUM(einspeisung_kwh) FROM messwerte WHERE DATE(timestamp) = DATE('now')").fetchone()
    verbrauch_heute = cursor.execute("SELECT SUM(bezug_kwh) FROM messwerte WHERE DATE(timestamp) = DATE('now')").fetchone()
    verbrauch_gestern = cursor.execute("SELECT SUM(bezug_kwh) FROM messwerte WHERE DATE(timestamp) = DATE('now', '-1 day')").fetchone()

    conn.close()

    # Daten als JSON zurückgeben
    return jsonify({
        "leistung": leistung["wirkleistung_watt"] if leistung else 0,
        "bezug": bezug["SUM(bezug_kwh)"] if bezug else 0,
        "einspeisung": einspeisung["SUM(einspeisung_kwh)"] if einspeisung else 0,
        "verbrauchHeute": verbrauch_heute["SUM(bezug_kwh)"] if verbrauch_heute else 0,
        "verbrauchGestern": verbrauch_gestern["SUM(bezug_kwh)"] if verbrauch_gestern else 0
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)