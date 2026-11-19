"""Read-only cumulative pilot progress/usage. Unknown cost is never zero."""
import json
from collections import Counter
from evidence_closure_api_v1 import OUTPUTS, read_jsonl


def model_status(model):
    path=OUTPUTS/f'model_{model}_smoke20_v1.jsonl'
    results=read_jsonl(path) if path.is_file() else []
    error_path=path.with_name(path.stem+'.errors.jsonl')
    errors=read_jsonl(error_path) if error_path.is_file() else []
    journal=path.with_name(path.stem+'.attempts.jsonl')
    # The writer may be appending a last line. Only ignore that last partial
    # line in this live status helper; archive verification is always strict.
    events=[]
    if journal.is_file():
        lines=journal.read_text().splitlines()
        for i,line in enumerate(lines):
            if not line.strip():continue
            try:events.append(json.loads(line))
            except json.JSONDecodeError:
                if i!=len(lines)-1:raise
    started=[r for r in events if r.get('event')=='request_started']
    finished=[r for r in events if r.get('event')=='request_finished']
    totals=Counter()
    for row in finished:totals.update(row.get('normalized_usage') or {})
    costs=[r['usage']['cost'] for r in finished if isinstance(r.get('usage',{}).get('cost'),(int,float))]
    return {'model':model,'validated_outputs':len(results),'failed_records':len(errors),
            'http_started':len(started),'http_finished':len(finished),
            'reported_token_totals':dict(totals),
            'reported_cost_usd':sum(costs) if costs else None,
            'cost_reporting_complete':len(costs)==len(started) and bool(started),
            'billing_note':'No currency inferred from token totals; consult provider billing for missing cost.',
            'semantic_acceptance':False}


if __name__=='__main__':
    print(json.dumps([model_status(m) for m in ('a','b','c')],ensure_ascii=False,indent=2))
