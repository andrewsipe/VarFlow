"""Phase 3 — reflow OT feature label nameIDs to a contiguous block."""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Set, Tuple

from fontTools.ttLib import TTFont

import FontCore.core_console_styles as cs
from FontCore.core_namerecord_matcher import EID_UNICODE_BMP, LANG_EN_US_INT, PID_WIN
from FontCore.core_ot_label_scanner import OTLabelRecord

from lib.models import FontAnalysis, ReflowPlan

console = cs.get_console()

_RE_STYLESET = re.compile(r"^ss\d{2}$")
_RE_CHARVAR = re.compile(r"^cv\d{2}$")

PID_MAC = 1


def _high_name_ids(font: TTFont, *, exclude_mac: bool) -> Set[int]:
    """nameIDs >= 256, optionally ignoring Mac-only platform records."""
    ids: Set[int] = set()
    for r in font["name"].names:
        if r.nameID < 256:
            continue
        if exclude_mac and r.platformID == PID_MAC:
            continue
        ids.add(r.nameID)
    return ids


def _reflow_block_start(font: TTFont, ot_name_ids: Set[int], *, exclude_mac: bool) -> int:
    """First free slot above non-OT nameIDs (and optionally Mac records slated for prune)."""
    ot_set = ot_name_ids
    eligible = [
        r.nameID
        for r in font["name"].names
        if r.nameID >= 256
        and r.nameID not in ot_set
        and not (exclude_mac and r.platformID == PID_MAC)
    ]
    return max(max(eligible, default=0) + 1, 256)


def reflow_needed(
    font: TTFont, analysis: FontAnalysis, *, exclude_mac: bool = False
) -> bool:
    """
    True when reflow would fix gaps, tail placement, or IDs mixed with non-OT records.

    Skips fonts like contiguous 256–258 when nothing else occupies ≥256 above them.
    """
    ot_ids = sorted(analysis.ot_name_ids)
    if not ot_ids:
        return False

    if analysis.contiguity_gaps:
        return True

    protected = set(analysis.protected_ids.keys())
    if protected & set(ot_ids):
        return True

    all_high = _high_name_ids(font, exclude_mac=exclude_mac)
    ot_set = set(ot_ids)
    min_ot, max_ot = ot_ids[0], ot_ids[-1]

    for nid in range(min_ot, max_ot + 1):
        if nid not in ot_set and nid in all_high:
            return True

    ideal_start = _reflow_block_start(font, ot_set, exclude_mac=exclude_mac)

    if min_ot >= ideal_start and len(ot_set) == max_ot - min_ot + 1:
        return False

    return True


def reflow_skip_reason(
    font: TTFont, analysis: FontAnalysis, *, exclude_mac: bool = False
) -> str:
    """Short explanation for why reflow is skipped."""
    ot_ids = sorted(analysis.ot_name_ids)
    if not ot_ids:
        return "no labeled OT nameIDs"
    if not reflow_needed(font, analysis, exclude_mac=exclude_mac):
        lo, hi = ot_ids[0], ot_ids[-1]
        if len(ot_ids) == hi - lo + 1:
            return f"IDs {lo}–{hi} already contiguous at end of name table"
        return "already in acceptable layout"
    return ""


def build_reflow_plan(
    font: TTFont, analysis: FontAnalysis, *, exclude_mac: bool = False
) -> ReflowPlan:
    """Compute old_id -> new_id remap for OT feature IDs."""
    ot_ids = sorted(analysis.ot_name_ids)
    ot_set = set(ot_ids)
    block_start = _reflow_block_start(font, ot_set, exclude_mac=exclude_mac)

    remap: Dict[int, int] = {}
    cursor = block_start
    for old_id in ot_ids:
        remap[old_id] = cursor
        cursor += 1

    return ReflowPlan(remap=remap, block_start=block_start, ot_ids_before=ot_ids)


def verify_remap_safe(remap: Dict[int, int], protected_ids: Set[int]) -> List[str]:
    """Return error messages if new IDs collide with protected IDs."""
    errors: List[str] = []
    new_ids = set(remap.values())
    overlap = new_ids & protected_ids
    for nid in sorted(overlap):
        errors.append(f"Reflow target nameID {nid} collides with protected STAT/fvar ID")
    return errors


def emit_remap_table(plan: ReflowPlan, *, dry_run: bool = False) -> None:
    cs.fmt_header("OT feature nameID remap", console=console)
    table = cs.create_table(title="Remap preview" if dry_run else "Remap", console=console)
    if table is not None:
        table.add_column("Old ID", justify="right")
        table.add_column("New ID", justify="right")
        for old_id, new_id in sorted(plan.remap.items()):
            table.add_row(str(old_id), str(new_id))
        console.print(table)
    else:
        for old_id, new_id in sorted(plan.remap.items()):
            cs.emit(f"  {old_id} -> {new_id}", console=console)


