"""Validate handoff integrity and key frozen estimates; no third-party packages.

PASS_FOR_HANDOFF does not mean new scientific figures have been generated.
"""
from pathlib import Path
import argparse,csv,hashlib,json,math,re,statistics

def read(p):
    with p.open(encoding='utf-8',newline='') as f:return list(csv.DictReader(f))
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()
def close(a,b,tol=1e-9):return math.isclose(float(a),float(b),abs_tol=tol,rel_tol=tol)
def quantile(xs,q):
    xs=sorted(xs);i=(len(xs)-1)*q;k=int(i);return xs[k]+(i-k)*(xs[min(k+1,len(xs)-1)]-xs[k])

def check(root,skip_manifest=False):
    checks={};details={};t=root/'reference/frozen_v5/tables';ready=root/'data/ready_sources'
    def ck(name,value,detail=None):
        checks[name]=bool(value)
        if detail is not None:details[name]=detail
    b=read(t/'institution_baseline_and_first_participation.csv')
    main=[r for r in b if r['eligible_20'].lower()=='true']
    ck('baseline_unique_52098',len(b)==52098 and len({r['institution_id'] for r in b})==52098)
    ck('primary_48010_68',len(main)==48010 and len({r['country'] for r in main})==68)
    ck('fixed_group_counts',dict((g,sum(r['group']==g for r in main)) for g in ['L','M','H'])==dict(L=17602,M=14720,H=15688))
    sx=read(t/'Table_SX_b_coverage.csv')
    ck('main_204_cells',len(sx)==204 and sum(int(r['baseline_group_n']) for r in sx)==48010)
    ck('pool_year_vs_date_counts',sum(int(r['ever_AF_by_2025_pool_year_n']) for r in sx)==7654 and sum(int(r['legacy_date_entry_2020_2025_n']) for r in sx)==6040)
    counts=read(ready/'ED3a_sample_flow.csv')
    ck('sample_flow_reconciles',[int(r['institutions']) for r in counts]==[52098,50371,50271,48010] and sum(int(r['excluded_to_next'] or 0) for r in counts)+48010==52098)
    date=read(t/'ED3_institutions.csv')
    ck('entry_cohort_unique_6369',len(date)==6369 and len({r['institution_id'] for r in date})==6369)
    entries=read(ready/'ED3b_first_entries.csv');eras=read(ready/'ED3b_eras.csv')
    ck('annual_entry_counts',[int(r['new_institutions']) for r in entries]==[16,562,1636,1551,1231,1373])
    ck('era_counts_41_4249_2079',[int(r['institutions']) for r in eras]==[41,4249,2079] and sum(int(r['institutions']) for r in eras)==6369)
    c=read(ready/'Fig2a_cumulative.csv')
    ck('fig2a_18_rows',len(c)==18)
    expected={'H':37.9130129649685,'M':8.300819240696515,'L':2.3471460849322112}
    ck('cumulative_2025_anchor',all(close(next(r for r in c if r['year']=='2025' and r['group']==g)['coverage_pct'],v) for g,v in expected.items()))
    ck('cumulative_nondecreasing',all(all(float(q[i]['C'])<=float(q[i+1]['C'])+1e-12 for i in range(len(q)-1)) for q in [sorted([r for r in c if r['group']==g],key=lambda r:int(r['year'])) for g in ['L','M','H']]))
    sy=read(ready/'Fig2b_ratio.csv');by={int(r['year']):r for r in sy}
    ck('annual_complete_2021_2025',set(by)==set(range(2021,2026)))
    ck('ratio_formula',all(close(r['R'],float(r['annual_L_coverage_pct'])/float(r['annual_H_coverage_pct'])) for r in sy))
    ck('gap_formula',all(close(r['G_pp'],float(r['annual_H_coverage_pct'])-float(r['annual_L_coverage_pct'])) for r in sy))
    ck('ratio_and_gap_endpoints',close(by[2021]['R'],0.009635763539298585) and close(by[2025]['R'],0.04450460985571247) and close(by[2021]['G_pp'],3.3607112732139) and close(by[2025]['G_pp'],23.50341402670982))
    summary=read(ready/'Fig2d_benchmark_summary.csv')[0]
    ck('formal_analytic_and_observed',close(summary['expected_delta_G'],23.146794624720332) and close(summary['actual_delta_G'],20.142702753495918))
    ck('benchmark_delta_D',close(float(by[2025]['G_pp'])-float(by[2021]['G_pp']),summary['actual_delta_G']) and close(float(summary['actual_delta_G'])-float(summary['expected_delta_G']),summary['excess']))
    d=read(ready/'Fig2d_benchmark_draws.csv');dv=[float(r['delta_G_pp']) for r in d]
    ck('all_5000_replicates',len(d)==5000 and len({r['replicate'] for r in d})==5000)
    ck('replicate_distribution_matches',close(statistics.mean(dv),summary['simulated_mean_delta_G']) and close(quantile(dv,.025),summary['reference_low']) and close(quantile(dv,.975),summary['reference_high']))
    comp={r['group']:r for r in read(ready/'Fig2e_growth_components.csv')}
    ck('both_growth_deviations_negative',all(float(r['r_pp'])<0 and close(float(r['observed_growth_pp'])-float(r['analytic_expected_growth_pp']),r['r_pp']) for r in comp.values()))
    ck('signed_decomposition',close(float(comp['H']['r_pp'])-float(comp['L']['r_pp']),summary['excess']))
    ed=read(ready/'ED4_country_endpoints.csv');pair={}
    for r in ed:pair.setdefault(r['country'],{})[int(r['year'])]=r
    defined=sum(bool(r[2021]['R']) for r in pair.values());up=sum(bool(r[2021]['R']) and float(r[2025]['R'])>float(r[2021]['R']) for r in pair.values())
    gaps=sum(float(r[2025]['G_pp'])>float(r[2021]['G_pp']) for r in pair.values())
    ck('country_ratios_NA_and_increases',len(pair)==68 and defined==44 and up==26 and all(r[2025]['R']!='' for r in pair.values()))
    ck('country_gap_increases_67_of_68',gaps==67)
    s8=read(ready/'S8_alternative_trajectories.csv');s8n={}
    for metric,sample,n,ct in [('authors','metric_valid',47910,67),('partners','metric_valid',48010,68),('authors','common_valid',47910,67),('partners','common_valid',47910,67)]:
        z=[r for r in s8 if r['metric']==metric and r['sample']==sample and r['year']=='2025']
        s8n[metric+'_'+sample]=len(z)==3 and sum(int(r['fixed_institutions']) for r in z)==n and all(int(r['countries'])==ct for r in z)
    ck('alternative_and_common_sample_sizes',all(s8n.values()),s8n)
    ck('s9_four_contexts_five_years',len(read(ready/'S9_annual_benchmark_gaps.csv'))==20)
    mapping=read(root/'05_tables/panel_source_map.csv')
    ck('six_figures_21_panels',len(mapping)==21 and len({r['figure'] for r in mapping})==6)
    ck('pending_panels_explicit',[(r['figure'],r['panel']) for r in mapping if r['status']=='PENDING_NEW_ANALYSIS']==[('S10','b'),('S10','d')])
    prov=json.loads((root/'SOURCE_PROVENANCE.json').read_text())
    pinned=[r for r in prov if r.get('expected_input_sha256')]
    ck('raw_input_pins_match',len(pinned)>=4 and all(sha(root/r['package_path'])==r['expected_input_sha256'] for r in pinned),{'pinned_files':len(pinned)})
    hist=root/'data/raw/historical_audits/benchmark_summary.csv'
    if hist.exists():
        old={(r['variant'],r['setting'],r['context']):r for r in read(hist)}
        reused=read(ready/'S10a_historical_thresholds.csv')+read(ready/'S10c_historical_benchmark_specs.csv')
        ck('historical_summary_reconciles',all((r['variant'],r['setting'],r['context']) in old and all(close(r[k],old[(r['variant'],r['setting'],r['context'])][k]) for k in ['actual_delta_G','expected_delta_G','excess']) for r in reused))
    else:ck('historical_summary_reconciles',False)
    broken=[]
    for p in root.rglob('*.md'):
        if 'reference' in p.relative_to(root).parts:continue
        for target in re.findall(r'\]\(([^)]+)\)',p.read_text(encoding='utf-8')):
            if target.startswith(('http:','https:','#','mailto:')):continue
            target=target.strip('<>').split('#',1)[0]
            if not (p.parent/target).exists():broken.append(dict(file=str(p.relative_to(root)),target=target))
    ck('new_document_relative_links',not broken,broken)
    if not skip_manifest:
        m=json.loads((root/'MANIFEST.json').read_text());bad=[]
        for r in m['files']:
            p=root/r['path']
            if not p.is_file() or p.stat().st_size!=r['bytes'] or sha(p)!=r['sha256']:bad.append(r['path'])
        actual={str(p.relative_to(root)) for p in root.rglob('*') if p.is_file() and p.name!='MANIFEST.json' and '__pycache__' not in p.parts}
        listed={r['path'] for r in m['files']}
        ck('manifest_hashes_and_file_set',not bad and actual==listed,{'mismatched':bad,'unlisted':sorted(actual-listed),'missing':sorted(listed-actual)})
    return dict(status='PASS_FOR_HANDOFF' if all(checks.values()) else 'FAIL',scope='handoff_files_and_frozen_numbers_only',new_figures_rendered=False,new_weighting_or_continuous_results=False,checks=checks,details=details,passed=sum(checks.values()),total=len(checks))

def main():
    a=argparse.ArgumentParser();a.add_argument('--root',type=Path,required=True);a.add_argument('--skip-manifest',action='store_true');a.add_argument('--report',type=Path)
    x=a.parse_args();result=check(x.root.resolve(),x.skip_manifest);s=json.dumps(result,ensure_ascii=False,indent=2)
    if x.report:x.report.write_text(s+'\n',encoding='utf-8')
    print(s)
    raise SystemExit(0 if result['status']=='PASS_FOR_HANDOFF' else 1)
if __name__=='__main__':main()
