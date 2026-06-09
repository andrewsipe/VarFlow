"""Known OpenType axis conventions for STAT guidance."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass(frozen=True)
class AxisConvention:
    tag: str
    full_name: str
    expected_min: float
    expected_max: float
    typical_formats: List[int]
    linked_counterpart: Optional[str] = None
    notes: str = ""


KNOWN_AXES: Dict[str, AxisConvention] = {
    "wght": AxisConvention(
        tag="wght",
        full_name="Weight",
        expected_min=100,
        expected_max=900,
        typical_formats=[1, 3],
        notes="Standard weight stops: 100–900. Values outside this range are "
        "valid but may not map correctly to CSS font-weight.",
    ),
    "wdth": AxisConvention(
        tag="wdth",
        full_name="Width",
        expected_min=50,
        expected_max=200,
        typical_formats=[1, 3],
        notes="Percentage-based. 100 = normal. usWidthClass maps to 9 stops.",
    ),
    "ital": AxisConvention(
        tag="ital",
        full_name="Italic",
        expected_min=0,
        expected_max=1,
        typical_formats=[1, 3],
        linked_counterpart="ital",
        notes="Binary axis: 0=Roman, 1=Italic. Format 3 links Roman to Italic.",
    ),
    "slnt": AxisConvention(
        tag="slnt",
        full_name="Slant",
        expected_min=-90,
        expected_max=90,
        typical_formats=[1, 2],
        notes="Negative values = clockwise slant. 0 = upright.",
    ),
    "opsz": AxisConvention(
        tag="opsz",
        full_name="Optical Size",
        expected_min=6,
        expected_max=144,
        typical_formats=[2],
        notes="Format 2 (range) is conventional for opsz.",
    ),
    "grad": AxisConvention(
        tag="grad",
        full_name="Grade",
        expected_min=-1,
        expected_max=1,
        typical_formats=[1, 2],
        notes="Grade adjusts apparent weight without changing spacing.",
    ),
}


def convention_for_tag(tag: str) -> Optional[AxisConvention]:
    return KNOWN_AXES.get(tag)
