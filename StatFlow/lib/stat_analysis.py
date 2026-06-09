"""Pure STAT table analysis."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from fontTools.ttLib import TTFont

from FontCore.core_namerecord_matcher import EID_UNICODE_BMP, LANG_EN_US_INT, PID_WIN
from FontCore.core_variable_font_detection import VariableFontMode, analyze_variable_font

from lib.stat_axis_registry import convention_for_tag
from lib.stat_models import StatAnalysis, StatAxisRecord, StatAxisValue, StatFlag

COORD_TOLERANCE = 0.001
ELIDABLE_FLAG = 0x0001


def windows_en_string(font: TTFont, name_id: int) -> str:
    try:
        rec = font["name"].getName(name_id, PID_WIN, EID_UNICODE_BMP, LANG_EN_US_INT)
        if rec:
            return rec.toUnicode()
    except Exception:
        pass
    return ""


def _axis_tag(stat, axis_index: int) -> str:
    try:
        return stat.DesignAxisRecord.Axis[axis_index].AxisTag
    except (AttributeError, IndexError, TypeError):
        return f"axis[{axis_index}]"


def _fvar_axis_tags(font: TTFont) -> Set[str]:
    if "fvar" not in font:
        return set()
    return {ax.axisTag for ax in font["fvar"].axes}


def _fvar_name_ids(font: TTFont) -> Set[int]:
    ids: Set[int] = set()
    if "fvar" not in font:
        return ids
    for axis in font["fvar"].axes:
        ids.add(axis.axisNameID)
    for inst in font["fvar"].instances:
        ids.add(inst.subfamilyNameID)
        ps = getattr(inst, "postscriptNameID", 0xFFFF)
        if ps not in (0xFFFF, 0, None):
            ids.add(ps)
    return ids


def _parse_axis_values(stat, font: TTFont) -> List[StatAxisValue]:
    values: List[StatAxisValue] = []
    if not hasattr(stat, "AxisValueArray") or stat.AxisValueArray is None:
        return values
    axis_values = getattr(stat.AxisValueArray, "AxisValue", None) or []
    for av in axis_values:
        fmt = int(av.Format)
        name_id = int(av.ValueNameID)
        name_en = windows_en_string(font, name_id)
        flags = int(getattr(av, "Flags", 0) or 0)
        elidable = bool(flags & ELIDABLE_FLAG)

        if fmt == 4:
            pairs: Dict[str, float] = {}
            for rec in getattr(av, "AxisValueRecord", None) or []:
                tag = _axis_tag(stat, rec.AxisIndex)
                pairs[tag] = float(rec.Value)
            values.append(
                StatAxisValue(
                    axis_tag="",
                    format=fmt,
                    name_id=name_id,
                    name_en=name_en,
                    axis_value_pairs=pairs,
                    flags=flags,
                    elidable=elidable,
                )
            )
            continue

        axis_tag = _axis_tag(stat, av.AxisIndex)
        entry = StatAxisValue(
            axis_tag=axis_tag,
            format=fmt,
            name_id=name_id,
            name_en=name_en,
            flags=flags,
            elidable=elidable,
        )
        if fmt == 1:
            entry.value = float(av.Value)
        elif fmt == 2:
            entry.range_min = float(av.RangeMinValue)
            entry.range_max = float(av.RangeMaxValue)
            entry.nominal_value = float(av.NominalValue)
        elif fmt == 3:
            entry.value = float(av.Value)
            entry.linked_value = float(av.LinkedValue)
        values.append(entry)
    return values


def _collect_stat_name_ids(
    axes: List[StatAxisRecord],
    axis_values: List[StatAxisValue],
    elidable_fallback: Optional[int],
) -> List[int]:
    ids: Set[int] = set()
    for ax in axes:
        ids.add(ax.name_id)
    for av in axis_values:
        ids.add(av.name_id)
    if elidable_fallback:
        ids.add(elidable_fallback)
    return sorted(ids)


def _format3_missing_linked(av: StatAxisValue) -> bool:
    if av.linked_value is None:
        return True
    if av.axis_tag == "ital":
        return False
    if av.value is not None and av.value != 0.0 and av.linked_value == 0.0:
        return True
    return False


def _axis_value_range(av: StatAxisValue) -> Tuple[Optional[float], Optional[float]]:
    if av.format == 2 and av.range_min is not None and av.range_max is not None:
        return av.range_min, av.range_max
    if av.value is not None:
        return av.value, av.value
    if av.format == 4 and av.axis_value_pairs:
        vals = list(av.axis_value_pairs.values())
        return min(vals), max(vals)
    return None, None


def _run_validation(
    analysis: StatAnalysis,
    font: TTFont,
    fvar_tags: Set[str],
    stat_tags: Set[str],
) -> None:
    fvar_name_ids = _fvar_name_ids(font)

    for ax in analysis.axes:
        if ax.name_id < 256:
            analysis.required_flags.append(
                StatFlag(
                    severity="required",
                    flag_type="nameID_below_256",
                    axis_tag=ax.tag,
                    name_id=ax.name_id,
                    detail=f"Axis {ax.tag} uses nameID {ax.name_id} (< 256).",
                    guidance="Assign a dedicated nameID ≥ 256 for STAT axis names.",
                )
            )
        if not windows_en_string(font, ax.name_id):
            analysis.required_flags.append(
                StatFlag(
                    severity="required",
                    flag_type="broken_name_ref",
                    axis_tag=ax.tag,
                    name_id=ax.name_id,
                    detail=f"Axis {ax.tag} nameID {ax.name_id} has no Windows en-US string.",
                    guidance="Add a platformID=3, langID=0x0409 name record.",
                )
            )

    for av in analysis.axis_values:
        if av.name_id < 256:
            analysis.required_flags.append(
                StatFlag(
                    severity="required",
                    flag_type="nameID_below_256",
                    axis_tag=av.axis_tag or None,
                    name_id=av.name_id,
                    detail=f"Axis value nameID {av.name_id} (< 256) on format {av.format}.",
                    guidance="Assign a dedicated nameID ≥ 256 for STAT axis values.",
                )
            )
        if not windows_en_string(font, av.name_id):
            analysis.required_flags.append(
                StatFlag(
                    severity="required",
                    flag_type="broken_name_ref",
                    axis_tag=av.axis_tag or None,
                    name_id=av.name_id,
                    detail=f"Axis value nameID {av.name_id} has no Windows en-US string.",
                    guidance="Add a platformID=3, langID=0x0409 name record.",
                )
            )
        if av.format == 3 and _format3_missing_linked(av):
            analysis.required_flags.append(
                StatFlag(
                    severity="required",
                    flag_type="missing_linked_value",
                    axis_tag=av.axis_tag,
                    name_id=av.name_id,
                    detail=(
                        f"Format 3 entry '{av.name_en or av.name_id}' on {av.axis_tag} "
                        f"has no linked value."
                    ),
                    guidance=(
                        "Format 3 requires a LinkedValue pointing to the counterpart "
                        "coordinate in the companion style."
                    ),
                )
            )
        if av.format == 4:
            unknown = [t for t in av.axis_value_pairs if t not in stat_tags]
            if unknown:
                analysis.required_flags.append(
                    StatFlag(
                        severity="required",
                        flag_type="compound_unknown_axis",
                        name_id=av.name_id,
                        detail=f"Format 4 entry references unknown axes: {', '.join(unknown)}.",
                        guidance="Compound entries must only reference axes in DesignAxisRecord.",
                    )
                )

        conv = convention_for_tag(av.axis_tag) if av.axis_tag else None
        if conv:
            lo, hi = _axis_value_range(av)
            if lo is not None and hi is not None:
                if lo < conv.expected_min - COORD_TOLERANCE or hi > conv.expected_max + COORD_TOLERANCE:
                    analysis.advisory_flags.append(
                        StatFlag(
                            severity="advisory",
                            flag_type="nonstandard_axis_range",
                            axis_tag=av.axis_tag,
                            name_id=av.name_id,
                            detail=(
                                f"{conv.full_name} value range {lo:g}–{hi:g} is outside "
                                f"conventional {conv.expected_min:g}–{conv.expected_max:g}."
                            ),
                            guidance="No action required — may be intentional.",
                        )
                    )
            if av.format == 1 and 3 in conv.typical_formats:
                analysis.advisory_flags.append(
                    StatFlag(
                        severity="advisory",
                        flag_type="format1_where_format3_expected",
                        axis_tag=av.axis_tag,
                        name_id=av.name_id,
                        detail=f"Format 1 on {av.axis_tag} where Format 3 is conventional.",
                        guidance=(
                            "A linked value could be added to connect this entry to its "
                            "counterpart in the companion style (Roman/Italic or Upright/Condensed)."
                        ),
                    )
                )

    stat_axis_set = {ax.tag for ax in analysis.axes}
    if "ital" in stat_axis_set and "slnt" in stat_axis_set:
        analysis.advisory_flags.append(
            StatFlag(
                severity="advisory",
                flag_type="ital_slnt_coexistence",
                detail="Both ital and slnt axes are present in STAT.",
                guidance="Prefer one italic mechanism; having both can confuse renderers.",
            )
        )

    for tag in stat_axis_set - fvar_tags:
        if fvar_tags:
            analysis.advisory_flags.append(
                StatFlag(
                    severity="advisory",
                    flag_type="stat_axis_not_in_fvar",
                    axis_tag=tag,
                    detail=f"STAT axis '{tag}' has no matching fvar axis.",
                    guidance="Align STAT DesignAxisRecord with fvar axes.",
                )
            )
    for tag in fvar_tags - stat_axis_set:
        analysis.advisory_flags.append(
            StatFlag(
                severity="advisory",
                flag_type="fvar_axis_not_in_stat",
                axis_tag=tag,
                detail=f"fvar axis '{tag}' is missing from STAT DesignAxisRecord.",
                guidance="Add a DesignAxisRecord entry for this axis.",
            )
        )

    if analysis.has_stat and not analysis.axis_values:
        analysis.advisory_flags.append(
            StatFlag(
                severity="advisory",
                flag_type="empty_axis_value_array",
                detail="STAT AxisValueArray is empty.",
                guidance="Add axis value entries for named positions on each axis.",
            )
        )

    orderings = [ax.ordering for ax in analysis.axes]
    if orderings and (len(set(orderings)) != len(orderings) or orderings != sorted(orderings)):
        analysis.advisory_flags.append(
            StatFlag(
                severity="advisory",
                flag_type="irregular_axis_ordering",
                detail=f"Axis ordering values are non-sequential or duplicate: {orderings}.",
                guidance="Use unique, sequential AxisOrdering values starting at 0.",
            )
        )

    if analysis.stat_version is not None and analysis.stat_version < 0x00010002:
        if not analysis.elidable_fallback_name_id:
            analysis.advisory_flags.append(
                StatFlag(
                    severity="advisory",
                    flag_type="missing_elidable_fallback",
                    detail="No ElidedFallbackNameID (STAT version < 1.2 or field absent).",
                    guidance="Upgrade STAT to 1.2+ and set ElidedFallbackNameID.",
                )
            )
    elif not analysis.elidable_fallback_name_id:
        analysis.advisory_flags.append(
            StatFlag(
                severity="advisory",
                flag_type="missing_elidable_fallback",
                detail="ElidedFallbackNameID is absent.",
                guidance="Set ElidedFallbackNameID to the elided style label (e.g. Regular).",
            )
        )

    shared: Set[int] = set(analysis.stat_name_ids) & fvar_name_ids
    for nid in sorted(shared):
        if nid in {ax.name_id for ax in analysis.axes}:
            continue
        analysis.advisory_flags.append(
            StatFlag(
                severity="advisory",
                flag_type="shared_name_id",
                name_id=nid,
                detail=f"nameID {nid} is used by both STAT and fvar.",
                guidance="Full cross-table analysis is NameFlow's job; consider dedicated IDs.",
            )
        )


def analyze_stat(path: Path, font: TTFont) -> StatAnalysis:
    """Analyze STAT table; pure read-only."""
    vf = analyze_variable_font(font, mode=VariableFontMode.LENIENT)
    analysis = StatAnalysis(
        path=path,
        is_variable=vf.is_technically_valid,
        mac_record_count=sum(1 for r in font["name"].names if r.platformID == 1),
    )

    if "STAT" not in font:
        return analysis

    analysis.has_stat = True
    stat = font["STAT"].table
    analysis.stat_version = int(getattr(stat, "Version", 0) or 0)
    analysis.has_varstore = bool(getattr(stat, "VarStore", None))

    if analysis.has_varstore:
        analysis.advisory_flags.append(
            StatFlag(
                severity="advisory",
                flag_type="stat_varstore_present",
                detail="STAT contains an ItemVariationStore (variable axis values).",
                guidance="This toolchain does not currently modify VarStore-backed STAT values.",
            )
        )

    if not vf.has_fvar:
        analysis.advisory_flags.append(
            StatFlag(
                severity="advisory",
                flag_type="stat_without_fvar",
                detail="STAT table present but font has no fvar table.",
                guidance="Unusual configuration — variable fonts normally require fvar.",
            )
        )

    if hasattr(stat, "DesignAxisRecord") and stat.DesignAxisRecord:
        for ax in stat.DesignAxisRecord.Axis:
            analysis.axes.append(
                StatAxisRecord(
                    tag=ax.AxisTag,
                    name_id=int(ax.AxisNameID),
                    name_en=windows_en_string(font, int(ax.AxisNameID)),
                    ordering=int(getattr(ax, "AxisOrdering", 0) or 0),
                )
            )

    analysis.axis_values = _parse_axis_values(stat, font)
    stat_tags = {ax.tag for ax in analysis.axes}

    efb = getattr(stat, "ElidedFallbackNameID", None)
    if efb:
        analysis.elidable_fallback_name_id = int(efb)
        analysis.elidable_fallback_label = windows_en_string(font, int(efb))

    analysis.stat_name_ids = _collect_stat_name_ids(
        analysis.axes,
        analysis.axis_values,
        analysis.elidable_fallback_name_id,
    )

    fvar_tags = _fvar_axis_tags(font)
    _run_validation(analysis, font, fvar_tags, stat_tags)
    return analysis
