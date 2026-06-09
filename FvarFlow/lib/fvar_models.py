"""Data models for FvarFlow fvar analysis."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


RESERVED_NAME_IDS: Dict[int, str] = {
    1: "Family name",
    2: "Subfamily",
    6: "PostScript name",
    16: "Typographic family",
    17: "Typographic subfamily",
}


@dataclass
class StatCoverageResult:
    covered: bool
    missing_axes: List[str] = field(default_factory=list)
    partial: bool = False


@dataclass
class FvarAxis:
    tag: str
    name_id: int
    name_en: str
    min_value: float
    default_value: float
    max_value: float
    in_stat: bool


@dataclass
class FvarInstance:
    index: int
    name_id: int
    name_en: str
    postscript_name_id: Optional[int]
    postscript_name: str
    coordinates: Dict[str, float]
    uses_shared_id: bool
    shared_id_note: str
    stat_coverage: StatCoverageResult


@dataclass
class FvarFlag:
    severity: str
    flag_type: str
    instance_index: Optional[int] = None
    axis_tag: Optional[str] = None
    detail: str = ""
    guidance: str = ""


@dataclass
class FvarAnalysis:
    path: Path
    has_fvar: bool = False
    is_variable: bool = False
    axes: List[FvarAxis] = field(default_factory=list)
    instances: List[FvarInstance] = field(default_factory=list)
    required_flags: List[FvarFlag] = field(default_factory=list)
    advisory_flags: List[FvarFlag] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": str(self.path),
            "has_fvar": self.has_fvar,
            "is_variable": self.is_variable,
            "axes": [asdict(a) for a in self.axes],
            "instances": [
                {
                    **asdict(i),
                    "stat_coverage": asdict(i.stat_coverage),
                }
                for i in self.instances
            ],
            "required_flags": [asdict(f) for f in self.required_flags],
            "advisory_flags": [asdict(f) for f in self.advisory_flags],
        }


@dataclass
class FontProcessResult:
    path: Path
    skipped: bool = False
    error: Optional[str] = None


@dataclass
class BatchSummary:
    fonts_processed: int = 0
    fonts_analyzed: int = 0
    fonts_skipped: int = 0
    fonts_errors: int = 0
