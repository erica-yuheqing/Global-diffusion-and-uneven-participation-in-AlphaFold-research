"""Independent numeric checks, figure bounds/fonts, immutable publication and portable ZIP."""
import re,shutil,subprocess,tempfile,zipfile
from urllib.parse import unquote,urlsplit
from PIL import Image
from common import *
from prepare import evaluate_pilot

def links(root):
    root=Path(root).resolve();records=[]
    for path in root.rglob('*.md'):
        for label,target in re.findall(r'!?\[([^\]\n]*)\]\(([^\n]+?)\)',path.read_text()):
            target=target.strip().strip('<>')
            if target.startswith(('https://','http://','mailto:','#')):continue
            target=unquote(urlsplit(target).path);require(not Path(target).is_absolute() and not re.match(r'^[A-Za-z]:',target),'Nonportable link '+str(path)+':'+target)
            full=(path.parent/target).resolve();require(full.is_relative_to(root) and full.is_file(),'Broken/escaping Markdown link '+str(path)+':'+target)
            records.append(dict(file=str(path.relative_to(root)),target=target))
    return records

def inputs_unchanged(out):
    for name in ['input_pins.json','additional_input_pins.json','handoff_input_pins.json']:
        for pin in json.loads((out/'provenance'/name).read_text()):
            p=Path(pin['path']);require(p.is_file() and not p.is_symlink() and sha(p)==pin['sha256'],'Source file changed '+str(p))

