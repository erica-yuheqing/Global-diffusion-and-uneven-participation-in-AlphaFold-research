"""Independent numeric/packaging validation; never updates labels or estimates."""
from common import *
from draw import FIGURES
from model import rcs
from scipy.special import expit
from PIL import Image
import re,argparse,csv

def numeric(out):
 checks={}
 def ck(name,v):require(v,name);checks[name]=bool(v)
 for pin in json.loads((out/'provenance/input_pins.json').read_text()):ck('input sha '+pin['copy'],sha(out/pin['copy'])==pin['sha256'])
 b=read(out,'institution_baseline_and_first_participation.csv');main=b.loc[truth(b.eligible_20)]
 ck('B0 IDs',len(b)==b.institution_id.nunique()==52098);ck('B1 country unique',sum(b.baseline_country_count.eq(1))==50371)
 ck('B2 population',len(main)==48010 and main.country.nunique()==68);ck('domestic group counts',main.groupby('group').size().to_dict()=={'L':17602,'M':14720,'H':15688})
 country=main.groupby('country').context.first();ck('national group counts',country.value_counts().to_dict()=={'High':23,'Low':23,'Middle':22})
 for c,q in main.groupby('country'):
  cuts=np.quantile(q.V_i,[1/3,2/3],method='linear');labels=np.where(q.V_i<=cuts[0],'L',np.where(q.V_i<=cuts[1],'M','H'))
  ck('type7 no split ties '+c,np.array_equal(labels,q.group) and q.groupby('group').size().min()>=20)
 sx=read(out,'Table_SX_a_sample.csv');q=sx[sx.country!='OVERALL'];counts=q.groupby('exclusion_reason').baseline_institutions.sum()
 ck('selection flow',counts['fixed_country_unknown_or_multiple']==1727 and counts['collapsed_or_empty_tertiles']==100 and counts['group_below_N20']==2261)
 status=table(out,'Table_SX_c_status_totals.csv').groupby('date_state').institutions.sum().to_dict()
 ck('B0 mutually exclusive statuses',status=={'confirmed_before_2020':2,'confirmed_year_only_or_other_legacy_exclusion':1663,'legacy_date_identifiable_entry_2020_2025':6369,'no_confirmed_AF_observed':44064})
 ck('cohort partition adds to B0',table(out,'Table_SX_c_cohort_partition.csv').institutions.sum()==52098)
 summaries=table(out,'Table_SX_c_cohort_summary.csv').set_index(['population_id','condition']).institutions
 ck('date vs pool counts distinct',summaries.loc['B0','legacy_date_entry']==6369 and summaries.loc['B2','legacy_date_entry']==6040 and summaries.loc['B2','ever_AF_pool_year_le2025']==7654)
 ck('main author missing38',table(out,'Table_SX_d_author_missingness.csv').query('population_id=="B2"').author_unobserved.sum()==38)
 cg=read(out,'country_group_year_primary.csv');cg=cg[truth(cg.eligible_20)&cg.year.between(2020,2025)]
 ck('full annual cells',len(cg)==1224 and not cg.duplicated(['country','group','year']).any());ck('fixed denominators',(cg.groupby(['country','group']).fixed_N.nunique()==1).all())
 ck('A/C raw rates',np.allclose(cg.A,cg.active_N/cg.fixed_N,atol=1e-12) and np.allclose(cg.C,cg.cumulative_N/cg.fixed_N,atol=1e-12))
 ck('cumulative 7654',cg[cg.year==2025].cumulative_N.sum()==7654)
 weights=table(out,'new_weighting_annual.csv');dis=table(out,'new_weighting_disparities.csv')
 for (yr,g),x in cg.groupby(['year','group']):
  for weighting in ['equal_country','pooled_institution']:
   expected=np.mean(x.active_N/x.fixed_N) if weighting=='equal_country' else x.active_N.sum()/x.fixed_N.sum()
   got=weights[(weights.year==yr)&(weights.group==g)&(weights.weighting==weighting)].iloc[0]
   ck(f'weight formula {weighting} {yr} {g}',np.isclose(got.A,expected,atol=1e-12))
 for row in dis.itertuples():
  q=weights[(weights.weighting==row.weighting)&(weights.year==row.year)].set_index('group').A
  ck(f'R and G from rates {row.weighting} {row.year}',(not bool(row.R_defined) if q.H==0 else np.isclose(float(row.R),q.L/q.H,atol=1e-12)) and np.isclose(row.G_pp,100*(q.H-q.L),atol=1e-12))
 ready=read(out,'Fig2a_cumulative.csv','ready');ck('main cumulative18',len(ready)==18)
 for g,val in [('H',37.9130129649685),('M',8.300819240696515),('L',2.3471460849322112)]:
  x=ready[ready.group==g].sort_values('year');ck('C curve '+g,(np.diff(x.C)>=0).all() and np.isclose(100*x.C.iloc[-1],val,atol=1e-10))
 for yr,expected in [(2021,.009635763539298585),(2025,.04450460985571247)]:ck('R anchor '+str(yr),np.isclose(dis[(dis.year==yr)&(dis.weighting=='equal_country')].R.iloc[0],expected,atol=1e-12))
 for yr,expected in [(2021,3.3607112732139),(2025,23.50341402670982)]:ck('G anchor '+str(yr),np.isclose(dis[(dis.year==yr)&(dis.weighting=='equal_country')].G_pp.iloc[0],expected,atol=1e-10))
 ed=read(out,'ED4_country_endpoints.csv','ready');ed['R']=number(ed.R);piv=ed.pivot(index='country',columns='year',values='R');gap=ed.pivot(index='country',columns='year',values='G_pp')
 ck('ED4 NA and paired increases',len(piv)==68 and piv[2021].isna().sum()==24 and piv[2025].notna().sum()==68 and ((piv[2025]>piv[2021])&piv[2021].notna()).sum()==26)
 ck('ED4 absolute increases67',(gap[2025]>gap[2021]).sum()==67)
 date=read(out,'ED3b_first_entries.csv','ready');era=read(out,'ED3b_eras.csv','ready');ck('entry annual counts',date.new_institutions.tolist()==[16,562,1636,1551,1231,1373]);ck('entry era counts',era.institutions.tolist()==[41,4249,2079])
 s8=read(out,'S8_alternative_trajectories.csv','ready');common=read(out,'S8_common_fixed_ID_registry.csv')
 ck('common identical IDs',set(common[common.metric=='authors'].institution_id)==set(common[common.metric=='partners'].institution_id) and common.institution_id.nunique()==47910)
 for metric,sample,ns,cs in [('authors','metric_valid',47910,67),('partners','metric_valid',48010,68),('authors','common_valid',47910,67),('partners','common_valid',47910,67)]:
  x=s8[(s8.metric==metric)&(s8['sample']==sample)&(s8.year==2025)];ck('S8 population '+metric+sample,x.fixed_institutions.sum()==ns and (x.countries==cs).all())
 draws=read(out,'Fig2d_benchmark_draws.csv','ready');summary=read(out,'Fig2d_benchmark_summary.csv','ready').iloc[0];rep=read(out,'benchmark_annual_gap_replicates.csv');rep=rep[rep.context=='All'].pivot(index='replicate',columns='year',values='G_pp')
 ck('5000 uncentered replicates',len(draws)==draws.replicate.nunique()==5000 and np.allclose(rep[2025]-rep[2021],draws.sort_values('replicate').delta_G_pp,atol=1e-12))
 ck('formal analytic mean not simulated',summary.expected_delta_G==23.146794624720332 and not np.isclose(summary.expected_delta_G,draws.delta_G_pp.mean(),atol=1e-5,rtol=0))
 ck('simulation mean and quantiles',np.isclose(draws.delta_G_pp.mean(),summary.simulated_mean_delta_G,atol=1e-12) and np.allclose(np.quantile(draws.delta_G_pp,[.025,.975]),[summary.reference_low,summary.reference_high],atol=1e-12))
 ck('observed delta identity',np.isclose(summary.actual_delta_G,23.50341402670982-3.3607112732139,atol=1e-12))
 ck('D computed before rounding',np.isclose(summary.excess,summary.actual_delta_G-summary.expected_delta_G,atol=1e-12) and f'{summary.excess:.2f}'=='-3.00')
 comp=read(out,'Fig2e_growth_components.csv','ready').set_index('group');ck('both deviations negative',(comp.r_pp<0).all());ck('signed decomposition rH minus rL',np.isclose(comp.loc['H','r_pp']-comp.loc['L','r_pp'],summary.excess,atol=1e-12))
 original=read(out,'benchmark_summary.csv');hist=pd.read_csv(out/'inputs/raw/historical_audits/benchmark_summary.csv')
 for name in ['S10a_historical_thresholds.csv','S10c_historical_benchmark_specs.csv']:
  reuse=read(out,name,'ready')
  for row in reuse.itertuples():
   h=hist[(hist.variant==row.variant)&(hist.setting==row.setting)&(hist.context==row.context)].iloc[0]
   ck(f'historical point {name} {row.variant} {row.setting}',np.allclose([h.actual_delta_G,h.expected_delta_G,h.excess],[row.actual_delta_G,row.expected_delta_G,row.excess],atol=1e-12))
 # Independently audit historical threshold observed endpoints from frozen annual series.
 contexts=read(out,'context_group_year.csv')
 for setting,analysis in [('N10','N10'),('main','N20'),('N30','N30')]:
  x=contexts[(contexts.analysis==analysis)&(contexts.context=='All')&(contexts.group=='H')].set_index('year')
  exp=original[(original.setting==setting)&(original.variant=='main')&(original.context=='All')].actual_delta_G.iloc[0]
  ck('threshold annual endpoint '+setting,np.isclose(float(x.loc[2025,'G'])-float(x.loc[2021,'G']),exp,atol=1e-10))
 s9=read(out,'S9_annual_benchmark_gaps.csv','ready');allrep=read(out,'benchmark_annual_gap_replicates.csv')
 for row in s9.itertuples():
  v=allrep[(allrep.context==row.context)&(allrep.year==row.year)].G_pp
  ck(f'S9 annual reference {row.context} {row.year}',len(v)==5000 and np.allclose(np.quantile(v,[.025,.975]),[row.reference_low_pp,row.reference_high_pp],atol=1e-12))
 model=json.loads((out/'quality/continuous_model.json').read_text());design=table(out,'new_continuous_institution_design.csv');ck('continuous actual population',len(design)==48010 and design.institution_id.nunique()==48010 and design.country.nunique()==68 and design.y.sum()==7654)
 ck('continuous no tied-value split',design.groupby(['country','V_i']).percentile.nunique().max()==1 and design.groupby(['country','V_i']).bin.nunique().max()==1)
 expected=(design.groupby('country').V_i.rank(method='average')-.5)/design.groupby('country').institution_id.transform('size');ck('midrank independently reconstructed',np.allclose(expected,design.percentile,atol=1e-12))
 ck('prespecified knots',np.allclose(model['knots'],np.unique(np.quantile(design.percentile,[.05,.35,.65,.95])),atol=1e-12))
 ck('spline convergence rank',model['active']['converged'] and model['rank']==model['columns']==71 and not model['fallback_used'])
 ck('score gradient verified',model['gradient_fd_max_abs_error']<1e-4 and model['active']['score']<1e-9)
 coefficients=table(out,'new_continuous_model_coefficients.csv').coefficient.to_numpy();pred=table(out,'new_continuous_scale_predictions.csv');basis=(rcs(pred.percentile,model['knots'])-model['basis_center'])/model['basis_scale'];cp=expit(coefficients[:68,None]+(basis@coefficients[68:])[None,:])
 ck('standardized curve independently reconstructed',np.allclose(cp.mean(axis=0),pred.predicted_coverage,atol=1e-12))
 ck('descriptive curve no fake CI',pred.lower.eq('').all() and pred.upper.eq('').all() and (pred.interval_type=='none_descriptive_point_estimates').all())
 bins=table(out,'new_continuous_scale_bins.csv');ck('bins full grid and counts',len(bins)==680 and bins.fixed_N.sum()==48010 and bins.AF_N.sum()==7654)
 ck('empty bins preserved',(bins.loc[bins.fixed_N==0,'coverage']=='').all())
 summary_n=table(out,'new_strata_diagnostic_summary.csv').set_index('variant');ck('main strata independent historical counts',summary_n.loc['main','strata']==194625 and summary_n.loc['main','mutable_strata']==3620 and summary_n.loc['main','mutable_studies']==1224425 and summary_n.loc['main','mutable_AF_studies']==14524)
 relations=table(out,'new_N20_exchangeability.csv');ck('N20 relation population',len(relations)==612 and (relations.groupby('variant').opportunity_relations.sum()==6347340).all() and (relations.denominator_scope=='N20_fixed_institutions').all())
 raw=json.loads((out/'quality/raw_relation_audit.json').read_text());ck('raw duplicates and orphan check',raw['duplicates']==raw['orphans']==0 and raw['full_memberships']==6585658 and raw['N20_memberships']==6347340 and raw['raw_annual_counts_match'])
 analytic=json.loads((out/'quality/independent_analytic_check.json').read_text());ck('independent raw analytic expectation',analytic['status']=='PASS' and abs(analytic['difference_pp'])<5e-7 and analytic['not_used_to_replace_formal_estimate'])
 activity=table(out,'optional_activity_opportunity_decomposition.csv');active=activity[activity.opportunity_active_N>0];ck('A equals BQ domestic cells',np.allclose(active.A,number(active.B)*number(active.Q),atol=1e-12))
 ck('Q undefined at no opportunity',(activity.loc[activity.opportunity_active_N==0,'Q']=='').all())
 map=pd.read_csv(out/'source_data/panel_source_map.csv');ck('6 figures 21 direct panels',len(map)==21 and map.figure.nunique()==6 and not map.duplicated(['figure','panel']).any())
 for row in map.itertuples():ck(f'direct source {row.figure}{row.panel}',(out/row.source_data).is_file() and len(pd.read_csv(out/row.source_data,keep_default_na=False))==row.rows)
 return checks

