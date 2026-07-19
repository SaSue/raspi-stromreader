import importlib.util
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


reader_health = load_module("reader_health", ROOT / "reader" / "healthcheck.py")
backend_health = load_module(
    "backend_health",
    ROOT / "dashboard" / "dashboard-backend" / "healthcheck.py",
)


class ReaderHealthcheckTest(unittest.TestCase):
    def create_database(self, timestamp=None):
        temporary_directory = tempfile.TemporaryDirectory()
        database = Path(temporary_directory.name) / "strom.sqlite"
        with sqlite3.connect(database) as connection:
            connection.execute(
                "CREATE TABLE messwerte (timestamp TEXT NOT NULL)"
            )
            if timestamp:
                connection.execute(
                    "INSERT INTO messwerte (timestamp) VALUES (?)",
                    (timestamp,),
                )
        return temporary_directory, database

    def test_recent_measurement_is_healthy(self):
        now = datetime.now(timezone.utc)
        temporary_directory, database = self.create_database(
            (now - timedelta(seconds=30)).isoformat()
        )
        self.addCleanup(temporary_directory.cleanup)

        healthy, _ = reader_health.check_health(database, now=now)

        self.assertTrue(healthy)

    def test_stale_measurement_is_unhealthy(self):
        now = datetime.now(timezone.utc)
        temporary_directory, database = self.create_database(
            (now - timedelta(seconds=600)).isoformat()
        )
        self.addCleanup(temporary_directory.cleanup)

        healthy, message = reader_health.check_health(database, now=now)

        self.assertFalse(healthy)
        self.assertIn("old", message)

    def test_naive_local_timestamp_is_supported(self):
        now = datetime.now(timezone.utc)
        local_timestamp = (
            now.astimezone(reader_health.LOCAL_TIMEZONE)
            - timedelta(seconds=30)
        ).replace(tzinfo=None)
        temporary_directory, database = self.create_database(
            local_timestamp.isoformat()
        )
        self.addCleanup(temporary_directory.cleanup)

        healthy, _ = reader_health.check_health(database, now=now)

        self.assertTrue(healthy)

    def test_missing_database_is_unhealthy(self):
        healthy, _ = reader_health.check_health("/does/not/exist.sqlite")

        self.assertFalse(healthy)


class FakeResponse:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, *_args):
        return b'{"timestamp": "2026-01-01T00:00:00+00:00"}'


class BackendHealthcheckTest(unittest.TestCase):
    @patch.object(backend_health, "urlopen", return_value=FakeResponse())
    def test_valid_api_response_is_healthy(self, _urlopen):
        healthy, _ = backend_health.check_health()

        self.assertTrue(healthy)

    @patch.object(backend_health, "urlopen")
    def test_unreachable_api_is_unhealthy(self, urlopen):
        urlopen.side_effect = backend_health.URLError("unreachable")

        healthy, _ = backend_health.check_health()

        self.assertFalse(healthy)


if __name__ == "__main__":
    unittest.main()
