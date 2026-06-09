"""Phase 5 — remove orphan name IDs (>255, no table reference)."""

from __future__ import annotations

from typing import Dict

from fontTools.ttLib import TTFont

import FontCore.core_console_styles as cs

console = cs.get_console()


def remove_orphans(
    font: TTFont,
    orphan_ids: Dict[int, str],
    *,
    skip_prompt: bool = False,
) -> int:
    """Remove orphan name records. Returns count removed."""
    if not orphan_ids:
        return 0

    removed = 0
    for nid in sorted(orphan_ids):
        string = font["name"].getDebugName(nid) or ""
        if not skip_prompt:
            if not cs.prompt_confirm(
                f"Remove orphan nameID {nid} ({string!r})?",
                default=False,
            ):
                continue

        font["name"].names = [r for r in font["name"].names if r.nameID != nid]
        cs.StatusIndicator("deleted").add_field("nameID", nid).add_values(
            old_value=string
        ).emit(console)
        removed += 1

    return removed
