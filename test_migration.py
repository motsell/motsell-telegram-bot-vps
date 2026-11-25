"""Reproduce the SQLite WAL example in docs/railway-sqlite-migration.md."""

import shutil
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path


def snapshot(source, path):
    with closing(sqlite3.connect(path)) as destination:
        source.backup(destination)
        destination.execute("PRAGMA journal_mode=DELETE")


def record(connection, update_id):
    with connection:
        connection.execute("INSERT INTO handled VALUES (?)", (update_id,))
        connection.execute("UPDATE cursor SET next_update = ?", (update_id + 1,))


def state(connection):
    return (
        connection.execute("PRAGMA integrity_check").fetchone(),
        connection.execute("SELECT update_id FROM handled ORDER BY update_id").fetchall(),
        connection.execute("SELECT next_update FROM cursor").fetchone(),
    )


class MigrationTests(unittest.TestCase):
    def test_wal_snapshot_and_rollback_keep_committed_updates(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_path = root / "source.db"
            raw_path = root / "raw.db"
            destination_path = root / "destination.db"
            rollback_path = root / "rollback.db"

            with closing(sqlite3.connect(source_path)) as source:
                self.assertEqual(source.execute("PRAGMA journal_mode=WAL").fetchone(), ("wal",))
                source.execute("PRAGMA wal_autocheckpoint=0")
                with source:
                    source.execute("CREATE TABLE handled (update_id INTEGER PRIMARY KEY)")
                    source.execute("CREATE TABLE cursor (next_update INTEGER NOT NULL)")
                    source.execute("INSERT INTO cursor VALUES (40)")
                record(source, 40)
                self.assertEqual(source.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()[0], 0)
                record(source, 41)

                # Deliberately incorrect export, only for this disposable fixture.
                shutil.copyfile(source_path, raw_path)
                snapshot(source, destination_path)
                with closing(sqlite3.connect(raw_path)) as raw:
                    self.assertEqual(state(raw), (("ok",), [(40,)], (41,)))

                with closing(sqlite3.connect(destination_path)) as destination:
                    self.assertEqual(state(destination), (("ok",), [(40,), (41,)], (42,)))
                    record(destination, 42)
                    record(destination, 43)
                    snapshot(destination, rollback_path)

                # The previous state remains intact; restoring it would lose 42 and 43.
                self.assertEqual(state(source), (("ok",), [(40,), (41,)], (42,)))
                with closing(sqlite3.connect(rollback_path)) as rollback:
                    self.assertEqual(state(rollback), (("ok",), [(40,), (41,), (42,), (43,)], (44,)))


if __name__ == "__main__":
    unittest.main()
