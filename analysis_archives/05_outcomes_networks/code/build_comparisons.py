"""All usable nonAF controls; equal AF papers within equal institutions."""
from common import *
KEY=['institution_id','year','subfield','work_type']
METRICS=['journal_position','high_journal75','high_journal90','official_best_Q1','percentile_12m','high_citation90','high_citation95','percentile_24m','high_citation24_90']
def controls_sql(keys):
 return 'SELECT '+','.join(keys)+','+','.join(f'count({m}) n_{m},avg({m}) ref_{m}' for m in METRICS)+' FROM observations WHERE screen_negative AND subfield IS NOT NULL GROUP BY '+','.join(keys)
def main():
 c=con();view(c,'p',D/'paper_metrics.parquet');view(c,'l',I/'work_institutions.parquet');view(c,'i',I/'institutions.parquet');view(c,'old',I/'paper_base.parquet')
 c.execute('''CREATE TEMP TABLE observations AS SELECT p.*,l.institution_id,i.country,i."group",
 (p.journal_position>=75)::DOUBLE high_journal75,(p.journal_position>=90)::DOUBLE high_journal90,
 (p.percentile_12m>=90)::DOUBLE high_citation90,(p.percentile_12m>=95)::DOUBLE high_citation95,
 (p.percentile_24m>=90)::DOUBLE high_citation24_90,((p.month-1)//3+1)::INT pub_quarter
 FROM l JOIN p USING(study_id,work_id,year) JOIN i USING(institution_id)
 WHERE p.publication_date BETWEEN DATE '2020-01-01' AND DATE '2025-12-31' AND i.baseline_eligible''')
 c.execute('CREATE TEMP TABLE refs AS '+controls_sql(KEY))
 c.execute('''CREATE TEMP TABLE history AS SELECT l.institution_id,p.subfield,p.work_type,
 count(p.journal_position) history_n,count(DISTINCT p.year) FILTER(WHERE p.journal_position IS NOT NULL) history_years,
 avg(p.journal_position) history_position FROM l JOIN old p USING(study_id,work_id,year)
 WHERE p.year BETWEEN 2015 AND 2019 AND p.subfield IS NOT NULL GROUP BY 1,2,3''')
 joins=' AND '.join('a.'+k+'=r.'+k for k in KEY)
 c.execute('''CREATE TEMP TABLE pairs AS SELECT a.*,r.* EXCLUDE(institution_id,year,subfield,work_type),h.history_n,h.history_years,h.history_position
 FROM observations a LEFT JOIN refs r ON '''+joins+''' LEFT JOIN history h ON a.institution_id=h.institution_id AND a.subfield=h.subfield AND a.work_type=h.work_type WHERE a.confirmed_af''')
 parquet(c,'SELECT * FROM pairs',D/'matched_comparisons.parquet')
 cols=['study_id','work_id','institution_id','year','month','pub_quarter','subfield','work_type']+METRICS
 parquet(c,'SELECT '+','.join(cols)+' FROM observations WHERE screen_negative',D/'control_links.parquet')
 for mode in ['month','pub_quarter']:
  keys=KEY+[mode];c.execute('CREATE TEMP TABLE fine AS '+controls_sql(keys))
  j=' AND '.join('a.'+k+'=r.'+k for k in keys)
  parquet(c,'SELECT a.study_id,a.institution_id,'+','.join('r.ref_'+m+','+'r.n_'+m for m in METRICS)+' FROM observations a LEFT JOIN fine r ON '+j+' WHERE a.confirmed_af',D/(mode+'_references.parquet'))
  c.execute('DROP TABLE fine')
 # Registered uncertainty only. No claim that this bounds unknown recall.
 c.execute('''CREATE TEMP TABLE events AS SELECT i.institution_id,i.country,i."group",
 coalesce(bool_or(o.confirmed_af),false) af_confirmed,
 coalesce(bool_or(o.confirmed_af OR o.possible_af OR o.af_use_label='uncertain' OR (o.af_use_label='yes' AND o.adoption_eligible='uncertain')),false) af_possible,
 coalesce(bool_or(o.confirmed_af AND o.journal_position>=75),false) venue_confirmed,
 coalesce(bool_or((o.confirmed_af OR o.possible_af OR o.af_use_label='uncertain' OR (o.af_use_label='yes' AND o.adoption_eligible='uncertain')) AND (o.journal_position>=75 OR o.journal_position IS NULL)),false) venue_possible,
 coalesce(bool_or(o.confirmed_af AND o.percentile_12m>=90),false) citation_confirmed,
 coalesce(bool_or((o.confirmed_af OR o.possible_af OR o.af_use_label='uncertain' OR (o.af_use_label='yes' AND o.adoption_eligible='uncertain')) AND (o.percentile_12m>=90 OR o.percentile_12m IS NULL)),false) citation_possible
 FROM i LEFT JOIN observations o ON i.institution_id=o.institution_id AND o.year BETWEEN 2020 AND 2024
 WHERE i.baseline_eligible GROUP BY 1,2,3''')
 parquet(c,'SELECT * FROM events',D/'coverage_events.parquet')
 coverage=c.execute('''SELECT country,"group",count(*) baseline_denominator,'''+','.join('sum('+ev+'_confirmed::INT) '+ev+'_confirmed_n,sum('+ev+'_possible::INT) '+ev+'_possible_n,avg('+ev+'_confirmed::INT)*100 '+ev+'_lower,avg('+ev+'_possible::INT)*100 '+ev+'_upper' for ev in ['af','venue','citation'])+' FROM events GROUP BY 1,2 ORDER BY 1,2').df()
 require(len(coverage)==204 and coverage.baseline_denominator.sum()==48010,'Coverage denominator differs')
 coverage.to_csv(D/'coverage_country_group.csv',index=False)
 table('coverage_summary',coverage.groupby('group')[[e+s for e in ['af','venue','citation'] for s in ['_lower','_upper']]].mean().reset_index())
 a=c.execute('SELECT * FROM pairs').df();a['publication_date']=pd.to_datetime(a.publication_date)
 a['in_main_years']=a.year.le(2024);a['journal_support']=a.journal_position.notna()&a.n_journal_position.ge(1);a['citation_support']=a.percentile_12m.notna()&a.n_percentile_12m.ge(1);a['common']=a.in_main_years&a.journal_support&a.citation_support
 require(not a[['study_id','institution_id']].duplicated().any(),'Duplicate AF institution link')
 a.to_parquet(D/'matched_comparisons.parquet',index=False)
 c.register('history_targets',a.loc[a.common & a.history_n.ge(1),KEY].drop_duplicates())
 parquet(c,'''SELECT p.study_id,p.work_id,l.institution_id,t.year,p.subfield,p.work_type,p.journal_position
 FROM l JOIN old p USING(study_id,work_id,year) JOIN history_targets t ON l.institution_id=t.institution_id AND p.subfield=t.subfield AND p.work_type=t.work_type
 WHERE p.year BETWEEN 2015 AND 2019 AND p.journal_position IS NOT NULL''',D/'historical_control_links.parquet')
 c.execute('''CREATE TEMP TABLE historic_sources AS SELECT DISTINCT l.institution_id,p.source_id FROM l JOIN old p USING(study_id,work_id,year) WHERE p.year BETWEEN 2015 AND 2019 AND p.source_id IS NOT NULL''')
 sources=c.execute('''SELECT a.study_id,a.institution_id,a.year,a.country,a."group",a.source_id,a.subfield,a.work_type,a.journal_position,a.history_n,a.history_years,
 h.source_id IS NULL AS source_not_observed_in_baseline FROM pairs a LEFT JOIN historic_sources h ON a.institution_id=h.institution_id AND a.source_id=h.source_id WHERE a.year<=2024 AND a.source_id IS NOT NULL''').df()
 sources.to_parquet(D/'new_source_observations.parquet',index=False)
 flows=[]
 for sample,mask in [('all_AF_2020_2025',pd.Series(True,index=a.index)),('AF_main_years',a.in_main_years),('journal_max',a.in_main_years&a.journal_support),('citation_max',a.in_main_years&a.citation_support),('common',a.common),('single_AF_common',a.common&a.groupby('institution_id').study_id.transform('nunique').eq(1))]:
  for g in ['L','M','H']:
   z=a[mask&a.group.eq(g)];flows.append(dict(sample_id=sample,group=g,n_af_works=z.study_id.nunique(),n_institutions=z.institution_id.nunique(),n_affiliation_links=len(z)))
 table('T_SI1_flow',pd.DataFrame(flows))
 table('T_SI4_matching',a.groupby(['group','year']).agg(AF_works=('study_id','nunique'),institutions=('institution_id','nunique'),AF_links=('study_id','size'),journal_supported=('journal_support','sum'),citation_supported=('citation_support','sum'),common_links=('common','sum'),median_journal_controls=('n_journal_position','median'),median_citation_controls=('n_percentile_12m','median')).reset_index())
 table('T_SI2_coverage',a.groupby(['country','group','year','subfield','work_type','language_status'],dropna=False).agg(AF_links=('study_id','size'),journal_known=('journal_position','count'),citation_known=('percentile_12m','count')).reset_index())
 # All low-output candidates retained, including discordant/unknown outcomes.
 z=a[a.group.eq('L')&a.in_main_years].copy();jd=z.journal_position-z.ref_journal_position;cd=z.percentile_12m-z.ref_percentile_12m
 z['candidate_stratum']=np.select([jd.isna()|cd.isna(),jd.gt(0)&cd.gt(0),jd.le(0)&cd.le(0)],['unknown','concordant_positive','nonpositive'],default='discordant')
 z['selected_for_main_case']=False;z['fulltext_review_status']='not_certified';z['exclusion_from_main_case_reason']='Direct pathway evidence has not yet been certified for these focal institutions'
 z.sort_values(['candidate_stratum','work_id','institution_id']).to_csv(P/'cases/candidates.csv',index=False)
 dump(Q/'comparison_audit.json',{'common_AF_studies':int(a.loc[a.common,'study_id'].nunique()),'common_institutions':int(a.loc[a.common,'institution_id'].nunique()),'common_links':int(a.common.sum()),'fixed_population':48010,'countries':68,'activity_validation':'upstream independent activity validation remains pending','nonAF':'screen_negative only, uncertain labels excluded','single_AF_institutions_allowed':True})
 print('COMPARISONS AND COVERAGE COMPLETE',int(a.common.sum()),flush=True)
if __name__=='__main__':main()
