#!/usr/bin/env python3
import serial
import time
import logging
import binascii
import crcmod
import argparse
from datetime import datetime
import os
import json
import logging
from pathlib import Path

# Speicherpfade
OUTPUT_PATH = Path("/app/data")
HISTORY_PATH = OUTPUT_PATH / "history"
HISTORY_PATH.mkdir(parents=True, exist_ok=True)

# Zeitkontrolle für JSON-Speicherung
last_json_write = 0
wait_time=60

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
print(f"args.debug: {args.debug}")
print(f"os.getenv('DEBUG'): {os.getenv('DEBUG')}")
print(f"debug_env: {debug_env}")
print(f"debug_mode: {debug_mode}")

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
        sml_komplett = buffer[:idx + 7] 
        sml_data = buffer[:idx + 5]         # inkl. 1a + Füllbyte (1 Byte)
        crc_raw = buffer[idx + 5:idx + 7]   # 2 CRC-Bytes
        crc_expected = int.from_bytes(crc_raw, "little")

        crc_func = crcmod.mkCrcFun(0x11021, initCrc=0, xorOut=0xFFFF, rev=True)

      #  crc_calculated = binascii.crc_hqx(sml_data, 0xffff)
        crc_calculated = crc_func(sml_data)
        logging.debug("")
        logging.debug("[%s]", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        logging.debug("📡 SML-Telegramm erkannt (Länge: %d Bytes)", len(sml_data))
        logging.debug("🔢 HEX: %s", sml_komplett.hex())
        logging.debug("🔢 HEX: %s", sml_data.hex())
        logging.debug("🔢 CRC-Rohbytes: %s", crc_raw.hex())
        crc_check_sml = False
        
        if crc_expected == crc_calculated:
            crc_check_sml = True    
            logging.debug("Verarbeitung SML Telegram starten!")
            
            # HErsteller suchen 07010060320101
            logging.debug(" ")
            logging.debug("*** Bezug ****")
            idx_vendor = 0
            vendor_kennung = b"\x07\x01\x00\x60\x32\x01\x01"
            idx_vendor = sml_data.find(vendor_kennung)
            logging.debug("Hersteller %s an Stelle %s", vendor_kennung.hex(), idx_vendor)
            idx_vendor_offset = 11
            vendor_str = ""
            if idx_vendor > 1:
                vendor_str = decode_manufacturer((sml_data[idx_vendor + idx_vendor_offset:idx_vendor + idx_vendor_offset + 4]).hex())
            else:
                vendor_str = "unbekannter Hersteller"
            logging.debug("Vendor %s", vendor_str)
            
          
            
            # Seriennummer suchen 01 00 60 01 00 FF
            logging.debug(" ")
            logging.debug("*** Gerätekennung ****")
            idx_sn = 0
            sn_kennung = b"\x07\x01\x00\x60\x01\x00\xff"
            idx_sn = sml_data.find(sn_kennung)
            logging.debug("SN %s an Stelle %s", sn_kennung.hex(), idx_sn)
            idx_sn_offset = 11
            
            if idx_sn > 1:
                sn_string = parse_device_id((sml_data[idx_sn + idx_sn_offset:idx_sn + idx_sn_offset + 11]).hex())
            else:
                sn_string = "unbekannte Gerätekennung"
            
            logging.debug("SN %s", sn_string)
              
            # Bezug gesamt suchen
            logging.debug(" ")
            logging.debug("*** Bezug ****")
            idx_bezug = 0
            idx_bezug = sml_data.find(bezug_kennung)           
            logging.debug("Bezug %s an Stelle %s", bezug_kennung.hex(), idx_bezug)
        
            if idx_bezug > 0:
            
                #Scale Faktor raussuchen
                idx_bezug_scale_offset = 22 # offset für die Skala
                bezug_scale = sml_data[idx_bezug + idx_bezug_scale_offset:idx_bezug + idx_bezug_scale_offset + 1]     # 1 Byte für den Scale raussuchen
                bezug_scale_int = pow(10, int.from_bytes(bezug_scale, byteorder="big", signed=True)) # potenz den scale errechnen
                logging.debug("Faktor %s = %s", bezug_scale.hex(), bezug_scale_int)
                
                # Bezug errechnen
                idx_bezug_value_offset = 24 # offset für den wer
                bezug_value = sml_data[idx_bezug + idx_bezug_value_offset:idx_bezug + idx_bezug_value_offset + 8]     # 9 Byte für den Wert
                bezug_value_int = int(bezug_value.hex(), 16) * bezug_scale_int # potenz den scale errechnen
                logging.debug("Bezugswert %s = %s", bezug_value.hex(), bezug_value_int)
                
                #Einheit raussuchen
                idx_bezug_unit_offset = 19 # offset für die Einheit
                bezug_unit = sml_data[idx_bezug + idx_bezug_unit_offset:idx_bezug + idx_bezug_unit_offset + 2]   # 2 Byte raussuchen
                if bezug_unit == b"\x62\x1e": # schauen ob Wh
                    logging.debug("Bezugeinheit %s = %s", bezug_unit.hex(), "Wh")
                    bezug_unit_string = "kWh" # ich will aber kWh
                    bezug_kvalue_int = bezug_value_int / 1000 # und den Wert rechnen wir um
                else: # ansonten unbekannt
                    bezug_unit_string = "unbekannte Einheit"
                    logging.debug("Bezugeinheit %s = %s", bezug_unit.hex(), bezug_unit_string)
                    bezug_kvalue_int = bezug_value_int 
                
                logging.debug("Der Bezug beträgt %s %s",bezug_kvalue_int, bezug_unit_string)
             
            else:
                bezug_unit_string = "kein Bezug"
                bezug_kvalue_int = 0
                
            # Einspeisung gesamt suchen 07 01 00 02 08 00 ff
            logging.debug(" ")
            logging.debug("*** Einspeisung ****")
            idx_einspeisung = 0
            idx_einspeisung = sml_data.find(einspeisung_kennung)
            
            logging.debug("Einspeisung %s an Stelle %s",einspeisung_kennung.hex(), idx_einspeisung)

            if idx_einspeisung > 0:
                
                #Scale Faktor raussuchen
                idx_einspeisung_scale_offset = 19 # offset für die Skala
                einspeisung_scale = sml_data[idx_einspeisung + idx_einspeisung_scale_offset:idx_einspeisung + idx_einspeisung_scale_offset + 1]     # 1 Byte für den Scale raussuchen
                einspeisung_scale_int = pow(10, int.from_bytes(einspeisung_scale, byteorder="big", signed=True)) # potenz den scale errechnen
                logging.debug("Faktor %s = %s", einspeisung_scale.hex(), einspeisung_scale_int)
                
                # Bezug errechnen
                idx_einspeisung_value_offset = 21 # offset für den wer
                einspeisung_value = sml_data[idx_einspeisung + idx_einspeisung_value_offset:idx_einspeisung + idx_einspeisung_value_offset + 8]     # 9 Byte für den Wert
                einspeisung_value_int = int(einspeisung_value.hex(), 16) * einspeisung_scale_int # potenz den scale errechnen
                logging.debug("Einspeisewert %s = %s", einspeisung_value.hex(), einspeisung_value_int)
                
                #Einheit raussuchen
                idx_einspeisung_unit_offset = 16 # offset für die Einheit
                einspeisung_unit = sml_data[idx_einspeisung + idx_einspeisung_unit_offset:idx_einspeisung + idx_einspeisung_unit_offset + 2]   # 2 Byte raussuchen
                if einspeisung_unit == b"\x62\x1e": # schauen ob Wh
                    logging.debug("Einspeiseeinheit %s = %s", einspeisung_unit.hex(), "Wh")
                    einspeisung_unit_string = "kWh" # ich will aber kWh
                    einspeisung_kvalue_int = einspeisung_value_int / 1000 # und den Wert rechnen wir um
                else: # ansonten unbekannt
                    einspeisung_unit_string = "unbekannte Einheit"
                    logging.debug("Einspeiseinheit %s = %s", einspeisung_unit.hex(), einspeisung_unit_string)
                    einspeisung_kvalue_int = einspeisung_value_int 
                
                logging.debug("Die Einspeisung beträgt %s %s",einspeisung_kvalue_int, einspeisung_unit_string)
            else:
                einspeisung_unit_string = "keine Einspeisung"
                einspeisung_kvalue_int = 0

            # Wirkleistung gesamt suchen 07 01 00 10 07 00 ff
            logging.debug(" ")
            logging.debug("*** Wirkleistung aktuell ****")
            idx_wirk = 0
            idx_wirk = sml_data.find(wirk_kennung)   
            logging.debug("Wirkleistung %s an Stelle %s", wirk_kennung.hex(), idx_wirk)  

            if idx_wirk > 0:
            
                #Scale Faktor raussuchen
                idx_wirk_scale_offset = 19 # offset für die Skala
                wirk_scale = sml_data[idx_wirk + idx_wirk_scale_offset:idx_wirk + idx_wirk_scale_offset + 1]     # 1 Byte für den Scale raussuchen
                wirk_scale_int = pow(10, int.from_bytes(wirk_scale, byteorder="big", signed=True)) # potenz den scale errechnen
                logging.debug("Faktor %s = %s", wirk_scale.hex(), wirk_scale_int)
                
                # Wirk errechnen
                idx_wirk_value_offset = 21 # offset für den wert
                wirk_value = sml_data[idx_wirk + idx_wirk_value_offset:idx_wirk + idx_wirk_value_offset + 4]     # 9 Byte für den Wert
                wirk_value_int = int(wirk_value.hex(), 16) * wirk_scale_int # potenz den scale errechnen
                logging.debug("Wirkwert %s = %s", wirk_value.hex(), wirk_value_int)
                
                #Einheit raussuchen
                idx_wirk_unit_offset = 16 # offset für die Einheit
                wirk_unit = sml_data[idx_wirk + idx_wirk_unit_offset:idx_wirk + idx_wirk_unit_offset + 2]   # 2 Byte raussuchen
                if wirk_unit == b"\x62\x1b": # schauen ob W
                    wirk_unit_string = "W" # ich will aber kWh
                else: # ansonten unbekannt
                    wirk_unit_string = "unbekannte Einheit"
                logging.debug("Wirkeinheit %s = %s", wirk_unit.hex(), wirk_unit_string )
                
                logging.debug("Die aktuelle Wirkleistung beträgt %s %s",wirk_value_int, wirk_unit_string)
                
            current_time = time.time()
            if current_time - last_json_write >= wait_time:
                now = datetime.now()
                timestamp = now.isoformat()
                date_str = now.strftime("%Y-%m-%d")
    
                output_data = {
                    "leistung": wirk_value_int, 
                    "bezug": bezug_kvalue_int,
                    "einspeisung": einspeisung_kvalue_int,
                    "seriennummer": sn_string,
                    "timestamp": datetime.now().isoformat(),
                    "zaehlername": vendor_str
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
        logging.debug(" ")    
        logging.debug("✅ CRC: erwartet %04X, berechnet %04X → %s",
                     crc_expected,
                     crc_calculated,
                     "✅ gültig" if crc_check_sml == True else "❌ ungültig")

        # Buffer bereinigen
        buffer = buffer[idx + 7:]
        