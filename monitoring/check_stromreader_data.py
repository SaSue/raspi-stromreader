#!/usr/bin/env python3
import argparse
import sqlite3
import sys
from datetime import datetime


def parse_timestamp(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-d", "--database", default="/var/www/html/strom.sqlite")
    parser.add_argument("-w", "--warning", type=int, default=180)
    parser.add_argument("-c", "--critical", type=int, default=600)
    args = parser.parse_args()

    if args.warning <= 0 or args.critical <= args.warning:
        print("UNKNOWN - thresholds must satisfy 0 < warning < critical")
        return 3

    try:
        connection = sqlite3.connect(
            f"file:{args.database}?mode=ro", uri=True, timeout=5
        )
        row = connection.execute(
            "SELECT MAX(timestamp) FROM messwerte"
        ).fetchone()
        connection.close()
        if not row or not row[0]:
            print("CRITICAL - no meter readings found")
            return 2

        last_reading = parse_timestamp(row[0])
        now = datetime.now(last_reading.tzinfo) if last_reading.tzinfo else datetime.now()
        age = max(0, int((now - last_reading).total_seconds()))
    except (OSError, sqlite3.Error, TypeError, ValueError) as error:
        print(f"UNKNOWN - cannot read meter database: {error}")
        return 3

    performance = f"age={age}s;{args.warning};{args.critical};0"
    if age >= args.critical:
        print(f"CRITICAL - last meter reading is {age}s old | {performance}")
        return 2
    if age >= args.warning:
        print(f"WARNING - last meter reading is {age}s old | {performance}")
        return 1

    print(f"OK - last meter reading is {age}s old | {performance}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
