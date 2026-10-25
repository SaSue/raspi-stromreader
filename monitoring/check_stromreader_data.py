#!/usr/bin/env python3
import argparse
import sqlite3
import sys
from datetime import datetime, timezone


def parse_timestamp(value):
    timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if timestamp.tzinfo is None:
        raise ValueError("timestamp without UTC offset; UTC migration required")
    return timestamp.astimezone(timezone.utc)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-d", "--database", default="/var/www/html/strom.sqlite")
    parser.add_argument("-w", "--warning", type=int, default=180)
    parser.add_argument("-c", "--critical", type=int, default=600)
    parser.add_argument("--timezone", help="Deprecated; timestamps must contain an offset")
    args = parser.parse_args()

    if args.warning <= 0 or args.critical <= args.warning:
        print("UNKNOWN - thresholds must satisfy 0 < warning < critical")
        return 3

    try:
        connection = sqlite3.connect(
            f"file:{args.database}?mode=ro", uri=True, timeout=5
        )
        row = connection.execute(
            "SELECT timestamp FROM messwerte ORDER BY rowid DESC LIMIT 1"
        ).fetchone()
        connection.close()
        if not row or not row[0]:
            print("CRITICAL - no meter readings found")
            return 2

        last_reading = parse_timestamp(row[0])
        now = datetime.now(timezone.utc)
        age = int((now - last_reading).total_seconds())
        if age < -300:
            print(f"UNKNOWN - last meter reading is {-age}s in the future")
            return 3
        age = max(0, age)
    except (OSError, sqlite3.Error, TypeError, ValueError, KeyError) as error:
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
