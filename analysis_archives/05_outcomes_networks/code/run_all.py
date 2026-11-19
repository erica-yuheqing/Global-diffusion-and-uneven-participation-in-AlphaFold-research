"""Offline reproduction from bundled frozen inputs, preserving cached draws."""
from common import *
import subprocess,sys,os
def main():
 for folder in [D,T,Q,P/'scratch',P/'manuscript',P/'captions',P/'supplementary']:folder.mkdir(parents=True,exist_ok=True)
 for x in json.loads((I/'provenance.json').read_text())['inputs']:require(sha(P/x['file'])==x['sha256'],'Input changed: '+x['file'])
 stages=[('metrics.py',D/'paper_metrics.parquet'),('rosters.py',D/'study_roster_quality.parquet'),('build_comparisons.py',D/'matched_comparisons.parquet'),('networks.py',Q/'network_audit.json'),('partners.py',Q/'partner_audit.json'),('outcomes.py',Q/'outcome_audit.json'),('strata.py',Q/'strata_audit.json'),('network_analysis.py',None),('network_diagnostics.py',None),('data_tables.py',Q/'data_tables_audit.json'),('contracts.py',None),('figures.py',None),('figure_details.py',None),('documents.py',None)]
 for name,cache in stages:
  if cache is not None and cache.exists():print('Reusing frozen intermediate:',name,flush=True);continue
  subprocess.run([sys.executable,str(P/'code'/name)],check=True)
 pdf_python=os.environ.get('PDF_PYTHON',sys.executable);subprocess.run([pdf_python,str(P/'code/render_supplement.py')],check=True)
 subprocess.run([sys.executable,str(P/'code/verify.py')],check=True)
 print('OFFLINE REPRODUCTION/QA COMPLETE; packaging is code/package.py',flush=True)
if __name__=='__main__':main()
