"""Freeze public-supplemented input, preserve original decisions and core rules."""
from collections import Counter
import copy
import hashlib
import json
from pathlib import Path
from evidence_closure_api_v1 import SOURCE, verify_inputs, read_jsonl, fingerprint, substantive_abstract
from prepare_evidence_closure_api_v2 import repair_packet, verify as verify_v2, DOIS
from prepare_evidence_closure_api_v1 import write_jsonl
from fetch_public_evidence import inventory
from local_recall import MODULE, destination, pin, sha, write_json, require

PUBLIC=MODULE/'evidence_closure_public_v4'
STABLE=MODULE/'evidence_closure_api_stable_inputs_v3'
OUT=MODULE/'evidence_closure_api_inputs_v3'

def stable():
    verify_v2(); source=json.loads((SOURCE/'packets_private.json').read_text())
    body_ids={r['work_id'] for r in source if r['body_document_path']}
    ps=read_jsonl(MODULE/'evidence_closure_api_inputs_v2/closure586_model_inputs.jsonl')
    ps=[p for p in ps if p['work_id'] in body_ids]
    destination(STABLE).mkdir(mode=0o700)
    write_jsonl(STABLE/'stable_body_inputs.jsonl',ps)
    write_json(STABLE/'run_manifest.json',{'schema':'closure-stable-before-public-v3','inputs':[pin(SOURCE/'packets_private.json'),pin(MODULE/'evidence_closure_api_inputs_v2/run_manifest.json')],
       'outputs':inventory(STABLE),'summary':{'stable_body_works':len(ps),'api_eligible':sum(p['model_eligible'] for p in ps),
       'reason':'Public v4 targets only the other 430 missing-body works; stable packets are byte-equivalent to v2 and will be checked against full v3.'}})
    print('Stable body input frozen:',len(ps),'works',flush=True)

def full():
    verify_v2()
    m=json.loads((PUBLIC/'run_manifest.json').read_text()); require(inventory(PUBLIC)==m['outputs'],'Public supplement changed')
    rows=copy.deepcopy(json.loads((SOURCE/'packets_private.json').read_text()))
    updates={r['work_id']:r for r in json.loads((PUBLIC/'results_private.json').read_text())}
    body_source=MODULE/'evidence_closure_public_bodies_v5'
    bm=json.loads((body_source/'run_manifest.json').read_text()); require(inventory(body_source)==bm['outputs'],'Body follow-up changed')
    body_updates={r['work_id']:r for r in json.loads((body_source/'results_private.json').read_text()) if r.get('body_path')}
    public_abstract_used=0; bodies=0; identity_holds=[]
    for row in rows:
        r=updates.get(row['work_id'])
        if not r: continue
        if r.get('title_similarity') is None or r['title_similarity']<.8:
            identity_holds.append(row['work_id']); continue
        if r.get('abstract') and substantive_abstract(r['abstract'],row['title']):
            # Both texts retained privately. Prefer exact-source addition only
            # after DOI/identifier and title checks; keep source version/date.
            text=r['abstract']
            row['abstract_variants'].insert(0,{'source_kind':'public_abstract','source':r['source']+'_exact_identity_supplement_v4',
               'text':text,'quality':{'structural_status':'usable','sha256':hashlib.sha256(text.encode()).hexdigest()}})
            row['public_lookup']['metadata_title']=r['metadata_title']; public_abstract_used+=1
        if r.get('body_path'):
            require(sha(r['body_path'])==r['body_sha256'],'Public body hash differs')
            row.update(body_document_path=r['body_path'],body_document_sha256=r['body_sha256']); bodies+=1
        elif row['work_id'] in body_updates:
            b=body_updates[row['work_id']]; require(sha(b['body_path'])==b['body_sha256'],'Follow-up body hash differs')
            row.update(body_document_path=b['body_path'],body_document_sha256=b['body_sha256']); bodies+=1
    pairs=[repair_packet(r) for r in rows]; packets=[p[0] for p in pairs]
    # Exact Crossref bibliography metadata is a different evidence source from
    # literal manuscript references. Preserve that distinction, never make it
    # into procedural/E3 evidence or imply an in-text citation has been linked.
    from fetch_public_evidence import norm_doi
    from evidence_closure_api_v1 import prepare_packet, CAP
    metadata_refs=0
    for packet,private in pairs:
        r=updates.get(packet['work_id'])
        if not r or r.get('source')!='crossref' or (r.get('title_similarity') or 0)<.8: continue
        refs=[ref for ref in r.get('reference_metadata',[]) if norm_doi(ref.get('DOI')) in DOIS]
        if not refs: continue
        for ref in refs:
            text=json.dumps(ref,ensure_ascii=False,sort_keys=True)
            packet['input_material']['matched_seed_references'].append({'reference_text':text,
               'matched_target':DOIS[norm_doi(ref['DOI'])], 'evidence_role':'bibliographic_identity_only',
               'source_kind':'crossref_deposited_reference_metadata_not_body',
               'limitation':'Exact-DOI Crossref reference record; not a literal body excerpt, not proof of use/execution or in-text linkage.'})
            private['reference_source_map'].append({'source_path':str(PUBLIC/'records'/(packet['work_id']+'.json')),
               'source_sha256':sha(PUBLIC/'records'/(packet['work_id']+'.json')),'source_kind':'crossref_reference_metadata',
               'text_sha256':hashlib.sha256(text.encode()).hexdigest()})
            metadata_refs+=1
        packet.update(prepare_packet(packet))
        if packet['model_eligible'] and packet['estimated_input_tokens']>CAP:
            packet.update(production_protocol='figure1-closure-api-v3',evidence_tier='oversize_context_human_review',
               model_eligible=False,forced_decision={'label':'U','reason':'Complete supplemented packet exceeds 30,000 estimated tokens; manual evidence review, not non-use.'})
            packet.update(prepare_packet(packet))
        private['input_packet_sha256']=fingerprint(packet)
    byid={p['work_id']:p for p in packets}
    for p in read_jsonl(STABLE/'stable_body_inputs.jsonl'):
        require(p==byid[p['work_id']],'Stable evidence unexpectedly changed; no mixed-input continuation')
    destination(OUT).mkdir(mode=0o700)
    write_jsonl(OUT/'closure586_model_inputs.jsonl',packets)
    write_json(OUT/'provenance_private.json',[p[1] for p in pairs])
    write_json(OUT/'evidence_rows_private.json',rows)
    summary={'queue_works':len(packets),'api_eligible':sum(p['model_eligible'] for p in packets),
      'tiers':dict(Counter(p['evidence_tier'] for p in packets)),'new_abstract_variants_used':public_abstract_used,
      'new_bodies':bodies,'identity_hold_works':identity_holds,'crossref_metadata_AF_references':metadata_refs,
      'public_http_sends':m['summary']['http_sends']+bm['summary']['http_sends'],
      'old_prompt_schema_retained':True,'old_core_labels_changed':False,'semantic_acceptance':False}
    write_json(OUT/'summary.json',summary)
    write_json(OUT/'run_manifest.json',{'schema':'closure-public-input-freeze-v3',
      'inputs':[pin(PUBLIC/'run_manifest.json'),pin(body_source/'run_manifest.json'),pin(SOURCE/'packets_private.json'),pin(Path(__file__)),pin(MODULE/'prepare_evidence_closure_api_v2.py')],
      'summary':summary,'outputs':inventory(OUT)})
    print('Full v3 inputs frozen:',summary,flush=True)

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(); p.add_argument('--stable',action='store_true'); a=p.parse_args()
    stable() if a.stable else full()
