"""Bounded pilot wrapper around the unchanged original core review runner."""
import argparse
import subprocess
import sys
from evidence_closure_api_v1 import INPUTS, OUTPUTS, PROMPT, SCHEMA, RUNNER, PROFILES, verify_inputs


def command(model,cap,workers,resume=False,dry_run=False):
    verify_inputs()
    profile=PROFILES[model]
    source=INPUTS/('smoke20_model_inputs.jsonl' if model in ('a','b') else 'smoke20_c_inputs.jsonl')
    if model=='c':
        from compare_evidence_closure_api_v1 import verify_c_route
        verify_c_route()
        source=OUTPUTS/'comparison_v1/smoke20_c_inputs.jsonl'
    args=[sys.executable,str(RUNNER),'--input',str(source),'--prompt',str(PROMPT),'--schema',str(SCHEMA),
          '--output',str(OUTPUTS/f'model_{model}_smoke20_v1.jsonl'),'--all',
          '--max-api-calls',str(cap),'--workers',str(workers),'--timeout','600',
          '--http-retries','0','--validation-retries','0','--max-output-tokens','20000']
    for key,value in profile.items():args.extend(['--'+key.replace('_','-'),value])
    if resume:args.append('--resume')
    if dry_run:args.append('--dry-run')
    return args


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('model',choices=tuple(PROFILES));p.add_argument('--max-api-calls',type=int,default=20)
    p.add_argument('--workers',type=int,default=2);p.add_argument('--resume',action='store_true')
    p.add_argument('--dry-run',action='store_true');a=p.parse_args()
    if not 1<=a.max_api_calls<=20 or not 1<=a.workers<=4:p.error('Pilot only: cap 1–20; workers 1–4')
    raise SystemExit(subprocess.call(command(a.model,a.max_api_calls,a.workers,a.resume,a.dry_run)))


if __name__=='__main__':main()
