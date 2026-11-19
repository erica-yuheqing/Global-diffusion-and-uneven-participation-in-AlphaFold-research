"""Prepare all real panel data; no values imported from prose examples."""
import shutil
from common import *

COPY=['concentration','concentration_endpoint_sensitivity','annual_country_credits','annual_counts','annual_source_coverage','bootstrap_draws',
 'fixed_ten_composition','country_year_AF_normalization','normalization_country_selection','figure1_normalization_heatmap_source',
 'monthly_diffusion','annual_diffusion_counts','first_observed_stage_map_source']

def pin(p):return dict(path=str(p),sha256=sha(p),bytes=p.stat().st_size)
def evaluate_pilot(x,prefix):
    # joint yes is the study-cohort positive rule, not a majority vote.
    eligible=x.metric_eligible.astype(str).str.lower().eq('true')
    if prefix=='c':eligible &= x.c_available.astype(str).str.lower().eq('true')
    x=x[eligible].copy();truth=np.where(x.human_af_use_label.eq('yes')&x.human_adoption_eligible.eq('yes'),'yes','no')
    a=x[prefix+'_af_use_label'].fillna('missing');b=x[prefix+'_adoption_eligible'].fillna('missing')
    pred=np.where(a.eq('yes')&b.eq('yes'),'yes',np.where(a.eq('no')|b.eq('no'),'no','uncertain/missing'))
    rows=[dict(system=prefix,reference=t,prediction=p,n=int(np.sum((truth==t)&(pred==p)))) for t in ['yes','no'] for p in ['yes','no','uncertain/missing']]
    tp=np.sum((truth=='yes')&(pred=='yes'));fp=np.sum((truth=='no')&(pred=='yes'));pos=np.sum(truth=='yes')
    return rows,dict(system=prefix,evaluated_n=len(x),reference_positive=int(pos),TP=int(tp),FP=int(fp),
      positive_not_detected=int(pos-tp),TN=int(np.sum((truth=='no')&(pred=='no'))),undecided_or_missing=int(np.sum(pred=='uncertain/missing')),
      precision=tp/(tp+fp) if tp+fp else np.nan,recall=tp/pos if pos else np.nan,independent_gold_confirmed=False)

