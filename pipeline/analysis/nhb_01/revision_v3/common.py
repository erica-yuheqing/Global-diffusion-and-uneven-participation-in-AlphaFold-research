"""Immutable inputs and exact output helpers for plan3."""
from pathlib import Path
import hashlib,json
import numpy as np
import pandas as pd

MOD=Path(__file__).resolve().parent;ROOT=MOD.parents[2]
PREV=MOD.parent/'revision_v2/figure1_plan2_final_v1'
RAW=MOD.parent/'revision_v1/figure1_revision_final_v2'
HISTORY=MOD.parent/'revision_v1/figure1_revision_reading_package_v4'
PLAN=Path('/historical-workspace/Library/Mobile Documents/iCloud~md~obsidian/Documents/Jaden/01_Projects/IGN/Revision/figure1-revision-plan-3.md')
OUT=MOD/'figure1_plan3_final_v1'
BLUE='#4865BC';ORANGE='#D17A26';GRAY='#565C65';MUTED='#626970'
ORDER=['US','CN','JP','DE','GB','IN','FR','KR','IT','CA','BR','ES','AU','IR','RU','NL','PL','TR','CH','TW']
SPECS=['count_only','count_composition','count_composition_known_country'];SEED=20261025;REPS=2000
def require(x,m):
    if not bool(x):raise ValueError(m)
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
def save(out,n,x):x.to_parquet(out/'tables'/f'{n}.parquet',index=False);x.to_csv(out/'tables'/f'{n}.csv',index=False)
def load(out,n):return pd.read_parquet(out/'tables'/f'{n}.parquet')
def gini(x):
    x=np.asarray(x,dtype=float);require(x.ndim>=1 and x.shape[-1]>0,'Empty credit vector')
    x=np.sort(x,axis=-1);n=x.shape[-1];total=x.sum(axis=-1)
    require(np.isfinite(x).all() and (x>=0).all(),'Invalid Gini credits')
    return np.divide(x@(2*np.arange(1,n+1)-n-1),n*total,out=np.full(total.shape,np.nan),where=total>0)

