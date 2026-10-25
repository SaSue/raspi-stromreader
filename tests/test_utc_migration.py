import importlib.util
import sqlite3
import tempfile
import unittest
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location('migrate_utc', ROOT / 'tools/migrate_utc.py')
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)


class UTCMigrationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.source = Path(self.tmp.name) / 'source.sqlite'
        self.output = Path(self.tmp.name) / 'utc.sqlite'
        with sqlite3.connect(self.source) as c:
            c.executescript('''CREATE TABLE zaehler(id INTEGER PRIMARY KEY);
                INSERT INTO zaehler VALUES (1);
                CREATE TABLE messwerte(id INTEGER PRIMARY KEY, zaehler_id INTEGER,
                timestamp TEXT, bezug_kwh REAL,
                FOREIGN KEY(zaehler_id) REFERENCES zaehler(id));
                PRAGMA user_version=2;''')

    def insert(self, *values):
        with sqlite3.connect(self.source) as c:
            c.executemany('INSERT INTO messwerte(zaehler_id,timestamp,bezug_kwh) VALUES (1,?,12.5)',
                          [(value,) for value in values])

    def test_offsets_and_dst_gap_are_not_guessed(self):
        zone = ZoneInfo('Europe/Berlin')
        for value in ('2026-10-25T02:20:00', '2026-03-29T02:20:00'):
            with self.assertRaises(ValueError):
                migration.normalize(value, zone)
        self.assertEqual(migration.normalize('2026-10-25T02:20:00', zone, 0)[0],
                         '2026-10-25T00:20:00.000000+00:00')
        self.assertEqual(migration.normalize('2026-10-25T02:20:00', zone, 1)[0],
                         '2026-10-25T01:20:00.000000+00:00')
        self.assertEqual(migration.normalize('2026-10-25T02:20:00+01:00', zone)[0],
                         '2026-10-25T01:20:00.000000+00:00')

    def test_snapshot_preserves_source_and_values_and_is_repeatable(self):
        self.insert('2026-07-01T00:30:00', '2026-01-01T00:30:00Z')
        original = self.source.read_bytes()
        self.assertTrue(migration.migrate(self.source)['ready'])
        self.assertFalse(self.output.exists())
        result = migration.migrate(self.source, self.output)
        self.assertTrue(result['ready'])
        self.assertEqual(self.source.read_bytes(), original)
        with sqlite3.connect(self.output) as c:
            self.assertEqual(c.execute('PRAGMA user_version').fetchone()[0], 3)
            self.assertEqual(c.execute('SELECT timestamp,bezug_kwh FROM messwerte WHERE id=1').fetchone(),
                             ('2026-06-30T22:30:00.000000+00:00',12.5))
            self.assertEqual(c.execute('SELECT count(*) FROM utc_migration_audit').fetchone()[0], 2)
        self.assertEqual(migration.migrate(self.output)['changed'], 0)
        with self.assertRaises(FileExistsError):
            migration.migrate(self.source, self.output)

    def test_ambiguous_rows_block_output_until_explicit_decision(self):
        self.insert('2026-10-25T02:59:00', '2026-10-25T02:01:00')
        result = migration.migrate(self.source, self.output)
        self.assertFalse(result['ready'])
        self.assertEqual(len(result['issues']),2)
        self.assertFalse(self.output.exists())
        self.assertTrue(migration.migrate(self.source,self.output,folds={'1':0,'2':1})['ready'])

    def test_mixed_naive_provenance_does_not_double_shift_utc(self):
        self.insert('2025-04-17T20:14:56', '2025-04-17T22:35:00')
        zones = [dict(start_id=1,end_id=1,timezone='UTC',reason='Writer ran without TZ')]
        result = migration.migrate(self.source,self.output,source_zones=zones)
        self.assertTrue(result['ready'])
        self.assertEqual(result['source_zone_rows'], {'UTC':1, 'Europe/Berlin':1})
        with sqlite3.connect(self.output) as c:
            self.assertEqual(c.execute('SELECT timestamp FROM messwerte ORDER BY id').fetchall(),
                             [('2025-04-17T20:14:56.000000+00:00',),
                              ('2025-04-17T20:35:00.000000+00:00',)])
            self.assertEqual(c.execute('SELECT source_timezone FROM utc_migration_audit ORDER BY measurement_id').fetchall(),
                             [('UTC',),('Europe/Berlin',)])

    def test_overlapping_source_ranges_are_rejected(self):
        zones = [dict(start_id=1,end_id=2,timezone='UTC',reason='test'),
                 dict(start_id=2,end_id=3,timezone='UTC',reason='test')]
        with self.assertRaisesRegex(ValueError,'overlapping'):
            migration.migrate(self.source,self.output,source_zones=zones)
        self.assertFalse(self.output.exists())

    def test_unused_decisions_and_invalid_timestamps_block_output(self):
        self.insert('invalid')
        self.assertFalse(migration.migrate(self.source,self.output,folds={'99':1})['ready'])
        self.assertFalse(self.output.exists())

    def test_failed_verification_removes_output(self):
        with sqlite3.connect(self.source) as c:
            c.execute("INSERT INTO messwerte VALUES(1,999,'2026-01-01T00:00:00',1)")
        with self.assertRaisesRegex(ValueError, 'foreign key'):
            migration.migrate(self.source,self.output)
        self.assertFalse(self.output.exists())


class JSONImportTest(unittest.TestCase):
    def test_z_and_offset_are_preserved_as_utc_and_naive_rejected(self):
        spec = importlib.util.spec_from_file_location(
            'json_import', ROOT / 'data-migration/data-migration.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual(module.utc_timestamp('2026-10-25T01:20:00Z'),
                         '2026-10-25T01:20:00.000000+00:00')
        self.assertEqual(module.utc_timestamp('2026-10-25T02:20:00+01:00'),
                         '2026-10-25T01:20:00.000000+00:00')
        with self.assertRaises(ValueError):
            module.utc_timestamp('2026-10-25T02:20:00')


    def test_json_import_rolls_back_all_rows_on_invalid_timestamp(self):
        import json
        spec = importlib.util.spec_from_file_location(
            'json_import_atomic', ROOT / 'data-migration/data-migration.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            module.DB_PATH = Path(directory) / 'strom.sqlite'
            module.HISTORY_PATH = Path(directory)
            with sqlite3.connect(module.DB_PATH) as c:
                c.executescript("""PRAGMA user_version=3;
                    CREATE TABLE messwerte(zaehler_id,timestamp,bezug_kwh,
                    einspeisung_kwh,wirkleistung_watt);""")
            records = [dict(timestamp=t,bezug=10,einspeisung=1,leistung=100)
                       for t in ('2026-10-25T01:00:00Z','2026-10-25T02:00:00')]
            (Path(directory)/'history.json').write_text(json.dumps(records))
            with self.assertRaises(ValueError):
                module.main()
            with sqlite3.connect(module.DB_PATH) as c:
                self.assertEqual(c.execute('SELECT count(*) FROM messwerte').fetchone()[0],0)


if __name__ == '__main__':
    unittest.main()
