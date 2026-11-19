"""One local entry point for verification or nondestructive replay in a fresh directory."""
from pathlib import Path
import argparse,subprocess,shutil,sys,os
ROOT=Path(__file__).resolve().parents[1]
def main():
    p=argparse.ArgumentParser();p.add_argument('--rebuild-to',type=Path);p.add_argument('--redraw',action='store_true');a=p.parse_args()
    env=dict(os.environ,OPENBLAS_NUM_THREADS='2',VECLIB_MAXIMUM_THREADS='2')
    if a.rebuild_to:
      target=a.rebuild_to.expanduser().resolve()
      if target.exists():raise ValueError('Replay destination must not exist; original outputs are never cleared')
      target.mkdir(parents=True)
      for name in ['inputs','code']:shutil.copytree(ROOT/name,target/name,ignore=shutil.ignore_patterns('__pycache__','*.dylib'))
      for name in ['tables','figures','draws','manuscript','source_data','provenance','scratch']:(target/name).mkdir()
      for n in ['N01_complete.json','input_pins.json','original_handoff_manifest.json','external_raw_input_manifest.json','input_catalog.json','accepted_scope_change.json','figure5_authority_addendum.json','runtime.json']:
        shutil.copy2(ROOT/'provenance'/n,target/'provenance'/n)
      shutil.copy2(ROOT/'analysis_config.json',target/'analysis_config.json')
      # N01 raw reconstruction has separate upstream dependencies; its normalized
      # snapshot is frozen. Rebuild all subsequent analysis from that snapshot.
      for name in ['study_eligibility.parquet','legacy_same_author_role_exclusions.csv','N01_credit_differences.csv','pairing_study_ids_and_weights.csv']:
        if (ROOT/'tables'/name).exists():shutil.copy2(ROOT/'tables'/name,target/'tables'/name)
      for n in ['country_pair_credit','country_pair_expected','role_country_institution_credit','author_group_memberships','study_structure','analysis_members','conditional_reference_studies','institution_zero_entities']:
        f=target/'inputs/normalized'/(n+'.parquet')
        if f.exists():f.unlink() # Only derived copies in this newly created replay directory.
      commands=['features','bootstrap','sensitivity','reference','ancillary','refinements','country_uncertainty','contract','draw','report']
      for n in commands:subprocess.run([sys.executable,str(target/'code'/(n+'.py'))],check=True,env=env)
      import json
      (target/'provenance/visual_review.json').write_text(json.dumps(dict(status='AUTHOR_INSPECTION_REQUIRED',scope='New automatic replay does not inherit the original release manual visual review; inspect regenerated figures.'),indent=2)+'\n')
      for n in ['tests','validate']:subprocess.run([sys.executable,str(target/'code'/(n+'.py'))],check=True,env=env)
    else:
      if a.redraw:subprocess.run([sys.executable,str(ROOT/'code/draw.py')],check=True,env=env)
      for n in ['tests','validate']:subprocess.run([sys.executable,str(ROOT/'code'/(n+'.py'))],check=True,env=env)
if __name__=='__main__':main()
