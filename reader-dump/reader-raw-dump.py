import serial
import time
import os
import logging

PORT = "/dev/ttyUSB0"      # ggf. anpassen
BAUDRATE = 9600
LOGFILE = "/app/data/log/strom_raw_dump.log"

# Logging konfigurieren
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOGFILE),
        logging.StreamHandler()  # Für die Ausgabe in die Konsole
    ]
)

def dump_serial():
    try:
        with serial.Serial(PORT, BAUDRATE, timeout=3) as ser:
            logging.info(f"Verbunden mit {PORT} @ {BAUDRATE} Baud")
            while True:
                data = ser.read(512)
                if data:
                    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
                    hex_data = data.hex()
                    ascii_data = data.decode('latin1', errors='replace')

                    logging.info(f"[{timestamp}] HEX: {hex_data}")
                    logging.info(f"[{timestamp}] ASCII: {ascii_data}")
    except serial.SerialException as e:
        logging.error("Serieller Zugriff fehlgeschlagen: %s", e)
    except KeyboardInterrupt:
        logging.info("Beendet durch Benutzer")

if __name__ == "__main__":
    dump_serial()
