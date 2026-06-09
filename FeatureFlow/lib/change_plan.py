"""Pending change detection and diff table before apply."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import FontCore.core_console_styles as cs
from fontTools.ttLib import TTFont

from lib.models import FontAnalysis, ReflowPlan
from lib.reflow import build_reflow_plan, reflow_needed, reflow_skip_reason
from lib.relabel import preview_relabel_map_changes

console = cs.get_console()


@dataclass
class DiffRow:
    action: str
    feature: str
    table: str
    field: str
    name_id: str
    before: str
    after: str


@dataclass
class PendingChanges:
    """All known changes before mutation."""

    rows: List[DiffRow] = field(default_factory=list)
    plan_lines: List[str] = field(default_factory=list)
    will_prune_mac: bool = False
    will_reflow: bool = False
    will_relabel_interactive: bool = False
    reflow_plan: Optional[ReflowPlan] = None

    @property
    def has_mutations(self) -> bool:
        return len(self.rows) > 0 or self.will_relabel_interactive

    @property
    def has_deterministic_mutations(self) -> bool:
        return len(self.rows) > 0


def _windows_string(font: TTFont, name_id: int) -> str:
    try:
        rec = font["name"].getName(name_id, 3, 1, 0x0409)
        if rec:
            return rec.toUnicode()
    except Exception:
        pass
    return ""


def _mac_prune_rows(font: TTFont) -> List[DiffRow]:
    rows: List[DiffRow] = []
    for rec in font["name"].names:
        if rec.platformID != 1:
            continue
        try:
            text = rec.toUnicode()
        except Exception:
            text = "?"
        rows.append(
            DiffRow(
                action="Mac prune",
                feature="—",
                table="name",
                field="platform 1",
                name_id=str(rec.nameID),
                before=text,
                after="(removed)",
            )
        )
    return rows


def _reflow_rows(
    font: TTFont, analysis: FontAnalysis, plan: ReflowPlan
) -> List[DiffRow]:
    by_id: Dict[int, List] = {}
    for rec in analysis.ot_labels:
        by_id.setdefault(rec.name_id, []).append(rec)

    rows: List[DiffRow] = []
    for old_id, new_id in sorted(plan.remap.items()):
        if old_id == new_id:
            continue
        label = _windows_string(font, old_id) or "──"
        refs = by_id.get(old_id)
        if refs:
            for rec in refs:
                rows.append(
                    DiffRow(
                        action="Reflow",
                        feature=rec.feature_tag,
                        table=rec.table,
                        field=rec.field,
                        name_id=f"{old_id}→{new_id}",
                        before=label,
                        after=label,
                    )
                )
        else:
            rows.append(
                DiffRow(
                    action="Reflow",
                    feature="—",
                    table="—",
                    field="nameID",
                    name_id=f"{old_id}→{new_id}",
                    before=label,
                    after=label,
                )
            )
    return rows


def _orphan_rows(analysis: FontAnalysis, font: TTFont) -> List[DiffRow]:
    rows: List[DiffRow] = []
    for nid in sorted(analysis.orphan_ids):
        string = font["name"].getDebugName(nid) or "──"
        rows.append(
            DiffRow(
                action="Remove orphan",
                feature="—",
                table="name",
                field="orphan",
                name_id=str(nid),
                before=string,
                after="(removed)",
            )
        )
    return rows


def build_pending_changes(
    font: TTFont,
    analysis: FontAnalysis,
    *,
    prune_mac: bool,
    do_reflow: bool,
    relabel_map: Optional[Dict[str, str]],
    interactive_relabel: bool,
    remove_orphans: bool,
    dry_run: bool,
) -> PendingChanges:
    from lib.preflight import build_action_plan

    pending = PendingChanges()
    pending.will_relabel_interactive = interactive_relabel

    if prune_mac:
        pending.will_prune_mac = True
        pending.rows.extend(_mac_prune_rows(font))

    reflow_skip_text: Optional[str] = None
    reflow_plan: Optional[ReflowPlan] = None

    if do_reflow and analysis.ot_name_ids:
        exclude_mac = prune_mac
        if reflow_needed(font, analysis, exclude_mac=exclude_mac):
            reflow_plan = build_reflow_plan(font, analysis, exclude_mac=exclude_mac)
            pending.reflow_plan = reflow_plan
            if not reflow_plan.is_identity:
                pending.will_reflow = True
                pending.rows.extend(_reflow_rows(font, analysis, reflow_plan))
        else:
            reflow_skip_text = reflow_skip_reason(font, analysis, exclude_mac=exclude_mac)

    if relabel_map:
        pending.rows.extend(preview_relabel_map_changes(font, relabel_map))

    if remove_orphans and analysis.orphan_ids:
        pending.rows.extend(_orphan_rows(analysis, font))
    elif analysis.orphan_ids:
        for nid in sorted(analysis.orphan_ids):
            string = font["name"].getDebugName(nid) or "──"
            pending.rows.append(
                DiffRow(
                    action="Orphan (prompt)",
                    feature="—",
                    table="name",
                    field="orphan",
                    name_id=str(nid),
                    before=string,
                    after="(confirm each)",
                )
            )

    pending.plan_lines = build_action_plan(
        analysis,
        font,
        prune_mac=prune_mac,
        do_reflow=do_reflow,
        relabel_map=relabel_map is not None,
        interactive_relabel=interactive_relabel,
        remove_orphans=remove_orphans,
        dry_run=dry_run,
        has_mutations=pending.has_mutations,
        reflow_plan=reflow_plan,
        reflow_skip_reason_text=reflow_skip_text,
    )
    return pending


def emit_change_diff(pending: PendingChanges, *, path_name: str) -> None:
    """Print a table of concrete before/after changes."""
    if not pending.rows and not pending.will_relabel_interactive:
        return

    cs.fmt_header(f"Change diff — {path_name}", console=console)

    if pending.rows:
        table = cs.create_table(title="Pending changes", console=console)
        if table is not None:
            table.add_column("Action", style="bold")
            table.add_column("Feature", style="cyan")
            table.add_column("Table")
            table.add_column("Field")
            table.add_column("NameID", justify="right")
            table.add_column("Before")
            table.add_column("After")
            for row in pending.rows:
                table.add_row(
                    row.action,
                    row.feature,
                    row.table,
                    row.field,
                    row.name_id,
                    _truncate(row.before),
                    _truncate(row.after),
                )
            console.print(table)
        else:
            cs.emit(
                f"{'Action':<14} {'Feature':<8} {'NameID':<10} {'Before':<24} After",
                console=console,
            )
            cs.emit("─" * 90, console=console)
            for row in pending.rows:
                cs.emit(
                    f"{row.action:<14} {row.feature:<8} {row.name_id:<10} "
                    f"{row.before[:24]:<24} {row.after}",
                    console=console,
                )

    if pending.will_relabel_interactive:
        cs.emit(
            "  Interactive relabel (--relabel): edits are not listed until you enter them.",
            console=console,
        )
    cs.emit("", console=console)


def _truncate(text: str, limit: int = 40) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"
