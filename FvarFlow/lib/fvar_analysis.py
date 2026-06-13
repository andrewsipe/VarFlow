"""Pure fvar table analysis."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Set

from fontTools.ttLib import TTFont

from FontCore.core_namerecord_matcher import EID_UNICODE_BMP, LANG_EN_US_INT, PID_WIN
from FontCore.core_variable_font_detection import VariableFontMode, analyze_variable_font

from lib.fvar_models import (
    RESERVED_NAME_IDS,
    FvarAnalysis,
    FvarAxis,
    FvarFlag,
    FvarInstance,
    StatCoverageResult,
)

COORD_TOLERANCE = 0.001


def windows_en_string(font: TTFont, name_id: int) -> str:
    try:
        rec = font["name"].getName(name_id, PID_WIN, EID_UNICODE_BMP, LANG_EN_US_INT)
        if rec:
            return rec.toUnicode()
    except Exception:
        pass
    return ""


def _stat_axis_tags(font: TTFont) -> Set[str]:
    if "STAT" not in font:
        return set()
    stat = font["STAT"].table
    if not hasattr(stat, "DesignAxisRecord") or not stat.DesignAxisRecord:
        return set()
    return {ax.AxisTag for ax in stat.DesignAxisRecord.Axis}


def _axis_tag(stat, axis_index: int) -> str:
    try:
        return stat.DesignAxisRecord.Axis[axis_index].AxisTag
    except (AttributeError, IndexError, TypeError):
        return f"axis[{axis_index}]"


def _coord_matches(value: float, coord: float) -> bool:
    return abs(value - coord) <= COORD_TOLERANCE


def _build_stat_index(font: TTFont) -> Dict[str, List[dict]]:
    """Index STAT axis values by tag for coverage checks (formats 1–3 only)."""
    index: Dict[str, List[dict]] = {}
    if "STAT" not in font:
        return index
    stat = font["STAT"].table
    if not hasattr(stat, "AxisValueArray") or not stat.AxisValueArray:
        return index
    for av in stat.AxisValueArray.AxisValue or []:
        fmt = int(av.Format)
        if fmt == 4:
            continue
        tag = _axis_tag(stat, av.AxisIndex)
        entry: dict = {"format": fmt}
        if fmt == 1:
            entry["value"] = float(av.Value)
        elif fmt == 2:
            entry["range_min"] = float(av.RangeMinValue)
            entry["range_max"] = float(av.RangeMaxValue)
        elif fmt == 3:
            entry["value"] = float(av.Value)
        index.setdefault(tag, []).append(entry)
    return index


def _axis_covered(stat_index: Dict[str, List[dict]], tag: str, coord: float) -> bool:
    entries = stat_index.get(tag, [])
    if not entries:
        return False
    for entry in entries:
        fmt = entry["format"]
        if fmt == 1 or fmt == 3:
            if _coord_matches(entry["value"], coord):
                return True
        elif fmt == 2:
            if entry["range_min"] - COORD_TOLERANCE <= coord <= entry["range_max"] + COORD_TOLERANCE:
                return True
    return False


def _stat_coverage(
    stat_index: Dict[str, List[dict]],
    coordinates: Dict[str, float],
) -> StatCoverageResult:
    if not stat_index:
        return StatCoverageResult(covered=False, missing_axes=list(coordinates.keys()), partial=False)
    missing = [tag for tag, coord in coordinates.items() if not _axis_covered(stat_index, tag, coord)]
    if not missing:
        return StatCoverageResult(covered=True, missing_axes=[], partial=False)
    covered_any = len(missing) < len(coordinates)
    return StatCoverageResult(covered=False, missing_axes=missing, partial=covered_any)


def _shared_id_info(name_id: int) -> tuple[bool, str]:
    if name_id in RESERVED_NAME_IDS:
        return True, RESERVED_NAME_IDS[name_id]
    return False, ""


def _run_validation(analysis: FvarAnalysis, font: TTFont, stat_index: Dict[str, List[dict]]) -> None:
    stat_tags = _stat_axis_tags(font)

    for ax in analysis.axes:
        if not windows_en_string(font, ax.name_id):
            analysis.required_flags.append(
                FvarFlag(
                    severity="required",
                    flag_type="axis_broken_name_ref",
                    axis_tag=ax.tag,
                    detail=f"fvar axis '{ax.tag}' nameID {ax.name_id} has no Windows en-US string.",
                    guidance="Add a platformID=3, langID=0x0409 name record.",
                )
            )
        if not ax.in_stat and stat_tags:
            analysis.advisory_flags.append(
                FvarFlag(
                    severity="advisory",
                    flag_type="fvar_axis_not_in_stat",
                    axis_tag=ax.tag,
                    detail=f"fvar axis '{ax.tag}' is missing from STAT DesignAxisRecord.",
                    guidance="Add a DesignAxisRecord entry for this axis.",
                )
            )

    axis_ranges = {ax.tag: (ax.min_value, ax.max_value) for ax in analysis.axes}
    axis_coords: Dict[str, List[float]] = {ax.tag: [] for ax in analysis.axes}

    for inst in analysis.instances:
        if inst.name_id < 256 and inst.name_id not in RESERVED_NAME_IDS:
            analysis.required_flags.append(
                FvarFlag(
                    severity="required",
                    flag_type="invalid_name_id",
                    instance_index=inst.index,
                    detail=f"Instance {inst.index} uses invalid nameID {inst.name_id}.",
                    guidance="Assign a dedicated nameID ≥ 256 or a recognised reserved slot.",
                )
            )
        if not windows_en_string(font, inst.name_id):
            analysis.required_flags.append(
                FvarFlag(
                    severity="required",
                    flag_type="broken_name_ref",
                    instance_index=inst.index,
                    detail=f"Instance '{inst.name_en or inst.index}' nameID {inst.name_id} has no en-US string.",
                    guidance="Add a Windows en-US name record.",
                )
            )
        if inst.uses_shared_id:
            analysis.advisory_flags.append(
                FvarFlag(
                    severity="advisory",
                    flag_type="shared_reserved_id",
                    instance_index=inst.index,
                    detail=(
                        f"Instance uses nameID {inst.name_id} ({inst.shared_id_note}) — "
                        f"a reserved standard slot."
                    ),
                    guidance="Assign a dedicated nameID > 255 in the rebuild phase.",
                )
            )
        if inst.postscript_name_id and inst.postscript_name_id not in (0, 0xFFFF):
            if not windows_en_string(font, inst.postscript_name_id):
                analysis.required_flags.append(
                    FvarFlag(
                        severity="required",
                        flag_type="broken_postscript_ref",
                        instance_index=inst.index,
                        detail=f"PostScript nameID {inst.postscript_name_id} has no name record.",
                        guidance="Add a Windows en-US PostScript name record.",
                    )
                )

        for tag, coord in inst.coordinates.items():
            axis_coords.setdefault(tag, []).append(coord)
            lo, hi = axis_ranges.get(tag, (None, None))
            if lo is not None and hi is not None:
                if coord < lo - COORD_TOLERANCE or coord > hi + COORD_TOLERANCE:
                    analysis.required_flags.append(
                        FvarFlag(
                            severity="required",
                            flag_type="coordinate_out_of_range",
                            instance_index=inst.index,
                            axis_tag=tag,
                            detail=f"Instance coordinate {tag}={coord:g} outside fvar range [{lo:g}, {hi:g}].",
                            guidance="Correct instance coordinates to fall within axis min/max.",
                        )
                    )

    if stat_index:
        coverage_patterns: Counter = Counter()
        for inst in analysis.instances:
            if not inst.stat_coverage.covered:
                coverage_patterns[frozenset(inst.stat_coverage.missing_axes)] += 1
        for missing_axes_set, count in coverage_patterns.items():
            missing = ", ".join(sorted(missing_axes_set))
            analysis.advisory_flags.append(
                FvarFlag(
                    severity="advisory",
                    flag_type="instance_missing_stat_coverage",
                    detail=f"{count} instance(s) missing STAT coverage for: {missing}.",
                    guidance="Add STAT AxisValue entries for uncovered coordinates.",
                )
            )

    if analysis.axes and not analysis.instances:
        analysis.advisory_flags.append(
            FvarFlag(
                severity="advisory",
                flag_type="no_named_instances",
                detail="fvar has axes but no named instances.",
                guidance="Add named instances for static positions if needed.",
            )
        )

    for tag, coords in axis_coords.items():
        if coords and len(set(round(c, 4) for c in coords)) == 1:
            analysis.advisory_flags.append(
                FvarFlag(
                    severity="advisory",
                    flag_type="static_axis_in_instances",
                    axis_tag=tag,
                    detail=f"All instances share identical coordinate on '{tag}' ({coords[0]:g}).",
                    guidance="Axis may be non-functional or decorative.",
                )
            )


def analyze_fvar(path: Path, font: TTFont) -> FvarAnalysis:
    """Analyze fvar table; pure read-only."""
    vf = analyze_variable_font(font, mode=VariableFontMode.LENIENT)
    analysis = FvarAnalysis(path=path, is_variable=vf.is_technically_valid)

    if "fvar" not in font:
        return analysis

    analysis.has_fvar = True
    stat_tags = _stat_axis_tags(font)
    stat_index = _build_stat_index(font)

    for axis in font["fvar"].axes:
        analysis.axes.append(
            FvarAxis(
                tag=axis.axisTag,
                name_id=int(axis.axisNameID),
                name_en=windows_en_string(font, int(axis.axisNameID)),
                min_value=float(axis.minValue),
                default_value=float(axis.defaultValue),
                max_value=float(axis.maxValue),
                in_stat=axis.axisTag in stat_tags,
            )
        )

    for idx, inst in enumerate(font["fvar"].instances):
        name_id = int(inst.subfamilyNameID)
        ps_id = getattr(inst, "postscriptNameID", 0xFFFF)
        ps_id_int: Optional[int] = None
        if ps_id not in (0xFFFF, 0, None):
            ps_id_int = int(ps_id)
        shared, note = _shared_id_info(name_id)
        coords = {k: float(v) for k, v in inst.coordinates.items()}
        coverage = _stat_coverage(stat_index, coords)
        analysis.instances.append(
            FvarInstance(
                index=idx + 1,
                name_id=name_id,
                name_en=windows_en_string(font, name_id),
                postscript_name_id=ps_id_int,
                postscript_name=windows_en_string(font, ps_id_int) if ps_id_int else "",
                coordinates=coords,
                uses_shared_id=shared,
                shared_id_note=note,
                stat_coverage=coverage,
            )
        )

    _run_validation(analysis, font, stat_index)
    return analysis
