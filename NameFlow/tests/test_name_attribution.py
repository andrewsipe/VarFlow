"""Tests for NameFlow attribution engine."""

from __future__ import annotations

import sys
from pathlib import Path

from fontTools.fontBuilder import FontBuilder
from fontTools.ttLib.tables import _g_l_y_f as glyf_module

_NAMEFLOW = Path(__file__).resolve().parents[1]
if str(_NAMEFLOW) not in sys.path:
    sys.path.insert(0, str(_NAMEFLOW))

from lib.fontcore_path import ensure_fontcore_on_path  # noqa: E402

ensure_fontcore_on_path(_NAMEFLOW)

from lib.name_analysis import analyze_name  # noqa: E402
from lib.name_models import NameIDSource, NameRecordStatus  # noqa: E402


def _minimal_font() -> object:
    fb = FontBuilder(1024, isTTF=True)
    fb.setupGlyphOrder([".notdef"])
    fb.setupCharacterMap({})
    fb.setupGlyf({".notdef": glyf_module.Glyph()})
    fb.setupHorizontalMetrics({".notdef": (600, 0)})
    fb.setupHorizontalHeader(ascent=800, descent=-200)
    fb.setupOS2()
    fb.setupPost()
    fb.setupNameTable({"familyName": "Test", "styleName": "Regular"})
    return fb.font


def _set_win_name(font, name_id: int, string: str) -> None:
    font["name"].setName(string, name_id, 3, 1, 0x0409)


class TestNameAttribution:
    def test_orphan_above_255(self):
        font = _minimal_font()
        _set_win_name(font, 300, "Old Heading")
        analysis = analyze_name(Path("t.ttf"), font)
        rec = next(r for r in analysis.records if r.name_id == 300)
        assert rec.status == NameRecordStatus.ORPHAN
        assert NameIDSource.ORPHAN in rec.sources

    def test_mac_only_required(self):
        font = _minimal_font()
        font["name"].setName("Mac only", 256, 1, 0, 0)
        analysis = analyze_name(Path("t.ttf"), font)
        types = {f.flag_type for f in analysis.required_flags}
        assert "mac_only_name_record" in types

    def test_fvar_shared_with_standard(self):
        font = _minimal_font()
        axes = [("wght", 100, 400, 900, "Weight")]
        instances = [{"location": {"wght": 700}, "stylename": "Bold"}]
        fb = FontBuilder(1024, isTTF=True)
        fb.setupGlyphOrder([".notdef"])
        fb.setupCharacterMap({})
        fb.setupGlyf({".notdef": glyf_module.Glyph()})
        fb.setupHorizontalMetrics({".notdef": (600, 0)})
        fb.setupHorizontalHeader(ascent=800, descent=-200)
        fb.setupOS2()
        fb.setupPost()
        fb.setupNameTable({"familyName": "Test", "styleName": "Bold"})
        fb.setupFvar(axes, instances)
        font = fb.font
        inst = font["fvar"].instances[0]
        inst.subfamilyNameID = 2
        analysis = analyze_name(Path("t.ttf"), font)
        rec = next(r for r in analysis.records if r.name_id == 2)
        assert rec.status == NameRecordStatus.SHARED
        assert NameIDSource.FVAR_INSTANCE in rec.sources

    def test_missing_referenced_id(self):
        font = _minimal_font()
        from fontTools.ttLib import newTable
        from fontTools.ttLib.tables import otTables

        stat = otTables.STAT()
        stat.Version = 0x00010002
        design = otTables.AxisRecordArray()
        ax = otTables.AxisRecord()
        ax.AxisTag = "wght"
        ax.AxisNameID = 999
        ax.AxisOrdering = 0
        design.Axis = [ax]
        stat.DesignAxisRecord = design
        t = newTable("STAT")
        t.table = stat
        font["STAT"] = t
        fb2 = FontBuilder(1024, isTTF=True)
        axes = [("wght", 100, 400, 900, "Weight")]
        instances = [{"location": {"wght": 400}, "stylename": "Regular"}]
        fb2.setupGlyphOrder([".notdef"])
        fb2.setupCharacterMap({})
        fb2.setupGlyf({".notdef": glyf_module.Glyph()})
        fb2.setupHorizontalMetrics({".notdef": (600, 0)})
        fb2.setupHorizontalHeader(ascent=800, descent=-200)
        fb2.setupOS2()
        fb2.setupPost()
        fb2.setupNameTable({"familyName": "Test", "styleName": "Regular"})
        fb2.setupFvar(axes, instances)
        font = fb2.font
        font["STAT"] = t
        analysis = analyze_name(Path("t.ttf"), font)
        rec = next(r for r in analysis.records if r.name_id == 999)
        assert rec.status == NameRecordStatus.MISSING
        types = {f.flag_type for f in analysis.required_flags}
        assert "missing_name_record" in types
