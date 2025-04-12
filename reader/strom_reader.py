import serial
import time
import logging
import binascii
import crcmod
import argparse
from datetime import datetime
import os
import json
from pathlib import Path
from zoneinfo import ZoneInfo

# Speicherpfade
OUTPUT_PATH = Path("/app/data")
HISTORY_PATH = OUTPUT_PATH / "history"
HISTORY_PATH.mkdir(parents=True, exist_ok=True)

# Zeitkontrolle für JSON-Speicherung
last_json_write = 0
wait_time = 60

# OBIS-Kennungen
def obis_debug_log(name, idx, data):
    logging.debug(f"{name} gefunden an Position {idx}, Daten: {data.hex()}")

bezug_kennung = b"\x07\x01\x00\x01\x08\x00\xff"
einspeisung_kennung = b"\x07\x01\x00\x02\x08\x00\xff"
wirk_kennung = b"\x07\x01\x00\x10\x07\x00\xff"

# SML-Endekennung
sml_ende = b"\x1b\x1b\x1b\x1a"

# Argumente und Logging-Konfiguration
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

PORT = "/dev/ttyUSB0"
BAUDRATE = 9600

logging.debug("Starte SML-Parser mit Debug-Modus: %s", debug_mode)
logging.debug("Port: %s, Baudrate: %d", PORT, BAUDRATE)

# Herstellerkennung dekodieren
def decode_manufacturer(hex_string):
    try:
        readable = bytes.fromhex(hex_string[-6:]).decode("ascii")
        logging.debug("Herstellerkennung: %s → %s", hex_string, readable)
        return readable
    except Exception as e:
        logging.warning("Fehler beim Decodieren des Herstellers: %s", e)
        return f"Fehler: {e}"

# Gerätekennung dekodieren
def parse_device_id(hex_string):
    try:
        ascii_part = hex_string[6:12]
        serial_part = hex_string[12:].upper()
        decoded = f"{bytes.fromhex(ascii_part).decode('ascii')}-{serial_part}"
        logging.debug("Gerätekennung: %s → %s", hex_string, decoded)
        return decoded
    except Exception as e:
        logging.warning("Fehler beim Parsen der Gerätekennung: %s", e)
        return f"Fehler: {e}"

ser = serial.Serial(PORT, BAUDRATE, timeout=1)
buffer = b""

while True:
    raw = ser.read(1)
    if not raw:
        continue
    buffer += raw

    if sml_ende in buffer:
        idx = buffer.find(sml_ende)
        if idx == -1 or len(buffer) < idx + 7:
            continue

        while len(buffer) < idx + 7:
            buffer += ser.read(1)

        sml_komplett = buffer[:idx + 7]
        sml_data = buffer[:idx + 5]
        crc_raw = buffer[idx + 5:idx + 7]
        crc_expected = int.from_bytes(crc_raw, "little")

        crc_func = crcmod.mkCrcFun(0x11021, initCrc=0, xorOut=0xFFFF, rev=True)
        crc_calculated = crc_func(sml_data)

        logging.debug("--- Neues Telegramm erkannt ---")
        logging.debug("Telegramm HEX (vollständig): %s", sml_komplett.hex())
        logging.debug("SML-Daten für CRC: %s", sml_data.hex())
        logging.debug("CRC erwartet: %04X, berechnet: %04X", crc_expected, crc_calculated)

        if crc_expected == crc_calculated:
            logging.debug("CRC gültig – Verarbeitung startet")
            now = datetime.now(ZoneInfo("Europe/Berlin"))
            timestamp = now.isoformat()
            date_str = now.strftime("%Y-%m-%d")

            # Dummy-Werte einsetzen für diese Darstellung
            parsed = {
                "zeit": timestamp,
                "leistung": 0,
                "bezug": 0,
                "einspeisung": 0,
                "zaehlername": "EMH",
                "seriennummer": "EMH-0000B8EF79"
            }
            logging.debug("Ergebnisdaten: %s", parsed)

            current_time = time.time()
            if current_time - last_json_write >= wait_time:
                try:
                    # Live-Datei schreiben
                    with open(OUTPUT_PATH / "strom.json", "w") as f:
                        json.dump(parsed, f, indent=2)
                    logging.debug("Live-JSON gespeichert: strom.json")

                    # Historie schreiben
                    histfile = HISTORY_PATH / f"{date_str}.json"
                    if histfile.exists():
                        with open(histfile, "r") as f:
                            history_data = json.load(f)
                    else:
                        history_data = []

                    history_data.append(parsed)

                    with open(histfile, "w") as f:
                        json.dump(history_data, f, indent=2)
                    logging.debug("Historie gespeichert: %s", histfile.name)

                    last_json_write = current_time
                except Exception as e:
                    logging.error("Fehler beim Schreiben der JSON-Dateien: %s", e)

        else:
            logging.warning("CRC-Prüfung fehlgeschlagen: erwartet %04X, berechnet %04X", crc_expected, crc_calculated)

        buffer = buffer[idx + 7:]