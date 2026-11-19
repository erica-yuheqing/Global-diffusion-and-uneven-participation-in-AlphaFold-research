"""Budget guarded execution of the unchanged legacy reviewer, new archives only.

Extra guards wrap transport/accounting, not prompts, schema or decision rules.
Each real request is reserved durably before dispatch. Missing billing retains
the conservative reservation; failed model output still incurs its full charge.
"""
from contextlib import contextmanager
from decimal import Decimal
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import threading
from datetime import datetime, timezone

from local_recall import MODULE, ROOT, require, pin, sha, write_json
from evidence_closure_api_v1 import PROFILES, PROMPT, SCHEMA, RUNNER, read_jsonl, fingerprint

OUT=MODULE/'evidence_closure_execution_v3'
AUTH=MODULE/'evidence_closure_execution_authorization_v3.json'
PREFLIGHT=MODULE/'evidence_closure_budget_preflight_v1/summary.json'
PRICES={
 'a': {'input':Decimal('0.000002'),'output':Decimal('0.000008'),'currency':'CNY'},
 'b': {'input':Decimal('0.0000008'),'output':Decimal('0.0000028'),'currency':'CNY'},
 # Highest archived catalog tier, including cache-write and long-context
 # overrides. Intentionally more conservative than these short packet prices.
 'c': {'input':Decimal('0.0000005'),'output':Decimal('0.0000018'),'currency':'USD'},
}

def clock(): return datetime.now(timezone.utc).isoformat()

def bounds(body,model):
    p=PRICES[model]
    # Byte-level upper bound + framing allowance. JSON representation is larger
    # than model message text; reserve all input at the highest uncached/write rate.
    n=len(json.dumps(body,ensure_ascii=False).encode('utf-8'))+4096
    output=int(body.get('max_output_tokens',body.get('max_tokens',body.get('max_completion_tokens',20000))))
    require(0<output<=20000,'Output reservation cannot exceed original fixed cap')
    return (Decimal(n)*p['input']+Decimal(output)*p['output'])*Decimal('1.10')

def charged(payload,model,reserved):
    u=payload.get('usage')
    if not isinstance(u,dict): return reserved,'missing_usage_retained_full_reservation'
    if model=='c':
        cost=u.get('cost')
        if cost is None: return reserved,'missing_cost_retained_full_reservation'
        cost=Decimal(str(cost))
        require(cost.is_finite() and cost>=0,'Invalid cost')
        return max(cost,Decimal('0')),'provider_reported_usd'
    inp=u.get('prompt_tokens',u.get('input_tokens')); out=u.get('completion_tokens',u.get('output_tokens'))
    if isinstance(inp,bool) or isinstance(out,bool) or not isinstance(inp,int) or not isinstance(out,int) or inp<0 or out<0:
        return reserved,'missing_token_totals_retained_full_reservation'
    return (Decimal(inp)*PRICES[model]['input']+Decimal(out)*PRICES[model]['output'])*Decimal('1.10'),'conservative_peak_no_cache_discount_not_actual_bill'

class Ledger:
    def __init__(self,directory=OUT):
        self.directory=directory; directory.mkdir(mode=0o700,exist_ok=True)
        self.path=directory/'paid_request_ledger.jsonl'; self.lock_path=directory/'ledger.lock'
        self.auth=json.loads(AUTH.read_text())
        require(self.auth['aggregate_paid_http_send_cap']==5274 and self.auth['sample_count']==586,'Authorization cap differs')
        self.limits={k[-1]:Decimal(str(v['maximum_new_spend'])) for k,v in self.auth['budgets'].items()}
        self.thread_lock=threading.Lock()
    @contextmanager
    def locked(self):
        with self.thread_lock, self.lock_path.open('a') as f:
            self.lock_path.chmod(0o600); fcntl.flock(f,fcntl.LOCK_EX)
            try: yield
            finally: fcntl.flock(f,fcntl.LOCK_UN)
    def rows(self): return read_jsonl(self.path) if self.path.exists() else []
    def append(self,event):
        with self.path.open('a') as f:
            f.write(json.dumps(event,ensure_ascii=False,allow_nan=False)+'\n'); f.flush(); os.fsync(f.fileno())
        self.path.chmod(0o600)
    @staticmethod
    def accounting(rows):
        starts={r['number']:r for r in rows if r['event']=='reserved_dispatch'}
        finishes={r['number']:r for r in rows if r['event']=='settled'}
        totals={m:Decimal(0) for m in PRICES}
        for n,r in starts.items(): totals[r['model_key']]+=Decimal(finishes.get(n,r).get('accounted_cost',r['reservation']))
        return starts,finishes,totals
    def reserve(self,model,wid,body):
        reserve=bounds(body,model)
        with self.locked():
            rows=self.rows(); starts,finishes,totals=self.accounting(rows)
            require(len(starts)<self.auth['aggregate_paid_http_send_cap'],'Aggregate request cap reached')
            require(not any(r.get('over_reservation') for r in finishes.values()),'Billing exceeded reservation; stop for reconciliation')
            require(totals[model]+reserve<=self.limits[model],f'Model {model} monetary budget guard reached')
            n=max(starts,default=0)+1
            self.append({'event':'reserved_dispatch','number':n,'time_utc':clock(),'model_key':model,
                'work_id':wid,'reservation':str(reserve),'currency':PRICES[model]['currency'],
                'request_body_sha256':fingerprint(body)})
        return n,reserve
    def settle(self,n,model,reserve,payload,status):
        value,basis=charged(payload,model,reserve)
        with self.locked():
            self.append({'event':'settled','number':n,'time_utc':clock(),'model_key':model,
                'http_status':status,'accounted_cost':str(value),'basis':basis,
                'over_reservation':value>reserve,'reported_model':payload.get('model'),
                'usage':payload.get('usage',{})})
    def summary(self):
        with self.locked():
            starts,finishes,totals=self.accounting(self.rows())
            return {'paid_dispatched_or_reserved_requests':len(starts),'settled_requests':len(finishes),
               'conservative_budget_accounting':{k:str(v) for k,v in totals.items()},
               'limits':{k:str(v) for k,v in self.limits.items()},'request_cap':5274,
               'warning':'A/B accounting is a conservative ceiling, not provider reported expenditure; unsettled requests retain full reservation.'}

