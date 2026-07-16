import importlib.util
import os
import sqlite3
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path


BACKEND_PATH = (
    Path(__file__).parents[1]
    / "dashboard"
    / "dashboard-backend"
    / "dashboard-backend.py"
)


def load_backend(db_path):
    os.environ["DB_PATH"] = str(db_path)
    spec = importlib.util.spec_from_file_location("dashboard_backend", BACKEND_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.app.config.update(TESTING=True)
    return module


class DashboardBackendTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "strom.sqlite"
        self.conn = sqlite3.connect(self.db_path)
        self.conn.executescript(
            """
            CREATE TABLE messwerte (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                zaehler_id INTEGER,
                timestamp TEXT,
                bezug_kwh REAL,
                einspeisung_kwh REAL,
                wirkleistung_watt REAL
            );
            CREATE INDEX idx_timestamp ON messwerte(timestamp);
            """
        )
        self.backend = load_backend(self.db_path)
        self.client = self.backend.app.test_client()

    def tearDown(self):
        self.conn.close()
        self.temp_dir.cleanup()

    def insert(self, day, hour, bezug, einspeisung, watt):
        timestamp = f"{day.isoformat()}T{hour:02d}:00:00"
        self.conn.execute(
            """
            INSERT INTO messwerte
                (zaehler_id, timestamp, bezug_kwh, einspeisung_kwh, wirkleistung_watt)
            VALUES (1, ?, ?, ?, ?)
            """,
            (timestamp, bezug, einspeisung, watt),
        )
        self.conn.commit()

    def test_tagesdaten_returns_same_aggregates_and_history(self):
        selected = date(2026, 1, 10)
        self.insert(selected, 0, 100.0, 10.0, 100)
        self.insert(selected, 12, 102.5, 10.5, 300)
        self.insert(selected + timedelta(days=1), 0, 103.0, 11.0, 900)

        response = self.client.get(f"/api/tagesdaten?datum={selected.isoformat()}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["verbrauch"], 2.5)
        self.assertEqual(response.json["endstand"], 102.5)
        self.assertEqual(len(response.json["verlauf"]), 2)

    def test_wochenstatistik_does_not_include_eighth_day(self):
        selected = date(2026, 2, 2)
        for offset in range(8):
            current = selected + timedelta(days=offset)
            self.insert(current, 0, 200 + offset, 0, 100)
            self.insert(current, 12, 201 + offset, 0, 200)

        response = self.client.get(
            f"/api/wochenstatistik?datum={selected.isoformat()}"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json), 7)
        self.assertEqual(response.json[-1]["datum"], (selected + timedelta(days=6)).isoformat())

    def test_invalid_date_is_rejected(self):
        response = self.client.get("/api/tagesdaten?datum=kein-datum")
        self.assertEqual(response.status_code, 400)

    def test_statistics_endpoints_keep_their_response_shape(self):
        first = date.today() - timedelta(days=40)
        second = date.today() - timedelta(days=10)
        for current, base in ((first, 100.0), (second, 150.0)):
            self.insert(current, 0, base, 10.0, 100)
            self.insert(current, 12, base + 2.0, 11.0, 300)

        dashboard = self.client.get("/api/dashboard")
        monthly = self.client.get("/api/monatsstatistik")
        yearly = self.client.get("/api/jahresstatistik")
        statistics = self.client.get("/api/statistik")

        self.assertEqual(dashboard.status_code, 200)
        self.assertEqual(
            set(dashboard.json),
            {
                "leistung", "timestamp", "bezug", "einspeisung",
                "verbrauchHeute", "tendenz", "verbrauchGestern",
                "maxHeute", "minHeute", "avgHeute", "maxGestern",
                "minGestern", "avgGestern",
            },
        )
        self.assertEqual(monthly.status_code, 200)
        self.assertEqual(yearly.status_code, 200)
        self.assertEqual(statistics.status_code, 200)
        self.assertEqual(
            set(statistics.json),
            {"maxTag", "minTag", "avgTag", "maxMonat", "minMonat", "avgMonat"},
        )

    def test_day_range_query_uses_timestamp_index_with_large_table(self):
        self.conn.execute(
            """
            WITH RECURSIVE sequence(value) AS (
                SELECT 0
                UNION ALL
                SELECT value + 1 FROM sequence WHERE value < 499999
            )
            INSERT INTO messwerte
                (zaehler_id, timestamp, bezug_kwh, einspeisung_kwh, wirkleistung_watt)
            SELECT 1,
                   datetime('2025-01-01', '+' || value || ' minutes'),
                   value / 1000.0,
                   0,
                   value % 5000
            FROM sequence
            """
        )
        self.conn.commit()

        plan = self.conn.execute(
            """
            EXPLAIN QUERY PLAN
            SELECT * FROM messwerte WHERE timestamp >= ? AND timestamp < ?
            """,
            ("2026-01-10", "2026-01-11"),
        ).fetchall()

        self.assertIn("USING INDEX idx_timestamp", " ".join(row[3] for row in plan))


if __name__ == "__main__":
    unittest.main()
