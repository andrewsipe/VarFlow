"""Discover ss/cv/size features in GSUB/GPOS, including those without label nameIDs."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Set, Tuple

from fontTools.ttLib import TTFont

from FontCore.core_logging_config import get_logger

logger = get_logger(__name__)

_RE_STYLESET = re.compile(r"^ss\d{2}$")
_RE_CHARVAR = re.compile(r"^cv\d{2}$")

# Primary label fields used for “has a label” detection (matches scanner coverage)
_SS_LABEL_FIELDS = ("UINameID", "FeatureNameID")
_CV_LABEL_FIELDS = ("LabelNameID", "TooltipTextNameID", "SampleTextNameID")
_SIZE_LABEL_FIELDS = ("SubFamilyID",)


@dataclass(frozen=True)
class FeaturePresence:
    """A label-capable OpenType feature present in GSUB or GPOS."""

    feature_tag: str
    table: str
    has_feature_params: bool
    label_name_ids: Tuple[int, ...]
    expected_fields: Tuple[str, ...]


def _collect_name_ids(params, fields: Tuple[str, ...]) -> Tuple[int, ...]:
    ids: List[int] = []
    for field in fields:
        val = getattr(params, field, None)
        if val is not None and int(val) > 0:
            ids.append(int(val))
    return tuple(ids)


def _expected_fields_for_tag(tag: str) -> Tuple[str, ...]:
    if _RE_STYLESET.match(tag):
        return _SS_LABEL_FIELDS
    if _RE_CHARVAR.match(tag):
        return _CV_LABEL_FIELDS + ("FirstParamUILabelNameID+n",)
    if tag == "size":
        return _SIZE_LABEL_FIELDS
    return ()


def scan_label_capable_features(font: TTFont) -> List[FeaturePresence]:
    """List ss##, cv##, and size features from GSUB/GPOS FeatureList."""
    out: List[FeaturePresence] = []
    seen: Set[Tuple[str, str]] = set()

    for table_tag in ("GSUB", "GPOS"):
        if table_tag not in font:
            continue
        try:
            feature_list = font[table_tag].table.FeatureList
            if feature_list is None:
                continue
            for rec in feature_list.FeatureRecord:
                tag = rec.FeatureTag
                if not (_RE_STYLESET.match(tag) or _RE_CHARVAR.match(tag) or tag == "size"):
                    continue
                key = (table_tag, tag)
                if key in seen:
                    continue
                seen.add(key)

                params = getattr(rec.Feature, "FeatureParams", None)
                expected = _expected_fields_for_tag(tag)
                if params is None:
                    out.append(
                        FeaturePresence(
                            feature_tag=tag,
                            table=table_tag,
                            has_feature_params=False,
                            label_name_ids=(),
                            expected_fields=expected,
                        )
                    )
                    continue

                if _RE_STYLESET.match(tag):
                    ids = _collect_name_ids(params, _SS_LABEL_FIELDS)
                elif _RE_CHARVAR.match(tag):
                    base_ids = list(_collect_name_ids(params, _CV_LABEL_FIELDS))
                    n = getattr(params, "NumNamedParameters", 0) or 0
                    first = getattr(params, "FirstParamUILabelNameID", None)
                    if first is not None and n > 0:
                        base_ids.extend(int(first) + o for o in range(n))
                    ids = tuple(base_ids)
                else:
                    ids = _collect_name_ids(params, _SIZE_LABEL_FIELDS)

                out.append(
                    FeaturePresence(
                        feature_tag=tag,
                        table=table_tag,
                        has_feature_params=True,
                        label_name_ids=ids,
                        expected_fields=expected,
                    )
                )
        except AttributeError:
            logger.debug("%s has no FeatureList", table_tag)
        except Exception as e:
            logger.warning("Error inventorying %s features: %s", table_tag, e)

    out.sort(key=lambda p: (p.table, p.feature_tag))
    return out


def labeled_feature_keys(ot_labels) -> Set[Tuple[str, str]]:
    """(table, feature_tag) pairs that already have scanned label nameIDs."""
    return {(rec.table, rec.feature_tag) for rec in ot_labels}