def numeric(out):
    checks=[]
    def check(n,v):require(bool(v),n);checks.append(dict(check=n,status='PASS'))
    def same(n,a,b,tol=1e-10):check(n,np.allclose(a,b,atol=tol,rtol=1e-9,equal_nan=True))
    p=load(out,'study_country_patterns');cr=load(out,'annual_country_credits');reg=sorted(cr.country_code.unique());c=load(out,'concentration');draw=load(out,'bootstrap_draws')
    check('Registry fixed 227 including zero credit',len(reg)==227 and cr.groupby(['year','group']).size().eq(227).all())
    check('Integer whole-study patterns',p.n.ge(1).all() and (p.n%1).eq(0).all())
    check('Study main eligible 2714594',p[p.year.between(2020,2025)].n.sum()==2714594)
    check('Study main AF16414;2020eleven',p[p.year.between(2020,2025)&p.group.eq('AF')].n.sum()==16414 and p[p.year.eq(2020)&p.group.eq('AF')].n.sum()==11)
    lookup={k:i for i,k in enumerate(reg)}
    for row in c.itertuples():
        for group,field in [('AF','af_gini'),('C','comparator_gini')]:
            x=p[p.year.eq(row.year)&p.group.eq(group)].groupby('signature').n.sum();credit=np.zeros(227)
            for sig,n in x.items():
                if not sig:continue
                codes=sig.split('|');check_key=len(codes)==len(set(codes)) and set(codes)<=set(reg)
                require(check_key,'Bad study country set')
                for code in codes:credit[lookup[code]]+=n/len(codes)
            same(f'{row.year} {group} country-set exact fractional credit',credit,cr[cr.year.eq(row.year)&cr.group.eq(group)].set_index('country_code').reindex(reg).credit,1e-7)
            same(f'{row.year} {group} 227-country Gini',gini(credit),getattr(row,field))
            d=draw[draw.year.eq(row.year)&draw.group.eq(group)];check(f'{row.year}{group}1000 unique bootstrap replicates',len(d)==1000 and d.replicate.is_unique)
            lower='af_lower' if group=='AF' else 'comparator_lower';upper=lower.replace('lower','upper')
            same(f'{row.year} {group} original study-bootstrap range',np.quantile(d.gini,[.025,.975]),[getattr(row,lower),getattr(row,upper)])
        x=draw[draw.year.eq(row.year)].pivot(index='replicate',columns='group',values='gini')
        same(f'{row.year} direct replicate difference interval',np.quantile(x.AF-x.C,[.025,.975]),[row.delta_lower,row.delta_upper])
        same(f'{row.year} signed raw gap',row.delta_gini,row.af_gini-row.comparator_gini)
    ep=load(out,'concentration_endpoint_sensitivity');pivot=draw.pivot(index='replicate',columns=['year','group'],values='gini')
    for r in ep.itertuples():
        values=pivot[(r.end,'AF')]-pivot[(r.start,'AF')]
        if r.estimand=='AF_minus_C_Gini_endpoint_change':values-=pivot[(r.end,'C')]-pivot[(r.start,'C')]
        same('Raw endpoint original repeat interval '+r.estimand+str(r.start),np.quantile(values,[.025,.975]),[r.lower,r.upper])
    cp=c.set_index('year');same('Raw change −0.01442729',cp.loc[2025,'delta_gini']-cp.loc[2021,'delta_gini'],-.01442729150470512)
    check('Raw reversals2023/2025 retained',cp.loc[2023,'delta_gini']>cp.loc[2022,'delta_gini'] and cp.loc[2025,'delta_gini']>cp.loc[2024,'delta_gini'])
    s=load(out,'matching_summary');h=pd.read_csv(out/'handoff_source/source_data/matching_summary.csv');check('15 exact supplied matching summaries',len(s)==len(h)==15)
    same('Main matching points taken from handoff not local audit',s.point,h.excess_gini);same('Supplied matched lower range',s.lower,h.excess_lower);same('Supplied matched upper range',s.upper,h.excess_upper)
    same('Fixed AF minus matched mean identity',s.point,s.AF_gini-s.matched_non_AF_mean)
    check('Matching ranges not CI',s.interval_type.str.contains('matched_range_AF_fixed').all())
    for name in ['matching_stratum_support','local_audit_matching_stratum_support']:
        x=load(out,name);check('All matching strata sufficient '+name,(x.non_AF_available>=x.AF_target).all() and x.supported.all())
    originalep=load(out,'matching_endpoint_changes');hp=pd.read_csv(out/'handoff_source/source_data/matching_endpoint_changes.csv')
    check('Six original supplied endpoint rows',len(originalep)==6);same('Handoff endpoint means',originalep.point,hp.mean_excess_change);same('Handoff endpoint ranges kept exactly',originalep[['lower','upper']],hp[['benchmark_lower','benchmark_upper']])
    for r in originalep.itertuples():
        q=s[s.spec.eq(r.spec)].set_index('year');same('Supplied endpoint point difference '+r.spec+str(r.start),r.point,q.loc[r.end,'point']-q.loc[r.start,'point'])
    audit=load(out,'local_audit_matching_draws');summary=load(out,'local_audit_matching_summary');target=load(out,'local_audit_matching_stratum_support').groupby(['spec','year']).AF_target.sum()
    check('Local independent audit draws explicitly separate',len(audit)==36000 and audit.groupby(['spec','year']).replicate.nunique().eq(2000).all())
    for r in summary.itertuples():
        x=audit[audit.spec.eq(r.spec)&audit.year.eq(r.year)];same('Local audit mean/range '+r.spec+str(r.year),[x.gap.mean(),*np.quantile(x.gap,[.025,.975])],[r.point,r.lower,r.upper])
        check('Local whole-study target conserved '+r.spec+str(r.year),x.matched_studies.eq(target.loc[(r.spec,r.year)]).all())
        same('Local fixed AF gap algebra '+r.spec+str(r.year),x.gap,x.AF_gini-x.matched_non_AF_gini)
    check('Main matched sequence no sustained narrowing',s.query('spec=="count_composition"').point.gt(0).all() and s.query('spec=="count_composition"').point.iloc[-1]>s.query('spec=="count_composition"').point.iloc[0])
    r=load(out,'country_year_AF_normalization');d=load(out,'figure1d_top10_endpoints');base=load(out,'normalization_country_selection')
    check('Fixed baseline ten, positive endpoints',base.head(10).country_code.tolist()==ORDER[:10] and d.R.gt(0).all() and len(d)==20)
    for year,x in r.groupby('year'):
        g=x.af_credit.sum()/x.local_all_credit.sum();positive=x.local_all_credit.gt(0)
        same(f'{year} raw national r',x.loc[positive,'r'],x.loc[positive,'af_credit']/x.loc[positive,'local_all_credit'])
        same(f'{year} R algebra and ALL denominator',x.loc[positive,'R'],x.loc[positive,'af_credit']/x.loc[positive,'local_all_credit']/g)
        check(f'{year} zeros distinct from undefined',x.loc[~positive,'R'].isna().all() and x.loc[positive&x.af_credit.eq(0),'R'].eq(0).all())
    norm=load(out,'figure1_normalization_heatmap_source');check('S5 105 cells, baseline fixed order',len(norm)==105 and norm.query('year==2021').country_code.tolist()==ORDER+['Other'])
    for year,x in norm.groupby('year'):
        other=x[x.country_code.eq('Other')].iloc[0];pool=r[r.year.eq(year)&~r.country_code.isin(ORDER)]
        same(f'{year} Other pooled R not mean',other.R,(pool.af_credit.sum()/pool.local_all_credit.sum())/(pool.A_total.iloc[0]/pool.T_total.iloc[0]))
    comp=load(out,'ed2a_attributed_composition');check('ED2a no unknown',not comp.country_code.eq('Unknown').any());same('ED2a known credit denominator',comp.attributed_fraction,comp.credit/comp.known_AF_studies);same('ED2a sums100%',comp.groupby('year').attributed_fraction.sum(),np.ones(5))
    for row in c.query('year>=2021').itertuples():
        credit=cr[cr.year.eq(row.year)&cr.group.eq('AF')].credit.sort_values(ascending=False)
        same(f'{row.year} annual ranked top5/top10',[credit.head(5).sum()/credit.sum(),credit.head(10).sum()/credit.sum()],[row.af_top5,row.af_top10])
    f=load(out,'Table_S3_subfield_year');check('22 fields by6years exactly132',len(f)==132 and f.subfield.nunique()==22);check('21 AF active fields',f.groupby('subfield').AF.sum().gt(0).sum()==21)
    check('Field eligible/AF conserved',f.eligible.sum()==2714594 and f.AF.sum()==16414)
    for (year,group),x in load(out,'subfield_year_top5_other').groupby(['year','display_group']):same(f'{year}{group} pooled rate',x.AF_rate,x.AF/x.eligible)
    pilot=load(out,'pilot_comparison_records');prod=load(out,'pilot_production_correspondence');merged=pilot.merge(prod[['work_id','production_af_use_label','production_adoption_eligible']],on='work_id',validate='one_to_one')
    rows,metric=evaluate_pilot(merged,'production');actual=load(out,'Table_S2_pilot_metrics').query('system=="production"').iloc[0]
    for name in ['evaluated_n','TP','FP','TN','undecided_or_missing','precision','recall']:same('Pilot final-production '+name,metric[name],actual[name])
    states=load(out,'pilot_reference_states').groupby('reference_status').n.sum();check('Pilot 150/122/28 states',states.sum()==150 and states['resolved']==122 and states['unresolved_evidence']==24 and states['uncertain_consensus']==4)
    mat=load(out,'pilot_confusion').query('system=="production"');check('Pilot2x3 matrix preserves 122',mat.n.sum()==122 and len(mat)==6 and mat[mat.prediction.eq('uncertain/missing')].n.sum()==2)
    acceptance=json.loads((out/'provenance/author_confirmation.json').read_text());check('Human pre-answer judgement explicitly author-confirmed',acceptance['exact_user_statement']=='人工判读前未查看模型答案')
    months=load(out,'monthly_diffusion').set_index('month')
    for month,n in [('2021-06-01',14),('2024-04-01',123),('2025-12-01',143)]:check('Phase cumulative '+month,months.loc[month,'cumulative_countries']==n)
    art=json.loads((out/'provenance/main_artist_contract.json').read_text());check('Only a/b/c/d main letters no titles',art['panel_labels']==['a','b','c','d'] and not art['titles']);same('b two-layer years exactly aligned',art['b_year_positions'],art['b_gap_positions'])
    check('Main d fixed baseline and actual R log2',art['d_order']==ORDER[:10] and art['d_scale']=='log2 raw R ticks')
    check('Main c only count-composition; nonAF label',art['main_matching_spec']=='count_composition' and art['non_AF_label']=='non-AF')
    index=load(out,'panel_source_index');check('25 per-panel CSV files',len(index)==25 and all((out/p).is_file() for p in index.path))
    return checks

