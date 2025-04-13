#!/usr/bin/env python3
import serial
import time
import logging
import binascii
import crcmod
import argparse
import os
import json
import logging
from pathlib import Path
from zoneinfo import ZoneInfo
from datetime import datetime

# Speicherpfade
OUTPUT_PATH = Path("/app/data")
HISTORY_PATH = OUTPUT_PATH / "history"
HISTORY_PATH.mkdir(parents=True, exist_ok=True)

# Zeitkontrolle für JSON-Speicherung
last_json_write = 0
wait_time=60

class Messwert:
    def __init__(self, wert, einheit, obis):
        self.wert = wert
        self.einheit = einheit
        self.obis = obis
        
class Zaehler:
    def __init__(self, vendor, sn, leistung, bezug, einspeisung):
        self.vendor = vendor
        self.sn = sn
        self.leistung = leistung
        self.bezug = bezug
        self.einspeisung = einspeisung

class OBIS_Object:
    def __init__(self, code, start):
        self.code = code
        self.start = start

def decode_manufacturer(hex_string):
    """
    Wandelt einen Hex-String wie '04454D48' in einen lesbaren Hersteller-Code (z. B. 'EMH') um.
    Ignoriert das erste Byte (Längen-/Typkennzeichen).
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
    Erwartet mindestens 10 Bytes nach dem TL-Feld (z. B. '0b0a01454d480000b8ef79').
    """
    try:
        # Nimmt nur den tatsächlichen Inhalt ohne das TL-Feld (z. B. nach '0b0a01')
        payload = hex_string[6:]  # ab Index 6 → 454d480000b8ef79
        ascii_part = payload[:6]  # 454d48
        serial_part = payload[6:] # 0000b8ef79

        hersteller = bytes.fromhex(ascii_part).decode("ascii")
        seriennummer = serial_part.upper()

        return f"{hersteller}-{seriennummer}"
    except Exception as e:
        return f"Fehler beim Parsen: {e}"
        
def crc_check(crc_raw,sml_telegram):
    crc_func = crcmod.mkCrcFun(0x11021, initCrc=0, xorOut=0xFFFF, rev=True)
    if crc_func(sml_telegram) == int.from_bytes(crc_raw, "little"):
        logging.debug("CRC Prüfung erfolgreich")
        return True
    else:
        logging.debug("CRC Prüfung fehlgeschlagen")
        return False
        
def wert_suchen(sml_telegram,idx_position,idx_offset,idx_len):
    return sml_telegram[idx_position + idx_offset:idx_position + idx_offset + idx_len]

def skalieren(wert, skala):
    """
    Skaliert den Wert mit dem angegebenen Skalenfaktor.
    """
    if skala == 0:
        return wert
    else:
        return wert * (10 ** skala)

def einheit_suchen(einheit_raw):
    if einheit_raw == b"\x62\x1e": # schauen ob Wh
        return ("Wh")
    elif einheit_raw == b"\x62\x1b": # schauen ob W
        return ("W")
    else:
        return ("unbekannte Einheit")

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

#obis kennungen
bezug_kennung = b"\x07\x01\x00\x01\x08\x00\xff"
einspeisung_kennung = b"\x07\x01\x00\x02\x08\x00\xff"
wirk_kennung = b"\x07\x01\x00\x10\x07\x00\xff"

#sml kennzeichen
sml_ende = b"\x1b\x1b\x1b\x1a"

parser = argparse.ArgumentParser()
parser.add_argument("--debug", action="store_true", help="Aktiviere Debug-Ausgabe")
args = parser.parse_args()

debug_env = os.getenv("DEBUG", "0").lower() in ("1", "true", "yes")
debug_mode = args.debug or debug_env

