"""Phase 2 — remove all Mac (platform 1) name records."""

from __future__ import annotations

from typing import List

from fontTools.ttLib import TTFont

import FontCore.core_console_styles as cs

console = cs.get_console()


def prune_mac_records(font: TTFont, *, dry_run: bool = False) -> int:
    """Remove platformID==1 records. Returns count removed."""
    mac_records = [r for r in font["name"].names if r.platformID == 1]
    for rec in mac_records:
        try:
            text = rec.toUnicode()
        except Exception:
            text = "?"
        cs.StatusIndicator("deleted", dry_run=dry_run).add_field(
            "nameID", rec.nameID
        ).add_values(old_value=text).emit(console)

    if not dry_run:
        font["name"].names = [r for r in font["name"].names if r.platformID != 1]

    return len(mac_records)
