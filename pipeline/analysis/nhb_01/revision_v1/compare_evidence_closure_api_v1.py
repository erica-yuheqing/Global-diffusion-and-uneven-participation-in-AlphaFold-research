"""Verify A/B pilot archives and route C without approving or merging labels."""
import argparse
from collections import Counter
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from jsonschema import Draft202012Validator

from evidence_closure_api_v1 import INPUTS, OUTPUTS, SCHEMA, RUNNER, PROFILES, verify_inputs, read_jsonl, fingerprint
from fetch_public_evidence import inventory
from local_recall import MODULE, ROOT, destination, pin, require, sha, write_csv, write_json

CORE=('af_use_label','adoption_eligible','relevance_level','evidence_level','primary_label','af_related_label')
OUT=OUTPUTS/'comparison_v1'


def route(a,b):
    reasons=[]
    if a is None or b is None: reasons.append('missing_valid_A_or_B')
    else:
        aa=a['response'];bb=b['response']
        if any(aa[k]!=bb[k] for k in CORE):reasons.append('core_disagreement')
        if any(r['af_use_label']=='uncertain' or r['adoption_eligible']=='uncertain' or r['relevance_level']=='RU' for r in (aa,bb)):
            reasons.append('uncertain_core')
        # Negative agreement also needs a safeguard: a general description of
        # another workflow is not proof of false-positive identity/non-use.
        if any(r['primary_label']=='FP' for r in (aa,bb)):
            reasons.append('false_positive_requires_specific_evidence_review')
        exceptions={'input_quality','conflicting_evidence','citation_link_uncertain','low_confidence','original_vs_downstream'}
        if any(exceptions.intersection(r['human_review_reasons']) for r in (aa,bb)):reasons.append('evidence_exception')
    return ('model_c_review' if reasons else 'agreement_pending_semantic_check'),reasons


def load_results(model, packets):
    path=OUTPUTS/f'model_{model}_smoke20_v1.jsonl'
    artifact=path.with_name(path.stem+'.artifacts')
    manifests=sorted(artifact.glob('*/run_manifest.json'))
    require(manifests, 'Missing finished model archive: '+model)
    pins=[]
    for mp in manifests:
        subprocess.run([sys.executable,str(ROOT/'code/10_verify_model_run_artifact.py'),str(mp.parent)],check=True)
        pins.append(pin(mp));pins.append(pin(mp.with_suffix('.json.sha256')))
    # The archive verifier proves frozen files are intact; also prove the
    # current cumulative success file is exactly its archived union.
    historical=[]
    for mp in manifests:
        m=json.loads(mp.read_text())
        entry=m['archived_records'].get('validated')
        if entry: historical.extend(read_jsonl(mp.parent/entry['snapshot_path']))
    rows=read_jsonl(path) if path.is_file() else []
    require(sorted(map(fingerprint,rows))==sorted(map(fingerprint,historical)),
            'Current cumulative output differs from frozen archive union: '+model)
    spec=importlib.util.spec_from_file_location('closure_original_review_runner',RUNNER)
    engine=importlib.util.module_from_spec(spec);spec.loader.exec_module(engine)
    validator=Draft202012Validator(json.loads(SCHEMA.read_text()))
    result={}
    for row in rows:
        wid=row['work_id'];require(wid in packets and wid not in result,'Unknown/duplicate model output')
        require(row['input_packet_sha256']==fingerprint(packets[wid]),'Model input fingerprint differs')
        require(row['model']==PROFILES[model]['model'] and row['provider']==PROFILES[model]['provider'],'Profile differs')
        require(row['run_signature']['schema_sha256']==sha(SCHEMA),'Schema differs')
        require(not engine.validate_review(row['response'],packets[wid],validator),'Output fails current original validator')
        result[wid]=row
    for file in (path,path.with_name(path.stem+'.errors.jsonl'),path.with_name(path.stem+'.attempts.jsonl')):
        if file.is_file():pins.append(pin(file))
    return result,pins


def assemble():
    verify_inputs()
    packets=read_jsonl(INPUTS/'smoke20_model_inputs.jsonl');by_id={p['work_id']:p for p in packets}
    a,ap=load_results('a',by_id);b,bp=load_results('b',by_id)
    records=[];c=[]
    for packet in packets:
        wid=packet['work_id'];status,reasons=route(a.get(wid),b.get(wid))
        records.append({'work_id':wid,'route':status,'reasons':'|'.join(reasons),
                        'a_valid':wid in a,'b_valid':wid in b,
                        **{'a_'+k:a[wid]['response'][k] if wid in a else None for k in CORE},
                        **{'b_'+k:b[wid]['response'][k] if wid in b else None for k in CORE}})
        if status=='model_c_review':c.append(packet)
    summary={'pilot_works':20,'a_valid':len(a),'b_valid':len(b),
             'paired_valid':len(set(a)&set(b)),'c_routed':len(c),
             'routes':dict(Counter(r['route'] for r in records)),
             'core_fields':list(CORE),'observed_actions_excluded':True,
             'semantic_approval':False,'full_queue_ready':False,'independent_human_gold':False}
    return records,c,summary,ap+bp+[pin(INPUTS/'run_manifest.json')]


def verify_c_route():
    m=json.loads((OUT/'run_manifest.json').read_text())
    require(inventory(OUT)==m['outputs'],'Comparison archive changed')
    for p in m['inputs']:require(sha(p['path'])==p['sha256'],'A/B input/output changed after C routing')
    packets=read_jsonl(INPUTS/'smoke20_model_inputs.jsonl');by_id={p['work_id']:p for p in packets}
    routed=read_jsonl(OUT/'smoke20_c_inputs.jsonl')
    require(all(p==by_id[p['work_id']] for p in routed),'C must receive identical evidence, not model answers')
    require(len(routed)==m['summary']['c_routed'],'C route count differs')
    return m['summary']


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--verify-only',action='store_true')
    args=p.parse_args()
    if args.verify_only:print('C route integrity: PASS;',verify_c_route());return
    rows,packets,summary,pins=assemble()
    out=destination(OUT);stage=Path(tempfile.mkdtemp(prefix='.closure-pilot-comparison-',dir=MODULE));stage.chmod(0o700)
    from prepare_evidence_closure_api_v1 import write_jsonl
    write_csv(stage/'ab_comparison_private.csv',rows,list(rows[0]));write_jsonl(stage/'smoke20_c_inputs.jsonl',packets)
    write_json(stage/'summary.json',summary)
    write_json(stage/'run_manifest.json',{'schema':'figure1-closure-smoke-comparison-v1','inputs':pins,'summary':summary,'outputs':inventory(stage)})
    stage.rename(out);verify_c_route()
    print('A/B verified; C route:',summary,'; no semantic acceptance or merge')


if __name__=='__main__':main()
