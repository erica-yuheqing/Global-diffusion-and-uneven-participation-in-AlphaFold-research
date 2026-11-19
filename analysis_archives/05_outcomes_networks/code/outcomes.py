"""V8 independent primary branches and all prespecified outcome sensitivities."""
from common import *
from bootstrap import engine,KEY,BINARY
from upstream_metrics import reference_percentiles
def supported(z,r,metrics,extra=None,minimum=1):
 keys=KEY+([extra] if extra else []);rr=r[r[metrics].notna().any(axis=1)]
 counts=rr.groupby(keys,dropna=False)[metrics].count().min(axis=1).rename('_usable_controls').reset_index()
 zz=z[z[metrics].notna().all(axis=1)].merge(counts,on=keys,how='inner',validate='many_to_one');return zz[zz._usable_controls.ge(minimum)],rr
def run_branch(z,r,name,metrics,extra=None,minimum=1,actual_inst=None):
 folder=T/'estimates';folder.mkdir(exist_ok=True);target=folder/(name+'.csv')
 if target.exists():return pd.read_csv(target)
 z,r=supported(z,r,metrics,extra,minimum)
 z.to_parquet(D/('AF_records_'+name+'.parquet'),index=False)
 rows,inst,_=engine(z,r,name,metrics,extra)
 for row in rows:
  if actual_inst is not None:
   row['n_institution_year_units']=row['n_institutions'];row['n_institutions']=z.loc[z.group.eq(row['group']),actual_inst].nunique();row['weighting']='equal_institution_year_then_AF_study'
  row['sample_role']='primary' if name in ['journal_full2025','citation_max'] else 'sensitivity_or_stratum'
  row['publication_window']='2020–2025' if name.startswith('journal_') and '2024' not in name else '2020–2024 or narrower; exact records supplied'
  row['citation_window_months']=24 if '24m' in row['metric'] else 12 if '12m' in row['metric'] or 'citation' in row['metric'] else None
  if row['n_institutions']<10:
   row['raw_conditional_lower']=row['lower'];row['raw_conditional_upper']=row['upper'];row['lower']=None;row['upper']=None;row['status']='completed_point_only_low_support'
 for metric in metrics:
  for group in ['L','M','H']:
   if not any(v['metric']==metric and v['group']==group for v in rows):rows.append(dict(sample_id=name,group=group,metric=metric,estimate=None,lower=None,upper=None,AF_mean=None,REF_mean=None,n_institutions=0,n_af_works=0,n_control_works=0,n_affiliation_links=0,n_countries=0,status='not_estimable_no_support',unit='percentage_points' if metric in BINARY else 'percentile_points',sample_role='sensitivity_or_stratum'))
 out=pd.DataFrame(rows);out.to_csv(target,index=False);return out
