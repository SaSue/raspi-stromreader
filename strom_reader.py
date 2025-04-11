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
    byte = ser.read(1)
    if not byte:
        continue

    buffer += byte

    # Suche nach Startmarker (erste 4 Bytes)
    start_idx = buffer.find(b"\x1b\x1b\x1b\x1b")
    if start_idx == -1:
        buffer = b""
        continue

    # Suche nach Ende (1b1b1b1a)
    end_idx = buffer.find(b"\x1b\x1b\x1b\x1a", start_idx)
    if end_idx == -1:
        continue  # Ende noch nicht da

    # Prüfe ob mind. 3 weitere Bytes (Padding + 2x CRC)
    if len(buffer) < end_idx + 5:
        continue  # Warte auf restliche Bytes

    # Alles da: Jetzt Telegramm extrahieren
    telegram = buffer[start_idx:end_idx + 5]
    sml_data = telegram[:-2]  # alles vor CRC
    crc_raw = telegram[-2:]   # letzte 2 Bytes = CRC

    # CRC prüfen
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

    # Reset Buffer
    buffer = b""