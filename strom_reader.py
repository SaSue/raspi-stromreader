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
    if b"\x1b\x1b\x1b\x1a" in buffer:
        idx = buffer.find(b"\x1b\x1b\x1b\x1a")
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
        else: 
            crc_check_sml = False
            
        logging.debug("✅ CRC: erwartet %04X, berechnet %04X → %s",
                     crc_expected,
                     crc_calculated,
                     "✅ gültig" if crc_check_sml == True else "❌ ungültig")

        # Buffer bereinigen
        buffer = buffer[idx + 7:]