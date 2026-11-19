"""Verify all new provider archives and assemble unaccepted incremental proposals."""
from collections import Counter
import json
from pathlib import Path
import subprocess
import sys
from jsonschema import Draft202012Validator
from evidence_closure_api_v1 import read_jsonl, fingerprint, PROFILES, SCHEMA, RUNNER
from compare_evidence_closure_api_v1 import route, CORE
from local_recall import MODULE, ROOT, destination, pin, sha, write_json, write_csv, require
from fetch_public_evidence import inventory
from prepare_evidence_closure_api_v1 import write_jsonl
from closure_execution_v3 import OUT, Ledger

INPUT=MODULE/'evidence_closure_api_inputs_v3/closure586_model_inputs.jsonl'
REPORT=MODULE/'evidence_closure_result_review_v3'

def load(model,packets):
    p=OUT/f'model_{model}_closure_v3.jsonl'
    manifests=sorted(p.with_name(p.stem+'.artifacts').glob('*/run_manifest.json'))
    historical=[]; pins=[]
    for mp in manifests:
        subprocess.run([sys.executable,str(ROOT/'code/10_verify_model_run_artifact.py'),str(mp.parent)],check=True)
        m=json.loads(mp.read_text()); entry=m['archived_records'].get('validated')
        if entry: historical+=read_jsonl(mp.parent/entry['snapshot_path'])
        pins.append(pin(mp)); pins.append(pin(mp.with_suffix('.json.sha256')))
    rows=read_jsonl(p) if p.exists() else []
    require(sorted(map(fingerprint,rows))==sorted(map(fingerprint,historical)),f'Cumulative {model} differs from archives')
    validator=Draft202012Validator(json.loads(SCHEMA.read_text()))
    import importlib.util
    spec=importlib.util.spec_from_file_location('verify_original_closure_engine',RUNNER); engine=importlib.util.module_from_spec(spec); spec.loader.exec_module(engine)
    results={}
    for r in rows:
        wid=r['work_id']; require(wid in packets and wid not in results,'Unknown/duplicate API result')
        require(r['input_packet_sha256']==fingerprint(packets[wid]),'Mixed evidence packet fingerprint')
        require(r['provider']==PROFILES[model]['provider'] and r['model']==PROFILES[model]['model'],'Model identity differs')
        require(r['run_signature']['prompt_sha256']==sha(MODULE.parents[2]/'config/af_review_prompt_v4.txt') and r['run_signature']['schema_sha256']==sha(SCHEMA),'Core prompt/schema differs')
        require(not engine.validate_review(r['response'],packets[wid],validator),'Current output validator refuses response')
        results[wid]=r
    if p.exists(): pins.append(pin(p))
    return results,pins

def c_route():
    packets=read_jsonl(INPUT); byid={p['work_id']:p for p in packets}
    a,ap=load('a',byid); b,bp=load('b',byid)
    selected=[]; records=[]
    for p in packets:
        if not p['model_eligible']: continue
        state,reasons=route(a.get(p['work_id']),b.get(p['work_id']))
        records.append({'work_id':p['work_id'],'route':state,'reasons':reasons})
        if state=='model_c_review': selected.append(p)
    out=destination(OUT/'c_route_v3'); out.mkdir(mode=0o700)
    write_jsonl(out/'model_c_inputs.jsonl',selected); write_json(out/'routes_private.json',records)
    write_json(out/'run_manifest.json',{'schema':'closure-c-routing-v3','inputs':ap+bp+[pin(INPUT)],
       'summary':{'eligible':sum(p['model_eligible'] for p in packets),'a_valid':len(a),'b_valid':len(b),'c_routed':len(selected),'observed_actions_excluded':True},'outputs':inventory(out)})
    print('C route frozen:',len(selected),'same-evidence records; answers not included',flush=True)

