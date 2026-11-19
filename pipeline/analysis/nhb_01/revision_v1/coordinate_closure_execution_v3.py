"""Continue the already-running work through full A/B/C, no automatic acceptance."""
import json
from pathlib import Path
import subprocess
import sys
import time
from local_recall import MODULE, require, pin, write_json
from closure_execution_v3 import OUT

def completed_initial():
    for m in ('a','b'):
        paths=list((OUT/f'model_{m}_closure_v3.artifacts').glob('*/run_manifest.json'))
        if not paths or any(json.loads(p.read_text()).get('status')=='running' for p in paths): return False
    return True

def run(script,*args):
    r=subprocess.run([sys.executable,str(MODULE/script),*map(str,args)])
    require(r.returncode in (0,1) if script.startswith('closure_execution') else r.returncode==0,'Stage failed: '+script)

def main():
    write_json(OUT/'coordinator_plan.json',{'schema':'closure-automatic-continuation-v3','pins':[pin(Path(__file__)),pin(MODULE/'closure_execution_v3_1.py'),pin(MODULE/'finish_closure_execution_v3.py')],
       'automatic_semantic_acceptance':False,'paid_cap_and_each_budget_binding':True})
    print('Coordinator active: waiting for stable A/B and public evidence; then freeze remaining inputs, A/B, C, verification/report.',flush=True)
    while not completed_initial() or not (MODULE/'evidence_closure_public_bodies_v5/run_manifest.json').is_file(): time.sleep(20)
    run('prepare_closure_inputs_v3.py')
    source=MODULE/'evidence_closure_api_inputs_v3/closure586_model_inputs.jsonl'
    print('Dispatching remaining A/B; original runner skips prior attempted stable records.',flush=True)
    procs=[subprocess.Popen([sys.executable,str(MODULE/'closure_execution_v3_1.py'),m,'--input',str(source)]) for m in ('a','b')]
    require(all(p.wait() in (0,1) for p in procs),'Remaining A/B stage failed')
    run('finish_closure_execution_v3.py','--route-c')
    c_input=OUT/'c_route_v3/model_c_inputs.jsonl'
    if c_input.stat().st_size: run('closure_execution_v3_1.py','c','--input',c_input)
    run('finish_closure_execution_v3.py')
    print('API pipeline finished and verified. Evidence review / user acceptance still required before merging.',flush=True)

if __name__=='__main__': main()
