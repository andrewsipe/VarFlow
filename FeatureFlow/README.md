# FeatureFlow — OT Feature Label Manager

Audit, prune Mac name records, reflow OpenType feature label nameIDs (GSUB/GPOS FeatureParams for `ss##`, `cv##`, `size`), and optionally relabel or remove orphan name IDs.

**Report-only** also lists stylistic sets and other label-capable features that exist in GSUB/GPOS but have no label nameIDs yet (`NO LABEL`). That inventory is informational; this tool does not assign new labels to unlabeled features.

When you run without `--report-only`, fonts that need **no** Mac prune, reflow, relabel, or orphan work exit immediately (`No changes needed — file left unchanged`) without save prompts. If changes are pending, a **change diff** table lists each action with before/after values before you confirm.

## Setup

From the monorepo, `FontCore` is a symlink to the shared library:

```bash
cd FeatureFlow
ln -sf ../../FontCore FontCore   # if missing
pip install -r requirements.txt
```

For a standalone clone, place this repo beside [FontCore](https://github.com/andrewsipe/FontCore.git) or use `git submodule add` instead of the symlink.

## Usage

```bash
python FeatureFlow.py /path/to/fonts --recursive --report-only
python FeatureFlow.py font.otf --dry-run          # preview plan; no writes
python FeatureFlow.py font.otf --yes              # apply without confirmation prompts
python FeatureFlow.py font.otf --output-dir ./out --suffix=-Fixed
python FeatureFlow.py font.otf --relabel-map labels.json --yes
python FeatureFlow.py font.otf --relabel          # optional interactive rename
```

### Options

Run `python FeatureFlow.py --help` for full detail and examples. Highlights:

| Flag | Description |
|------|-------------|
| `--report-only` | Inventory only; no writes |
| `--dry-run` | Planned changes + diff; no writes |
| `--relabel` | Interactive rename session (`q` or Enter finishes; edits kept) |
| `--relabel-map` | Batch JSON `{"ss01": "Label"}` (wins over `--relabel` if both passed) |
| `--no-prune-mac` | Keep Mac name records (pruned by default) |
| `--remove-orphans` | Remove orphan nameIDs >255 without per-ID prompts |
| `--yes` | Auto-confirm preflight, overwrite, orphans (not the `--relabel` session) |

## Reflow behavior

- OT label nameIDs are reflowed only when gaps, protected collisions, orphans in the OT range, or non-OT high nameIDs require it. Contiguous blocks already at the tail of the table are left alone.
- Orphan nameIDs in the OT numeric range can trigger reflow (remove orphans first, or let reflow compact around them).
- `--no-prune-mac` keeps Mac records in the name table and includes them when computing the reflow target block.
- Dry-run / preflight reflow preview uses `exclude_mac=True` when Mac prune is scheduled, so the diff matches the post-prune apply path.

## Tests

```bash
cd FeatureFlow
python -m pytest tests -q
```

## Out of scope

- **Creating** labels for features that have no FeatureParams / nameIDs (report shows them as `NO LABEL` only)
- STAT / fvar nameID reflow → [Variable_Instancer/VariableFont_TableEditor.py](../../Variable_Instancer/VariableFont_TableEditor.py)
- nameID 1–25 → [FontNameID](../../FontNameID/)
- Non–en-US name records beyond logging (flag only)

## Related

- [FontCore](../../FontCore/) — `scan_ot_label_nameids`, `audit_nameids`, console and file helpers