def report():
    packets=read_jsonl(INPUT); byid={p['work_id']:p for p in packets}
    results={}; pins=[]
    for m in PROFILES: results[m],pp=load(m,byid); pins+=pp
    source=json.loads((MODULE/'evidence_closure_api_inputs_v3/evidence_rows_private.json').read_text())
    prior={r['work_id']:r for r in source}; proposals=[]; comparison=[]
    for p in packets:
        wid=p['work_id']; a=results['a'].get(wid); b=results['b'].get(wid); c=results['c'].get(wid)
        state,reasons=route(a,b)
        choice=c or (a if a and b and state=='agreement_pending_semantic_check' else None)
        proposals.append({'work_id':wid,'review_id':prior[wid]['review_id'],
           'publication_year':prior[wid]['publication_year'],'input_packet_sha256':fingerprint(p),
           'model_eligible':p['model_eligible'],'evidence_tier':p['evidence_tier'],
           'prior_accepted_decision':prior[wid]['prior_accepted_decision'],
           'candidate_response':choice['response'] if choice else None,
           'candidate_source':'model_c' if c else ('AB_core_agreement' if choice else 'unresolved_no_valid_conclusion'),
           'candidate_artifact':choice['run_artifact'] if choice else None,
           'semantic_status':'pending_current_assistant_evidence_review_and_user_confirmation',
           'old_labels_overwritten':False})
        comparison.append({'work_id':wid,'review_id':prior[wid]['review_id'],'year':prior[wid]['publication_year'],
           'a_valid':bool(a),'b_valid':bool(b),'c_valid':bool(c),'route':state,'reasons':'|'.join(reasons),
           'suggested_use':choice['response']['af_use_label'] if choice else 'uncertain',
           'suggested_adoption':choice['response']['adoption_eligible'] if choice else 'uncertain',
           'suggested_R':choice['response']['relevance_level'] if choice else 'RU',
           'suggested_E':choice['response']['evidence_level'] if choice else '',
           'suggested_label':choice['response']['primary_label'] if choice else 'uncertain'})
    summary={'queue_works':len(packets),'api_valid_by_model':{m:len(r) for m,r in results.items()},
       'candidate_response_sources':dict(Counter(p['candidate_source'] for p in proposals)),
       'suggested_core_pairs':dict(Counter(r['suggested_use']+'/'+r['suggested_adoption'] for r in comparison)),
       'budget_ledger':Ledger().summary(),'accepted_new_labels':0,'old_database_changed':False,
       'deepseek_service_version_change_disclosed':True,'all_model_suggestions_not_human_gold':True,
       'status':'API and archive stage completed; semantic review/acceptance and integration remain pending'}
    destination(REPORT).mkdir(mode=0o700)
    write_json(REPORT/'candidate_proposals_private.json',proposals)
    write_csv(REPORT/'comparison_private.csv',comparison,list(comparison[0]))
    write_json(REPORT/'summary.json',summary)
    text='# 586项增量评审：API阶段汇总\n\n'+json.dumps(summary,ensure_ascii=False,indent=2)+'\n\n以上是模型候选建议，不是新接受层。缺少证据和无有效响应保留未知；原接受结果不覆盖。A保留原API名称，但服务端已更换为V4.1-Flash，已获用户同意并须在合并方法中披露。\n\n[逐项对照](comparison_private.csv) · [候选及原接受判定](candidate_proposals_private.json)\n'
    (REPORT/'results_zh.md').write_text(text); (REPORT/'results_zh.md').chmod(0o600)
    write_json(REPORT/'run_manifest.json',{'schema':'closure-incremental-api-proposals-v3','inputs':pins+[pin(INPUT),pin(Path(__file__))],
       'summary':summary,'outputs':inventory(REPORT)})
    print('Verified candidate report:',json.dumps(summary,ensure_ascii=False),flush=True)

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(); p.add_argument('--route-c',action='store_true'); a=p.parse_args()
    c_route() if a.route_c else report()
