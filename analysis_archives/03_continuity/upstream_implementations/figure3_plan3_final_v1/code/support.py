from pathlib import Path
import hashlib
import json
import numpy as np
import pandas as pd
import duckdb
import importlib.util

MODULE=Path(__file__).resolve().parent
ROOT=MODULE.parents[2]
UP=ROOT/'analysis/nhb_revision_v1'
F1=ROOT/'analysis/nhb_01/revision_v1/figure1_revision_final_v2'
F2=ROOT/'analysis/nhb_02/revision_v3/figure2_annotated_v1'
OLD=ROOT/'analysis/nhb_03/revision_v1/figure3_revision_final_v1'
PREVIOUS=ROOT/'analysis/nhb_03/revision_v6/figure3_annotation_final_v6'
PLAN=Path('/historical-workspace/Library/Mobile Documents/iCloud~md~obsidian/Documents/Jaden/01_Projects/IGN/Revision/figure3-recision-plan-3.md')
OUT=MODULE/'figure3_plan3_final_v1'
SEED=20261023
MODES=['precomputed_structure_use','prediction_run','method_or_tool_development','prediction_evaluation_or_validation']
LABELS=['Precomputed structures','Prediction runs','Method / tool development','Evaluation / validation']

def require(ok,message):
    if not ok:raise ValueError(message)

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()

def clean(x):
    if isinstance(x,dict):return {str(k):clean(v) for k,v in x.items()}
    if isinstance(x,(tuple,list)):return [clean(v) for v in x]
    if isinstance(x,(np.integer,)):return int(x)
    if isinstance(x,(np.bool_,)):return bool(x)
    if isinstance(x,(float,np.floating)):return float(x) if np.isfinite(x) else None
    if isinstance(x,(Path,pd.Timestamp)):return str(x)
    if x is pd.NA:return None
    return x

