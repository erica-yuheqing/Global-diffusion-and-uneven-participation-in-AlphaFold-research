"""Numeric, artist, output and portable link validation; no re-estimation."""
from common import *
import re
from PIL import Image

def validate_inputs(out):
    checks={}
    def ck(n,v):require(v,n);checks[n]=bool(v)
    pins=json.loads((out/'provenance/original_inputs_manifest.json').read_text())['input_files']
    ck('45 frozen inputs',len(pins)==45)
    for pin in pins:ck('input hash: '+pin['copy'],sha(out/pin['copy'])==pin['sha256'])
    a=load(out,'source_data/Figure1b_upper.csv');r=load(out,'source_data/Figure1b_lower.csv');m=load(out,'source_data/Figure1c.csv')
    ck('main years exactly 2021–2025',a.year.tolist()==r.year.tolist()==m.year.tolist()==list(range(2021,2026)))
    ck('Gini 227 countries including zeros',(a.country_count==227).all())
    ck('raw difference identity',np.allclose(a.af_gini-a.comparator_gini,r.delta_gini,atol=1e-12,rtol=0))
    ck('matched point identity',np.allclose(m.AF_gini-m.matched_non_AF_mean,m.point,atol=1e-12,rtol=0))
    ck('main matched spec',(m.spec=='count_composition').all() and (m.replicates==2000).all())
    ck('matched interval lower inversion',np.allclose(m.AF_gini-m.benchmark_upper,m.lower,atol=1e-12,rtol=0))
    ck('matched interval upper inversion',np.allclose(m.AF_gini-m.benchmark_lower,m.upper,atol=1e-12,rtol=0))
    for frame,p,lo,hi,label in [(a,'af_gini','af_lower','af_upper','AF'),(a,'comparator_gini','comparator_lower','comparator_upper','non-AF'),(r,'delta_gini','delta_lower','delta_upper','raw'),(m,'point','lower','upper','matched')]:ck('interval encloses point: '+label,((frame[lo]<=frame[p])&(frame[p]<=frame[hi])).all())
    sf=load(out,'tables/Table_S3_subfield_year.csv');ck('16414 AF studies',sf.AF.sum()==16414);ck('2714594 eligible studies',sf.eligible.sum()==2714594)
    ck('22 eligible and 21 nonzero AF subfields',sf.subfield.nunique()==22 and sf.loc[sf.AF>0,'subfield'].nunique()==21)
    ck('22 by 6 subfield-year rows',len(sf)==132 and not sf.duplicated(['year','subfield']).any())
    s3=load(out,'source_data/S3a.csv');ck('annual AF counts',s3.confirmed_af.tolist()==[11,393,2389,3904,4144,5573])
    diff=load(out,'monthly_diffusion');month=pd.to_datetime(diff.month);ck('72 consecutive months',month.tolist()==pd.date_range('2020-01-01','2025-12-01',freq='MS').tolist())
    ck('historical base retained',(diff.pre2020_countries==1).all() and np.array_equal(diff.cumulative_countries,diff.new_countries.cumsum()+1))
    ck('era cumulative endpoints',[int(diff.loc[month.eq(pd.Timestamp(s)),'cumulative_countries'].iloc[0]) for s in ['2021-06-01','2024-04-01','2025-12-01']]==[14,123,143])
    first=load(out,'first_observed_stage_map_source');ck('143 first-observed countries',len(first)==143 and first.country_code.nunique()==143)
    full=load(out,'tables/Table_S4_country_year_R_first_observation.csv');ck('Namibia retained',(full.country_code=='NA').sum()==6)
    ck('227 by 6 country rows',len(full)==1362 and full.country_code.nunique()==227)
    ck('2025 active countries 128',full.loc[(full.year==2025)&(full.af_credit>0),'country_code'].nunique()==128)
    for y,block in full.groupby('year'):
        ck(f'R formula {y}',np.allclose(block.loc[block.value_status=='positive','R'].astype(float),(block.loc[block.value_status=='positive','af_credit']/block.loc[block.value_status=='positive','A_total'])/(block.loc[block.value_status=='positive','local_all_credit']/block.loc[block.value_status=='positive','T_total']),atol=1e-10))
    end=load(out,'figure1d_top10_endpoints');ck('baseline ten fixed',end.country_code.drop_duplicates().tolist()==ORDER[:10] and len(end)==20)
    ck('positive R endpoints',(end.R>0).all())
    comp=load(out,'ed2a_attributed_composition');ck('fixed AF ten plus Other',comp.country_code.drop_duplicates().tolist()==['US','CN','DE','GB','FR','JP','CA','IT','ES','IN','Other'])
    ck('composition uses attributed fraction',np.allclose(comp.attributed_fraction,comp.credit/comp.known_AF_studies))
    ck('composition sums to 100%',np.allclose(comp.groupby('year').attributed_fraction.sum(),1))
    top=load(out,'source_data/ED2b.csv');ck('dynamic top ten separately computed',np.allclose(top.af_top10*100,top.top10_percent) and (top.top10_percent>=top.top5_percent).all())
    # Verify pooled Other from full country credits, not mean of ratios.
    heat=load(out,'figure1_normalization_heatmap_source')
    for y in range(2021,2026):
        other=full[(full.year==y)&~full.country_code.isin(ORDER)];expected=(other.af_credit.sum()/other.local_all_credit.sum())/(other.A_total.iloc[0]/other.T_total.iloc[0])
        ck(f'pooled Other R {y}',np.isclose(float(heat.loc[(heat.year==y)&(heat.country_code=='Other'),'R'].iloc[0]),expected))
    ck('heatmap 105 cells',len(heat)==105)
    for name in ['source_data/S4a.csv','source_data/S4b.csv']:
        x=load(out,name)
        ck('Other pooled counts '+name, all(int(x.loc[(x.year==y)&(x.display_group=='Other'),'AF'].iloc[0])==int(sf.loc[(sf.year==y)&(sf.display_group=='Other'),'AF'].sum()) and int(x.loc[(x.year==y)&(x.display_group=='Other'),'eligible'].iloc[0])==int(sf.loc[(sf.year==y)&(sf.display_group=='Other'),'eligible'].sum()) for y in range(2020,2026)))
    counts=load(out,'source_data/S1c.csv').set_index('node').n
    ck('765 supplementary dispositions',sum(int(counts[n]) for n in ['Supplementary accepted use','Supplementary non-use','Supplementary platform','Supplementary uncertain'])==765)
    ck('net studies 16341+70+3',int(counts['Old main AF'])+int(counts['Initial added net AF'])+int(counts['Latest added net AF'])==int(counts['Final main AF'])==16414)
    states=load(out,'pilot_reference_states');ck('pilot150 with122 resolved',states.n.sum()==150 and states.loc[states.reference_status=='resolved','n'].sum()==122)
    confusion=load(out,'source_data/S2b.csv');ck('production confusion122',confusion.n.sum()==122)
    metric=load(out,'Table_S2_pilot_metrics').set_index('system');ck('production precision and recall',np.isclose(metric.loc['production','precision'],103/105) and metric.loc['production','recall']==1)
    ck('ensemble kept separate',np.isclose(metric.loc['ensemble','precision'],100/101) and np.isclose(metric.loc['ensemble','recall'],100/103))
    support=load(out,'tables/matching_stratum_support.csv');ck('all target strata supported',(support.non_AF_available>=support.AF_target).all())
    ep=load(out,'matching_endpoint_changes');ck('6 matched endpoint rows',len(ep)==6)
    mat=load(out,'matching_summary')
    ck('15 complete matched points',len(mat)==15 and set(mat.spec)==set(SPECS) and not mat.duplicated(['spec','year']).any() and (mat.replicates==2000).all())
    for frame,key,lo,hi,label in [(mat,'point','lower','upper','all matched years'),(ep,'point','lower','upper','all matched endpoint changes'),(load(out,'concentration'),'delta_gini','delta_lower','delta_upper','full raw gap series')]:
        ck('interval encloses point: '+label,((frame[lo]<=frame[key])&(frame[key]<=frame[hi])).all())
    for row in ep.itertuples():
        vals=mat.loc[mat.spec==row.spec].set_index('year').point
        ck(f'endpoint point identity {row.spec} {row.start}',np.isclose(row.point,vals.loc[2025]-vals.loc[row.start]))
    raw=load(out,'tables/concentration_endpoint_sensitivity.csv');e=raw[(raw.start==2021)&(raw.end==2025)&(raw.estimand=='AF_minus_C_Gini_endpoint_change')].iloc[0]
    ck('raw paired endpoint estimate',np.isclose(e.point,r.delta_gini.iloc[-1]-r.delta_gini.iloc[0]))
    ck('raw paired interval rounded',round(e.lower,4)==-.0232 and round(e.upper,4)==-.0105)
    ck('all raw endpoint intervals enclose point',((raw.lower<=raw.point)&(raw.point<=raw.upper)).all())
    cov=load(out,'annual_source_coverage');ck('complete 12 attribution rows',len(cov)==12 and not cov.duplicated(['year','group']).any() and set(cov.group)=={'AF','C'})
    ck('raw narrowing early fraction',np.isclose((r.delta_gini.iloc[0]-r.delta_gini.iloc[1])/(r.delta_gini.iloc[0]-r.delta_gini.iloc[-1]),.659,atol=.001))
    return checks

