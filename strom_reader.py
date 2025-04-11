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

    # Prüfe auf SML-Ende
    if buffer.endswith(b"\x1b\x1b\x1b\x1b\x1a") and len(buffer) > 100:
        try:
            start_idx = buffer.find(b"\x1b\x1b\x1b\x1b")
            if start_idx == -1:
                buffer = b""
                continue

            # Finde erstes komplettes Telegramm
            end_idx = buffer.find(b"\x1b\x1b\x1b\x1b\x1a", start_idx)
            if end_idx == -1 or len(buffer) < end_idx + 5:
                continue

            # Enthält: [START]...1b1b1b1b1a[FILLBYTE][CRC1][CRC2]
            telegram_body = buffer[start_idx:end_idx + 2]  # inkl. 0x1a
            fill_byte = buffer[end_idx + 2:end_idx + 3]
            logging.info("🔢 HEX raw: %s", telegram_body.hex())
            crc_raw = buffer[end_idx + 3:end_idx + 5]

            if len(fill_byte) < 1 or len(crc_raw) < 2:
                continue

            telegram_for_crc = telegram_body + fill_byte
            crc_expected = int.from_bytes(crc_raw, "little")
            crc_calculated = binascii.crc_hqx(telegram_for_crc, 0xffff)

            logging.info("")
            logging.info("[%s]", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            logging.info("📡 SML-Telegramm erkannt (Länge: %d Bytes)", len(telegram_for_crc))
            logging.info("🔢 HEX komplett: %s", (telegram_for_crc + crc_raw).hex())
            logging.info("🔢 CRC-Rohbytes: %s", crc_raw.hex())
            logging.info("✅ CRC: erwartet %04X, berechnet %04X → %s",
                         crc_expected,
                         crc_calculated,
                         "✅ gültig" if crc_expected == crc_calculated else "❌ ungültig")

        except Exception as e:
            logging.error("❌ Fehler beim Verarbeiten: %s", e)
        finally:
            buffer = b""