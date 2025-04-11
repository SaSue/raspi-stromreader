#!/usr/bin/env python3
import serial
import time
import logging
import binascii
import crcmod
from datetime import datetime

PORT = "/dev/ttyUSB0"
BAUDRATE = 9600

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

logging.info("🔌 Verbinde mit %s @ %d Baud", PORT, BAUDRATE)

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

        crc_func = crcmod.mkCrcFun(0x11021, initCrc=0xFFFF, rev=False, xorOut=0x0000)

      #  crc_calculated = binascii.crc_hqx(sml_data, 0xffff)
        crc_calculated = crc_func(sml_data)
        logging.info("")
        logging.info("[%s]", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        logging.info("📡 SML-Telegramm erkannt (Länge: %d Bytes)", len(sml_data))
        logging.info("🔢 HEX: %s", sml_komplett.hex())
        logging.info("🔢 HEX: %s", sml_data.hex())
        logging.info("🔢 CRC-Rohbytes: %s", crc_raw.hex())
        logging.info("✅ CRC: erwartet %04X, berechnet %04X → %s",
                     crc_expected,
                     crc_calculated,
                     "✅ gültig" if crc_expected == crc_calculated else "❌ ungültig")

        # Buffer bereinigen
        buffer = buffer[idx + 7:]