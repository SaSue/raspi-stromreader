#!/usr/bin/env python3
import serial
import time
import logging
import binascii
import crcmod
import argparse
import os
import json
import sqlite3
from pathlib import Path
from zoneinfo import ZoneInfo
from datetime import datetime

# Logging konfigurieren
parser = argparse.ArgumentParser()
parser.add_argument("--debug", action="store_true", help="Aktiviere Debug-Ausgabe")
args = parser.parse_args()

# Überprüfen, ob der Debug-Modus aktiviert ist
# Überprüfen, ob der Debug-Modus über Umgebungsvariablen aktiviert ist
# DEBUG=1 oder DEBUG=true
# DEBUG=0 oder DEBUG=false
debug_env = os.getenv("DEBUG", "0").lower() in ("1", "true", "yes")
debug_mode = args.debug or debug_env
# Setze den Logging-Level basierend auf dem Debug-Modus
logging.basicConfig(
    level=logging.DEBUG if debug_mode else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

logging.debug("args.debug: %s", args.debug)
logging.debug("os.getenv('DEBUG'): %s", os.getenv('DEBUG'))
logging.debug("debug_env: %s", debug_env)
logging.debug("debug_mode: %s", debug_mode)

logging.info("Debug-Modus: %s", "Aktiviert" if debug_mode else "Deaktiviert")

# Umgebungsvariablen laden
# Übernehme die Umgebungsvariable OUTPUT
output_modes = os.getenv("OUTPUT", "sqlite").lower().split(",")
logging.info("📤 Ausgabemodi: %s", output_modes)


# Zeitkontrolle für JSON-Speicherung 
# Standardwert auf 0 setzen
# und dann auf den Wert aus environment setzen
# wenn der Wert nicht gesetzt ist, wird der Standardwert 60 Sekunden verwendet
last_json_write = 0
wait_time = int(os.getenv("WAIT_TIMER", 60))  # Standardwert 60 Sekunden, kann aber in der .env-Datei überschrieben werden
# entspricht der Zeit, die gewartet wird, bevor die JSON-Datei/Datenbank gespeichert wird
logging.info("⏳ Wartezeit für JSON-Speicherung (wait_time): %d Sekunden", wait_time)

# Hersteller aus Umgebungsvariable lesen
MANUFACTURER = os.getenv("MANUFACTURER", "1")  # Standardwert 1
logging.info("🏭 Herstellerkennung eingestellt auf: %s", MANUFACTURER) 

# Speicherpfade für JSON
OUTPUT_PATH = Path("/app/data")
logging.debug("📂 Speicherpfad: %s", OUTPUT_PATH)
HISTORY_PATH = OUTPUT_PATH / "history"
HISTORY_PATH.mkdir(parents=True, exist_ok=True)
logging.debug("📂 Historie-Pfad: %s", HISTORY_PATH)

# SQLite-Datei definieren
DB_PATH = Path("/app/data/strom.sqlite")
logging.debug("📂 SQLite-Pfad: %s", DB_PATH
              )
# Sicherstellen, dass die Datenbank existiert
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
logging.debug("📂 SQLite-Datenbankverzeichnis erstellt: %s", DB_PATH.parent)

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

# Tabellen erstellen, falls sie nicht existieren
c.execute("""
CREATE TABLE IF NOT EXISTS zaehler (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    seriennummer TEXT UNIQUE,
    hersteller TEXT,
    name TEXT
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS messwerte (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    zaehler_id INTEGER,
    timestamp TEXT,
    bezug_kwh REAL,
    einspeisung_kwh REAL,
    wirkleistung_watt REAL,
    FOREIGN KEY (zaehler_id) REFERENCES zaehler(id)
)
""")

# Prüfen, ob der Index existiert
c.execute("""
SELECT name 
FROM sqlite_master 
WHERE type='index' AND name='idx_timestamp';
""")
index_exists = c.fetchone()

# Wenn nicht, erstelle ihn
if not index_exists:
    logging.debug("🔍 Index 'idx_timestamp' existiert nicht. Erstelle Index...")
    c.execute("CREATE INDEX idx_timestamp ON messwerte(timestamp);")
    logging.debug("✅ Index 'idx_timestamp' wurde erstellt.")
else:
    logging.debug("✅ Index 'idx_timestamp' existiert bereits.")

conn.commit()
conn.close()

# Klassen für Messwerte und Zähler
class LeserKonfiguration:
    """
    Konfiguration für den Leser.
    :param port: Der serielle Port (z. B. /dev/ttyUSB0).
    :param baudrate: Die Baudrate (z. B. 9600).
    :param hersteller_env: Herstellerkennung aus der Umgebungsvariable.
    :param hersteller: OBIS-Code für den Hersteller.
    :param sn: OBIS-Code für die Seriennummer.
    :param leistung: OBIS-Code für die Wirkleistung.
    :param bezug: OBIS-Code für den Bezug.
    :param einspeisung: OBIS-Code für die Einspeisung.
    :param sml_ende: Endezeichen für das SML-Telegramm.
    """
    def __init__(self, port, baudrate, hersteller_env, hersteller, sn, leistung, bezug, einspeisung, sml_ende):
        self.port = port
        self.baudrate = baudrate
        self.hersteller_env = hersteller_env
        self.hersteller = hersteller
        self.sn = sn
        self.leistung = leistung
        self.bezug = bezug
        self.einspeisung = einspeisung
        self.sml_ende = sml_ende

#hier geht es dann weiter
class Messwert:
    """
    Klasse für Messwerte.
    :param wert: Der Wert des Messwerts.
    :param einheit: Die Einheit des Messwerts.
    :param obis: Der OBIS-Code des Messwerts.
    """
    def __init__(self, wert, einheit, obis):
        self.wert = wert
        self.einheit = einheit
        self.obis = obis
        
class Zaehler:
    """
    Klasse für Zähler.
    :param vendor: Der Hersteller des Zählers.
    :param sn: Die Seriennummer des Zählers.
    :param leistung: Die Wirkleistung des Zählers.
    :param bezug: Der Bezug des Zählers.
    :param einspeisung: Die Einspeisung des Zählers.
    """
    def __init__(self, vendor, sn, leistung, bezug, einspeisung):
        self.vendor = vendor
        self.sn = sn
        self.leistung = leistung
        self.bezug = bezug
        self.einspeisung = einspeisung

class OBIS_Object:
    """
    Klasse für OBIS-Objekte.
    :param code: Der OBIS-Code des Objekts.
    :param start: Die Startposition des Objekts im SML-Telegramm.
    :param factor: Der Skalenfaktor des Objekts.
    :param einheit: Die Einheit des Objekts.
    :param wert: Der Wert des Objekts.
    """
    def __init__(self, code, start, factor, einheit, wert):
        self.code = code
        self.start = start
        self.factor = factor
        self.einheit = einheit
        self.wert = wert

class OBIS_Unterobject:
    """
    Klasse für OBIS-Unterobjekte.
    :param offset: Der Offset des Unterobjekts im SML-Telegramm.
    :param laenge: Die Länge des Unterobjekts im SML-Telegramm.
    """
    def __init__(self, offset, laenge):
        self.offset = offset
        self.laenge = laenge    

# Funktion: Werte speichern
def save_to_sqlite(seriennummer, hersteller, bezug_kwh, einspeisung_kwh, wirkleistung_watt):
    """
    Speichert die Messwerte in der SQLite-Datenbank.
    :param seriennummer: Die Seriennummer des Zählers.
    :param hersteller: Der Hersteller des Zählers.
    :param bezug_kwh: Der Bezug in kWh.
    :param einspeisung_kwh: Die Einspeisung in kWh.
    :param wirkleistung_watt: Die Wirkleistung in Watt.
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Zähler-ID abrufen oder einfügen
    c.execute("SELECT id FROM zaehler WHERE seriennummer = ?", (seriennummer,))
    row = c.fetchone()
    if row:
        zaehler_id = row[0]
        logging.debug("🔍 Zähler-ID gefunden: %s", zaehler_id)
    else:
        c.execute("INSERT INTO zaehler (seriennummer, hersteller) VALUES (?, ?)", (seriennummer, hersteller))
        zaehler_id = c.lastrowid
        logging.debug("💾 Neuer Zähler in SQLite gespeichert: %s", (seriennummer, hersteller))

    # Messwert einfügen
    timestamp = datetime.now().isoformat()
    c.execute("""
        INSERT INTO messwerte (zaehler_id, timestamp, bezug_kwh, einspeisung_kwh, wirkleistung_watt)
        VALUES (?, ?, ?, ?, ?)
    """, (zaehler_id, timestamp, bezug_kwh, einspeisung_kwh, wirkleistung_watt))

    conn.commit()
    conn.close()
    logging.debug("💾 Messwerte in SQLite gespeichert: %s", (seriennummer, bezug_kwh, einspeisung_kwh, wirkleistung_watt))


def decode_manufacturer(hex_string):
    """
    Wandelt einen Hex-String wie '04454D48' in einen lesbaren Hersteller-Code (z. B. 'EMH') um.
    Ignoriert das erste Byte (Längen-/Typkennzeichen).
    :param hex_string: Der Hex-String, der den Hersteller-Code enthält.
    :return: Ein lesbarer Hersteller-Code.
    Beispiel: '04454D48' wird zu 'EMH'.
    """
    # Sicherstellen, dass der String eine gerade Anzahl von Zeichen hat
    hex_string = hex_string.strip().lower()
    if len(hex_string) < 8:
        raise ValueError("Ungültiger Hersteller-Code: zu kurz")

    # Die letzten 3 Bytes (6 Zeichen) nehmen
    ascii_part = hex_string[-6:]
    try:
        readable = bytes.fromhex(ascii_part).decode("ascii")
        return readable
    except Exception as e:
        return f"Fehler beim Decodieren: {e}"

def parse_device_id(hex_string):
    """
    Extrahiert die Gerätekennung aus einem vollständigen Hex-String.
    Erwartet mindestens 10 Bytes nach dem TL-Feld (z.B. '0b0a01454d4xxxxx'). 
    Ignoriert das TL-Feld und gibt den Hersteller und die Seriennummer zurück.
    Beispiel: 'EMH-0000xxxxxxx'
    :param hex_string: Der vollständige Hex-String.
    :return: Ein String im Format 'Hersteller-Seriennummer'.
    """
    try:
        # Nimmt nur den tatsächlichen Inhalt ohne das TL-Feld (z. B. nach '0b0a01')
        payload = hex_string[6:]  # ab Index 6 → 454d48xxxx
        ascii_part = payload[:6]  # 454xxx
        serial_part = payload[6:] # 0000xxxx

        hersteller = bytes.fromhex(ascii_part).decode("ascii")
        seriennummer = serial_part.upper()

        return f"{hersteller}-{seriennummer}"
    except Exception as e:
        return f"Fehler beim Parsen: {e}"
        
def crc_check(crc_raw,sml_telegram):
    """
    Prüft die CRC-Prüfziffer des SML-Telegramms.
    :param crc_raw: Die Rohdaten der CRC-Prüfziffer (2 Bytes).
    :param sml_telegram: Das gesamte SML-Telegramm (Bytes).
    :return: True, wenn die CRC-Prüfziffer gültig ist, sonst False.
    """
    crc_func = crcmod.mkCrcFun(0x11021, initCrc=0, xorOut=0xFFFF, rev=True)
    if crc_func(sml_telegram) == int.from_bytes(crc_raw, "little"):
        logging.debug("CRC Prüfung erfolgreich")
        return True
    else:
        logging.debug("CRC Prüfung fehlgeschlagen")
        return False
        
def wert_suchen(sml_telegram,idx_position,idx_offset,idx_len):
    """
    Sucht den Wert im SML-Telegramm.
    :param sml_telegram: Das SML-Telegramm (Bytes).
    :param idx_position: Startposition im Telegramm.
    :param idx_offset: Offset für den Wert.
    :param idx_len: Länge des Wertes.
    :return: Der gefundene Wert (Bytes).
    """
    return sml_telegram[idx_position + idx_offset:idx_position + idx_offset + idx_len]

def skalieren(wert, skala):
    """
    Skaliert den Wert mit dem angegebenen Skalenfaktor.
    :param wert: Der Wert, der skaliert werden soll (int oder float).
    :param skala: Der Skalenfaktor (int).
    :return: Der skalierte Wert (float).
    Beispiel: Wenn wert = 123 und skala = 2, dann wird der Wert zu 12300 skaliert, mit 0.01 = 1.23
    :param wert: Der Wert, der skaliert werden soll.
    :param skala: Der Skalenfaktor (int).
    :return: Der skalierte Wert (float).
    """
    if skala == 0:
        return wert
    else:
        return wert * (10 ** skala)

def einheit_suchen(einheit_raw):
    """
    Sucht die Einheit im SML-Telegramm.
    :param einheit_raw: Die Rohdaten der Einheit (Bytes).
    :return: Die Einheit als String.
    """
    if einheit_raw == b"\x62\x1e":  # Wh
        return "Wh"
    elif einheit_raw == b"\x62\x1b":  # W
        return "W"
    else:
        logging.warning("⚠️ Unbekannte Einheit: %s", einheit_raw.hex())
        return "unbekannte Einheit"

def convert_wh_to_kwh(value, unit):
    """
    Konvertiert einen Wert von Wh in kWh und passt die Einheit an.
    :param value: Der Wert in Wh (int oder float).
    :param unit: Die Einheit als String (z. B. "Wh").
    :return: Tuple (converted_value, converted_unit)
    """
    if unit == "Wh":
        converted_value = value / 1000  # Umrechnung in kWh
        converted_unit = "kWh"         # Einheit anpassen
    else:
        converted_value = value        # Keine Umrechnung, wenn Einheit nicht "Wh" ist
        converted_unit = unit          # Einheit bleibt unverändert

    return converted_value, converted_unit

# Hier wird die Konfiguration für den Leser gesetzt
if MANUFACTURER == "1": # EMH
    # Hier setzen wir die Konfiguration für den Leser
    # Diese Konfiguration wird dann in der Klasse LeserKonfiguration gespeichert
    # und später verwendet, um die Daten zu lesen
    tech_konfiguration = LeserKonfiguration(
        port="/dev/ttyUSB0" ,  # Port, ist immer gleich und kommt aus der Docker-Compose Datei
        baudrate=int(os.getenv("BAUDRATE", 9600)), # Baudrate, kommt aus der Umgebungsvariable
        hersteller_env=MANUFACTURER, # Herstellerkennung, kommt aus der Umgebungsvariable
        hersteller=OBIS_Object (
            code=b"\x07\x01\x00\x60\x32\x01\x01",  # OBIS-Code für den Hersteller
            start=None,  # Startposition wird erst ermittelt
            factor=None, # Herstellerkennung hat keinen Faktor
            einheit=None, # Herstellerkennung hat keine Einheit
            wert=OBIS_Unterobject (
                offset=11,  # Offset nach der Startposition
                laenge=4    # Länge nach dem Offset
            )
        ),
        sn=OBIS_Object ( # Seriennummer
            code=b"\x07\x01\x00\x60\x01\x00\xff",  # OBIS-Code für die Seriennummer, wird erst ermittelt
            start=None,  # Startposition wird erst ermittelt
            factor=None, # SN hat keinen Faktor
            einheit=None, # SN hat keine Einheit
            wert=OBIS_Unterobject (
                offset=11,  # Offset nach der Startposition
                laenge=11   # Länge nach dem Offset
            )
        ),
        leistung=OBIS_Object (
            code=b"\x07\x01\x00\x10\x07\x00\xff",  # OBIS-Code für die Wirkleistung
            start=None,  # Startposition wird erst ermittelt
            factor=OBIS_Unterobject (
                offset=19,  # Offset nach der Startposition
                laenge=1    # Länge nach dem Offset
            ),
            einheit=OBIS_Unterobject (
                offset=16,  # Offset nach der Startposition
                laenge=2    # Länge nach dem Offset
            ),
            wert=OBIS_Unterobject (
                offset=21,  # Offset nach der Startposition
                laenge=4    # Länge nach dem Offset
            )
        ),
        bezug=OBIS_Object (
            code=b"\x07\x01\x00\x01\x08\x00\xff",  # OBIS-Code für den Bezug
            start=None,  # Startposition wird erst ermittelt
            factor=OBIS_Unterobject (
                offset=22,  # Offset nach der Startposition
                laenge=1    # Länge nach dem Offset
            ),
            einheit=OBIS_Unterobject (
                offset=19,  # Offset nach der Startposition
                laenge=2    # Länge nach dem Offset
            ),
            wert=OBIS_Unterobject (
                offset=24,  # Offset nach der Startposition
                laenge=8    # Länge nach dem Offset
            )
        ),
        einspeisung=OBIS_Object (
            code=b"\x07\x01\x00\x02\x08\x00\xff",  # OBIS-Code für die Einspeisung
            start=None,  # Startposition wird erst ermittelt
            factor=OBIS_Unterobject (
                offset=19,  # Offset nach der Startposition
                laenge=1    # Länge nach dem Offset
            ),
            einheit=OBIS_Unterobject (
                offset=16,  # Offset nach der Startposition
                laenge=2    # Länge nach dem Offset
            ),
            wert=OBIS_Unterobject (
                offset=21,  # Offset nach der Startposition
                laenge=8    # Länge nach dem Offset
            )
        ),
        sml_ende=b"\x1b\x1b\x1b\x1a"
    )
else: # Hier kann eine andere Konfiguration für andere Hersteller gesetzt werden
    logging.error("❌ Herstellerkennung nicht unterstützt.")
    exit(1)

# Verbinde mit dem seriellen Port
# und öffne den Port
logging.debug("🔌 Verbinde mit %s @ %d Baud", 
              tech_konfiguration.port, 
              tech_konfiguration.baudrate)
try:
    # Öffne den seriellen Port
    ser = serial.Serial(
        tech_konfiguration.port,
        tech_konfiguration.baudrate, timeout=1)
    logging.debug("🔌 Verbindung erfolgreich hergestellt.")
except serial.SerialException as e:
    logging.error("❌ Fehler beim Öffnen des seriellen Ports: %s", e)
    exit(1)

# Endlosschleife zum Lesen der Daten
logging.debug("🔄 Starte Endlosschleife zum Lesen der Daten...")
  
buffer = b"" # Initialisiere den Buffer
while True:
    # Lese ein Byte vom seriellen Port 
    raw = ser.read(1)
    if not raw:
        continue
    # Füge das gelesene Byte zum Buffer hinzu
    buffer += raw

    # Suche nach Endezeichen
    if tech_konfiguration.sml_ende in buffer:
        idx = buffer.find(tech_konfiguration.sml_ende) # postion des Endezeichens
        if idx == -1 or len(buffer) < idx + 4 + 3: #wenn kein Endezeichen gefunden wurde
            continue  # noch nicht vollständig, mehr Daten lesen

        # Lies genau 3 weitere Bytes (CRC + Füllbyte)
        # da die CRC Prüfziffer immer 2 Bytes lang ist und das Füllbyte 1 Byte (weiterlesen)
        # und das Endezeichen 4 Bytes lang ist
        while len(buffer) < idx + 4 + 3:
            buffer += ser.read(1)
        logging.debug("🔢 komplettes Telegram: %s", buffer[:idx + 7].hex())
        sml_data = buffer[:idx + 5]         # inkl. 1a + Füllbyte (1 Byte)

        logging.debug("[%s]", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        logging.debug("📡 SML-Telegramm erkannt (Länge: %d Bytes)", len(sml_data))
        
        # prüfen ob crc passt
        # CRC-Prüfziffer ist immer 2 Bytes lang
        # und das Füllbyte ist 1 Byte lang
        # nur dann ist das Telegramm vollständig und korrekt
        if crc_check(buffer[idx + 5:idx + 7], sml_data) == True:   
            
            logging.debug("Verarbeitung SML Telegram starten!")
            # Zaehler initialisieren
            mein_zaehler = Zaehler(None, None, None, None, None)

            # OBIS Herstellerkennung und Seriennummer suchen
            # Herstellerkennung suchen
            tech_konfiguration.hersteller.start = sml_data.find(tech_konfiguration.hersteller.code) # finde die Startposition des OBIS-Codes
            if tech_konfiguration.hersteller.start == -1:
                logging.error("❌ OBIS-Code für Hersteller nicht gefunden.")
                continue  # Überspringt die Verarbeitung dieses Telegramms
            mein_zaehler.vendor = decode_manufacturer(
                wert_suchen(
                    sml_data,
                    tech_konfiguration.hersteller.start,
                    tech_konfiguration.hersteller.wert.offset,
                    tech_konfiguration.hersteller.wert.laenge
                    ).hex())

            # Seriennummer suchen 
            tech_konfiguration.sn.start = sml_data.find(tech_konfiguration.sn.code) # finde die Startposition des OBIS-Codes
            if tech_konfiguration.sn.start == -1:
                logging.error("❌ OBIS-Code für Seriennummer nicht gefunden.")
                continue

            # Seriennummer parsen
            mein_zaehler.sn = parse_device_id(
                wert_suchen(
                    sml_data,
                    tech_konfiguration.sn.start,
                    tech_konfiguration.sn.wert.offset,
                    tech_konfiguration.sn.wert.laenge
                    ).hex()) 
            
            logging.debug("Hersteller / SN : %s / %s", mein_zaehler.vendor, mein_zaehler.sn)
            
            # Bezug gesamt suchen 
            tech_konfiguration.bezug.start = sml_data.find(tech_konfiguration.bezug.code)
            if tech_konfiguration.bezug.start == -1:  
                logging.error("❌ OBIS-Code für Bezug nicht gefunden.")
                continue
            bezug = Messwert(None,None,tech_konfiguration.bezug.code) 
            
            bezug.wert = skalieren(
                int(
                    wert_suchen(
                        sml_data,
                        tech_konfiguration.bezug.start,
                        tech_konfiguration.bezug.wert.offset,
                        tech_konfiguration.bezug.wert.laenge
                        ).hex(),16), # 
                int.from_bytes(
                    wert_suchen(
                        sml_data,
                        tech_konfiguration.bezug.start,
                        tech_konfiguration.bezug.factor.offset,
                        tech_konfiguration.bezug.factor.laenge 
                    ), 
                    byteorder="big", signed=True
                )
            )

            bezug.einheit = einheit_suchen(
                wert_suchen(
                    sml_data,
                    tech_konfiguration.bezug.start,
                    tech_konfiguration.bezug.einheit.offset,
                    tech_konfiguration.bezug.einheit.laenge
                )
            )
            
            mein_zaehler.bezug = Messwert(
                None,
                None,
                tech_konfiguration.bezug.code.hex()
            )

            mein_zaehler.bezug.wert, mein_zaehler.bezug.einheit = convert_wh_to_kwh(bezug.wert, bezug.einheit)  #in kWh umrechnen    
            logging.debug("Bezug %s = %s %s", mein_zaehler.bezug.obis, mein_zaehler.bezug.wert, mein_zaehler.bezug.einheit)
                    
            # Einspeisung gesamt suchen 
            tech_konfiguration.einspeisung.start = sml_data.find(tech_konfiguration.einspeisung.code)
            if tech_konfiguration.einspeisung.start == -1:
                logging.error("❌ OBIS-Code für Einspeisung nicht gefunden.")
                continue   
            
            einspeisung = Messwert(None,None,tech_konfiguration.einspeisung.code.hex())
            
            # Einspeisung suchen und skalieren
            einspeisung.wert = skalieren(
                int(
                    wert_suchen(
                        sml_data,
                        tech_konfiguration.einspeisung.start,
                        tech_konfiguration.einspeisung.wert.offset,
                        tech_konfiguration.einspeisung.wert.laenge
                    ).hex(),16), 
                int.from_bytes(
                    wert_suchen(
                        sml_data,
                        tech_konfiguration.einspeisung.start,
                        tech_konfiguration.einspeisung.factor.offset,
                        tech_konfiguration.einspeisung.factor.laenge
                    ), byteorder="big", signed=True) 
             )
            
            einspeisung.einheit = einheit_suchen(
                wert_suchen(
                    sml_data,
                    tech_konfiguration.einspeisung.start,
                    tech_konfiguration.einspeisung.einheit.offset,
                    tech_konfiguration.einspeisung.einheit.laenge
                ))
            
            mein_zaehler.einspeisung = Messwert(None, None, einspeisung.obis)
            mein_zaehler.einspeisung.wert, mein_zaehler.einspeisung.einheit = convert_wh_to_kwh(einspeisung.wert, einspeisung.einheit)
            logging.debug("Einspeisung %s = %s %s", mein_zaehler.einspeisung.obis, mein_zaehler.einspeisung.wert, mein_zaehler.einspeisung.einheit)

            # Wirkleistung suchen
            tech_konfiguration.leistung.start = sml_data.find(tech_konfiguration.leistung.code)
            if tech_konfiguration.leistung.start == -1:
                logging.error("❌ OBIS-Code für Wirkleistung nicht gefunden.")
                continue

            wirk = Messwert(None,None,tech_konfiguration.leistung.code.hex())

            # Wirkleistung suchen und skalieren
            wirk.wert = skalieren(
                int(
                    wert_suchen(
                        sml_data,
                        tech_konfiguration.leistung.start,
                        tech_konfiguration.leistung.wert.offset,
                        tech_konfiguration.leistung.wert.laenge
                    ).hex(),16), 
                int.from_bytes(
                    wert_suchen(
                        sml_data,
                        tech_konfiguration.leistung.start,
                        tech_konfiguration.leistung.factor.offset,
                        tech_konfiguration.leistung.factor.laenge
                        ), byteorder="big", signed=True) 
            )

            # Wirkleistung Einheit suchen
            wirk.einheit = einheit_suchen(
                wert_suchen(
                    sml_data,
                    tech_konfiguration.leistung.start,
                    tech_konfiguration.leistung.einheit.offset,
                    tech_konfiguration.leistung.einheit.laenge
                    )) 
            
            mein_zaehler.leistung = Messwert(wirk.wert,wirk.einheit,wirk.obis)
            logging.debug("Wirkleistung %s = %s %s", mein_zaehler.leistung.obis, mein_zaehler.leistung.wert, mein_zaehler.leistung.einheit)
            
            current_time = time.time()
            if current_time - last_json_write >= wait_time:
                now = datetime.now(ZoneInfo("Europe/Berlin"))
                timestamp = now.isoformat()
                date_str = now.strftime("%Y-%m-%d")
    
                output_data = {
                    "leistung": mein_zaehler.leistung.wert,
                    "leistung_einheit": mein_zaehler.leistung.einheit, 
                    "bezug": mein_zaehler.bezug.wert,
                    "bezug_einheit": mein_zaehler.bezug.einheit,
                    "einspeisung": mein_zaehler.einspeisung.wert, 
                    "einspeisung_einheit": mein_zaehler.einspeisung.einheit,
                    "seriennummer": mein_zaehler.sn,
                    "timestamp": timestamp,
                    "zaehlername": mein_zaehler.vendor
                }
                
                # Prüfen, ob die Umgebungsvariable OUTPUT gesetzt ist
                # und ob sie "sqlite" enthält
                if "sqlite" in output_modes:
                    logging.debug("💾 Daten in SQLite speichern")           
                    # SQLite-Daten speichern
                    try:
                        save_to_sqlite(
                            mein_zaehler.sn,
                            mein_zaehler.vendor,
                            mein_zaehler.bezug.wert,
                            mein_zaehler.einspeisung.wert,
                            mein_zaehler.leistung.wert
                        )
                        logging.debug("💾 Daten in SQLite gespeichert")   
                    except Exception as e:
                        logging.error("❌ Fehler beim Speichern in SQLite: %s", e)
                    
                # Prüfen, ob die Umgebungsvariable OUTPUT gesetzt ist
                # und ob sie "json" enthält
                if "json" in output_modes:
                    logging.debug("💾 JSON-Daten speichern")
                    # JSON-Daten speichern  
                    try:
                        # Aktuelle Datei speichern
                        with open(OUTPUT_PATH / "strom.json", "w") as f:
                            json.dump(output_data, f, indent=2)
                        logging.debug("💾 JSON-Daten gespeichert (%s)", timestamp)
                        
                    # Historie laden oder leere Liste
                        history_file = HISTORY_PATH / f"{date_str}.json"
                        if history_file.exists():
                            with open(history_file, "r") as f:
                                history_data = json.load(f)                
                        else:
                            history_data = []
                            
                        history_data.append(output_data)  
                        
                        # Historie zurückschreiben
                        with open(history_file, "w") as f:
                            json.dump(history_data, f, indent=2)
    
                    except Exception as e:
                        logging.error("❌ Fehler beim Schreiben der JSON-Dateien: %s", e)
                                 
                last_json_write = current_time             
            else:
                logging.debug("⏳ Warte auf nächsten Schreibzeitpunkt...")
                 
        else: 
            crc_check_sml = False
            logging.debug("Kein gültiges Telegram zum verarbeiten")    
        
        # Buffer bereinigen
        if idx + 7 <= len(buffer):
            buffer = buffer[idx + 7:]
        else:
            buffer = b""

        logging.debug("🔄 Buffer zurückgesetzt")       
