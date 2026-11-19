"""Build one frozen institution/window table and complete publication opportunities."""
import argparse
import json
import numpy as np
import pandas as pd
from support import *

def build(out):
    e=pd.read_parquet(OLD/'tables/institution_events.parquet')
    frozen=pd.read_parquet(OLD/'tables/institution_history.parquet')
    code=oldcode();scale=frozen[['institution_id','baseline_papers','fixed_cohort_ge1']]
    h,z=code.history(e,scale)
    require(np.array_equal(h.eligible_fixed,frozen.eligible_fixed),'Primary follow-up membership changed')
    primary=h[h.eligible_fixed].copy()
    require((len(primary),int(primary.repeat.sum()),int(primary.sustained.sum()))==(2339,1255,454),'Primary cohort reconstruction failed')
    f2=pd.read_parquet(F2/'tables/entry_cohort_registry.parquet').set_index('institution_id')
    require(f2.loc[primary.institution_id,'entry_cohort'].isin(['Pre-AF2','AF2','AF3']).all(),'Cohort is outside Figure2 resolved entries')
    mh,mz=monthly_history(e,scale)
    sens=[]
    for policy,history in [('day_primary',h),('all_month_precision_sensitivity',mh)]:
        a=code.state_summary(history)
        a['policy']=policy;sens.append(a)
    save(out,'window_policy_sensitivity',pd.concat(sens,ignore_index=True))
    save(out,'complete_cohort',primary)
    save(out,'cohort_flow',h.groupby(['fixed_cohort_ge1','status'],dropna=False).size().rename('N').reset_index())
    save(out,'panel_a_participation',code.state_summary(h).rename(columns={'state':'status','institutions':'N','percent':'percentage'}))
    r=code.followup_relations(z,h)
    save(out,'af_initial_followup_relations',r)
    activity=pd.read_parquet(OLD/'tables/activity_relations.parquet')
    require(not activity.duplicated(['institution_id','study_id','activity']).any(),'Activity relation duplicates')
    initial=activity[activity.interval.eq(0)].copy()
    save(out,'initial_activity_evidence',initial)
    first=initial.groupby(['institution_id','activity']).agg(initial_studies=('study_id','nunique'),supported=('supported','sum'),assessable=('strict_determinate','sum')).reset_index()
    first['initial_state']=np.select([first.supported.gt(0),first.assessable.eq(first.initial_studies)],['present','assessed_absent'],default='unassessable')
    require(len(first)==4*len(primary),'An institution lacks initial activity set')
    save(out,'initial_activity_institution',first)
    features=pd.read_parquet(OLD/'tables/baseline_predictors.parquet')
    base=primary.merge(features.drop(columns=['baseline_papers','fixed_cohort_ge1','repeat','sustained']),on='institution_id',validate='one_to_one')
    thresholds=[]
    for variable in ['baseline_papers','known_linked_author_ids','observed_partner_ids']:
        q,cuts=quintiles(base[variable]);base[variable+'_quintile']=q
        for k,v in enumerate(cuts,1):thresholds.append(dict(measure=variable,cut_index=k,cut=v,method='type7_ties_lower_group_key_round12'))
    base['quintile']=base.baseline_papers_quintile
    save(out,'quintile_cut_points',pd.DataFrame(thresholds))
    with connect(out) as c:
        c.register('cohort',primary[['institution_id','first_date','month12_end','window_end']])
        # Restrict columns/years before linking, not a 4.7-million × institution Cartesian join.
        c.execute(f'''CREATE TEMP TABLE studies AS SELECT study_id,annual_representative_work_id AS work_id,
          publication_year,try_cast(publication_date AS DATE) AS date,primary_subfield_id,
          confirmed_af,screen_negative,af_use_label,adoption_eligible,possible_af
          FROM read_parquet({lit(F1/'derived_study_records.parquet')})
          WHERE publication_year BETWEEN 2020 AND 2025''')
        c.execute(f'''CREATE TEMP TABLE target_links AS SELECT DISTINCT i.work_id,i.institution_id
          FROM read_parquet({lit(UP/'out_v2/work_institutions.parquet')}) i JOIN cohort h USING(institution_id)''')
        c.execute('''CREATE TEMP TABLE nonaf AS SELECT DISTINCT h.institution_id,s.study_id,s.work_id AS source_work_id,
          s.date,s.primary_subfield_id,s.publication_year AS reference_year,
          FALSE AS confirmed_af, CASE WHEN s.screen_negative OR s.af_use_label='no' THEN 'comparison' ELSE 'unknown_label' END AS label_state,
          CASE WHEN s.date>h.first_date AND s.date<=h.month12_end THEN 1
               WHEN s.date>h.month12_end AND s.date<=h.window_end THEN 2 ELSE -1 END AS interval,
          h.first_date,h.month12_end,h.window_end
          FROM studies s JOIN target_links i USING(work_id) JOIN cohort h USING(institution_id)
          WHERE NOT s.confirmed_af''')
        nonaf=c.execute('SELECT * FROM nonaf WHERE interval>0').df()
        # Missing/conflicting dates that may overlap a window must be visible.
        missing=c.execute('''SELECT h.institution_id,count(*) AS undated_possible_window_records
          FROM studies s JOIN target_links i USING(work_id) JOIN cohort h USING(institution_id)
          WHERE NOT s.confirmed_af AND (s.date IS NULL OR year(s.date)<>s.publication_year)
          AND s.publication_year BETWEEN year(h.first_date) AND year(h.window_end) GROUP BY h.institution_id''').df()
        af=r[r.interval.gt(0)].merge(c.execute('SELECT study_id,publication_year AS reference_year,primary_subfield_id FROM studies WHERE confirmed_af').df(),on='study_id',how='left',validate='many_to_one')
        require(af.reference_year.notna().all(),'An AF event lacks the latest confirmed study metadata')
        af=af.rename(columns={'event_date':'date','event_source_work_id':'source_work_id'})
        af['confirmed_af']=True;af['label_state']='AF'
        af=af.merge(primary[['institution_id','month12_end','window_end']],on='institution_id',validate='many_to_one')
        cols=['institution_id','study_id','source_work_id','date','primary_subfield_id','reference_year','confirmed_af','label_state','interval','first_date','month12_end','window_end']
        opportunities=pd.concat([nonaf[cols],af[cols]],ignore_index=True)
        require(not opportunities.duplicated(['institution_id','study_id']).any(),'Study counted twice within an institution')
        require(opportunities.date.notna().all(),'Undated opportunities cannot be assigned to a window')
        opportunities['year']=pd.to_datetime(opportunities.date).dt.year
        opportunities['subfield']=opportunities.primary_subfield_id.fillna('Unknown subfield')
        # Reference has one row per research unit, even where version-specific event years differ.
        ref=opportunities[['study_id','primary_subfield_id','reference_year','label_state','confirmed_af']].drop_duplicates()
        require(not ref.study_id.duplicated().any(),'Conflicting reference metadata across institutions')
        ref=ref.rename(columns={'reference_year':'year'});ref['subfield']=ref.primary_subfield_id.fillna('Unknown subfield')
        save(out,'publication_opportunities',opportunities,csv=False)
        save(out,'benchmark_reference_unique_studies',ref,csv=False)
        # Alternative reference covers the whole frozen corpus, not just entered institutions.
        globalref=c.execute('''SELECT coalesce(primary_subfield_id,'Unknown subfield') AS subfield,
          publication_year AS year,count(*) AS all_n,
          count(*) FILTER (WHERE confirmed_af) AS af_n,
          count(*) FILTER (WHERE NOT confirmed_af AND (screen_negative OR af_use_label='no')) AS comparison_n
          FROM studies GROUP BY ALL''').df()
        globalref['unknown_n']=globalref.all_n-globalref.af_n-globalref.comparison_n
        save(out,'all_corpus_reference_counts',globalref)
        # Baseline affiliations determine country, not later AF output.
        c.register('all_base_ids',base[['institution_id']])
        countries=c.execute(f'''SELECT i.institution_id,i.country_code,count(DISTINCT i.work_id) AS baseline_works
          FROM read_parquet({lit(UP/'out_v2/work_institutions.parquet')}) i
          JOIN all_base_ids b USING(institution_id)
          JOIN read_parquet({lit(UP/'out_v2/works_eligible.parquet')}) w USING(work_id)
          WHERE w.publication_year BETWEEN 2015 AND 2019 GROUP BY ALL''').df()
        dominant=[]
        for inst,x in countries.groupby('institution_id'):
            top=x[x.baseline_works.eq(x.baseline_works.max())]
            dominant.append(dict(institution_id=inst,baseline_country=top.country_code.iloc[0] if len(top)==1 else 'Multiple baseline countries',baseline_country_tied=len(top)>1))
        base=base.merge(pd.DataFrame(dominant),on='institution_id',how='left',validate='one_to_one')
        base['baseline_country']=base.baseline_country.fillna('Unknown')
    background=pd.read_parquet(UP/'model_foundations_v1/institution_background_long.parquet')
    background=background[background.institution_id.isin(base.institution_id)&~background.subfield_unknown].copy()
    dominant=background.sort_values(['institution_id','subfield_papers','primary_subfield_id'],ascending=[True,False,True]).drop_duplicates('institution_id')
    base=base.merge(dominant[['institution_id','primary_subfield_id']].rename(columns={'primary_subfield_id':'baseline_subfield'}),on='institution_id',how='left',validate='one_to_one')
    base['baseline_subfield']=base.baseline_subfield.fillna('Unknown')
    base['entry_year']=base.first_date.dt.year
    for col,minimum in [('baseline_country',30),('baseline_subfield',50)]:
        counts=base[col].value_counts();base[col+'_model']=base[col].where(base[col].map(counts).ge(minimum)|base[col].eq('Unknown'),'Other')
    base=base.merge(missing,on='institution_id',how='left',validate='one_to_one')
    base['undated_possible_window_records']=base.undated_possible_window_records.fillna(0).astype(int)
    base['opportunity_timing_complete']=base.undated_possible_window_records.eq(0)
    save(out,'institution_analysis_base',base)
    qa=[]
    actual=opportunities[opportunities.confirmed_af].groupby(['institution_id','interval']).size().unstack(fill_value=0).reindex(index=primary.institution_id,columns=[1,2],fill_value=0)
    expected=primary.set_index('institution_id')[['bin1','bin2']]
    require(np.array_equal(actual,expected),'AF opportunities do not reproduce follow-up outcome counts')
    qa.extend([dict(check='cohort_2339',value=len(base),status='PASS'),dict(check='AF_integer_windows_match_old',value=len(af),status='PASS'),
      dict(check='opportunity_relations',value=len(opportunities),status='OBSERVED'),dict(check='unique_reference_studies',value=len(ref),status='OBSERVED'),
      dict(check='date_incomplete_institutions',value=int((~base.opportunity_timing_complete).sum()),status='RETAINED'),
      dict(check='member_reference_year_disagreements',value=int(opportunities.year.ne(opportunities.reference_year).sum()),status='AUDITED')])
    save(out,'preparation_audit',pd.DataFrame(qa))
    print(f'Preparation: cohort {len(base)}; AF window relations {len(af)}; all opportunity relations {len(opportunities):,}; reference studies {len(ref):,}',flush=True)

def main():
    p=argparse.ArgumentParser();p.add_argument('--output-dir',type=Path,default=OUT);a=p.parse_args();out=a.output_dir
    require(not out.exists(),'Choose a new version; preparation never overwrites')
    inputs=pins();out.mkdir();(out/'tables').mkdir();(out/'provenance').mkdir();(out/'scratch').mkdir()
    dump(out/'provenance/input_pins.json',inputs)
    build(out)
    dump(out/'provenance/prepare_complete.json',dict(status='PASS',input_pins_unchanged=inputs==pins()))

if __name__=='__main__':main()
