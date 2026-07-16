import sqlite3
import tempfile
import unittest
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).parents[1] / "reader"))
from sqlite_store import SQLiteStore


class SQLiteStoreTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "strom.sqlite"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_reuses_connection_and_meter_id(self):
        store = SQLiteStore(self.db_path)
        original_connection = store.connection

        store.save("meter-1", "EMH", 10.0, 1.0, 100)
        store.save("meter-1", "EMH", 10.1, 1.0, 110)

        self.assertIs(store.connection, original_connection)
        self.assertEqual(
            store.connection.execute("SELECT COUNT(*) FROM zaehler").fetchone()[0], 1
        )
        self.assertEqual(
            store.connection.execute("SELECT COUNT(*) FROM messwerte").fetchone()[0], 2
        )
        store.close()

    def test_reconnects_once_after_connection_failure(self):
        store = SQLiteStore(self.db_path)
        failed_connection = store.connection
        failed_connection.close()

        store.save("meter-1", "EMH", 10.0, 1.0, 100)

        self.assertIsNot(store.connection, failed_connection)
        self.assertEqual(
            store.connection.execute("SELECT COUNT(*) FROM messwerte").fetchone()[0], 1
        )
        store.close()

    def test_existing_database_is_kept_without_data_loss(self):
        connection = sqlite3.connect(self.db_path)
        connection.executescript(
            """
            CREATE TABLE zaehler (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                seriennummer TEXT UNIQUE,
                hersteller TEXT,
                name TEXT
            );
            CREATE TABLE messwerte (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                zaehler_id INTEGER,
                timestamp TEXT,
                bezug_kwh REAL,
                einspeisung_kwh REAL,
                wirkleistung_watt REAL,
                FOREIGN KEY (zaehler_id) REFERENCES zaehler(id)
            );
            INSERT INTO zaehler (seriennummer, hersteller) VALUES ('old-meter', 'EMH');
            INSERT INTO messwerte
                (zaehler_id, timestamp, bezug_kwh, einspeisung_kwh, wirkleistung_watt)
            VALUES (1, '2025-01-01T00:00:00', 1.0, 0.0, 50);
            """
        )
        connection.commit()
        connection.close()

        store = SQLiteStore(self.db_path)

        self.assertEqual(
            store.connection.execute("PRAGMA user_version").fetchone()[0],
            SQLiteStore.SCHEMA_VERSION,
        )
        self.assertEqual(
            store.connection.execute("SELECT COUNT(*) FROM messwerte").fetchone()[0], 1
        )
        self.assertIsNotNone(
            store.connection.execute(
                "SELECT name FROM sqlite_master WHERE name = 'idx_timestamp'"
            ).fetchone()
        )
        self.assertTrue(store.backup_path.exists())
        backup = sqlite3.connect(store.backup_path)
        self.assertEqual(backup.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        self.assertEqual(backup.execute("SELECT COUNT(*) FROM messwerte").fetchone()[0], 1)
        backup.close()
        store.close()

    def test_migration_is_idempotent_and_does_not_replace_backup(self):
        store = SQLiteStore(self.db_path)
        store.save("meter-1", "EMH", 1.0, 0.0, 10)
        store.close()

        # Simulate a pre-1.1.3 database once so that a rollback backup is created.
        connection = sqlite3.connect(self.db_path)
        connection.execute("PRAGMA user_version = 0")
        connection.commit()
        connection.close()
        migrated = SQLiteStore(self.db_path)
        backup_mtime = migrated.backup_path.stat().st_mtime_ns
        migrated.close()

        reopened = SQLiteStore(self.db_path)
        self.assertEqual(reopened.backup_path.stat().st_mtime_ns, backup_mtime)
        self.assertEqual(
            reopened.connection.execute("SELECT COUNT(*) FROM messwerte").fetchone()[0], 1
        )
        reopened.close()

    def test_migration_stops_when_existing_backup_is_invalid(self):
        connection = sqlite3.connect(self.db_path)
        connection.execute("CREATE TABLE existing_data (value TEXT)")
        connection.commit()
        connection.close()
        backup_path = Path(f"{self.db_path}.backup-v1.1.3")
        backup_path.write_bytes(b"not a sqlite database")

        with self.assertRaises(sqlite3.DatabaseError):
            SQLiteStore(self.db_path)

        connection = sqlite3.connect(self.db_path)
        self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 0)
        self.assertIsNotNone(
            connection.execute(
                "SELECT name FROM sqlite_master WHERE name = 'existing_data'"
            ).fetchone()
        )
        connection.close()


if __name__ == "__main__":
    unittest.main()