def media(out):
    checks=[];pdfs=sorted((out/'figures').glob('*.pdf'));require(len(pdfs)==9,'Need exactly 1main+2ED+6S PDFs')
    for p in pdfs:
        name=p.stem;bounds=json.loads((out/'provenance'/f'{name}_text_bounds.json').read_text())
        require(all(t['x0']>=-.001 and t['y0']>=-.001 and t['x1']<=1.001 and t['y1']<=1.001 for t in bounds),'Out-of-page text '+name)
        checks.append(dict(check=name+' text inside page',status='PASS'))
        for suffix in ['png','tiff']:
            raster=out/'figures'/f'{name}_600dpi.{suffix}'
            with Image.open(raster) as im:
                require(im.mode=='RGB' and im.info.get('icc_profile') and all(abs(d-600)<.1 for d in im.info['dpi']),'Invalid RGB/sRGB/dpi '+name)
                if name=='Figure1_a_d':require(abs(im.width/600*25.4-183)<.06 and abs(im.height/600*25.4-193)<.06,'Main dimensions differ')
                if suffix=='tiff':require(im.info.get('compression')=='tiff_lzw','TIFF not LZW')
            checks.append(dict(check=name+' '+suffix+' native600dpiRGB/sRGB',status='PASS'))
        fonts=subprocess.run([shutil.which('pdffonts'),str(p)],capture_output=True,text=True,check=True).stdout.splitlines()[2:]
        require(fonts and all(' yes ' in line and 'Type 3' not in line for line in fonts),'PDF fonts not embedded '+name)
        require('<text' in p.with_suffix('.svg').read_text(),'SVG not editable '+name);checks.append(dict(check=name+' embedded PDF fonts/editable SVG',status='PASS'))
    return checks

