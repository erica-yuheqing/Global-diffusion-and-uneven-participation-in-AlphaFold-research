"""Numerical, source, source-coordinate and portable-link verification (offline)."""
from common import *
import re,os
import pyarrow.parquet as pq
from PIL import Image
def main():
 checks=[]
 def check(name,ok,detail=None):
  require(bool(ok),name+': '+str(detail));checks.append(dict(check=name,status='PASS',detail=detail))
 # Establish target before link validation (report links are intentionally self-referential).
 dump(Q/'validation_report.json',{'status':'VALIDATING','semantic_gold_certified':False})
 prov=json.loads((I/'provenance.json').read_text())
 for x in prov['inputs']:
  f=P/x['file'];check('input_hash_'+f.name,f.stat().st_size==x['bytes'] and sha(f)==x['sha256'])
 inst=pd.read_parquet(I/'institutions.parquet');b=inst[inst.baseline_eligible];check('fixed_48010_68',len(b)==48010 and b.country.nunique()==68);check('fixed_group_counts',b.groupby('group').size().to_dict()=={'L':17602,'M':14720,'H':15688})
 c=con();view(c,'p',D/'paper_metrics.parquet');view(c,'e',I/'citation_edges.parquet');view(c,'a',D/'matched_comparisons.parquet');view(c,'q',D/'study_roster_quality.parquet');view(c,'node',D/'networks/baseline_B2/nodes.parquet');view(c,'si',D/'study_institutions_all.parquet')
 check('study_metrics_unique',c.execute('SELECT count(*)=count(DISTINCT study_id) FROM p').fetchone()[0]);check('incoming_edges_unique',c.execute('SELECT count(*)=count(DISTINCT(citing_study_id,study_id)) FROM e').fetchone()[0]);check('study_affiliations_unique',c.execute('SELECT count(*)=count(DISTINCT(study_id,institution_id)) FROM si').fetchone()[0]);check('quarantine_not_zero',c.execute('SELECT count(*) FROM p WHERE citation_status IS NOT NULL AND citations_12m IS NOT NULL AND study_id IN (SELECT study_id FROM read_parquet('+lit(D/'citation_quality.parquet')+') WHERE quarantined)').fetchone()[0]==0)
 check('actual_window_count_reconstruction',c.execute('''SELECT count(*) FROM p LEFT JOIN (SELECT p.study_id,count(*) FILTER(WHERE e.citing_study_id<>p.study_id AND e.citing_publication_date>=p.publication_date AND e.citing_publication_date<p.publication_date+INTERVAL 12 MONTH) n12,count(*) FILTER(WHERE e.citing_study_id<>p.study_id AND e.citing_publication_date>=p.publication_date AND e.citing_publication_date<p.publication_date+INTERVAL 24 MONTH AND e.citing_publication_date<=DATE '2025-12-31') n24 FROM p JOIN e USING(study_id) GROUP BY 1) n USING(study_id) WHERE (p.citations_12m IS NOT NULL AND p.citations_12m<>coalesce(n.n12,0)) OR (p.citations_24m IS NOT NULL AND p.citations_24m<>coalesce(n.n24,0))''').fetchone()[0]==0)
 view(c,'old',I/'study_metrics_v1.parquet');check('citation_metrics_reconcile_v1',c.execute('''SELECT count(*) FROM p JOIN old USING(study_id) WHERE p.citations_12m IS DISTINCT FROM old.citations_12m OR p.percentile_12m IS DISTINCT FROM old.percentile_12m OR p.citations_24m IS DISTINCT FROM old.citations_24m OR p.percentile_24m IS DISTINCT FROM old.percentile_24m''').fetchone()[0]==0)
 pri=pd.read_csv(T/'primary_estimates.csv');expect={'journal_full2025':{'L':(121,197),'M':(576,771),'H':(5202,11077)},'citation_max':{'L':(45,68),'M':(269,305),'H':(3735,5392)}}
 for sample,groups in expect.items():
  metric='journal_position' if sample.startswith('journal') else 'percentile_12m';z=pri[pri.sample_id.eq(sample)&pri.metric.eq(metric)];raw=pd.read_parquet(D/f'AF_records_{sample}.parquet');units=pd.read_parquet(D/f'institutions_{sample}.parquet');draws=pd.read_parquet(D/f'draws_{sample}.parquet')
  for group,(n,af) in groups.items():
   r=z[z.group.eq(group)].iloc[0];b=raw[raw.group.eq(group)];check('primary_support_'+sample+group,int(r.n_institutions)==n and int(r.n_af_works)==af and b.institution_id.nunique()==n and b.study_id.nunique()==af)
   u=units[units.group.eq(group)];check('primary_point_'+sample+group,np.isclose(u['delta_'+metric].mean(),r.estimate,atol=1e-10))
   vv=draws[draws.group.eq(group)&draws.metric.eq(metric)].delta;check('primary_CI_'+sample+group,len(vv)==5000 and np.allclose(vv.quantile([.025,.975]),[r.lower,r.upper],atol=1e-10))
 for outcome in ['journal','citation']:
  marker=json.loads((Q/f'network_models_{outcome}.json').read_text());check('all_adjusted_5000_'+outcome,all((lambda vv:len(vv)==5000 and np.isfinite(vv).all())(np.load(D/f'model_draws/{outcome}_{m["name"]}.npz')['values']) for m in marker['adjusted_models']))
  for kind in ['own','partner']:
   x=pd.read_parquet(D/f'network_records_{outcome}_degree_{kind}.parquet');pt=pd.read_parquet(D/f'network_points_{outcome}_degree_{kind}.parquet');check('point_ID_and_keys_'+outcome+kind,pt.institution_id.nunique()==len(pt) and set(x.institution_id)==set(pt.institution_id))
   check('point_unique_AF_'+outcome+kind,pt.set_index('institution_id').n_AF.equals(x.groupby('institution_id').study_id.nunique().reindex(pt.institution_id).set_axis(pt.institution_id)))
   if kind=='partner':check('partner_gate_'+outcome,(x.n_other_institutions>0).all() and x.coverage.eq(1).all() and x.observed_author_roster_covered.all() and x.focal_in_roster.all() and x.n_unknown_baseline.eq(0).all() and x.n_outside_boundary.eq(0).all())
  # Direct same-P-and-D point reconstruction and institution row weights.
  from network_analysis import Bundle
  bundle=Bundle(outcome);f=pd.read_parquet(D/f'network_records_{outcome}_degree_partner.parquet');pt=pd.read_parquet(D/f'network_points_{outcome}_degree_partner.parquet');f['D_reconstructed']=bundle.point['default'][1][f.af_row.to_numpy(int),0];agg=f.groupby('institution_id')[['D_reconstructed','partner_mean_percentile']].mean().reindex(pt.institution_id);check('same_AF_for_P_D_'+outcome,np.allclose(agg.D_reconstructed,pt.D_i) and np.allclose(agg.partner_mean_percentile,pt.x))
  diag=pd.read_parquet(D/f'model_diagnostics_{outcome}_M2.parquet');diag1=pd.read_parquet(D/f'model_diagnostics_{outcome}_M1_partner_sample.parquet');check('M1_M2_identical_keys_'+outcome,set(zip(diag.study_id,diag.institution_id))==set(zip(diag1.study_id,diag1.institution_id)));check('model_institution_weights_'+outcome,np.allclose(diag.groupby('institution_id').institution_normalized_weight.sum(),1))
  results=pd.read_csv(T/f'network_results_{outcome}.csv');metric='journal_position' if outcome=='journal' else 'percentile_12m'
  for kind in ['own','partner']:
   for group in ['L','M','H']:
    path=D/f'model_draws/{outcome}_degree_{kind}_{group}_{metric}.npz';vv=np.load(path)['values'];q=np.quantile(vv[:,1],[.025,.975]);r=results[results.sample_id.eq('degree_'+kind)&results.group.eq(group)&results.metric.eq(metric)&results.coefficient.eq('slope')].iloc[0];check('network_slope_interval_'+outcome+kind+group,np.isfinite(vv).all() and len(vv)==5000 and np.allclose(q,[r.lower,r.upper]))
  del bundle
 for path in (D/'networks').iterdir():
  audit=json.loads((path/'audit.json').read_text());n=pd.read_parquet(path/'nodes.parquet');view(c,'edges',path/'edges.parquet');check('no_self_duplicate_edges_'+path.name,c.execute('SELECT count(*)=count(DISTINCT(institution_u,institution_v)) AND count(*) FILTER(WHERE institution_u=institution_v)=0 FROM edges').fetchone()[0]);check('unknown_not_isolate_'+path.name,n.loc[n.baseline_n_studies.eq(0),['degree','degree_percentile']].isna().all().all());check('known_nodes_have_scores_'+path.name,n.loc[n.baseline_n_studies.gt(0),'degree'].notna().all())
 for year in [2024,2025]:
  z=pd.read_csv(T/f'coverage_country_group_{year}.csv');check('fixed_204_cells_'+str(year),len(z)==204 and z.baseline_denominator.sum()==48010 and z.country.nunique()==68);check('bounds_order_'+str(year),all((z[e+'_lower']<=z[e+'_upper']).all() for e in ['af','venue','citation']))
 # Each logical contract has measured column/key validation, not merely a template flag.
 contracts=json.loads((Q/'logical_contract_schema_audit.json').read_text());check('12_logical_contracts',len(contracts)==12 and all(z['required_columns_present'] and z['key_duplicate_groups']==0 for z in contracts))
 reg=pd.read_csv(P/'specification/registry/panel_registry.csv',encoding='utf-8-sig');status=json.loads((Q/'panel_status.json').read_text());check('56_registered_states',len(status)==56 and set(zip(reg.figure_id,reg.panel_id))=={(x['figure_id'],x['panel_id']) for x in status})
 pngs=[];links=0
 for item in status:
  folder=P/item['source_data'];line=json.loads((folder/'lineage.json').read_text());check('panel_files_'+folder.name,all((folder/f).is_file() for f in ['summary.csv','coordinates.csv','records_index.csv','lineage.json']))
  for source in line['inputs']+line.get('additional_inputs',[]):
   f=(folder/source['path']).resolve();check('panel_source_'+folder.name+'_'+f.name,f.is_relative_to(P.resolve()) and f.exists() and sha(f)==source['sha256'])
  data=pd.read_csv(folder/'coordinates.csv')
  if item['status']=='completed':
   level=reg[(reg.figure_id==item['figure_id'])&(reg.panel_id==item['panel_id'])].level.iloc[0]
   for ext in ['pdf','svg','png']:check('panel_format_'+folder.name+ext,(P/f'figures/{level}/panels/{folder.name}.{ext}').is_file())
   check('nonempty_panel_coordinates_'+folder.name,len(data)>0)
  else:check('no_fake_unavailable_coordinates',len(data)==0 and item['figure_id']=='S_SI4' and item['panel_id']=='d')
 for f in (P/'figures').rglob('*.png'):
  with Image.open(f) as im:check('PNG_'+str(f.relative_to(P)),im.mode=='RGBA' and im.getextrema()[3]==(255,255) and min(im.info.get('dpi',(0,0)))>=299 or im.mode=='RGB' and min(im.info.get('dpi',(0,0)))>=299)
 for f in P.rglob('*.md'):
  for href in re.findall(r'\]\(([^)]+)\)',f.read_text(errors='replace')):
   href=href.strip('<>').split('#')[0]
   if not href or href.startswith(('https:','http:','mailto:')):continue
   target=(f.parent/href).resolve();require(target.is_relative_to(P.resolve()) and target.exists(),'Broken/nonportable Markdown link: '+str(f.relative_to(P))+' '+href);links+=1
 vals=json.loads((P/'manuscript/results_values.json').read_text());check('result_key_count',len(vals)==39)
 for key,value in vals.items():
  if key.startswith(('fig6a.','fig6b.')):
   r=pri[pri.sample_id.eq(value['sample_id'])&pri.group.eq(value['group'])&pri.metric.eq(value['metric'])];check('stable_key_'+key,len(r)==1 and np.isclose(r.estimate.iloc[0],value['estimate'],atol=1e-12))
 check('all_nine_tables',all((T/f'T_SI{k}.csv').exists() for k in range(1,10)));check('six_notes',all((P/f'supplementary/N_SI{k}.md').exists() for k in range(1,7)));check('supplement_PDF',(P/'supplementary/supplementary_v2.0.pdf').exists())
 report={'status':'PASS','checks':checks,'n_checks':len(checks),'relative_markdown_links':links,'main_or_registered_panels':56,'completed_registered_panels':55,'unavailable_panel':'S_SI4d','semantic_gold_certified':False,'publisher_roster_completeness_certified':False,'causal_effects_certified':False,'journal_editorial_acceptance_certified':False,'api_calls':0,'verified_utc':utc()};dump(Q/'validation_report.json',report);print('V2 NUMERICAL/SOURCE/LINK QA PASS:',len(checks),'checks;',links,'portable MD links',flush=True)
if __name__=='__main__':main()
