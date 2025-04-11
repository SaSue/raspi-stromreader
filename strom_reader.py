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

    # Prüfe, ob wir das Ende eines SML-Telegramms sehen
    if buffer.endswith(b"\x1b\x1b\x1b\x1a") and len(buffer) > 8:
        try:
            start_idx = buffer.find(b"\x1b\x1b\x1b\x1b")
            if start_idx == -1:
                buffer = b""
                continue

            # Telegramm extrahieren (inkl. 1a)
            telegram = buffer[start_idx:]
            end_idx = telegram.find(b"\x1b\x1b\x1b\x1a")
            if end_idx == -1:
                continue
            crc_raw = telegram[end_idx+8:end_idx+12]
            end_idx += 4  # bis einschließlich \x1a
            sml_data = telegram[:end_idx]
           
            crc_expected = int.from_bytes(crc_raw, byteorder="little")

            crc_calculated = binascii.crc_hqx(sml_data, 0xffff)

            logging.info("")
            logging.info("[%s]", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            logging.info("📡 SML-Telegramm erkannt (Länge: %d Bytes)", len(sml_data))
            logging.info("🔢 HEX: %s", sml_data.hex())
            logging.info("✅ CRC: erwartet %04X, berechnet %04X → %s",
                         crc_expected,
                         crc_calculated,
                         "✅ gültig" if crc_expected == crc_calculated else "❌ ungültig")
        except Exception as e:
            logging.error("❌ Fehler beim Verarbeiten: %s", e)
        finally:
            buffer = b""
