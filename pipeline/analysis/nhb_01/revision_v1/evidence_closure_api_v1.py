"""Adapt the frozen closure evidence to the original core-review runner.

No prior decisions or recall signals are sent to models. This module does not
download evidence, approve semantics, change the accepted layer, or merge works.
"""
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
import sys

from local_recall import MODULE, ROOT, pin, require, sha
from prepare_evidence_closure import OUT as SOURCE, verify as verify_source
from fetch_public_evidence import inventory

sys.path.insert(0, str(ROOT / 'code'))
from fulltext_pipeline.model_review_support import prepare_packet, fingerprint

INPUTS = MODULE / 'evidence_closure_api_inputs_v1'
OUTPUTS = MODULE / 'evidence_closure_api_smoke_v1'
PROMPT = ROOT / 'config/af_review_prompt_v4.txt'
SCHEMA = ROOT / 'config/af_review_output_schema_v2.json'
RUNNER = ROOT / 'code/08_run_model_review.py'
CAP = 30000
PROFILES = {
    'a': {'provider':'deepseek', 'endpoint':'https://api.deepseek.com/chat/completions',
          'api_style':'chat_completions', 'model':'deepseek-v4-flash',
          'api_key_env':'DEEPSEEK_API_KEY', 'thinking':'enabled',
          'reasoning_effort':'high', 'response_format':'json_object'},
    'b': {'provider':'zhipu_cn', 'endpoint':'https://open.bigmodel.cn/api/paas/v4/chat/completions',
          'api_style':'chat_completions', 'model':'glm-5.3-flash',
          'api_key_env':'ZHIPU_API_KEY', 'thinking':'enabled',
          'reasoning_effort':'high', 'response_format':'json_object'},
    'c': {'provider':'openrouter', 'endpoint':'https://openrouter.ai/api/v1/responses',
          'api_style':'responses', 'model':'openai/gpt-5.6-luna',
          'api_key_env':'OPENROUTER_API_KEY', 'thinking':'none',
          'reasoning_effort':'xhigh', 'response_format':'json_schema'},
}
ADMIN = re.compile(r'^(?:references?|bibliography|acknowledg\w*|funding|footnotes?|'
                   r'author\w* contributions?|declaration\w*|conflict\w*|competing interests?|'
                   r'data availability|supplementary (?:material|data))\b', re.I)


def substantive_abstract(text, title):
    from fulltext_pipeline.model_review_support import abstract_status
    if abstract_status(text, title) != 'usable':
        return False
    normalized = ' '.join(re.sub(r'<[^>]+>', ' ', text).lower().split()).strip(' .')
    # A known metadata-only abstract observed in this corpus. Do not reject
    # real abstracts merely because they include a supplementary-data sentence.
    return normalized not in {
        'supplementary data are available at bioinformatics online',
        'supplementary information is available at bioinformatics online',
    }


def build_packet(row):
    title = row['title']
    variants = [a for a in row['abstract_variants'] if substantive_abstract(a['text'], title)]
    # Public exact-DOI identity may have a different title/version. Fall back
    # conservatively to local text when public title similarity is poor.
    import difflib
    norm = lambda x: ' '.join(re.sub(r'<[^>]+>', ' ', x or '').lower().split())
    public_title = row['public_lookup'].get('metadata_title')
    similarity = difflib.SequenceMatcher(None, norm(title), norm(public_title), autojunk=False).ratio()
    preferred = next((a for a in variants if a['source_kind']=='public_abstract' and similarity >= .80), None)
    preferred = preferred or next((a for a in variants if a['source_kind']=='local_abstract'), None)
    # Identity-different public abstracts are retained in the private archive,
    # not silently passed as this paper's scientific evidence.
    blocks = []
    source_map = []
    if row['body_document_path']:
        path = Path(row['body_document_path'])
        require(path.resolve().is_relative_to(MODULE) and not path.is_symlink(), 'Invalid body path')
        require(sha(path)==row['body_document_sha256'], 'Body fingerprint differs')
        doc = json.loads(path.read_text())
        require(doc.get('work_id')==row['work_id'] and doc.get('full_text_available') is True,
                'Body identity/availability differs')
        for i, section in enumerate(doc.get('sections', [])):
            name = section.get('title') or ''
            text = section.get('text') or ''
            if not text.strip() or ADMIN.match(name) or name.strip().lower() in {'title','abstract'}:
                continue
            index = len(blocks)
            blocks.append({'index':index,'role':'evidence','section':name,
                           'block_type':'body_section','text':text})
            source_map.append({'block_index':index,'source_section_index':i,
                               'source_path':str(path),'source_sha256':sha(path),
                               'text_sha256':hashlib.sha256(text.encode()).hexdigest()})
    packet = prepare_packet({
        'schema_version':'af-model-review-input-v2', 'review_id':row['work_id'],
        'work_id':row['work_id'], 'context_policy':{
            'version':'figure1-closure-whole-extracted-scientific-sections-v1',
            'full_document_included':False,
            'all_available_scientific_body_sections_included':True,
            'bibliography_and_administrative_sections_excluded':True,
            'limitations':'Extraction may omit tables, equations and supplements; no claim of complete publisher full text.',
        },
        'input_material':{'title':title,'abstract':preferred['text'] if preferred else None,
                          'publication_year':row['publication_year'],'work_type':row['work_type'],
                          'doi':row['doi'],'evidence_blocks':blocks,'matched_seed_references':[]},
    })
    oversize = packet['model_eligible'] and packet['estimated_input_tokens'] > CAP
    if oversize:
        # Existing runner respects this explicit production-oversize routing;
        # preserve every block, never silently truncate evidence for an API call.
        packet.update(production_protocol='figure1-closure-api-v1',
                      evidence_tier='oversize_context_human_review', model_eligible=False,
                      forced_decision={'label':'U','reason':'Complete scientific-section packet exceeds 30,000 estimated tokens; manual evidence review, not a non-use decision.'})
        packet = prepare_packet(packet)
    private = {'work_id':row['work_id'],'review_id':row['review_id'],
               'abstract_source_kind':preferred['source_kind'] if preferred else None,
               'abstract_source':preferred['source'] if preferred else None,
               'abstract_sha256':hashlib.sha256(preferred['text'].encode()).hexdigest() if preferred else None,
               'public_title_similarity':similarity,'body_source_map':source_map,
               'prior_route':row['prior_route'],'manual_review_status':'retained_separately_not_model_resume_credit',
               'input_packet_sha256':fingerprint(packet)}
    require(prepare_packet(packet)==packet, 'Packet sanitizer is not idempotent')
    return packet, private


