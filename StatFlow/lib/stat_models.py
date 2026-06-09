"""Data models for StatFlow STAT analysis."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class StatAxisRecord:
    tag: str
    name_id: int
    name_en: str
    ordering: int


@dataclass
class StatAxisValue:
    axis_tag: str
    format: int
    name_id: int
    name_en: str
    value: Optional[float] = None
    range_min: Optional[float] = None
    range_max: Optional[float] = None
    nominal_value: Optional[float] = None
    linked_value: Optional[float] = None
    axis_value_pairs: Dict[str, float] = field(default_factory=dict)
    flags: int = 0
    elidable: bool = False


@dataclass
class StatFlag:
    severity: str
    flag_type: str
    axis_tag: Optional[str] = None
    name_id: Optional[int] = None
    detail: str = ""
    guidance: str = ""


@dataclass
class StatAnalysis:
    path: Path
    has_stat: bool = False
    is_variable: bool = False
    stat_version: Optional[int] = None
    elidable_fallback_name_id: Optional[int] = None
    elidable_fallback_label: str = ""
    axes: List[StatAxisRecord] = field(default_factory=list)
    axis_values: List[StatAxisValue] = field(default_factory=list)
    has_varstore: bool = False
    mac_record_count: int = 0
    required_flags: List[StatFlag] = field(default_factory=list)
    advisory_flags: List[StatFlag] = field(default_factory=list)
    stat_name_ids: List[int] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Section-shaped dict for future ``[stat]`` audit TOML."""
        return {
            "path": str(self.path),
            "has_stat": self.has_stat,
            "is_variable": self.is_variable,
            "stat_version": self.stat_version,
            "elidable_fallback_name_id": self.elidable_fallback_name_id,
            "elidable_fallback_label": self.elidable_fallback_label,
            "has_varstore": self.has_varstore,
            "mac_record_count": self.mac_record_count,
            "axes": [asdict(a) for a in self.axes],
            "axis_values": [asdict(v) for v in self.axis_values],
            "required_flags": [asdict(f) for f in self.required_flags],
            "advisory_flags": [asdict(f) for f in self.advisory_flags],
            "stat_name_ids": self.stat_name_ids,
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
