"""Stable request identities; usable during recovery without dataframe packages."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field


def compact(obj: object) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


def digest(obj: object) -> str:
    return hashlib.sha256(compact(obj).encode()).hexdigest()


@dataclass(frozen=True)
class Job:
    source: str
    dataset: str
    adapter: str
    url: str
    options: dict = field(default_factory=dict)
    priority: int = 100

    @property
    def id(self) -> str:
        return digest({k: v for k, v in asdict(self).items() if k != "priority"})[:32]
