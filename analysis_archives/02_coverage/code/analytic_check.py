"""Independent deterministic primary analytic expectation check, not a new simulation."""
from common import *
from scipy.special import gammaln
import duckdb

def check_analytic(out):
 base=read(out,'institution_baseline_and_first_participation.csv');b=base.loc[truth(base.eligible_20),['institution_id','country','group']].reset_index(drop=True);b['idx']=np.arange(len(b))
 c=duckdb.connect();c.execute("SET threads=2");c.execute("SET memory_limit='4GiB'");c.execute('SET preserve_insertion_order=false');c.register('reg',b)
 p=str(out/'inputs/raw/opportunity_studies.parquet').replace("'","''");m=str(out/'inputs/raw/opportunity_memberships.parquet').replace("'","''")
 c.execute(f"CREATE TEMP TABLE s AS SELECT study_id,year,field,country_set,z FROM read_parquet('{p}') WHERE year IN (2021,2025)")
 c.execute('CREATE TEMP TABLE h AS SELECT year,field,country_set,count(*)::BIGINT n,sum(z)::BIGINT K FROM s GROUP BY year,field,country_set')
 sql=f'''SELECT r.idx,s.year,h.n,h.K,count(*)::BIGINT m FROM read_parquet('{m}') a JOIN s USING(study_id) JOIN reg r USING(institution_id) JOIN h USING(year,field,country_set) WHERE h.K>0 GROUP BY r.idx,s.year,s.field,s.country_set,h.n,h.K'''
 reader=c.execute(sql).to_arrow_reader(batch_size=100000);logp=np.zeros((len(b),2));rows=0;max_positive=0
 for batch in reader:
  x=batch.to_pandas();idx=x.idx.to_numpy();yi=np.where(x.year.to_numpy()==2021,0,1);n=x.n.to_numpy(float);K=x.K.to_numpy(float);mi=x.m.to_numpy(float);valid=(n-mi)>=K
  lp=np.full(len(x),-np.inf);nv=n[valid];kv=K[valid];mv=mi[valid]
  lp[valid]=gammaln(nv-mv+1)-gammaln(nv-mv-kv+1)+gammaln(nv-kv+1)-gammaln(nv+1)
  max_positive=max(max_positive,float(lp.max()));require(max_positive<1e-8,'Invalid positive log probability')
  np.add.at(logp,(idx,yi),np.minimum(lp,0));rows+=len(x)
 pred=-np.expm1(logp);results=[]
 for i,year in enumerate([2021,2025]):
  q=b.copy();q['analytic_A']=pred[:,i];dom=q.groupby(['country','group']).analytic_A.mean().unstack('group');G=100*(dom.H.mean()-dom.L.mean())
  results.append({'year':year,'analytic_H':dom.H.mean(),'analytic_L':dom.L.mean(),'analytic_G_pp':G})
 delta=results[1]['analytic_G_pp']-results[0]['analytic_G_pp'];formal=read(out,'Fig2d_benchmark_summary.csv','ready').expected_delta_G.iloc[0];error=delta-formal
 require(abs(error)<5e-7,'Independent analytic expectation differs from frozen formal value')
 save(out,'independent_analytic_check_annual.csv',pd.DataFrame(results));dump(out/'quality/independent_analytic_check.json',{'status':'PASS','calculated_delta_G_pp':delta,'formal_frozen_delta_G_pp':formal,'difference_pp':error,'tolerance_pp':5e-7,'institution_positive_stratum_cells':rows,'method':'independent raw membership hypergeometric no-event product; no randomization','not_used_to_replace_formal_estimate':True})
 c.close();print('Independent analytic check PASS; error pp:',error,flush=True)
if __name__=='__main__':
 import sys
 check_analytic(Path(sys.argv[1]))