logging.basicConfig(
    level=logging.DEBUG if debug_mode else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

logging.debug("args.debug: %s", args.debug)
logging.debug("os.getenv('DEBUG'): %s", os.getenv('DEBUG'))
logging.debug("debug_env: %s", debug_env)
logging.debug("debug_mode: %s", debug_mode)

PORT = "/dev/ttyUSB0"
BAUDRATE = 9600

logging.debug("🔌 Verbinde mit %s @ %d Baud", PORT, BAUDRATE)

ser = serial.Serial(PORT, BAUDRATE, timeout=1)

buffer = b""
while True:
    raw = ser.read(1)
    if not raw:
        continue
    buffer += raw

    # Suche nach Endezeichen
    if sml_ende in buffer:
        idx = buffer.find(sml_ende)
        if idx == -1 or len(buffer) < idx + 4 + 3:
            continue  # noch nicht vollständig

        # Lies genau 3 weitere Bytes (CRC + Füllbyte)
        while len(buffer) < idx + 4 + 3:
            buffer += ser.read(1)
        # sml_komplett = buffer[:idx + 7] 
        logging.debug("🔢 komplettes Telegram: %s", buffer[:idx + 7].hex())
        sml_data = buffer[:idx + 5]         # inkl. 1a + Füllbyte (1 Byte)

        logging.debug("[%s]", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        logging.debug("📡 SML-Telegramm erkannt (Länge: %d Bytes)", len(sml_data))
        
        #prüfen ob crc passt
        if crc_check(buffer[idx + 5:idx + 7],sml_data) == True:   
            
            logging.debug("Verarbeitung SML Telegram starten!")
            # Zaehler initialisieren
            mein_zaehler = Zaehler(None,None,None,None,None)

            # Herstellerkennung und Seriennummer suchen
            # 07 01 00 60 32 01 01
            # 07 01 00 60 01 00 FF
            vendor_obis = OBIS_Object(b"\x07\x01\x00\x60\x32\x01\x01",0)
            vendor_obis.start = sml_data.find(vendor_obis.code)
            # Hersteller offset 11, laenge 4
            mein_zaehler.vendor = decode_manufacturer(wert_suchen(sml_data,vendor_obis.start,11,4).hex())

            sn_obis = OBIS_Object(b"\x07\x01\x00\x60\x01\x00\xff",0)
            sn_obis.start = sml_data.find(sn_obis.code)
            # Seriennummer offset 11, laenge 11
            mein_zaehler.sn = parse_device_id(wert_suchen(sml_data,sn_obis.start,11,11).hex())
            
            logging.debug("Hersteller / SN : %s / %s", mein_zaehler.vendor, mein_zaehler.sn)
            
            # bis hierhin alles ok

            # Bezug gesamt suchen 07 01 00 01 08 00 ff
            bezug_obis = OBIS_Object(b"\x07\x01\x00\x01\x08\x00\xff",0)
            bezug_obis.start = sml_data.find(bezug_obis.code)
            bezug = Messwert(None,None,bezug_obis.code) 
            
            bezug.wert = skalieren(
                int(wert_suchen(sml_data,bezug_obis.start,24,8).hex(),16), # Wert Offset 24, laenge 8
                int.from_bytes(wert_suchen(sml_data,bezug_obis.start,22,1), byteorder="big", signed=True) # Scale Offset 22, laenge 1
             ) 

            bezug.einheit = einheit_suchen(wert_suchen(sml_data,bezug_obis.start,19,2)) # Einheit Offset 19, laenge 2
            mein_zaehler.bezug = Messwert(None,None,bezug_obis.code)
            mein_zaehler.bezug.wert, mein_zaehler.bezug.einheit = convert_wh_to_kwh(bezug.wert, bezug.einheit)  #in kWh umrechnen    
            logging.debug("Bezug %s = %s %s", bezug_obis.code.hex(), mein_zaehler.bezug.wert, mein_zaehler.bezug.einheit)
                    
            # Einspeisung gesamt suchen 07 01 00 02 08 00 ff
            einspeisung_obis = OBIS_Object(b"\x07\x01\x00\x02\x08\x00\xff",0)
            einspeisung_obis.start = sml_data.find(einspeisung_obis.code)
            einspeisung = Messwert(None,None,einspeisung_obis.code)
            
            einspeisung.wert = skalieren(
                int(wert_suchen(sml_data,einspeisung_obis.start,21,8).hex(),16), # Wert Offset 24, laenge 8
                int.from_bytes(wert_suchen(sml_data,einspeisung_obis.start,19,1), byteorder="big", signed=True) # Scale Offset 22, laenge 1
             )
            einspeisung.einheit = einheit_suchen(wert_suchen(sml_data,einspeisung_obis.start,16,2)) # Einheit Offset 19, laenge 2
            mein_zaehler.einspeisung = Messwert(None,None,einspeisung_obis.code)
            mein_zaehler.einspeisung.wert, mein_zaehler.einspeisung.einheit = convert_wh_to_kwh(einspeisung.wert, einspeisung.einheit)
            logging.debug("Einspeisung %s = %s %s", einspeisung_obis.code.hex(), mein_zaehler.einspeisung.wert, mein_zaehler.einspeisung.einheit)

            # Wirkleistung gesamt suchen 07 01 00 10 07 00 ff
            wirk_obis = OBIS_Object(b"\x07\x01\x00\x10\x07\x00\xff",0) 
            wirk_obis.start = sml_data.find(wirk_obis.code)
            wirk = Messwert(None,None,wirk_obis.code)
            wirk.wert = skalieren(
                int(wert_suchen(sml_data,wirk_obis.start,21,4).hex(),16), # Wert Offset 21, laenge 4
                int.from_bytes(wert_suchen(sml_data,wirk_obis.start,19,1), byteorder="big", signed=True) # Scale Offset 22, laenge 1
             )
            wirk.einheit = einheit_suchen(wert_suchen(sml_data,wirk_obis.start,16,2)) # Einheit Offset 16, laenge 2
            mein_zaehler.leistung = Messwert(wirk.wert,wirk.einheit,wirk_obis.code)
            logging.debug("Wirkleistung %s = %s %s", wirk_obis.code.hex(), mein_zaehler.leistung.wert, mein_zaehler.leistung.einheit)
            
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

                    last_json_write = current_time
                    
                except Exception as e:
                    logging.error("❌ Fehler beim Schreiben der JSON-Dateien: %s", e)
                    
        else: 
            crc_check_sml = False
            logging.debug("Kein gültiges Telegram zum verarbeiten")    
        
        # Buffer bereinigen
        buffer = buffer[idx + 7:]
        