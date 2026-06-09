"""Phase 6 — output path resolution."""

from __future__ import annotations

from pathlib import Path
from typing import Optional


def resolve_output_path(
    source: Path,
    *,
    output_dir: Optional[Path] = None,
    suffix: Optional[str] = None,
) -> Path:
    """Compute destination path for a saved font."""
    name = source.name
    if suffix:
        stem = source.stem
        ext = source.suffix
        name = f"{stem}{suffix}{ext}"

    if output_dir is not None:
        return (output_dir / name).resolve()

    if suffix:
        return source.parent / name
    return source.resolve()