def links(out):
    result=[]
    for p in out.rglob('*.md'):
        for raw in re.findall(r'!?\[[^\]]*\]\(([^\n]+?)\)',p.read_text()):
            target=raw.strip().strip('<>')
            if target.startswith(('https:','http:','mailto:','#')):continue
            target=target.split('#')[0];require(not target.startswith('/'),'Nonportable link '+str(p)+': '+target)
            q=p.parent/target;require(q.exists(),'Broken link '+str(p)+': '+target);result.append({'document':str(p.relative_to(out)),'target':target})
    return result

def validate_outputs(out):
    from figures import NAMES
    checks=validate_inputs(out);bounds=[]
    for name in NAMES:
        for ext in ['pdf','svg','_600dpi.png','_preview.png']:
            path=out/'figures'/(name+ext if ext.startswith('_') else name+'.'+ext);require(path.is_file(),'Missing figure '+str(path))
        info=json.loads((out/'provenance'/f'{name}_render.json').read_text())
        with Image.open(out/'figures'/f'{name}_600dpi.png') as im:
            require(im.mode=='RGB' and min(im.info['dpi'])>599,'RGB/DPI '+name)
            require(all(abs(size-mm/25.4*600)<2 for size,mm in zip(im.size,info['physical_mm'])),'Physical size '+name)
        for t in json.loads((out/'provenance'/f'{name}_text_bounds.json').read_text()):
            if min(t['x0'],t['y0'])<-.004 or max(t['x1'],t['y1'])>1.004:bounds.append({'figure':name,**t})
    require(not bounds,'Text outside page '+str(bounds))
    contract=json.loads((out/'provenance/main_artist_contract.json').read_text());require(contract['b_markers']==['D','o'] and contract['panels']==['a','b'],'Main artist contract')
    checks['ten figure sets with vector and RGB600dpi']=True;checks['all recorded text within page']=True;checks['main exact dimensions']=np.allclose(json.loads((out/'provenance/Figure1_a_b_render.json').read_text())['physical_mm'],[183,92])
    dump(out/'validation_report.json',{'status':'IN_PROGRESS','scope':'Link validation pending'})
    records=links(out);dump(out/'provenance/relative_links.json',records)
    report={'status':'PASS','checks':checks,'check_count':len(checks),'link_count':len(records),'limits':['No new bootstrap/matching estimation; frozen summaries only','No independent held-out certification','No publisher acceptance certification','Whole-manuscript original DOCX not edited; integrated cross-reference copies supplied separately']}
    dump(out/'validation_report.json',report);return report

if __name__=='__main__':
    import sys
    report=validate_outputs(Path(sys.argv[1]) if len(sys.argv)>1 else Path(__file__).resolve().parent.parent)
    print(f"Validation PASS: {report['check_count']} checks, {report['link_count']} local links")