def inventory(out):return {str(p.relative_to(out)):{'sha256':sha(p),'bytes':p.stat().st_size} for p in sorted(out.rglob('*')) if p.is_file() and p.name not in ['run_manifest.json','.DS_Store'] and '__pycache__' not in p.parts}
def verify(out,check_sources=True):
    require(inventory(out)==json.loads((out/'run_manifest.json').read_text())['outputs'],'Published output bytes/inventory differ')
    if check_sources:inputs_unchanged(out)
    checks=numeric(out)+media(out);lk=links(out);print(f'Plan3 read-only PASS: {len(checks)} checks; {len(lk)} local links',flush=True);return checks,lk

def finish(out):
    require(not (out/'run_manifest.json').exists(),'Do not overwrite published version')
    require((out/'provenance/visual_review_zh.md').is_file(),'Actual visual inspection required')
    inputs_unchanged(out);checks=numeric(out)+media(out)
    code=out/'code';code.mkdir(exist_ok=True)
    for p in MOD.glob('*.py'):shutil.copy2(p,code/p.name)
    for p in [MOD/'README.md',MOD/'protocol_update_v2.md']:shutil.copy2(p,code/p.name)
    dump(out/'validation_report.json',dict(status='VERIFYING',checks=checks));lk=links(out)
    dump(out/'provenance/relative_links.json',lk)
    dump(out/'validation_report.json',dict(status='PASS',checks=checks,check_count=len(checks),links=len(lk),nine_figures=True,original_matching_summary_used=True,
      original_matching_draws_certified=False,author_reported_pre_answer_human_judgement=True,independent_holdout_certified=False,new_API_calls=0))
    dump(out/'run_manifest.json',dict(version=out.name,outputs=inventory(out),scope='1 main a-d +2 ED +6 S; author-supplied handoff; not independent holdout certification',new_API_calls=0));verify(out)
    target=MOD/'Figure1_plan3_reading_package_v1.zip';require(not target.exists(),'Do not overwrite previous ZIP')
    with zipfile.ZipFile(target,'x',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in sorted(out.rglob('*')):
            if p.is_file() and '__pycache__' not in p.parts and p.name!='.DS_Store':z.write(p,Path(out.name)/p.relative_to(out))
    with tempfile.TemporaryDirectory(prefix='figure1-plan3-extract-') as tmp:
        with zipfile.ZipFile(target) as z:require(z.testzip() is None,'ZIP CRC failure');z.extractall(tmp)
        verify(Path(tmp)/out.name,check_sources=False)
    dump(target.with_suffix('.verification.json'),dict(status='PASS',sha256=sha(target),bytes=target.stat().st_size,actual_extraction=True,all_output_hashes=True,relative_links=len(lk)))
    print('ZIP extraction/link verification PASS: '+str(target),flush=True)

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--finish',action='store_true');args=parser.parse_args()
    if args.finish:finish(OUT)
    elif (OUT/'run_manifest.json').exists():verify(OUT)
    else:print('Unpublished numeric/export checks:',len(numeric(OUT)+media(OUT)))
