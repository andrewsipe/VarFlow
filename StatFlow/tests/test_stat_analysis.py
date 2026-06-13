"""Tests for StatFlow STAT analysis."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fontTools.fontBuilder import FontBuilder
from fontTools.ttLib import newTable
from fontTools.ttLib.tables import _g_l_y_f as glyf_module
from fontTools.ttLib.tables import otTables

_STATFLOW = Path(__file__).resolve().parents[1]
if str(_STATFLOW) not in sys.path:
    sys.path.insert(0, str(_STATFLOW))

from lib.fontcore_path import ensure_fontcore_on_path  # noqa: E402

ensure_fontcore_on_path(_STATFLOW)

from lib.stat_analysis import analyze_stat  # noqa: E402


def _minimal_vf() -> object:
    fb = FontBuilder(1024, isTTF=True)
    fb.setupGlyphOrder([".notdef"])
    fb.setupCharacterMap({})
    fb.setupGlyf({".notdef": glyf_module.Glyph()})
    fb.setupHorizontalMetrics({".notdef": (600, 0)})
    fb.setupHorizontalHeader(ascent=800, descent=-200)
    fb.setupOS2()
    fb.setupPost()
    fb.setupNameTable({"familyName": "Test", "styleName": "Regular"})
    axes = [("wght", 100, 400, 900, "Weight")]
    instances = [{"location": {"wght": 400}, "stylename": "Regular"}]
    fb.setupFvar(axes, instances)
    return fb.font


def _set_win_name(font, name_id: int, string: str) -> None:
    font["name"].setName(string, name_id, 3, 1, 0x0409)


def _add_stat_wght(font) -> None:
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
    av.Value = 400.0
    av_array = otTables.AxisValueArray()
    av_array.AxisValue = [av]
    stat.AxisValueArray = av_array
    stat.ElidedFallbackNameID = 258
    t = newTable("STAT")
    t.table = stat
    font["STAT"] = t


class TestStatAnalysis:
    def test_no_stat_early_return(self):
        font = _minimal_vf()
        analysis = analyze_stat(Path("test.ttf"), font)
        assert not analysis.has_stat
        assert analysis.is_variable

    def test_format1_axis_value(self):
        font = _minimal_vf()
        _add_stat_wght(font)
        analysis = analyze_stat(Path("test.ttf"), font)
        assert analysis.has_stat
        assert len(analysis.axes) == 1
        assert len(analysis.axis_values) == 1
        assert analysis.axis_values[0].format == 1
        assert analysis.axis_values[0].value == 400.0

    def test_nameid_below_256_flag(self):
        font = _minimal_vf()
        _set_win_name(font, 2, "Bold")
        stat = otTables.STAT()
        stat.Version = 0x00010002
        design = otTables.AxisRecordArray()
        ax = otTables.AxisRecord()
        ax.AxisTag = "wght"
        ax.AxisNameID = 256
        ax.AxisOrdering = 0
        design.Axis = [ax]
        stat.DesignAxisRecord = design
        _set_win_name(font, 256, "Weight")
        av = otTables.AxisValue()
        av.Format = 1
        av.AxisIndex = 0
        av.Flags = 0
        av.ValueNameID = 2
        av.Value = 700.0
        av_array = otTables.AxisValueArray()
        av_array.AxisValue = [av]
        stat.AxisValueArray = av_array
        t = newTable("STAT")
        t.table = stat
        font["STAT"] = t
        analysis = analyze_stat(Path("test.ttf"), font)
        types = {f.flag_type for f in analysis.required_flags}
        assert "nameID_below_256" in types

    def test_format1_advisory_once_per_axis(self):
        font = _minimal_vf()
        _add_stat_wght(font)
        stat = font["STAT"].table
        for value, nid in ((100.0, 257), (700.0, 259), (900.0, 260)):
            av = otTables.AxisValue()
            av.Format = 1
            av.AxisIndex = 0
            av.Flags = 0
            av.ValueNameID = nid
            av.Value = value
            _set_win_name(font, nid, f"Weight {int(value)}")
            stat.AxisValueArray.AxisValue.append(av)
        analysis = analyze_stat(Path("test.ttf"), font)
        f1_flags = [
            f for f in analysis.advisory_flags if f.flag_type == "format1_where_format3_expected"
        ]
        assert len(f1_flags) == 1
        assert "4 of 4" in f1_flags[0].detail

    def test_shared_name_id_summary(self):
        font = _minimal_vf()
        _add_stat_wght(font)
        stat = font["STAT"].table
        for value, nid in ((100.0, 257), (700.0, 259)):
            av = otTables.AxisValue()
            av.Format = 1
            av.AxisIndex = 0
            av.Flags = 0
            av.ValueNameID = nid
            av.Value = value
            _set_win_name(font, nid, f"W{int(value)}")
            stat.AxisValueArray.AxisValue.append(av)
        inst = font["fvar"].instances[0]
        inst.subfamilyNameID = 257
        analysis = analyze_stat(Path("test.ttf"), font)
        summary = [
            f for f in analysis.advisory_flags if f.flag_type == "shared_name_id_summary"
        ]
        per_id = [f for f in analysis.advisory_flags if f.flag_type == "shared_name_id"]
        assert len(summary) == 1
        assert len(per_id) == 0
        assert "257" in summary[0].detail

    def test_shared_name_id_internal(self):
        font = _minimal_vf()
        _set_win_name(font, 258, "Italic")
        stat = otTables.STAT()
        stat.Version = 0x00010002
        design = otTables.AxisRecordArray()
        ax = otTables.AxisRecord()
        ax.AxisTag = "ital"
        ax.AxisNameID = 258
        ax.AxisOrdering = 0
        design.Axis = [ax]
        stat.DesignAxisRecord = design
        av = otTables.AxisValue()
        av.Format = 1
        av.AxisIndex = 0
        av.Flags = 0
        av.ValueNameID = 258
        av.Value = 1.0
        av_array = otTables.AxisValueArray()
        av_array.AxisValue = [av]
        stat.AxisValueArray = av_array
        t = newTable("STAT")
        t.table = stat
        font["STAT"] = t
        analysis = analyze_stat(Path("test.ttf"), font)
        types = {f.flag_type for f in analysis.advisory_flags}
        assert "shared_name_id_internal" in types

    def test_fvar_axis_not_in_stat_advisory(self):
        font = _minimal_vf()
        axes = [("wght", 100, 400, 900, "Weight"), ("ital", 0, 0, 1, "Italic")]
        instances = [{"location": {"wght": 400, "ital": 0}, "stylename": "Regular"}]
        fb = FontBuilder(1024, isTTF=True)
        fb.setupGlyphOrder([".notdef"])
        fb.setupCharacterMap({})
        fb.setupGlyf({".notdef": glyf_module.Glyph()})
        fb.setupHorizontalMetrics({".notdef": (600, 0)})
        fb.setupHorizontalHeader(ascent=800, descent=-200)
        fb.setupOS2()
        fb.setupPost()
        fb.setupNameTable({"familyName": "Test", "styleName": "Regular"})
        fb.setupFvar(axes, instances)
        font = fb.font
        _add_stat_wght(font)
        analysis = analyze_stat(Path("test.ttf"), font)
        types = {f.flag_type for f in analysis.advisory_flags}
        assert "fvar_axis_not_in_stat" in types
