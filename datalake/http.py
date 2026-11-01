"""Polite, bounded downloads; exact response bytes and failed requests stay auditable."""
from __future__ import annotations

import hashlib
import os
import threading
import time
import uuid
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlparse

import requests

from .model import Job
from .storage import Lake, utcnow


class Downloader:
    def __init__(self, lake: Lake, max_gb=40.0, min_free_gb=8.0, max_file_gb=8.0, delay=0.5):
        self.lake, self.max_gb, self.min_free_gb = lake, max_gb, min_free_gb
        self.max_file_bytes = int(max_file_gb * 1024**3)
        self.delay = delay
        self._host_locks: dict[str, threading.Lock] = {}
        self._last: dict[str, float] = {}
        self._guard = threading.Lock()
        self._disk_guard = threading.Lock()
        self.local = threading.local()

    def session(self):
        if not hasattr(self.local, "session"):
            self.local.session = requests.Session()
            self.local.session.headers.update({"User-Agent": "SovereignDebtTransmission-ResearchData/0.1 (+https://github.com/cichons808-boop/sovereign-debt-transmission)", "Accept-Encoding": "identity"})
        return self.local.session

    def _pace(self, url: str):
        host = urlparse(url).netloc
        with self._guard:
            lock = self._host_locks.setdefault(host, threading.Lock())
        with lock:
            wait = self.delay - (time.monotonic() - self._last.get(host, 0))
            if wait > 0:
                time.sleep(wait)
            self._last[host] = time.monotonic()

    def fetch(self, job: Job, refresh=False) -> dict:
        old = self.lake.latest_download(job)
        if old and not refresh and (self.lake.root / old["path"]).is_file():
            return old
        headers = dict(job.options.get("headers", {}))
        # Content-encoding is disabled so hashes refer to the downloaded representation.
        if old and refresh:
            if old.get("etag"): headers["If-None-Match"] = old["etag"]
            if old.get("source_last_modified"): headers["If-Modified-Since"] = old["source_last_modified"]
        for attempt in range(4):
            self._pace(job.url)
            tmp = self.lake.root / "raw/tmp" / (uuid.uuid4().hex + ".part")
            try:
                self.lake.check_space(self.max_gb, self.min_free_gb)
                with self.session().get(job.url, headers=headers, stream=True, timeout=(20, 150)) as response:
                    if response.status_code == 304 and old:
                        if not (self.lake.root / old["path"]).is_file():
                            raise ValueError("Server returned 304 but cached object is absent")
                        return old
                    if response.status_code in {429, 500, 502, 503, 504}:
                        response.raise_for_status()
                    response.raise_for_status()
                    ct = response.headers.get("Content-Type", "").lower()
                    if "text/html" in ct and not job.options.get("allow_html"):
                        raise ValueError(f"HTML response instead of data ({response.url})")
                    length = int(response.headers.get("Content-Length", 0))
                    if length > self.max_file_bytes:
                        raise OSError(f"File exceeds per-file budget: {length} bytes")
                    sha = hashlib.sha256(); size = 0; checked = 0
                    with tmp.open("wb") as f:
                        for chunk in response.iter_content(1024 * 1024):
                            if not chunk: continue
                            size += len(chunk)
                            if size > self.max_file_bytes:
                                raise OSError("Download exceeds per-file budget")
                            if size - checked >= 64 * 1024**2:
                                with self._disk_guard:
                                    self.lake.check_space(self.max_gb, self.min_free_gb, len(chunk))
                                checked = size
                            sha.update(chunk); f.write(chunk)
                    if size == 0:
                        raise ValueError("Empty response body")
                    hexdigest = sha.hexdigest()
                    target = self.lake.root / "raw/objects" / hexdigest[:2] / hexdigest
                    target.parent.mkdir(exist_ok=True)
                    if target.exists(): tmp.unlink()
                    else: os.replace(tmp, target)
                    stamp = utcnow()
                    row = dict(snapshot_id=uuid.uuid4().hex, job_id=job.id, url=job.url,
                               sha256=hexdigest, bytes=size, retrieved_at=stamp,
                               source_last_modified=response.headers.get("Last-Modified"),
                               etag=response.headers.get("ETag"), content_type=ct,
                               path=str(target.relative_to(self.lake.root)), http_status=response.status_code)
                    self.lake.register_download(row)
                    self.lake.event(job.id, "downloaded", f"{size} bytes {hexdigest}")
                    return row
            except Exception as exc:
                tmp.unlink(missing_ok=True)
                retryable = isinstance(exc, (requests.Timeout, requests.ConnectionError)) or (
                    isinstance(exc, requests.HTTPError) and exc.response is not None and exc.response.status_code in {429, 500, 502, 503, 504})
                if not retryable or attempt == 3:
                    raise
                retry_after = getattr(getattr(exc, "response", None), "headers", {}).get("Retry-After", "")
                wait = min(45.0, 2.0 ** (attempt + 1))
                if str(retry_after).isdigit(): wait = min(45.0, float(retry_after))
                self.lake.event(job.id, "retry", f"attempt={attempt + 1} wait={wait} error={exc}")
                time.sleep(wait)
        raise AssertionError("unreachable")
