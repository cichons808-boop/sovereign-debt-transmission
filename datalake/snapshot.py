"""Full checkpoint CLI bridge; original article files and code stay in Git."""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from .checkpoint import create

if TYPE_CHECKING:
    from .storage import Lake


def snapshot(lake: Lake, output: Path) -> dict:
    result = create(lake.root, output)
    lake.atomic_json('reports/latest_checkpoint.json', result)
    return result