def check_links(out):
 links=[]
 for path in out.rglob('*.md'):
  if 'inputs' in path.relative_to(out).parts:continue
  for raw in re.findall(r'!?\[[^\]]*\]\(([^\n]+?)\)',path.read_text()):
   target=raw.strip().strip('<>')
   if target.startswith(('https:','http:','mailto:','#')):continue
   target=target.split('#')[0];require(not target.startswith('/'),'Absolute reading link '+str(path));dest=(path.parent/target).resolve()
   require(dest.is_relative_to(out.resolve()) and dest.exists(),'Broken relative link '+str(path)+': '+target);links.append({'file':str(path.relative_to(out)),'target':target})
 return links

def validate(out):
 checks=numeric(out);bounds=[]
 for name,folder in FIGURES.items():
  meta=json.loads((out/'quality'/f'{name}_metadata.json').read_text());require(abs(meta['physical_mm'][0]-183)<1e-8,'Figure width')
  for ext in ['pdf','svg','_600dpi.png','_600dpi.tiff','_preview.png']:
   p=out/'figures'/folder/(name+ext if ext.startswith('_') else name+'.'+ext);require(p.is_file(),'Missing '+str(p))
  for ext in ['png','tiff']:
   with Image.open(out/'figures'/folder/f'{name}_600dpi.{ext}') as im:
    require(im.mode=='RGB' and min(im.info.get('dpi',(0,0)))>599,'RGB600dpi '+name)
    require(all(abs(px-mm/25.4*600)<2 for px,mm in zip(im.size,meta['physical_mm'])),'Native pixels '+name)
    if ext=='tiff':require(im.info.get('compression')=='tiff_lzw','LZW TIFF '+name)
  for t in json.loads((out/'quality'/f'{name}_text_extents.json').read_text()):
   if min(t['x0'],t['y0'])<-.002 or max(t['x1'],t['y1'])>1.002:bounds.append({'figure':name,**t})
 require(not bounds,'Clipped text '+str(bounds))
 checks['6 native figure families, vector/RGB/TIFF']=True;checks['all measured text inside pages']=True
 dump(out/'quality/numerical_checks.json',{'status':'IN_PROGRESS'})
 links=check_links(out);dump(out/'quality/link_audit.json',{'status':'PASS','links':links,'scope':'active reading documents; archived source text is .source.txt'})
 report={'status':'PASS','checks':checks,'check_count':len(checks),'links':len(links),'new_simulations':0,'limits':['No causal or dependence-robust CI','ED manuscript-global collision explicitly pending; local ED3/4 respected','Original manuscript Word not overwritten']};dump(out/'quality/numerical_checks.json',report);return report

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parent.parent);args=parser.parse_args();r=validate(args.root.resolve());print('Validation PASS:',r['check_count'],'checks;',r['links'],'active links')
