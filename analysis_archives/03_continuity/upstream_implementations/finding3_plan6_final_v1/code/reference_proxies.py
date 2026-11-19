"""Observed seed-reference proxies; never substitute them for actual action evidence."""
from common import *
import pyarrow.parquet as pq

def run():
    files=sorted((ROOT/'derived_tables/work_references').glob('*.parquet'));require(bool(files),'No local reference shards')
    schema=pq.ParquetFile(files[0]).schema_arrow.names;require('source_work_id' in schema and 'referenced_work_id' in schema,'Unexpected reference schema')
    seedfile=ROOT/'analysis/nhb_01/revision_v3/figure1_plan3_final_v1/tables/Table_S1_seed_registry.csv'
    seeds=pd.read_csv(seedfile);needed=load('work_metadata')[['work_id']]
    require(len(files)<=500,'Reference inventory unexpectedly large')
    pins=json.loads((OUT/'provenance/input_pins.json').read_text());known={v['path'] for v in pins}
    for p in [seedfile,*files]:
        if str(p) not in known:pins.append(dict(path=str(p),sha256=sha(p),bytes=p.stat().st_size))
    with con() as c:
        c.register('needed',needed);c.register('seeds',seeds)
        # Only records for actual frozen event works are materialized.
        c.execute('''CREATE TEMP TABLE refs AS SELECT DISTINCT n.work_id,
            regexp_extract(r.referenced_work_id,'W[0-9]+',0) AS referenced_work_id
            FROM read_parquet(?) r JOIN needed n
            ON regexp_extract(r.source_work_id,'W[0-9]+',0)=n.work_id''',[[str(p) for p in files]])
        counts=c.execute('SELECT work_id,count(*) AS recorded_reference_N FROM refs GROUP BY work_id').df()
        matches=c.execute('''SELECT r.work_id,s.seed,s.openalex_id FROM refs r
            JOIN seeds s ON r.referenced_work_id=s.openalex_id''').df()
    q=needed.merge(counts,on='work_id',how='left');q.recorded_reference_N=q.recorded_reference_N.fillna(0).astype(int)
    for name in ['AF2','AlphaFold-Multimer','AFDB','AF3']:
        q['cites_'+name]=q.work_id.isin(matches[matches.seed.eq(name)].work_id)
    q['model_seed_recorded']=q[['cites_AF2','cites_AlphaFold-Multimer','cites_AF3']].any(axis=1)
    q['database_seed_recorded']=q.cites_AFDB
    q['reference_availability']=np.where(q.recorded_reference_N.gt(0),'at_least_one_recorded_reference','no_reference_edges_observed_unknown_completeness')
    save('S2_reference_proxies',q);save('S2_seed_reference_matches',matches)
    x=load('entry_cohort').merge(q,left_on='entry_work_id',right_on='work_id',validate='many_to_one');rows=[]
    for co,g,z in scopes(x):
        for proxy in ['model_seed_recorded','database_seed_recorded']:
            for observed in [True,False]:
                part=z[z[proxy].eq(observed)]
                for m in MODES:
                    for state in ['supported','not_established','unknown']:
                        v=part['entry_'+m];n=int(v.eq(1).sum()) if state=='supported' else int(v.eq(0).sum()) if state=='not_established' else int(v.isna().sum())
                        rows.append(dict(cohort=co,size_group=g,proxy=proxy,proxy_state='recorded_seed_match' if observed else 'no_recorded_seed_match_not_proven_absence',activity=m,evidence_state=state,n=n,N=len(part),fraction=ratio(n,len(part))))
    save('S2_reference_action_crosscheck',pd.DataFrame(rows))
    save('S2_proxy_field_audit',pd.DataFrame([dict(field='source_work_id -> referenced_work_id + frozen four-seed registry',available=True,status='observed model/database seed proxies reconstructed from local reference shards; no-recorded-match is not proved absence; no action-label replacement')]))
    dump(OUT/'provenance/input_pins.json',pins)
    dump(OUT/'provenance/reference_proxy_audit.json',dict(status='executed_observed_reference_proxy',shards=len(files),selected_event_works=len(q),with_reference_edges=int(q.recorded_reference_N.gt(0).sum()),seed_matching_works=matches.work_id.nunique(),complete_reference_lists_certified=False,proxy_not_action_validation=True,API_calls=0))
    print('Observed reference proxy cross-check completed:',len(files),'shards;',matches.work_id.nunique(),'event works with frozen seed matches',flush=True)
if __name__=='__main__':run()
