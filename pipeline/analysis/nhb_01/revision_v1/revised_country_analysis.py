"""Derived-only Figure1 calculations; input semantic approval is a runner gate."""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from country_stats import signature_matrix, interval, concentration
from data import vector, annual_credits, build_metrics, coverage, heatmap_data
from local_recall import require


def fixed_ten(credits):
    totals=credits[credits.group.eq('AF') & credits.year.between(2020,2025)].groupby('country_code').credit.sum()
    return totals.rename('credit').reset_index().sort_values(['credit','country_code'],ascending=[False,True]).head(10).country_code.tolist()


def annual_diffusion(monthly,active):
    frame=monthly.assign(year=pd.to_datetime(monthly.month).dt.year)
    result=frame.groupby('year').agg(new_countries=('new_countries','sum'),
        cumulative_countries=('cumulative_countries','last'),
        pre2020_countries=('pre2020_countries','first')).reset_index()
    result=result.merge(active.rename(columns={'publication_year':'year'}),on='year',how='left')
    result['active_countries']=result.active_countries.fillna(0).astype(int)
    return result


def stacked_composition(credits,leaders):
    require(len(leaders)==len(set(leaders))<=10,'Invalid fixed country set')
    rows=[]
    for year,p in credits[credits.group.eq('AF') & credits.year.between(2020,2025)].groupby('year'):
        n=int(p.n.iloc[0]);unknown=int(p.unknown_n.iloc[0]);known=int(p.assigned_n.iloc[0])
        values={code:float(p.loc[p.country_code.eq(code),'credit'].sum()) for code in leaders}
        values['Other']=float(p.credit.sum()-sum(values.values()));values['Unknown']=float(unknown)
        require(np.isclose(sum(values.values()),n),'Stack weights do not sum to all AF studies')
        for code,value in values.items():rows.append({'year':int(year),'country_code':code,'credit':value,
            'all_AF_studies':n,'known_AF_studies':known,'fraction':value/n if n else np.nan})
    return pd.DataFrame(rows)


def trends(main,draws):
    """Endpoint differences, not a fitted monotonic or causal trend test."""
    p=draws.pivot(index='replicate',columns=['year','group'],values='gini')
    table=main.set_index('year');rows=[]
    for start in (2020,2021,2022):
        for end in (2024,2025):
            for metric in ('AF_Gini','AF_minus_C_Gini'):
                a=p[(start,'AF')];b=p[(end,'AF')]
                point=table.loc[end,'af_gini']-table.loc[start,'af_gini']
                if metric=='AF_minus_C_Gini':
                    a=a-p[(start,'C')];b=b-p[(end,'C')]
                    point=table.loc[end,'delta_gini']-table.loc[start,'delta_gini']
                rows.append({'start':start,'end':end,'estimand':metric+'_endpoint_change',
                    'point':float(point),**interval(b-a),
                    'dependence_limitation':'independent annual study draws; longitudinal research-team dependence not modeled',
                    'inference':'conditional_descriptive_uncertainty_not_release_effect'})
    return pd.DataFrame(rows)


def paired_domestic_heatmaps(patterns,registry):
    """Same annual/type/subfield support on both sides; AF mix reweights ALL.

    A matched hypothetical ALL denominator retains the observed common ALL
    total, but distributes strata to the observed AF mix. This is an explicitly
    descriptive composition sensitivity, NOT the original domestic rate.
    """
    result=[];support=[]
    keys=['work_type','subfield']
    for year in range(2020,2026):
        part=patterns[patterns.year.eq(year) & patterns.signature.ne('')].copy()
        af=part[part.group.eq('AF')]
        all_counts=part.groupby(keys)['n'].sum()
        af_counts=af.groupby(keys)['n'].sum()
        common=sorted(set(all_counts.index)&set(af_counts.index))
        all_mask=pd.MultiIndex.from_frame(part[keys]).isin(common)
        af_mask=pd.MultiIndex.from_frame(af[keys]).isin(common)
        q_all=part[all_mask];q_af=af[af_mask]
        N=int(q_all.n.sum());A=int(q_af.n.sum())
        raw_all=vector(q_all,registry);raw_af=vector(q_af,registry)
        matched=np.zeros(len(registry))
        if A:
            for typ,field in common:
                s=part[part.work_type.eq(typ) & part.subfield.eq(field)]
                mix=float(af_counts.loc[(typ,field)])/A
                matched+=N*mix*vector(s,registry)/float(s.n.sum())
        require(np.isclose(raw_all.sum(),N),'Raw common ALL credit loss')
        require(np.isclose(raw_af.sum(),A),'Raw common AF credit loss')
        require(np.isclose(matched.sum(),N) if A else not matched.any(),'Matched common ALL credit loss')
        for i,code in enumerate(registry):
            raw=raw_af[i]/raw_all[i] if raw_all[i]>0 else np.nan
            adj=raw_af[i]/matched[i] if matched[i]>0 else np.nan
            result.append({'year':year,'country_code':code,'AF_credit_common':raw_af[i],
                'ALL_credit_common':raw_all[i],'matched_ALL_credit_common':matched[i],
                'raw_common_AF_fraction':raw,'matched_AF_mix_fraction':adj,
                'common_strata':len(common),'same_study_support_both_panels':True})
        support.append({'year':year,'common_strata':len(common),
            'AF_known_before':int(af.n.sum()),'AF_known_common':A,
            'ALL_known_before':int(part.n.sum()),'ALL_known_common':N,
            'ALL_retained_fraction':N/int(part.n.sum()) if len(part) else np.nan,
            'target':'observed assigned AF type/subfield mix within year',
            'not_a_causal_adjustment':True})
    return pd.DataFrame(result),pd.DataFrame(support)


def prepare_annual(c,registry):
    # The monthly preparation already created a coherent representative basis.
    patterns=c.execute('''SELECT b.publication_year AS year,b.work_type,
        coalesce(b.primary_subfield_id,'__unknown_subfield__') AS subfield,
        CASE WHEN b.confirmed_af THEN 'AF' WHEN b.screen_negative THEN 'C'
        WHEN b.candidate_reviewed AND l.af_use_label='no' THEN 'R'
        ELSE 'U' END AS "group",b.signature,count(*)::BIGINT AS n
        FROM basis b JOIN label_metadata l USING(study_id) GROUP BY ALL ORDER BY ALL''').df()
    require(int(patterns.n.sum())==c.execute('SELECT count(*) FROM basis').fetchone()[0],'Pattern coverage differs')
    signature_matrix(list(patterns.signature.unique()),registry)
    credits=annual_credits(patterns,registry)
    leaders=fixed_ten(credits)
    concentration_table,sensitivity,draws=build_metrics(patterns,registry,credits,1000,20261009)
    heat,support=paired_domestic_heatmaps(patterns,registry)
    return {'annual_patterns_private':patterns,'annual_country_credits':credits,
        'annual_source_coverage':coverage(patterns),'fixed_ten_composition':stacked_composition(credits,leaders),
        'concentration':concentration_table,'concentration_sensitivity':sensitivity,
        'bootstrap_draws':draws,'concentration_endpoint_sensitivity':trends(concentration_table,draws),
        'raw_domestic_heatmap':heatmap_data(credits),
        'paired_domestic_heatmaps':heat,'paired_domestic_heatmap_support':support},leaders
