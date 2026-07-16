import logging
import os
import sqlite3
from datetime import datetime
from pathlib import Path


class SQLiteStore:
    """Long-lived SQLite writer with one reconnect attempt per measurement."""

    SCHEMA_VERSION = 2
    VALID_JOURNAL_MODES = {"DELETE", "TRUNCATE", "PERSIST", "MEMORY", "WAL", "OFF"}

    def __init__(self, db_path, timeout=10.0, journal_mode="WAL"):
        self.db_path = Path(db_path)
        self.database_existed = self.db_path.exists() and self.db_path.stat().st_size > 0
        self.timeout = timeout
        self.journal_mode = journal_mode.upper()
        self.connection = None
        self.zaehler_ids = {}
        self.connect()
        self.migrate_schema()

    def connect(self):
        self.close()
        connection = sqlite3.connect(str(self.db_path), timeout=self.timeout)
        connection.execute("PRAGMA busy_timeout = 10000")
        connection.execute("PRAGMA foreign_keys = ON")
        self.connection = connection
        self.zaehler_ids.clear()

    def integrity_check(self):
        result = self.connection.execute("PRAGMA integrity_check").fetchone()[0]
        if result != "ok":
            raise sqlite3.DatabaseError(f"SQLite integrity check failed: {result}")

    @property
    def backup_path(self):
        return Path(f"{self.db_path}.backup-v1.1.3")

    def create_migration_backup(self):
        if not self.database_existed:
            return

        if self.backup_path.exists():
            backup_connection = sqlite3.connect(
                f"file:{self.backup_path}?mode=ro", uri=True
            )
            try:
                backup_result = backup_connection.execute(
                    "PRAGMA integrity_check"
                ).fetchone()[0]
            finally:
                backup_connection.close()
            if backup_result != "ok":
                raise sqlite3.DatabaseError(
                    f"Existing SQLite backup integrity check failed: {backup_result}"
                )
            logging.info("Vorhandenes SQLite-Migrationsbackup geprüft: %s", self.backup_path)
            return

        temporary_path = Path(f"{self.backup_path}.tmp")
        try:
            backup_connection = sqlite3.connect(str(temporary_path))
            self.connection.backup(backup_connection)
            backup_result = backup_connection.execute(
                "PRAGMA integrity_check"
            ).fetchone()[0]
            backup_connection.close()
            if backup_result != "ok":
                raise sqlite3.DatabaseError(
                    f"SQLite backup integrity check failed: {backup_result}"
                )
            os.replace(temporary_path, self.backup_path)
            logging.info("SQLite-Migrationsbackup erstellt: %s", self.backup_path)
        except Exception:
            if temporary_path.exists():
                temporary_path.unlink()
            raise

    def migrate_schema(self):
        self.integrity_check()
        current_version = self.connection.execute("PRAGMA user_version").fetchone()[0]
        if current_version > self.SCHEMA_VERSION:
            raise sqlite3.DatabaseError(
                f"Database schema {current_version} is newer than supported "
                f"schema {self.SCHEMA_VERSION}"
            )

        if current_version < self.SCHEMA_VERSION:
            self.create_migration_backup()
            with self.connection:
                self.connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS zaehler (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        seriennummer TEXT UNIQUE,
                        hersteller TEXT,
                        name TEXT
                    )
                    """
                )
                self.connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS messwerte (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        zaehler_id INTEGER,
                        timestamp TEXT,
                        bezug_kwh REAL,
                        einspeisung_kwh REAL,
                        wirkleistung_watt REAL,
                        FOREIGN KEY (zaehler_id) REFERENCES zaehler(id)
                    )
                    """
                )
                self.connection.execute(
                    "CREATE INDEX IF NOT EXISTS idx_timestamp ON messwerte(timestamp)"
                )
                self.connection.execute(f"PRAGMA user_version = {self.SCHEMA_VERSION}")
            self.integrity_check()
            logging.info(
                "SQLite-Schema von Version %d auf %d migriert",
                current_version,
                self.SCHEMA_VERSION,
            )

        if self.journal_mode in self.VALID_JOURNAL_MODES:
            active_mode = self.connection.execute(
                f"PRAGMA journal_mode = {self.journal_mode}"
            ).fetchone()[0]
            logging.info("SQLite Journal-Modus: %s", active_mode)
        else:
            logging.warning("Ungültiger SQLITE_JOURNAL_MODE: %s", self.journal_mode)

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
            self.migrate_schema()
            self._save_once(
                seriennummer, hersteller, bezug_kwh, einspeisung_kwh, wirkleistung_watt
            )

    def close(self):
        if self.connection is not None:
            try:
                self.connection.close()
            finally:
                self.connection = None
