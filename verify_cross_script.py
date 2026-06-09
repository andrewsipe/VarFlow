#!/usr/bin/env python3
"""Verify StatFlow/FvarFlow nameIDs match NameFlow attribution."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _run_snippet(pkg: str, snippet: str, font_path: Path) -> dict:
    pkg_dir = ROOT / pkg
    code = f"""
import sys, json
from pathlib import Path
sys.path.insert(0, {str(pkg_dir)!r})
from lib.fontcore_path import ensure_fontcore_on_path
ensure_fontcore_on_path({str(pkg_dir)!r})
from fontTools.ttLib import TTFont
font_path = Path({str(font_path)!r})
font = TTFont(font_path, lazy=True)
{snippet}
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"{pkg} failed:\n{result.stderr}")
    return json.loads(result.stdout.strip())


def verify(font_path: Path) -> int:
    stat = _run_snippet(
        "StatFlow",
        """
from lib.stat_analysis import analyze_stat
a = analyze_stat(font_path, font)
print(json.dumps({"stat_ids": a.stat_name_ids}))
font.close()
""",
        font_path,
    )
    fvar = _run_snippet(
        "FvarFlow",
        """
from lib.fvar_analysis import analyze_fvar
a = analyze_fvar(font_path, font)
ids = {ax.name_id for ax in a.axes}
for inst in a.instances:
    ids.add(inst.name_id)
    if inst.postscript_name_id:
        ids.add(inst.postscript_name_id)
print(json.dumps({"fvar_ids": sorted(ids)}))
font.close()
""",
        font_path,
    )
    name = _run_snippet(
        "NameFlow",
        """
from lib.name_analysis import analyze_name
a = analyze_name(font_path, font)
rows = {}
for r in a.records:
    rows[r.name_id] = [s.value for s in r.sources]
print(json.dumps({"sources": rows}))
font.close()
""",
        font_path,
    )

    stat_sources = {"stat_axis", "stat_value", "stat_elidable"}
    fvar_sources = {"fvar_axis", "fvar_instance", "fvar_ps"}
    mismatches: list[tuple[str, int, str]] = []

    for nid in stat["stat_ids"]:
        src = set(name["sources"].get(str(nid), name["sources"].get(nid, [])))
        if not src & stat_sources:
            mismatches.append(("stat", nid, str(src)))

    for nid in fvar["fvar_ids"]:
        if nid < 256:
            continue
        src = set(name["sources"].get(str(nid), name["sources"].get(nid, [])))
        if not src & fvar_sources:
            mismatches.append(("fvar", nid, str(src)))

    if mismatches:
        print(f"FAIL {font_path.name}: {len(mismatches)} mismatches")
        for m in mismatches[:10]:
            print(" ", m)
        return 1
    print(
        f"OK {font_path.name}: {len(stat['stat_ids'])} STAT, "
        f"{len([i for i in fvar['fvar_ids'] if i >= 256])} fvar >=256"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    paths = argv or sys.argv[1:]
    if not paths:
        print("Usage: verify_cross_script.py font.ttf ...")
        return 1
    return max(verify(Path(p)) for p in paths)


if __name__ == "__main__":
    sys.exit(main())
