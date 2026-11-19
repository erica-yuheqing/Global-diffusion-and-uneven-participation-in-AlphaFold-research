"""Fixed denominators, observable missingness, complete traceable matching links."""
from common import *
POSSIBLE="(m.confirmed_af OR m.possible_af OR m.af_use_label='uncertain' OR (m.af_use_label='yes' AND m.adoption_eligible='uncertain'))"
def coverage(c,endyear):
 c.execute('''CREATE OR REPLACE TEMP TABLE events AS SELECT i.institution_id,i.country,i."group",
 coalesce(bool_or(m.confirmed_af),false) af_confirmed,coalesce(bool_or('''+POSSIBLE+'''),false) af_possible,
 coalesce(bool_or(m.confirmed_af AND m.journal_position>=75),false) venue_confirmed,
 coalesce(bool_or('''+POSSIBLE+''' AND (m.journal_position>=75 OR m.journal_position IS NULL)),false) venue_possible,
 coalesce(bool_or(m.confirmed_af AND m.percentile_12m>=90),false) citation_confirmed,
 coalesce(bool_or('''+POSSIBLE+''' AND (m.percentile_12m>=90 OR m.percentile_12m IS NULL)),false) citation_possible
 FROM i LEFT JOIN l USING(institution_id) LEFT JOIN m ON l.study_id=m.study_id AND m.year BETWEEN 2020 AND '''+str(endyear)+''' WHERE i.baseline_eligible GROUP BY 1,2,3''')
 parquet(c,'SELECT * FROM events',D/f'coverage_events_{endyear}.parquet')
 z=c.execute('SELECT country,"group",count(*) baseline_denominator,'+','.join('sum('+ev+'_confirmed::INT) '+ev+'_confirmed_n,sum('+ev+'_possible::INT) '+ev+'_possible_n,avg('+ev+'_confirmed::INT)*100 '+ev+'_lower,avg('+ev+'_possible::INT)*100 '+ev+'_upper' for ev in ['af','venue','citation'])+' FROM events GROUP BY 1,2').df();z['publication_end_year']=endyear
 require(len(z)==204 and z.baseline_denominator.sum()==48010,'Fixed coverage denominator differs');table(f'coverage_country_group_{endyear}',z)
 summary=z.groupby('group')[[ev+s for ev in ['af','venue','citation'] for s in ['_lower','_upper']]].mean().reset_index();summary['publication_end_year']=endyear;table(f'coverage_summary_{endyear}',summary)
 return z,summary
