"""Outcome-specific activity/role/collaboration strata; stable-author legacy cohort."""
from common import *
from outcomes import run_branch
from bootstrap import engine,M

def stable_authors(c,a):
 main=a[a.common].copy();c.register('main',main[['study_id','work_id','institution_id','year','subfield','work_type','country','group']])
 # Stable = exactly one observed baseline institution and exactly that same
 # institution in the local current-period record, conditional on frozen IDs.
 # This is observed-ID stability, not external identity validation.
 c.execute('''CREATE TEMP TABLE candidate_authors AS SELECT DISTINCT f.author_id FROM f JOIN main m ON f.work_id=m.work_id AND f.institution_id=m.institution_id WHERE f.author_id IS NOT NULL''')
 c.execute('''CREATE TEMP TABLE author_observed AS SELECT DISTINCT f.author_id,f.institution_id,p.study_id,p.work_id,p.year,p.subfield,p.work_type,
 p.confirmed_af,p.screen_negative,p.journal_position,p.percentile_12m,
 (p.journal_position>=75)::DOUBLE high_journal75,(p.percentile_12m>=90)::DOUBLE high_citation90
 FROM f SEMI JOIN candidate_authors ca USING(author_id) JOIN p ON f.work_id=p.work_id WHERE p.year<=2024''')
 c.execute('''CREATE TEMP TABLE stable_baseline AS SELECT f.author_id,min(f.institution_id) institution_id
 FROM f SEMI JOIN candidate_authors ca USING(author_id) JOIN old ON f.work_id=old.work_id
 WHERE old.year BETWEEN 2015 AND 2019 GROUP BY 1 HAVING count(DISTINCT f.institution_id)=1''')
 c.execute('''CREATE TEMP TABLE stable AS SELECT a.author_id,min(a.institution_id) institution_id FROM author_observed a
 JOIN stable_baseline b ON a.author_id=b.author_id GROUP BY 1 HAVING count(DISTINCT a.institution_id)=1 AND min(a.institution_id)=min(b.institution_id)''')
 stable=c.execute('SELECT * FROM stable').df();stable.to_parquet(D/'stable_author_registry.parquet',index=False)
 if len(stable):
  c.execute('''CREATE TEMP TABLE ar AS SELECT a.author_id,a.year,a.subfield,a.work_type,'''+','.join('count('+m+') n_'+m+',avg('+m+') ref_'+m for m in M[:4])+''' FROM author_observed a JOIN stable b USING(author_id,institution_id) WHERE screen_negative AND subfield IS NOT NULL GROUP BY 1,2,3,4''')
  author=c.execute('''SELECT a.*,r.* EXCLUDE(author_id,year,subfield,work_type) FROM author_observed a JOIN stable b USING(author_id,institution_id)
   LEFT JOIN ar r USING(author_id,year,subfield,work_type) WHERE a.confirmed_af''').df()
  author=author[author.journal_position.notna()&author.percentile_12m.notna()&author.n_journal_position.ge(1)&author.n_percentile_12m.ge(1)]
  inst=pd.read_parquet(I/'institutions.parquet')[['institution_id','country','group']]
  author=author.merge(inst,on='institution_id',validate='many_to_one');author['actual_institution_id']=author.institution_id;author['institution_id']=author.author_id
  author_refs=c.execute('SELECT a.* FROM author_observed a JOIN stable b USING(author_id,institution_id) WHERE a.screen_negative').df();author_refs['institution_id']=author_refs.author_id
  if len(author):
   rows,units,_=engine(author,author_refs,'stable_authors',M[:4])
   for row in rows:
    row['n_authors']=row['n_institutions'];row['n_institutions']=author.loc[author.group.eq(row['group']),'actual_institution_id'].nunique();row['weighting']='equal_observed_stable_author'
   table('stable_author_estimates',pd.DataFrame(rows));pd.DataFrame(rows).to_csv(T/'estimates/stable_authors.csv',index=False);units.rename(columns={'institution_id':'author_id'}).to_parquet(D/'author_metrics.parquet',index=False)

