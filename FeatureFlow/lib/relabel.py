"""Phase 4 — relabel OT feature strings."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from fontTools.ttLib import TTFont

import FontCore.core_console_styles as cs
from FontCore.core_namerecord_matcher import EID_UNICODE_BMP, LANG_EN_US_INT, PID_WIN
from FontCore.core_ot_label_scanner import scan_ot_label_nameids

console = cs.get_console()

_SESSION_FINISH = frozenset({"", "done", "finish", "q", "quit", "exit", "cancel"})


@dataclass
class RelabelChange:
    feature_tag: str
    old_label: str
    new_label: str


def load_relabel_map(path: Path) -> Dict[str, str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("relabel map must be a JSON object")
    return {str(k): str(v) for k, v in data.items()}


def preview_relabel_map_changes(font: TTFont, relabel_map: Dict[str, str]) -> List:
    """Diff rows for --relabel-map without modifying the font."""
    from lib.change_plan import DiffRow

    rows: List[DiffRow] = []
    labels = scan_ot_label_nameids(font)
    seen_tags: set = set()
    for rec in labels:
        if rec.feature_tag in seen_tags:
            continue
        if rec.feature_tag not in relabel_map:
            continue
        seen_tags.add(rec.feature_tag)
        new_string = relabel_map[rec.feature_tag]
        old = _get_windows_string(font, rec.name_id)
        if old == new_string:
            continue
        rows.append(
            DiffRow(
                action="Relabel",
                feature=rec.feature_tag,
                table=rec.table,
                field=rec.field,
                name_id=str(rec.name_id),
                before=old or "──",
                after=new_string,
            )
        )
    return rows


def apply_relabel_map(font: TTFont, relabel_map: Dict[str, str]) -> int:
    """Set Windows en-US strings for features listed in map (before reflow)."""
    count = 0
    labels = scan_ot_label_nameids(font)
    seen_tags: set = set()
    for rec in labels:
        if rec.feature_tag in seen_tags:
            continue
        if rec.feature_tag not in relabel_map:
            continue
        seen_tags.add(rec.feature_tag)
        new_string = relabel_map[rec.feature_tag]
        old = _get_windows_string(font, rec.name_id)
        if old == new_string:
            continue
        font["name"].setName(new_string, rec.name_id, PID_WIN, EID_UNICODE_BMP, LANG_EN_US_INT)
        cs.StatusIndicator("updated").add_field("feature", rec.feature_tag).add_values(
            old_value=old or "──", new_value=new_string
        ).emit(console)
        count += 1
    return count


def _get_windows_string(font: TTFont, name_id: int) -> str:
    try:
        rec = font["name"].getName(name_id, PID_WIN, EID_UNICODE_BMP, LANG_EN_US_INT)
        if rec:
            return rec.toUnicode()
    except Exception:
        pass
    return ""


def _emit_relabel_summary(changes: List[RelabelChange]) -> None:
    cs.fmt_header("Relabel summary", console=console)
    cs.emit(f"  {len(changes)} change(s) this session:", console=console)
    for ch in changes:
        cs.emit(
            f"  {ch.feature_tag}  {ch.old_label}  →  {ch.new_label}",
            console=console,
        )
    cs.emit("", console=console)


def interactive_relabel(font: TTFont, *, auto_skip: bool = False) -> int:
    """Prompt user to edit OT feature label strings."""
    if auto_skip:
        return 0

    labels = scan_ot_label_nameids(font)
    if not labels:
        return 0

    by_tag: Dict[str, int] = {}
    for rec in labels:
        if rec.field in ("UINameID", "LabelNameID", "FeatureNameID"):
            by_tag.setdefault(rec.feature_tag, rec.name_id)

    if not by_tag:
        return 0

    by_tag_lower = {k.lower(): k for k in by_tag}
    cs.fmt_header("Interactive relabel", console=console)
    cs.emit("Editable features:", console=console)
    for tag in sorted(by_tag):
        label = _get_windows_string(font, by_tag[tag]) or "──"
        cs.emit(f"  {tag}  {label}", console=console)
    cs.emit(
        "Enter a feature tag to change its label. "
        "Press Enter, done, or q to finish (edits are kept).",
        console=console,
    )

    session_changes: List[RelabelChange] = []

    while True:
        try:
            raw = cs.prompt_input("Feature tag (Enter or q=done)", console=console)
        except (EOFError, KeyboardInterrupt):
            break
        tag = raw.strip().lower()
        if tag in _SESSION_FINISH:
            break
        canonical = by_tag_lower.get(raw.strip().lower())
        if canonical is None:
            cs.StatusIndicator("warning").add_message(
                f"Unknown tag {raw.strip()!r} — choose from: {', '.join(sorted(by_tag))}"
            ).emit(console)
            continue
        name_id = by_tag[canonical]
        old = _get_windows_string(font, name_id)
        cs.emit(f"  Current ({name_id}): {old or '──'}", console=console)
        try:
            new_raw = cs.prompt_input("New label (Enter=keep unchanged)", console=console)
        except (EOFError, KeyboardInterrupt):
            break
        new = new_raw.strip()
        if new.lower() in _SESSION_FINISH:
            break
        if not new or new == old:
            continue
        font["name"].setName(new, name_id, PID_WIN, EID_UNICODE_BMP, LANG_EN_US_INT)
        cs.StatusIndicator("updated").add_field("nameID", name_id).add_values(
            old_value=old or "──", new_value=new
        ).emit(console)
        session_changes.append(
            RelabelChange(
                feature_tag=canonical,
                old_label=old or "──",
                new_label=new,
            )
        )

    if session_changes:
        _emit_relabel_summary(session_changes)

    return len(session_changes)
