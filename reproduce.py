#!/usr/bin/env python3
"""Run one manuscript figure in a fresh working copy. No API calls or model refits."""
from pathlib import Path
import argparse,sys,json,shutil,subprocess,time,hashlib,os
ROOT=Path(__file__).resolve().parent

def digest(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def run(item,out,timeout=240):
 if out.exists():raise FileExistsError('Output must be a new directory: '+str(out))
 out.parent.mkdir(parents=True,exist_ok=True)
 src=ROOT/item['path'];shutil.copytree(src,out,ignore=shutil.ignore_patterns('__pycache__','scratch','*.png'))
 # Remove reference outputs from the work copy so a stale PDF cannot masquerade as a successful redraw.
 for f in (out/'figures').glob('*'):
  if f.is_file():f.unlink()
 for d in ['figures','validation','scratch','captions','text']:(out/d).mkdir(exist_ok=True)
 (out.parent/'Review.html').touch(exist_ok=True) if not (out.parent/'Review.html').exists() else None
 inputs={str(f.relative_to(out)):digest(f) for f in (out/'source_data').rglob('*') if f.is_file()}
 env=os.environ.copy();env.update(MPLCONFIGDIR=str(out/'scratch/mpl'),OPENBLAS_NUM_THREADS='2',OMP_NUM_THREADS='2',VECLIB_MAXIMUM_THREADS='2')
 start=time.monotonic();log=out/'execution.log'
 with log.open('w') as f:
  try:r=subprocess.run([sys.executable,str(out/item['script']),*item.get('arguments',[])],cwd=out,env=env,stdout=f,stderr=subprocess.STDOUT,timeout=timeout);rc=r.returncode
  except subprocess.TimeoutExpired:rc=124
 pdfs=[p for p in out.rglob('*.pdf') if 'source_data' not in p.parts]
 changed=[p for p,h in inputs.items() if not (out/p).exists() or digest(out/p)!=h]
 report={'id':item['id'],'returncode':rc,'seconds':round(time.monotonic()-start,3),'pdf_outputs':[str(p.relative_to(out)) for p in pdfs],'input_files_rewritten_in_work_copy':changed,'upstream_analysis_rerun':False,'primary_pdf':item.get('primary_pdf'), 'status':'passed' if rc==0 and pdfs and (not item.get('primary_pdf') or (out/item['primary_pdf']).is_file()) else 'failed'}
 (out/'run_report.json').write_text(json.dumps(report,indent=2));return report

def main():
 p=argparse.ArgumentParser();sub=p.add_subparsers(dest='action',required=True);sub.add_parser('list');r=sub.add_parser('redraw');r.add_argument('figure');r.add_argument('--output',type=Path,required=True);r.add_argument('--timeout',type=int,default=240);sub.add_parser('verify')
 a=p.parse_args();items=json.loads((ROOT/'manifests/figure_index.json').read_text())
 if a.action=='list':
  for s in items: print(s['id'],s['method'],s['module'],s['path'])
 elif a.action=='verify':
  m=ROOT/'manifests/code_checksums.json'
  if not m.exists():raise SystemExit('Checksum manifest has not yet been generated.')
  bad=[row['path'] for row in json.loads(m.read_text()) if not (ROOT/row['path']).exists() or digest(ROOT/row['path'])!=row['sha256']]
  print(json.dumps({'verified':not bad,'mismatches':bad},indent=2));return bool(bad)
 else:
  item=next((s for s in items if s['id'].lower()==a.figure.lower()),None)
  if item is None:raise SystemExit('Unknown figure; use list.')
  report=run(item,a.output.resolve(),a.timeout);print(json.dumps(report,indent=2));return report['status']!='passed'
 return 0
if __name__=='__main__':raise SystemExit(main())
