"""Consistent, portable checkpoints; code and frozen Git files stay in Git."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import tarfile
import tempfile
from pathlib import Path

from .storage import Lake, utcnow


def snapshot(lake:Lake, output:Path) -> dict:
    output=output.resolve()
    if output.is_relative_to(lake.root):raise ValueError("Write the archive outside the lake")
    output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="lake-snapshot-") as scratch:
        stage=Path(scratch); catalog=stage/"catalog.sqlite"
        with lake.db() as db:
            dest=sqlite3.connect(catalog)
            try:db.backup(dest)
            finally:dest.close()
        db=sqlite3.connect(catalog);db.row_factory=sqlite3.Row
        # Frozen article bytes are already durably versioned in the original
        # repository. Reattach with import-existing after restoring a checkpoint.
        db.execute("DELETE FROM partitions WHERE source LIKE 'PROJECT_LEGACY%'")
        db.execute("DELETE FROM downloads WHERE job_id IN (SELECT id FROM jobs WHERE source LIKE 'PROJECT_LEGACY%')")
        db.execute("DELETE FROM jobs WHERE source LIKE 'PROJECT_LEGACY%'")
        db.execute("DELETE FROM locks")
        db.execute("UPDATE jobs SET state='pending' WHERE state='running'")
        db.commit()
        downloads=[dict(r) for r in db.execute("SELECT * FROM downloads")]
        parts=[dict(r) for r in db.execute("SELECT * FROM partitions")]
        jobs=[dict(r) for r in db.execute("SELECT * FROM jobs")]
        db.close()
        paths={r["path"] for r in downloads+parts}
        for row in downloads:paths.add(f"metadata/downloads/{row['snapshot_id']}.json")
        for row in parts:paths.add(f"metadata/partitions/{row['id']}.json")
        for row in jobs:paths.add(f"metadata/jobs/{row['id']}.json")
        paths.update(str(p.relative_to(lake.root)) for p in (lake.root/"metadata").glob("*.json") if not p.name.startswith(("legacy_","recovery_")))
        manifest={"created_at":utcnow(),"schema_version":"1.0","download_count":len(downloads),"partition_count":len(parts),
                  "observation_rows":sum(r["rows"] for r in parts),"snapshot_semantics":"Consistent SQLite backup; immutable objects only",
                  "code_repository":"https://github.com/cichons808-boop/sovereign-debt-transmission",
                  "excluded":"Frozen original article files and code already in Git; optional import-existing rebuilds that bridge",
                  "pending_jobs_resume":True,"downloads":downloads,"partitions":parts}
        (stage/"SNAPSHOT.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n")
        tmp=output.with_suffix(output.suffix+".part")
        with tarfile.open(tmp,"w:gz",compresslevel=6) as archive:
            archive.add(catalog,arcname="metadata/catalog.sqlite")
            archive.add(stage/"SNAPSHOT.json",arcname="SNAPSHOT.json")
            for relative in sorted(paths):
                p=(lake.root/relative).resolve()
                if not p.is_relative_to(lake.root):raise ValueError("Catalog path escapes the data root")
                if p.is_file():archive.add(p,arcname=relative)
                elif relative in {r["path"] for r in downloads+parts}:raise FileNotFoundError(p)
        tmp.replace(output)
    with output.open("rb") as f:sha=hashlib.file_digest(f,"sha256").hexdigest()
    result={"path":str(output),"bytes":output.stat().st_size,"sha256":sha,
            "download_count":len(downloads),"partition_count":len(parts),"observation_rows":sum(r["rows"] for r in parts)}
    lake.atomic_json("reports/latest_checkpoint.json",result)
    return result
