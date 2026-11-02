"""Recovery tests run even when the dataframe environment is unavailable."""
import io
import json
import sqlite3
import tarfile
import tempfile
import unittest
from pathlib import Path

from datalake.checkpoint import create, read_manifest, restore, safe_path, sha256


class CheckpointTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.work = Path(self.tmp.name)
        self.root = self.work / "lake"
        (self.root / "metadata").mkdir(parents=True)
        (self.root / "raw/objects").mkdir(parents=True)
        self.raw = self.root / "raw/objects/source"
        self.raw.write_bytes(b"original source bytes")
        with sqlite3.connect(self.root / "metadata/catalog.sqlite") as db:
            db.executescript("""
            CREATE TABLE jobs(id TEXT PRIMARY KEY, source TEXT, state TEXT);
            CREATE TABLE downloads(snapshot_id TEXT,job_id TEXT,path TEXT,sha256 TEXT);
            CREATE TABLE partitions(id TEXT,source TEXT,path TEXT,sha256 TEXT,rows INTEGER);
            CREATE TABLE locks(name TEXT,pid INTEGER);
            INSERT INTO jobs VALUES('request','OFFICIAL','running');
            INSERT INTO locks VALUES('runner',999);
            """)
            db.execute("INSERT INTO downloads VALUES(?,?,?,?)", ("download", "request", "raw/objects/source", sha256(self.raw)))

    def pack(self, name, base=None):
        path = self.work / name
        create(self.root, path, base=base, min_free_gb=0)
        return path

    def test_full_then_delta_restores_new_data_without_recopying_old_source(self):
        base = self.pack("base.tar.gz")
        new = self.root / "raw/objects/new"; new.write_bytes(b"new release")
        with sqlite3.connect(self.root / "metadata/catalog.sqlite") as db:
            db.execute("INSERT INTO downloads VALUES(?,?,?,?)", ("release", "request", "raw/objects/new", sha256(new)))
        delta = self.pack("delta.tar.gz", base)
        manifest = read_manifest(delta)
        self.assertNotIn("raw/objects/source", manifest["included_files"])
        self.assertIn("raw/objects/new", manifest["included_files"])
        restored = self.work / "restored"
        result = restore([base, delta], restored)
        self.assertEqual(result["errors"], [])
        self.assertEqual((restored / "raw/objects/source").read_bytes(), self.raw.read_bytes())
        self.assertEqual((restored / "raw/objects/new").read_bytes(), b"new release")

    def test_mutable_reports_and_views_are_retained_and_updates_are_in_delta(self):
        (self.root / "gold").mkdir(); (self.root / "gold/view.parquet").write_bytes(b"view bytes")
        (self.root / "reports").mkdir(); report = self.root / "reports/coverage.json"
        report.write_text('{"rows":1}')
        base = self.pack("base.tar.gz")
        report.write_text('{"rows":2}')
        delta = self.pack("delta.tar.gz", base)
        self.assertIn("reports/coverage.json", read_manifest(delta)["included_files"])
        self.assertNotIn("gold/view.parquet", read_manifest(delta)["included_files"])
        restore([base, delta], self.work / "restored")
        self.assertEqual((self.work / "restored/reports/coverage.json").read_text(), '{"rows":2}')

    def test_live_running_jobs_and_locks_are_untouched(self):
        base = self.pack("base.tar.gz")
        with sqlite3.connect(self.root / "metadata/catalog.sqlite") as db:
            self.assertEqual(db.execute("SELECT state FROM jobs").fetchone()[0], "running")
            self.assertEqual(db.execute("SELECT count(*) FROM locks").fetchone()[0], 1)
        restore([base], self.work / "restored")
        with sqlite3.connect(self.work / "restored/metadata/catalog.sqlite") as db:
            self.assertEqual(db.execute("SELECT state FROM jobs").fetchone()[0], "pending")
            self.assertEqual(db.execute("SELECT count(*) FROM locks").fetchone()[0], 0)

    def test_corrupted_original_cannot_be_published(self):
        self.raw.write_bytes(b"tampered")
        with self.assertRaisesRegex(ValueError, "Catalog SHA256 mismatch"):
            self.pack("bad.tar.gz")
        self.assertFalse((self.work / "bad.tar.gz").exists())

    def test_missing_parent_and_nonempty_destination_are_rejected(self):
        base = self.pack("base.tar.gz"); delta = self.pack("delta.tar.gz", base)
        with self.assertRaisesRegex(ValueError, "parent"):
            restore([delta], self.work / "wrong-order")
        with self.assertRaisesRegex(ValueError, "empty"):
            restore([base], self.root)
        with self.assertRaises(FileExistsError):
            create(self.root, base, min_free_gb=0)

    def test_unsafe_members_and_symlinks_are_rejected(self):
        for name in ["../escape", "/tmp/escape", "metadata/../../escape", "windows\\escape"]:
            with self.assertRaises(ValueError): safe_path(self.root, name)
        (self.root / "link").symlink_to(self.work)
        with self.assertRaises(ValueError): safe_path(self.root, "link/escape")
        malicious = self.work / "malicious.tar.gz"
        with tarfile.open(malicious, "w:gz") as archive:
            content = json.dumps({"schema_version":"2.0", "files":{}, "included_files":[]}).encode()
            member = tarfile.TarInfo("SNAPSHOT.json"); member.size = len(content)
            archive.addfile(member, io.BytesIO(content))
            member = tarfile.TarInfo("../escape"); member.size = 1
            archive.addfile(member, io.BytesIO(b"x"))
        with self.assertRaises(ValueError): restore([malicious], self.work / "clean")
        self.assertFalse((self.work / "escape").exists())

    def test_legacy_git_backed_rows_are_excluded(self):
        with sqlite3.connect(self.root / "metadata/catalog.sqlite") as db:
            db.execute("INSERT INTO jobs VALUES('legacy','PROJECT_LEGACY','done')")
            db.execute("INSERT INTO downloads VALUES('legacy','legacy','outside', 'unused')")
            db.execute("INSERT INTO partitions VALUES('legacy','PROJECT_LEGACY','outside','unused',404)")
        manifest = read_manifest(self.pack("base.tar.gz"))
        self.assertEqual(manifest["download_count"], 1)
        self.assertEqual(manifest["partition_count"], 0)
        self.assertNotIn("outside", manifest["files"])

    def test_queue_identity_and_claim_work_without_dataframe_dependencies(self):
        from datalake.identity import Job
        from datalake.storage import Lake
        lake = Lake(self.work / "queue")
        job = Job("WB_ARCHIVE", "release", "raw", "https://example.org/source", priority=28)
        changed_priority = Job("WB_ARCHIVE", "release", "raw", "https://example.org/source", priority=10)
        self.assertEqual(job.id, changed_priority.id)
        self.assertEqual(lake.add([job]), 1)
        self.assertEqual(lake.add([changed_priority]), 0)
        lake.acquire()
        try:
            claimed = lake.claim()
            self.assertEqual(claimed.id, job.id)
            self.assertEqual(claimed.priority, 10)
            lake.finish(claimed, state="archived")
        finally:
            lake.release()


if __name__ == "__main__":
    unittest.main()
