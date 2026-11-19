"""Rebuild fixed-window counts/ranks from frozen edges, never a provider call."""
from common import *
from upstream_metrics import reference_percentiles
def main():
 c=con()
 for n,f in [('p','paper_base.parquet'),('e','citation_edges.parquet'),('bad','citation_quality_exclusions.parquet'),('parent','parent_fields.parquet'),('b','batch_status.parquet'),('old','study_metrics_v1.parquet')]:view(c,n,I/f)
 require(c.execute("SELECT count(*) FROM b WHERE status<>'query_complete'").fetchone()[0]==0,'Incomplete frozen citation pagination')
 require(c.execute('SELECT count(*) FROM e WHERE citing_publication_date IS NULL').fetchone()[0]==0,'Unparseable citing dates')
 c.execute('''CREATE TEMP TABLE counts AS SELECT p.study_id,
 count(*) FILTER(WHERE e.citing_publication_date>=p.publication_date AND e.citing_publication_date<p.publication_date+INTERVAL 12 MONTH AND e.citing_study_id<>p.study_id) n12,
 count(*) FILTER(WHERE e.citing_publication_date>=p.publication_date AND e.citing_publication_date<p.publication_date+INTERVAL 24 MONTH AND e.citing_publication_date<=DATE '2025-12-31' AND e.citing_study_id<>p.study_id) n24
 FROM e JOIN p USING(study_id) GROUP BY 1''')
 x=c.execute('''SELECT p.* EXCLUDE(citation_status,citations_12m,citations_24m),parent.parent_field,
 CASE WHEN q.study_id IS NOT NULL THEN 'quality_quarantine' WHEN NOT mature12 THEN 'not_mature' ELSE 'complete_provider_query' END citation_status,
 CASE WHEN q.study_id IS NULL AND mature12 AND p.year<=2024 THEN coalesce(n12,0) END citations_12m,
 CASE WHEN q.study_id IS NULL AND mature24 AND p.year<=2023 THEN coalesce(n24,0) END citations_24m
 FROM p LEFT JOIN (SELECT DISTINCT study_id FROM bad) q USING(study_id) LEFT JOIN counts USING(study_id)
 LEFT JOIN parent USING(subfield) WHERE p.year BETWEEN 2020 AND 2025''').df()
 x['publication_date']=pd.to_datetime(x.publication_date);x['month']=x.publication_date.dt.month
 for col,mat in [('citations_12m','mature12'),('citations_24m','mature24')]:
  x[col.replace('citations','percentile')],cells=reference_percentiles(x,col,mat,100);table('reference_cells_'+col,cells)
 require(x.study_id.is_unique,'Duplicated study metric')
 x.to_parquet(D/'paper_metrics.parquet',index=False);view(c,'new',D/'paper_metrics.parquet')
 fields=['citations_12m','citations_24m','percentile_12m','percentile_24m']
 mismatches=c.execute('SELECT count(*) FROM new JOIN old USING(study_id) WHERE '+' OR '.join('new.'+v+' IS DISTINCT FROM old.'+v for v in fields)).fetchone()[0]
 require(mismatches==0,'Citation reconstruction differs from validated v1; investigate before fitting')
 parquet(c,'''SELECT p.study_id,p.year,CASE WHEN p.year<=2024 THEN true END pagination_complete,p.mature12,p.mature24,
 q.study_id IS NOT NULL quarantined,q.reason FROM p LEFT JOIN (SELECT study_id,string_agg(DISTINCT reason,'; ' ORDER BY reason) reason FROM bad GROUP BY 1) q USING(study_id)
 WHERE p.year BETWEEN 2020 AND 2025''',D/'citation_quality.parquet')
 table('citation_assessability',x.groupby(['year','work_type','citation_status'],dropna=False).agg(studies=('study_id','size'),AF=('confirmed_af','sum'),known12=('citations_12m','count'),known24=('citations_24m','count')).reset_index())
 dump(Q/'metric_audit.json',{'status':'PASS','studies':len(x),'quarantined':int(x.citation_status.eq('quality_quarantine').sum()),'known12':int(x.citations_12m.notna().sum()),'v1_count_rank_mismatches':mismatches,'new_requests':0,'reference_population':'assessable eligible collected corpus, all AF labels','snapshot':'incoming 2026-10-30_to_31; citing publication cutoff 2025-12-31'})
 print('FIXED-WINDOW RECONSTRUCTION PASS',len(x),'studies; identical v1 counts/ranks',flush=True)
if __name__=='__main__':main()