def _windows_string(font: TTFont, name_id: int, ot_labels: List[OTLabelRecord]) -> str:
    try:
        rec = font["name"].getName(name_id, PID_WIN, EID_UNICODE_BMP, LANG_EN_US_INT)
        if rec:
            return rec.toUnicode()
    except Exception:
        pass
    for rec in ot_labels:
        if rec.name_id == name_id and rec.string:
            return rec.string
    return ""


def _count_non_mac_locales(font: TTFont, name_id: int) -> int:
    strings: Set[str] = set()
    for r in font["name"].names:
        if r.nameID == name_id and r.platformID != PID_MAC:
            try:
                strings.add(r.toUnicode())
            except Exception:
                strings.add("")
    return len(strings)


def _remove_name_id(font: TTFont, name_id: int) -> None:
    font["name"].names = [r for r in font["name"].names if r.nameID != name_id]


def _set_windows_name(font: TTFont, name_id: int, string: str) -> None:
    font["name"].setName(string, name_id, PID_WIN, EID_UNICODE_BMP, LANG_EN_US_INT)


def apply_reflow(
    font: TTFont,
    analysis: FontAnalysis,
    plan: ReflowPlan,
    *,
    dry_run: bool = False,
) -> int:
    """Rewrite name table and FeatureParams. Returns count of IDs remapped."""
    if plan.is_identity or not plan.remap:
        return 0

    if dry_run:
        emit_remap_table(plan, dry_run=True)
        return len(plan.remap)

    strings_by_old: Dict[int, str] = {}
    for old_id in plan.remap:
        strings_by_old[old_id] = _windows_string(font, old_id, analysis.ot_labels)
        locale_count = _count_non_mac_locales(font, old_id)
        if locale_count > 1:
            cs.StatusIndicator("warning").add_message(
                f"nameID {old_id} has {locale_count} non-Mac locale variants; only en-US carried forward"
            ).emit(console)

    for old_id in plan.remap:
        _remove_name_id(font, old_id)

    for old_id, new_id in sorted(plan.remap.items()):
        text = strings_by_old.get(old_id, "")
        if text:
            _set_windows_name(font, new_id, text)
        if old_id != new_id:
            cs.StatusIndicator("updated").add_field("nameID", new_id).add_values(
                old_value=str(old_id), new_value=str(new_id)
            ).emit(console)

    # Walk mirrors FontCore/core_ot_label_scanner.py FeatureParams fields.
    _apply_remap_to_feature_params(font, plan.remap)
    return len(plan.remap)


def _remap_value(nid: int, remap: Dict[int, int]) -> int:
    return remap.get(nid, nid)


def _apply_remap_to_feature_params(font: TTFont, remap: Dict[int, int]) -> None:
    for table_tag in ("GSUB", "GPOS"):
        if table_tag not in font:
            continue
        try:
            feature_list = font[table_tag].table.FeatureList
            if feature_list is None:
                continue
            for rec in feature_list.FeatureRecord:
                _remap_feature_record(rec, table_tag, remap)
        except Exception as e:
            cs.StatusIndicator("warning").add_message(
                f"Could not update {table_tag} FeatureParams: {e}"
            ).emit(console)


def _remap_feature_record(feature_record, table_tag: str, remap: Dict[int, int]) -> None:
    tag = feature_record.FeatureTag
    params = getattr(feature_record.Feature, "FeatureParams", None)
    if params is None:
        return

    try:
        if _RE_STYLESET.match(tag):
            _remap_field(params, "FeatureNameID", tag, table_tag, remap)
            _remap_field(params, "UINameID", tag, table_tag, remap)

        elif _RE_CHARVAR.match(tag):
            _remap_field(params, "LabelNameID", tag, table_tag, remap)
            _remap_field(params, "TooltipTextNameID", tag, table_tag, remap)
            _remap_field(params, "SampleTextNameID", tag, table_tag, remap)
            n = getattr(params, "NumNamedParameters", 0) or 0
            first = getattr(params, "FirstParamUILabelNameID", None)
            if first is not None and n > 0:
                new_first = _remap_value(int(first), remap)
                if new_first != first:
                    params.FirstParamUILabelNameID = new_first
                    cs.StatusIndicator("updated").add_field("feature", tag).add_field(
                        "field", "FirstParamUILabelNameID"
                    ).add_values(old_value=str(first), new_value=str(new_first)).emit(console)

        elif tag == "size":
            _remap_field(params, "SubFamilyID", tag, table_tag, remap)
    except Exception as e:
        cs.StatusIndicator("warning").add_message(
            f"Skipping remap for {table_tag}/{tag}: {e}"
        ).emit(console)


def _remap_field(params, field: str, feature_tag: str, table_tag: str, remap: Dict[int, int]) -> None:
    nid = getattr(params, field, None)
    if nid is None or nid == 0:
        return
    old = int(nid)
    new = _remap_value(old, remap)
    if new != old:
        setattr(params, field, new)
        cs.StatusIndicator("updated").add_field("feature", feature_tag).add_field(
            "table", table_tag
        ).add_field("field", field).add_values(old_value=str(old), new_value=str(new)).emit(
            console
        )
