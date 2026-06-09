"""Terminal reporting for StatFlow."""

from __future__ import annotations

from typing import List

import FontCore.core_console_styles as cs

from lib.stat_models import StatAnalysis, StatAxisValue, StatFlag

console = cs.get_console()


def _value_status(av: StatAxisValue, flags: List[StatFlag]) -> str:
    for f in flags:
        if f.severity != "required":
            continue
        if f.name_id == av.name_id and (
            f.axis_tag in (None, av.axis_tag) or not av.axis_tag
        ):
            return "MISSING"
    return "OK"


def _axis_status(tag: str, name_id: int, flags: List[StatFlag]) -> str:
    for f in flags:
        if f.severity == "required" and f.axis_tag == tag and f.name_id in (None, name_id):
            return "MISSING"
    return "OK"


def _format_version(version: int | None) -> str:
    if version is None:
        return "unknown"
    major = (version >> 16) & 0xFFFF
    minor = version & 0xFFFF
    return f"{major}.{minor}"


def _emit_flags(title: str, flags: List[StatFlag]) -> None:
    cs.emit(f"  {title} ({len(flags)})", console=console)
    if not flags:
        cs.emit("  (none)", console=console)
        return
    for f in flags:
        loc_parts = []
        if f.axis_tag:
            loc_parts.append(f.axis_tag)
        if f.name_id is not None:
            loc_parts.append(f"nameID {f.name_id}")
        loc = f"[{' / '.join(loc_parts)}] " if loc_parts else ""
        cs.emit(f"  • {loc}{f.flag_type}", console=console)
        if f.detail:
            cs.emit(f"    {f.detail}", console=console)
        if f.guidance:
            cs.emit(f"    {f.guidance}", console=console)


def emit_stat_report(analysis: StatAnalysis) -> None:
    """Print STAT analysis report."""
    path = analysis.path
    cs.fmt_header(f"STAT Table — {path.name}", console=console)

    if not analysis.has_stat:
        cs.StatusIndicator("info").add_message("No STAT table — skipped").emit(console)
        return

    var_label = "Variable font" if analysis.is_variable else "Not variable (no fvar)"
    varstore = "yes" if analysis.has_varstore else "no"
    cs.emit(
        f"  {var_label}  |  STAT version: {_format_version(analysis.stat_version)}  |  "
        f"VarStore: {varstore}",
        console=console,
    )
    cs.emit("", console=console)

    all_flags = analysis.required_flags + analysis.advisory_flags

    table = cs.create_table(title=f"Axes ({len(analysis.axes)})", console=console)
    if table is not None:
        table.add_column("Tag")
        table.add_column("Name")
        table.add_column("NameID", justify="right")
        table.add_column("Ordering", justify="right")
        table.add_column("Status")
        for ax in analysis.axes:
            table.add_row(
                ax.tag,
                ax.name_en or "──",
                str(ax.name_id),
                str(ax.ordering),
                _axis_status(ax.tag, ax.name_id, all_flags),
            )
        console.print(table)
    else:
        cs.emit(f"Axes ({len(analysis.axes)})", console=console)
        for ax in analysis.axes:
            cs.emit(
                f"  {ax.tag}  {ax.name_en}  nameID={ax.name_id}  ordering={ax.ordering}",
                console=console,
            )

    cs.emit("", console=console)
    non_f4 = [av for av in analysis.axis_values if av.format != 4]
    f4 = [av for av in analysis.axis_values if av.format == 4]

    table = cs.create_table(title=f"Axis values ({len(non_f4)})", console=console)
    if table is not None:
        table.add_column("Axis")
        table.add_column("Format", justify="right")
        table.add_column("NameID", justify="right")
        table.add_column("Name")
        table.add_column("Value")
        table.add_column("Linked")
        table.add_column("Status")
        for av in non_f4:
            val_s = "──"
            if av.format == 1 or av.format == 3:
                val_s = f"{av.value:g}" if av.value is not None else "──"
            elif av.format == 2:
                val_s = (
                    f"{av.nominal_value:g} [{av.range_min:g}–{av.range_max:g}]"
                    if av.nominal_value is not None
                    else "──"
                )
            linked_s = "──"
            if av.format == 3 and av.linked_value is not None:
                linked_s = f"{av.linked_value:g}"
            table.add_row(
                av.axis_tag,
                str(av.format),
                str(av.name_id),
                av.name_en or "──",
                val_s,
                linked_s,
                _value_status(av, all_flags),
            )
        console.print(table)
    else:
        cs.emit(f"Axis values ({len(non_f4)})", console=console)
        for av in non_f4:
            cs.emit(f"  {av.axis_tag} fmt={av.format} nameID={av.name_id} {av.name_en}", console=console)

    cs.emit("", console=console)
    if f4:
        table = cs.create_table(title=f"Format 4 (compound) entries ({len(f4)})", console=console)
        if table is not None:
            table.add_column("Coordinates")
            table.add_column("NameID", justify="right")
            table.add_column("Name")
            table.add_column("Status")
            for av in f4:
                coords = ", ".join(f"{k}={v:g}" for k, v in sorted(av.axis_value_pairs.items()))
                table.add_row(
                    coords,
                    str(av.name_id),
                    av.name_en or "──",
                    _value_status(av, all_flags),
                )
            console.print(table)
        else:
            cs.emit(f"Format 4 entries ({len(f4)})", console=console)
            for av in f4:
                cs.emit(f"  {av.axis_value_pairs} nameID={av.name_id}", console=console)
    else:
        cs.emit("  Format 4 (compound) entries: none", console=console)

    cs.emit("", console=console)
    if analysis.elidable_fallback_name_id:
        cs.emit(
            f"  Elidable fallback: nameID {analysis.elidable_fallback_name_id} — "
            f'"{analysis.elidable_fallback_label or "──"}"',
            console=console,
        )
    else:
        cs.emit("  Elidable fallback: none", console=console)

    cs.emit("", console=console)
    _emit_flags("Required flags", analysis.required_flags)
    cs.emit("", console=console)
    _emit_flags("Advisory flags", analysis.advisory_flags)

    cs.emit("", console=console)
    ids_str = ", ".join(str(i) for i in analysis.stat_name_ids) if analysis.stat_name_ids else "none"
    cs.emit(f"  Name IDs used by STAT: {ids_str}", console=console)
    cs.emit(f"  Mac name records: {analysis.mac_record_count}", console=console)
