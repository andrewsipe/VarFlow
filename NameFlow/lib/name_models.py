"""Data models for NameFlow name table analysis."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


class NameIDSource(str, Enum):
    OT_FEATURE = "ot_feature"
    STAT_AXIS = "stat_axis"
    STAT_VALUE = "stat_value"
    STAT_ELIDABLE = "stat_elidable"
    FVAR_AXIS = "fvar_axis"
    FVAR_INSTANCE = "fvar_instance"
    FVAR_PS = "fvar_ps"
    STANDARD = "standard"
    ORPHAN = "orphan"
    UNKNOWN = "unknown"


class NameRecordStatus(str, Enum):
    OK = "ok"
    ORPHAN = "orphan"
    SHARED = "shared"
    MISSING = "missing"
    MAC_ONLY = "mac_only"
    BELOW_256 = "below_256"


SOURCE_LABELS: Dict[NameIDSource, str] = {
    NameIDSource.OT_FEATURE: "ot_feature",
    NameIDSource.STAT_AXIS: "stat_axis",
    NameIDSource.STAT_VALUE: "stat_value",
    NameIDSource.STAT_ELIDABLE: "stat_elidable",
    NameIDSource.FVAR_AXIS: "fvar_axis",
    NameIDSource.FVAR_INSTANCE: "fvar_instance",
    NameIDSource.FVAR_PS: "fvar_ps",
    NameIDSource.STANDARD: "standard",
    NameIDSource.ORPHAN: "orphan",
    NameIDSource.UNKNOWN: "unknown",
}


@dataclass
class NameRecord:
    name_id: int
    platforms: List[str]
    has_windows: bool
    has_mac: bool
    label_en: str
    sources: List[NameIDSource]
    is_shared: bool
    shared_note: str
    status: NameRecordStatus


@dataclass
class NameFlag:
    severity: str
    flag_type: str
    name_id: Optional[int] = None
    detail: str = ""
    guidance: str = ""


@dataclass
class NameAnalysis:
    path: Path
    is_variable: bool = False
    records: List[NameRecord] = field(default_factory=list)
    mac_record_count: int = 0
    required_flags: List[NameFlag] = field(default_factory=list)
    advisory_flags: List[NameFlag] = field(default_factory=list)
    total_above_255: int = 0
    ot_feature_count: int = 0
    stat_count: int = 0
    fvar_count: int = 0
    orphan_count: int = 0
    shared_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": str(self.path),
            "is_variable": self.is_variable,
            "mac_record_count": self.mac_record_count,
            "total_above_255": self.total_above_255,
            "ot_feature_count": self.ot_feature_count,
            "stat_count": self.stat_count,
            "fvar_count": self.fvar_count,
            "orphan_count": self.orphan_count,
            "shared_count": self.shared_count,
            "records": [
                {
                    **asdict(r),
                    "sources": [s.value for s in r.sources],
                    "status": r.status.value,
                }
                for r in self.records
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
    fonts_errors: int = 0