def dump(path,obj):path.write_text(json.dumps(clean(obj),ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def lit(path):return "'"+str(path).replace("'","''")+"'"
def save(out,name,df,csv=True):
    df.to_parquet(out/'tables'/f'{name}.parquet',index=False)
    if csv:df.to_csv(out/'tables'/f'{name}.csv',index=False)
def load(out,name):return pd.read_parquet(out/'tables'/f'{name}.parquet')
def module(name,path):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def oldcode():return module('f3_verified_events',OLD.parent/'data.py')

def monthly_history(events,scale):
    """Exact calendar-month windows, including leap-year February month ends."""
    e=events.copy();e['event_date']=pd.to_datetime(e.event_date).dt.to_period('M').dt.to_timestamp('M')
    h,z=oldcode().history(e,scale)
    first=pd.to_datetime(h.first_date).dt.to_period('M')
    h['month12_end']=(first+12).dt.to_timestamp('M')
    h['window_end']=(first+24).dt.to_timestamp('M')
    lookup=h.set_index('institution_id')
    for name in ['month12_end','window_end']:z[name]=z.institution_id.map(lookup[name])
    end=z.window_end.clip(upper=pd.Timestamp('2025-12-31'))
    def overlap(year):
        y=pd.to_numeric(year,errors='coerce').astype('Int64').astype('string')
        lo=pd.to_datetime(y+'-01-01',errors='coerce');hi=pd.to_datetime(y+'-12-31',errors='coerce')
        return hi.gt(z.first_date)&lo.le(end)
    unknown=(z.possible_af_only & z.event_date.gt(z.first_date)&z.event_date.le(end)) | (
      (z.confirmed_af|z.possible_af_only)&z.event_date.isna()&overlap(z.earliest_version_evidence_year)) | (
      z.undated_confirmed_versions.gt(0)&z.event_date.notna()&z.event_date.ne(z.first_date)&overlap(z.earliest_undated_confirmed_year))
    z['window_uncertainty']=unknown.astype(int)
    z['bin1']=z.confirmed_af & z.event_date.gt(z.first_date)&z.event_date.le(z.month12_end)&z.event_date.le(end)
    z['bin2']=z.confirmed_af & z.event_date.gt(z.month12_end)&z.event_date.le(end)
    totals=z.groupby('institution_id').agg(window_uncertainty=('window_uncertainty','sum'),bin1=('bin1','sum'),bin2=('bin2','sum'))
    h=h.drop(columns=['window_uncertainty','bin1','bin2']).merge(totals,on='institution_id',how='left',validate='one_to_one')
    for name in ['window_uncertainty','bin1','bin2']:h[name]=h[name].fillna(0).astype(int)
    h['administratively_complete']=h.window_end.le(pd.Timestamp('2025-12-31'))
    h['eligible']=h.entry_resolved&~h.pre_main&h.first_date.dt.year.ge(2020)&h.administratively_complete&h.window_uncertainty.eq(0)
    h['eligible_fixed']=h.eligible&h.fixed_cohort_ge1
    for name,values in [('repeat',(h.bin1+h.bin2).gt(0)),('sustained',h.bin1.gt(0)&h.bin2.gt(0))]:
        h[name]=pd.Series(pd.NA,index=h.index,dtype='boolean');h.loc[h.eligible,name]=values
    h['status']=np.select([h.confirmed_study_units.eq(0)&h.possible_only_study_units.eq(0),h.confirmed_study_units.eq(0),
      h.first_date.isna(),~h.entry_resolved,h.pre_main,~h.administratively_complete,h.window_uncertainty.gt(0)],
      ['no_confirmed_or_possible_event','possible_only','confirmed_date_missing','first_entry_unknown','pre_main_separate','administrative_censoring','followup_event_unknown'],default='complete_identifiable')
    return h,z

def connect(out):
    c=duckdb.connect()
    c.execute("SET threads=1; SET memory_limit='2GB'; SET preserve_insertion_order=false; SET max_temp_directory_size='4GB'")
    c.execute('SET temp_directory='+lit(out/'scratch'))
    return c

def quintiles(values):
    raw=np.asarray(values,dtype=float);require(np.isfinite(raw).all(),'Unknown scale cannot become zero')
    x=np.round(raw,12);cuts=np.quantile(x,[.2,.4,.6,.8],method='linear')
    require(len(np.unique(cuts))==4,'Five distinct quintile cut points unavailable; report instead of forcing groups')
    return np.searchsorted(cuts,x,side='left')+1,cuts

def pins():
    selections=[(OLD,'run_manifest.json',['tables/institution_history.parquet','tables/institution_events.parquet','tables/activity_relations.parquet','tables/followup_relations.parquet','tables/baseline_predictors.parquet','tables/dependency_diagnostics.parquet']),
      (F1,'run_manifest.json',['derived_study_records.parquet']),
      (F2,'run_manifest.json',['summary.json','tables/entry_cohort_registry.parquet']),
      (UP/'out_v2','prepare_manifest.json',['work_institutions.parquet','author_institution_membership.parquet','authorships.parquet']),
      (UP/'model_foundations_v1','model_foundations_manifest.json',['institution_background_long.parquet'])]
    result=[]
    for directory,mname,names in selections:
        mp=directory/mname;m=json.loads(mp.read_text());records=m.get('outputs',m.get('exports',{}))
        for name in names:
            p=directory/name;require(p.is_file() and not p.is_symlink(),'Nonregular input')
            digest=sha(p);require(digest==records[name]['sha256'],'Frozen source differs: '+name)
            result.append(dict(path=str(p),sha256=digest,bytes=p.stat().st_size))
        result.append(dict(path=str(mp),sha256=sha(mp),bytes=mp.stat().st_size))
    for p in [PLAN,MODULE/'README.md',OLD.parent/'data.py',OLD.parent/'models.py',UP/'association_models.py',PREVIOUS/'run_manifest.json']:
        result.append(dict(path=str(p),sha256=sha(p),bytes=p.stat().st_size))
    return result
