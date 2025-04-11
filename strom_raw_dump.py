import serial
import time
import os

PORT = "/dev/ttyUSB0"      # ggf. anpassen
BAUDRATE = 9600
LOGFILE = "strom_raw_dump.log"

def dump_serial():
    try:
        with serial.Serial(PORT, BAUDRATE, timeout=3) as ser:
            print(f"[INFO] Verbunden mit {PORT} @ {BAUDRATE} Baud")
            with open(LOGFILE, "a") as logfile:
                while True:
                    data = ser.read(512)
                    if data:
                        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
                        hex_data = data.hex()
                        ascii_data = data.decode('latin1', errors='replace')

                        print(f"\n[{timestamp}]")
                        print("🔢 HEX:", hex_data)
                        print("🔤 ASCII:", ascii_data)

                        logfile.write(f"[{timestamp}] HEX: {hex_data}\n")
                        logfile.write(f"[{timestamp}] ASCII: {ascii_data}\n")
                        logfile.flush()
    except serial.SerialException as e:
        print("[FEHLER] Serieller Zugriff fehlgeschlagen:", e)
    except KeyboardInterrupt:
        print("\n[INFO] Beendet durch Benutzer")

if __name__ == "__main__":
    dump_serial()