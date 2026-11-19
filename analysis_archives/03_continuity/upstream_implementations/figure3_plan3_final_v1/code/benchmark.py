"""Conditional publication-opportunity reference, not a causal model."""
import numpy as np
import pandas as pd
from support import *

def reference_counts(ref):
    require(ref.study_id.is_unique,'Reference papers must be unique across institutions')
    x=ref.copy();x['af_n']=x.label_state.eq('AF').astype(int)
    x['comparison_n']=x.label_state.eq('comparison').astype(int)
    x['unknown_n']=x.label_state.eq('unknown_label').astype(int);x['all_n']=1
    return x.groupby(['subfield','year'])[['all_n','af_n','comparison_n','unknown_n']].sum().reset_index()

def assign_rates(exposure,counts,minimum=100,probability='known',leaveout=None,year_only=False):
    x=exposure.merge(counts,on=['subfield','year'],how='left',validate='many_to_one')
    metrics=['all_n','af_n','comparison_n','unknown_n']
    x[metrics]=x[metrics].fillna(0)
    yearly=counts.groupby('year')[metrics].sum().add_prefix('year_').reset_index()
    x=x.merge(yearly,on='year',how='left',validate='many_to_one')
    if leaveout is not None:
        leave=leaveout.rename(columns={v:'remove_'+v for v in metrics})
        x=x.merge(leave,on=['institution_id','subfield','year'],how='left',validate='many_to_one')
        removed_year=leaveout.groupby(['institution_id','year'])[metrics].sum().add_prefix('remove_year_').reset_index()
        x=x.merge(removed_year,on=['institution_id','year'],how='left',validate='many_to_one')
        for v in metrics:
            x[v]-=x['remove_'+v].fillna(0)
            x['year_'+v]-=x['remove_year_'+v].fillna(0)
            require(x[v].ge(0).all() and x['year_'+v].ge(0).all(),'Leave-out subtraction exceeded reference')
    known=x.af_n+x.comparison_n
    fallback=known.lt(minimum) | year_only
    for v in metrics:x['effective_'+v]=x[v].where(~fallback,x['year_'+v])
    denom=x.effective_af_n+x.effective_comparison_n
    if probability=='known':num=x.effective_af_n
    elif probability=='lower':num=x.effective_af_n;denom=x.effective_all_n
    elif probability=='upper':num=x.effective_af_n+x.effective_unknown_n;denom=x.effective_all_n
    else:raise ValueError('Unknown benchmark probability definition')
    x['p']=np.where(denom.gt(0),num/denom,np.nan)
    x['rate_level']=np.where(fallback,'pooled_calendar_year','subfield_calendar_year')
    require(x.p.dropna().between(0,1).all(),'Invalid reference probability')
    return x

def expected_probabilities(rates,base):
    require(rates.n.gt(0).all(),'Exposure table must contain positive integer counts only')
    x=rates.copy()
    with np.errstate(divide='ignore',invalid='ignore'):
        x['log_none']=x.n*np.log1p(-x.p)
    x['missing_rate']=x.p.isna()
    # Do not skip NaN when interpreting an institution's opportunity record.
    g=x.groupby(['institution_id','interval']).agg(log_none=('log_none',lambda s:s.sum(skipna=False)),missing_rate=('missing_rate','any'),papers=('n','sum')).reset_index()
    g['q']= -np.expm1(g.log_none)
    g.loc[g.missing_rate,'q']=np.nan
    m=pd.MultiIndex.from_product([base.institution_id,[1,2]],names=['institution_id','interval'])
    g=g.set_index(['institution_id','interval']).reindex(m)
    empty=g.papers.isna();g.loc[empty,'papers']=0;g.loc[empty,'q']=0;g.loc[empty,'missing_rate']=False
    # Missing publication timing is not a true zero-opportunity window.
    q=g.q.unstack('interval');n=g.papers.unstack('interval')
    out=base[['institution_id','quintile','sustained','repeat','opportunity_timing_complete']].copy().set_index('institution_id')
    out['q1']=q[1];out['q2']=q[2];out['n1']=n[1];out['n2']=n[2]
    out['expected']=out.q1*out.q2
    out.loc[~out.opportunity_timing_complete,'expected']=np.nan
    out['difference_pp']=100*(out.sustained.astype(float)-out.expected)
    return out.reset_index()

def summarize(inst,variant):
    rows=[]
    for quintile,x in inst.groupby('quintile'):
        valid=x[x.expected.notna()]
        rows.append(dict(variant=variant,quintile=int(quintile),N=len(valid),cohort_N=len(x),
           observed=float(valid.sustained.mean()) if len(valid) else np.nan,
           expected=float(valid.expected.mean()) if len(valid) else np.nan,
           difference_pp=float(valid.difference_pp.mean()) if len(valid) else np.nan,
           incomplete_expected=len(x)-len(valid)))
    return pd.DataFrame(rows)

