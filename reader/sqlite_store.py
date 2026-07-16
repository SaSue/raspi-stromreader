import logging
import sqlite3
from datetime import datetime


class SQLiteStore:
    """Long-lived SQLite writer with one reconnect attempt per measurement."""

    VALID_JOURNAL_MODES = {"DELETE", "TRUNCATE", "PERSIST", "MEMORY", "WAL", "OFF"}

    def __init__(self, db_path, timeout=10.0, journal_mode="WAL"):
        self.db_path = db_path
        self.timeout = timeout
        self.journal_mode = journal_mode.upper()
        self.connection = None
        self.zaehler_ids = {}
        self.connect()
        self.initialize_schema()

    def connect(self):
        self.close()
        connection = sqlite3.connect(self.db_path, timeout=self.timeout)
        connection.execute("PRAGMA busy_timeout = 10000")
        connection.execute("PRAGMA foreign_keys = ON")
        self.connection = connection
        self.zaehler_ids.clear()

    def initialize_schema(self):
        if self.journal_mode in self.VALID_JOURNAL_MODES:
            active_mode = self.connection.execute(
                f"PRAGMA journal_mode = {self.journal_mode}"
            ).fetchone()[0]
            logging.info("SQLite Journal-Modus: %s", active_mode)
        else:
            logging.warning("Ungültiger SQLITE_JOURNAL_MODE: %s", self.journal_mode)

        with self.connection:
            self.connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS zaehler (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    seriennummer TEXT UNIQUE,
                    hersteller TEXT,
                    name TEXT
                );

                CREATE TABLE IF NOT EXISTS messwerte (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    zaehler_id INTEGER,
                    timestamp TEXT,
                    bezug_kwh REAL,
                    einspeisung_kwh REAL,
                    wirkleistung_watt REAL,
                    FOREIGN KEY (zaehler_id) REFERENCES zaehler(id)
                );

                CREATE INDEX IF NOT EXISTS idx_timestamp ON messwerte(timestamp);
                """
            )

    def _save_once(self, seriennummer, hersteller, bezug_kwh, einspeisung_kwh, wirkleistung_watt):
        with self.connection:
            cursor = self.connection.cursor()
            zaehler_id = self.zaehler_ids.get(seriennummer)
            if zaehler_id is None:
                row = cursor.execute(
                    "SELECT id FROM zaehler WHERE seriennummer = ?", (seriennummer,)
                ).fetchone()
                if row:
                    zaehler_id = row[0]
                else:
                    cursor.execute(
                        "INSERT INTO zaehler (seriennummer, hersteller) VALUES (?, ?)",
                        (seriennummer, hersteller),
                    )
                    zaehler_id = cursor.lastrowid
                self.zaehler_ids[seriennummer] = zaehler_id

            cursor.execute(
                """
                INSERT INTO messwerte
                    (zaehler_id, timestamp, bezug_kwh, einspeisung_kwh, wirkleistung_watt)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    zaehler_id,
                    datetime.now().isoformat(),
                    bezug_kwh,
                    einspeisung_kwh,
                    wirkleistung_watt,
                ),
            )

    def save(self, seriennummer, hersteller, bezug_kwh, einspeisung_kwh, wirkleistung_watt):
        try:
            self._save_once(
                seriennummer, hersteller, bezug_kwh, einspeisung_kwh, wirkleistung_watt
            )
        except sqlite3.Error:
            logging.exception("SQLite-Schreibfehler; Verbindung wird einmal neu aufgebaut")
            self.connect()
            self.initialize_schema()
            self._save_once(
                seriennummer, hersteller, bezug_kwh, einspeisung_kwh, wirkleistung_watt
            )

    def close(self):
        if self.connection is not None:
            try:
                self.connection.close()
            finally:
                self.connection = None
