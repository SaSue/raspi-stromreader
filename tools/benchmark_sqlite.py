#!/usr/bin/env python3
import argparse
import sqlite3
import time
from datetime import datetime, date, timezone
from zoneinfo import ZoneInfo


OLD_QUERY = """
SELECT MAX(bezug_kwh) - MIN(bezug_kwh)
FROM messwerte
WHERE berlin_date(timestamp) = ?
"""

NEW_QUERY = """
SELECT MAX(bezug_kwh) - MIN(bezug_kwh)
FROM messwerte
WHERE timestamp >= ? AND timestamp < ?
"""


def measure(connection, query, parameters, repetitions):
    started = time.perf_counter()
    for _ in range(repetitions):
        connection.execute(query, parameters).fetchone()
    return (time.perf_counter() - started) / repetitions


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("database")
    parser.add_argument("date", help="Date to benchmark in YYYY-MM-DD format")
    parser.add_argument("next_date", help="Following date in YYYY-MM-DD format")
    parser.add_argument("--repetitions", type=int, default=5)
    args = parser.parse_args()

    connection = sqlite3.connect(
        f"file:{args.database}?mode=ro", uri=True, timeout=10
    )
    zone = ZoneInfo("Europe/Berlin")
    connection.create_function("berlin_date", 1, lambda value: datetime.fromisoformat(
        value.replace("Z", "+00:00")).astimezone(zone).date().isoformat())
    bounds = tuple(datetime.combine(date.fromisoformat(day), datetime.min.time(), zone)
                   .astimezone(timezone.utc).isoformat(timespec="microseconds")
                   for day in (args.date, args.next_date))
    old_duration = measure(
        connection, OLD_QUERY, (args.date,), args.repetitions
    )
    new_duration = measure(
        connection, NEW_QUERY, bounds, args.repetitions
    )
    plan = connection.execute(
        f"EXPLAIN QUERY PLAN {NEW_QUERY}", bounds
    ).fetchall()
    connection.close()

    print(f"old_seconds={old_duration:.6f}")
    print(f"new_seconds={new_duration:.6f}")
    print(f"speedup={old_duration / new_duration:.1f}x")
    print("query_plan=" + " | ".join(row[3] for row in plan))


if __name__ == "__main__":
    main()
