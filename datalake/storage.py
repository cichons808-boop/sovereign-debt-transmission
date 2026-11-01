"""Content-addressed originals, resumable queue, and durable provenance in SQLite."""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import time
import threading
import fcntl
import uuid
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from .model import Job, compact

_DB_GUARD = threading.RLock()


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Lake:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self._locks = {}
        for name in ("raw/objects", "raw/tmp", "metadata", "silver", "gold", "reports", "logs"):
            (self.root / name).mkdir(parents=True, exist_ok=True)
        with self.db() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS jobs (
              id TEXT PRIMARY KEY, spec TEXT NOT NULL, source TEXT, dataset TEXT,
              priority INTEGER, state TEXT DEFAULT 'pending', attempts INTEGER DEFAULT 0,
              updated_at TEXT, error TEXT);
            CREATE INDEX IF NOT EXISTS ix_jobs_state ON jobs(state,priority);
            CREATE TABLE IF NOT EXISTS downloads (
              snapshot_id TEXT PRIMARY KEY, job_id TEXT, url TEXT, sha256 TEXT,
              bytes INTEGER, retrieved_at TEXT, source_last_modified TEXT,
              etag TEXT, content_type TEXT, path TEXT, http_status INTEGER);
            CREATE INDEX IF NOT EXISTS ix_downloads_job ON downloads(job_id,retrieved_at);
            CREATE TABLE IF NOT EXISTS partitions (
              id TEXT PRIMARY KEY, job_id TEXT, snapshot_id TEXT, path TEXT,
              source TEXT, dataset TEXT, rows INTEGER, missing_values INTEGER,
              duplicates INTEGER, countries INTEGER, series INTEGER,
              first_period TEXT, last_period TEXT, sha256 TEXT, created_at TEXT);
            CREATE TABLE IF NOT EXISTS events (
              at TEXT, job_id TEXT, event TEXT, detail TEXT);
            CREATE TABLE IF NOT EXISTS locks (name TEXT PRIMARY KEY, pid INTEGER, acquired_at TEXT);
            """)

    @contextmanager
    def db(self):
        # A single short-lived writer connection also works on managed filesystems
        # where mmap-backed WAL shared memory is unreliable. Network transfers and
        # Parquet work happen outside this lock. Never sync an active SQLite file.
        with _DB_GUARD:
            db = sqlite3.connect(self.root / "metadata/catalog.sqlite", timeout=60)
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA journal_mode=DELETE")
            db.execute("PRAGMA synchronous=FULL")
            db.execute("PRAGMA busy_timeout=60000")
            try:
                yield db
                db.commit()
            except BaseException:
                db.rollback(); raise
            finally:
                db.close()

    def add(self, jobs: list[Job]) -> int:
        for j in jobs:
            self.atomic_json(f"metadata/jobs/{j.id}.json", asdict(j))
        with self.db() as db:
            before = db.total_changes
            db.executemany("INSERT OR IGNORE INTO jobs(id,spec,source,dataset,priority,updated_at) VALUES(?,?,?,?,?,?)",
                           [(j.id, compact(asdict(j)), j.source, j.dataset, j.priority, utcnow()) for j in jobs])
            inserted=db.total_changes-before
            db.executemany("UPDATE jobs SET priority=MIN(priority,?) WHERE id=?",[(j.priority,j.id) for j in jobs])
            return inserted

    def claim(self, sources: list[str] | None = None, retry: bool = False) -> Job | None:
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            states = "('pending','failed')" if retry else "('pending')"
            sql = f"SELECT * FROM jobs WHERE state IN {states} AND attempts < 4"
            args: list = []
            if sources:
                sql += " AND source IN (" + ",".join("?" for _ in sources) + ")"; args += sources
            row = db.execute(sql + " ORDER BY priority,id LIMIT 1", args).fetchone()
            if not row:
                return None
            db.execute("UPDATE jobs SET state='running',attempts=attempts+1,updated_at=?,error=NULL WHERE id=?", (utcnow(), row["id"]))
            return Job(**{**json.loads(row["spec"]),"priority":row["priority"]})

    def finish(self, job: Job, error: str | None = None, state="done"):
        with self.db() as db:
            db.execute("UPDATE jobs SET state=?,error=?,updated_at=? WHERE id=?",
                       ("failed" if error else state, error, utcnow(), job.id))
        self.event(job.id, "failed" if error else "done", error or "")

    def event(self, job_id: str, event: str, detail: str):
        with self.db() as db:
            db.execute("INSERT INTO events VALUES(?,?,?,?)", (utcnow(), job_id, event, detail[:10000]))

    def latest_download(self, job: Job) -> dict | None:
        with self.db() as db:
            row = db.execute("SELECT * FROM downloads WHERE job_id=? ORDER BY retrieved_at DESC,snapshot_id DESC LIMIT 1", (job.id,)).fetchone()
        return dict(row) if row else None

    def register_download(self, row: dict):
        self.atomic_json(f"metadata/downloads/{row['snapshot_id']}.json", row)
        with self.db() as db:
            names = list(row)
            db.execute("INSERT OR IGNORE INTO downloads(" + ",".join(names) + ") VALUES(" + ",".join("?" for _ in names) + ")", tuple(row.values()))

    def register_partition(self, row: dict):
        self.atomic_json(f"metadata/partitions/{row['id']}.json", row)
        with self.db() as db:
            names = list(row)
            db.execute("INSERT OR REPLACE INTO partitions(" + ",".join(names) + ") VALUES(" + ",".join("?" for _ in names) + ")", tuple(row.values()))

    def acquire(self, name="runner"):
        handle = (self.root / "metadata" / f"{name}.lock").open("a+")
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            handle.close(); raise RuntimeError(f"Another {name} process holds the lake lock")
        self._locks[name] = handle
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM locks WHERE name=?", (name,))
            db.execute("INSERT INTO locks VALUES(?,?,?)", (name, os.getpid(), utcnow()))
            # Safe recovery only after taking the exclusive runner lock.
            if name == "runner":
                db.execute("UPDATE jobs SET state='pending' WHERE state='running'")

    def release(self, name="runner"):
        with self.db() as db:
            db.execute("DELETE FROM locks WHERE name=? AND pid=?", (name, os.getpid()))
        handle = self._locks.pop(name, None)
        if handle:
            fcntl.flock(handle, fcntl.LOCK_UN); handle.close()

    def usage(self) -> int:
        # Includes both immutable originals and normalized partitions.
        return sum(p.stat().st_size for p in self.root.rglob("*") if p.is_file())

    def check_space(self, max_gb: float, min_free_gb: float, additional: int = 0):
        unit = 1024**3
        if self.usage() + additional > max_gb * unit:
            raise OSError(f"Lake budget reached ({max_gb:g} GiB); increase --max-gb or move the lake")
        if shutil.disk_usage(self.root).free - additional < min_free_gb * unit:
            raise OSError(f"Free-space reserve reached ({min_free_gb:g} GiB)")

    def atomic_json(self, relative: str, obj: object):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + "." + uuid.uuid4().hex + ".part")
        tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2, default=str) + "\n")
        os.replace(tmp, path)

    def status(self) -> dict:
        with self.db() as db:
            jobs = [dict(r) for r in db.execute("SELECT source,dataset,state,COUNT(*) jobs FROM jobs GROUP BY source,dataset,state ORDER BY source,dataset,state")]
            summary = dict(db.execute("SELECT COUNT(*) partitions, COALESCE(SUM(rows),0) observations, COALESCE(SUM(missing_values),0) missing_values FROM partitions").fetchone())
            failures = [dict(r) for r in db.execute("SELECT source,dataset,error FROM jobs WHERE state='failed' LIMIT 100")]
        return {"generated_at": utcnow(), "root": str(self.root), "schema_version": "1.0", "bytes_on_disk": self.usage(), **summary, "jobs": jobs, "failures": failures}
