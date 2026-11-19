"""Independently compare paper-level matching and institution-level regressions to final figure sources."""
from pathlib import Path
import argparse,json,tempfile
import numpy as np
import pandas as pd
import duckdb
ROOT=Path(__file__).resolve().parents[1]
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
 if args.output.exists():raise SystemExit('Choose a fresh report path')
 d=ROOT/'analysis_archives/05_outcomes_networks';f=ROOT/'figures/main'; checks=[]
 def check(label,actual,expected,tol=1e-9):
  if not np.isclose(actual,expected,atol=tol,rtol=0):raise ValueError(f'{label}: {actual} differs from {expected}')
  checks.append(dict(check=label,observed=float(actual),target=float(expected)))
 with tempfile.TemporaryDirectory() as scratch:
  c=duckdb.connect(config={'threads':2,'memory_limit':'2GB','temp_directory':scratch,'preserve_insertion_order':False})
  for name,path in [('m',d/'source_data/paper_metrics.parquet'),('l',d/'inputs/work_institutions.parquet'),('i',d/'inputs/institutions.parquet'),('p',d/'inputs/paper_base.parquet'),('x',d/'inputs/approved_crosswalk.parquet'),('master',ROOT/'data/corpus/works_master_public.parquet'),('original',ROOT/'data/corpus/original_decisions.parquet')]:
   c.read_parquet(str(path)).create_view(name)
  for name,sql,expected in [
   ('master records','SELECT count(*) FROM master',6046663),('original candidate work IDs','SELECT count(DISTINCT work_id) FROM original',29127),('eligible records','SELECT count(*) FROM x',4686896),('consolidated studies','SELECT count(DISTINCT study_id) FROM p',4686879),('main eligible studies','SELECT count(*) FROM m',2714594),('main AF studies','SELECT count(*) FROM m WHERE confirmed_af',16414),('AF subfields','SELECT count(DISTINCT subfield) FROM m WHERE confirmed_af',21),('fixed institutions','SELECT count(*) FROM i WHERE baseline_eligible',48010),('fixed countries','SELECT count(DISTINCT country) FROM i WHERE baseline_eligible',68)]:check(name,c.execute(sql).fetchone()[0],expected,0)
  for y,n in zip(range(2020,2026),[11,393,2389,3904,4144,5573]):check(f'AF {y}',c.execute('SELECT count(*) FROM m WHERE confirmed_af AND year=?',[y]).fetchone()[0],n,0)
  c.execute("""CREATE TEMP TABLE obs AS SELECT l.institution_id,i."group" grp,m.year,m.subfield,m.work_type,m.study_id,m.screen_negative,m.confirmed_af,m.journal_position,m.percentile_12m FROM m JOIN l USING(study_id,work_id,year) JOIN i USING(institution_id) WHERE i.baseline_eligible AND m.publication_date BETWEEN DATE '2020-01-01' AND DATE '2025-12-31' """)
  for outcome,col,last,threshold in [('journal','journal_position',2025,75),('citation','percentile_12m',2024,90)]:
   exp=pd.read_csv(f/'Fig05/source_data'/f'{outcome}_estimates.csv')
   for metric,expr in [(col,col),(('high_journal75' if outcome=='journal' else 'high_citation90'),f'100*({col}>={threshold})::INT')]:
    scores=c.execute(f"""WITH controls AS (SELECT institution_id,year,subfield,work_type,avg({expr}) AS reference_mean FROM obs WHERE screen_negative AND year<={last} AND {col} IS NOT NULL GROUP BY ALL),
    pairs AS (SELECT institution_id,grp,study_id,{expr}-reference_mean AS delta FROM obs JOIN controls USING(institution_id,year,subfield,work_type) WHERE confirmed_af AND {col} IS NOT NULL),
    inst AS (SELECT grp,institution_id,avg(delta) d FROM pairs GROUP BY ALL)
    SELECT grp,count(*) n,avg(d) estimate FROM inst GROUP BY grp""").df()
    for row in scores.itertuples():
     target=exp[(exp.group==row.grp)&(exp.metric==metric)].iloc[0]
     check(f'Fig05 {metric} {row.grp} matched institutions',row.n,target.n_institutions,0);check(f'Fig05 {metric} {row.grp} difference',row.estimate,target.estimate)
  c.close()
 slopes=pd.read_csv(f/'Fig06/source_data/plotted_slopes.csv')
 for kind,file,scale in [('own','own_connectivity_coordinates.csv',1),('partner','partner_centrality_coordinates.csv',10)]:
  pts=pd.read_csv(f/'Fig06/source_data'/file);pts=pts[pts.coordinate_type.eq('institution')]
  for r in slopes[slopes.sample_id.eq('degree_'+kind)].itertuples():
   s=pts[(pts.outcome==r.outcome)&(pts.group==r.group)]
   b=np.linalg.lstsq(np.column_stack((np.ones(len(s)),s.x/scale)),s.y,rcond=None)[0][1]
   check(f'Fig06 {kind} {r.outcome} {r.group} slope',b,r.estimate)
 args.output.parent.mkdir(parents=True,exist_ok=True)
 args.output.write_text(json.dumps(checks,indent=2));print('Passed',len(checks),'cohort, matching and regression checks')
if __name__=='__main__':main()