def choose_smoke(packets):
    eligible = {p['work_id']:p for p in packets if p['model_eligible']}
    # Three 2019 preprints and two directly-read early full texts; selection
    # uses identities/evidence availability, not model or prior outcome labels.
    fixed = ['W2952771283','W2979255327','W2990374534','W3025755767','W3062307266']
    chosen = [wid for wid in fixed if wid in eligible]
    require(len(chosen)==5, 'Expected boundary fixtures not API eligible')
    buckets = defaultdict(list)
    for wid,p in eligible.items():
        if wid in chosen: continue
        key = (p['input_material']['publication_year'],p['evidence_tier'])
        buckets[key].append(wid)
    for values in buckets.values():
        values.sort(key=lambda wid:hashlib.sha256(('figure1-closure-smoke20-v1:'+wid).encode()).hexdigest())
    keys = sorted(buckets)
    while len(chosen)<20:
        previous=len(chosen)
        for key in keys:
            if buckets[key] and len(chosen)<20: chosen.append(buckets[key].pop(0))
        require(len(chosen)>previous, 'Insufficient eligible smoke candidates')
    return chosen


def assemble():
    verify_source(SOURCE)
    rows=json.loads((SOURCE/'packets_private.json').read_text())
    pairs=[build_packet(r) for r in rows]
    packets=[x[0] for x in pairs]; private=[x[1] for x in pairs]
    ids=choose_smoke(packets)
    summary={'queue_works':len(packets),'api_eligible':sum(p['model_eligible'] for p in packets),
             'tiers':dict(Counter(p['evidence_tier'] for p in packets)),
             'estimated_tokens_per_model':sum(p['estimated_input_tokens'] for p in packets if p['model_eligible']),
             'smoke_works':len(ids),'smoke_estimated_tokens_per_model':sum(p['estimated_input_tokens'] for p in packets if p['work_id'] in ids),
             'public_downloads':0,'paid_llm_calls':0,'approvals_or_merges':0,
             'manual52_preserved':True,'independent_human_gold':False,
             'full_queue_api_gate':'pending_smoke_semantic_review',
             'smoke_plan':'A and B independent; C for core disagreements/uncertainty/failure only; no validation retries',
             'core_fields':['af_use_label','adoption_eligible','relevance_level','evidence_level','primary_label','af_related_label'],
             'observed_actions_in_core_agreement':False}
    pins=[pin(SOURCE/'packets_private.json'),pin(SOURCE/'run_manifest.json'),pin(PROMPT),pin(SCHEMA),pin(RUNNER),pin(Path(__file__)),
          pin(ROOT/'code/fulltext_pipeline/model_review_support.py')]
    return packets, private, ids, summary, pins


def read_jsonl(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def verify_inputs(directory=INPUTS):
    manifest=json.loads((directory/'run_manifest.json').read_text())
    require(inventory(directory)==manifest['outputs'], 'Input archive inventory changed')
    for p in manifest['inputs']: require(sha(p['path'])==p['sha256'], 'Pinned input/code changed')
    packets=read_jsonl(directory/'closure586_model_inputs.jsonl')
    smoke=read_jsonl(directory/'smoke20_model_inputs.jsonl')
    require(len(packets)==586 and len(smoke)==20, 'Queue/smoke count differs')
    expected=json.loads((directory/'smoke20_ids.json').read_text())
    require([p['work_id'] for p in smoke]==expected, 'Smoke order differs')
    by_id={p['work_id']:p for p in packets}
    require(len(by_id)==586 and all(p==by_id[p['work_id']] for p in smoke), 'Smoke/frozen packet identity differs')
    require(all(prepare_packet(p)==p for p in packets), 'Sanitizer/signature differs')
    forbidden={'prior_route','prior_accepted_decision','recall_signals','semantic_review_status','country','institution'}
    require(all(not forbidden.intersection(p) and not forbidden.intersection(p['input_material']) for p in packets), 'Blinding violated')
    return manifest
