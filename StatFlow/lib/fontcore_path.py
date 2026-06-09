"""Resolve FontCore via the VarFlow suite root (walk up until ``FontCore/`` exists)."""

from __future__ import annotations

import sys
from pathlib import Path

_done: Path | None = None


def ensure_fontcore_on_path(start: Path | None = None) -> Path:
    """Walk upward until ``FontCore/`` exists (suite root); insert parent on sys.path once."""
    global _done
    origin = Path(start).resolve() if start is not None else Path(__file__).resolve().parent
    repo = origin
    while not (repo / "FontCore").exists() and repo.parent != repo:
        repo = repo.parent

    if _done == repo:
        return repo

    if str(repo) not in sys.path:
        sys.path.insert(0, str(repo))

    _done = repo
    return repo
