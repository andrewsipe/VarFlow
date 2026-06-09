"""Terminal reporting for NameFlow."""

from __future__ import annotations

import FontCore.core_console_styles as cs

from lib.name_analysis import source_tables_for_record
from lib.name_models import NameAnalysis, NameIDSource, NameRecordStatus

console = cs.get_console()


def _primary_source_label(rec) -> str:
    if rec.status == NameRecordStatus.ORPHAN:
        return "orphan"
    if rec.is_shared:
        return "shared"
    if rec.sources:
        return rec.sources[0].value
    return "──"


def _emit_flags(title: str, flags: list) -> None:
    cs.emit(f"  {title}: {'none' if not flags else ''}", console=console)
    for f in flags:
        loc = f"[nameID {f.name_id}] " if f.name_id is not None else ""
        cs.emit(f"  • {loc}{f.flag_type}", console=console)
        if f.detail:
            cs.emit(f"    {f.detail}", console=console)
        if f.guidance:
            cs.emit(f"    {f.guidance}", console=console)


def emit_name_report(analysis: NameAnalysis) -> None:
    path = analysis.path
    cs.fmt_header(f"name table — {path.name}", console=console)

    var_label = "variable" if analysis.is_variable else "static"
    cs.emit(
        f"  Total nameIDs: {len(analysis.records)}  |  "
        f"Above 255: {analysis.total_above_255}  |  "
        f"Mac records: {analysis.mac_record_count}  |  {var_label}",
        console=console,
    )
    cs.emit("", console=console)

    above = [r for r in analysis.records if r.name_id > 255]
    table = cs.create_table(title=f"nameID inventory (above 255)", console=console)
    if table is not None:
        table.add_column("NameID", justify="right")
        table.add_column("String (en)")
        table.add_column("Source")
        table.add_column("Tables")
        table.add_column("Status")
        for rec in above:
            table.add_row(
                str(rec.name_id),
                (rec.label_en or "──")[:40],
                _primary_source_label(rec),
                source_tables_for_record(rec),
                rec.status.value.upper(),
            )
        console.print(table)
    else:
        for rec in above:
            cs.emit(f"  {rec.name_id} {rec.label_en} {rec.status.value}", console=console)

    shared = [r for r in above if r.is_shared]
    cs.emit("", console=console)
    cs.emit(f"  Shared nameIDs: {len(shared)}", console=console)
    for rec in shared:
        cs.emit(f"  • {rec.shared_note}", console=console)

    cs.emit("", console=console)
    cs.emit("  Summary", console=console)
    ot_ids = [r.name_id for r in above if NameIDSource.OT_FEATURE in r.sources]
    stat_ids = [
        r.name_id
        for r in above
        if any(
            s in r.sources
            for s in (
                NameIDSource.STAT_AXIS,
                NameIDSource.STAT_VALUE,
                NameIDSource.STAT_ELIDABLE,
            )
        )
    ]
    fvar_ids = [
        r.name_id
        for r in above
        if any(
            s in r.sources
            for s in (NameIDSource.FVAR_AXIS, NameIDSource.FVAR_INSTANCE, NameIDSource.FVAR_PS)
        )
    ]
    orphan_ids = [r.name_id for r in above if r.status == NameRecordStatus.ORPHAN]

    def _range_str(ids: list) -> str:
        if not ids:
            return "0"
        s = sorted(set(ids))
        if len(s) == 1:
            return f"1 ({s[0]})"
        return f"{len(s)} ({s[0]}–{s[-1]})"

    cs.emit(f"  OT feature IDs:   {_range_str(ot_ids)}", console=console)
    cs.emit(f"  STAT IDs:        {_range_str(stat_ids)}", console=console)
    cs.emit(f"  fvar IDs:         {_range_str(fvar_ids)}", console=console)
    cs.emit(f"  Orphan IDs:       {_range_str(orphan_ids)}", console=console)

    cs.emit("", console=console)
    _emit_flags("Required flags", analysis.required_flags)
    cs.emit("", console=console)
    _emit_flags("Advisory flags", analysis.advisory_flags)
