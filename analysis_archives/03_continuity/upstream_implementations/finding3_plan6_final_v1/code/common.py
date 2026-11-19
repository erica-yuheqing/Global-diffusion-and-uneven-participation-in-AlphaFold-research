from pathlib import Path
import hashlib, json, sys
import numpy as np
import pandas as pd
import duckdb

MODULE=Path(__file__).resolve().parent
ROOT=MODULE.parents[2]
OUT=MODULE/'finding3_plan6_final_v1'
OLD=ROOT/'analysis/nhb_03/revision_v9/finding3_plan5_final_v1'
F2=ROOT/'analysis/nhb_02/revision_v6/finding2_plan5_final_v1'
UP=ROOT/'analysis/nhb_revision_v1/out_v2'
PLAN=Path('/historical-workspace/projects/IGN/revision/finding3-revision-plan-v6')
ACCEPT=ROOT/'analysis/nhb_01/revision_v1/accepted_candidate_layer_v2/accepted_layer_private.json'
LAYER=ROOT/'analysis/nhb_revision_v1/action_layer_v1'
CUTOFF=pd.Timestamp('2025-12-31')
MODES=['precomputed_structure_use','prediction_run','method_or_tool_development','prediction_evaluation_or_validation']
LABELS=['Precomputed structures','Prediction runs','Method / tool development','Evaluation / validation']
TERMS={MODES[0]:['retrieved_precomputed_structure'],MODES[1]:['ran_alphafold','ran_colabfold'],MODES[2]:['modified_or_extended','developed_downstream_tool'],MODES[3]:['benchmarked_or_evaluated']}
AUTH=['initial_only','mixed','no_initial_overlap']
AUTH_LABELS=['Initial authors only','Initial + other authors','No initial-author overlap']
GROUPS=['All','L','M','H','Unclassified']
COHORTS=['All','AF2','AF3']
def require(ok,message):
    if not bool(ok):raise ValueError(message)
def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for block in iter(lambda:f.read(2**20),b''):h.update(block)
    return h.hexdigest()
def clean(x):
    if isinstance(x,dict):return {str(k):clean(v) for k,v in x.items()}
    if isinstance(x,(list,tuple,np.ndarray)):return [clean(v) for v in x]
    if isinstance(x,np.integer):return int(x)
    if isinstance(x,np.bool_):return bool(x)
    if isinstance(x,(np.floating,float)):return float(x) if np.isfinite(x) else None
    if x is pd.NA or x is pd.NaT:return None
    if isinstance(x,(Path,pd.Timestamp)):return str(x)
    return x
def dump(p,x):Path(p).write_text(json.dumps(clean(x),ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def save(name,x,csv=True):
    x.to_parquet(OUT/'tables'/f'{name}.parquet',index=False)
    if csv:x.to_csv(OUT/'tables'/f'{name}.csv',index=False)
def load(name):return pd.read_parquet(OUT/'tables'/f'{name}.parquet')
def con():
    c=duckdb.connect();c.execute("SET threads=1;SET memory_limit='3GB';SET max_temp_directory_size='6GB';SET preserve_insertion_order=false")
    return c
def phase(d,shift=0):
    a=pd.Timestamp('2021-07-01')+pd.DateOffset(months=shift)
    b=pd.Timestamp('2024-05-01')+pd.DateOffset(months=shift)
    return pd.Series(np.select([d.isna(),d.lt(a),d.lt(b)],['Unknown','Pre-AF2','AF2'],default='AF3'),index=d.index)
def combine(states):
    if 'quarantined' in states:return 'quarantined'
    if 'supported' in states:return 'supported'
    if all(v=='not_established' for v in states):return 'not_established'
    if 'uncertain' in states:return 'uncertain'
    if 'not_assessed' in states:return 'not_assessed'
    return 'not_listed_legacy'
def scopes(df):
    for co in COHORTS:
        x=df if co=='All' else df[df.entry_cohort.eq(co)]
        for g in GROUPS:yield co,g,x if g=='All' else x[x.size_group.eq(g)]
def ratio(n,d):return n/d if d else np.nan
def transition(x,mode):
    q=x[~x.pair_order_uncertain & x['entry_'+mode].notna() & x['followup_'+mode].notna()]
    a=q['entry_'+mode];b=q['followup_'+mode]
    c={f'n{i}{j}':int((a.eq(i)&b.eq(j)).sum()) for i in [0,1] for j in [0,1]};N=len(q)
    return dict(N=N,**c,entry_fraction=ratio(c['n10']+c['n11'],N),followup_fraction=ratio(c['n01']+c['n11'],N),
        change_rate=ratio(c['n01']+c['n10'],N),new_rate=ratio(c['n01'],N),not_reestablished_rate=ratio(c['n10'],N),
        net_change_pp=100*ratio(c['n01']-c['n10'],N),retention=ratio(c['n11'],c['n11']+c['n10']),
        new_establishment=ratio(c['n01'],c['n00']+c['n01']),retention_N=c['n11']+c['n10'],new_N=c['n00']+c['n01'])
def configuration():
    return dict(version='Finding3-v6-1',authorized='user 2026-10-26 strict implementation',cutoff='2025-12-31',
      main_months=12,sensitivity_months=[3,6],weighting='equal institutions',size='frozen Fig2 domestic baseline integer-study L/M/H, eligible20',
      state_0='assessed; evidence not established, not proven non-use',unknown='NA; never impute zero',
      pair='fixed initial/first strictly subsequent confirmed different study; stable study_id tie-break; no metadata reselection',
      common_support_min_denominator=10,common_support_rule='at least 10 institutions per compared group per stratum; no condition on outcome count; sparse raw counts retained',
      author_composition_bins=dict(initial_authors=[1,2,5],gap_days=[0,92,183,366]),
      standardization='pooled category-specific assessable population over common supported strata; same weights for every compared group',
      country_sensitivity='same-country support and equal-country estimates are separate estimands',
      uncertainty='registered-event bounds and extreme missingness bounds; no unvalidated CI or p-values',
      period_sensitivity='both phase boundaries shifted minus/plus one calendar month; not actual release dates',
      API_calls=0,LLM_calls=0)
def pin_inputs():
    selections=[(OLD,'run_manifest.json',['tables/institution_pairs.parquet','tables/original_institution_events.parquet','tables/followup_relations.parquet','tables/ED5_annual_cohort_output.parquet','tables/ED5_growth_contributions.parquet','tables/ED5_institution_studies.parquet']),
      (F2,'run_manifest.json',['tables/baseline_groups.parquet']),
      (UP,'prepare_manifest.json',['works_eligible.parquet','authorships.parquet','author_institution_membership.parquet'])]
    rows=[]
    for folder,mname,names in selections:
        m=json.loads((folder/mname).read_text());records=m.get('outputs',m.get('exports',{}))
        for name in names:
            p=folder/name;h=sha(p);require(h==records[name]['sha256'],'Input changed '+str(p));rows.append(dict(path=str(p),sha256=h,bytes=p.stat().st_size))
    lm=json.loads((LAYER/'layer_manifest.json').read_text())
    require(sha(LAYER/'action_layer3755.jsonl')==lm['outputs']['action_layer3755.jsonl']['sha256'],'Action overlay changed')
    for p in [ACCEPT,LAYER/'action_layer3755.jsonl',*sorted(PLAN.rglob('*'))]:
        if p.is_file():rows.append(dict(path=str(p),sha256=sha(p),bytes=p.stat().st_size))
    return rows
