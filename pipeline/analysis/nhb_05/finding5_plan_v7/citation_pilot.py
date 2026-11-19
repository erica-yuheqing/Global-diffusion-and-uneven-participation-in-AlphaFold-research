"""Bounded incoming-citation feasibility pilot. Never spends prepaid balance."""
import os,json,urllib.request,urllib.parse,urllib.error,gzip,time,datetime
from pathlib import Path
import numpy as np,pandas as pd
from prepare_inputs import HERE,dump,require,sha
OUT=HERE/'citation_pilot_v1'
def get(url,key):
 req=urllib.request.Request(url,headers={'Authorization':'Bearer '+key,'User-Agent':'ScientificInfluenceDataAudit/1.0'})
 try:
  with urllib.request.urlopen(req,timeout=60) as r:return json.load(r),dict(r.headers)
 except urllib.error.HTTPError as e:
  # Never print request headers or URL credentials.
  raise RuntimeError('OpenAlex HTTP '+str(e.code)) from None
def main():
 key=os.environ.get('OPENALEX_API_KEY');require(bool(key),'OPENALEX_API_KEY unavailable')
 require(not OUT.exists(),'Pilot output exists; inspect rather than resend')
 budget,_=get('https://api.openalex.org/rate-limit',key)
 rate=budget.get('rate_limit',{})
 require(rate.get('daily_remaining_usd',0)>=.02,'Free daily allowance insufficient; no prepaid spending')
 OUT.mkdir();dump(OUT/'rate_limit_before.json',{'rate_limit':rate})
 t=HERE/'foundations_v1/data/citation_target_universe.parquet'
 x=pd.read_parquet(t);rng=np.random.default_rng(20261029);summary=[];selected=[]
 for year in range(2020,2025):
  for af in [False,True]:
   pool=x[x.year.eq(year)&x.confirmed_af.eq(af)]
   take=pool.iloc[rng.choice(len(pool),min(100,len(pool)),replace=False)].sort_values('work_id')
   name=f'{year}_'+('AF' if af else 'all_other_labels')
   take.assign(batch=name).to_csv(OUT/(name+'_targets.csv'),index=False)
   ids=[str(w).rsplit('/',1)[-1] for w in take.work_id]
   params={'filter':'cites:'+'|'.join(ids)+f',from_publication_date:{year}-01-01,to_publication_date:2025-12-31',
           'per_page':100,'cursor':'*','select':'id,doi,publication_date,referenced_works,authorships'}
   url='https://api.openalex.org/works?'+urllib.parse.urlencode(params)
   # Fixed 10-request cap, no retries, first-page feasibility only.
   data,headers=get(url,key)
   with gzip.open(OUT/(name+'_first_page.json.gz'),'wt') as f:json.dump(data,f)
   cost=data.get('meta',{}).get('cost_usd',data.get('meta',{}).get('cost'))
   summary.append({'batch':name,'year':year,'AF_stratum':af,'targets':len(take),'citing_records_until_cutoff':data.get('meta',{}).get('count'),'first_page_rows':len(data.get('results',[])),'next_cursor_exists':bool(data.get('meta',{}).get('next_cursor')),'response_cost_reported':cost,'query':params,'retrieved_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()})
   dump(OUT/'requests.json',summary);print(name,'targets',len(take),'citing records',data.get('meta',{}).get('count'),flush=True)
   time.sleep(1)
 after,_=get('https://api.openalex.org/rate-limit',key);dump(OUT/'rate_limit_after.json',{'rate_limit':after.get('rate_limit',{})})
 dump(OUT/'pilot_status.json',dict(status='feasibility_only_not_complete_citations',target_input_sha256=sha(t),calls=len(summary),paid_calls_authorized=False,fixed_window_counts_ready=False,selection='seeded random up to 100 per year x confirmed_AF yes/no; no outcome sampling',full_request_volume='requires target-batch plan; sample not a precise full-volume estimator',self_citation='authorships requested; not yet assessed'))
if __name__=='__main__':main()
