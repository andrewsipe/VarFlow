"""Tests for FvarFlow STAT coverage and validation."""

from __future__ import annotations

import sys
from pathlib import Path

from fontTools.fontBuilder import FontBuilder
from fontTools.ttLib import newTable
from fontTools.ttLib.tables import _g_l_y_f as glyf_module
from fontTools.ttLib.tables import otTables

_FVARFLOW = Path(__file__).resolve().parents[1]
if str(_FVARFLOW) not in sys.path:
    sys.path.insert(0, str(_FVARFLOW))

from lib.fontcore_path import ensure_fontcore_on_path  # noqa: E402

ensure_fontcore_on_path(_FVARFLOW)

from lib.fvar_analysis import analyze_fvar  # noqa: E402


def _set_win_name(font, name_id: int, string: str) -> None:
    font["name"].setName(string, name_id, 3, 1, 0x0409)


def _minimal_vf(*, instance_name_id: int = 257, coords: dict | None = None) -> object:
    coords = coords or {"wght": 400}
    fb = FontBuilder(1024, isTTF=True)
    fb.setupGlyphOrder([".notdef"])
    fb.setupCharacterMap({})
    fb.setupGlyf({".notdef": glyf_module.Glyph()})
    fb.setupHorizontalMetrics({".notdef": (600, 0)})
    fb.setupHorizontalHeader(ascent=800, descent=-200)
    fb.setupOS2()
    fb.setupPost()
    fb.setupNameTable({"familyName": "Test", "styleName": "Regular"})
    _set_win_name(fb.font, instance_name_id, "Instance")
    axes = [("wght", 100, 400, 900, "Weight")]
    instances = [{"location": coords, "stylename": "Instance"}]
    fb.setupFvar(axes, instances)
    inst = fb.font["fvar"].instances[0]
    inst.subfamilyNameID = instance_name_id
    return fb.font


def _add_stat_format1(font, value: float = 400.0) -> None:
    _set_win_name(font, 256, "Weight")
    _set_win_name(font, 258, "Regular")
    stat = otTables.STAT()
    stat.Version = 0x00010002
    design = otTables.AxisRecordArray()
    ax = otTables.AxisRecord()
    ax.AxisTag = "wght"
    ax.AxisNameID = 256
    ax.AxisOrdering = 0
    design.Axis = [ax]
    stat.DesignAxisRecord = design
    av = otTables.AxisValue()
    av.Format = 1
    av.AxisIndex = 0
    av.Flags = 0
    av.ValueNameID = 258
    av.Value = value
    av_array = otTables.AxisValueArray()
    av_array.AxisValue = [av]
    stat.AxisValueArray = av_array
    t = newTable("STAT")
    t.table = stat
    font["STAT"] = t


class TestFvarCoverage:
    def test_no_fvar_skipped(self):
        fb = FontBuilder(1024, isTTF=True)
        fb.setupGlyphOrder([".notdef"])
        fb.setupCharacterMap({})
        fb.setupGlyf({".notdef": glyf_module.Glyph()})
        fb.setupHorizontalMetrics({".notdef": (600, 0)})
        fb.setupHorizontalHeader(ascent=800, descent=-200)
        fb.setupOS2()
        fb.setupPost()
        fb.setupNameTable({"familyName": "Test", "styleName": "Regular"})
        analysis = analyze_fvar(Path("t.ttf"), fb.font)
        assert not analysis.has_fvar

    def test_stat_coverage_full(self):
        font = _minimal_vf()
        _add_stat_format1(font, 400.0)
        analysis = analyze_fvar(Path("t.ttf"), font)
        assert analysis.instances[0].stat_coverage.covered

    def test_shared_reserved_id(self):
        font = _minimal_vf(instance_name_id=2)
        _set_win_name(font, 2, "Bold")
        analysis = analyze_fvar(Path("t.ttf"), font)
        assert analysis.instances[0].uses_shared_id
        types = {f.flag_type for f in analysis.advisory_flags}
        assert "shared_reserved_id" in types

    def test_coordinate_out_of_range(self):
        font = _minimal_vf(coords={"wght": 950})
        analysis = analyze_fvar(Path("t.ttf"), font)
        types = {f.flag_type for f in analysis.required_flags}
        assert "coordinate_out_of_range" in types
