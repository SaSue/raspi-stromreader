#!/usr/bin/env python3
import os
import pty
import time
import argparse

# Beispiel-Telegramm (als Hex-String), das du vorgibst
SML_HEX = (
    "691cbf621b520055000007270101016356ea007605007701bd620062007263020171016396bf000000001b1b1b1b1a031b831b1b1b1b010101017605007701be6200620072630101760107ffffffffffff050027ab400b0a01454d480000b8ef797262016501691cc0620163bf91007605007701bf62006200726307017707ffffffffffff0b0a01454d480000b8ef79070100620affff7262016501691cc07577070100603201010101010104454d480177070100600100ff010101010b0a01454d480000b8ef790177070100010800ff641c81047262016501691cc0621e52ff690000000002a021180177070100020800ff017262016501691cc0621e52ff6900000000000006110177070100100700ff017262016501691cc0621b5200550000072d01010163ebc5007605007701c062006200726302017101633256000000001b1b1b1b1a0359461b1b1b1b010101017605007701c16200620072630101760107ffffffffffff050027ab410b0a01454d480000b8ef797262016501691cc16201635d0f007605007701c262006200726307017707ffffffffffff0b0a01454d480000b8ef79070100620affff7262016501691cc17577070100603201010101010104454d480177070100600100ff010101010b0a01454d480000b8ef790177070100010800ff641c81047262016501691cc1621e52ff690000000002a0"
)

def hex_to_bytes(hex_string: str) -> bytes:
    return bytes.fromhex(hex_string.replace(" ", "").replace("\n", ""))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--interval", type=float, default=5.0, help="Wiederholintervall in Sekunden")
    parser.add_argument("--telegram", type=str, help="Pfad zu Datei mit SML-Telegramm (hex)", required=False)
    args = parser.parse_args()

    # Telegramm laden
    telegram = hex_to_bytes(SML_HEX)
    if args.telegram:
        with open(args.telegram, "r") as f:
            telegram = hex_to_bytes(f.read())

    master, slave = pty.openpty()
    slave_name = os.ttyname(slave)

    print(f"Virtueller Zähler läuft. Serielle Schnittstelle: {slave_name}")
    print(f"Telegrammlänge: {len(telegram)} Bytes")
    print("Zum Testen in strom_reader.py einfach diese Schnittstelle verwenden.")

    while True:
        os.write(master, telegram)
        time.sleep(args.interval)

if __name__ == "__main__":
    main()