def run(out):
    require(not out.exists(),'Choose a new output version');out.mkdir()
    for n in ['tables','source_data','provenance','figures','manuscript','assets']: (out/n).mkdir()
    old=json.loads((PREV/'run_manifest.json').read_text());pins=[pin(PREV/'run_manifest.json'),pin(PLAN),pin(MOD/'README.md')]
    for name in COPY:
        p=PREV/'tables'/f'{name}.parquet';require(sha(p)==old['outputs'][f'tables/{name}.parquet']['sha256'],'Frozen table mismatch '+name)
        shutil.copy2(p,out/'tables'/p.name);pins.append(pin(p))
    for p in (PREV/'assets').iterdir():
        require(sha(p)==old['outputs'][str(p.relative_to(PREV))]['sha256'],'Frozen map asset differs');shutil.copy2(p,out/'assets'/p.name);pins.append(pin(p))
    p=RAW/'annual_patterns_private.parquet';manifest=json.loads((RAW/'run_manifest.json').read_text())
    require(sha(p)==manifest['outputs'][p.name]['sha256'],'Country-set patterns differ');pins.extend([pin(p),pin(RAW/'run_manifest.json')])
    # Patterns are integer study-frequency cells, not country counts.
    patterns=pd.read_parquet(p);require(patterns.n.ge(1).all() and (patterns.n%1).eq(0).all(),'Invalid study pattern frequencies')
    main=patterns[patterns.year.between(2020,2025)];require(main.n.sum()==2714594,'Eligible-study total differs')
    require(main.subfield.nunique()==22,'Eligible subfield scope differs')
    # Copy exact aggregated frequencies so matching can be replayed without private full text.
    save(out,'study_country_patterns',patterns)
    dictionary=ROOT/'analysis/nhb_revision_v1/baseline_features_v1/baseline_subfield_dictionary.parquet';pins.append(pin(dictionary))
    names=pd.read_parquet(dictionary).set_index('primary_subfield_id').example_subfield_name.to_dict()
    af=main[main.group.eq('AF')].groupby('subfield').n.sum();eligible=main.groupby('subfield').n.sum()
    top=af.sort_values(ascending=False,kind='stable').head(5).index.tolist()
    require(len(top)==5,'Need fixed five subfields');table=[]
    for field in sorted(main.subfield.unique()):
        require(field in names,'Missing real subfield name')
        for year in range(2020,2026):
            part=main[main.year.eq(year)&main.subfield.eq(field)];A=int(part[part.group.eq('AF')].n.sum());T=int(part.n.sum())
            table.append(dict(year=year,subfield=field,subfield_name=names[field],AF=A,eligible=T,
              AF_share=A/main[main.year.eq(year)&main.group.eq('AF')].n.sum(),eligible_share=T/main[main.year.eq(year)].n.sum(),AF_rate=A/T,
              top5=field in top,display_group=names[field] if field in top else 'Other'))
    full=pd.DataFrame(table);save(out,'Table_S3_subfield_year',full)
    grouped=full.groupby(['year','display_group'],sort=False)[['AF','eligible']].sum().reset_index()
    grouped['AF_share']=grouped.AF/grouped.groupby('year').AF.transform('sum');grouped['eligible_share']=grouped.eligible/grouped.groupby('year').eligible.transform('sum');grouped['AF_rate']=grouped.AF/grouped.eligible
    save(out,'subfield_year_top5_other',grouped)
    period=grouped.groupby('display_group',sort=False)[['AF','eligible']].sum().reset_index();period['AF_share']=period.AF/period.AF.sum();period['eligible_share']=period.eligible/period.eligible.sum()
    save(out,'subfield_period_top5_other',period)
    dump(out/'provenance/subfield_order.json',[names[k] for k in top]+['Other'])
    # Top ten chosen on baseline eligible credit, never R outcomes.
    norm=load(out,'country_year_AF_normalization');selection=load(out,'normalization_country_selection');require(selection.head(10).country_code.tolist()==ORDER[:10],'Baseline ten changed')
    endpoints=norm[norm.country_code.isin(ORDER[:10])&norm.year.isin([2021,2025])].merge(selection[['country_code','baseline_rank','baseline_credit']],on='country_code',validate='many_to_one').sort_values(['baseline_rank','year'])
    require(endpoints.R.gt(0).all() and len(endpoints)==20,'Endpoint log2 axis needs positive R')
    save(out,'figure1d_top10_endpoints',endpoints)
    # ED2a re-denominator: known attributed output, unlike previous all-study fraction.
    comp=load(out,'fixed_ten_composition');fixed=comp[~comp.country_code.isin(['Other','Unknown'])].country_code.drop_duplicates().tolist()
    require(fixed==['US','CN','DE','GB','FR','JP','CA','IT','ES','IN'],'Fixed AF-output ten changed')
    comp=comp[comp.year.between(2021,2025)&comp.country_code.ne('Unknown')].copy();comp['attributed_fraction']=comp.credit/comp.known_AF_studies
    require(np.allclose(comp.groupby('year').attributed_fraction.sum(),1),'ED2 attribution shares do not conserve')
    save(out,'ed2a_attributed_composition',comp)
    # Historical pilot data: no independent gold-standard assumption.
    pf=ROOT/'fulltext/pilot/human_annotation_v6/evaluation';pr=pf/'pilot_150_models_vs_human_report_v6.json';px=pf/'pilot_150_models_vs_human_records_v6.csv'
    report=json.loads(pr.read_text());require(sha(px)==report['outputs']['per_record_comparison']['sha256'],'Pilot comparison bytes differ')
    x=pd.read_csv(px,keep_default_na=False);require(len(x)==150 and x.work_id.is_unique,'Pilot cohort differs')
    matrices=[];metrics=[]
    for prefix in ['a','b','c','ensemble']:
        rows,metric=evaluate_pilot(x,prefix);matrices.extend(rows);metrics.append(metric)
    require(metrics[-1]['evaluated_n']==122,'Pilot evaluated count differs')
    save(out,'pilot_comparison_records',x);save(out,'pilot_confusion',pd.DataFrame(matrices));save(out,'Table_S2_pilot_metrics',pd.DataFrame(metrics))
    save(out,'pilot_reference_states',x.groupby(['reference_status','reference_route'],dropna=False).size().reset_index(name='n'))
    pins.extend([pin(pr),pin(px)])
    human=ROOT/'fulltext/pilot/human_annotation_v6/final/pilot_150_human_reference_report_v6.json';pins.append(pin(human))
    shutil.copy2(pr,out/'provenance/pilot_evaluation_report.json');shutil.copy2(human,out/'provenance/pilot_human_reference_report.json')
    finalmeta=ROOT/'fulltext/production/final_database_v2/af_research_database_final_summary_v2.json';pins.append(pin(finalmeta));shutil.copy2(finalmeta,out/'provenance/production_summary.json')
    for name in ['data_flow_zh.md','methods_zh.md']:
        p=HISTORY/name;oldmanifest=json.loads((HISTORY/'run_manifest.json').read_text());require(sha(p)==oldmanifest['outputs'][name]['sha256'],'Historical process narrative differs');pins.append(pin(p));shutil.copy2(p,out/'provenance'/('historical_'+name.replace('.md','.source.txt')))
    # Named nodes retain their units and parallel branches, not a false single funnel.
    nodes=[('Raw corpus',6046663,'publication records','2015–2025 master'),('Eligible foundations',4686896,'work records','article/review/preprint'),('Original approved links',4686894,'study units','two original study links'),('Revision approved links',4686879,'study units','15 additional duplicate members removed'),
      ('Main eligible corpus',2714594,'studies','2020–2025'),('Initial candidates',29127,'work records','initial keyword/seed retrieval, not complete final-cohort denominator'),('Additional retrieval leads',826,'work records','old screen-negative pool; expanded keywords/AF1'),('Additional eligible candidates',765,'work records','61 other-type leads outside eligible recall'),
      ('Earlier decisive supplementary reviews',179,'work records','71 use/107 non-use/1 platform'),('Remaining supplementary review',586,'work records','556 A/B-eligible;28 insufficient;2 oversize'),('A/B submitted',556,'work records per model','154 full-text packets;402 abstract packets'),('C reviewed',516,'work records','exception routing'),('Supplementary accepted use',74,'work records','not all net additional studies'),('Supplementary non-use',159,'work records','accepted non-use'),('Supplementary platform',1,'work record','platform excluded'),('Supplementary uncertain',531,'work records','unknown retained'),('Old main AF',16341,'studies','work-to-study coherent representatives'),('Initial added net AF',70,'studies','71 positive records minus one duplicate'),('Latest added net AF',3,'studies','latest accepted three'),('Final main AF',16414,'studies','2020–2025')]
    save(out,'Table_S1_process_nodes',pd.DataFrame(nodes,columns=['node','n','unit','definition']))
    seeds=pd.DataFrame([['AF2','W3177828909','Highly accurate protein structure prediction with AlphaFold','2021-07','initial'],['AlphaFold-Multimer','W3202105508','Protein complex prediction with AlphaFold-Multimer','2021-10','initial'],['AFDB','W3211795435','AlphaFold Protein Structure Database','2021-07','initial'],['AF3','W4396721167','Accurate structure prediction of biomolecular interactions with AlphaFold 3','2024-05','initial']],columns=['seed','openalex_id','archived_title','milestone_month','strategy'])
    save(out,'Table_S1_seed_registry',seeds);pins.append(pin(ROOT/'code/01_data_prepare_new.py'))
    shutil.copy2(PLAN,out/'provenance/figure1-revision-plan-3.md');dump(out/'provenance/input_pins.json',pins)
    for n in COPY:
        if not (out/'tables'/f'{n}.csv').exists():load(out,n).to_csv(out/'tables'/f'{n}.csv',index=False)
    dump(out/'preparation_summary.json',dict(eligible_main_studies=int(main.n.sum()),AF_main_studies=int(main[main.group.eq('AF')].n.sum()),eligible_subfields=22,
      AF_observed_subfields=int(len(af)),pilot_N=150,pilot_evaluated=122,pilot_unresolved=28,
      named_handoff_tables_found=False,pilot_reference_independence='not_confirmed',production_process_equivalence='not_confirmed',new_API_calls=0))
    print('Plan3 preparation PASS: 2714594 eligible /16414 AF studies;22 eligible fields;pilot150/122;exact source pins retained.',flush=True)

if __name__=='__main__':run(OUT)