def main():
 c=con()
 for n,path in [('p',I/'paper_base.parquet'),('bridge',I/'approved_crosswalk.parquet'),('i',I/'institutions.parquet'),('l',I/'work_institutions.parquet'),('m',D/'paper_metrics.parquet'),('a',D/'matched_comparisons.parquet'),('r',D/'control_links.parquet'),('q',D/'study_roster_quality.parquet'),('node',D/'networks/baseline_B2/nodes.parquet'),('ps',D/'partners_degree.parquet')]:view(c,n,path)
 flows=[]
 for name,sql,unit in [('eligible_work_records','SELECT work_id FROM bridge','work'),('approved_studies','SELECT study_id FROM p','study'),('eligible_2020_2025','SELECT study_id FROM m','study'),('eligible_2020_2024','SELECT study_id FROM m WHERE year<=2024','study'),('AF_2020_2025','SELECT study_id FROM m WHERE confirmed_af','study'),('AF_2020_2024','SELECT study_id FROM m WHERE confirmed_af AND year<=2024','study'),('journal_primary','SELECT DISTINCT study_id FROM a WHERE journal_support','study'),('citation_primary','SELECT DISTINCT study_id FROM a WHERE in_main_years AND citation_support','study'),('common_2020_2024','SELECT DISTINCT study_id FROM a WHERE common','study')]:flows.append(dict(stage=name,count=c.execute('SELECT count(*) FROM ('+sql+')').fetchone()[0],unit=unit))
 table('T_SI1_global_flow',pd.DataFrame(flows))
 frame=pd.read_parquet(D/'matched_comparisons.parquet');wide=[];flow=[];miss=[]
 for window,mask in [('2020_2025',pd.Series(True,index=frame.index)),('2020_2024',frame.in_main_years)]:
  z=frame[mask];c.register('scope',z)
  wide.append(c.execute('''SELECT i.country,i."group",count(*) baseline_institutions,count(*) FILTER(WHERE n.AF_n>0) AF_institutions,
  count(*) FILTER(WHERE n.AF_n IS NULL) no_observed_AF_institutions,count(*) FILTER(WHERE n.J>0) journal_matched_institutions,
  count(*) FILTER(WHERE n.C>0) citation_matched_institutions,count(*) FILTER(WHERE n.JC>0) common_institutions,
  count(*) FILTER(WHERE n.AF_n=1) single_AF_institutions FROM i LEFT JOIN (SELECT institution_id,count(DISTINCT study_id) AF_n,
  sum(journal_support::INT) J,sum(citation_support::INT) C,sum(common::INT) JC FROM scope GROUP BY 1) n USING(institution_id)
  WHERE i.baseline_eligible GROUP BY 1,2''').df().assign(window=window))
  for group in ['L','M','H']:
   zz=z[z.group.eq(group)];baseline=c.execute('SELECT count(*) FROM i WHERE baseline_eligible AND "group"=?',[group]).fetchone()[0]
   for sample,condition in [('AF_participants',pd.Series(True,index=zz.index)),('journal_matched',zz.journal_support),('citation_matched',zz.citation_support if window=='2020_2024' else pd.Series(False,index=zz.index)),('common',zz.common)]:
    b=zz[condition];flow.append(dict(window=window,sample_id=sample,group=group,n_institutions=b.institution_id.nunique(),n_AF_unique=b.study_id.nunique(),n_links=len(b),baseline_denominator=baseline,retention_percent=100*b.institution_id.nunique()/baseline))
  pp=z.merge(pd.read_parquet(D/'partners_degree.parquet')[['study_id','institution_id','x_log','focal_in_roster','observed_author_roster_covered','n_outside_boundary','n_unknown_baseline','partner_mean_percentile']],on=['study_id','institution_id'],validate='one_to_one')
  flags={'journal_missing':pp.journal_position.isna(),'citation_quality_or_rank_missing':pp.percentile_12m.isna()&pp.year.le(2024),'citation_immature_2025':pp.year.eq(2025),'no_journal_reference':pp.journal_position.notna()&pp.n_journal_position.fillna(0).eq(0),'no_citation_reference':pp.percentile_12m.notna()&pp.n_percentile_12m.fillna(0).eq(0),'network_baseline_unknown':pp.x_log.isna(),'focal_not_in_raw_roster':~pp.focal_in_roster,'observed_author_roster_uncovered':~pp.observed_author_roster_covered,'outside_boundary_partner':pp.n_outside_boundary.gt(0),'unknown_partner_baseline':pp.n_unknown_baseline.gt(0)}
  for group in ['L','M','H']:
   g=pp.group.eq(group)
   for name,flag in flags.items():miss.append(dict(window=window,group=group,reason=name,AF_links=int((g&flag).sum()),AF_studies=pp.loc[g&flag,'study_id'].nunique(),denominator_AF_links=int(g.sum()),percent=100*(g&flag).sum()/g.sum() if g.sum() else np.nan,overlapping=True))
 table('T_SI1_country_group',pd.concat(wide,ignore_index=True));table('T_SI1',pd.DataFrame(flow));table('T_SI1_overlapping_missingness',pd.DataFrame(miss))
 table('T_SI2',frame.groupby(['country','group','year','subfield','work_type','language_status'],dropna=False).agg(AF_links=('study_id','size'),AF_studies=('study_id','nunique'),journal_known=('journal_position','count'),citation_known=('percentile_12m','count'),journal_supported=('journal_support','sum'),citation_supported=('citation_support','sum')).reset_index())
 table('T_SI4',frame.groupby(['institution_id','country','group','year','subfield','work_type'],dropna=False).agg(AF_links=('study_id','size'),journal_controls=('n_journal_position','max'),citation_controls=('n_percentile_12m','max'),journal_supported_AF=('journal_support','sum'),citation_supported_AF=('citation_support','sum')).reset_index())
 # Literal control links, streamed by year to avoid quadratic in-memory tables.
 for outcome,metric,predicate,years in [('journal','journal_position','a.journal_support',range(2020,2026)),('citation','percentile_12m','a.in_main_years AND a.citation_support',range(2020,2025))]:
  folder=D/'comparison_links'/outcome;folder.mkdir(parents=True,exist_ok=True)
  for year in years:
   dest=folder/f'{year}.parquet'
   if dest.exists():continue
   sql=f'''SELECT '{outcome}' outcome,a.study_id focal_study_id,a.institution_id,r.study_id control_study_id,
   a.institution_id||'|'||a.year::VARCHAR||'|'||a.subfield||'|'||a.work_type match_cell_id,'usable_observed_reference' support_status
   FROM a JOIN r USING(institution_id,year,subfield,work_type) WHERE {predicate} AND a.year={year} AND r.{metric} IS NOT NULL'''
   parquet(c,sql,dest);print('Literal comparison links',outcome,year,flush=True)
  path=str(folder/'*.parquet');table('T_SI4_control_reuse_'+outcome,c.execute("SELECT \"group\",count(*) unique_control_studies,sum(use_n) reference_uses,max(use_n) maximum_reuse,median(use_n) median_reuse FROM (SELECT i.\"group\",l.control_study_id,count(*) use_n FROM read_parquet("+lit(path)+") l JOIN i USING(institution_id) GROUP BY 1,2) u GROUP BY 1").df())
 cov24,s24=coverage(c,2024);cov25,s25=coverage(c,2025);long=[]
 for v in [cov24,cov25]:
  for event in ['af','venue','citation']:
   if v.publication_end_year.iloc[0]==2025 and event=='citation':continue
   z=v[['country','group','publication_end_year','baseline_denominator',event+'_confirmed_n',event+'_possible_n',event+'_lower',event+'_upper']].rename(columns={event+'_confirmed_n':'confirmed_success_institutions',event+'_possible_n':'possible_success_institutions',event+'_lower':'coverage_lower',event+'_upper':'coverage_upper'});z['unresolved_institutions']=z.possible_success_institutions-z.confirmed_success_institutions;z['event']=event;long.append(z)
 table('T_SI6_coverage',pd.concat(long,ignore_index=True));table('coverage_summary',pd.concat([s24,s25],ignore_index=True))
 opportunity=frame.groupby(['institution_id','group','country']).agg(first_AF_year=('year','min'),observed_AF_years=('year','nunique'),AF_studies=('study_id','nunique')).reset_index();opportunity.to_parquet(D/'institution_opportunity.parquet',index=False)
 c.execute('''CREATE TEMP TABLE entry AS SELECT l.institution_id,min(p.publication_date) first_date FROM l JOIN p USING(study_id,work_id,year)
 WHERE p.confirmed_af GROUP BY 1 HAVING min(p.publication_date)>=DATE '2020-01-01' AND min(p.publication_date)+INTERVAL 36 MONTH<=DATE '2025-12-31' ''')
 entry=[]
 for months in [12,24]:
  z=c.execute('''SELECT e.institution_id,i.country,i."group",coalesce(bool_or(m.confirmed_af AND m.journal_position>=75),false) venue_confirmed,
  coalesce(bool_or(m.study_id IS NOT NULL AND (m.journal_position>=75 OR m.journal_position IS NULL)),false) venue_possible,
  coalesce(bool_or(m.confirmed_af AND m.percentile_12m>=90),false) citation_confirmed,
  coalesce(bool_or(m.study_id IS NOT NULL AND (m.percentile_12m>=90 OR m.percentile_12m IS NULL)),false) citation_possible
  FROM entry e JOIN i USING(institution_id) LEFT JOIN l ON e.institution_id=l.institution_id
  LEFT JOIN m ON l.study_id=m.study_id AND '''+POSSIBLE+''' AND m.publication_date>=e.first_date AND m.publication_date<e.first_date+INTERVAL '''+str(months)+''' MONTH GROUP BY 1,2,3''').df();z['followup_months']=months;entry.append(z)
 entry=pd.concat(entry,ignore_index=True);entry.to_parquet(D/'entry_opportunity.parquet',index=False);table('entry_opportunity_summary',entry.groupby(['group','followup_months']).agg(institutions=('institution_id','size'),venue_confirmed=('venue_confirmed','mean'),venue_possible=('venue_possible','mean'),citation_confirmed=('citation_confirmed','mean'),citation_possible=('citation_possible','mean')).reset_index())
 source=pd.read_parquet(D/'new_source_observations.parquet');source['history_status']=np.where(source.history_n.ge(1).fillna(False),'observed_support','no_same_field_type_history')
 inst=source.groupby(['institution_id','group','year']).agg(new_source_share=('source_not_observed_in_baseline','mean')).reset_index();table('new_source_share',inst.groupby(['group','year']).agg(mean_new_source_share=('new_source_share','mean'),institutions=('institution_id','nunique')).reset_index())
 pos=source.groupby(['institution_id','group','year','source_not_observed_in_baseline']).journal_position.mean().reset_index();table('new_source_positions',pos.groupby(['group','year','source_not_observed_in_baseline']).agg(journal_position=('journal_position','mean'),institutions=('institution_id','nunique')).reset_index());table('history_support',source.groupby(['group','year','history_status'],dropna=False).agg(AF_studies=('study_id','nunique'),AF_links=('study_id','size'),institutions=('institution_id','nunique'),median_history_papers=('history_n','median'),median_history_years=('history_years','median'),journal_known=('journal_position','count')).reset_index())
 source.to_parquet(D/'new_source_with_history_status.parquet',index=False)
 # Standardized composition diagnostics are point-only, not causal DID.
 composition=[]
 for outcome,mask,metric in [('journal',frame.in_main_years&frame.journal_support,'journal_position'),('citation',frame.in_main_years&frame.citation_support,'percentile_12m')]:
  z=frame[mask];cells=z.groupby(['institution_id','group','year','subfield','work_type']).agg(AF=(metric,'mean'),REF=('ref_'+metric,'mean')).reset_index();support=cells.groupby(['year','subfield','work_type']).group.nunique();keys=support[support.eq(3)].reset_index()[['year','subfield','work_type']];common=cells.merge(keys,on=['year','subfield','work_type'])
  for group in ['L','M','H']:
   block=common[common.group.eq(group)];v=block.groupby(['year','subfield','work_type'])[['AF','REF']].mean().mean();composition.append(dict(outcome=outcome,group=group,AF_mean=v.AF,REF_mean=v.REF,difference=v.AF-v.REF,common_strata=len(keys),n_institutions=block.institution_id.nunique(),status='point_only_equal_common_strata_then_institution'))
 table('T_SI6_common_composition',pd.DataFrame(composition));gaps=[]
 for outcome,v in pd.DataFrame(composition).groupby('outcome'):
  v=v.set_index('group');gaps.append(dict(outcome=outcome,AF_L_minus_H=v.loc['L','AF_mean']-v.loc['H','AF_mean'],REF_L_minus_H=v.loc['L','REF_mean']-v.loc['H','REF_mean'],gap_of_gaps=v.loc['L','difference']-v.loc['H','difference'],causal_DID=False,status='point_only'))
 table('T_SI6_group_gaps',pd.DataFrame(gaps))
 # Retain the complete candidate ledger; no primary case is selected.
 cases=pd.read_csv(P/'cases/candidates.csv');cases['selected_for_main_case']=False;cases['review_population']='inherited low-group 2020–2024 review, not silently expanded';table('T_SI7',cases)
 dump(Q/'data_tables_audit.json',{'fixed_B2':48010,'countries':68,'coverage_main_end':2024,'journal_2025_coverage_separate':True,'literal_matching_links_streamed_by_year':True,'same_entrant_cohort_12_24':True,'history_start':'old common, not silently replaced','case_main_panel':'not restored','language_unknown_not_English':True})
 print('FLOW/MISSINGNESS/CONTROLS/FIXED-COVERAGE/OPPORTUNITY TABLES COMPLETE',flush=True)
if __name__=='__main__':main()
