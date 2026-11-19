"""Offline field/edge reuse audit. No API requests, no raw JSONL dependency."""
import gzip,json,math
from pathlib import Path
import duckdb,pandas as pd
from prepare_inputs import HERE,ROOT,sha,dump,require
def short(s):return str(s).rsplit('/',1)[-1]
def main():
 out=HERE/'local_reuse_audit_v1';out.mkdir(exist_ok=False)
 pilot=HERE/'citation_pilot_v1';rows=[]
 for f in sorted(pilot.glob('*_first_page.json.gz')):
  name=f.name.removesuffix('_first_page.json.gz');targets=pd.read_csv(pilot/(name+'_targets.csv'))
  by={short(r.work_id):r for r in targets.itertuples()}
  with gzip.open(f,'rt') as h:data=json.load(h)
  for w in data['results']:
   for ref in w.get('referenced_works',[]):
    key=short(ref)
    if key not in by:continue
    r=by[key];date=pd.to_datetime(w.get('publication_date'),errors='coerce');pub=pd.to_datetime(r.publication_date,errors='coerce')
    rows.append(dict(citing_id=short(w['id']),cited_id=key,citing_date=str(w.get('publication_date')),target_date=str(r.publication_date),within12=bool(pd.notna(date) and pd.notna(pub) and pub<=date<pub+pd.DateOffset(months=12)),within24=bool(pd.notna(date) and pd.notna(pub) and pub<=date<pub+pd.DateOffset(months=24))))
 x=pd.DataFrame(rows).drop_duplicates(['citing_id','cited_id']);c=duckdb.connect(config={'threads':1,'memory_limit':'2GiB','max_temp_directory_size':'1GiB'})
 c.register('pilot',x)
 # Semi-join before deduplication keeps the 175M-row scan bounded.
 c.execute("""CREATE TEMP TABLE local_pairs AS SELECT DISTINCT regexp_replace(source_work_id,'^https://openalex.org/','') citing_id,
 regexp_replace(referenced_work_id,'^https://openalex.org/','') cited_id FROM read_parquet('derived_tables/work_references/*.parquet') r
 SEMI JOIN pilot p ON regexp_replace(r.source_work_id,'^https://openalex.org/','')=p.citing_id
 AND regexp_replace(r.referenced_work_id,'^https://openalex.org/','')=p.cited_id""")
 c.execute("""CREATE TEMP TABLE local_works AS SELECT regexp_replace(work_id,'^https://openalex.org/','') id,
 min(publication_date) date_first,max(publication_date) date_last,count(*) records
 FROM read_parquet('derived_tables/works/*.parquet') GROUP BY 1""")
 z=c.execute('''SELECT p.*,w.id IS NOT NULL citing_paper_local,l.citing_id IS NOT NULL exact_edge_local,
 w.date_first,w.date_last FROM pilot p LEFT JOIN local_pairs l USING(citing_id,cited_id)
 LEFT JOIN local_works w ON p.citing_id=w.id''').df()
 z.to_csv(out/'pilot_edge_reuse.csv',index=False)
 raw=c.execute("""SELECT count(*) unique_works,count(*) FILTER(WHERE date_first IS NULL) missing_date,
 count(*) FILTER(WHERE date_first<>date_last) conflicting_dates FROM local_works""").df().to_dict('records')[0]
 fields={}
 import pyarrow.parquet as pq
 for folder in ['works','work_references','authorships']:
  fs=sorted((ROOT/'derived_tables'/folder).glob('*.parquet'))
  fields[folder]={'files':len(fs),'raw_rows':sum(pq.ParquetFile(f).metadata.num_rows for f in fs),'schemas':[list(s) for s in sorted({tuple(pq.ParquetFile(f).schema_arrow.names) for f in fs})]}
 counts={}
 for label,mask in [('all_returned_edges',pd.Series(True,index=z.index)),('within12',z.within12),('within24',z.within24)]:
  t=z[mask];counts[label]={'pilot_unique_edges':len(t),'exact_edges_locally_saved':int(t.exact_edge_local.sum()),'edges_missing_locally':int((~t.exact_edge_local).sum()),'missing_edge_with_local_citing_paper':int((~t.exact_edge_local&t.citing_paper_local).sum()),'missing_edge_with_outside_citing_paper':int((~t.exact_edge_local&~t.citing_paper_local).sum())}
 budget=json.loads((HERE/'citation_budget_audit_v1/summary.json').read_text())
 report={'status':'offline_audit_completed','raw_JSONL_directly_read':False,'JSONL_needed_for_main_citation_fields':False,'JSONL_condition':'Revisit only if input-export manifests reveal dropped records/fields or a focused row anomaly; not needed to obtain outside-corpus citing papers','local_inventory':fields,'local_works_profile':raw,'pilot_edge_comparison':counts,'selection':'10 first-page pilot responses; not random incoming-edge sample; missing fraction cannot be extrapolated','cost':{'additional_API_calls_this_audit':0,'observed_pilot_and_cost_survey_usage_usd':.019,'estimated_incoming_query_pages':budget['estimated_total_pages'],'estimated_incoming_query_usage_usd':budget['estimated_total_nominal_usd'],'identity_refresh_all_targets_optional_usd':2.2209,'exact_missing_edges_full_population':'unknown until query completeness verified','cost_savings_from_reusing_local_edges':'reduces storage/metadata processing, does not itself remove query/page cost; no demonstrated automatic price reduction'},'source_code_sha256':{str(p):sha(p) for p in [ROOT/'code/00_data_download.py',ROOT/'code/01_data_prepare_new.py']}}
 dump(out/'audit_report.json',report);print(json.dumps(report|{'local_inventory':'saved in audit report'},ensure_ascii=False,indent=2),flush=True)
if __name__=='__main__':main()
