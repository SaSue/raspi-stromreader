"""Import archived JSON into an already migrated UTC database atomically.

Legacy timestamps without offsets must first be resolved from provenance;
never discard a Z suffix or assume a fold during the autumn rollback.
"""
import glob
import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path('/app/data/strom.sqlite')
HISTORY_PATH = Path('/app/data/history')
ZAEHLER_ID = 1


def utc_timestamp(value):
    moment = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if moment.tzinfo is None:
        raise ValueError('JSON timestamp without offset; resolve timezone first')
    return moment.astimezone(timezone.utc).isoformat(timespec='microseconds')


def main():
    # mode=rw prevents an accidental empty database at a misspelled path.
    with sqlite3.connect(DB_PATH.resolve().as_uri() + '?mode=rw', uri=True) as conn:
        if conn.execute('PRAGMA user_version').fetchone()[0] != 3:
            raise ValueError('UTC schema 3 required; migrate database first')
        conn.execute('PRAGMA foreign_keys=ON')
        count = 0
        for filename in sorted(glob.glob(str(HISTORY_PATH / '*.json'))):
            with open(filename, encoding='utf-8') as stream:
                for entry in json.load(stream):
                    conn.execute('''INSERT INTO messwerte
                        (zaehler_id,timestamp,bezug_kwh,einspeisung_kwh,wirkleistung_watt)
                        VALUES (?, ?, ?, ?, ?)''',
                        (ZAEHLER_ID, utc_timestamp(entry['timestamp']), float(entry['bezug']),
                         float(entry['einspeisung']), int(entry['leistung'])))
                    count += 1
        # Context manager commits all files together, or rolls back on any error.
    logging.info('Imported %d UTC measurements', count)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    main()
