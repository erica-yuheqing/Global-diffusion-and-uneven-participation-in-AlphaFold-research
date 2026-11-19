"""Shared, bounded, local-only I/O and fixed protocol for Figure 2 plan 3."""
from pathlib import Path
import hashlib
import json
import sys
import numpy as np
import pandas as pd
import duckdb

MODULE = Path(__file__).resolve().parent
ROOT = MODULE.parents[2]
F1 = ROOT / 'analysis/nhb_01/revision_v1/figure1_revision_final_v2'
UP = ROOT / 'analysis/nhb_revision_v1/out_v2'
OLD = ROOT / 'analysis/nhb_02/revision_v3/figure2_annotated_v1'
PLAN = Path('/historical-workspace/Library/Mobile Documents/iCloud~md~obsidian/Documents/Jaden/01_Projects/IGN/Revision/figure2-revision-plan-3.md')
OUT = MODULE / 'figure2_plan3_final_v1'
GROUPS = ['L', 'M', 'H']
CONTEXTS = ['All', 'Low', 'Middle', 'High']
YEARS = np.arange(2020, 2026)
SEED = 20261024

def require(ok, message):
    if not ok:
        raise ValueError(message)

def clean(x):
    if isinstance(x, dict): return {str(k): clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)): return [clean(v) for v in x]
    if isinstance(x, (np.bool_,)): return bool(x)
    if isinstance(x, (np.integer,)): return int(x)
    if isinstance(x, (float, np.floating)): return float(x) if np.isfinite(x) else None
    if isinstance(x, (Path, pd.Timestamp)): return str(x)
    if x is pd.NA: return None
    return x

def dump(path, obj):
    Path(path).write_text(json.dumps(clean(obj), ensure_ascii=False, indent=2, allow_nan=False) + '\n')

def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda: f.read(1024 * 1024), b''): h.update(b)
    return h.hexdigest()

def lit(x): return "'" + str(x).replace("'", "''") + "'"
def save(out, name, df, csv=True):
    df.to_parquet(out / 'tables' / (name + '.parquet'), index=False)
    if csv: df.to_csv(out / 'tables' / (name + '.csv'), index=False)
def load(out, name): return pd.read_parquet(out / 'tables' / (name + '.parquet'))

def connect(out):
    c = duckdb.connect()
    c.execute("SET threads=1; SET memory_limit='4GB'; SET preserve_insertion_order=false; SET max_temp_directory_size='8GB'")
    c.execute('SET temp_directory=' + lit(out / 'scratch'))
    return c

def tertiles(values):
    v = np.asarray(values)
    require(len(v) > 0 and np.isfinite(v).all(), 'Invalid baseline grouping values')
    cuts = np.quantile(v, [1/3, 2/3], method='linear')
    g = np.searchsorted(cuts, v, side='left')
    valid = cuts[0] < cuts[1] and len(np.unique(g)) == 3
    return g, cuts, bool(valid)

def pins():
    selections = [(F1, 'run_manifest.json', ['derived_study_records.parquet']),
                  (UP, 'prepare_manifest.json', ['work_institutions.parquet', 'work_institution_membership.parquet', 'work_countries.parquet', 'country_registry.parquet']),
                  (OLD, 'run_manifest.json', ['summary.json', 'tables/entry_cohort_registry.parquet'])]
    records = []
    for directory, manifest_name, names in selections:
        mp = directory / manifest_name
        manifest = json.loads(mp.read_text())
        outputs = manifest.get('outputs', manifest.get('exports', {}))
        for name in names:
            p = directory / name
            require(p.is_file() and not p.is_symlink(), 'Invalid source: ' + str(p))
            digest = sha(p)
            require(digest == outputs[name]['sha256'], 'Source differs from frozen hash: ' + str(p))
            records.append(dict(path=str(p), sha256=digest, bytes=p.stat().st_size))
        records.append(dict(path=str(mp), sha256=sha(mp), bytes=mp.stat().st_size))
    for p in [PLAN, MODULE / 'README.md']:
        records.append(dict(path=str(p), sha256=sha(p), bytes=p.stat().st_size))
    return records

def configuration():
    import scipy, pyarrow, matplotlib, PIL
    return dict(schema='figure2-plan3-v1', seed=SEED, pilot_seed=SEED+1,
                baseline_years=[2015, 2019], main_years=[2020, 2025], endpoints=[2021, 2025],
                main_minimum_per_group=20, sensitivity_minima=[10, 30], main_replicates=5000,
                max_replicates=10000, pilot_replicates=200, mcse_extension_threshold_pp=.05,
                field='primary_subfield_id; unknown retained as named stratum',
                strata=['field', 'year', 'country_set'], context='2015-2019 unique participating studies, country tertiles',
                country='unique baseline country only', weighting='equal country, not equal context',
                uncertainty='centered conditional benchmark 95% reference range; not sampling CI',
                software=dict(python=sys.version, numpy=np.__version__, pandas=pd.__version__, scipy=scipy.__version__,
                              duckdb=duckdb.__version__, pyarrow=pyarrow.__version__, matplotlib=matplotlib.__version__, pillow=PIL.__version__))
