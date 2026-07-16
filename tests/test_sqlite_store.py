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
            store.connection.execute("SELECT COUNT(*) FROM messwerte").fetchone()[0], 1
        )
        self.assertIsNotNone(
            store.connection.execute(
                "SELECT name FROM sqlite_master WHERE name = 'idx_timestamp'"
            ).fetchone()
        )
        store.close()


if __name__ == "__main__":
    unittest.main()
