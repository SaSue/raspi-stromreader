#!/usr/bin/env python3
"""Audit legacy timestamps or create an independently migrated SQLite snapshot.

Never modifies the source. Naive timestamps require a known source timezone;
ambiguous DST folds require explicit per-row decisions. See docs/utc-migration.md.
"""
import argparse
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo


def normalize(value, zone, fold=None):
    moment = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if moment.tzinfo is not None:
        return moment.astimezone(timezone.utc).isoformat(timespec='microseconds'), 'offset'
    candidates = {}
    for candidate_fold in (0, 1):
        utc = moment.replace(tzinfo=zone, fold=candidate_fold).astimezone(timezone.utc)
        if utc.astimezone(zone).replace(tzinfo=None) == moment:
            candidates[candidate_fold] = utc.isoformat(timespec='microseconds')
    if not candidates:
        raise ValueError('nonexistent local time (spring DST gap)')
    if len(set(candidates.values())) > 1:
        if fold is None:
            raise ValueError('ambiguous local time; choose fold 0 (first) or 1 (second)')
        return candidates[fold], f'explicit-fold-{fold}'
    return next(iter(candidates.values())), 'local-unambiguous'


def migrate(source, output=None, source_timezone='Europe/Berlin', folds=None, source_zones=None):
    zone = ZoneInfo(source_timezone)
    folds = folds or {}
    ranges = []
    for item in source_zones or []:
        start, end = item['start_id'], item['end_id']
        if type(start) is not int or type(end) is not int or not 0 < start <= end:
            raise ValueError('source zone ranges require positive start_id <= end_id')
        if not item.get('reason', '').strip():
            raise ValueError('source zone ranges require a documented reason')
        ranges.append((start, end, ZoneInfo(item['timezone']), item['reason']))
    ranges.sort(key=lambda item: item[0])
    if any(a[1] >= b[0] for a, b in zip(ranges, ranges[1:])):
        raise ValueError('overlapping source zone ranges')
    if any(type(value) is not int or value not in (0, 1) for value in folds.values()):
        raise ValueError('fold decisions must be integer 0 or 1')
    source = Path(source).resolve(strict=True)
    if output is not None and Path(output).resolve() == source:
        raise ValueError('output must differ from source')
    report = {'source_timezone': source_timezone, 'rows': 0, 'changed': 0,
              'ambiguous_resolved': 0, 'issues': [], 'unused_folds': [],
              'source_zone_rows': {}, 'source_zones': source_zones or []}
    created = False
    completed = False
    target = None
    with sqlite3.connect(source.as_uri() + '?mode=ro', uri=True) as src:
        try:
            if output is not None:
                output = Path(output)
                # Exclusive creation: existing snapshots/backups must never be overwritten.
                fd = os.open(output, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                os.close(fd)
                created = True
                target = sqlite3.connect(output)
                src.backup(target)
                db = target
            else:
                db = src
            if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise ValueError('database integrity check failed')
            if db.execute('PRAGMA foreign_key_check').fetchone():
                raise ValueError('foreign key check failed')
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if version not in (0, 1, 2, 3):
                raise ValueError(f'unsupported schema {version}')
            db.execute('BEGIN' if output is None else 'BEGIN IMMEDIATE')
            if output is not None:
                db.execute('''CREATE TABLE IF NOT EXISTS utc_migration_audit (
                    measurement_id INTEGER PRIMARY KEY, original_timestamp TEXT,
                    utc_timestamp TEXT, resolution TEXT, source_timezone TEXT)''')
            used = set()
            for row_id, value in db.execute('SELECT id, timestamp FROM messwerte ORDER BY id'):
                report['rows'] += 1
                try:
                    row_zone = zone
                    for start, end, range_zone, reason in ranges:
                        if start <= row_id <= end:
                            row_zone = range_zone
                            break
                    utc, resolution = normalize(value, row_zone, folds.get(str(row_id)))
                    provenance = 'explicit-offset' if resolution == 'offset' else str(row_zone)
                    report['source_zone_rows'][provenance] = report['source_zone_rows'].get(provenance, 0) + 1
                    if resolution.startswith('explicit-fold'):
                        used.add(str(row_id))
                        report['ambiguous_resolved'] += 1
                    if utc != value:
                        report['changed'] += 1
                        if output is not None:
                            db.execute('INSERT OR IGNORE INTO utc_migration_audit VALUES (?, ?, ?, ?, ?)',
                                       (row_id, value, utc, resolution, provenance))
                            db.execute('UPDATE messwerte SET timestamp=? WHERE id=?', (utc, row_id))
                except (ValueError, TypeError, AttributeError) as error:
                    report['issues'].append({'id': row_id, 'timestamp': value, 'reason': str(error)})
            report['unused_folds'] = sorted(set(folds) - used)
            report['ready'] = not report['issues'] and not report['unused_folds']
            if output is not None and report['ready']:
                db.execute('CREATE INDEX IF NOT EXISTS idx_timestamp ON messwerte(timestamp)')
                db.execute('PRAGMA user_version=3')
                if db.execute('PRAGMA foreign_key_check').fetchone():
                    raise ValueError('foreign key check failed')
                if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                    raise ValueError('post-migration integrity check failed')
                db.commit()
                # Leave one self-contained file, even if source used WAL.
                db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
                db.execute('PRAGMA journal_mode=DELETE')
            else:
                db.rollback()
            completed = report["ready"]
            return report
        except BaseException:
            if target is not None:
                target.rollback()
            raise
        finally:
            if target is not None:
                target.close()
            if created and not completed:
                output.unlink(missing_ok=True)
                Path(str(output) + '-wal').unlink(missing_ok=True)
                Path(str(output) + '-shm').unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--output', type=Path, help='new snapshot; omit for read-only audit')
    parser.add_argument('--source-timezone', default='Europe/Berlin')
    parser.add_argument('--source-zones', type=Path, help='JSON list of documented per-ID source timezone ranges')
    parser.add_argument('--folds', type=Path, help='JSON mapping measurement ID to fold 0/1')
    args = parser.parse_args()
    try:
        folds = json.loads(args.folds.read_text()) if args.folds else {}
        if not isinstance(folds, dict):
            raise ValueError('folds must be a JSON object')
        source_zones = json.loads(args.source_zones.read_text()) if args.source_zones else []
        if not isinstance(source_zones, list):
            raise ValueError('source-zones must be a JSON list')
        report = migrate(args.source, args.output, args.source_timezone, folds, source_zones)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report['ready'] else 2
    except (OSError, ValueError, sqlite3.Error, KeyError) as error:
        parser.exit(1, f'Migration failed: {error}\n')


if __name__ == '__main__':
    raise SystemExit(main())
