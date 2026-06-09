"""Phase 1 — analyze fonts and build reports."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Set

from fontTools.ttLib import TTFont

import FontCore.core_console_styles as cs
from FontCore.core_nameid_allocator import audit_nameids
from FontCore.core_ot_label_scanner import OTLabelRecord, scan_ot_label_nameids

from lib.feature_inventory import scan_label_capable_features
from lib.models import FontAnalysis, ReportRow, RowStatus

console = cs.get_console()
ORPHAN_PREFIX = "name table only"


def _windows_string(font: TTFont, name_id: int) -> str:
    try:
        rec = font["name"].getName(name_id, 3, 1, 0x0409)
        if rec:
            return rec.toUnicode()
    except Exception:
        pass
    return ""


def analyze_font(path: Path, font: TTFont) -> FontAnalysis:
    """Run full Phase 1 analysis on a loaded font."""
    analysis = FontAnalysis(path=path, font=font)
    analysis.is_variable = "fvar" in font
    analysis.ot_labels = scan_ot_label_nameids(font)
    analysis.used_nameids = audit_nameids(font, analysis.ot_labels)
    analysis.ot_name_ids = {rec.name_id for rec in analysis.ot_labels}

    for nid, desc in analysis.used_nameids.items():
        if nid in analysis.ot_name_ids:
            continue
        if desc.startswith(ORPHAN_PREFIX):
            analysis.orphan_ids[nid] = desc
        elif nid >= 256:
            analysis.protected_ids[nid] = desc

    analysis.mac_record_count = sum(1 for r in font["name"].names if r.platformID == 1)

    _run_validation(analysis)
    _build_report_rows(analysis)
    _append_unlabeled_feature_rows(analysis)
    return analysis


def _run_validation(analysis: FontAnalysis) -> None:
    font = analysis.font
    assert font is not None

    checked_below_256: Set[int] = set()
    checked_protected: Set[int] = set()
    checked_broken: Set[int] = set()

    for rec in analysis.ot_labels:
        if rec.name_id < 256 and rec.name_id not in checked_below_256:
            checked_below_256.add(rec.name_id)
            analysis.blocking_errors.append(
                f"nameID {rec.name_id} < 256 ({rec.table} {rec.feature_tag} {rec.field})"
            )

        if (
            rec.name_id in analysis.protected_ids
            and rec.name_id not in checked_protected
        ):
            checked_protected.add(rec.name_id)
            analysis.blocking_errors.append(
                f"OT feature nameID {rec.name_id} collides with protected ID: "
                f"{analysis.protected_ids[rec.name_id]}"
            )

        if rec.name_id in checked_broken:
            continue
        win = _windows_string(font, rec.name_id)
        if not win and not rec.string:
            checked_broken.add(rec.name_id)
            analysis.blocking_errors.append(
                f"BROKEN REF: nameID {rec.name_id} ({rec.feature_tag} {rec.field}) has no en-US string"
            )

    ot_unique = sorted(analysis.ot_name_ids)
    if ot_unique:
        gaps: List[tuple] = []
        for i in range(len(ot_unique) - 1):
            if ot_unique[i + 1] - ot_unique[i] > 1:
                gaps.append((ot_unique[i] + 1, ot_unique[i + 1] - 1))
        analysis.contiguity_gaps = gaps
        if gaps:
            gap_str = ", ".join(f"{lo}–{hi}" for lo, hi in gaps)
            analysis.warnings.append(
                f"OT feature nameIDs are not contiguous (gaps: {gap_str}); reflow will compact them"
            )


def _primary_label_field(feature_tag: str) -> str:
    if feature_tag.startswith("ss"):
        return "UINameID"
    if feature_tag.startswith("cv"):
        return "LabelNameID"
    if feature_tag == "size":
        return "SubFamilyID"
    return "—"


def _append_unlabeled_feature_rows(analysis: FontAnalysis) -> None:
    """Add inventory rows for ss/cv/size features with no label nameIDs in FeatureParams."""
    font = analysis.font
    assert font is not None

    labeled_keys = {(rec.table, rec.feature_tag) for rec in analysis.ot_labels}
    inventory = scan_label_capable_features(font)

    for presence in inventory:
        key = (presence.table, presence.feature_tag)
        if key in labeled_keys:
            continue
        if presence.label_name_ids:
            # FeatureParams reference nameIDs but scanner found nothing — surface as broken inventory
            for nid in presence.label_name_ids:
                if nid not in analysis.ot_name_ids:
                    analysis.report_rows.append(
                        ReportRow(
                            feature=presence.feature_tag,
                            table=presence.table,
                            field=_primary_label_field(presence.feature_tag),
                            name_id=nid,
                            string_en="──",
                            status=RowStatus.BROKEN_REF,
                            source="FeatureParams (not resolved in name table)",
                        )
                    )
            continue

        field_desc = (
            "(no FeatureParams)"
            if not presence.has_feature_params
            else f"{_primary_label_field(presence.feature_tag)} (missing)"
        )
        analysis.report_rows.append(
            ReportRow(
                feature=presence.feature_tag,
                table=presence.table,
                field=field_desc,
                name_id=0,
                string_en="──",
                status=RowStatus.NO_LABEL,
                source="feature present, no label nameID",
            )
        )
        analysis.unlabeled_feature_count += 1

    inventory_keys = {(p.table, p.feature_tag) for p in inventory}
    analysis.labeled_feature_count = len(labeled_keys & inventory_keys)

    analysis.report_rows.sort(key=lambda r: (r.table, r.feature, r.field))


def _build_report_rows(analysis: FontAnalysis) -> None:
    font = analysis.font
    assert font is not None

    for rec in analysis.ot_labels:
        status = RowStatus.OK
        if rec.name_id < 256:
            status = RowStatus.ERROR
        elif rec.name_id in analysis.protected_ids:
            status = RowStatus.ERROR
        elif not _windows_string(font, rec.name_id) and not rec.string:
            status = RowStatus.BROKEN_REF

        analysis.report_rows.append(
            ReportRow(
                feature=rec.feature_tag,
                table=rec.table,
                field=rec.field,
                name_id=rec.name_id,
                string_en=rec.string or _windows_string(font, rec.name_id) or "──",
                status=status,
                source=analysis.used_nameids.get(rec.name_id, ""),
            )
        )

    for nid, desc in sorted(analysis.orphan_ids.items()):
        string = font["name"].getDebugName(nid) or ""
        analysis.report_rows.append(
            ReportRow(
                feature="──",
                table="──",
                field="name only (orphan)",
                name_id=nid,
                string_en=string or "──",
                status=RowStatus.ORPHAN,
                source=desc,
            )
        )


def emit_report(analysis: FontAnalysis, *, title: Optional[str] = None) -> None:
    """Print Phase 1 report to console."""
    path = analysis.path
    header = title or f"OT feature labels — {path.name}"
    cs.fmt_header(header, console=console)
    if analysis.is_variable:
        cs.emit(f"  Variable font (fvar present)", console=console)

    if analysis.blocking_errors:
        cs.emit("", console=console)
        cs.StatusIndicator("error").add_message("Blocking errors").emit(console)
        for msg in analysis.blocking_errors:
            cs.emit(f"  • {msg}", console=console)

    if analysis.warnings:
        cs.emit("", console=console)
        cs.StatusIndicator("warning").add_message("Warnings").emit(console)
        for msg in analysis.warnings:
            cs.emit(f"  • {msg}", console=console)

    table = cs.create_table(title="Feature label inventory", console=console)
    if table is not None:
        table.add_column("Feature", style="cyan")
        table.add_column("Table")
        table.add_column("Field")
        table.add_column("NameID", justify="right")
        table.add_column("String (en)")
        table.add_column("Status")
        for row in analysis.report_rows:
            name_id_col = "──" if row.name_id <= 0 else str(row.name_id)
            table.add_row(
                row.feature,
                row.table,
                row.field,
                name_id_col,
                row.string_en[:60] + ("…" if len(row.string_en) > 60 else ""),
                row.status.value,
            )
        console.print(table)
    else:
        cs.emit(f"{'Feature':<8} {'Table':<6} {'Field':<28} {'NameID':>6}  {'Status':<12}  String", console=console)
        cs.emit("─" * 90, console=console)
        for row in analysis.report_rows:
            nid_s = "──" if row.name_id <= 0 else str(row.name_id)
            cs.emit(
                f"{row.feature:<8} {row.table:<6} {row.field:<28} {nid_s:>6}  "
                f"{row.status.value:<12}  {row.string_en}",
                console=console,
            )

    if analysis.protected_ids:
        cs.emit("", console=console)
        cs.StatusIndicator("info").add_message("Protected IDs (skipped by reflow)").emit(console)
        for nid, desc in sorted(analysis.protected_ids.items()):
            cs.emit(f"  {nid}: {desc}", console=console)

    inventory_total = analysis.labeled_feature_count + analysis.unlabeled_feature_count
    if inventory_total:
        cs.emit(
            f"Label-capable features (ss/cv/size): {inventory_total} total — "
            f"{analysis.labeled_feature_count} labeled, {analysis.unlabeled_feature_count} without labels",
            console=console,
        )
        if analysis.unlabeled_feature_count:
            cs.emit(
                "  Unlabeled features are listed for inspection only; "
                "reflow and relabel require existing nameIDs (not created by this tool).",
                console=console,
            )

    ot_ids = sorted(analysis.ot_name_ids)
    if ot_ids:
        cs.emit("", console=console)
        cs.emit(
            f"OT feature ID range: {ot_ids[0]}–{ot_ids[-1]} ({len(ot_ids)} unique IDs)",
            console=console,
        )
        if analysis.contiguity_gaps:
            gap_str = ", ".join(f"{lo}–{hi}" for lo, hi in analysis.contiguity_gaps)
            cs.emit(f"Gaps before reflow: {gap_str}", console=console)

    cs.emit(f"Mac name records to prune: {analysis.mac_record_count}", console=console)


def confirm_contiguity_if_needed(analysis: FontAnalysis, *, auto_yes: bool) -> bool:
    """Return False if user aborts due to contiguity warning."""
    if not analysis.contiguity_gaps or auto_yes:
        return True
    return cs.prompt_confirm(
        "OT feature nameIDs have gaps. Proceed with reflow?",
        default=False,
    )
