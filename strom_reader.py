#!/usr/bin/env python3
import serial
import logging
import binascii
from datetime import datetime

# Konfiguration
PORT = "/dev/ttyUSB0"
BAUDRATE = 9600

# Logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

logging.info("🔌 Verbinde mit %s @ %d Baud", PORT, BAUDRATE)

ser = serial.Serial(PORT, BAUDRATE, timeout=1)
buffer = b""

while True:
    byte = ser.read(1)
    if not byte:
        continue

    buffer += byte

    # Prüfe auf vollständiges Telegramm-Ende
    if buffer.endswith(b"\x1b\x1b\x1b\x1a") and len(buffer) > 8:
        try:
            start_idx = buffer.find(b"\x1b\x1b\x1b\x1b")
            if start_idx == -1:
                buffer = b""
                continue

            telegram = buffer[start_idx:]
            end_marker = b"\x1b\x1b\x1b\x1a"
            end_idx = telegram.find(end_marker)

            if end_idx == -1 or len(telegram) < end_idx + 4:
                continue  # Unvollständig

            # Datenbereich für CRC (inkl. SML, bis inkl. 0x1A)
            crc_data = telegram[:end_idx + 1]

            # Die 2 Bytes direkt nach 1A enthalten den CRC
            crc_bytes = telegram[end_idx + 1:end_idx + 3]
            if len(crc_bytes) != 2:
                continue  # Ungültige Länge

            crc_expected = int.from_bytes(crc_bytes, "little")
            crc_calculated = binascii.crc_hqx(crc_data, 0xFFFF)

            logging.info("")
            logging.info("[%s]", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            logging.info("📡 SML-Telegramm erkannt (Länge: %d Bytes)", len(crc_data))
            logging.info("🔢 HEX: %s", crc_data.hex())
            logging.info("🔢 CRC-Rohbytes: %s", crc_bytes.hex())
            logging.info("✅ CRC: erwartet %04X, berechnet %04X → %s",
                         crc_expected,
                         crc_calculated,
                         "✅ gültig" if crc_expected == crc_calculated else "❌ ungültig")

        except Exception as e:
            logging.error("❌ Fehler beim Verarbeiten: %s", e)
        finally:
            buffer = b""