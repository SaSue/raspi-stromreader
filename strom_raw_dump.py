import serial
import time
import os
import binascii

PORT = "/dev/ttyUSB0"      # ggf. anpassen
BAUDRATE = 9600
LOGFILE = "strom_raw_dump.log"

SML_START = bytes.fromhex("1b1b1b1b01010101")
SML_END = bytes.fromhex("1b1b1b1b1a")


def crc16_sml(data):
    crc = 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = (crc << 1) ^ 0x1021
            else:
                crc <<= 1
            crc &= 0xFFFF
    return crc


def find_telegram(buffer):
    start_idx = buffer.find(SML_START)
    if start_idx == -1:
        return None, buffer

    end_idx = buffer.find(SML_END, start_idx + len(SML_START))
    if end_idx == -1:
        return None, buffer

    telegram = buffer[start_idx:end_idx + len(SML_END)]
    remaining = buffer[end_idx + len(SML_END):]
    return telegram, remaining


def dump_serial():
    try:
        with serial.Serial(PORT, BAUDRATE, timeout=3) as ser:
            print(f"[INFO] Verbunden mit {PORT} @ {BAUDRATE} Baud")
            with open(LOGFILE, "a") as logfile:
                buffer = b""
                while True:
                    data = ser.read(512)
                    if data:
                        buffer += data
                        while True:
                            telegram, buffer = find_telegram(buffer)
                            if not telegram:
                                break

                            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
                            hex_data = telegram.hex()
                            length = len(telegram)

                            # CRC prüfen (letzte 3 Bytes = CRC + 0x1a Padding)
                            crc_data = telegram[:-3]  # alles bis vor CRC
                            crc_expected = int.from_bytes(telegram[-3:-1], "big")
                            crc_actual = crc16_sml(crc_data)
                            crc_ok = crc_actual == crc_expected

                            print(f"\n[{timestamp}]\n📡 SML-Telegramm erkannt (Länge: {length} Bytes)")
                            print("🔢 HEX:", hex_data)
                            print(f"✅ CRC: erwartet {crc_expected:04X}, berechnet {crc_actual:04X} → {'✔ gültig' if crc_ok else '❌ ungültig'}")

                            logfile.write(f"[{timestamp}] SML ({length} Bytes): {hex_data}\n")
                            logfile.write(f"CRC erwartet: {crc_expected:04X}, berechnet: {crc_actual:04X} → {'OK' if crc_ok else 'FEHLER'}\n")
                            logfile.flush()
    except serial.SerialException as e:
        print("[FEHLER] Serieller Zugriff fehlgeschlagen:", e)
    except KeyboardInterrupt:
        print("\n[INFO] Beendet durch Benutzer")


if __name__ == "__main__":
    dump_serial()
