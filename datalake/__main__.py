"""Command line entry point: python -m datalake --root /data/lake ..."""
from __future__ import annotations

import argparse
import json
import signal
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .http import Downloader
from .normalize import normalize
from .providers import PLANNERS
from .extra_sources import PLANNERS as EXTRA_PLANNERS, ADAPTERS as EXTRA_ADAPTERS
from .normalize import ADAPTERS
from . import legacy  # Registers the read-only replication-data adapter.
from .storage import Lake, utcnow

PLANNERS.update(EXTRA_PLANNERS)
ADAPTERS.update(EXTRA_ADAPTERS)


def run(lake, dl, args):
    lake.acquire()
    (lake.root / "metadata/STOP").unlink(missing_ok=True)
    stop = threading.Event(); started = time.monotonic(); counter = 0; guard = threading.Lock()
    previous = {}
    for sig in (signal.SIGINT, signal.SIGTERM):
        previous[sig] = signal.signal(sig, lambda *_: stop.set())
    def worker():
        nonlocal counter
        while not stop.is_set():
            if (lake.root / "metadata/STOP").exists(): return
            with guard:
                if time.monotonic() - started >= args.hours * 3600 or (args.max_jobs and counter >= args.max_jobs):
                    return
                job = lake.claim(args.sources, args.retry_failed)
                if not job: return
                counter += 1
            try:
                print(json.dumps({"at": utcnow(), "event": "start", "source": job.source, "dataset": job.dataset, "job": job.id}), flush=True)
                raw = dl.fetch(job, refresh=args.refresh)
                result = normalize(lake, job, raw,max_gb=args.max_gb,min_free_gb=args.min_free_gb)
                lake.finish(job,state="empty" if result.get("empty") else ("archived" if result.get("raw_only") else "done"))
                print(json.dumps({"at": utcnow(), "event": "done", "source": job.source, "dataset": job.dataset,
                                  "rows": result.get("rows", 0), "bytes": raw["bytes"], "job": job.id}), flush=True)
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
                lake.finish(job, error)
                if job.source=="BIS" and job.adapter=="sdmx_csv" and any(t in str(exc) for t in ["CSV row","native period"]):
                    from dataclasses import replace
                    fallback=replace(job,adapter="bis_wide",url=job.url.replace("_csv_flat.zip","_csv_col.zip"))
                    lake.add([fallback])
                    with lake.db() as db:db.execute("UPDATE jobs SET state='superseded' WHERE id=?",(job.id,))
                print(json.dumps({"at": utcnow(), "event": "failed", "source": job.source,
                                  "dataset": job.dataset, "error": error, "job": job.id}), flush=True)
                if isinstance(exc, OSError) and any(s in str(exc) for s in ["reserve", "budget", "No space"]): stop.set()
    try:
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futures = [ex.submit(worker) for _ in range(args.workers)]
            for future in futures: future.result()
    finally:
        lake.release()
        for sig, handler in previous.items(): signal.signal(sig, handler)
        status = lake.status(); lake.atomic_json("reports/status.json", status)
        print(json.dumps({k: v for k, v in status.items() if k not in {"jobs", "failures"}}), flush=True)


