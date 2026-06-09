# VarFlow — Variable Font Table Analysis Suite

Terminal analysis tools for variable font OpenType tables. Each script is a standalone package under this directory; they share [FontCore](../FontCore/) from the monorepo root.

| Script | Table | Scope |
|--------|-------|-------|
| [FeatureFlow](FeatureFlow/) | GSUB/GPOS | OT feature label nameIDs (audit + modify) |
| [StatFlow](StatFlow/) | STAT | Style attributes analysis (read-only) |
| [FvarFlow](FvarFlow/) | fvar | Variation axes and named instances (read-only) |
| [NameFlow](NameFlow/) | name | Cross-table nameID inventory (read-only) |

## Setup

From the monorepo, each script resolves FontCore via `lib/fontcore_path.py` (walks up to the repo root).

**Standalone clone** ([VarFlow](https://github.com/andrewsipe/VarFlow)) — FontCore is a submodule at the repo root:

```bash
git clone https://github.com/andrewsipe/VarFlow.git
cd VarFlow
git submodule update --init --recursive
cd StatFlow   # or FvarFlow, NameFlow, FeatureFlow
pip install -r requirements.txt
```

**Monorepo** — optional local symlink at repo root:

```bash
cd VarFlow
ln -sf ../FontCore FontCore
```

## Analysis phase (current)

StatFlow, FvarFlow, and NameFlow are read-only reporters:

```bash
python StatFlow.py font.ttf
python FvarFlow.py ./fonts --recursive
python NameFlow.py font.ttf --verbose
```

Future phases will add unified `.audit.toml` output and modification workflows.
