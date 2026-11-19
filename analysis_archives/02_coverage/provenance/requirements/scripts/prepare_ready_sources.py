"""Extract frozen estimates for the proposed layout; no new analysis or simulation.

Python 3.9+ standard library. Always writes into a new output directory.
"""
from pathlib import Path
import argparse,csv,json

def load(p):
    with p.open(encoding='utf-8',newline='') as f:return list(csv.DictReader(f))
def save(folder,name,data):
    data=list(data)
    if not data:raise ValueError('Empty source: '+name)
    with (folder/name).open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(data[0]));w.writeheader();w.writerows(data)
def truth(x):return str(x).lower()=='true'

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);ap.add_argument('--out',type=Path,required=True)
    args=ap.parse_args();root=args.root.resolve();out=args.out.resolve()
    if out.exists():raise ValueError('Use a new empty/nonexistent output directory; existing outputs are not overwritten')
    out.mkdir(parents=True);t=root/'reference/frozen_v5/tables'
    a=[dict(r,coverage_pct=100*float(r['C']),population_id='B2',weighting='equal_country',coverage_units='fraction; coverage_pct=percent')
       for r in load(t/'Fig2a_cumulative.csv') if r['context']=='All' and 2020<=int(r['year'])<=2025]
    save(out,'Fig2a_cumulative.csv',a)
    sy=[r for r in load(t/'Table_SY_a_annual.csv') if r['context']=='All' and 2021<=int(r['year'])<=2025]
    save(out,'Fig2b_ratio.csv',[dict(r,units='ratio',population_id='B2') for r in sy])
    save(out,'Fig2c_gap.csv',[dict(r,units='percentage_points',population_id='B2') for r in sy])
    draws={}
    for r in load(t/'benchmark_annual_gap_replicates.csv'):
        if r['context']=='All' and r['year'] in ['2021','2025']:
            draws.setdefault(int(r['replicate']),{})[int(r['year'])]=float(r['G_pp'])
    if len(draws)!=5000 or any(set(x)!={2021,2025} for x in draws.values()):raise ValueError('Incomplete endpoint draws')
    save(out,'Fig2d_benchmark_draws.csv',[dict(replicate=k,delta_G_pp=v[2025]-v[2021],units='percentage_points',benchmark='main',evidence_status='frozen_5000_replicates_not_rerun') for k,v in sorted(draws.items())])
    save(out,'Fig2d_benchmark_summary.csv',[dict(r,formal_mean='exact_analytic_expectation',evidence_status='frozen_primary') for r in load(t/'Table_SY_b_benchmark.csv') if r['context']=='All' and r['variant']=='main' and r['setting']=='main'])
    save(out,'Fig2e_growth_components.csv',[dict(r,units='percentage_points',population_id='B2') for r in load(t/'S10_components.csv') if r['context']=='All' and r['group'] in ['H','L']])
    sx=load(t/'Table_SX_a_sample.csv');exc={}
    for r in sx:
        if r['country']=='OVERALL':continue
        exc[r['exclusion_reason']]=exc.get(r['exclusion_reason'],0)+int(r['baseline_institutions'])
    n0=sum(exc.values());n1=n0-exc['fixed_country_unknown_or_multiple'];n2=n1-exc['collapsed_or_empty_tertiles'];n3=n2-exc['group_below_N20']
    save(out,'ED3a_sample_flow.csv',[
        dict(node='B0',institutions=n0,label='Baseline institutions',excluded_to_next=exc['fixed_country_unknown_or_multiple'],exclusion_reason='unknown_or_multiple_baseline_countries'),
        dict(node='B1',institutions=n1,label='Unique known baseline country',excluded_to_next=exc['collapsed_or_empty_tertiles'],exclusion_reason='collapsed_or_empty_domestic_tertiles'),
        dict(node='VALID_TERTILES',institutions=n2,label='Valid domestic tertiles',excluded_to_next=exc['group_below_N20'],exclusion_reason='domestic_group_below_20'),
        dict(node='B2',institutions=n3,label='Main sample; 68 countries',excluded_to_next='',exclusion_reason='')])
    save(out,'ED3b_first_entries.csv',[dict(r,population_id='B0_date_resolved_entry',count_is_rate=False) for r in load(t/'ED3_annual.csv')])
    save(out,'ED3b_eras.csv',load(t/'legacy_resolved_entry_phase_counts.csv'))
    save(out,'ED4_country_endpoints.csv',load(t/'ED4_endpoints.csv'))
    save(out,'S8_alternative_trajectories.csv',[dict(r,coverage_pct=100*float(r['C']),weighting='equal_country') for r in load(t/'S8_trajectories.csv') if 2020<=int(r['year'])<=2025])
    save(out,'S9_annual_benchmark_gaps.csv',[dict(r,interval_type='pointwise_conditional_reference_range_not_effect_CI') for r in load(t/'S9_annual_gaps.csv') if 2021<=int(r['year'])<=2025])
    bs=load(t/'benchmark_summary.csv')
    save(out,'S10a_historical_thresholds.csv',[dict(r,evidence_status='historical_frozen_not_new_simulation') for r in bs if r['variant']=='main' and r['context']=='All' and r['setting'] in ['main','N10','N30']])
    save(out,'S10c_historical_benchmark_specs.csv',[dict(r,evidence_status='historical_frozen_not_new_simulation') for r in bs if r['setting']=='main' and r['context']=='All' and r['variant'] in ['main','document_type','team_size']])
    status=dict(schema='ready-source-extract-v1',source='reference/frozen_v5',new_simulations=0,new_weighting_analysis=False,new_continuous_model=False,pending=['S10b','S10d','N20_membership_exchangeability_diagnostics','new_figure_rendering_and_visual_review'])
    (out/'EXTRACTION_STATUS.json').write_text(json.dumps(status,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(output=str(out),csv_files=len(list(out.glob('*.csv'))),new_analyses=0),ensure_ascii=False))

if __name__=='__main__':main()
