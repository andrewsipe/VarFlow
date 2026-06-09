"""Preflight summary before mutating fonts."""

from __future__ import annotations

from typing import List, Optional

import FontCore.core_console_styles as cs
from fontTools.ttLib import TTFont

from lib.models import FontAnalysis, ReflowPlan

console = cs.get_console()


def build_action_plan(
    analysis: FontAnalysis,
    font: TTFont,
    *,
    prune_mac: bool,
    do_reflow: bool,
    relabel_map: bool,
    interactive_relabel: bool,
    remove_orphans: bool,
    dry_run: bool,
    has_mutations: bool = True,
    reflow_plan: Optional[ReflowPlan] = None,
    reflow_skip_reason_text: Optional[str] = None,
) -> List[str]:
    """Human-readable list of planned steps."""
    lines: List[str] = []
    prefix = "[dry-run] " if dry_run else ""

    if prune_mac:
        n = analysis.mac_record_count
        lines.append(f"{prefix}Mac prune: remove {n} platform-1 name record(s)")
    else:
        lines.append(f"{prefix}Mac prune: skipped (--no-prune-mac)")

    if not do_reflow:
        lines.append(f"{prefix}Reflow: skipped (--no-reflow)")
    elif not analysis.ot_name_ids:
        lines.append(f"{prefix}Reflow: skipped (no labeled OT feature nameIDs)")
    elif reflow_skip_reason_text:
        lines.append(f"{prefix}Reflow: not needed ({reflow_skip_reason_text})")
    elif reflow_plan is not None:
        moves = sum(1 for o, n in reflow_plan.remap.items() if o != n)
        if moves:
            sample = ", ".join(
                f"{o}→{n}" for o, n in sorted(reflow_plan.remap.items())[:5]
            )
            if len(reflow_plan.remap) > 5:
                sample += ", …"
            lines.append(f"{prefix}Reflow: remap {moves} nameID(s) ({sample})")
        else:
            lines.append(f"{prefix}Reflow: no ID changes")
    else:
        lines.append(f"{prefix}Reflow: skipped")

    if relabel_map:
        lines.append(f"{prefix}Relabel: apply --relabel-map")
    elif interactive_relabel:
        lines.append(f"{prefix}Relabel: interactive (--relabel)")
    else:
        lines.append(f"{prefix}Relabel: skipped (use --relabel or --relabel-map)")

    if analysis.orphan_ids:
        if remove_orphans:
            lines.append(f"{prefix}Orphans: remove {len(analysis.orphan_ids)} without prompt")
        else:
            lines.append(
                f"{prefix}Orphans: prompt for {len(analysis.orphan_ids)} "
                "(or --remove-orphans / --yes)"
            )
    else:
        lines.append(f"{prefix}Orphans: none")

    if dry_run:
        lines.append(f"{prefix}Save: none (dry-run)")
    elif not has_mutations:
        lines.append(f"{prefix}Save: skipped (no changes)")
    else:
        lines.append(f"{prefix}Save: write font (confirm unless --yes)")

    return lines


def emit_preflight(
    analysis: FontAnalysis,
    font: TTFont,
    lines: List[str],
    *,
    path_name: str,
) -> None:
    cs.fmt_header(f"Planned changes — {path_name}", console=console)
    for line in lines:
        cs.emit(f"  • {line}", console=console)
    cs.emit("", console=console)


def confirm_preflight(lines: List[str], *, auto_yes: bool) -> bool:
    if auto_yes:
        return True
    cs.emit(
        "Use --dry-run to preview without writing, or --yes to skip this prompt.",
        console=console,
    )
    return cs.prompt_confirm(
        "Apply the planned changes to this font?",
        action_prompt="Proceed?",
        default=False,
    )
