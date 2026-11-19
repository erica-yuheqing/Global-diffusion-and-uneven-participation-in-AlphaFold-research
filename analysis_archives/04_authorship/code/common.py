from pathlib import Path
import hashlib,json
import numpy as np
import pandas as pd
import duckdb
ROOT=Path(__file__).resolve().parents[1]
GROUPS=['higher','middle','lower','outside'];CORPORA=['AF','reference'];KEY=['publication_year','work_type','primary_subfield_id']
B=2000;SEED=20261029
def require(ok,message):
    if not bool(ok):raise ValueError(message)
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
def q(p):return "'"+str(p).replace("'","''")+"'"
def connect():
    c=duckdb.connect();c.execute("SET threads=1;SET memory_limit='3GB';SET max_temp_directory_size='8GB';SET preserve_insertion_order=false")
    (ROOT/'scratch').mkdir(exist_ok=True);c.execute('SET temp_directory='+q(ROOT/'scratch'));return c
def read(name):return pd.read_csv(ROOT/'inputs/handoff/06_data/existing'/name,keep_default_na=False,low_memory=False)
def norm(name):return pd.read_parquet(ROOT/'inputs/normalized'/name)
def save(name,data):
    data.to_parquet(ROOT/'tables'/f'{name}.parquet',index=False)
    data.to_csv(ROOT/'tables'/f'{name}.csv',index=False)
def div(a,b):
    a,b=np.broadcast_arrays(np.asarray(a,float),np.asarray(b,float));return np.divide(a,b,out=np.full(a.shape,np.nan),where=b>0)
def support(m,cell=KEY):
    s=m.dropna(subset=cell).groupby(cell+['corpus'],observed=True).size().unstack(fill_value=0)
    for c in CORPORA:
        if c not in s:s[c]=0
    s=s.reset_index();s['supported']=(s.AF>=1)&(s.reference>=5);s['w_AF']=np.where(s.supported,1.,0.);s['w_reference']=np.where(s.supported,s.AF/s.reference.replace(0,np.nan),0.);return s
def add_weights(m,s,cell=KEY):
    z=m.merge(s[cell+['supported','w_AF','w_reference']],on=cell,how='left',validate='many_to_one');z['supported']=z.supported.fillna(False)
    z['weight']=np.where(z.corpus.eq('AF'),z.w_AF,z.w_reference);z['weight']=z.weight.fillna(0.);return z
