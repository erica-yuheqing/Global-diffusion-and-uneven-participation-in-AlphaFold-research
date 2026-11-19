"""Audit the user-supplied handoff and make its matched summaries authoritative."""
import ast,shutil
from common import *
from prepare import pin

HAND=Path('/historical-workspace/Downloads/Finding1_revision_handoff_v2')
def run(out):
    require(not (out/'provenance/handoff_audit.json').exists(),'Handoff already imported')
    manifest=json.loads((HAND/'manifest.json').read_text());expected={x['file']:x['sha256'] for x in manifest['copied']}
    expected.update({k:v['sha256'] for k,v in manifest['derived'].items()});require(len(expected)==23,'Handoff inventory differs')
    target=out/'handoff_source';target.mkdir();(target/'source_data').mkdir();pins=[pin(HAND/'manifest.json')];checks=[]
    def check(name,condition):require(bool(condition),name);checks.append(dict(check=name,status='PASS'))
    for name,digest in expected.items():
        p=HAND/'source_data'/name;check('Handoff SHA256 '+name,sha(p)==digest and not p.is_symlink());pins.append(pin(p));shutil.copy2(p,target/'source_data'/name)
    for name in ['manifest.json','README.md','Finding1_修改说明_合作伙伴版.md','prepare_handoff.py']:
        p=HAND/name;pins.append(pin(p));shutil.copy2(p,target/name)
    def read(name):return pd.read_csv(HAND/'source_data'/f'{name}.csv',keep_default_na=False)
    for name in ['concentration','annual_country_credits','annual_source_coverage','normalization_country_selection','fixed_ten_composition','monthly_diffusion','annual_diffusion_counts']:
        a=read(name);b=load(out,name);check('Same local and handoff row count '+name,len(a)==len(b))
        for column in a.select_dtypes(include='number').columns:
            if column in b:check('Frozen numeric values '+name+'.'+column,np.allclose(pd.to_numeric(a[column],errors='coerce'),pd.to_numeric(b[column],errors='coerce'),equal_nan=True,atol=1e-9,rtol=1e-9))
    hand=read('country_normalization');local=load(out,'country_year_AF_normalization');join=hand.merge(local,on=['year','country_code'],suffixes=('_hand','_local'),validate='one_to_one')
    check('All handoff country-year R rows map to local',len(join)==len(hand)==227*5)
    for old,new in [('AF_credit','af_credit'),('ALL_credit','local_all_credit'),('R_hand','R_local')]:
        check('Handoff R numerator denominator identity '+old,np.allclose(pd.to_numeric(join[old],errors='coerce'),pd.to_numeric(join[new],errors='coerce'),equal_nan=True,atol=1e-9))
    hand=read('figure1d_top10_endpoints');local=load(out,'figure1d_top10_endpoints');join=hand.merge(local,on=['year','country_code'],suffixes=('_hand','_local'),validate='one_to_one')
    check('Top ten endpoints agree',len(join)==20 and np.allclose(join.R_hand,join.R_local))
    hand=read('ed2a_attributed_composition');local=load(out,'ed2a_attributed_composition');join=hand.merge(local,on=['year','country_code'])
    check('Attributed ED2 shares agree',len(join)==55 and np.allclose(join.share_of_attributed_AF,join.attributed_fraction))
    hand=read('subfield_year_handoff');local=load(out,'Table_S3_subfield_year');hand['subfield_key']='https://openalex.org/subfields/'+hand.subfield_id.astype(str)
    join=hand.merge(local,left_on=['year','subfield_key'],right_on=['year','subfield'],suffixes=('_h','_l'),validate='one_to_one')
    check('132 field-year exact AF/eligible counts agree',len(join)==132 and np.array_equal(join.AF_studies,join.AF) and np.array_equal(join.eligible_studies,join.eligible))
    # Preserve the independent local simulation; never call it the original handoff draws.
    for name in ['matching_summary','matching_endpoint_changes','matching_stratum_support','matching_draws']:
        for ext in ['csv','parquet']:
            p=out/'tables'/f'{name}.{ext}';p.rename(p.with_name('local_audit_'+p.name))
    local=load(out,'local_audit_matching_summary');source=read('matching_summary')
    check('Handoff has all 15 required matching points',len(source)==15 and source.replicates.eq(2000).all() and set(source.variant)==set(SPECS))
    check('Handoff mean-gap algebra',np.allclose(source.excess_gini,source.observed_AF_gini-source.benchmark_mean))
    check('Handoff matched range from fixed-AF marginal quantiles',np.allclose(source.excess_lower,source.observed_AF_gini-source.benchmark_upper) and np.allclose(source.excess_upper,source.observed_AF_gini-source.benchmark_lower))
    mapped=source.rename(columns={'variant':'spec','target_AF':'n_AF','observed_AF_gini':'AF_gini','benchmark_mean':'matched_non_AF_mean','excess_gini':'point','excess_lower':'lower','excess_upper':'upper'})
    mapped['interval_type']='central95_conditional_matched_range_AF_fixed';mapped['source']='user_supplied_handoff_v2';mapped['original_seed_available']=False
    save(out,'matching_summary',mapped)
    source=read('matching_endpoint_changes');mapped=source.rename(columns={'variant':'spec','mean_excess_change':'point','benchmark_lower':'lower','benchmark_upper':'upper'})
    check('Six handoff endpoint rows',len(mapped)==6 and mapped.replicates.eq(2000).all())
    points=load(out,'matching_summary').set_index(['spec','year']).point
    for r in mapped.itertuples():check('Handoff endpoint mean algebra '+r.spec+str(r.start),np.isclose(r.point,points.loc[(r.spec,r.end)]-points.loc[(r.spec,r.start)]))
    mapped['interval_type']='conditional_matched_endpoint_range_from_handoff';mapped['source']='user_supplied_handoff_v2';save(out,'matching_endpoint_changes',mapped)
    source=read('matching_stratum_support').rename(columns={'variant':'spec','target_AF':'AF_target','available_C':'non_AF_available'})
    source['stratum']=source.stratum.map(lambda s:'|'.join(map(str,ast.literal_eval(s))) if s.startswith('(') else s)
    source['supported']=source.supported.astype(str).str.lower().eq('true');check('All original handoff matching strata supported',source.supported.all())
    local_support=load(out,'local_audit_matching_stratum_support').query('year>=2021')
    j=source.merge(local_support,on=['year','spec','stratum'],suffixes=('_hand','_local'),validate='one_to_one')
    check('Handoff matching pools/targets exact local reconstruction',len(j)==len(source)==len(local_support) and np.array_equal(j.AF_target_hand,j.AF_target_local) and np.array_equal(j.non_AF_available_hand,j.non_AF_available_local))
    save(out,'matching_stratum_support',source)
    local=local[local.year.ge(2021)].merge(load(out,'matching_summary')[['year','spec','point','lower','upper','benchmark_mean_MCSE']],on=['year','spec'],suffixes=('_local','_handoff'))
    local['point_difference']=local.point_local-local.point_handoff;save(out,'handoff_local_matching_comparison',local)
    # Authority updated by a direct human response, not inferred from workbook names.
    acceptance=dict(date='2026-10-25',source='direct user response in this chat',human_reference_blinding='author confirms human judgement preceded viewing model answers',
      exact_user_statement='人工判读前未查看模型答案',handoff_path=str(HAND),original_matching_draws_supplied=False,heldout_validation_confirmed=False)
    dump(out/'provenance/author_confirmation.json',acceptance)
    dump(out/'provenance/handoff_input_pins.json',pins);dump(out/'provenance/handoff_audit.json',dict(status='PASS',checks=checks,check_count=len(checks),
      matching_source='user_supplied_handoff_v2',raw_country_field_counts_independently_agree=True,original_draws_not_in_lightweight_handoff=True,local_simulation_separate=True))
    # Earlier comparison remains an historical, explicitly superseded audit, not current unresolved status.
    (out/'provenance/provisional_matching_note.txt').write_text('Before handoff delivery, a local reconstruction used seed20261025 and produced slightly different composition-matched Monte Carlo means. User then supplied handoff_v2. Authoritative plotted matching summaries/ranges now use that supplied handoff; original lightweight handoff does not include full draws/seed. Local draws retained separately, never used to certify original handoff quantiles.\n')
    print(f'Handoff v2 imported and independently aligned: {len(checks)} checks; authoritative composition gap 0.0168→0.0194; human pre-answer blinding confirmed by user.',flush=True)

if __name__=='__main__':run(OUT)
