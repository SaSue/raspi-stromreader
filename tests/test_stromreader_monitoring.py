import importlib.util
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from pathlib import Path
from unittest.mock import patch


PLUGIN_PATH = Path(__file__).parents[1] / "monitoring" / "check_stromreader_data.py"
spec = importlib.util.spec_from_file_location("check_stromreader_data", PLUGIN_PATH)
plugin = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plugin)


class StromreaderMonitoringTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "strom.sqlite"
        connection = sqlite3.connect(self.db_path)
        connection.execute("CREATE TABLE messwerte (timestamp TEXT)")
        connection.commit()
        connection.close()

    def tearDown(self):
        self.temp_dir.cleanup()

    def run_check(self, age):
        timestamp = (
            datetime.now(timezone.utc) - timedelta(seconds=age)
        ).isoformat()
        connection = sqlite3.connect(self.db_path)
        connection.execute("DELETE FROM messwerte")
        connection.execute("INSERT INTO messwerte VALUES (?)", (timestamp,))
        connection.commit()
        connection.close()
        arguments = [
            "check_stromreader_data.py", "-d", str(self.db_path),
            "-w", "180", "-c", "600",
        ]
        with patch("sys.argv", arguments):
            return plugin.main()

    def test_ok_warning_and_critical_thresholds(self):
        self.assertEqual(self.run_check(60), 0)
        self.assertEqual(self.run_check(240), 1)
        self.assertEqual(self.run_check(900), 2)

    def test_autumn_rollback_does_not_select_text_maximum(self):
        with sqlite3.connect(self.db_path) as c:
            c.executemany("INSERT INTO messwerte VALUES (?)", [
                ("2026-10-25T02:59:00+02:00",), ("2026-10-25T02:01:30+01:00",)])
        class Clock(datetime):
            @classmethod
            def now(cls, tz=None):
                return datetime.fromisoformat("2026-10-25T01:02:00+00:00")
        with patch.object(plugin, "datetime", Clock), patch("sys.argv", [
            "check", "-d", str(self.db_path)]):
            self.assertEqual(plugin.main(),0)

    def test_empty_database_is_critical(self):
        with patch(
            "sys.argv",
            ["check_stromreader_data.py", "-d", str(self.db_path)],
        ):
            self.assertEqual(plugin.main(), 2)


if __name__ == "__main__":
    unittest.main()
