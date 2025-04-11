#!/usr/bin/env python3
import serial
import time
import logging
import binascii
import crcmod
import argparse
from datetime import datetime
import os

import argparse
import os
import logging

#offsets
idx_bezug_offset = 19

#obis kennungen
bezug_kennung = b"\x07\x01\x00\x01\x08\x00\xff"

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
            idx_vendor = 0
            vendor_kennung = b"\x07\x01\x00\x60\x32\x01\x01"
            idx_vendor = sml_data.find(vendor_kennung)
            
            logging.debug("Hersteller %s an Stelle %s", vendor_kennung.hex(), idx_vendor)
            
            # Seriennummer suchen 01 00 60 01 00 FF
            idx_sn = 0
            sn_kennung = b"\x07\x01\x00\x60\x01\x00\xff"
            idx_sn = sml_data.find(sn_kennung)
            
            logging.debug("SN %s an Stelle %s", sn_kennung.hex(), idx_sn)
            
            # Bezug gesamt suchen
            logging.debug(" ")
            logging.debug("*** Bezug ****")
            idx_bezug = 0
            idx_bezug = sml_data.find(bezug_kennung)           
            logging.debug("Bezug %s an Stelle %s", bezug_kennung.hex(), idx_bezug)
            bezug_unit = sml_data[idx_bezug + idx_bezug_offset:idx_bezug + idx_bezug_offset + 2] 
            logging.debug("Bezugeinheit %s", bezug_unit.hex())
            
            # Einspeisung gesamt suchen 07 01 00 02 08 00 ff
            idx_einspeisung = 0
            einspeisung_kennung = b"\x07\x01\x00\x02\x08\x00\xff"
            idx_einspeisung = sml_data.find(einspeisung_kennung)
            
            logging.debug("Einspeisung %s an Stelle %s",einspeisung_kennung.hex(), idx_einspeisung)

            # Wirkleistung gesamt suchen 07 01 00 10 07 00 ff
            idx_wirk = 0
            wirk_kennung = b"\x07\x01\x00\x10\x07\x00\xff"
            idx_wirk = sml_data.find(wirk_kennung)
            
            logging.debug("Wirkleistung %s an Stelle %s", wirk_kennung.hex(), idx_wirk)   
            
                     
        else: 
            crc_check_sml = False
            
        logging.debug("✅ CRC: erwartet %04X, berechnet %04X → %s",
                     crc_expected,
                     crc_calculated,
                     "✅ gültig" if crc_check_sml == True else "❌ ungültig")

        # Buffer bereinigen
        buffer = buffer[idx + 7:]