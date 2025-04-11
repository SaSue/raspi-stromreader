#!/usr/bin/env python3
import serial
import time
import logging
import binascii
from datetime import datetime

# Konfiguration
PORT = "/dev/ttyUSB0"
BAUDRATE = 9600

# Logging konfigurieren
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

    # Suche nach Start- und Endsequenz
    start_marker = b"\x1b\x1b\x1b\x1b"
    end_marker = b"\x1b\x1b\x1b\x1a"

    start_idx = buffer.find(start_marker)
    end_idx = buffer.find(end_marker)

    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
        try:
            # Position nach end_marker
            crc_start = end_idx + len(end_marker)
            if crc_start + 2 > len(buffer):
                continue  # warte auf CRC-Bytes

            telegram = buffer[start_idx:crc_start + 2]
            sml_data = telegram[:crc_start]
            crc_raw = telegram[crc_start:crc_start + 2]

            crc_expected = int.from_bytes(crc_raw, byteorder="little")
            crc_calculated = binascii.crc_hqx(sml_data, 0xffff)

            logging.info("")
            logging.info("[%s]", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            logging.info("📡 SML-Telegramm erkannt (Länge: %d Bytes)", len(telegram))
            logging.info("🔢 CRC RAW: %s", crc_raw.hex())
            logging.info("🔢 HEX: %s", telegram.hex())
            logging.info("✅ CRC: erwartet %04X, berechnet %04X → %s",
                         crc_expected,
                         crc_calculated,
                         "✅ gültig" if crc_expected == crc_calculated else "❌ ungültig")
        except Exception as e:
            logging.error("❌ Fehler beim Verarbeiten: %s", e)
        finally:
            buffer = b""