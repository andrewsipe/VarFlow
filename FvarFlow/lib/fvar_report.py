"""Terminal reporting for FvarFlow."""

from __future__ import annotations

import FontCore.core_console_styles as cs

from lib.fvar_models import FvarAnalysis, FvarInstance

console = cs.get_console()


def _instance_status(inst: FvarInstance) -> str:
    if inst.uses_shared_id:
        return "SHARED"
    if not inst.stat_coverage.covered and inst.stat_coverage.missing_axes:
        return "PARTIAL" if inst.stat_coverage.partial else "UNCOVERED"
    return "OK"


def _coverage_label(inst: FvarInstance) -> str:
    cov = inst.stat_coverage
    if cov.covered:
        return "full"
    if not cov.missing_axes:
        return "none"
    if cov.partial:
        return f"partial ({', '.join(cov.missing_axes)})"
    return f"missing ({', '.join(cov.missing_axes)})"


def _coords_str(coords: dict) -> str:
    return ", ".join(f"{k}={v:g}" for k, v in sorted(coords.items()))


def _emit_flags(title: str, flags: list) -> None:
    cs.emit(f"  {title}: {'none' if not flags else ''}", console=console)
    for f in flags:
        loc = ""
        if f.instance_index is not None:
            loc = f"[instance {f.instance_index}] "
        elif f.axis_tag:
            loc = f"[{f.axis_tag}] "
        cs.emit(f"  • {loc}{f.flag_type}", console=console)
        if f.detail:
            cs.emit(f"    {f.detail}", console=console)
        if f.guidance:
            cs.emit(f"    {f.guidance}", console=console)


def emit_fvar_report(analysis: FvarAnalysis) -> None:
    path = analysis.path
    cs.fmt_header(f"fvar Table — {path.name}", console=console)

    if not analysis.has_fvar:
        cs.StatusIndicator("info").add_message("No fvar table — skipped").emit(console)
        return

    table = cs.create_table(title=f"Axes ({len(analysis.axes)})", console=console)
    if table is not None:
        table.add_column("Tag")
        table.add_column("Name")
        table.add_column("NameID", justify="right")
        table.add_column("Min", justify="right")
        table.add_column("Default", justify="right")
        table.add_column("Max", justify="right")
        table.add_column("In STAT")
        for ax in analysis.axes:
            table.add_row(
                ax.tag,
                ax.name_en or "──",
                str(ax.name_id),
                f"{ax.min_value:g}",
                f"{ax.default_value:g}",
                f"{ax.max_value:g}",
                "yes" if ax.in_stat else "no",
            )
        console.print(table)
    else:
        cs.emit(f"Axes ({len(analysis.axes)})", console=console)
        for ax in analysis.axes:
            cs.emit(f"  {ax.tag} {ax.name_en} nameID={ax.name_id}", console=console)

    cs.emit("", console=console)
    table = cs.create_table(title=f"Named instances ({len(analysis.instances)})", console=console)
    if table is not None:
        table.add_column("#", justify="right")
        table.add_column("Name")
        table.add_column("NameID", justify="right")
        table.add_column("Coordinates")
        table.add_column("STAT coverage")
        table.add_column("Status")
        for inst in analysis.instances:
            table.add_row(
                str(inst.index),
                inst.name_en or "──",
                str(inst.name_id),
                _coords_str(inst.coordinates),
                _coverage_label(inst),
                _instance_status(inst),
            )
        console.print(table)
    else:
        cs.emit(f"Named instances ({len(analysis.instances)})", console=console)
        for inst in analysis.instances:
            coord_str = " ".join(
                f"{k}={v:g}" for k, v in sorted(inst.coordinates.items())
            )
            coverage = "full" if inst.stat_coverage.covered else _coverage_label(inst)
            cs.emit(
                f"  {inst.index} {inst.name_en or '──'} nameID={inst.name_id}  "
                f"[{coord_str}]  coverage={coverage}",
                console=console,
            )

    cs.emit("", console=console)
    _emit_flags("Required flags", analysis.required_flags)
    cs.emit("", console=console)
    _emit_flags("Advisory flags", analysis.advisory_flags)
