"""Verified one-way cloud copies through an already authorized rclone remote.

No credentials are read from another app, committed, printed, or requested by
this module. Google Drive authorization in ChatGPT is not an rclone token.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import subprocess
from pathlib import Path

from .storage import Lake, utcnow


def checkpoint(lake: Lake) -> Path:
    """Snapshot SQLite with its backup API, never copy a live database file."""
    stamp=utcnow().replace(":","").replace("+0000","Z")
    target=lake.root/"metadata/checkpoints"/f"catalog-{stamp}.sqlite"
    target.parent.mkdir(exist_ok=True)
    with lake.db() as source:
        dest=sqlite3.connect(target)
        try:source.backup(dest)
        finally:dest.close()
    return target


def cloud_copy(lake: Lake, remote: str, dry_run=False) -> dict:
    binary=shutil.which("rclone")
    if not binary:raise RuntimeError("rclone is not installed; no cloud copy has been made")
    if ":" not in remote or remote.startswith(("http:","https:")):
        raise ValueError("Use a configured rclone remote such as gdrive:MonetaryFiscalLake")
    # Only this named, user-authorized destination is queried. Never enumerate
    # unrelated drives or reuse app/session credentials.
    snapshot=checkpoint(lake)
    include=["raw/objects/**","silver/**","gold/**","metadata/jobs/**","metadata/downloads/**",
             "metadata/partitions/**","metadata/checkpoints/**","metadata/*.json","metadata/*.parquet","reports/**"]
    filters=[]
    for pattern in ["*.part","metadata/quarantine*","metadata/recovery*"]:
        filters.extend(["--exclude",pattern])
    for pattern in include:filters.extend(["--include",pattern])
    args=[binary,"copy",str(lake.root),remote,"--checksum","--transfers","2","--checkers","4",
          "--max-transfer","600G","--cutoff-mode","soft","--retries","3","--low-level-retries","5",*filters]
    if dry_run:args.append("--dry-run")
    subprocess.run(args,check=True)
    if not dry_run:
        subprocess.run([binary,"check",str(lake.root),remote,"--one-way","--checkers","4",*filters],check=True)
    result={"at":utcnow(),"destination":remote,"dry_run":dry_run,"verified":not dry_run,
            "local_files_deleted":0,"catalog_snapshot":str(snapshot.relative_to(lake.root)),
            "note":"Copy/check compares provider-supported checksums; originals retain SHA256 provenance. No remote or local deletion."}
    lake.atomic_json("reports/cloud_copy.json",result)
    return result