def run(out):
    base=load(out,'institution_analysis_base');op=load(out,'publication_opportunities');ref=load(out,'benchmark_reference_unique_studies')
    counts=reference_counts(ref)
    exposure=op.groupby(['institution_id','interval','subfield','year']).size().rename('n').reset_index()
    require(exposure.n.sum()==len(op),'Integer exposure counts changed')
    # Remove the institution's unique studies from all reference institutions,
    # not merely its own rows: shared papers are removed in their entirety.
    membership=op[['institution_id','study_id']].drop_duplicates().merge(ref[['study_id','subfield','year','label_state']],on='study_id',validate='many_to_one')
    membership['all_n']=1
    for state,name in [('AF','af_n'),('comparison','comparison_n'),('unknown_label','unknown_n')]:membership[name]=membership.label_state.eq(state).astype(int)
    loo=membership.groupby(['institution_id','subfield','year'])[['all_n','af_n','comparison_n','unknown_n']].sum().reset_index()
    settings=[('main',dict()),('leave_institution_and_shared_papers_out',dict(leaveout=loo)),
              ('sparse_min50',dict(minimum=50)),('sparse_min200',dict(minimum=200)),
              ('year_only',dict(year_only=True)),('unknown_lower',dict(probability='lower')),
              ('unknown_upper',dict(probability='upper'))]
    summaries=[];individual=[];rateaudit=[]
    for name,kwargs in settings:
        rate=assign_rates(exposure,counts,**kwargs);inst=expected_probabilities(rate,base)
        inst['variant']=name;individual.append(inst);summaries.append(summarize(inst,name))
        rateaudit.append(dict(variant=name,exposure_records=len(rate),paper_relations=int(rate.n.sum()),
          year_fallback_paper_relations=int(rate.loc[rate.rate_level.eq('pooled_calendar_year'),'n'].sum()),missing_rates=int(rate.p.isna().sum())))
        if name=='main':
            save(out,'institution_window_stratum_exposures',exposure,csv=False)
            # One main rate record for every exposure stratum, including year fallback.
            keys=rate[['subfield','year','p','rate_level','effective_all_n','effective_af_n','effective_comparison_n','effective_unknown_n']].drop_duplicates()
            save(out,'field_year_benchmark_rates',keys)
    globalcounts=load(out,'all_corpus_reference_counts')
    rate=assign_rates(exposure,globalcounts);inst=expected_probabilities(rate,base);inst['variant']='all_corpus_reference'
    summaries.append(summarize(inst,'all_corpus_reference'));individual.append(inst)
    twice_ref=ref.copy();twice_ref['year']=(twice_ref.year.astype(int)//2)*2
    twice_exp=exposure.copy();twice_exp['year']=(twice_exp.year.astype(int)//2)*2
    twice_exp=twice_exp.groupby(['institution_id','interval','subfield','year']).n.sum().reset_index()
    rate=assign_rates(twice_exp,reference_counts(twice_ref));inst=expected_probabilities(rate,base);inst['variant']='subfield_two_year_bins'
    summaries.append(summarize(inst,'subfield_two_year_bins'));individual.append(inst)
    summary=pd.concat(summaries,ignore_index=True)
    save(out,'benchmark_sensitivity',summary)
    save(out,'benchmark_institution_probabilities',pd.concat(individual,ignore_index=True))
    save(out,'panel_b_observed_expected',summary[summary.variant.eq('main')].copy())
    save(out,'benchmark_reference_counts',counts)
    save(out,'benchmark_rate_audit',pd.DataFrame(rateaudit))
    contrast=[]
    for name,x in summary.groupby('variant'):
        q=x.set_index('quintile')
        contrast.append(dict(variant=name,observed_gradient_pp=100*(q.loc[5,'observed']-q.loc[1,'observed']),
            expected_gradient_pp=100*(q.loc[5,'expected']-q.loc[1,'expected']),
            residual_gradient_pp=q.loc[5,'difference_pp']-q.loc[1,'difference_pp'],
            interpretation='descriptive_independent_publication_opportunity_reference_not_causal'))
    save(out,'benchmark_gradient_comparison',pd.DataFrame(contrast))
    # Supplemental raw scale gradients use the same frozen cohort, different cuts.
    raw=[]
    for var in ['baseline_papers','known_linked_author_ids','observed_partner_ids']:
        for q,x in base.groupby(var+'_quintile'):raw.append(dict(measure=var,quintile=q,N=len(x),events=int(x.sustained.sum()),rate=x.sustained.mean()))
    save(out,'supplement_raw_scale_gradients',pd.DataFrame(raw))
    print('Opportunity benchmark: 9 prespecified settings, five fixed scale groups; no simulated CI or causal test',flush=True)

if __name__=='__main__':run(OUT)