def command(model,source,output,ids,dry=False):
    a=[str(RUNNER),'--input',str(source),'--prompt',str(PROMPT),'--schema',str(SCHEMA),'--output',str(output),
       '--all','--max-api-calls',str(len(ids)),'--workers','4','--timeout','600','--http-retries','0',
       '--validation-retries','0','--max-output-tokens','20000']
    for k,v in PROFILES[model].items(): a+=['--'+k.replace('_','-'),v]
    for wid in ids: a+=['--work-id',wid]
    if output.exists() or output.with_name(output.stem+'.errors.jsonl').exists(): a+=['--resume']
    if dry: a+=['--dry-run']
    return a

def run_model(model,source,ids=None,dry=False):
    require(model in PROFILES,'Unknown model')
    if model=='a':
        approval=MODULE/'evidence_closure_deepseek_alias_acceptance_v1.json'
        require(approval.is_file() and json.loads(approval.read_text()).get('approved') is True,
                'DeepSeek service-version change requires user acceptance; no A dispatch')
    packets=read_jsonl(source)
    eligible={p['work_id'] for p in packets if p['model_eligible']}
    ids=ids or [p['work_id'] for p in packets if p['model_eligible']]
    require(set(ids)<=eligible and len(ids)==len(set(ids)),'Invalid/duplicate selected IDs')
    output=OUT/f'model_{model}_closure_v3.jsonl'
    # Do not turn automatic stage continuation into an unbounded retry loop.
    attempted=set()
    audit_path=output.with_name(output.stem+'.attempts.jsonl')
    if audit_path.exists(): attempted={r['work_id'] for r in read_jsonl(audit_path) if r.get('event')=='request_started'}
    ids=[w for w in ids if w not in attempted]
    if not ids: print(f'Model {model}: no not-yet-attempted selected records',flush=True); return
    spec=importlib.util.spec_from_file_location('legacy_closure_engine',RUNNER)
    engine=importlib.util.module_from_spec(spec); spec.loader.exec_module(engine)
    args=command(model,source,output,ids,dry)
    transport=engine.requests.post; original_review=engine.review_one; local=threading.local()
    ledger=None if dry else Ledger()
    def review(**kwargs):
        local.wid=kwargs['packet']['work_id']
        return original_review(**kwargs)
    def post(url,**kwargs):
        require(url==PROFILES[model]['endpoint'] and kwargs.get('allow_redirects') is False,'Unexpected paid endpoint/redirect')
        n,reserve=ledger.reserve(model,local.wid,kwargs['json'])
        payload={}; status=None
        try:
            response=transport(url,**kwargs); status=response.status_code
            try:
                data=response.json()
                if isinstance(data,dict): payload=data
            except ValueError: pass
            return response
        finally: ledger.settle(n,model,reserve,payload,status)
    oldargv=sys.argv
    try:
        sys.argv=args; engine.review_one=review
        if not dry: engine.requests.post=post
        code=engine.main()
        print(f'Model {model}: original runner exit {code}; no semantic acceptance',flush=True)
    finally:
        sys.argv=oldargv; engine.requests.post=transport
    if ledger: print('Budget ledger:',json.dumps(ledger.summary()),flush=True)

def main():
    import argparse
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('model',choices=('a','b','c'))
    p.add_argument('--input',type=Path,required=True); p.add_argument('--dry-run',action='store_true')
    a=p.parse_args(); run_model(a.model,a.input,dry=a.dry_run)

if __name__=='__main__': main()
