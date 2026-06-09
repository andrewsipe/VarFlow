# VarFlow — Variable Font Table Analysis Suite

Terminal tools for variable font OpenType tables. Each script lives in its own subdirectory; **all scripts share one [FontCore](https://github.com/andrewsipe/FontCore) at the VarFlow repo root** — not per-script symlinks or submodules.

| Script | Table | Scope |
|--------|-------|-------|
| [FeatureFlow](FeatureFlow/) | GSUB/GPOS | OT feature label nameIDs (audit + modify) |
| [StatFlow](StatFlow/) | STAT | Style attributes analysis (read-only) |
| [FvarFlow](FvarFlow/) | fvar | Variation axes and named instances (read-only) |
| [NameFlow](NameFlow/) | name | Cross-table nameID inventory (read-only) |

## FontCore (suite root only)

```
VarFlow/
  FontCore/          ← submodule on GitHub; symlink in monorepo
  FeatureFlow/
  StatFlow/
  FvarFlow/
  NameFlow/
```

Each script’s `lib/fontcore_path.py` walks **up** from its own directory until it finds `FontCore/`. No FontCore link is needed inside `StatFlow/`, `FvarFlow/`, etc.

**Standalone clone** ([github.com/andrewsipe/VarFlow](https://github.com/andrewsipe/VarFlow)):

```bash
git clone https://github.com/andrewsipe/VarFlow.git
cd VarFlow
git submodule update --init --recursive
cd StatFlow   # or FvarFlow, NameFlow, FeatureFlow
pip install -r requirements.txt
```

**Monorepo** — one symlink at the VarFlow root:

```bash
cd VarFlow
ln -sf ../FontCore FontCore   # if missing
```

Then run any script from its subdirectory as usual.

## Analysis phase (current)

StatFlow, FvarFlow, and NameFlow are read-only reporters:

```bash
cd StatFlow
python StatFlow.py font.ttf
python StatFlow.py ../fonts --recursive

cd ../FvarFlow
python FvarFlow.py font.ttf --verbose

cd ../NameFlow
python NameFlow.py font.ttf
```

Cross-script consistency check (optional):

```bash
python verify_cross_script.py /path/to/font.ttf
```

Future phases will add unified `.audit.toml` output and modification workflows.