def main(argv=None):
    p = argparse.ArgumentParser(description="Auditable monetary/fiscal research lake")
    p.add_argument("--root", default="lake", help="Data location, outside Git; movable without rewriting catalog paths")
    p.add_argument("--max-gb", type=float, default=40, help="Total raw+normalized storage budget, GiB")
    p.add_argument("--min-free-gb", type=float, default=8, help="Leave this much filesystem space free")
    sub = p.add_subparsers(dest="command", required=True)
    plan = sub.add_parser("plan")
    plan.add_argument("--providers", nargs="+", choices=list(PLANNERS), default=list(PLANNERS))
    plan.add_argument("--profile", choices=["smoke", "broad", "full"], default="broad")
    plan.add_argument("--wb-sources", nargs="+", help="Optional exact World Bank source IDs")
    plan.add_argument("--imf-flows", nargs="+", help="Optional exact IMF flow IDs")
    r = sub.add_parser("run")
    r.add_argument("--workers", type=int, choices=range(1,9), default=3)
    r.add_argument("--hours", type=float, default=6)
    r.add_argument("--max-jobs", type=int, default=0)
    r.add_argument("--sources", nargs="+")
    r.add_argument("--retry-failed", action="store_true")
    r.add_argument("--refresh", action="store_true", help="Revalidate claimed requests; existing done jobs remain done")
    sub.add_parser("status")
    sub.add_parser("stop", help="Stop the current runner after active jobs finish")
    sub.add_parser("report")
    sub.add_parser("build-panels")
    sub.add_parser("research-readiness",help="Build observed refinancing ratios and monetary-event coverage")
    sync=sub.add_parser("cloud-copy",help="Copy to an already authorized Google Drive/S3 rclone remote and verify")
    sync.add_argument("--remote",required=True)
    sync.add_argument("--dry-run",action="store_true")
    save=sub.add_parser("snapshot",help="Create a consistent compressed data checkpoint, excluding code/frozen Git files")
    save.add_argument("--output",required=True)
    verify = sub.add_parser("verify")
    verify.add_argument("--hashes", action="store_true", help="Rehash all raw and Parquet objects")
    retry = sub.add_parser("retry")
    retry.add_argument("--sources", nargs="+")
    retry.add_argument("--include-done", action="store_true", help="Explicitly request a new retrieval vintage")
    import_old = sub.add_parser("import-existing")
    import_old.add_argument("--repository", default=".")
    a = p.parse_args(argv)
    lake = Lake(a.root); dl = Downloader(lake, a.max_gb, a.min_free_gb)
    if a.command == "plan":
        total = 0
        for provider in a.providers:
            kwargs = {"profile": a.profile}
            if provider == "WORLDBANK" and a.wb_sources: kwargs["source_ids"] = a.wb_sources
            if provider == "IMF" and a.imf_flows: kwargs["flow_ids"] = a.imf_flows
            try:
                jobs = PLANNERS[provider](lake, dl, **kwargs)
                added = lake.add(jobs); total += added
                print(json.dumps({"provider": provider, "planned": len(jobs), "added": added}), flush=True)
            except Exception as exc:
                lake.event("plan", "failed", f"{provider}: {type(exc).__name__}: {exc}")
                print(json.dumps({"provider": provider, "error": f"{type(exc).__name__}: {exc}"}), flush=True)
        print(json.dumps({"new_jobs": total}), flush=True)
    elif a.command == "run": run(lake, dl, a)
    elif a.command == "status": print(json.dumps(lake.status(), indent=2))
    elif a.command == "stop": (lake.root / "metadata/STOP").touch(); print("Stop requested")
    elif a.command == "report":
        from .research import report
        print(json.dumps(report(lake), indent=2))
    elif a.command == "build-panels":
        from .research import build_panels
        print(json.dumps(build_panels(lake), indent=2))
    elif a.command == "cloud-copy":
        from .remote import cloud_copy
        print(json.dumps(cloud_copy(lake,a.remote,a.dry_run),indent=2))
    elif a.command == "research-readiness":
        from .research import research_readiness
        print(json.dumps(research_readiness(lake),indent=2))
    elif a.command == "snapshot":
        from .snapshot import snapshot
        print(json.dumps(snapshot(lake,Path(a.output)),indent=2))
    elif a.command == "verify":
        from .research import verify
        result = verify(lake, a.hashes); print(json.dumps(result, indent=2))
        if result["errors"]: raise SystemExit(1)
    elif a.command == "retry":
        lake.acquire()
        try:
            with lake.db() as db:
                query = "UPDATE jobs SET state='pending',attempts=0,error=NULL WHERE state IN " + ("('failed','done')" if a.include_done else "('failed')")
                params = []
                if a.sources:
                    query += " AND source IN (" + ",".join("?" for _ in a.sources) + ")"; params = a.sources
                cursor = db.execute(query, params); print(json.dumps({"reset_jobs": cursor.rowcount}))
        finally: lake.release()
    elif a.command == "import-existing":
        from .legacy import import_existing
        print(json.dumps(import_existing(lake, Path(a.repository).resolve()), indent=2))


if __name__ == "__main__": main()
