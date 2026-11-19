"""Portable frozen inputs and bounded, append-only release helpers."""
from pathlib import Path
import json,hashlib
import numpy as np
import pandas as pd
GROUPS=['L','M','H'];CONTEXTS=['All','High','Middle','Low']
INST={'L':'#6C86B3','M':'#4865BC','H':'#183B75'}
CTX={'All':'#363C43','High':'#9B4C26','Middle':'#725599','Low':'#167B6A'}
MARK={'L':'o','M':'s','H':'^'}
LABEL={'L':'Lower-output institutions','M':'Middle-output institutions','H':'Higher-output institutions'}
def require(ok,msg):
    if not bool(ok):raise ValueError(msg)
def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()
def clean(x):
    if isinstance(x,dict):return {str(k):clean(v) for k,v in x.items()}
    if isinstance(x,(list,tuple,np.ndarray)):return [clean(v) for v in x]
    if isinstance(x,(bool,np.bool_)):return bool(x)
    if isinstance(x,(int,np.integer)):return int(x)
    if isinstance(x,(float,np.floating)):return float(x) if np.isfinite(x) else None
    if isinstance(x,Path):return str(x)
    return x
def dump(p,x):Path(p).write_text(json.dumps(clean(x),ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def read(out,name,kind='frozen'):return pd.read_csv(out/'inputs'/kind/name,keep_default_na=False,low_memory=False)
def table(out,name):return pd.read_csv(out/'tables'/name,keep_default_na=False,low_memory=False)
def save(out,name,x):x.to_csv(out/'tables'/name,index=False)
def truth(s):return s.astype(str).str.lower().eq('true')
def number(s):return pd.to_numeric(s,errors='coerce')
def protocol():
    return {'version':'Finding2_v7_20261029','primary_population':'B2_48010_68','baseline':'2015–2019',
      'cumulative_years':list(range(2020,2026)),'annual_years':list(range(2021,2026)),
      'main_weighting':'equal_country','tertiles':'type7_boundary_ties_lower_no_split','minimum_domestic_group':20,
      'new_simulations':False,'frozen_replicates':5000,'historical_seed':20261024,
      'continuous_model':{'family':'binomial_logit','likelihood_weights':'one per institution',
        'basis':'restricted_cubic_spline','knots_quantiles':[.05,.35,.65,.95],
        'knot_collision_rule':'sorted unique original knots; 3 unique -> 3-knot RCS; 2 -> linear',
        'country_fixed_effects':True,'percentile':'(within-country average rank - 0.5)/N_country',
        'outcome':'first_pool_AF_year <= 2025; missing = no confirmed pool publication observed',
        'standardization':'equal mean of 68 country predictions at each common x',
        'uncertainty':'none_point_estimates_only_no_independent_institution_CI',
        'primary_solver':'Newton with exact gradient/Hessian and backtracking',
        'max_iterations':100,'normalized_score_tolerance':1e-9,
        'fallback':'if rank failure/separation/nonconvergence, L2 all coefficients lambda=1e-6; record failure',
        'prediction_grid_points':201,'bins':'10 fixed percentile bins; tied values share bin; empty retained',
        'no_significance_selection':True},
      'scope':'observed publication coverage, not resources/capability/causal AF effect',
      'numbering':'local ED3/ED4 and S8–S10; no S7/ED5; global ED collision explicitly unresolved'}
