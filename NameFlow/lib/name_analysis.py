"""Cross-table nameID attribution and validation."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Set

from fontTools.ttLib import TTFont

from FontCore.core_namerecord_matcher import EID_UNICODE_BMP, LANG_EN_US_INT, PID_WIN
from FontCore.core_ot_label_scanner import scan_ot_label_nameids
from FontCore.core_variable_font_detection import VariableFontMode, analyze_variable_font

from lib.name_models import (
    NameAnalysis,
    NameFlag,
    NameIDSource,
    NameRecord,
    NameRecordStatus,
    SOURCE_LABELS,
)

STAT_SOURCES = {
    NameIDSource.STAT_AXIS,
    NameIDSource.STAT_VALUE,
    NameIDSource.STAT_ELIDABLE,
}
FVAR_SOURCES = {
    NameIDSource.FVAR_AXIS,
    NameIDSource.FVAR_INSTANCE,
    NameIDSource.FVAR_PS,
}


def windows_en_string(font: TTFont, name_id: int) -> str:
    try:
        rec = font["name"].getName(name_id, PID_WIN, EID_UNICODE_BMP, LANG_EN_US_INT)
        if rec:
            return rec.toUnicode()
    except Exception:
        pass
    return ""


def _platform_labels(font: TTFont, name_id: int) -> tuple[List[str], bool, bool]:
    platforms: List[str] = []
    has_win = False
    has_mac = False
    for nr in font["name"].names:
        if nr.nameID != name_id:
            continue
        if nr.platformID == PID_WIN:
            has_win = True
            if "windows" not in platforms:
                platforms.append("windows")
        elif nr.platformID == 1:
            has_mac = True
            if "mac" not in platforms:
                platforms.append("mac")
    return platforms, has_win, has_mac


def _collect_references(font: TTFont) -> Dict[int, Set[NameIDSource]]:
    refs: Dict[int, Set[NameIDSource]] = defaultdict(set)

    for nr in font["name"].names:
        if nr.nameID <= 25:
            refs[nr.nameID].add(NameIDSource.STANDARD)

    for rec in scan_ot_label_nameids(font):
        if rec.name_id >= 0:
            refs[rec.name_id].add(NameIDSource.OT_FEATURE)

    if "STAT" in font:
        stat = font["STAT"].table
        if hasattr(stat, "DesignAxisRecord") and stat.DesignAxisRecord:
            for ax in stat.DesignAxisRecord.Axis:
                refs[int(ax.AxisNameID)].add(NameIDSource.STAT_AXIS)
        if hasattr(stat, "AxisValueArray") and stat.AxisValueArray:
            for av in stat.AxisValueArray.AxisValue or []:
                refs[int(av.ValueNameID)].add(NameIDSource.STAT_VALUE)
        efb = getattr(stat, "ElidedFallbackNameID", None)
        if efb:
            refs[int(efb)].add(NameIDSource.STAT_ELIDABLE)

    if "fvar" in font:
        for axis in font["fvar"].axes:
            refs[int(axis.axisNameID)].add(NameIDSource.FVAR_AXIS)
        for inst in font["fvar"].instances:
            refs[int(inst.subfamilyNameID)].add(NameIDSource.FVAR_INSTANCE)
            ps = getattr(inst, "postscriptNameID", 0xFFFF)
            if ps not in (0xFFFF, 0, None):
                refs[int(ps)].add(NameIDSource.FVAR_PS)

    return refs


def _source_tables(sources: Set[NameIDSource]) -> str:
    tables: List[str] = []
    if NameIDSource.OT_FEATURE in sources:
        tables.append("GSUB/GPOS")
    if sources & STAT_SOURCES:
        tables.append("STAT")
    if sources & FVAR_SOURCES:
        tables.append("fvar")
    if NameIDSource.STANDARD in sources and len(sources) == 1:
        tables.append("standard")
    return ", ".join(tables) if tables else "──"


def _primary_source(sources: List[NameIDSource]) -> str:
    if not sources:
        return NameIDSource.ORPHAN.value
    if len(sources) == 1:
        return SOURCE_LABELS[sources[0]]
    return "shared"


def _shared_note(name_id: int, sources: Set[NameIDSource], font: TTFont) -> str:
    parts = []
    label = windows_en_string(font, name_id) or font["name"].getDebugName(name_id) or ""
    for src in sorted(sources, key=lambda s: s.value):
        parts.append(SOURCE_LABELS[src])
    return f'nameID {name_id} ("{label}") used by: {", ".join(parts)}'


def _classify_status(
    name_id: int,
    sources: Set[NameIDSource],
    has_windows: bool,
    has_mac: bool,
    in_name_table: bool,
) -> NameRecordStatus:
    if not in_name_table:
        return NameRecordStatus.MISSING
    if 26 <= name_id <= 255:
        return NameRecordStatus.BELOW_256
    if has_mac and not has_windows:
        return NameRecordStatus.MAC_ONLY
    non_std = sources - {NameIDSource.STANDARD}
    if name_id > 255 and not non_std:
        return NameRecordStatus.ORPHAN
    elidable_value_pair = {NameIDSource.STAT_ELIDABLE, NameIDSource.STAT_VALUE}
    if non_std == elidable_value_pair:
        return NameRecordStatus.OK
    if len(non_std) > 1 or (non_std and NameIDSource.STANDARD in sources):
        return NameRecordStatus.SHARED
    return NameRecordStatus.OK


def _run_validation(analysis: NameAnalysis, font: TTFont) -> None:
    if analysis.mac_record_count:
        mac_ids = sorted(
            {nr.nameID for nr in font["name"].names if nr.platformID == 1}
        )
        analysis.advisory_flags.append(
            NameFlag(
                severity="advisory",
                flag_type="mac_records_present",
                detail=f"{analysis.mac_record_count} Mac (platformID=1) records: {mac_ids[:10]}",
                guidance="Mac records are deprecated. FeatureFlow can remove these.",
            )
        )

    for rec in analysis.records:
        if rec.status == NameRecordStatus.MISSING:
            analysis.required_flags.append(
                NameFlag(
                    severity="required",
                    flag_type="missing_name_record",
                    name_id=rec.name_id,
                    detail=f"nameID {rec.name_id} is referenced but not in the name table.",
                    guidance="Add the missing name record or fix the table reference.",
                )
            )
        elif rec.status == NameRecordStatus.BELOW_256:
            analysis.required_flags.append(
                NameFlag(
                    severity="required",
                    flag_type="invalid_name_id_range",
                    name_id=rec.name_id,
                    detail=f"nameID {rec.name_id} is in invalid user range 26–255.",
                    guidance="Use standard slots 0–25 or dedicated IDs ≥ 256.",
                )
            )
        elif rec.status == NameRecordStatus.MAC_ONLY:
            analysis.required_flags.append(
                NameFlag(
                    severity="required",
                    flag_type="mac_only_name_record",
                    name_id=rec.name_id,
                    detail=f"nameID {rec.name_id} has only Mac records, no Windows.",
                    guidance="Add Windows en-US records for modern renderer visibility.",
                )
            )
        elif rec.status == NameRecordStatus.ORPHAN:
            analysis.advisory_flags.append(
                NameFlag(
                    severity="advisory",
                    flag_type="orphan_name_id",
                    name_id=rec.name_id,
                    detail=f'nameID {rec.name_id} ("{rec.label_en}") has no table reference.',
                    guidance="Remove in rebuild or assign to a table entry.",
                )
            )
        elif rec.status == NameRecordStatus.SHARED:
            analysis.advisory_flags.append(
                NameFlag(
                    severity="advisory",
                    flag_type="shared_name_id",
                    name_id=rec.name_id,
                    detail=rec.shared_note,
                    guidance="Assign dedicated nameIDs per source in the rebuild phase.",
                )
            )
        if rec.name_id > 255 and rec.has_windows is False and rec.status not in (
            NameRecordStatus.MISSING,
            NameRecordStatus.MAC_ONLY,
        ):
            if rec.label_en == "":
                analysis.advisory_flags.append(
                    NameFlag(
                        severity="advisory",
                        flag_type="missing_english_string",
                        name_id=rec.name_id,
                        detail=f"nameID {rec.name_id} has no Windows en-US string.",
                        guidance="Add platformID=3, langID=0x0409 record.",
                    )
                )


def analyze_name(path: Path, font: TTFont) -> NameAnalysis:
    """Full name table cross-reference analysis."""
    vf = analyze_variable_font(font, mode=VariableFontMode.LENIENT)
    analysis = NameAnalysis(path=path, is_variable=vf.is_technically_valid)
    analysis.mac_record_count = sum(1 for r in font["name"].names if r.platformID == 1)

    refs = _collect_references(font)
    name_ids_in_table = {nr.nameID for nr in font["name"].names}
    all_ids = sorted(set(name_ids_in_table) | set(refs.keys()))

    records: List[NameRecord] = []
    for name_id in all_ids:
        sources_set = refs.get(name_id, set())
        in_table = name_id in name_ids_in_table
        platforms, has_win, has_mac = _platform_labels(font, name_id) if in_table else ([], False, False)
        label = windows_en_string(font, name_id) if in_table else ""
        if not label and in_table:
            label = font["name"].getDebugName(name_id) or ""

        status = _classify_status(name_id, sources_set, has_win, has_mac, in_table)
        sources_list = sorted(sources_set - {NameIDSource.STANDARD}, key=lambda s: s.value)
        if not sources_list and name_id <= 25:
            sources_list = [NameIDSource.STANDARD]
        elif not sources_list and name_id > 255:
            sources_list = [NameIDSource.ORPHAN]

        is_shared = status == NameRecordStatus.SHARED
        note = _shared_note(name_id, sources_set, font) if is_shared else ""

        records.append(
            NameRecord(
                name_id=name_id,
                platforms=platforms,
                has_windows=has_win,
                has_mac=has_mac,
                label_en=label,
                sources=sources_list,
                is_shared=is_shared,
                shared_note=note,
                status=status,
            )
        )

    analysis.records = records

    above = [r for r in records if r.name_id > 255]
    analysis.total_above_255 = len(above)
    analysis.ot_feature_count = sum(1 for r in above if NameIDSource.OT_FEATURE in r.sources)
    analysis.stat_count = sum(
        1 for r in above if any(s in r.sources for s in STAT_SOURCES)
    )
    analysis.fvar_count = sum(
        1 for r in above if any(s in r.sources for s in FVAR_SOURCES)
    )
    analysis.orphan_count = sum(1 for r in above if r.status == NameRecordStatus.ORPHAN)
    analysis.shared_count = sum(1 for r in above if r.status == NameRecordStatus.SHARED)

    _run_validation(analysis, font)
    return analysis


def source_tables_for_record(rec: NameRecord) -> str:
    return _source_tables(set(rec.sources))
