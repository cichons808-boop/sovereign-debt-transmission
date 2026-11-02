"""Portable full/incremental checkpoints using only the Python standard library.

No Drive credentials or deletion operations. Restore into a new directory only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import tarfile
import tempfile
from datetime import datetime, timezone
from contextlib import closing
from pathlib import Path, PurePosixPath


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def safe_path(root: Path, relative: str) -> Path:
    name = PurePosixPath(relative)
    if name.is_absolute() or ".." in name.parts or "\\" in relative or not name.parts:
        raise ValueError(f"Unsafe archive path: {relative}")
    target = root.joinpath(*name.parts)
    if not target.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"Path escapes root: {relative}")
    if any(p.is_symlink() for p in [target, *target.parents] if p.is_relative_to(root)):
        raise ValueError(f"Symlink in archive path: {relative}")
    return target


def read_manifest(archive: Path) -> dict:
    with tarfile.open(archive, "r|*") as stream:
        for member in stream:
            if member.name == "SNAPSHOT.json":
                if not member.isfile() or member.size > 64 * 1024**2:
                    raise ValueError("Invalid checkpoint manifest")
                return json.load(stream.extractfile(member))
    raise ValueError("Missing SNAPSHOT.json")


def inventory(manifest: dict) -> dict:
    if "files" in manifest:
        return manifest["files"]
    # Compatibility with the original full v1 checkpoint. It did not hash
    # auxiliary metadata, which is therefore included once in the first delta.
    return {r["path"]: {"sha256": r["sha256"]} for r in
            manifest.get("downloads", []) + manifest.get("partitions", [])}


def verify(root: Path, manifest: dict) -> dict:
    errors = []
    files = inventory(manifest)
    for relative, expected in files.items():
        path = safe_path(root, relative)
        if not path.is_file():
            errors.append({"path": relative, "error": "missing"})
        elif sha256(path) != expected["sha256"]:
            errors.append({"path": relative, "error": "SHA256 mismatch"})
    catalog = root / "metadata/catalog.sqlite"
    with closing(sqlite3.connect(catalog.as_uri() + "?mode=ro", uri=True)) as db:
        integrity = db.execute("PRAGMA integrity_check").fetchone()[0]
    if integrity != "ok":
        errors.append({"error": "catalog integrity", "detail": integrity})
    return {"checked_files": len(files), "catalog_integrity": integrity, "errors": errors,
            "scope": "File SHA256 and SQLite integrity; not Parquet schema or economic comparability"}


def create(root: Path, output: Path, *, base: Path | None = None, min_free_gb=8) -> dict:
    root, output = root.resolve(), output.resolve()
    if output.is_relative_to(root):
        raise ValueError("Write checkpoints outside the lake")
    if output.exists():
        raise FileExistsError(output)
    previous = inventory(read_manifest(base)) if base else {}
    parent_sha = sha256(base) if base else None
    output.parent.mkdir(parents=True, exist_ok=True)
    reserve = min_free_gb * 1024**3
    if shutil.disk_usage(output.parent).free < reserve:
        raise OSError("Free-space reserve reached")
    with tempfile.TemporaryDirectory(prefix="lake-checkpoint-", dir=output.parent) as temporary:
        stage = Path(temporary)
        catalog = stage / "metadata/catalog.sqlite"
        catalog.parent.mkdir()
        # Backup API obtains a transactionally consistent database without
        # touching the live runner, its lock or the live job states.
        with closing(sqlite3.connect((root / "metadata/catalog.sqlite").as_uri() + "?mode=ro", uri=True)) as source:
            with closing(sqlite3.connect(catalog)) as target:
                source.backup(target)
        with closing(sqlite3.connect(catalog)) as db:
            db.row_factory = sqlite3.Row
            db.execute("DELETE FROM partitions WHERE source LIKE 'PROJECT_LEGACY%'")
            db.execute("DELETE FROM downloads WHERE job_id IN (SELECT id FROM jobs WHERE source LIKE 'PROJECT_LEGACY%')")
            db.execute("DELETE FROM jobs WHERE source LIKE 'PROJECT_LEGACY%'")
            db.execute("DELETE FROM locks")
            db.execute("UPDATE jobs SET state='pending' WHERE state='running'")
            downloads = [dict(r) for r in db.execute("SELECT * FROM downloads")]
            partitions = [dict(r) for r in db.execute("SELECT * FROM partitions")]
            jobs = [dict(r) for r in db.execute("SELECT id FROM jobs")]
            db.commit()
        expected = {r["path"]: r["sha256"] for r in downloads + partitions}
        paths = set(expected)
        paths.update(f"metadata/downloads/{r['snapshot_id']}.json" for r in downloads)
        paths.update(f"metadata/partitions/{r['id']}.json" for r in partitions)
        paths.update(f"metadata/jobs/{r['id']}.json" for r in jobs)
        paths.update(str(p.relative_to(root)) for p in (root / "metadata").glob("*.json")
                     if not p.name.startswith(("legacy_", "recovery_")))
        for directory, pattern in [("metadata", "*.parquet"), ("gold", "**/*"), ("reports", "**/*")]:
            paths.update(str(p.relative_to(root)) for p in (root / directory).glob(pattern) if p.is_file())
        files = {}
        for relative in sorted(paths):
            path = safe_path(root, relative)
            if not path.is_file():
                if relative in expected:
                    raise FileNotFoundError(path)
                continue
            # Stage mutable sidecars, views and reports. Immutable originals
            # and Parquet partitions are never copied just for staging.
            if relative not in expected:
                staged = safe_path(stage, relative)
                staged.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, staged)
                path = staged
            checksum = sha256(path)
            if relative in expected and checksum != expected[relative]:
                raise ValueError(f"Catalog SHA256 mismatch: {relative}")
            files[relative] = {"sha256": checksum, "bytes": path.stat().st_size}
        files["metadata/catalog.sqlite"] = {"sha256": sha256(catalog), "bytes": catalog.stat().st_size}
        included = [p for p, value in files.items() if previous.get(p, {}).get("sha256") != value["sha256"]]
        # A delta always carries the catalog it describes, even when identical.
        if "metadata/catalog.sqlite" not in included:
            included.append("metadata/catalog.sqlite")
        required_bytes = sum(files[p]["bytes"] for p in included)
        if shutil.disk_usage(output.parent).free - required_bytes < reserve:
            raise OSError("Insufficient space for checkpoint and free-space reserve")
        manifest = {"created_at": datetime.now(timezone.utc).isoformat(), "schema_version": "2.0",
                    "kind": "incremental" if base else "full", "parent_archive_sha256": parent_sha,
                    "download_count": len(downloads), "partition_count": len(partitions),
                    "observation_rows": sum(r["rows"] for r in partitions),
                    "downloads": downloads, "partitions": partitions, "files": files,
                    "included_files": sorted(included), "deletions": [],
                    "snapshot_semantics": "SQLite backup; immutable sources; staged mutable metadata/views",
                    "excluded": "Code and original article files in Git; optional import-existing restores their bridge"}
        (stage / "SNAPSHOT.json").write_text(json.dumps(manifest, indent=2) + "\n")
        partial = stage / "archive.tar.gz"
        with tarfile.open(partial, "w:gz", compresslevel=6) as archive:
            archive.add(stage / "SNAPSHOT.json", arcname="SNAPSHOT.json")
            for relative in sorted(included):
                path = stage / relative
                if not path.is_file():
                    path = safe_path(root, relative)
                archive.add(path, arcname=relative, recursive=False)
        # Atomic publication with no replacement of an existing archive.
        os.link(partial, output)
    return {"path": str(output), "bytes": output.stat().st_size, "sha256": sha256(output),
            "kind": manifest["kind"], "parent_archive_sha256": parent_sha,
            "included_files": len(included), "inherited_files": len(files) - len(included),
            "download_count": len(downloads), "partition_count": len(partitions),
            "observation_rows": manifest["observation_rows"]}


def restore(archives: list[Path], destination: Path) -> dict:
    if not archives:
        raise ValueError("Provide at least one full checkpoint")
    destination = destination.resolve()
    if destination.exists() and any(destination.iterdir()):
        raise ValueError("Restore requires an empty destination")
    destination.mkdir(parents=True, exist_ok=True)
    previous = None
    for path in archives:
        manifest = read_manifest(path)
        if manifest.get("schema_version") not in {"1.0", "2.0"}:
            raise ValueError("Unknown checkpoint schema version")
        if manifest.get("parent_archive_sha256") != previous:
            raise ValueError("Wrong or missing parent checkpoint; provide full base then deltas in order")
        declared = set(manifest.get("included_files", inventory(manifest))) | {"SNAPSHOT.json"}
        seen = set()
        with tarfile.open(path) as archive:
            for member in archive:
                target = safe_path(destination, member.name)
                if not member.isfile() or member.name in seen:
                    raise ValueError(f"Unexpected archive member: {member.name}")
                # The original v1 full archive also contains unhashed sidecars.
                if manifest.get("schema_version") == "2.0" and member.name not in declared:
                    raise ValueError(f"Undeclared archive member: {member.name}")
                seen.add(member.name)
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.extractfile(member) as source, target.open("wb") as output:
                    shutil.copyfileobj(source, output, length=1024**2)
        if manifest.get("schema_version") == "2.0" and declared - seen:
            raise ValueError("Checkpoint is missing declared files")
        result = verify(destination, manifest)
        if result["errors"]:
            raise ValueError(f"Restored checkpoint failed verification: {result['errors'][:5]}")
        previous = sha256(path)
    return {"archives": len(archives), "latest_archive_sha256": previous, **result}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    pack = commands.add_parser("create")
    pack.add_argument("--root", type=Path, required=True)
    pack.add_argument("--output", type=Path, required=True)
    pack.add_argument("--base", type=Path)
    pack.add_argument("--min-free-gb", type=float, default=8)
    unpack = commands.add_parser("restore")
    unpack.add_argument("--destination", type=Path, required=True)
    unpack.add_argument("archives", nargs="+", type=Path)
    args = parser.parse_args()
    if args.command == "create":
        result = create(args.root, args.output, base=args.base, min_free_gb=args.min_free_gb)
    else:
        result = restore(args.archives, args.destination)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
