"""Tests for reflow block_start and reflow_needed logic."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fontTools.fontBuilder import FontBuilder
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables import _g_l_y_f as glyf_module

_FEATUREFLOW = Path(__file__).resolve().parents[1]
if str(_FEATUREFLOW) not in sys.path:
    sys.path.insert(0, str(_FEATUREFLOW))

from lib.fontcore_path import ensure_fontcore_on_path  # noqa: E402

ensure_fontcore_on_path(_FEATUREFLOW)

from lib.models import FontAnalysis  # noqa: E402
from lib.reflow import (  # noqa: E402
    _reflow_block_start,
    build_reflow_plan,
    reflow_needed,
)


def _minimal_font() -> TTFont:
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


def _analysis(ot_ids: set[int], *, gaps: list | None = None) -> FontAnalysis:
    a = FontAnalysis(path=Path("test.ttf"))
    a.ot_name_ids = ot_ids
    a.contiguity_gaps = gaps or []
    a.protected_ids = {}
    return a


def _set_win_name(font: TTFont, name_id: int, string: str) -> None:
    font["name"].setName(string, name_id, 3, 1, 0x0409)


class TestReflowBlockStart:
    def test_contiguous_ot_at_tail_block_start_256(self):
        font = _minimal_font()
        ot = {256, 257, 258}
        for nid in ot:
            _set_win_name(font, nid, f"Label {nid}")
        assert _reflow_block_start(font, ot, exclude_mac=False) == 256

    def test_non_ot_high_sets_block_above(self):
        font = _minimal_font()
        ot = {256, 257, 258}
        for nid in ot:
            _set_win_name(font, nid, f"Label {nid}")
        _set_win_name(font, 300, "STAT label")
        assert _reflow_block_start(font, ot, exclude_mac=False) == 301

    def test_mac_high_ignored_when_exclude_mac(self):
        font = _minimal_font()
        ot = {256, 257, 258}
        for nid in ot:
            _set_win_name(font, nid, f"Label {nid}")
        font["name"].setName("Mac only", 500, 1, 0, 0)
        assert _reflow_block_start(font, ot, exclude_mac=True) == 256
        assert _reflow_block_start(font, ot, exclude_mac=False) == 501


class TestReflowNeeded:
    def test_contiguous_ot_only_not_needed(self):
        font = _minimal_font()
        for nid in (256, 257, 258):
            _set_win_name(font, nid, "x")
        analysis = _analysis({256, 257, 258})
        assert reflow_needed(font, analysis) is False

    def test_gap_in_ot_ids_needed(self):
        font = _minimal_font()
        _set_win_name(font, 256, "a")
        _set_win_name(font, 258, "b")
        analysis = _analysis({256, 258}, gaps=[(257, 257)])
        assert reflow_needed(font, analysis) is True

    def test_orphan_in_ot_range_needed(self):
        font = _minimal_font()
        _set_win_name(font, 256, "a")
        _set_win_name(font, 257, "orphan")
        _set_win_name(font, 258, "b")
        analysis = _analysis({256, 258})
        assert reflow_needed(font, analysis) is True

    def test_stat_above_ot_needed(self):
        font = _minimal_font()
        for nid in (256, 257, 258):
            _set_win_name(font, nid, "ot")
        _set_win_name(font, 300, "axis")
        analysis = _analysis({256, 257, 258})
        assert reflow_needed(font, analysis) is True


class TestBuildReflowPlan:
    def test_identity_when_already_at_tail(self):
        font = _minimal_font()
        for nid in (256, 257, 258):
            _set_win_name(font, nid, "x")
        analysis = _analysis({256, 257, 258})
        plan = build_reflow_plan(font, analysis)
        assert plan.is_identity

    def test_gap_compacts_to_contiguous_block(self):
        font = _minimal_font()
        _set_win_name(font, 256, "a")
        _set_win_name(font, 258, "b")
        analysis = _analysis({256, 258}, gaps=[(257, 257)])
        plan = build_reflow_plan(font, analysis)
        assert plan.remap[256] == 256
        assert plan.remap[258] == 257

    def test_reflow_above_stat(self):
        font = _minimal_font()
        for nid in (256, 257, 258):
            _set_win_name(font, nid, "ot")
        _set_win_name(font, 300, "stat")
        analysis = _analysis({256, 257, 258})
        plan = build_reflow_plan(font, analysis)
        assert plan.block_start == 301
        assert plan.remap[256] == 301
        assert plan.remap[257] == 302
        assert plan.remap[258] == 303
