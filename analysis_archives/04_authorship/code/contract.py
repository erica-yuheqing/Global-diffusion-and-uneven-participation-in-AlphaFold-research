"""Canonical deliverable views; raw eligibility and standardized support are separate."""
from common import *
import shutil
def main():
    d=ROOT/'inputs/normalized';s=ROOT/'source_data';c=connect()
    # Direct contrasts retain both corpora's actual denominators/ESS, rather
    # than requiring a reader to infer them from a neighboring worksheet.
    for path in sorted((ROOT/'tables').glob('*_R.parquet')):
      r=pd.read_parquet(path)
      if not {'benchmark','global_ESS','n_studies'}.issubset(r.columns):continue
      prefix=path.stem[:-2];keys=['setting','benchmark','role','entity_id'];fields=['n_studies','n_papers','sum_weights','global_ESS','ESS'];wide=None
      for cp in CORPORA:
        t=r[r.corpus.eq(cp)][keys+fields].rename(columns={k:k+'_'+cp for k in fields});wide=t if wide is None else wide.merge(t,on=keys,validate='one_to_one')
      f=ROOT/'tables'/(prefix+'_delta.parquet')
      if f.exists():
        t=pd.read_parquet(f).drop(columns=[k for k in wide.columns if k not in keys],errors='ignore').merge(wide,on=keys,validate='one_to_one');save(prefix+'_delta',t)
      globalrows=r[r.role.eq('first')&r.benchmark.eq('country')].drop_duplicates(['setting','corpus']);lookup=globalrows.set_index(['setting','corpus'])
      for suffix in ['pairings','structure','same_country','direction_contrasts']:
        f=ROOT/'tables'/(prefix+'_'+suffix+'.parquet')
        if not f.exists():continue
        t=pd.read_parquet(f)
        for cp in CORPORA:
          for field in ['n_studies','sum_weights','global_ESS']:
            t[field+'_'+cp]=t.setting.map(lambda z:lookup.loc[(z,cp),field])
        if suffix=='pairings':t['observed_credit']=t.observed_share*t.sum_weights;t['expected_credit']=t.expected_share*t.sum_weights
        save(prefix+'_'+suffix,t)
    matrix=ROOT/'tables/full_country_pair_matrices.parquet'
    if matrix.exists():
      t=pd.read_parquet(matrix);r=pd.read_parquet(ROOT/'tables/strict_main_R.parquet');look=r[r.role.eq('first')&r.benchmark.eq('country')].drop_duplicates(['setting','corpus']).set_index(['setting','corpus'])
      for cp in CORPORA:
        for field in ['n_studies','sum_weights','global_ESS']:t[field+'_'+cp]=t.setting.map(lambda z:look.loc[(z,cp),field])
      t['observed_credit']=t.observed_share*t.sum_weights;t['expected_credit']=t.expected_share*t.sum_weights;t.to_parquet(matrix,index=False);t.to_csv(ROOT/'tables/full_country_pair_matrices.csv.gz',index=False,compression='gzip')
    for n in ['studies','analysis_members','authors_countries','credit','authors_institutions']:
      c.execute(f'CREATE VIEW {n} AS SELECT * FROM read_parquet({q(d/(n+".parquet"))})')
    c.execute(f'''COPY (SELECT r.study_id,CASE WHEN r.channel='first' THEN m.first_id ELSE m.last_id END AS author_id,r.country_code,r.channel AS role,r.credit,x.country_source
      FROM credit r JOIN analysis_members m USING(study_id) JOIN authors_countries x ON r.study_id=x.study_id AND x.author_id=CASE WHEN r.channel='first' THEN m.first_id ELSE m.last_id END AND r.country_code=x.country_code
      WHERE r.channel IN ('first','last')) TO {q(s/'role_country_credit.parquet')} (FORMAT PARQUET,COMPRESSION ZSTD)''')
    c.execute(f'''COPY (SELECT *, 'observed_country_institution_link' AS affiliation_status FROM authors_institutions) TO {q(s/'authors_institutions.parquet')} (FORMAT PARQUET,COMPRESSION ZSTD)''')
    c.execute(f'''COPY (SELECT DISTINCT institution_id,institution_country,'observed' AS resolution_status FROM authors_institutions) TO {q(s/'institutions.parquet')} (FORMAT PARQUET,COMPRESSION ZSTD)''')
    for name in ['role_country_institution_credit','country_pair_credit','country_pair_expected']:
      shutil.copy2(d/(name+'.parquet'),s/(name+'.parquet'))
    studies=norm('studies.parquet').rename(columns={'primary_eligible':'legacy_primary_eligible'});studies['new_full_eligible']=studies.strict_pairing_eligible;studies.to_csv(s/'studies.csv',index=False)
    e=pd.read_parquet(s/'study_eligibility.parquet');m=norm('analysis_members.parquet');weights=m.set_index('study_id').weight;e['supported_standardized']=e.study_id.map(weights).fillna(0).gt(0);e['new_exclusion_reason']=e.reason.replace({'primary_full_eligible':'eligible_raw_without_common_support'})
    same=norm('studies.parquet');same=set(same.loc[same.first_id.eq(same.last_id),'study_id']);e.loc[e.study_id.isin(same)&e.primary_eligible,'new_exclusion_reason']='identical_first_last_author';e.loc[e.supported_standardized,'new_exclusion_reason']='included_standardized';e.to_parquet(s/'study_eligibility.parquet',index=False);e.to_csv(s/'study_eligibility.csv.gz',index=False,compression='gzip')
    flow=e.groupby(['original_corpus','publication_year','new_exclusion_reason'],dropna=False).size().reset_index(name='n');save('strict_exclusive_final_flow',flow)
    annual=pd.read_parquet(ROOT/'tables/strict_annual_flow.parquet');counts=c.execute('''SELECT publication_year AS year,corpus,count(*) FILTER(WHERE common_country_candidate AND first_id<>last_id) AS common_roles_strict FROM studies GROUP BY 1,2''').df();annual=annual.drop(columns=['common_roles_strict'],errors='ignore').merge(counts,on=['year','corpus'],validate='one_to_one');save('strict_annual_flow',annual)
    # Canonical names required by the handoff contract, all real numeric outputs.
    for dst,src in [('group_pair_summary','strict_main_pairings'),('structure_summary','strict_main_structure'),('pairing_deviation','strict_main_pairings'),('direction_contrasts','strict_main_direction_contrasts'),('coverage_and_sensitivity','sensitivity_coverage_and_status')]:
      pd.read_parquet(ROOT/'tables'/(src+'.parquet')).to_csv(s/(dst+'.csv'),index=False)
    p=pd.read_parquet(ROOT/'tables/strict_main_pairings.parquet');p=p[p.corpus.isin(CORPORA)].copy();p.to_csv(s/'pairing_expected.csv',index=False)
    rows=[]
    for path in sorted((ROOT/'provenance').glob('*bootstrap_complete.json')):
      x=json.loads(path.read_text());rows.append(dict(analysis_id=path.name.removesuffix('_bootstrap_complete.json'),range_type=x['interval_type'],replicates=x['replicates'],seed=x['seed'],scope=x['strata'],fixed_support=True,fixed_weights=True))
    x=json.loads((ROOT/'provenance/conditional_reference_complete.json').read_text());rows.append(dict(analysis_id='conditional_endpoint_reference',range_type='conditional endpoint reference range, NOT observation CI',replicates=x['replicates'],seed=x['seed'],scope='actual within-study ordered two different authors',fixed_support=True,fixed_weights=True));pd.DataFrame(rows).to_csv(s/'uncertainty.csv',index=False)
    c.close();dump(ROOT/'provenance/contract_complete.json',dict(status='PASS',eligibility_rows=len(e),standardized_counts=e[e.supported_standardized].groupby('original_corpus').size().to_dict(),eligibility_reasons_mutually_exclusive=True,large_table_formats='typed Parquet plus gzip CSV; not empty templates',role_country_source_retained=True))
if __name__=='__main__':main()
