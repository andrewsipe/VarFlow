#!/usr/bin/env python3
"""
Name table inventory and cross-table reference validation.

Usage:
  python NameFlow.py font.ttf
  python NameFlow.py ./fonts --recursive
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional

_NAMEFLOW_DIR = Path(__file__).resolve().parent
if str(_NAMEFLOW_DIR) not in sys.path:
    sys.path.insert(0, str(_NAMEFLOW_DIR))

from lib.fontcore_path import ensure_fontcore_on_path  # noqa: E402

ensure_fontcore_on_path(_NAMEFLOW_DIR)

import FontCore.core_console_styles as cs  # noqa: E402
from FontCore.core_error_handling import ErrorContext, ErrorInfo, ErrorTracker  # noqa: E402
from FontCore.core_file_collector import collect_font_files_with_rich_progress  # noqa: E402
from fontTools.ttLib import TTFont  # noqa: E402

from lib.name_analysis import analyze_name  # noqa: E402
from lib.name_models import BatchSummary, FontProcessResult  # noqa: E402
from lib.name_report import emit_name_report  # noqa: E402

console = cs.get_console()


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Analyze name table cross-references across OpenType tables.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  %(prog)s font.ttf
  %(prog)s ./fonts --recursive
  %(prog)s font.ttf --verbose
""",
    )
    p.add_argument("paths", nargs="+", help="Font files or directories")
    p.add_argument("--recursive", action="store_true", help="Recurse into directories")
    p.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    p.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Reserved for future modification phase (no-op)",
    )
    return p.parse_args(argv)


def process_font(path: Path) -> FontProcessResult:
    result = FontProcessResult(path=path)
    tracker = ErrorTracker()
    try:
        font = TTFont(path, lazy=True)
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
        analysis = analyze_name(path, font)
        emit_name_report(analysis)
        font.close()
    except Exception as e:
        tracker.add_error(
            ErrorInfo.from_exception(
                context=ErrorContext.NAME_TABLE,
                filepath=str(path),
                exception=e,
                message="Name analysis failed",
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

    font_paths = collect_font_files_with_rich_progress(
        args.paths, recursive=args.recursive, console=console
    )
    if not font_paths:
        cs.StatusIndicator("warning").add_message("No font files found").emit(console)
        return 1

    cs.print_session_header(
        f"Name Table Analysis — {len(font_paths)} font(s)", console=console
    )
    summary = BatchSummary()
    for fp in font_paths:
        result = process_font(Path(fp))
        summary.fonts_processed += 1
        if result.error:
            summary.fonts_errors += 1
        else:
            summary.fonts_analyzed += 1

    cs.fmt_processing_summary(
        dry_run=True,
        updated=0,
        unchanged=summary.fonts_analyzed,
        errors=summary.fonts_errors,
        console=console,
        additional_info=[f"Fonts analyzed: {summary.fonts_analyzed}"],
    )
    return 1 if summary.fonts_errors else 0


if __name__ == "__main__":
    sys.exit(main())
