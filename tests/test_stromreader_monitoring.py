import importlib.util
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta
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
        timestamp = (datetime.now() - timedelta(seconds=age)).isoformat()
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

    def test_empty_database_is_critical(self):
        with patch(
            "sys.argv",
            ["check_stromreader_data.py", "-d", str(self.db_path)],
        ):
            self.assertEqual(plugin.main(), 2)


if __name__ == "__main__":
    unittest.main()