def main():
 c=con()
 for name,path in [('p',D/'paper_metrics.parquet'),('old',I/'paper_base.parquet'),('f',I/'author_affiliations.parquet'),('u',I/'authorships.parquet'),('act',I/'activities.parquet'),('quality',D/'study_roster_quality.parquet')]:view(c,name,path)
 a=pd.read_parquet(D/'matched_comparisons.parquet');r=pd.read_parquet(D/'control_links.parquet');c.register('main',a[['study_id','work_id','institution_id','year','subfield','work_type','country','group']])
 role=c.execute("""SELECT m.study_id,m.institution_id,bool_or(u.author_position='first' OR u.author_position='last' OR u.is_corresponding) any_role,
 bool_or(u.author_position IS NULL OR u.is_corresponding IS NULL) missing_role,bool_or(u.author_position='first') first_role,
 bool_or(u.author_position='last') last_role,bool_or(u.is_corresponding) corresponding_role
 FROM main m LEFT JOIN f ON m.work_id=f.work_id AND m.institution_id=f.institution_id LEFT JOIN u ON f.work_id=u.work_id AND f.author_id=u.author_id GROUP BY 1,2""").df()
 role['role_class']=np.select([role.any_role.fillna(False),role.missing_role.fillna(True)],['any_first_last_corresponding','unknown'],default='other_observed_positions')
 q=c.execute('SELECT quality.* FROM quality SEMI JOIN main USING(study_id)').df()
 q['collaboration']=np.select([q.n_countries.ge(2),q.observed_author_roster_covered&q.missing_country_rows.eq(0)&q.n_countries.eq(1)&q.n_institutions.gt(1),q.observed_author_roster_covered&q.missing_country_rows.eq(0)&q.n_countries.eq(1)&q.n_institutions.eq(1)],['international','domestic_multi','domestic_single'],default='unknown')
 a=a.merge(role,on=['study_id','institution_id'],validate='one_to_one').merge(q[['study_id','collaboration']],on='study_id',validate='many_to_one');a.to_parquet(D/'stratified_AF_links.parquet',index=False)
 acts=c.execute("SELECT p.study_id,act.activity,act.state,act.positive,act.determinate FROM act JOIN p ON act.work_id=p.work_id WHERE act.label_level='mode'").df();acts.to_parquet(D/'activities.parquet',index=False);support=[]
 for outcome,mask,metrics in [('journal',a.journal_support,['journal_position','high_journal75']),('citation',a.in_main_years&a.citation_support,['percentile_12m','high_citation90'])]:
  z=a[mask]
  for activity,block in acts.groupby('activity'):
   positive=set(block.loc[block.positive,'study_id']);known=set(block.loc[block.determinate,'study_id']);run_branch(z[z.study_id.isin(positive)],r,outcome+'_activity_'+activity,metrics)
   for group in ['L','M','H']:
    zz=z[z.group.eq(group)];total=zz.study_id.nunique();nk=zz.loc[zz.study_id.isin(known),'study_id'].nunique();pos=zz.loc[zz.study_id.isin(positive),'study_id'].nunique();support.append(dict(outcome=outcome,activity=activity,group=group,AF_total=total,assessable=nk,positive=pos,negative=nk-pos,unknown=total-nk,independent_human_validation='not_certified_upstream'))
  for value in ['international','domestic_multi','domestic_single']:run_branch(z[z.collaboration.eq(value)],r,outcome+'_cooperation_'+value,metrics)
  for value in ['any_first_last_corresponding','other_observed_positions']:run_branch(z[z.group.eq('L')&z.role_class.eq(value)],r,outcome+'_position_'+value,metrics)
  rows=[]
  for kind,col,groups,levels in [('position','role_class',['L'],['any_first_last_corresponding','other_observed_positions']),('cooperation','collaboration',['L','M','H'],['domestic_single','domestic_multi','international'])]:
   for group in groups:
    b=z[z.group.eq(group)&z[col].isin(levels)];sizes=b.groupby(['year','subfield','work_type'])[col].nunique();keys=sizes[sizes.eq(len(levels))].reset_index()[['year','subfield','work_type']];selected=b.merge(keys,on=['year','subfield','work_type'])
    for level in levels:
     before=b[b[col].eq(level)];after=selected[selected[col].eq(level)];rows.append(dict(outcome=outcome,kind=kind,group=group,stratum=level,institutions_before=before.institution_id.nunique(),institutions_after=after.institution_id.nunique(),AF_before=before.study_id.nunique(),AF_after=after.study_id.nunique(),common_cells=len(keys)))
  table('ED_SI3_support_'+outcome,pd.DataFrame(rows))
 table('activity_assessability',pd.DataFrame(support))
 if not (T/'estimates/stable_authors.csv').exists():stable_authors(c,a)
 table('T_SI3_estimates',pd.concat([pd.read_csv(f) for f in sorted((T/'estimates').glob('*.csv'))],ignore_index=True))
 dump(Q/'strata_audit.json',{'outcome_specific_primary_sets':True,'stable_author_start':'legacy common cohort retained, not expanded silently','activities':'positive/negative/unknown retained; independent human validation not certified','role':'any first/last/corresponding vs other known; unknown separate','collaboration':'international if >=2 observed countries; domestic only if observed author roster covered and countries available'})
 print('OUTCOME-SPECIFIC ACTIVITY/ROLE/COOPERATION AND STABLE AUTHOR BRANCHES COMPLETE',flush=True)
if __name__=='__main__':main()
