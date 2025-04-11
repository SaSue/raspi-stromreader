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

    # Prüfe auf Endezeichen
    if buffer.endswith(b"\x1b\x1b\x1b\x1a") and len(buffer) > 100:
        try:
            start_idx = buffer.find(b"\x1b\x1b\x1b\x1b")
            end_marker = b"\x1b\x1b\x1b\x1a"

            if start_idx == -1:
                buffer = b""
                continue

            telegram = buffer[start_idx:]
            end_idx = telegram.find(end_marker)

            if end_idx == -1 or len(telegram) < end_idx + 6:
                continue

            # SML ohne CRC (bis einschließlich 1a)
            sml_data = telegram[:end_idx + len(end_marker)]

            # CRC liegt direkt NACH der 1a, 2 Bytes
            crc_raw = telegram[end_idx + len(end_marker): end_idx + len(end_marker) + 2]
            crc_expected = int.from_bytes(crc_raw, byteorder="little")
            crc_calculated = binascii.crc_hqx(sml_data, 0xFFFF)

            logging.info("")
            logging.info("[%s]", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            logging.info("📡 SML-Telegramm erkannt (Länge: %d Bytes)", len(sml_data))
            logging.info("🔢 CRC-Rohbytes: %s", crc_raw.hex())
            logging.info("🔢 HEX: %s", sml_data.hex())
            logging.info("✅ CRC: erwartet %04X, berechnet %04X → %s",
                         crc_expected,
                         crc_calculated,
                         "✅ gültig" if crc_expected == crc_calculated else "❌ ungültig")
        except Exception as e:
            logging.error("❌ Fehler beim Verarbeiten: %s", e)
        finally:
            buffer = b""