def main():
 a=pd.read_parquet(D/'matched_comparisons.parquet');r=pd.read_parquet(D/'control_links.parquet');J=['journal_position','high_journal75','high_journal90'];C=['percentile_12m','high_citation90','high_citation95']
 j=a[a.journal_support];cit=a[a.in_main_years&a.citation_support];common=a[a.common]
 run_branch(j,r,'journal_full2025',J);run_branch(cit,r,'citation_max',C)
 run_branch(a[a.in_main_years&a.journal_support],r,'journal_max2024',J);run_branch(common,r,'common',['journal_position','high_journal75','percentile_12m','high_citation90'])
 for outcome,z,metrics in [('journal',j,J[:2]),('citation',cit,C[:2])]:
  run_branch(z,r,outcome+'_min5',metrics,minimum=5)
  for mode in ['month','pub_quarter']:run_branch(z,r,outcome+'_'+mode,metrics,extra=mode)
  zz=z.copy();zz['actual_institution_id']=zz.institution_id;zz['institution_id']=zz.institution_id+'::'+zz.year.astype(str);rr=r.copy();rr['institution_id']=rr.institution_id+'::'+rr.year.astype(str)
  run_branch(zz,rr,outcome+'_institution_year',metrics,actual_inst='actual_institution_id')
  for year in range(2020,2026 if outcome=='journal' else 2025):run_branch(z[z.year.eq(year)],r,outcome+'_annual_'+str(year),metrics)
 run_branch(j[j.official_best_Q1.notna()],r,'journal_official_Q1',['official_best_Q1'])
 history=pd.read_parquet(D/'historical_control_links.parquet')
 for minimum in [1,3,5,10]:run_branch(common[common.history_n.ge(minimum).fillna(False)],history,'history_min'+str(minimum),['journal_position'])
 # Same AF records AND same available controls for 12/24-month comparison.
 rr=r[r.percentile_12m.notna()&r.percentile_24m.notna()];zz=cit[cit.percentile_24m.notna()]
 run_branch(zz,rr,'paired_12_24',['percentile_12m','percentile_24m','high_citation90','high_citation24_90'])
 p=pd.read_parquet(D/'paper_metrics.parquet')
 for minimum in [50,200]:
  name='citation_reference_min'+str(minimum)
  if (T/'estimates'/(name+'.csv')).exists():continue
  pct,cells=reference_percentiles(p,'citations_12m','mature12',minimum);table('reference_cells_min'+str(minimum),cells)
  bridge=pd.DataFrame({'study_id':p.study_id,'new_percentile':pct})
  zz=a[a.in_main_years].drop(columns=C).merge(bridge,on='study_id',validate='many_to_one');rr=r.drop(columns=C).merge(bridge,on='study_id',validate='many_to_one')
  for obj in [zz,rr]:
   obj['percentile_12m']=obj.pop('new_percentile');obj['high_citation90']=obj.percentile_12m.ge(90).where(obj.percentile_12m.notna()).astype(float);obj['high_citation95']=obj.percentile_12m.ge(95).where(obj.percentile_12m.notna()).astype(float)
  run_branch(zz,rr,name,C)
 marked=pd.read_parquet(I/'multidisciplinary_sources.parquet');broad_keys=set(zip(marked.source_id,marked.metric_year));bad=set(p.loc[[(s,y) in broad_keys for s,y in zip(p.source_id,p.year)],'study_id'])
 run_branch(j[~j.study_id.isin(bad)],r[~r.study_id.isin(bad)],'journal_exclude_multidisciplinary',J[:2])
 allrows=pd.concat([pd.read_csv(f) for f in sorted((T/'estimates').glob('*.csv'))],ignore_index=True);table('T_SI3_estimates',allrows)
 primary=allrows[allrows.sample_id.isin(['journal_full2025','citation_max'])];table('primary_estimates',primary)
 # Country and unique-study reweighting hold exactly the same primary support.
 reweighted=[]
 for name,z,metric in [('journal_full2025',j,'journal_position'),('citation_max',cit,'percentile_12m')]:
  draws=pd.read_parquet(D/('draws_'+name+'.parquet'))
  for group in ['L','M','H']:
   block=z[z.group.eq(group)];columns=[metric,'ref_'+metric]
   for weighting,col in [('country_equal','country_equal_delta'),('paper_equal','paper_equal_delta')]:
    absolute=block.groupby(['country','institution_id'])[columns].mean().groupby('country').mean().mean() if weighting=='country_equal' else block.groupby('study_id')[columns].mean().mean()
    values=draws.loc[draws.group.eq(group)&draws.metric.eq(metric),col]
    reweighted.append(dict(sample_id=name+'_'+weighting,group=group,metric=metric,estimate=absolute[metric]-absolute['ref_'+metric],AF_mean=absolute[metric],REF_mean=absolute['ref_'+metric],lower=values.quantile(.025),upper=values.quantile(.975),n_institutions=block.institution_id.nunique(),n_af_works=block.study_id.nunique(),n_affiliation_links=len(block),n_countries=block.country.nunique(),weighting=weighting,interval_type='conditional_shared_study_Exp1_5000',status='completed'))
 table('outcome_weighting',pd.DataFrame(reweighted))
 dump(Q/'outcome_audit.json',{'primary_journal':'journal_full2025','primary_citation':'citation_max','same_AF_sample_required':False,'shared_study_multiplier_keyed_across_subsets':True,'all_branches_in_summary':len(allrows),'no_result_direction_selection':True})
 print('OUTCOME PRIMARY AND PRESPECIFIED SENSITIVITIES COMPLETE',len(allrows),flush=True)
if __name__=='__main__':main()
