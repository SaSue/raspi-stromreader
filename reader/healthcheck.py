#!/usr/bin/env python3
"""Docker health check for the meter reader."""

import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo


DB_PATH = Path(os.getenv("DB_PATH", "/app/data/strom.sqlite"))
MAX_AGE_SECONDS = int(os.getenv("READER_HEALTH_MAX_AGE_SECONDS", "180"))
FUTURE_TOLERANCE_SECONDS = int(
    os.getenv("READER_HEALTH_FUTURE_TOLERANCE_SECONDS", "60")
)
LOCAL_TIMEZONE = ZoneInfo(os.getenv("TZ", "Europe/Berlin"))


def newest_measurement(db_path=DB_PATH):
    uri = f"{Path(db_path).resolve().as_uri()}?mode=ro"
    with sqlite3.connect(uri, uri=True, timeout=5) as connection:
        row = connection.execute(
            "SELECT MAX(timestamp) FROM messwerte"
        ).fetchone()
    return row[0] if row else None


def parse_timestamp(value):
    timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=LOCAL_TIMEZONE)
    return timestamp.astimezone(timezone.utc)


def check_health(db_path=DB_PATH, now=None):
    try:
        value = newest_measurement(db_path)
        if not value:
            return False, "no measurements in database"

        current_time = now or datetime.now(timezone.utc)
        age = (current_time - parse_timestamp(value)).total_seconds()
        if age < -FUTURE_TOLERANCE_SECONDS:
            return False, f"newest measurement is {-age:.0f}s in the future"
        if age > MAX_AGE_SECONDS:
            return False, f"newest measurement is {age:.0f}s old"
        return True, f"newest measurement is {max(age, 0):.0f}s old"
    except (OSError, sqlite3.Error, TypeError, ValueError) as error:
        return False, f"database check failed: {error}"


def main():
    healthy, message = check_health()
    print(message)
    return 0 if healthy else 1


if __name__ == "__main__":
    sys.exit(main())
