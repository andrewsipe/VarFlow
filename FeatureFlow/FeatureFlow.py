#!/usr/bin/env python3
"""
OT Feature Label Manager — audit, prune Mac names, reflow GSUB/GPOS label nameIDs.

Usage:
  python FeatureFlow.py font.otf --report-only
  python FeatureFlow.py ./fonts --recursive --dry-run
  python FeatureFlow.py font.otf --output-dir ./out --suffix -Fixed --yes
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional

_FEATUREFLOW_DIR = Path(__file__).resolve().parent
if str(_FEATUREFLOW_DIR) not in sys.path:
    sys.path.insert(0, str(_FEATUREFLOW_DIR))

from lib.fontcore_path import ensure_fontcore_on_path  # noqa: E402

ensure_fontcore_on_path(_FEATUREFLOW_DIR)

import FontCore.core_console_styles as cs  # noqa: E402
from FontCore.core_error_handling import ErrorContext, ErrorInfo, ErrorTracker  # noqa: E402
from FontCore.core_file_collector import collect_font_files_with_rich_progress  # noqa: E402
from fontTools.ttLib import TTFont  # noqa: E402

from lib.analyze import analyze_font, confirm_contiguity_if_needed, emit_report  # noqa: E402
from lib.io_paths import resolve_output_path  # noqa: E402
from lib.mac_prune import prune_mac_records  # noqa: E402
from lib.models import BatchSummary, FontProcessResult  # noqa: E402
from lib.orphans import remove_orphans  # noqa: E402
from lib.change_plan import build_pending_changes, emit_change_diff  # noqa: E402
from lib.preflight import confirm_preflight, emit_preflight  # noqa: E402
from lib.reflow import (  # noqa: E402
    apply_reflow,
    build_reflow_plan,
    reflow_needed,
    verify_remap_safe,
)
from lib.relabel import apply_relabel_map, interactive_relabel, load_relabel_map  # noqa: E402

console = cs.get_console()
logger = cs.get_logger(__name__)


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Inspect, reflow, and relabel OpenType feature UI labels in font files.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  %(prog)s font.otf --report-only
  %(prog)s ./fonts --recursive --dry-run
  %(prog)s font.otf --output-dir ./out --suffix=-Fixed --yes
  %(prog)s font.otf --relabel --no-reflow
""",
    )
    p.add_argument(
        "paths",
        nargs="+",
        help="One or more font files or directories (use --recursive to descend)",
    )
    p.add_argument(
        "--recursive",
        action="store_true",
        help="Recurse into subdirectories when a path is a directory",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Show planned changes and diff; do not write files",
    )
    p.add_argument(
        "--report-only",
        action="store_true",
        help="Analyze and print inventory only; no mutations",
    )
    p.add_argument(
        "--no-reflow",
        action="store_true",
        help="Skip OT feature label nameID reflow",
    )
    p.add_argument(
        "--no-prune-mac",
        action="store_true",
        help="Keep Mac (platformID 1) name records — removed by default",
    )
    p.add_argument(
        "--remove-orphans",
        action="store_true",
        help="Remove orphan nameIDs >255 with no GSUB/GPOS reference (no per-ID prompt)",
    )
    p.add_argument(
        "--relabel",
        action="store_true",
        help="Interactive relabel session after other steps (off by default)",
    )
    p.add_argument(
        "--relabel-map",
        type=Path,
        metavar="PATH",
        help='Batch relabel JSON object, e.g. {"ss01": "Label", "cv01": "Label"}',
    )
    p.add_argument(
        "--output-dir",
        type=Path,
        metavar="DIR",
        help="Write output fonts to this directory",
    )
    p.add_argument(
        "--suffix",
        type=str,
        metavar="STR",
        help="Append suffix before extension (e.g. -Fixed)",
    )
    p.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    p.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Auto-confirm preflight, overwrite, and orphan prompts (not --relabel)",
    )
    return p.parse_args(argv)


