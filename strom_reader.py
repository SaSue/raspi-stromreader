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
    if raw:
        buffer += raw

        # Suche nach Start und Ende
        start_idx = buffer.find(b"\x1b\x1b\x1b\x1b")
        end_idx = buffer.find(b"\x1b\x1b\x1b\x1a", start_idx)

        # Telegramm gefunden?
        if start_idx != -1 and end_idx != -1 and len(buffer) >= end_idx + 6:
            try:
                # SML-Daten + CRC-Bytes
                sml_data = buffer[start_idx:end_idx + 5]
                crc_raw = buffer[end_idx + 5:end_idx + 7]
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

            # Buffer nach Telegramm bereinigen
            buffer = buffer[end_idx + 6:]

    # Optional: Puffergröße begrenzen (gegen Buffer Overflow bei fehlerhaftem Stream)
    if len(buffer) > 2000:
        buffer = buffer[-1000:]