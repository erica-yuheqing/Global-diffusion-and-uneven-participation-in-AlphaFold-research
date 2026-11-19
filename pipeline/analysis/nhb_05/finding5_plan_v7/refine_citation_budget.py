"""Count-only, bounded survey of frozen monthly query batches; no citation counts."""
import concurrent.futures,datetime,gzip,json,math,os,urllib.parse
from pathlib import Path
import numpy as np,pandas as pd
from prepare_inputs import HERE,dump,sha,require
from citation_pilot import get
P=HERE/'citation_acquisition_plan_v1';O=HERE/'citation_budget_audit_v1'
def main():
 require(not O.exists(),'Existing audit must not be re-requested');O.mkdir()
 key=os.environ.get('OPENALEX_API_KEY');require(bool(key),'Missing OpenAlex key')
 rate=get('https://api.openalex.org/rate-limit',key)[0]['rate_limit']
 require(rate['daily_remaining_usd']>=.07,'Insufficient free reserve')
 dump(O/'rate_limit_before.json',{'rate_limit':rate})
 batches=[json.loads(s) for s in (P/'batches.jsonl').read_text().splitlines()]
 by={}
 for b in batches:by.setdefault(b['batch_id'][:7],[]).append(b)
 rng=np.random.default_rng(20261029);selected=[]
 for month,pool in sorted(by.items()):
  selected.extend(pool[i] for i in sorted(rng.choice(len(pool),min(3,len(pool)),replace=False)))
 require(len(selected)<=180,'HTTP-send cap exceeds 180')
 dump(O/'selected_batch_ids.json',[b['batch_id'] for b in selected])
 def one(b):
  params={'filter':b['filter'],'per_page':1,'select':'id'}
  data,headers=get('https://api.openalex.org/works?'+urllib.parse.urlencode(params),key)
  require(isinstance(data.get('meta',{}).get('count'),int),'Missing count is unknown, not zero')
  with gzip.open(O/(b['batch_id']+'.json.gz'),'wt') as f:json.dump(data,f)
  return dict(batch_id=b['batch_id'],month=b['batch_id'][:7],citing_records=data['meta']['count'],nominal_pages_at_100=max(1,math.ceil(data['meta']['count']/100)),retrieved_at=datetime.datetime.now(datetime.timezone.utc).isoformat())
 rows=[]
 for start in range(0,len(selected),12):
  now=get('https://api.openalex.org/rate-limit',key)[0]['rate_limit']
  require(now['daily_remaining_usd']>=.0512,'Free reserve reached; no prepaid usage')
  with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
   for row in pool.map(one,selected[start:start+12]):rows.append(row)
  dump(O/'requests.json',rows);print('Count-only batch survey:',len(rows),'/',len(selected),flush=True)
 frame=pd.DataFrame(rows);monthly=[]
 for month,pool in sorted(by.items()):
  a=frame[frame.month.eq(month)].nominal_pages_at_100.to_numpy()
  monthly.append(dict(month=month,population_batches=len(pool),sampled_batches=len(a),mean_pages=float(a.mean()),sample_sd_pages=float(a.std(ddof=1)) if len(a)>1 else None,estimated_pages=float(a.mean()*len(pool))))
 pd.DataFrame(monthly).to_csv(O/'monthly_cost_projection.csv',index=False)
 after=get('https://api.openalex.org/rate-limit',key)[0]['rate_limit'];dump(O/'rate_limit_after.json',{'rate_limit':after})
 estimate=sum(x['estimated_pages'] for x in monthly)
 result=dict(status='completed_cost_survey_only',seed=20261029,http_list_calls=len(rows),free_usage_observed_usd=after['daily_used_usd']-rate['daily_used_usd'],prepaid_unchanged=after['prepaid_remaining_usd']==rate['prepaid_remaining_usd'],total_frozen_batches=len(batches),estimated_total_pages=estimate,estimated_total_nominal_usd=estimate*.0001,minimum_pages=len(batches),minimum_nominal_usd=len(batches)*.0001,assumptions=['three random batches per publication month','pages estimated from current API counts; no exact full pagination yet','zero-result batch still needs one request','provider changes, retries and high-degree citing works can change total','no full citation counts or reference percentiles derived'],input_sha256=sha(P/'batches.jsonl'))
 dump(O/'summary.json',result);print(json.dumps(result,indent=2),flush=True)
if __name__=='__main__':main()