def process_font(
    path: Path,
    args: argparse.Namespace,
    relabel_map: Optional[dict],
) -> FontProcessResult:
    result = FontProcessResult(path=path)
    tracker = ErrorTracker()

    try:
        font = TTFont(path, lazy=False)
    except Exception as e:
        tracker.add_error(
            ErrorInfo.from_exception(
                context=ErrorContext.LOADING,
                filepath=str(path),
                exception=e,
                message="Failed to load font",
            )
        )
        result.error = str(e)
        cs.StatusIndicator("error").add_file(path).add_message(str(e)).emit(console)
        return result

    try:
        analysis = analyze_font(path, font)
        emit_report(analysis)

        if args.report_only:
            result.skipped = True
            font.close()
            return result

        if analysis.has_blocking_errors and not args.dry_run:
            cs.StatusIndicator("error").add_message(
                "Blocking errors — fix or use --report-only before writing"
            ).emit(console)
            result.error = "blocking errors"
            font.close()
            return result

        will_prune_mac = not args.no_prune_mac and analysis.mac_record_count > 0
        will_reflow_flag = not args.no_reflow
        will_relabel_interactive = bool(args.relabel) and relabel_map is None and not args.dry_run

        pending = build_pending_changes(
            font,
            analysis,
            prune_mac=will_prune_mac,
            do_reflow=will_reflow_flag,
            relabel_map=relabel_map,
            interactive_relabel=will_relabel_interactive,
            remove_orphans=args.remove_orphans,
            dry_run=args.dry_run,
        )

        if not pending.has_mutations:
            cs.StatusIndicator("unchanged").add_message(
                "No changes needed — file left unchanged"
            ).emit(console)
            result.skipped = True
            font.close()
            return result

        emit_preflight(analysis, font, pending.plan_lines, path_name=path.name)
        emit_change_diff(pending, path_name=path.name)

        if args.dry_run:
            cs.StatusIndicator("preview", dry_run=True).add_message(
                "Dry run — no file written"
            ).emit(console)
            font.close()
            return result

        relabel_only = (
            will_relabel_interactive and not pending.has_deterministic_mutations
        )
        if not relabel_only and not confirm_preflight(
            pending.plan_lines, auto_yes=args.yes
        ):
            cs.StatusIndicator("skipped").add_message("Cancelled before changes").emit(console)
            result.skipped = True
            font.close()
            return result

        if relabel_map:
            result.labels_relabeled += apply_relabel_map(font, relabel_map)

        if pending.will_prune_mac:
            result.mac_removed = prune_mac_records(font, dry_run=args.dry_run)

        if not args.no_reflow and analysis.ot_name_ids:
            if reflow_needed(font, analysis, exclude_mac=False):
                if not confirm_contiguity_if_needed(analysis, auto_yes=args.yes):
                    cs.StatusIndicator("skipped").add_message(
                        "Reflow aborted by user"
                    ).emit(console)
                else:
                    plan = build_reflow_plan(font, analysis, exclude_mac=False)
                    if plan.is_identity:
                        cs.StatusIndicator("unchanged").add_message(
                            "Reflow: no nameID changes required"
                        ).emit(console)
                    else:
                        errors = verify_remap_safe(
                            plan.remap, set(analysis.protected_ids.keys())
                        )
                        if errors:
                            for msg in errors:
                                cs.StatusIndicator("error").add_message(msg).emit(
                                    console
                                )
                            result.error = "; ".join(errors)
                            font.close()
                            return result
                        result.ids_reflowed = apply_reflow(
                            font, analysis, plan, dry_run=False
                        )
                        analysis = analyze_font(path, font)

        if will_relabel_interactive:
            result.labels_relabeled += interactive_relabel(font, auto_skip=False)

        if analysis.orphan_ids:
            result.orphans_removed = remove_orphans(
                font,
                analysis.orphan_ids,
                skip_prompt=args.remove_orphans or args.yes,
            )

        mutations_applied = (
            result.mac_removed
            + result.ids_reflowed
            + result.labels_relabeled
            + result.orphans_removed
        )
        if mutations_applied == 0:
            cs.StatusIndicator("unchanged").add_message(
                "No changes applied — file not written"
            ).emit(console)
            result.skipped = True
            font.close()
            return result

        out_path = resolve_output_path(
            path,
            output_dir=args.output_dir,
            suffix=args.suffix,
        )
        if out_path != path.resolve() and args.output_dir:
            args.output_dir.mkdir(parents=True, exist_ok=True)

        if out_path == path.resolve() and not args.yes:
            if not cs.prompt_confirm(f"Overwrite {path.name}?", default=False):
                cs.StatusIndicator("skipped").add_message("Save cancelled").emit(console)
                result.skipped = True
                font.close()
                return result

        font.save(out_path)
        result.output_path = out_path
        result.saved = True
        cs.StatusIndicator("saved").add_file(out_path).emit(console)
        font.close()

    except Exception as e:
        tracker.add_error(
            ErrorInfo.from_exception(
                context=ErrorContext.NAME_TABLE,
                filepath=str(path),
                exception=e,
                message="Processing failed",
            )
        )
        result.error = str(e)
        cs.StatusIndicator("error").add_file(path).add_message(str(e)).emit(console)
        try:
            font.close()
        except Exception:
            pass

    return result


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    if args.verbose:
        import logging

        logging.getLogger().setLevel(logging.DEBUG)

    if args.output_dir:
        args.output_dir = args.output_dir.resolve()

    if args.relabel and args.relabel_map:
        cs.StatusIndicator("warning").add_message(
            "--relabel ignored because --relabel-map was provided"
        ).emit(console)

    relabel_map = None
    if args.relabel_map:
        relabel_map = load_relabel_map(args.relabel_map.resolve())

    font_paths = collect_font_files_with_rich_progress(
        args.paths,
        recursive=args.recursive,
        console=console,
    )
    if not font_paths:
        cs.StatusIndicator("warning").add_message("No font files found").emit(console)
        return 1

    cs.print_session_header(
        f"OT Feature Label Manager — {len(font_paths)} font(s)",
        console=console,
    )

    summary = BatchSummary()
    relabeled_from_cli = relabel_map is not None

    for fp in font_paths:
        path = Path(fp)
        cs.fmt_header(path.name, console=console)
        result = process_font(path, args, relabel_map if relabeled_from_cli else None)
        summary.fonts_processed += 1
        if result.error:
            summary.fonts_errors += 1
        elif result.saved:
            summary.fonts_saved += 1
        summary.mac_removed_total += result.mac_removed
        summary.ids_reflowed_total += result.ids_reflowed
        summary.labels_relabeled_total += result.labels_relabeled
        summary.orphans_removed_total += result.orphans_removed

    additional = [
        f"Mac records removed: {summary.mac_removed_total}",
        f"OT IDs reflowed: {summary.ids_reflowed_total}",
        f"Labels relabeled: {summary.labels_relabeled_total}",
        f"Orphans removed: {summary.orphans_removed_total}",
        f"Fonts saved: {summary.fonts_saved}",
    ]
    cs.fmt_processing_summary(
        dry_run=args.dry_run or args.report_only,
        updated=summary.fonts_saved,
        unchanged=summary.fonts_processed - summary.fonts_saved - summary.fonts_errors,
        errors=summary.fonts_errors,
        console=console,
        additional_info=additional,
    )
    return 1 if summary.fonts_errors else 0


if __name__ == "__main__":
    sys.exit(main())
