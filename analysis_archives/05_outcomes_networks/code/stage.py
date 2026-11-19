"""Versioned local input staging; no credentials, requests or older-output edits."""
import shutil,sys
from common import *
ROOT=Path('/historical-workspace/projects/IGN/AlphaFoldResearch')
OLD=ROOT/'analysis/nhb_05/finding5_plan_v7/Scientific_Influence_analysis_v1.0'
SPEC=Path('/historical-workspace/projects/IGN/revision/finding5-revision-plan-v8')
def main():
 require(not (I/'provenance.json').exists(),'Inputs already staged; do not silently overwrite')
 for folder in ['inputs','source_data','tables','qa','code','cases','specification','manuscript','captions','supplementary','scratch','figures/main','figures/extended','figures/supplementary']:(P/folder).mkdir(parents=True,exist_ok=True)
 manifest=json.loads((SPEC/'manifest.json').read_text())
 for row in manifest['files']:
  f=SPEC/row['path'];require(f.stat().st_size==row['bytes'] and sha(f)==row['sha256'],'Specification changed: '+str(f))
 shutil.copytree(SPEC,P/'specification',dirs_exist_ok=True)
 mappings={
  **{name:'inputs/'+name for name in ['paper_base.parquet','institutions.parquet','work_institutions.parquet','approved_crosswalk.parquet','activities.parquet','authorships.parquet','author_affiliations.parquet','journal_year_positions.parquet','journal_category_positions.parquet','parent_fields.parquet']},
  'citation_edges.parquet':'source_data/citation_edges.parquet',
  'citation_quality_exclusions.parquet':'source_data/citation_quality_exclusions.parquet',
  'batch_status.parquet':'source_data/batch_status.parquet',
  'study_metrics_v1.parquet':'source_data/paper_metrics.parquet'}
 records=[]
 for name,source in mappings.items():
  origin=OLD/source;dst=I/name;shutil.copyfile(origin,dst);digest=sha(origin);require(sha(dst)==digest,'Copy differs: '+name)
  records.append({'file':'inputs/'+name,'source':str(origin),'bytes':dst.stat().st_size,'sha256':digest})
 shutil.copytree(OLD/'cases',P/'cases',dirs_exist_ok=True)
 shutil.copyfile(OLD/'qa/validation_report.json',I/'upstream_v1_validation.json')
 shutil.copyfile(OLD/'environment.lock',P/'environment.lock')
 for name in ['bootstrap.py','build_comparisons.py']:
  shutil.copyfile(OLD/'code'/name,P/'code'/name)
 # The reference-percentile function is unchanged; the old network/collection
 # runner is retained as provenance and is never called.
 shutil.copyfile(OLD/'code/build_metrics.py',P/'code/upstream_metrics.py')
 cfg=json.loads((SPEC/'config/analysis_config.template.json').read_text())
 cfg['status']='execution_frozen_before_new_network_coefficients';cfg['frozen_utc']=utc();cfg['actual_input_availability']='verified_local_copies_with_hashes'
 cfg['network']['boundary_decision']='Finding4 v7 explicitly did not build centrality; use default B2 induced graph; expanded boundary separate'
 cfg['network']['fractional_m']='distinct institutions inside this network boundary; full roster m_all retained separately'
 cfg['network']['large_team_m']='all observed institutions before boundary projection'
 cfg['network']['record_quality']='observed roster; publisher/truncation completeness not collected and not certified'
 cfg['network']['conservative_sensitivity']='all observed authors have non-null IDs and >=1 institution; not publisher certification'
 cfg['partner']['main_observed_roster_rule']='all observed author IDs assigned, all observed distinct partners scored; source roster completeness remains unverified'
 cfg['partner']['certified_publisher_roster_branch']='not_computable unless real completeness flag recovered'
 cfg['models']['high_leverage_rule']='weighted hat diagonal > 2*rank/n_links; diagnostic removal only, no main-sample deletion'
 cfg['models']['category_rule']='observed levels within frozen model sample; treatment coding; numeric prespecified variables retained; rank failure not repaired after coefficients'
 cfg['models']['leave_one_country']='omit focal-country outcome records, keep baseline network fixed'
 cfg['dates']['database_retrieved_at']='metadata week containing 2026-04-03; incoming citations 2026-10-30_to_31'
 dump(P/'analysis_config.frozen.json',cfg)
 dump(I/'provenance.json',{'staged_utc':utc(),'source_specification_version':'2.0','inputs':records,'paid_API_calls_this_execution':0,'original_inputs_modified':False})
 for f in Path(__file__).parent.glob('*.py'):
  if f.resolve()!=(P/'code'/f.name).resolve():shutil.copyfile(f,P/'code'/f.name)
 print('V8 INPUTS STAGED',len(records),'frozen inputs; no APIs; main roster quality explicitly unverified',flush=True)
if __name__=='__main__':main()
