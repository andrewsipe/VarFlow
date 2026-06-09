"""Data models for FeatureFlow analysis and processing."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from fontTools.ttLib import TTFont

from FontCore.core_ot_label_scanner import OTLabelRecord


class RowStatus(str, Enum):
    OK = "OK"
    BROKEN_REF = "BROKEN REF"
    ORPHAN = "ORPHAN"
    PROTECTED = "PROTECTED"
    ERROR = "ERROR"
    WARNING = "WARNING"
    NO_LABEL = "NO LABEL"


@dataclass
class ReportRow:
    feature: str
    table: str
    field: str
    name_id: int
    string_en: str
    status: RowStatus
    source: str = ""


@dataclass
class FontAnalysis:
    path: Path
    font: Optional[TTFont] = None
    is_variable: bool = False
    ot_labels: List[OTLabelRecord] = field(default_factory=list)
    used_nameids: Dict[int, str] = field(default_factory=dict)
    ot_name_ids: Set[int] = field(default_factory=set)
    protected_ids: Dict[int, str] = field(default_factory=dict)
    orphan_ids: Dict[int, str] = field(default_factory=dict)
    report_rows: List[ReportRow] = field(default_factory=list)
    blocking_errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    mac_record_count: int = 0
    contiguity_gaps: List[Tuple[int, int]] = field(default_factory=list)
    unlabeled_feature_count: int = 0
    labeled_feature_count: int = 0

    @property
    def has_blocking_errors(self) -> bool:
        return len(self.blocking_errors) > 0


@dataclass
class ReflowPlan:
    remap: Dict[int, int]
    block_start: int
    ot_ids_before: List[int]

    @property
    def is_identity(self) -> bool:
        return all(old == new for old, new in self.remap.items())


@dataclass
class FontProcessResult:
    path: Path
    output_path: Optional[Path] = None
    saved: bool = False
    mac_removed: int = 0
    ids_reflowed: int = 0
    labels_relabeled: int = 0
    orphans_removed: int = 0
    skipped: bool = False
    error: Optional[str] = None


@dataclass
class BatchSummary:
    fonts_processed: int = 0
    fonts_saved: int = 0
    fonts_errors: int = 0
    mac_removed_total: int = 0
    ids_reflowed_total: int = 0
    labels_relabeled_total: int = 0
    orphans_removed_total: int = 0
