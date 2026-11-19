"""Freeze approved-version citation queries; offline only, no HTTP sends."""
import json,math
import pandas as pd,duckdb
from prepare_inputs import HERE,ROOT,S,F,sha,q,dump,require
O=HERE/'citation_acquisition_plan_v1';D=HERE/'foundations_v2'
def main():
 require(not O.exists(),'Plan exists');O.mkdir()
 mapping=ROOT/'analysis/nhb_revision_v1/study_events_v1/work_study_map.parquet'
 approvals=ROOT/'analysis/nhb_01/revision_v1/accepted_candidate_layer_v2/accepted_layer_private.json'
 expected={x['path']:x['sha256'] for x in json.loads((S/'run_manifest.json').read_text())['inputs']}
 require(sha(approvals)==expected[str(approvals)],'Approved version layer differs')
 layer=json.loads(approvals.read_text());links=layer.get('accepted_version_links',[])
 c=duckdb.connect(config={'threads':1,'memory_limit':'2GiB','preserve_insertion_order':False})
 c.execute(f'CREATE VIEW m AS SELECT * FROM read_parquet({q(mapping)})')
 c.execute(f'CREATE VIEW p AS SELECT * FROM read_parquet({q(D/"data/paper_metrics.parquet")})')
 c.execute(f'CREATE VIEW old AS SELECT * FROM read_parquet({q(ROOT/"analysis/nhb_revision_v1/study_events_v1/study_records.parquet")})')
 aliases=[]
 for g in links:
  require(g.get('approval_status')=='accepted_by_user','Unapproved version link')
  rep=g['representative_work_id'];final=c.execute('SELECT study_id FROM p WHERE work_id=?',[rep]).fetchone()
  require(final is not None,'Approved representative missing')
  for member in g['member_work_ids']:
   old=c.execute('SELECT study_id FROM old WHERE annual_representative_work_id=?',[member]).fetchone()
   require(old is not None,'Version member absent')
   aliases.append({'old_study':old[0],'final_study':final[0]})
 a=pd.DataFrame(aliases).drop_duplicates();require(not a.old_study.duplicated().any(),'Overlapping alias map')
 c.register('alias',a)
 c.execute('''CREATE TEMP TABLE crosswalk AS SELECT m.work_id,coalesce(a.final_study,m.study_id) AS study_id
 FROM m LEFT JOIN alias a ON m.study_id=a.old_study''')
 require(c.execute('SELECT count(*)=count(DISTINCT work_id) FROM crosswalk').fetchone()[0],'Duplicate work aliases')
 c.execute(f'''COPY (SELECT x.* FROM crosswalk x JOIN p USING(study_id)) TO {q(O/'approved_work_study_crosswalk.parquet')} (FORMAT PARQUET,COMPRESSION ZSTD)''')
 x=c.execute('''SELECT x.work_id,p.study_id,p.publication_date,p.year,p.work_type,p.subfield,p.confirmed_af,p.mature12,p.mature24
 FROM crosswalk x JOIN p USING(study_id) WHERE p.year BETWEEN 2020 AND 2024 AND p.publication_date IS NOT NULL
 AND p.mature12 ORDER BY p.publication_date,x.work_id''').df()
 x['publication_date']=pd.to_datetime(x.publication_date);x['month']=x.publication_date.dt.strftime('%Y-%m')
 x.to_parquet(O/'target_member_ids.parquet',index=False)
 batches=[]
 for month,z in x.groupby('month',sort=True):
  for start in range(0,len(z),100):
   t=z.iloc[start:start+100];begin=t.publication_date.min();end=min(t.publication_date.max()+pd.DateOffset(months=24),pd.Timestamp('2025-12-31'))
   # 2024 cannot complete 24m, so its query remains sufficient for main 12m.
   if int(month[:4])==2024:end=min(t.publication_date.max()+pd.DateOffset(months=12),pd.Timestamp('2025-12-31'))
   ids=[v.rsplit('/',1)[-1] for v in t.work_id]
   batches.append({'batch_id':f'{month}-{start//100:04d}','work_ids':ids,'study_ids':t.study_id.tolist(),
     'filter':'cites:'+'|'.join(ids)+',from_publication_date:'+begin.strftime('%Y-%m-%d')+',to_publication_date:'+end.strftime('%Y-%m-%d'),
     'per_page':100,'select':'id,doi,publication_date,referenced_works,authorships','first_cursor':'*'})
 with (O/'batches.jsonl').open('w') as f:
  for b in batches:f.write(json.dumps(b,separators=(',',':'))+'\n')
 pilot=HERE/'citation_pilot_v1';r=json.loads((pilot/'requests.json').read_text());original=pd.read_parquet(D/'data/citation_target_universe.parquet')
 rough=sum(math.ceil(len(original[original.year.eq(v['year'])&original.confirmed_af.eq(v['AF_stratum'])])/100)*max(1,math.ceil(v['citing_records_until_cutoff']/100)) for v in r)
 report={'status':'planned_not_executed','unique_target_studies':x.study_id.nunique(),'target_member_work_IDs':len(x),'query_batches':len(batches),'minimum_list_calls':len(batches),'minimum_nominal_list_cost_usd':len(batches)*.0001,'rough_pilot_extrapolated_pages_before_month_window_reduction':rough,'rough_cost_usd_not_quote':rough*.0001,'version_groups_applied':len(links),'input_pins':{str(p):sha(p) for p in [mapping,approvals,D/'data/paper_metrics.parquet']},'publication_cutoff':'2025-12-31','upper_bound_date_query_is_inclusive':'exact half-open per-paper anniversary filtering occurs after collection','limitations':['pilot count includes citations outside individual anniversaries','version IDs collapsed after retrieval; not one independent citation per alias','provider completeness only, cannot establish complete worldwide citation universe','free versus prepaid budget checked before dispatch','2GiB collection ceiling requires compact edge and author-ID extraction; full HTTP bodies only for small pilot'],'run_status':'waiting_for_spending_limit_answer; no full-batch API requests sent'}
 dump(O/'collection_plan.json',report);print(json.dumps(report,indent=2),flush=True)
if __name__=='__main__':main()
