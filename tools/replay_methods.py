"""Replay selected manuscript methods offline into a new writable directory."""
from pathlib import Path
import argparse, json, shutil, subprocess, sys, os
ROOT=Path(__file__).resolve().parents[1]
def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('module',choices=['national','coverage','continuity','authorship','citations','ed8-bootstrap'])
 p.add_argument('--output',type=Path,required=True)
 a=p.parse_args(); out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
 src=ROOT/'analysis_archives'
 env=dict(os.environ,OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='2',VECLIB_MAXIMUM_THREADS='2',PYTHONDONTWRITEBYTECODE='1')
 def run(script,*args):
  subprocess.run([sys.executable,str(script),*map(str,args)],cwd=out,env=env,check=True)
 def init(name,links=()):
  base=src/name
  shutil.copytree(base/'code',out/'code')
  for name in links:(out/name).symlink_to(base/name,target_is_directory=True)
  for name in ['tables','quality','plot_data','qa','scratch','provenance','source_data']:
   if not (out/name).exists():(out/name).mkdir()
  return base
 if a.module=='national':run(ROOT/'tools/check_national_points.py','--analysis-root',src)
 if a.module=='coverage':
  base=init('02_coverage',['inputs'])
  run(out/'code/test_methods.py')
  subprocess.run([sys.executable,'-c','from pathlib import Path;from prepare import prepare;prepare(Path.cwd())'],cwd=out,env=dict(env,PYTHONPATH=str(out/'code')),check=True)
  run(out/'code/analytic_check.py',out)
 if a.module=='continuity':
  base=init('03_continuity',['source_inputs'])
  run(out/'code/prepare_plot_data.py')
  import csv
  for f in (out/'plot_data').glob('*.csv'):
   with f.open() as s,(base/'plot_data'/f.name).open() as t:
    if list(csv.reader(s))!=list(csv.reader(t)):raise ValueError(f'Frozen table differs: {f.name}')
  shutil.copy2(base/'provenance/local_linkage_pins.json',out/'provenance')
  run(out/'code/prepare_linkage.py')
 if a.module=='authorship':
  run(src/'04_authorship/code/tests.py')
 if a.module=='citations':
  init('05_outcomes_networks',['inputs'])
  run(out/'code/test_methods.py');run(out/'code/metrics.py')
 if a.module=='ed8-bootstrap':
  # ED8 uses study-level group matrices; refit the frozen 2,000 draws.
  base=ROOT/'figures/extended/ED08'
  for name in ['uncertainty.py','release_support.py','study_features.npz','analysis_provenance.json']:
   shutil.copy2(base/name,out/name)
  shutil.copy2(src/'04_authorship/ed8_analysis/cohort_audit.csv.gz',out)
  run(out/'uncertainty.py')
  import numpy as np
  with np.load(out/'bootstrap_group_matrices.npz') as fresh, np.load(base/'bootstrap_group_matrices.npz') as frozen:
   for k in ('AF','reference'):np.testing.assert_allclose(fresh[k],frozen[k],atol=1e-12,rtol=0)
 print(a.module,'OK')
if __name__=='__main__':main()
